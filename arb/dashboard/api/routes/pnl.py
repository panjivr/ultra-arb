from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from arb.dashboard.api.deps import get_db
from arb.dashboard.api.routes.stats import _trades_from_redis

router = APIRouter(prefix="/api/pnl", tags=["pnl"])

# interval is chosen from this whitelist only — safe to inline into the SQL.
_INTERVAL_MAP = {"1h": "1 hour", "6h": "6 hours", "24h": "24 hours", "7d": "7 days"}
_BUCKET_MS = 5 * 60 * 1000  # 5-minute buckets, matching the DB time_bucket()


async def _pnl_from_redis(window: str) -> list[dict]:
    """Reconstruct the 5-min-bucketed PnL series from arb:orders (Redis).

    This is the source that actually has data in production: the engine writes
    closed-trade PnL to the arb:orders List, and NOTHING ever INSERTs into the
    Postgres `trades` table — so the DB query returns empty on the live stack.
    """
    trades = await _trades_from_redis(window)
    buckets: dict[int, dict] = {}
    for t in trades:
        b = (int(t["time"]) // _BUCKET_MS) * _BUCKET_MS
        agg = buckets.setdefault(b, {"pnl": 0.0, "trades": 0})
        agg["pnl"] += float(t.get("pnl", 0) or 0)
        agg["trades"] += 1
    out = []
    for b in sorted(buckets):
        iso = datetime.fromtimestamp(b / 1000, tz=timezone.utc).isoformat()
        out.append({"time": iso, "pnl": round(buckets[b]["pnl"], 4),
                    "trades": buckets[b]["trades"]})
    return out


@router.get("")
async def get_pnl(window: str = "24h", db: AsyncSession = Depends(get_db)):
    interval = _INTERVAL_MAP.get(window, "24 hours")
    data: list[dict] = []

    # Primary source: the trades hypertable (authoritative IF ever populated).
    # A DB outage — or the missing TimescaleDB time_bucket() — must NOT 500 the
    # PnL panel the way it used to, so any failure falls through to Redis.
    try:
        rows = await db.execute(
            text(
                f"SELECT time_bucket('5 minutes', time) AS bucket, "
                f"SUM(pnl) AS pnl, COUNT(*) AS trades "
                f"FROM trades WHERE time > NOW() - INTERVAL '{interval}' "
                f"GROUP BY bucket ORDER BY bucket ASC"
            )
        )
        data = [{"time": str(r[0]), "pnl": float(r[1] or 0), "trades": int(r[2])}
                for r in rows]
    except Exception:
        data = []

    # Fall back to the Redis order stream when the DB has nothing (the normal
    # production case) or is unreachable.
    if not data:
        try:
            data = await _pnl_from_redis(window)
        except Exception:
            data = []

    total_pnl = sum(d["pnl"] for d in data)
    return {"window": window, "total_pnl": round(total_pnl, 4), "data": data}
