"""
YES/NO sum arbitrage on Polymarket.

When YES + NO < $1, we can buy BOTH sides and guarantee a profit when one resolves.
When YES + NO > $1, we can SELL both (short) for guaranteed profit.

This happens briefly during:
  - Fast price moves (market makers update one side faster than other)
  - Low-liquidity markets where bid-ask spreads create gaps
  - Order book imbalance

Edge: 100% mathematical certainty IF you can execute both legs fast enough.
Bot advantage: millisecond execution vs minute-level human reaction.
"""
import asyncio
import json
import time
import httpx
from arb.infra.redis_bus import publish, get_redis
from arb.edges.ensemble import emit_vote, SignalVote

TIMEOUT = httpx.Timeout(8, connect=4)
MIN_PROFIT_BPS = 20  # Flag arbs where guaranteed profit >= 0.2% (covers fees)
# Realistic cost to execute both legs: Polymarket fee ~2% per side + slippage on thin books
EXECUTION_COST_PCT = 2.5


async def scan_yesno_sum_arb() -> list[dict]:
    """Find markets where YES + NO != $1 (sum arbitrage opportunity)."""
    found = []
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        try:
            r = await client.get(
                "https://gamma-api.polymarket.com/markets",
                params={"active": "true", "closed": "false",
                        "limit": "200", "order": "volume", "ascending": "false"},
            )
            if r.status_code != 200:
                return []
            markets = r.json()
        except Exception:
            return []

    for m in markets:
        try:
            prices = json.loads(m.get("outcomePrices") or "[]")
            if len(prices) != 2:
                continue
            yes_p = float(prices[0])
            no_p = float(prices[1])
            total = yes_p + no_p
            # If sum < 1, buying both legs at current prices guarantees $1 - total profit/contract
            if 0 < total < 1 - MIN_PROFIT_BPS / 10_000:
                gross_roi_pct = (1 - total) / total * 100  # ROI before costs
                # Subtract realistic execution costs (fees + slippage on thin orderbooks)
                net_roi_pct = round(gross_roi_pct - EXECUTION_COST_PCT, 2)
                if net_roi_pct < 0.3:
                    # Not profitable after costs — skip
                    continue
                found.append({
                    "id": m.get("id"),
                    "condition_id": m.get("conditionId"),
                    "question": m.get("question", "")[:200],
                    "yes_price": yes_p,
                    "no_price": no_p,
                    "sum": round(total, 4),
                    "guaranteed_roi_pct": net_roi_pct,
                    "gross_roi_pct": round(gross_roi_pct, 2),
                    "profit_bps": round((1 - total) * 10_000, 1),
                    "liquidity": float(m.get("liquidity", 0) or 0),
                    "volume": float(m.get("volume", 0) or 0),
                    "end_date": m.get("endDate"),
                    "url": f"https://polymarket.com/market/{m.get('slug')}",
                    "kind": "yesno_sum_under",
                    "ts": int(time.time() * 1000),
                })
            # Sum > 1: SHORT both legs guarantees profit (only if Polymarket allows shorts; usually you'd sell YES if you hold and buy NO at low to cover)
            elif total > 1 + MIN_PROFIT_BPS / 10_000:
                # For prediction markets you typically can't naked-short; mark as informational
                found.append({
                    "id": m.get("id"),
                    "condition_id": m.get("conditionId"),
                    "question": m.get("question", "")[:200],
                    "yes_price": yes_p,
                    "no_price": no_p,
                    "sum": round(total, 4),
                    "overpriced_bps": round((total - 1) * 10_000, 1),
                    "liquidity": float(m.get("liquidity", 0) or 0),
                    "volume": float(m.get("volume", 0) or 0),
                    "end_date": m.get("endDate"),
                    "url": f"https://polymarket.com/market/{m.get('slug')}",
                    "kind": "yesno_sum_over",
                    "ts": int(time.time() * 1000),
                })
        except Exception:
            continue
    found.sort(key=lambda x: x.get("guaranteed_roi_pct", 0), reverse=True)
    return found


async def run_yesno_arb_loop(interval_s: int = 30):
    """Background task: scan every 30s, publish edges to Redis."""
    while True:
        try:
            arbs = await scan_yesno_sum_arb()
            r = get_redis()
            now_ms = int(time.time() * 1000)
            for arb in arbs[:20]:
                await publish("arb:edges:yesno_arb", arb)
                cid = arb.get("condition_id")
                if cid:
                    conf = min(0.5 + arb.get("net_roi_pct", 0) / 20, 0.9)
                    await emit_vote(SignalVote(
                        condition_id=cid,
                        direction="yes" if arb.get("kind") == "yesno_sum_under" else "no",
                        confidence=round(conf, 3), source="yesno_arb",
                        asset="POLY/USDT", kind=arb.get("kind", "yesno"),
                        ts=now_ms,
                    ))
            await r.lpush("arb:edges:yesno_arb:summary", json.dumps({
                "ts": int(time.time() * 1000),
                "count": len(arbs),
                "top_roi": arbs[0]["guaranteed_roi_pct"] if arbs else 0,
            }))
            await r.ltrim("arb:edges:yesno_arb:summary", 0, 100)
        except Exception as e:
            print(f"[yesno_arb] error: {repr(e)[:120]}")
        await asyncio.sleep(interval_s)
