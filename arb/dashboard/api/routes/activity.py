"""
Live activity monitor — real-time rates of every operation the system does.
Shows the user that the bot is actively fetching, computing, executing.
"""
import time
from collections import defaultdict
from fastapi import APIRouter
from arb.infra.redis_bus import get_redis, latest

router = APIRouter(prefix="/api", tags=["activity"])


def _rate_per_sec(timestamps: list[int], window_ms: int = 60_000) -> float:
    """Calc msgs/sec over the last window_ms."""
    if not timestamps: return 0.0
    now = int(time.time() * 1000)
    cutoff = now - window_ms
    recent = [t for t in timestamps if t > cutoff]
    return len(recent) / (window_ms / 1000) if recent else 0.0


_NON_LIST_PREFIXES = ("arb:wallet:", "arb:bloomberg:cache:", "arb:config:")


def _is_stream_key(key: str) -> bool:
    """Filter keys that are NOT list-typed (wallet state, bloomberg cache, etc)."""
    return not any(key.startswith(p) for p in _NON_LIST_PREFIXES)


@router.get("/activity")
async def get_live_activity():
    """
    Real-time activity rates across every Redis stream.
    Shows: ticks/sec per exchange, signals/sec, orders/sec, total ops/min.
    """
    r = get_redis()
    all_keys = await r.keys("arb:*")
    keys = [k for k in all_keys if _is_stream_key(k)]

    streams = []
    total_msgs = 0
    total_rate = 0.0

    for key in sorted(keys):
        # Skip keys that aren't lists (safety check)
        try:
            ktype = await r.type(key)
            if ktype != "list":
                continue
        except Exception:
            continue
        # Cap at 120 items per key (covers 60s window at 2 msgs/s)
        raw = await r.lrange(key, 0, 119)
        timestamps = []
        for item in raw:
            try:
                import json
                d = json.loads(item)
                ts = d.get("ts", 0)
                if ts: timestamps.append(ts)
            except Exception:
                pass

        rate_1s = _rate_per_sec(timestamps, 1_000)
        rate_60s = _rate_per_sec(timestamps, 60_000)
        rate_5m = _rate_per_sec(timestamps, 300_000)
        llen = await r.llen(key)
        total_msgs += llen
        total_rate += rate_60s

        # Classify stream type
        kind = "tick" if "ticks:" in key else \
               "signal" if "signals" in key else \
               "order" if "orders" in key else \
               "funding" if "funding:" in key else \
               "risk" if "risk:" in key else \
               "model" if "models:" in key else \
               "position" if "positions:" in key else "other"

        streams.append({
            "stream": key,
            "kind": kind,
            "total": llen,
            "rate_1s": round(rate_1s, 2),
            "rate_60s": round(rate_60s, 2),
            "rate_5m": round(rate_5m, 2),
            "last_ts": max(timestamps) if timestamps else 0,
        })

    # Aggregate by kind
    by_kind: dict[str, dict] = defaultdict(lambda: {"streams": 0, "total": 0, "rate": 0.0})
    for s in streams:
        by_kind[s["kind"]]["streams"] += 1
        by_kind[s["kind"]]["total"] += s["total"]
        by_kind[s["kind"]]["rate"] += s["rate_60s"]

    return {
        "ts": int(time.time() * 1000),
        "total_messages": total_msgs,
        "total_rate_per_sec": round(total_rate, 2),
        "total_rate_per_min": round(total_rate * 60, 1),
        "total_rate_per_hour": round(total_rate * 3600, 0),
        "stream_count": len(streams),
        "streams": streams,
        "by_kind": [
            {"kind": k, **v, "rate": round(v["rate"], 2)}
            for k, v in by_kind.items()
        ],
    }


@router.get("/activity/recent")
async def get_recent_events(limit: int = 30):
    """
    Last N events across all streams — for the scrolling event log ticker.
    """
    r = get_redis()
    all_keys = await r.keys("arb:*")
    keys = [k for k in all_keys if _is_stream_key(k)]
    events = []

    for key in keys:
        try:
            ktype = await r.type(key)
            if ktype != "list":
                continue
        except Exception:
            continue
        raw = await r.lrange(key, 0, 5)
        for item in raw:
            try:
                import json
                d = json.loads(item)
                events.append({
                    "stream": key.replace("arb:", ""),
                    "ts": d.get("ts", 0),
                    "data": d,
                })
            except Exception:
                pass

    events.sort(key=lambda x: x["ts"], reverse=True)
    return {"events": events[:limit], "count": len(events[:limit])}
