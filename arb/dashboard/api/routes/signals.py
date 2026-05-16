from fastapi import APIRouter
from arb.infra.redis_bus import latest

router = APIRouter(prefix="/api/signals", tags=["signals"])


@router.get("")
async def get_signals(limit: int = 50):
    signals = await latest("arb:signals", count=limit)
    return {"count": len(signals), "signals": signals}
