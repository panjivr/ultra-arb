"""
Edge detection API — aggregated view of all live opportunities the bot found.

Streams:
  arb:edges:yesno_arb       — YES + NO sum != $1 (math arbitrage)
  arb:edges:smart_money     — Top wallet's recent positions
  arb:edges:time_decay      — Near-expiry mispricings
  arb:edges:related         — Probability ordering violations
  arb:edges:news_signal     — High-impact news with sentiment
  arb:edges:basis_carry     — Funding-rate basis trade APR
"""
import json
import time
from fastapi import APIRouter
from arb.infra.redis_bus import get_redis, latest

router = APIRouter(prefix="/api/edges", tags=["edges"])


@router.get("/all")
async def all_edges(limit: int = 20):
    """Aggregated edges across all detectors, sorted by recency."""
    r = get_redis()
    yesno = await latest("arb:edges:yesno_arb", count=limit)
    smart = await latest("arb:edges:smart_money", count=limit)
    decay = await latest("arb:edges:time_decay", count=limit)
    related = await latest("arb:edges:related", count=limit)
    news = await latest("arb:edges:news_signal", count=limit)
    basis = await latest("arb:edges:basis_carry", count=limit)

    return {
        "yesno_arb": yesno,
        "smart_money": smart,
        "time_decay": decay,
        "related": related,
        "news_signal": news,
        "basis_carry": basis,
        "counts": {
            "yesno_arb": len(yesno),
            "smart_money": len(smart),
            "time_decay": len(decay),
            "related": len(related),
            "news_signal": len(news),
            "basis_carry": len(basis),
        },
        "ts": int(time.time() * 1000),
    }


@router.get("/yesno-arb")
async def yesno_arb(limit: int = 30):
    items = await latest("arb:edges:yesno_arb", count=limit)
    return {"items": items, "count": len(items)}


@router.get("/smart-money")
async def smart_money(limit: int = 30):
    items = await latest("arb:edges:smart_money", count=limit)
    r = get_redis()
    raw = await r.get("arb:edges:smart_wallets")
    wallets = []
    if raw:
        try:
            wallets = json.loads(raw).get("wallets", [])
        except Exception:
            pass
    return {"signals": items, "top_wallets": wallets,
            "signal_count": len(items), "wallet_count": len(wallets)}


@router.get("/leaders")
async def leaders():
    """The TOP 1-10 Polymarket leaders we copy (from copy_leaders)."""
    r = get_redis()
    raw = await r.get("arb:edges:leaders")
    data = {}
    if raw:
        try:
            data = json.loads(raw)
        except Exception:
            data = {}
    return {"leaders": data.get("leaders", []), "top_n": data.get("top_n", 10),
            "ts": data.get("ts")}


@router.get("/copy-trades")
async def copy_trades(limit: int = 40):
    """Recent trades mirrored from the leaders."""
    items = await latest("arb:edges:copy_trades", count=limit)
    return {"items": items, "count": len(items)}


@router.get("/time-decay")
async def time_decay(limit: int = 20):
    items = await latest("arb:edges:time_decay", count=limit)
    return {"items": items, "count": len(items)}


@router.get("/related")
async def related(limit: int = 20):
    items = await latest("arb:edges:related", count=limit)
    return {"items": items, "count": len(items)}


@router.get("/news-signal")
async def news_signal(limit: int = 20):
    items = await latest("arb:edges:news_signal", count=limit)
    return {"items": items, "count": len(items)}


@router.get("/basis-carry")
async def basis_carry(limit: int = 10):
    items = await latest("arb:edges:basis_carry", count=limit)
    # Dedupe by symbol — keep newest
    seen = set()
    deduped = []
    for it in items:
        s = it.get("symbol")
        if s in seen:
            continue
        seen.add(s)
        deduped.append(it)
    return {"items": deduped, "count": len(deduped)}


@router.get("/summary")
async def edge_summary():
    """One-line summary: are we finding edge right now? Used for KPI cards."""
    r = get_redis()
    yesno_count = await r.llen("arb:edges:yesno_arb")
    smart_count = await r.llen("arb:edges:smart_money")
    decay_count = await r.llen("arb:edges:time_decay")
    related_count = await r.llen("arb:edges:related")
    news_count = await r.llen("arb:edges:news_signal")
    basis_count = await r.llen("arb:edges:basis_carry")

    # Get top-EV edge across all detectors
    candidates = []
    for stream in ["arb:edges:yesno_arb", "arb:edges:time_decay", "arb:edges:basis_carry"]:
        raw = await r.lindex(stream, 0)
        if raw:
            try:
                d = json.loads(raw)
                ev = (d.get("guaranteed_roi_pct", 0) or
                      (d.get("ev_per_dollar", 0) or 0) * 100 or
                      d.get("net_apr_after_costs", 0))
                if ev > 0:
                    candidates.append({"stream": stream, "ev_pct": ev, "data": d})
            except Exception:
                pass
    candidates.sort(key=lambda x: x["ev_pct"], reverse=True)

    return {
        "total_edges_24h": yesno_count + smart_count + decay_count + related_count + news_count + basis_count,
        "by_kind": {
            "yesno_arb": yesno_count,
            "smart_money": smart_count,
            "time_decay": decay_count,
            "related": related_count,
            "news_signal": news_count,
            "basis_carry": basis_count,
        },
        "top_edge": candidates[0] if candidates else None,
        "ts": int(time.time() * 1000),
    }
