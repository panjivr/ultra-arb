"""
Copy-trade the TOP Polymarket champions (juara 1-N) — precision edition.

Precision (higher win potential, not just more volume):
  - Rank weighting: a rank-1 champion's move counts more than rank-15's.
  - Consensus: when 2+ champions take the SAME side on the SAME market inside a
    short window, conviction jumps — agreement among winners is the strongest
    signal. Those get a bigger stake.
  - Conviction gate: only mirror trades above a conviction threshold, and size
    the bet by conviction (Kelly-ish), so weak singletons are skipped and strong
    consensus is pressed.

Frequency: a wide champion net (top-N) + fast polling + a modest size floor
means a bet lands whenever any champion moves on any crypto ticker — typically
several times per hour, clustered around volatile minutes.

Mirrored bets go to `arb:polymarket:bets` (existing real-oracle resolver + PnL).
Publishes `arb:edges:leaders` and `arb:edges:copy_trades` for the UI.
"""
import asyncio
import json
import os
import time
import httpx
from arb.infra.redis_bus import publish, get_redis

TIMEOUT = httpx.Timeout(10, connect=4)
TRADES_URL = "https://data-api.polymarket.com/trades"
LEADERBOARD_URLS = [
    "https://lb-api.polymarket.com/leaderboard?window=all&limit=40&orderBy=profit",
    "https://lb-api.polymarket.com/leaderboard?window=month&limit=40&orderBy=profit",
]

TOP_N = int(os.getenv("COPY_TOP_N", "15"))                 # champion net width
POLL_SECONDS = int(os.getenv("COPY_POLL_SECONDS", "15"))
LEADERBOARD_REFRESH_SECONDS = int(os.getenv("COPY_LEADERBOARD_REFRESH", "900"))
MIN_COPY_SIZE_USD = float(os.getenv("COPY_MIN_LEADER_SIZE", "25"))
BASE_STAKE_USD = float(os.getenv("COPY_STAKE_USD", "10"))
MIN_CONVICTION = float(os.getenv("COPY_MIN_CONVICTION", "0.60"))
CONSENSUS_WINDOW_S = int(os.getenv("COPY_CONSENSUS_WINDOW", "600"))  # 10 min
CRYPTO_KEYS = ("bitcoin", "btc", "ethereum", "eth", "solana", "sol",
               "bnb", "xrp", "ripple", "dogecoin", "doge", "cardano", "ada",
               "polkadot", "dot", "crypto")


def _addr(x) -> str:
    return (x or "").lower().strip()


def _asset_of(title: str, slug: str) -> str | None:
    t = f"{title} {slug}".lower()
    if not any(k in t for k in CRYPTO_KEYS):
        return None
    for keys, sym in [(("bitcoin", "btc"), "BTC"), (("ethereum", "eth"), "ETH"),
                      (("solana", "sol"), "SOL"), (("bnb",), "BNB"),
                      (("xrp", "ripple"), "XRP"), (("dogecoin", "doge"), "DOGE"),
                      (("cardano", "ada"), "ADA"), (("polkadot", "dot"), "DOT")]:
        if any(k in t for k in keys):
            return sym
    return "CRYPTO"


def _norm_side(outcome: str, side: str) -> str:
    s = (outcome or side or "").upper()
    if s in ("YES", "UP", "BUY", "LONG"):
        return "YES"
    if s in ("NO", "DOWN", "SELL", "SHORT"):
        return "NO"
    return s or "YES"


async def fetch_leaders(r) -> list[dict]:
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
                        "rank": i + 1, "wallet": w,
                        "name": row.get("pseudonym") or row.get("name") or f"#{i+1}",
                        "profit_usd": round(float(row.get("profit") or row.get("pnl") or 0), 2),
                        "source": "polymarket_leaderboard",
                    })
                if leaders:
                    return leaders
            except Exception:
                continue
    try:
        top = await r.zrevrange("arb:edges:wallet_volume_24h", 0, TOP_N - 1, withscores=True)
        return [{"rank": i + 1, "wallet": _addr(a), "name": f"#{i+1}",
                 "profit_usd": None, "volume_usd": round(float(v), 2),
                 "source": "observed_volume"} for i, (a, v) in enumerate(top)]
    except Exception:
        return []


async def _crypto_price(r, asset: str) -> float | None:
    """Latest mid for an asset from the engine's Redis tick streams (fast, no API)."""
    try:
        keys = await r.keys(f"arb:ticks:{asset}:*")
        for k in keys:
            head = await r.lindex(k, 0)
            if head:
                d = json.loads(head)
                mid = d.get("mid") or d.get("price")
                if mid:
                    return float(mid)
    except Exception:
        pass
    return None


def _conviction(rank: int, consensus: int, size_usd: float) -> float:
    base = 0.50
    rank_bonus = 0.25 * max(0.0, 1.0 - (rank - 1) / max(TOP_N, 1))
    consensus_bonus = min(0.30, 0.15 * max(0, consensus - 1))
    size_bonus = min(0.10, (size_usd / 5000.0) * 0.10)
    return round(min(0.98, base + rank_bonus + consensus_bonus + size_bonus), 3)


