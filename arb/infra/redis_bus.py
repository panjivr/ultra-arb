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
    Polling consumer loop using BRPOP (blocking pop from the tail).

    publish() prepends with LPUSH (newest at head), so the OLDEST message sits
    at the tail. BRPOP pops the tail → FIFO delivery order. (The old BLPOP
    popped the head → LIFO, delivering newest-first and starving older messages
    under load.)
    """
    r = get_redis()
    while True:
        try:
            # Use BRPOP with timeout for blocking pop from the tail (FIFO).
            result = await r.brpop([stream], timeout=block_ms / 1000)
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


async def read_new(stream: str, last_seen_ts: int = 0, count: int = 50) -> tuple[list[dict], int]:
    """
    Non-blocking read of messages newer than `last_seen_ts` (epoch ms cursor).
    Returns (messages_newest_first, new_cursor_ts). For the WebSocket routes —
    poll at ~100ms intervals; pass the returned cursor back in each call.

    Why a timestamp cursor and not a list index: arb:* are CAPPED Redis Lists
    (publish → LPUSH at head, then LTRIM to MAX_LIST_LENGTH). An index/llen
    cursor breaks the moment a list saturates — llen stops growing while items
    keep flowing through the head, so `total - last_seen_index` goes ≤ 0 and the
    feed silently dies. The newest item's `ts` (always injected by publish())
    is monotonic and survives both the cap and trimming.
    """
    r = get_redis()
    # O(1) head peek — skip the lrange entirely when nothing is new (works even
    # at the cap, where llen no longer changes).
    head = await r.lindex(stream, 0)
    if head is None:
        return [], last_seen_ts
    try:
        head_ts = int(json.loads(head).get("ts", 0) or 0)
    except Exception:
        head_ts = 0
    if head_ts <= last_seen_ts:
        return [], last_seen_ts

    raw_list = await r.lrange(stream, 0, count - 1)  # newest-first
    result = []
    max_ts = last_seen_ts
    for raw in raw_list:
        try:
            d = json.loads(raw)
        except Exception:
            continue
        ts = int(d.get("ts", 0) or 0)
        if ts <= last_seen_ts:
            continue
        result.append(d)
        if ts > max_ts:
            max_ts = ts
    return result, max(max_ts, head_ts)
