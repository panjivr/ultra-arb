from fastapi import APIRouter
from arb.infra.redis_bus import latest

router = APIRouter(prefix="/api/positions", tags=["positions"])


@router.get("")
async def get_positions():
    orders = await latest("arb:orders", count=100)
    risk_alerts = await latest("arb:risk:alerts", count=10)
    return {
        "recent_orders": orders[:20],
        "risk_alerts": risk_alerts[:5],
    }
