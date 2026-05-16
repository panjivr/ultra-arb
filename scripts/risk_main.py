"""
G1.1-prod: RiskRunner-only production service.

Why this exists (and is NOT `python -m arb.main`):
  arb.main also starts LiveExecutor + feeds_main. In production the engine
  (scripts/real_market_engine.py) is already the single honest writer to
  arb:orders (emit_trades) and the single price-feed source. Running the
  full arb.main alongside it would:
    - double-execute arb:signals (LiveExecutor vs emit_trades)
    - duplicate price feeds (feeds_main vs the engine)
    - trip LiveExecutor's own latent xread/WRONGTYPE bug (live_executor.py:52)
  ...all of which would re-pollute the honest paper window.

  This entrypoint runs ONLY the RiskRunner (DrawdownBreaker +
  VolatilityBreaker + arb:risk:halted publisher) plus a /health endpoint.
  RiskRunner reads arb:orders (read-only) and arb:signals is untouched.

Usage (container): python -m scripts.risk_main
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import uvicorn
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from arb.infra.redis_bus import get_redis
from arb.risk.risk_runner import RiskRunner

HEALTH_PORT = int(os.environ.get("RISK_HEALTH_PORT", "8001"))

app = FastAPI(title="reyog-risk", docs_url=None, redoc_url=None)
_risk: RiskRunner | None = None


@app.get("/health")
async def health() -> JSONResponse:
    """Liveness + Redis connectivity. 200 only if Redis reachable."""
    try:
        r = get_redis()
        await r.ping()
    except Exception as e:
        return JSONResponse(
            status_code=503,
            content={"status": "redis_unreachable", "error": repr(e)[:160]},
        )
    return JSONResponse(
        status_code=200,
        content={
            "status": "ok",
            "service": "reyog_risk",
            "halted": bool(_risk.is_halted) if _risk else None,
        },
    )


async def main() -> None:
    global _risk
    print("=" * 56)
    print("  REYOG RISK SERVICE  (RiskRunner-only — F2)")
    print("  NOT arb.main: no LiveExecutor, no feeds_main.")
    print(f"  /health on :{HEALTH_PORT}")
    print("=" * 56)

    _risk = RiskRunner()

    config = uvicorn.Config(
        app, host="0.0.0.0", port=HEALTH_PORT,
        log_level="warning", access_log=False,
    )
    server = uvicorn.Server(config)

    # RiskRunner.start() = _check_loop (sets/clears arb:risk:halted) +
    # _trade_monitor_loop (consumes arb:orders List → DrawdownBreaker).
    await asyncio.gather(
        asyncio.create_task(server.serve(), name="health"),
        asyncio.create_task(_risk.start(), name="risk"),
    )


if __name__ == "__main__":
    asyncio.run(main())
