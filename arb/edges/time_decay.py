"""
Pre-resolution time-decay arbitrage.

Near a market's end_date, prices should converge to either 0 or 1 (binary outcome).
But thin-liquidity markets sometimes still trade at non-extreme prices (0.05, 0.95)
even with high certainty.

Strategy:
  - Find markets with < 30 min to resolve
  - Pull our internal probability model (using live asset price)
  - If our certainty > 95% AND market priced 0.10-0.40 of that outcome → BUY (high EV)
  - If our certainty > 95% AND market priced 0.60-0.90 of opposite → also BUY high-prob side

This is the "last mile" arbitrage. Bots have time-clock advantage because they
can re-price every second; humans miss the window.
"""
import asyncio
import json
import math
import time
import re
from datetime import datetime, timezone
import httpx
from arb.infra.redis_bus import publish, get_redis
from arb.edges.ensemble import emit_vote, SignalVote

TIMEOUT = httpx.Timeout(8, connect=4)


def _normal_cdf(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def _parse_btc_range(q: str) -> tuple[float, float] | None:
    nums = re.findall(r"\$?([\d,]+(?:\.\d+)?)", q)
    parsed = []
    for n in nums:
        try:
            v = float(n.replace(",", ""))
            if 100 < v < 1_000_000:
                parsed.append(v)
        except Exception:
            pass
    if len(parsed) >= 2:
        return min(parsed[0], parsed[1]), max(parsed[0], parsed[1])
    return None


def _detect_asset(question: str) -> str | None:
    q = question.lower()
    if "bitcoin" in q or "btc" in q: return "BTC/USDT"
    if "ethereum" in q or "eth " in q or "eth/" in q: return "ETH/USDT"
    if "solana" in q or "sol " in q: return "SOL/USDT"
    if "xrp" in q: return "XRP/USDT"
    if "bnb" in q or "binance" in q: return "BNB/USDT"
    return None


async def _get_asset_price(r, asset: str) -> float:
    """Get latest mid price from our REAL feed."""
    try:
        keys = await r.keys(f"arb:ticks:{asset}*")
        for k in keys:
            raw = await r.lindex(k, 0)
            if raw:
                return float(json.loads(raw).get("mid", 0))
    except Exception:
        pass
    return 0


async def scan_time_decay_arbs(min_hours: float = 0.0, max_hours: float = 0.5) -> list[dict]:
    """Find markets close to resolution with potential certainty mismatch."""
    r = get_redis()
    found = []
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        try:
            res = await client.get("https://gamma-api.polymarket.com/markets",
                params={"active": "true", "closed": "false",
                        "tag_id": "21", "limit": "100",
                        "order": "endDate", "ascending": "true"})
            if res.status_code != 200:
                return []
            markets = res.json()
        except Exception:
            return []

    for m in markets:
        try:
            end = datetime.fromisoformat(m.get("endDate", "").replace("Z", "+00:00"))
            hours_left = (end - datetime.now(timezone.utc)).total_seconds() / 3600
            if hours_left < min_hours or hours_left > max_hours:
                continue
            prices = json.loads(m.get("outcomePrices") or "[]")
            if len(prices) != 2:
                continue
            yes_p = float(prices[0])
            no_p = float(prices[1])
            q = m.get("question", "")
            asset = _detect_asset(q)
            if not asset:
                continue
            asset_price = await _get_asset_price(r, asset)
            if asset_price <= 0:
                continue

            # For BTC range markets
            rng = _parse_btc_range(q) if asset == "BTC/USDT" else None
            if rng:
                low, high = rng
                in_range_now = low <= asset_price <= high
                # With < 30 min to resolve and asset deep inside/outside range,
                # the outcome is near-certain (volatility can't move price much)
                # Distance from boundary as % of price → confidence
                if in_range_now:
                    dist_pct = min((asset_price - low) / asset_price,
                                   (high - asset_price) / asset_price) * 100
                    our_prob_yes = min(0.98, 0.5 + dist_pct * 0.5)  # heuristic
                else:
                    # Asset outside range — probability of YES drops with distance
                    if asset_price < low:
                        dist_pct = (low - asset_price) / low * 100
                    else:
                        dist_pct = (asset_price - high) / high * 100
                    # Each 1% outside range reduces confidence; floor at 2%
                    our_prob_yes = max(0.02, 0.5 - min(dist_pct, 48) * 0.01)

                edge = our_prob_yes - yes_p
                if abs(edge) < 0.10:  # require 10% edge for time-decay arbs
                    continue
                if edge > 0:
                    side = "Yes"; entry = yes_p; p_win = our_prob_yes
                else:
                    side = "No"; entry = no_p; p_win = 1 - our_prob_yes
                if entry <= 0.01:
                    continue
                # EV per dollar
                payoff = 1 / entry  # contract pays $1 if win
                ev_per_dollar = p_win * payoff - 1
                if ev_per_dollar < 0.05:
                    continue
                found.append({
                    "kind": "time_decay_range",
                    "asset": asset,
                    "asset_price": asset_price,
                    "question": q[:200],
                    "condition_id": m.get("conditionId"),
                    "range_low": low,
                    "range_high": high,
                    "side": side,
                    "entry_price": round(entry, 4),
                    "our_prob": round(p_win, 3),
                    "implied_prob": round(yes_p if side == "Yes" else no_p, 3),
                    "edge_bps": round(edge * 10_000, 1),
                    "ev_per_dollar": round(ev_per_dollar, 3),
                    "hours_to_resolve": round(hours_left, 3),
                    "minutes_to_resolve": round(hours_left * 60, 1),
                    "end_date": m.get("endDate"),
                    "url": f"https://polymarket.com/market/{m.get('slug')}",
                    "ts": int(time.time() * 1000),
                })
        except Exception:
            continue
    found.sort(key=lambda x: x["ev_per_dollar"], reverse=True)
    return found


async def run_time_decay_loop(interval_s: int = 30):
    while True:
        try:
            arbs = await scan_time_decay_arbs(min_hours=0.0, max_hours=0.5)
            now_ms = int(time.time() * 1000)
            for a in arbs[:10]:
                await publish("arb:edges:time_decay", a)
                cid = a.get("condition_id")
                if cid:
                    direction = "yes" if a.get("side") == "Yes" else "no"
                    await emit_vote(SignalVote(
                        condition_id=cid, direction=direction,
                        confidence=min(a.get("our_prob", 0.55), 0.95),
                        source="time_decay", asset=a.get("asset") or "BTC/USDT",
                        kind=a.get("kind", "time_decay"), ts=now_ms,
                    ))
        except Exception as e:
            print(f"[time_decay] error: {repr(e)[:120]}")
        await asyncio.sleep(interval_s)