async def run_copy_leaders():
    r = get_redis()
    seen: set[str] = set()
    leaders: list[dict] = []
    leader_set: set[str] = set()
    # consensus[condition_id][side] = {wallet: ts}
    consensus: dict[str, dict[str, dict[str, float]]] = {}
    last_lb = 0.0
    print(f"[copy_leaders] precision copy — top-{TOP_N}, poll {POLL_SECONDS}s, "
          f"min conviction {MIN_CONVICTION}")

    while True:
        try:
            now = time.time()
            now_ms = int(now * 1000)

            if now - last_lb > LEADERBOARD_REFRESH_SECONDS or not leaders:
                leaders = await fetch_leaders(r)
                leader_set = {l["wallet"] for l in leaders}
                await r.set("arb:edges:leaders",
                            json.dumps({"leaders": leaders, "ts": now_ms, "top_n": TOP_N}), ex=1800)
                last_lb = now
                if leaders:
                    print(f"[copy_leaders] leaderboard: {len(leaders)} champions "
                          f"({leaders[0].get('source')})")

            if not leader_set:
                await asyncio.sleep(POLL_SECONDS)
                continue

            # `live` must match mode.py's server_live_ready: REAL intent AND the
            # server actually able to execute (PAPER_TRADE=false AND a live key).
            # Without the key present, labelling a bet is_real_wallet/mode=real
            # would show fictional real-money PnL for a bet that is never placed
            # on-chain (copy_leaders only publishes signals; live execution is the
            # operator's manual CLI step).
            mode = (await r.get("arb:mode")) or "demo"
            paper = os.getenv("PAPER_TRADE", "true").lower() != "false"
            has_live_key = bool(os.getenv("POLYMARKET_PRIVATE_KEY", "").strip())
            live = (mode == "real") and (not paper) and has_live_key

            async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                resp = await client.get(TRADES_URL, params={"limit": "150"})
                trades = resp.json() if resp.status_code == 200 else []
            if not isinstance(trades, list):
                trades = []

            # Prune stale consensus entries
            for cid in list(consensus.keys()):
                for sd in list(consensus[cid].keys()):
                    consensus[cid][sd] = {w: ts for w, ts in consensus[cid][sd].items()
                                          if now - ts < CONSENSUS_WINDOW_S}
                    if not consensus[cid][sd]:
                        del consensus[cid][sd]
                if not consensus[cid]:
                    del consensus[cid]

            copied = 0
            # Oldest-first so consensus builds before we size the later ones
            for t in reversed(trades):
                w = _addr(t.get("proxyWallet"))
                if w not in leader_set:
                    continue
                cond = t.get("conditionId")
                if not cond:
                    continue
                price = float(t.get("price", 0) or 0)
                size_usd = float(t.get("size", 0) or 0) * price
                if size_usd < MIN_COPY_SIZE_USD:
                    continue
                asset = _asset_of(t.get("title", ""), t.get("slug", ""))
                if asset is None:
                    continue
                side = _norm_side(t.get("outcome", ""), t.get("side", ""))

                # Record consensus (per market+side, unique wallets)
                consensus.setdefault(cond, {}).setdefault(side, {})[w] = now
                n_consensus = len(consensus[cond][side])

                key = f"{w}:{t.get('timestamp')}:{cond[:16]}"
                if key in seen:
                    continue
                seen.add(key)

                leader = next((l for l in leaders if l["wallet"] == w), {})
                rank = leader.get("rank", TOP_N)
                conviction = _conviction(rank, n_consensus, size_usd)
                if conviction < MIN_CONVICTION:
                    continue  # precision gate — skip weak singletons

                # Size by conviction (0.5x..1.5x base), capped
                stake = round(BASE_STAKE_USD * (0.5 + conviction), 2)
                asset_px = await _crypto_price(r, asset)

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
                    "stake_usd": stake,
                    "entry_price": round(price, 4),
                    "implied_prob": round(price, 4),
                    "our_prob": conviction,
                    "conviction": conviction,
                    "consensus": n_consensus,
                    "asset_price_at_bet": asset_px,
                    "status": "open",
                    "end_date": t.get("endDate"),
                    "slug": t.get("slug"),
                    "source": "copy_leader",
                    "leader_wallet": w,
                    "leader_rank": rank,
                    "leader_name": leader.get("name"),
                    "leader_size_usd": round(size_usd, 2),
                    "mode": "real" if live else "demo",
                    "is_real_wallet": bool(live),
                }
                await publish("arb:polymarket:bets", bet)
                await publish("arb:edges:copy_trades", bet)
                copied += 1

            if copied:
                print(f"[copy_leaders] mirrored {copied} champion trade(s) "
                      f"[mode={'REAL' if live else 'DEMO'}]")

            if len(seen) > 30000:
                seen = set(list(seen)[-10000:])

        except Exception as e:
            print(f"[copy_leaders] WARN {repr(e)[:160]}")

        await asyncio.sleep(POLL_SECONDS)


if __name__ == "__main__":
    asyncio.run(run_copy_leaders())
