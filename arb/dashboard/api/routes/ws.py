"""
WebSocket endpoint: /ws/live
Pushes combined tick + signal data to connected clients at ~100ms cadence.
Uses polling (read_new) since we're on Redis Lists instead of Streams.
"""
import asyncio
import json
import time
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from arb.infra.redis_bus import get_redis, read_new

router = APIRouter(tags=["websocket"])
PUSH_INTERVAL = 0.1  # 100ms

# Non-tick streams are fixed. Tick streams are resolved dynamically from Redis
# so we follow whatever venues the engine actually publishes (GATEIO/HTX in
# production; BINANCE/BYBIT only if feed_runner is running). Hardcoding venues
# meant the live feed watched empty BINANCE/BYBIT keys and showed no ticks.
FIXED_STREAMS = ["arb:signals", "arb:risk:alerts"]
STREAM_REFRESH_SECONDS = 30


async def _resolve_tick_streams(r) -> list[str]:
    try:
        return sorted(await r.keys("arb:ticks:*"))
    except Exception:
        return []


@router.websocket("/ws/live")
async def live_ws(websocket: WebSocket):
    await websocket.accept()
    r = get_redis()
    watched = await _resolve_tick_streams(r) + FIXED_STREAMS
    # Timestamp cursor per stream (epoch ms). See redis_bus.read_new.
    cursors: dict[str, int] = {s: 0 for s in watched}
    last_refresh = time.time()

    try:
        while True:
            messages = []
            for stream in watched:
                new_msgs, cursor = await read_new(stream, cursors.get(stream, 0), count=20)
                cursors[stream] = cursor
                for msg in new_msgs:
                    msg["_stream"] = stream
                    messages.append(msg)

            if messages:
                await websocket.send_json({
                    "ts": int(time.time() * 1000),
                    "messages": messages,
                })
            else:
                await websocket.send_json({"ts": int(time.time() * 1000), "heartbeat": True})

            # New tick streams can appear after connect (extra symbols/venues).
            if time.time() - last_refresh > STREAM_REFRESH_SECONDS:
                for s in await _resolve_tick_streams(r):
                    if s not in cursors:
                        cursors[s] = 0
                        watched.append(s)
                last_refresh = time.time()

            await asyncio.sleep(PUSH_INTERVAL)
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
