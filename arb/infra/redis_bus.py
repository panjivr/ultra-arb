"""
Central inter-process message bus.
Uses Redis Lists (LPUSH/LRANGE) for compatibility with Redis 3.x+.
API is identical to the Streams version — swap to Streams when Redis 5+ is available.
"""
import asyncio
import json
import time
from typing import Any, Awaitable, Callable
import redis.asyncio as aioredis
from arb.config import settings

_pool: aioredis.Redis | None = None
MAX_LIST_LENGTH = 50_000  # cap each stream at 50k entries (HFT volumes)


def get_redis() -> aioredis.Redis:
    global _pool
    if _pool is None:
        _pool = aioredis.from_url(settings.redis_url, decode_responses=True)
    return _pool


async def close_redis() -> None:
    global _pool
    if _pool is not None:
        await _pool.aclose()
        _pool = None


async def publish(stream: str, payload: dict[str, Any]) -> str:
    """Prepend message to list. Trims list to MAX_LIST_LENGTH. Returns synthetic ID."""
    r = get_redis()
    entry = json.dumps({"ts": payload.get("ts", int(time.time() * 1000)), **payload})
    pipe = r.pipeline()
    pipe.lpush(stream, entry)
    pipe.ltrim(stream, 0, MAX_LIST_LENGTH - 1)
    await pipe.execute()
    return f"{int(time.time() * 1000)}-0"


async def subscribe(
    stream: str,
    group: str,
    consumer: str,
    handler: Callable[[dict[str, Any]], Awaitable[None]],
    batch_size: int = 10,
    block_ms: int = 100,
) -> None:
    """
    Polling consumer loop using BLPOP (blocking pop from right/tail).
    Processes messages and calls handler. Runs until CancelledError.
    """
    r = get_redis()
    while True:
        try:
            # Use BLPOP with timeout for blocking pop
            result = await r.blpop([stream], timeout=block_ms / 1000)
            if result:
                _, raw = result
                try:
                    data = json.loads(raw)
                    await handler(data)
                except Exception as e:
                    print(f"[redis_bus] handler error on {stream}: {e}")
        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"[redis_bus] subscribe error on {stream}: {e}")
            await asyncio.sleep(1)


async def latest(stream: str, count: int = 50) -> list[dict[str, Any]]:
    """Read the last N messages from a stream (from head of list — most recent first)."""
    r = get_redis()
    raw_list = await r.lrange(stream, 0, count - 1)
    result = []
    for raw in raw_list:
        try:
            result.append(json.loads(raw))
        except Exception:
            pass
    return result


async def read_new(stream: str, last_seen_index: int = 0, count: int = 50) -> tuple[list[dict], int]:
    """
    Non-blocking read of new messages since last_seen_index.
    Returns (messages, new_last_index).
    For the WebSocket route — use polling at 100ms intervals.
    """
    r = get_redis()
    total = await r.llen(stream)
    if total <= last_seen_index:
        return [], last_seen_index

    # Read from tail (oldest at tail, newest at head)
    # Get all items newer than last_seen_index
    new_count = min(count, total - last_seen_index)
    raw_list = await r.lrange(stream, 0, new_count - 1)
    result = []
    for raw in raw_list:
        try:
            result.append(json.loads(raw))
        except Exception:
            pass
    return result, total
