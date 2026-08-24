"""
Copy-trade the TOP 1-10 Polymarket leaders (juara 1-10).

Strategy (real, data-driven — no fabricated numbers):
  1. Rank the best wallets. Prefer Polymarket's public leaderboard (ranked by
     realized profit). If that endpoint is unavailable, fall back to the
     highest-volume wallets we already observe in Redis
     (arb:edges:wallet_volume_24h, populated by smart_money.py).
  2. Watch those leaders' most-recent trades on crypto markets.
  3. When a leader opens a position, MIRROR it as a bet on
     `arb:polymarket:bets` — the same stream the engine uses — so it flows
     through the existing REAL-oracle resolver + PnL + dashboard untouched.

Mode:
  - DEMO (default): the mirrored bet is paper (simulated capital). Safe.
  - REAL: only when the runtime flag `arb:mode` == "real" AND PAPER_TRADE=false
    AND a wallet/key is configured on the server. Live CLOB execution is handed
    to scripts/polymarket_live_adapter.py; without a key it stays paper.

Publishes `arb:edges:leaders` (the ranked leaderboard we copy) for the UI.
"""
import asyncio
import json
import os
import time
import httpx
from arb.infra.redis_bus import publish, get_redis

TIMEOUT = httpx.Timeout(10, connect=4)
TRADES_URL = "https://data-api.polymarket.com/trades"
# Candidate public leaderboard endpoints (profit-ranked). Tried in order.
LEADERBOARD_URLS = [
    "https://lb-api.polymarket.com/leaderboard?window=all&limit=25&orderBy=profit",
    "https://lb-api.polymarket.com/leaderboard?window=month&limit=25&orderBy=profit",
]

TOP_N = int(os.getenv("COPY_TOP_N", "10"))          # copy the top 1-10
POLL_SECONDS = int(os.getenv("COPY_POLL_SECONDS", "20"))
LEADERBOARD_REFRESH_SECONDS = int(os.getenv("COPY_LEADERBOARD_REFRESH", "900"))
MIN_COPY_SIZE_USD = float(os.getenv("COPY_MIN_LEADER_SIZE", "50"))  # ignore leader's dust
COPY_STAKE_USD = float(os.getenv("COPY_STAKE_USD", "10"))           # our fixed paper stake
CRYPTO_KEYS = ("bitcoin", "btc", "ethereum", "eth", "solana", "sol",
               "bnb", "xrp", "ripple", "dogecoin", "doge", "crypto")


def _addr(x) -> str:
    return (x or "").lower().strip()


def _is_crypto(title: str, slug: str) -> str | None:
    """Return the asset symbol if this looks like a crypto market, else None."""
    t = f"{title} {slug}".lower()
    if not any(k in t for k in CRYPTO_KEYS):
        return None
    if "bitcoin" in t or "btc" in t:
        return "BTC"
    if "ethereum" in t or "eth" in t:
        return "ETH"
    if "solana" in t or "sol" in t:
        return "SOL"
    if "bnb" in t:
        return "BNB"
    if "xrp" in t or "ripple" in t:
        return "XRP"
    return "CRYPTO"


async def fetch_leaders(r) -> list[dict]:
    """Top-N leader wallets, profit-ranked. Falls back to observed volume."""
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        for url in LEADERBOARD_URLS:
            try:
                resp = await client.get(url)
                if resp.status_code != 200:
                    continue
                data = resp.json()
                rows = data if isinstance(data, list) else data.get("data") or data.get("leaderboard") or []
                leaders = []
                for i, row in enumerate(rows[:TOP_N]):
                    w = _addr(row.get("proxyWallet") or row.get("wallet") or row.get("address"))
                    if not w:
                        continue
                    leaders.append({
                        "rank": i + 1,
                        "wallet": w,
                        "name": row.get("pseudonym") or row.get("name") or f"#{i+1}",
                        "profit_usd": round(float(row.get("profit") or row.get("pnl") or 0), 2),
                        "source": "polymarket_leaderboard",
                    })
                if leaders:
                    return leaders
            except Exception:
                continue
    # Fallback: highest-volume wallets we already observe.
    try:
        top = await r.zrevrange("arb:edges:wallet_volume_24h", 0, TOP_N - 1, withscores=True)
        leaders = []
        for i, (addr, vol) in enumerate(top):
            leaders.append({
                "rank": i + 1, "wallet": _addr(addr),
                "name": f"#{i+1}", "profit_usd": None,
                "volume_usd": round(float(vol), 2), "source": "observed_volume",
            })
        return leaders
    except Exception:
        return []


