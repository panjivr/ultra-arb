from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from arb.config import settings
from arb.dashboard.api.routes import (
    pnl, signals, positions, ws, stats, markets, activity, extended_stats,
    wallet, bloomberg, latency, firehose, financial, polymarket, compounding,
    edges, onchain, mode,
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    from arb.dashboard.api.routes.wallet import _migrate_old_wallet
    await _migrate_old_wallet()
    yield

app = FastAPI(title="REYOG CAPITAL — Market Intelligence API", version="0.3.0", lifespan=lifespan)

# Parse CORS_ORIGINS env: comma-separated list or "*"
_origins_raw = settings.cors_origins.strip()
if _origins_raw == "*":
    _allow_origins = ["*"]
else:
    _allow_origins = [o.strip() for o in _origins_raw.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(pnl.router)
app.include_router(signals.router)
app.include_router(positions.router)
app.include_router(ws.router)
app.include_router(stats.router)
app.include_router(markets.router)
app.include_router(activity.router)
app.include_router(extended_stats.router)
app.include_router(wallet.router)
app.include_router(bloomberg.router)
app.include_router(latency.router)
app.include_router(firehose.router)
app.include_router(financial.router)
app.include_router(polymarket.router)
app.include_router(compounding.router)
app.include_router(edges.router)
app.include_router(onchain.router)
app.include_router(mode.router)


@app.get("/health")
async def health():
    return {"status": "ok"}
