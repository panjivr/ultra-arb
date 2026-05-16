"""
Polymarket prediction market integration.

Reads real markets from Polymarket's gamma-api (public, no auth) and computes
implied probability from outcome prices. The arb bot then compares this to
its internal probability model and bets when there's edge.

For real-money betting: needs Polygon wallet + USDC.e approval + py-clob-client.
This module handles READ + PAPER BET. Real on-chain execution lives in
arb.execution.polymarket_executor (added when user enables live mode).

Endpoints:
  GET  /api/polymarket/markets   — list active crypto markets with our edge calc
  GET  /api/polymarket/bets      — bot's open + resolved bets
  GET  /api/polymarket/pnl       — Polymarket-specific PnL summary
  POST /api/polymarket/bet       — manually place a paper bet (also called by engine)
"""
import asyncio
import json
import time
from typing import Any
from fastapi import APIRouter, Body
import httpx
from arb.infra.redis_bus import get_redis, publish, latest

router = APIRouter(prefix="/api/polymarket", tags=["polymarket"])

GAMMA = "https://gamma-api.polymarket.com"
CRYPTO_TAG_ID = 21
_timeout = httpx.Timeout(8.0, connect=4.0)


async def _cached(key: str, ttl: int, fetcher):
    r = get_redis()
    ck = f"arb:polymarket:cache:{key}"
    cached = await r.get(ck)
    if cached:
        try:
            return {**json.loads(cached), "_cached": True}
        except Exception:
            pass
    try:
        data = await fetcher()
        await r.set(ck, json.dumps(data), ex=ttl)
        return {**data, "_cached": False, "_fetched_at": int(time.time() * 1000)}
    except Exception as e:
        return {"error": str(e)[:200]}


def _parse_outcome_prices(s: str) -> list[float]:
    try:
        arr = json.loads(s) if isinstance(s, str) else s
        return [float(x) for x in arr]
    except Exception:
        return []


def _our_probability(market: dict) -> float | None:
    """
    Rough internal probability estimate for BTC price-range markets.
    Pulls our latest BTC mid from Redis ticks and uses 1-day vol to score
    P(BTC in range at resolution).

    For now: returns None for non-crypto markets. The engine can be plugged
    here with our Bayesian/HMM model output.
    """
    # Simplified: use question text heuristics
    q = (market.get("question") or "").lower()
    if "bitcoin" not in q and "btc" not in q:
        return None
    # If question is "Will BTC be between $X and $Y on May 15" — we'd need to
    # query our BTC price + a normal distribution. Defer to engine.
    return None


async def _fetch_crypto_markets() -> dict:
    """Active crypto prediction markets sorted by liquidity."""
    async with httpx.AsyncClient(timeout=_timeout) as client:
        r = await client.get(
            f"{GAMMA}/markets",
            params={"active": "true", "closed": "false",
                    "tag_id": str(CRYPTO_TAG_ID), "limit": 30,
                    "order": "volume", "ascending": "false"},
        )
        if r.status_code != 200:
            return {"error": f"http {r.status_code}", "markets": []}
        raw = r.json()
        markets = []
        for m in raw:
            prices = _parse_outcome_prices(m.get("outcomePrices") or "[]")
            outcomes = []
            try:
                outcomes = json.loads(m.get("outcomes") or "[]")
            except Exception:
                pass
            yes_price = prices[0] if prices else None
            no_price = prices[1] if len(prices) > 1 else (1 - yes_price if yes_price is not None else None)
            implied_prob_yes = yes_price  # already 0-1
            markets.append({
                "id": m.get("id"),
                "question": m.get("question"),
                "slug": m.get("slug"),
                "end_date": m.get("endDate"),
                "image": m.get("image"),
                "outcomes": outcomes,
                "yes_price": yes_price,
                "no_price": no_price,
                "implied_prob_yes": implied_prob_yes,
                "implied_prob_no": no_price,
                "liquidity": float(m.get("liquidity", 0) or 0),
                "volume": float(m.get("volume", 0) or 0),
                "condition_id": m.get("conditionId"),
                "url": f"https://polymarket.com/market/{m.get('slug')}",
            })
        return {"markets": markets, "count": len(markets)}


@router.get("/markets")
async def get_markets():
    """Active crypto markets ranked by 24h volume."""
    return await _cached("crypto_markets", 30, _fetch_crypto_markets)


@router.get("/bets")
async def get_bets(limit: int = 50):
    """All Polymarket bets placed by the engine (paper or live)."""
    bets = await latest("arb:polymarket:bets", count=limit)
    return {"bets": bets, "count": len(bets)}


@router.get("/pnl")
async def polymarket_pnl():
    """Aggregated PnL from Polymarket bets."""
    bets = await latest("arb:polymarket:bets", count=1000)
    total_staked = 0.0
    total_won = 0.0
    total_lost = 0.0
    open_bets = 0
    resolved = 0
    win_count = 0
    loss_count = 0
    for b in bets:
        stake = float(b.get("stake_usd", 0) or 0)
        total_staked += stake
        st = b.get("status", "open")
        if st == "open":
            open_bets += 1
        elif st == "won":
            resolved += 1
            win_count += 1
            total_won += float(b.get("payout_usd", 0) or 0)
        elif st == "lost":
            resolved += 1
            loss_count += 1
            total_lost += stake
    net = total_won - total_lost
    return {
        "total_bets": len(bets),
        "open": open_bets,
        "resolved": resolved,
        "wins": win_count,
        "losses": loss_count,
        "win_rate": round(win_count / max(resolved, 1) * 100, 2),
        "total_staked_usd": round(total_staked, 2),
        "total_won_usd": round(total_won, 2),
        "total_lost_usd": round(total_lost, 2),
        "net_pnl_usd": round(net, 2),
        "roi_pct": round(net / max(total_staked, 1) * 100, 2),
    }


@router.post("/bet")
async def place_paper_bet(body: dict = Body(...)):
    """
    Record a paper bet — used by the engine when it identifies edge.
    Real on-chain execution would call py-clob-client here.
    """
    bet = {
        "id": f"bet-{int(time.time()*1000)}",
        "ts": int(time.time() * 1000),
        "condition_id": body.get("condition_id"),
        "market_id": body.get("market_id"),
        "question": body.get("question", "")[:240],
        "side": body.get("side"),  # "Yes" or "No"
        "stake_usd": float(body.get("stake_usd", 0)),
        "entry_price": float(body.get("entry_price", 0)),
        "implied_prob": float(body.get("implied_prob", 0)),
        "our_prob": float(body.get("our_prob", 0)),
        "edge_bps": float(body.get("edge_bps", 0)),
        "expected_value_usd": float(body.get("expected_value_usd", 0)),
        "status": "open",
        "end_date": body.get("end_date"),
        "source": body.get("source", "engine"),
    }
    await publish("arb:polymarket:bets", bet)
    return {"ok": True, "bet": bet}
