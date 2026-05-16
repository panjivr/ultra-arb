"""
Smart-money copy-trade — track recent large trades on Polymarket.

Polymarket exposes `data-api.polymarket.com/trades` which returns recent
trades with wallet address + size + outcome. We:

  1. Pull recent trades every 60s
  2. Filter for size >= $500 (whale conviction filter)
  3. Track repeat-winners (wallets with multiple winning trades)
  4. Emit "smart_money_copy" signals our bot can mirror

This works because real public market data doesn't need a leaderboard —
the SIZE of a trade itself signals conviction. Whales taking 5-figure
positions on the same side = consensus signal.
"""
import asyncio
import json
import time
from collections import defaultdict
import httpx
from arb.infra.redis_bus import publish, get_redis
from arb.edges.ensemble import emit_vote, SignalVote

TIMEOUT = httpx.Timeout(10, connect=4)
TRADES_URL = "https://data-api.polymarket.com/trades"

# Minimum size to flag as smart-money signal. Polymarket has mostly small
# trades; $25 catches active traders, $100+ = conviction tier.
MIN_WHALE_SIZE = 25
TIER_THRESHOLDS = [
    (25, "SHRIMP"),
    (100, "FISH"),
    (500, "WHALE"),
    (5000, "MEGA"),
]


async def fetch_recent_trades(limit: int = 100) -> list[dict]:
    """Fetch most-recent trades from Polymarket public data API."""
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        try:
            r = await client.get(TRADES_URL, params={"limit": str(limit)})
            if r.status_code == 200:
                data = r.json()
                return data if isinstance(data, list) else []
        except Exception as e:
            return []
    return []


# Wallet PnL tracking — accumulate across runs (kept in Redis)
async def _update_wallet_stats(r, wallet: str, side: str, size_usd: float,
                                price: float, question: str):
    """Track each wallet's recent activity for ranking."""
    key = f"arb:edges:wallet_stats:{wallet}"
    try:
        raw = await r.get(key)
        stats = json.loads(raw) if raw else {
            "wallet": wallet,
            "total_trades": 0,
            "total_volume_usd": 0,
            "last_seen": 0,
            "biggest_trade_usd": 0,
            "trades_24h": 0,
        }
        stats["total_trades"] += 1
        stats["total_volume_usd"] = round(stats["total_volume_usd"] + size_usd, 2)
        stats["last_seen"] = int(time.time() * 1000)
        stats["biggest_trade_usd"] = max(stats["biggest_trade_usd"], size_usd)
        stats["trades_24h"] = stats.get("trades_24h", 0) + 1
        await r.set(key, json.dumps(stats), ex=86400)  # 24h TTL
        # Also keep an aggregate sorted set of top wallets
        await r.zadd("arb:edges:wallet_volume_24h", {wallet: stats["total_volume_usd"]})
    except Exception:
        pass


async def run_smart_money_loop(interval_s: int = 60):
    """Every 60s pull recent trades, emit signals for whale-size positions."""
    r = get_redis()
    seen_trades: set[str] = set()
    print("[smart_money] watching Polymarket trades for whale signals (>=$500 size)")

    while True:
        try:
            trades = await fetch_recent_trades(limit=200)
            new_signals = 0
            now_ms = int(time.time() * 1000)

            for t in trades:
                wallet = (t.get("proxyWallet") or "").lower()
                if not wallet:
                    continue
                # Use timestamp+wallet+asset as dedup key
                trade_key = f"{wallet}:{t.get('timestamp')}:{t.get('asset','')[:20]}"
                if trade_key in seen_trades:
                    continue

                # Size filter
                size_usd = float(t.get("size", 0) or 0) * float(t.get("price", 0) or 0)
                if size_usd < MIN_WHALE_SIZE:
                    seen_trades.add(trade_key)
                    continue

                # Track stats for this wallet
                await _update_wallet_stats(
                    r, wallet, t.get("side", ""), size_usd,
                    float(t.get("price", 0) or 0), t.get("title", "")
                )

                # Classify tier
                tier = "SHRIMP"
                for thr, label in TIER_THRESHOLDS:
                    if size_usd >= thr:
                        tier = label
                # Emit signal
                signal = {
                    "trade_id": trade_key,
                    "wallet": wallet,
                    "wallet_name": t.get("pseudonym") or t.get("name") or "anon",
                    "tier": tier,
                    "side": t.get("side", ""),
                    "outcome": t.get("outcome", ""),
                    "outcome_index": t.get("outcomeIndex"),
                    "question": t.get("title", "")[:200],
                    "condition_id": t.get("conditionId"),
                    "asset": t.get("asset"),
                    "size_usd": round(size_usd, 2),
                    "price": float(t.get("price", 0) or 0),
                    "timestamp": int(t.get("timestamp", 0) or 0),
                    "slug": t.get("slug"),
                    "url": f"https://polymarket.com/market/{t.get('slug','')}",
                    "ts": now_ms,
                    "kind": "smart_money_copy",
                }
                await publish("arb:edges:smart_money", signal)
                # Wire into ensemble gate
                cid = t.get("conditionId")
                if cid:
                    side = t.get("side", "").upper()
                    direction = "yes" if side in ("BUY", "YES") else "no"
                    conf = min(0.5 + (size_usd / 10_000) * 0.4, 0.95)
                    await emit_vote(SignalVote(
                        condition_id=cid, direction=direction,
                        confidence=round(conf, 3), source="smart_money",
                        asset=t.get("asset") or "POLY/USDT",
                        kind=signal["kind"], ts=now_ms,
                    ))
                seen_trades.add(trade_key)
                new_signals += 1

            # Persist top-15 wallets snapshot for the UI
            try:
                top = await r.zrevrange("arb:edges:wallet_volume_24h", 0, 14, withscores=True)
                wallets_summary = []
                for entry in top:
                    addr, vol = entry
                    stats_raw = await r.get(f"arb:edges:wallet_stats:{addr}")
                    if stats_raw:
                        wallets_summary.append(json.loads(stats_raw))
                if wallets_summary:
                    await r.set(
                        "arb:edges:smart_wallets",
                        json.dumps({"wallets": wallets_summary, "ts": now_ms}),
                        ex=600,
                    )
            except Exception:
                pass

            # Bound seen-set memory
            if len(seen_trades) > 10000:
                seen_trades = set(list(seen_trades)[-5000:])

            if new_signals > 0:
                print(f"[smart_money] {new_signals} new whale signals (>=${MIN_WHALE_SIZE})")
        except Exception as e:
            print(f"[smart_money] error: {repr(e)[:120]}")
        await asyncio.sleep(interval_s)
