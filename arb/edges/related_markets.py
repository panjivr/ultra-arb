"""
Related-markets arbitrage.

Two related markets MUST have ordered probabilities:
  - P(BTC > $80,000) >= P(BTC > $85,000)    [strict subset]
  - P(BTC > $85,000) >= P(BTC > $90,000)
  - P(BTC between $80k-$82k) + P(BTC between $82k-$84k) ≈ P(BTC between $80k-$84k)

When the market violates these orderings, there's a riskless or near-riskless arb.

Example violation:
  P(BTC > $80k) = 0.30  AND  P(BTC > $75k) = 0.20  ← impossible (subset must be ≥)
  → Buy YES on $75k market, sell YES on $80k market (or buy NO on $80k)
"""
import asyncio
import json
import re
import time
from collections import defaultdict
import httpx
from arb.infra.redis_bus import publish
from arb.edges.ensemble import emit_vote, SignalVote

TIMEOUT = httpx.Timeout(8, connect=4)


def _parse_price_threshold(question: str) -> tuple[str | None, str | None, float | None]:
    """
    Returns (asset_id, comparator, price).
    Examples:
      'Will Bitcoin reach $80,000 by May 15?' → ('btc-may15', '>=', 80000)
      'Bitcoin above $85,000 on May 14?'       → ('btc-may14', '>', 85000)
    """
    q = question.lower()
    asset = None
    if "bitcoin" in q or "btc" in q: asset = "btc"
    elif "ethereum" in q or "eth " in q: asset = "eth"
    elif "solana" in q or "sol " in q: asset = "sol"
    if not asset:
        return None, None, None

    # Extract date (rough; only group by date string for buckets)
    date_match = re.search(r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\w*\s+\d{1,2}", q)
    date_str = date_match.group(0) if date_match else "unspecified"

    # Comparator
    if any(w in q for w in ["above", "over", "higher than", ">=", "≥", "reach", "hit"]):
        cmp = ">"
    elif any(w in q for w in ["below", "under", "lower than", "<=", "≤"]):
        cmp = "<"
    else:
        return None, None, None

    # Price
    nums = re.findall(r"\$?([\d,]+(?:\.\d+)?)\b", q)
    parsed_prices = []
    for n in nums:
        try:
            v = float(n.replace(",", ""))
            if 100 < v < 1_000_000:
                parsed_prices.append(v)
        except Exception:
            pass
    if not parsed_prices:
        return None, None, None

    asset_id = f"{asset}-{date_str}"
    return asset_id, cmp, max(parsed_prices) if cmp == ">" else min(parsed_prices)


async def scan_related_arb() -> list[dict]:
    """Find probability ordering violations across related markets."""
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        try:
            r = await client.get("https://gamma-api.polymarket.com/markets",
                params={"active": "true", "closed": "false",
                        "tag_id": "21", "limit": "200",
                        "order": "volume", "ascending": "false"})
            if r.status_code != 200:
                return []
            markets = r.json()
        except Exception:
            return []

    # Group by (asset, date)
    buckets: dict[str, list[dict]] = defaultdict(list)
    for m in markets:
        q = m.get("question", "")
        asset_id, cmp, threshold = _parse_price_threshold(q)
        if not asset_id or cmp is None or threshold is None:
            continue
        try:
            prices = json.loads(m.get("outcomePrices") or "[]")
            yes_p = float(prices[0])
        except Exception:
            continue
        buckets[asset_id].append({
            "question": q,
            "comparator": cmp,
            "threshold": threshold,
            "yes_price": yes_p,
            "condition_id": m.get("conditionId"),
            "url": f"https://polymarket.com/market/{m.get('slug')}",
            "liquidity": float(m.get("liquidity", 0) or 0),
            "end_date": m.get("endDate"),
        })

    violations = []
    for asset_id, items in buckets.items():
        # Only consider buckets with 2+ markets
        if len(items) < 2:
            continue
        # For ">" markets: higher threshold → lower YES probability
        gt = sorted([i for i in items if i["comparator"] == ">"],
                    key=lambda x: x["threshold"])
        for i in range(len(gt) - 1):
            low = gt[i]
            high = gt[i + 1]
            # P(price > low) MUST be >= P(price > high)
            if low["yes_price"] < high["yes_price"] - 0.01:
                # Violation! Arb: buy YES on low (cheap), sell YES on high (expensive)
                edge = high["yes_price"] - low["yes_price"]
                violations.append({
                    "kind": "ordering_violation_gt",
                    "asset_id": asset_id,
                    "cheap_market": low["question"][:200],
                    "cheap_url": low["url"],
                    "cheap_threshold": low["threshold"],
                    "cheap_yes_price": low["yes_price"],
                    "expensive_market": high["question"][:200],
                    "expensive_url": high["url"],
                    "expensive_threshold": high["threshold"],
                    "expensive_yes_price": high["yes_price"],
                    "edge": round(edge, 4),
                    "edge_bps": round(edge * 10_000, 1),
                    "ts": int(time.time() * 1000),
                })

    violations.sort(key=lambda x: x["edge"], reverse=True)
    return violations


async def run_related_arb_loop(interval_s: int = 60):
    while True:
        try:
            arbs = await scan_related_arb()
            now_ms = int(time.time() * 1000)
            for a in arbs[:10]:
                await publish("arb:edges:related", a)
                # Ordering violation: cheap_market (buy YES) is the signal
                cid = a.get("cheap_market", "")[:40].replace(" ", "_")
                asset_part = (a.get("asset_id", "BTC") or "BTC").split("-")[0].upper()
                await emit_vote(SignalVote(
                    condition_id=f"related:{cid}",
                    direction="yes",
                    confidence=min(0.55 + a.get("edge", 0) * 2, 0.9),
                    source="related_markets",
                    asset=f"{asset_part}/USDT",
                    kind=a.get("kind", "ordering_violation"),
                    ts=now_ms,
                ))
            if arbs:
                print(f"[related_arb] {len(arbs)} probability-ordering violations")
        except Exception as e:
            print(f"[related_arb] error: {repr(e)[:120]}")
        await asyncio.sleep(interval_s)
