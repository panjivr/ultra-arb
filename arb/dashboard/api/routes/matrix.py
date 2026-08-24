"""
Robustness Matrix — REAL multi-timeframe returns for the tracked crypto assets.

Like the reference terminal's 7-asset × 6-timeframe grid, but every number is
real: computed from Gate.io spot candlesticks (public, free). One 5-minute
candle series per asset (≈1 day) is fetched and every timeframe is derived from
it, so it's just 7 upstream calls, cached in Redis.
"""
import json
import time
import httpx
from fastapi import APIRouter
from arb.infra.redis_bus import get_redis

router = APIRouter(prefix="/api", tags=["matrix"])

ASSETS = ["BTC", "ETH", "SOL", "BNB", "XRP", "ADA", "DOT"]
# timeframe label -> how many 5-minute candles it spans
TF = {"5m": 1, "15m": 3, "30m": 6, "1h": 12, "4h": 48, "1d": 288}
GATE = "https://api.gateio.ws/api/v4/spot/candlesticks"
_TIMEOUT = httpx.Timeout(8, connect=4)


async def _candles(client, pair: str) -> list[list]:
    try:
        r = await client.get(GATE, params={"currency_pair": pair,
                                            "interval": "5m", "limit": "290"})
        if r.status_code == 200 and isinstance(r.json(), list):
            return r.json()
    except Exception:
        pass
    return []


def _ret_pct(candles: list[list], n: int) -> float | None:
    # Gate.io candle: [ts, quote_vol, close, high, low, open, ...]
    if len(candles) < n + 1:
        return None
    try:
        last_close = float(candles[-1][2])
        past_open = float(candles[-(n)][5]) if n >= 1 else float(candles[-1][5])
        if past_open <= 0:
            return None
        return (last_close / past_open - 1.0) * 100.0
    except Exception:
        return None


@router.get("/matrix")
async def robustness_matrix():
    r = get_redis()
    ck = "arb:matrix:cache"
    cached = await r.get(ck)
    if cached:
        try:
            return json.loads(cached)
        except Exception:
            pass

    rows = []
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        for sym in ASSETS:
            candles = await _candles(client, f"{sym}_USDT")
            rets = {tf: _ret_pct(candles, n) for tf, n in TF.items()}
            vals = [v for v in rets.values() if v is not None]
            avg = round(sum(vals) / len(vals), 2) if vals else None
            rows.append({
                "asset": f"{sym}USD",
                "symbol": sym,
                "returns": {k: (round(v, 1) if v is not None else None) for k, v in rets.items()},
                "avg": avg,
                "price": (round(float(candles[-1][2]), 4) if candles else None),
            })

    out = {"timeframes": list(TF.keys()), "rows": rows, "ts": int(time.time() * 1000)}
    await r.set(ck, json.dumps(out), ex=60)
    return out
