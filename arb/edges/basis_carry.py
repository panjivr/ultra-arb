"""
Funding-rate basis arbitrage (delta-neutral carry).

Mechanic:
  - Perpetual futures have funding payments every 8 hours
  - If funding rate is +0.05% (longs pay shorts), you can:
    SHORT the perp, BUY spot → collect funding payments while delta-neutral
  - If funding rate is -0.05% (shorts pay longs):
    LONG the perp, SELL spot (or borrow & short) → collect negative funding

When funding APR > borrow cost + fees, this is a low-risk carry trade.
Bots scan 24/7; humans miss the windows.
"""
import asyncio
import json
import time
import httpx
from arb.infra.redis_bus import publish, get_redis
from arb.edges.ensemble import emit_vote, SignalVote

TIMEOUT = httpx.Timeout(8, connect=4)

# Symbols to monitor; we use Gate.io public futures endpoints (no SSL issues)
SYMBOLS = ["BTC_USDT", "ETH_USDT", "SOL_USDT", "BNB_USDT", "XRP_USDT"]


async def _fetch_funding(symbol: str) -> dict | None:
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        try:
            r = await client.get(
                f"https://api.gateio.ws/api/v4/futures/usdt/contracts/{symbol}"
            )
            if r.status_code != 200:
                return None
            c = r.json()
            rate = float(c.get("funding_rate_indicative", 0) or c.get("funding_rate", 0) or 0)
            mark = float(c.get("mark_price", 0) or 0)
            index = float(c.get("index_price", 0) or 0)
            return {"rate": rate, "mark": mark, "index": index}
        except Exception:
            return None


async def scan_basis_carry(min_apr: float = 3.0) -> list[dict]:
    """Find symbols where funding APR justifies a basis trade."""
    found = []
    for sym in SYMBOLS:
        data = await _fetch_funding(sym)
        if not data:
            continue
        rate = data["rate"]
        # Funding paid every 8h → 3x/day → 365 days for APR
        apr_pct = rate * 3 * 365 * 100
        # Conservative cost: ~2% roundtrip fees for delta-neutral basis
        net_apr = abs(apr_pct) - 2.0
        if net_apr < min_apr:
            continue
        if apr_pct > 0:
            # Funding positive → longs pay shorts → SHORT perp + LONG spot
            strategy = "SHORT_PERP_LONG_SPOT"
            description = (
                f"Funding +{apr_pct:.1f}% APR — short perp, long spot. "
                f"Collect funding, neutral on price."
            )
        else:
            strategy = "LONG_PERP_SHORT_SPOT"
            description = (
                f"Funding {apr_pct:.1f}% APR — long perp, short spot. "
                f"Collect inverse funding."
            )
        basis_bps = ((data["mark"] - data["index"]) / data["index"] * 10_000) if data["index"] else 0
        found.append({
            "symbol": sym.replace("_", "/"),
            "funding_rate": rate,
            "funding_rate_pct": round(rate * 100, 4),
            "apr_pct": round(apr_pct, 2),
            "net_apr_after_costs": round(net_apr, 2),
            "mark_price": data["mark"],
            "index_price": data["index"],
            "basis_bps": round(basis_bps, 2),
            "strategy": strategy,
            "description": description,
            "kind": "basis_carry",
            "ts": int(time.time() * 1000),
        })
    found.sort(key=lambda x: x["net_apr_after_costs"], reverse=True)
    return found


async def run_basis_carry_loop(interval_s: int = 120):
    while True:
        try:
            arbs = await scan_basis_carry(min_apr=3.0)
            for a in arbs:
                await publish("arb:edges:basis_carry", a)
            if arbs:
                top = arbs[0]
                print(f"[basis_carry] best: {top['symbol']} {top['strategy']} {top['net_apr_after_costs']}% net APR")
            # Wire into ensemble gate — funding rate direction signals crypto price bias
            now_ms = int(time.time() * 1000)
            for a in arbs:
                sym = a["symbol"].replace("/", "_")
                # Positive funding = longs crowded = mild bearish bias for spot
                direction = "no" if a["apr_pct"] > 0 else "yes"
                conf = min(0.5 + abs(a["net_apr_after_costs"]) / 50, 0.85)
                await emit_vote(SignalVote(
                    condition_id=f"basis:{sym}:daily",
                    direction=direction, confidence=round(conf, 3),
                    source="basis_carry", asset=a["symbol"],
                    kind="basis_carry", ts=now_ms,
                ))
        except Exception as e:
            print(f"[basis_carry] error: {repr(e)[:120]}")
        await asyncio.sleep(interval_s)
