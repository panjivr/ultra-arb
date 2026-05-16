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

WATCHED_STREAMS = [
    "arb:ticks:BTC/USDT:USDT:BINANCE",
    "arb:ticks:BTC/USDT:USDT:BYBIT",
    "arb:signals",
    "arb:risk:alerts",
]


@router.websocket("/ws/live")
async def live_ws(websocket: WebSocket):
    await websocket.accept()
    stream_indices: dict[str, int] = {s: 0 for s in WATCHED_STREAMS}

    try:
        while True:
            messages = []
            for stream in WATCHED_STREAMS:
                new_msgs, new_idx = await read_new(stream, stream_indices[stream], count=20)
                stream_indices[stream] = new_idx
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

            await asyncio.sleep(PUSH_INTERVAL)
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
