from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from arb.dashboard.api.deps import get_db

router = APIRouter(prefix="/api/pnl", tags=["pnl"])


@router.get("")
async def get_pnl(window: str = "24h", db: AsyncSession = Depends(get_db)):
    interval_map = {"1h": "1 hour", "6h": "6 hours", "24h": "24 hours", "7d": "7 days"}
    interval = interval_map.get(window, "24 hours")
    rows = await db.execute(
        text(
            f"SELECT time_bucket('5 minutes', time) AS bucket, "
            f"SUM(pnl) AS pnl, COUNT(*) AS trades "
            f"FROM trades WHERE time > NOW() - INTERVAL '{interval}' "
            f"GROUP BY bucket ORDER BY bucket ASC"
        )
    )
    data = [{"time": str(r[0]), "pnl": float(r[1] or 0), "trades": int(r[2])} for r in rows]
    total_pnl = sum(d["pnl"] for d in data)
    return {"window": window, "total_pnl": round(total_pnl, 4), "data": data}
