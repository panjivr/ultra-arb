"""
Compounding interest tracker — shows projected growth assuming the bot
continues to deliver its current daily return.

Combines: spot/perp arb PnL + Polymarket bet PnL + funding carry.
"""
import json
import math
import time
from fastapi import APIRouter
from arb.infra.redis_bus import get_redis, latest

router = APIRouter(prefix="/api", tags=["compounding"])


async def _wallet_capital(r) -> tuple[float, bool, str | None, int]:
    raw = await r.get("arb:wallet:linked")
    if not raw:
        return 10_000.0, False, None, 0
    try:
        d = json.loads(raw)
        bal = float(d.get("usdc_balance", 10_000)) or 10_000.0
        return bal, True, d.get("address"), int(d.get("linked_at", 0) or 0)
    except Exception:
        return 10_000.0, False, None, 0


@router.get("/compounding")
async def compounding_projection():
    """Live compounding projection based on observed performance."""
    r = get_redis()
    start_capital, is_real, addr, linked_at = await _wallet_capital(r)

    # Read recent CLOSE orders — filter by linked_at when wallet connected
    orders = await latest("arb:orders", count=8000)
    closes = []
    for o in orders:
        if o.get("event") != "CLOSE" or "pnl" not in o:
            continue
        if is_real and int(o.get("ts", 0) or 0) < linked_at:
            continue
        closes.append(o)
    spot_pnl = sum(float(o.get("pnl", 0) or 0) for o in closes)

    # Polymarket realized PnL
    bets = await latest("arb:polymarket:bets", count=500)
    poly_pnl = 0.0
    poly_open = 0
    poly_won = 0
    poly_lost = 0
    poly_stake_open = 0.0
    for b in bets:
        st = b.get("status")
        if st == "won":
            poly_pnl += float(b.get("payout_usd", 0) or 0) - float(b.get("stake_usd", 0) or 0)
            poly_won += 1
        elif st == "lost":
            poly_pnl -= float(b.get("stake_usd", 0) or 0)
            poly_lost += 1
        elif st == "open":
            poly_open += 1
            poly_stake_open += float(b.get("stake_usd", 0) or 0)

    total_pnl = spot_pnl + poly_pnl
    current_equity = start_capital + total_pnl

    # Compute observed period & rate from oldest-to-newest order
    if closes:
        # closes are returned newest-first
        first_ts = min(int(c.get("ts", 0)) for c in closes if c.get("ts"))
        last_ts = max(int(c.get("ts", 0)) for c in closes if c.get("ts"))
        elapsed_ms = max(last_ts - first_ts, 1)
        elapsed_hours = elapsed_ms / 3_600_000
        elapsed_days = elapsed_hours / 24
    else:
        elapsed_hours = 0.001
        elapsed_days = 0.001

    # Hourly return rate (compound)
    if start_capital > 0 and elapsed_hours > 0 and current_equity > 0:
        hourly_return = (current_equity / start_capital) ** (1 / max(elapsed_hours, 0.01)) - 1
    else:
        hourly_return = 0

    # Project forward — applying caps (real markets degrade at extrapolation)
    # Use the more conservative of: actual rate, or 50%/year cap
    annual_cap = 0.5  # 50% APR realistic cap
    hourly_cap = (1 + annual_cap) ** (1 / 8760) - 1
    safe_hourly = max(-0.01, min(hourly_return, hourly_cap))

    def project(h: float) -> float:
        return current_equity * (1 + safe_hourly) ** h

    projection = {
        "next_24h": round(project(24), 2),
        "next_7d": round(project(168), 2),
        "next_30d": round(project(720), 2),
        "next_90d": round(project(2160), 2),
        "next_1y": round(project(8760), 2),
    }
    # Raw (unbounded) projection for comparison
    def raw_project(h: float) -> float:
        try:
            return current_equity * (1 + hourly_return) ** h
        except Exception:
            return current_equity
    raw_projection = {
        "next_24h": round(raw_project(24), 2),
        "next_30d": round(raw_project(720), 2),
        "next_1y": round(raw_project(8760), 2),
    }

    return {
        "start_capital": round(start_capital, 2),
        "current_equity": round(current_equity, 2),
        "is_real_wallet": is_real,
        "wallet_addr": addr,
        "spot_perp_pnl": round(spot_pnl, 2),
        "polymarket_pnl": round(poly_pnl, 2),
        "polymarket_open_bets": poly_open,
        "polymarket_open_stake_usd": round(poly_stake_open, 2),
        "polymarket_wins": poly_won,
        "polymarket_losses": poly_lost,
        "total_pnl": round(total_pnl, 2),
        "total_return_pct": round(total_pnl / max(start_capital, 1) * 100, 3),
        "elapsed_hours": round(elapsed_hours, 2),
        "elapsed_days": round(elapsed_days, 2),
        "trade_count": len(closes),
        "hourly_return_pct": round(hourly_return * 100, 5),
        "hourly_return_capped_pct": round(safe_hourly * 100, 5),
        "daily_return_pct": round(((1 + safe_hourly) ** 24 - 1) * 100, 3),
        "monthly_return_pct": round(((1 + safe_hourly) ** 720 - 1) * 100, 2),
        "annual_return_pct": round(((1 + safe_hourly) ** 8760 - 1) * 100, 2),
        "projection_capped": projection,
        "projection_raw_uncapped": raw_projection,
        "note": "Capped at 50% APR for realistic projection. Real returns degrade as capital scales.",
        "ts": int(time.time() * 1000),
    }
