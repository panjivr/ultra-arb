"""
On-chain intelligence API — whale movements and trending meme coins.

Data source: Redis key ``arb:edges:onchain_intel`` (JSON with keys
``hyperliquid_whales``, ``meme_trending``, ``ts``).
"""
import json
import time
from fastapi import APIRouter
from arb.infra.redis_bus import get_redis

router = APIRouter(prefix="/api/onchain", tags=["onchain"])

REDIS_KEY = "arb:edges:onchain_intel"


async def _load_intel(limit: int = 50) -> list[dict]:
    """Read latest entries from the onchain_intel list."""
    r = get_redis()
    raws = await r.lrange(REDIS_KEY, 0, limit - 1)
    entries = []
    for raw in raws:
        try:
            entries.append(json.loads(raw))
        except Exception:
            continue
    return entries


@router.get("/whales")
async def whales():
    """Latest whale activity from Hyperliquid and other chains."""
    entries = await _load_intel()
    whale_entries = [e for e in entries if e.get("source") == "hyperliquid"]
    return {
        "whales": whale_entries,
        "count": len(whale_entries),
        "ts": int(time.time() * 1000),
    }


@router.get("/trending")
async def trending():
    """Trending meme coins detected on-chain."""
    entries = await _load_intel()
    meme_entries = [e for e in entries if e.get("source") == "dexscreener"]
    return {
        "trending": meme_entries,
        "count": len(meme_entries),
        "ts": int(time.time() * 1000),
    }


@router.get("/summary")
async def summary():
    """Combined on-chain intelligence summary."""
    entries = await _load_intel(100)
    whale_entries = [e for e in entries if e.get("source") == "hyperliquid"]
    meme_entries = [e for e in entries if e.get("source") == "dexscreener"]
    return {
        "whales": whale_entries,
        "trending": meme_entries,
        "whale_count": len(whale_entries),
        "trending_count": len(meme_entries),
        "total_signals": len(entries),
        "ts": int(time.time() * 1000),
    }