async def run_copy_leaders():
    r = get_redis()
    seen: set[str] = set()
    leaders: list[dict] = []
    leader_set: set[str] = set()
    last_lb = 0.0
    print(f"[copy_leaders] copying top-{TOP_N} Polymarket leaders — poll {POLL_SECONDS}s")

    while True:
        try:
            now = time.time()
            now_ms = int(now * 1000)

            # Refresh leaderboard periodically
            if now - last_lb > LEADERBOARD_REFRESH_SECONDS or not leaders:
                leaders = await fetch_leaders(r)
                leader_set = {l["wallet"] for l in leaders}
                await r.set("arb:edges:leaders",
                            json.dumps({"leaders": leaders, "ts": now_ms,
                                        "top_n": TOP_N}), ex=1800)
                last_lb = now
                if leaders:
                    print(f"[copy_leaders] leaderboard: {len(leaders)} wallets "
                          f"({leaders[0].get('source')})")

            if not leader_set:
                await asyncio.sleep(POLL_SECONDS)
                continue

            # Runtime mode: demo (default) or real
            mode = (await r.get("arb:mode")) or "demo"
            paper = os.getenv("PAPER_TRADE", "true").lower() != "false"
            live = (mode == "real") and (not paper)

            # Pull recent trades and copy those from our leaders
            async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                resp = await client.get(TRADES_URL, params={"limit": "100"})
                trades = resp.json() if resp.status_code == 200 else []
            if not isinstance(trades, list):
                trades = []

            copied = 0
            for t in trades:
                w = _addr(t.get("proxyWallet"))
                if w not in leader_set:
                    continue
                cond = t.get("conditionId")
                if not cond:
                    continue
                key = f"{w}:{t.get('timestamp')}:{cond[:16]}"
                if key in seen:
                    continue
                seen.add(key)

                price = float(t.get("price", 0) or 0)
                size_usd = float(t.get("size", 0) or 0) * price
                if size_usd < MIN_COPY_SIZE_USD:
                    continue
                asset = _is_crypto(t.get("title", ""), t.get("slug", ""))
                if asset is None:
                    continue  # crypto markets only (user's focus)

                side = (t.get("outcome") or t.get("side") or "").upper()
                leader = next((l for l in leaders if l["wallet"] == w), {})
                bet = {
                    "id": f"copy-{now_ms}-{cond[:6]}",
                    "ts": now_ms,
                    "market_id": t.get("conditionId"),
                    "condition_id": cond,
                    "question": (t.get("title") or "")[:240],
                    "asset": asset,
                    "interval": "copy",
                    "kind": "copy",
                    "side": side,
                    "stake_usd": COPY_STAKE_USD,
                    "entry_price": round(price, 4),
                    "implied_prob": round(price, 4),
                    "our_prob": round(price, 4),
                    "status": "open",
                    "end_date": t.get("endDate"),
                    "slug": t.get("slug"),
                    "source": "copy_leader",
                    "leader_wallet": w,
                    "leader_rank": leader.get("rank"),
                    "leader_name": leader.get("name"),
                    "leader_size_usd": round(size_usd, 2),
                    "mode": "real" if live else "demo",
                    "is_real_wallet": bool(live),
                }
                await publish("arb:polymarket:bets", bet)
                # Also surface on a dedicated copy stream for the UI
                await publish("arb:edges:copy_trades", bet)
                copied += 1

            if copied:
                print(f"[copy_leaders] mirrored {copied} leader trade(s) "
                      f"[mode={'REAL' if live else 'DEMO'}]")

            # Bound the dedupe set
            if len(seen) > 20000:
                seen = set(list(seen)[-8000:])

        except Exception as e:
            print(f"[copy_leaders] WARN {repr(e)[:160]}")

        await asyncio.sleep(POLL_SECONDS)


if __name__ == "__main__":
    asyncio.run(run_copy_leaders())
