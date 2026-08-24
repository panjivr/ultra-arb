"""
Live equity = realized PnL + unrealized mark-to-market of OPEN bets.

Unrealized is honest: each open bet is marked at the market's CURRENT Polymarket
outcome price (from the Gamma API, cached ~6s), so equity breathes with the real
market every poll instead of only jumping when a bet resolves.

  unrealized_i = stake_i * (current_price / entry_price - 1)
"""
import json
import time
import httpx
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from arb.infra.redis_bus import latest, get_redis
from arb.dashboard.api.deps import get_db
from arb.dashboard.api.routes.stats import (
    _account_start_capital, _trades_from_redis, _compute_stats,
)

router = APIRouter(prefix="/api/equity", tags=["equity"])

GAMMA = "https://gamma-api.polymarket.com/markets"
_TIMEOUT = httpx.Timeout(6, connect=3)


def _outcome_prices(m: dict) -> list[float]:
    raw = m.get("outcomePrices")
    try:
        if isinstance(raw, str):
            raw = json.loads(raw)
        return [float(x) for x in raw]
    except Exception:
        return []


async def _current_price(client, r, cond: str, side: str) -> float | None:
    """Current price of our side for a condition_id (cached 6s in Redis)."""
    ck = f"arb:equity:mark:{cond}"
    cached = await r.get(ck)
    prices = None
    if cached:
        try:
            prices = json.loads(cached)
        except Exception:
            prices = None
    if prices is None:
        try:
            resp = await client.get(GAMMA, params={"condition_ids": cond})
            if resp.status_code == 200:
                arr = resp.json()
                m = arr[0] if isinstance(arr, list) and arr else None
                if m:
                    prices = _outcome_prices(m)
                    await r.set(ck, json.dumps(prices), ex=6)
        except Exception:
            prices = None
    if not prices:
        return None
    # Convention: index 0 = YES/first outcome, index 1 = NO
    idx = 0 if side.upper() in ("YES", "UP", "BUY", "LONG") else 1
    return prices[idx] if idx < len(prices) else prices[0]


@router.get("/live")
async def live_equity(db: AsyncSession = Depends(get_db)):
    r = get_redis()
    start_cap, is_real, addr, linked_at = await _account_start_capital()
    trades = await _trades_from_redis(since_ms=linked_at)
    base = _compute_stats(trades, start_cap)
    realized_equity = base["current_equity"]

    # Open bets (most recent), mark to current market price.
    bets = await latest("arb:polymarket:bets", count=400)
    open_bets = [b for b in bets if b.get("status") == "open"][:30]
    unrealized = 0.0
    marked = 0
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        for b in open_bets:
            cond = b.get("condition_id")
            entry = float(b.get("entry_price") or 0)
            stake = float(b.get("stake_usd") or 0)
            side = b.get("side") or "YES"
            if not cond or entry <= 0 or stake <= 0:
                continue
            cur = await _current_price(client, r, cond, side)
            if cur is None or cur <= 0:
                continue
            unrealized += stake * (cur / entry - 1.0)
            marked += 1

    unrealized = round(unrealized, 4)
    return {
        "realized_equity": round(realized_equity, 2),
        "unrealized_usd": unrealized,
        "live_equity": round(realized_equity + unrealized, 2),
        "start_capital": start_cap,
        "open_marked": marked,
        "is_real_wallet": is_real,
        "ts": int(time.time() * 1000),
    }
