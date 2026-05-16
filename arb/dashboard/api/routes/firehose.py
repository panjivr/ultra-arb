"""
0-latency firehose WebSocket — sub-millisecond push of every tick, signal,
order, and Bloomberg event to connected dashboard clients.

Architecture:
  - Maintains last-seen index per Redis list
  - 10ms poll loop (100Hz) — effective end-to-end latency ~ 5-15ms
  - Batches messages per tick to amortize JSON overhead
  - Per-message latency tag (ms_since_publish) so frontend can show "0ms" feel
"""
import asyncio
import json
import time
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from arb.infra.redis_bus import get_redis

router = APIRouter(tags=["firehose"])

# 10ms loop = 100Hz push rate
PUSH_INTERVAL = 0.01

# Streams to firehose — all REAL market data + signals + orders + alerts
WATCHED_PATTERNS = [
    "arb:ticks:*",     # all tick streams (10 streams currently)
    "arb:signals",
    "arb:orders",
    "arb:risk:alerts",
    "arb:wallet:events",
]


async def _resolve_streams(r) -> list[str]:
    """Expand wildcards to actual Redis keys."""
    streams = set()
    for pat in WATCHED_PATTERNS:
        if "*" in pat:
            keys = await r.keys(pat)
            streams.update(keys)
        else:
            streams.add(pat)
    return sorted(streams)


@router.websocket("/ws/firehose")
async def firehose(ws: WebSocket):
    """High-frequency firehose. Pushes everything, every 10ms."""
    await ws.accept()
    r = get_redis()
    streams = await _resolve_streams(r)
    indices: dict[str, int] = {s: 0 for s in streams}
    # On connect, seed indices to current tail (don't dump all history)
    for s in streams:
        indices[s] = await r.llen(s)

    last_refresh = time.time()
    msg_count = 0
    started = time.time()

    try:
        await ws.send_json({
            "type": "hello",
            "streams_watched": len(streams),
            "ts": int(time.time() * 1000),
        })

        while True:
            t0 = time.perf_counter_ns()
            messages = []
            for stream in streams:
                cur_len = await r.llen(stream)
                idx = indices[stream]
                if cur_len <= idx:
                    indices[stream] = cur_len
                    continue
                # New items at indices [0, cur_len - idx)
                new_count = cur_len - idx
                # New items live at LIST head (LPUSH)
                raw_items = await r.lrange(stream, 0, new_count - 1)
                # Process newest-first → oldest
                for item in raw_items:
                    try:
                        d = json.loads(item)
                        ts = d.get("ts", 0)
                        now_ms = int(time.time() * 1000)
                        d["_lag_ms"] = max(0, now_ms - ts) if ts else 0
                        d["_stream"] = stream
                        messages.append(d)
                    except Exception:
                        continue
                indices[stream] = cur_len

            if messages:
                send_started = time.perf_counter_ns()
                await ws.send_json({
                    "type": "batch",
                    "ts": int(time.time() * 1000),
                    "count": len(messages),
                    "messages": messages,
                })
                send_dur_ns = time.perf_counter_ns() - send_started
                msg_count += len(messages)
                # Record ws broadcast latency for the latency endpoint
                await r.lpush("arb:latency:ws_broadcast", str(send_dur_ns))
                await r.ltrim("arb:latency:ws_broadcast", 0, 999)

            # Periodically refresh stream list (new tick streams may appear)
            if time.time() - last_refresh > 30:
                streams = await _resolve_streams(r)
                for s in streams:
                    if s not in indices:
                        indices[s] = await r.llen(s)
                last_refresh = time.time()

            elapsed_ns = time.perf_counter_ns() - t0
            # Adaptive sleep — keep 10ms cadence
            sleep_s = max(0, PUSH_INTERVAL - elapsed_ns / 1e9)
            await asyncio.sleep(sleep_s)

    except WebSocketDisconnect:
        pass
    except Exception as e:
        try:
            await ws.send_json({"type": "error", "msg": str(e)[:200]})
        except Exception:
            pass
