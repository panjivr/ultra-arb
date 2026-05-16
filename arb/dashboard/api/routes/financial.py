"""
financialdatasets.ai integration — real equities, fundamentals, earnings.

The bot uses this data as macro/correlation signals:
  - AAPL/MSFT/NVDA — tech sector → BTC correlation
  - TSLA — Bitcoin treasury exposure (Tesla holds BTC)
  - GOOGL — AI/quantum proxy
  - COIN/MSTR — crypto-correlated equities (require API key)

Free tier (no API key): AAPL, GOOGL, MSFT, NVDA, TSLA — prices + fundamentals.
Add FINANCIAL_DATASETS_API_KEY to .env for full 17,000+ ticker access.
"""
import asyncio
import json
import os
import time
from fastapi import APIRouter
import httpx
from arb.infra.redis_bus import get_redis

router = APIRouter(prefix="/api/financial", tags=["financial"])

API_KEY = os.environ.get("FINANCIAL_DATASETS_API_KEY", "").strip()
BASE = "https://api.financialdatasets.ai"

# Watchlist — crypto-relevant equities
FREE_TICKERS = ["AAPL", "GOOGL", "MSFT", "NVDA", "TSLA"]
PRO_TICKERS = ["COIN", "MSTR", "RIOT", "MARA", "HOOD", "SQ", "PYPL", "PLTR"]

_timeout = httpx.Timeout(10.0, connect=5.0)


def _headers() -> dict:
    return {"X-API-KEY": API_KEY} if API_KEY else {}


async def _cached(key: str, ttl: int, fetcher):
    r = get_redis()
    ck = f"arb:financial:cache:{key}"
    cached = await r.get(ck)
    if cached:
        try:
            return {**json.loads(cached), "_cached": True}
        except Exception:
            pass
    try:
        data = await fetcher()
        await r.set(ck, json.dumps(data), ex=ttl)
        return {**data, "_cached": False, "_fetched_at": int(time.time() * 1000)}
    except Exception as e:
        return {"error": str(e)[:200], "_cached": False}


async def _fetch_snapshot(ticker: str) -> dict | None:
    async with httpx.AsyncClient(timeout=_timeout, headers=_headers()) as client:
        r = await client.get(f"{BASE}/prices/snapshot", params={"ticker": ticker})
        if r.status_code != 200:
            return None
        return r.json().get("snapshot")


async def _fetch_metrics(ticker: str) -> dict | None:
    async with httpx.AsyncClient(timeout=_timeout, headers=_headers()) as client:
        r = await client.get(f"{BASE}/financial-metrics/snapshot", params={"ticker": ticker})
        if r.status_code != 200:
            return None
        return r.json().get("snapshot")


# ─────────── EQUITIES WATCHLIST ───────────
@router.get("/watchlist")
async def get_watchlist():
    """Live snapshot of crypto-relevant equities."""
    async def fetcher():
        tickers = FREE_TICKERS + (PRO_TICKERS if API_KEY else [])
        results = await asyncio.gather(
            *[_fetch_snapshot(t) for t in tickers],
            return_exceptions=True,
        )
        items = []
        for t, snap in zip(tickers, results):
            if isinstance(snap, Exception) or snap is None:
                continue
            items.append({
                "ticker": t,
                "price": snap.get("price"),
                "change": snap.get("day_change"),
                "change_pct": snap.get("day_change_percent"),
                "time": snap.get("time"),
                "is_pro": t in PRO_TICKERS,
            })
        return {"watchlist": items, "count": len(items),
                "api_key_loaded": bool(API_KEY),
                "tickers_available": len(tickers)}

    return await _cached("watchlist", 30, fetcher)


# ─────────── DETAILED METRICS (single ticker) ───────────
@router.get("/metrics/{ticker}")
async def get_metrics(ticker: str):
    """Full fundamentals snapshot — P/E, P/B, market cap, ROE, margins, etc."""
    ticker = ticker.upper()

    async def fetcher():
        snap = await _fetch_snapshot(ticker)
        metrics = await _fetch_metrics(ticker)
        if not snap and not metrics:
            return {"error": "ticker unavailable (may require API key)", "ticker": ticker}
        return {
            "ticker": ticker,
            "price": snap or {},
            "metrics": metrics or {},
        }

    return await _cached(f"metrics:{ticker}", 60, fetcher)


# ─────────── CRYPTO CORRELATION (uses our internal BTC prices) ───────────
@router.get("/correlation")
async def crypto_equities_correlation():
    """
    Rough equity vs crypto correlation hint based on day-change directionality.
    Useful as macro signal: if equities sell off → crypto often follows.
    """
    async def fetcher():
        # Get equity snapshots
        snaps = await asyncio.gather(
            *[_fetch_snapshot(t) for t in FREE_TICKERS],
            return_exceptions=True,
        )
        equity_avg_change = 0.0
        n = 0
        rows = []
        for t, s in zip(FREE_TICKERS, snaps):
            if isinstance(s, Exception) or s is None:
                continue
            cp = s.get("day_change_percent", 0) or 0
            equity_avg_change += cp
            n += 1
            rows.append({"ticker": t, "change_pct": cp})
        equity_avg_change = equity_avg_change / max(n, 1)

        # Get BTC price from our Redis tick stream
        r = get_redis()
        btc_now = 0
        try:
            keys = await r.keys("arb:ticks:BTC/USDT*")
            if keys:
                raw = await r.lindex(keys[0], 0)
                if raw:
                    btc_now = float(json.loads(raw).get("mid", 0))
        except Exception:
            pass

        sentiment = (
            "RISK-ON" if equity_avg_change > 0.5 else
            "RISK-OFF" if equity_avg_change < -0.5 else
            "NEUTRAL"
        )
        return {
            "equity_avg_change_pct": round(equity_avg_change, 3),
            "btc_price_now": btc_now,
            "sentiment": sentiment,
            "rows": rows,
            "signal": (
                "BULLISH for BTC" if sentiment == "RISK-ON" else
                "BEARISH for BTC" if sentiment == "RISK-OFF" else
                "NO DIRECTIONAL EDGE"
            ),
        }

    return await _cached("correlation", 60, fetcher)


# ─────────── STATUS ───────────
@router.get("/status")
async def status():
    return {
        "api_key_loaded": bool(API_KEY),
        "free_tickers": FREE_TICKERS,
        "pro_tickers_available": PRO_TICKERS if API_KEY else [],
        "docs": "https://docs.financialdatasets.ai/",
        "upgrade_hint": "Set FINANCIAL_DATASETS_API_KEY in .env to unlock 17,000+ tickers + earnings + filings",
    }
