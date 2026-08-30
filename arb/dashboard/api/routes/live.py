"""
Read-only live state of the autonomous executor for the dashboard visualisation.
Reads the arb:live:* keys the executor maintains — never writes, never trades.
"""
from datetime import datetime, timezone

from fastapi import APIRouter

from arb.dashboard.api.deps import get_redis

router = APIRouter(prefix="/api/live", tags=["live"])

# Display defaults — mirror the executor's conservative caps. The executor is
# the source of truth for enforcement; these are only for the UI.
CAPS = {"bet": 2.0, "daily": 5.0, "total": 25.0, "min_edge_bps": 500, "max_open": 5}


@router.get("")
async def live_state():
    r = get_redis()

    async def _get(key, default=None):
        try:
            v = await r.get(key)
            return v if v is not None else default
        except Exception:
            return default

    mode = await _get("arb:mode", "demo")
    try:
        armed_ttl = await r.ttl("arb:live:autonomous_armed")
    except Exception:
        armed_ttl = -2
    armed = isinstance(armed_ttl, int) and armed_ttl > 0

    halt_reason = await _get("arb:live:halted")
    total_spend = float(await _get("arb:live:total_spend", 0) or 0)
    open_count = max(0, int(float(await _get("arb:live:open_count", 0) or 0)))
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    daily_spend = float(await _get(f"arb:live:daily_spend:{today}", 0) or 0)

    # REAL account figures (written by the executor) — the dashboard's REAL view.
    wallet_balance = await _get("arb:live:wallet_balance")
    wallet_balance = float(wallet_balance) if wallet_balance not in (None, "") else None
    realized_pnl = float(await _get("arb:live:realized_pnl", 0) or 0)
    try:
        orders_count = int(await r.scard("arb:live:placed"))
    except Exception:
        orders_count = 0
    # Most recent real orders placed on-chain (from the audit list).
    recent_orders = []
    import json
    try:
        for raw in (await r.lrange("arb:live:orders", 0, 14)) or []:
            try:
                recent_orders.append(json.loads(raw))
            except Exception:
                pass
    except Exception:
        pass

    return {
        "mode": mode,
        "armed": bool(armed),
        "armed_ttl_sec": armed_ttl if armed else 0,
        "halted": bool(halt_reason),
        "halt_reason": halt_reason,
        "total_spend": round(total_spend, 2),
        "daily_spend": round(daily_spend, 2),
        "open_count": open_count,
        # real account
        "wallet_balance": wallet_balance,
        "realized_pnl": round(realized_pnl, 4),
        "orders_count": orders_count,
        "recent_orders": recent_orders,
        "caps": CAPS,
        "gates": {
            "mode_real": mode == "real",
            "armed": bool(armed),
            "not_halted": not bool(halt_reason),
        },
        "ts": int(datetime.now(timezone.utc).timestamp() * 1000),
    }
