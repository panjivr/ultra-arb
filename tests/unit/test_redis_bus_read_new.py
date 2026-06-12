"""
Regression tests for the Redis-List message bus cursor logic.

These pin the two bugs fixed in redis_bus.read_new:
  1. A timestamp cursor must keep delivering NEW items even after the list
     saturates at MAX_LIST_LENGTH (the old llen/index cursor went silent).
  2. read_new must never re-deliver an item the caller has already seen.
"""
import json

import pytest
import fakeredis.aioredis

import arb.infra.redis_bus as bus


@pytest.fixture
def fake_redis(monkeypatch):
    r = fakeredis.aioredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(bus, "_pool", r)
    return r


async def _publish(r, stream, ts, **extra):
    """Mimic redis_bus.publish() (LPUSH newest-at-head + cap trim)."""
    entry = json.dumps({"ts": ts, **extra})
    await r.lpush(stream, entry)
    await r.ltrim(stream, 0, bus.MAX_LIST_LENGTH - 1)


@pytest.mark.asyncio
async def test_read_new_returns_only_newer_items(fake_redis):
    r = fake_redis
    await _publish(r, "s", 1000, v="a")
    await _publish(r, "s", 1001, v="b")

    msgs, cursor = await bus.read_new("s", 0)
    assert {m["v"] for m in msgs} == {"a", "b"}
    assert cursor == 1001

    # Nothing new → empty, cursor unchanged.
    msgs2, cursor2 = await bus.read_new("s", cursor)
    assert msgs2 == []
    assert cursor2 == 1001

    # One more arrives → only that one comes back.
    await _publish(r, "s", 1002, v="c")
    msgs3, cursor3 = await bus.read_new("s", cursor2)
    assert [m["v"] for m in msgs3] == ["c"]
    assert cursor3 == 1002


@pytest.mark.asyncio
async def test_read_new_survives_list_saturation(fake_redis, monkeypatch):
    """Once the list is capped, llen stops growing — the cursor must still work."""
    r = fake_redis
    monkeypatch.setattr(bus, "MAX_LIST_LENGTH", 5)

    # Fill past the cap. llen is now pinned at 5 forever.
    for i in range(8):
        await _publish(r, "s", 2000 + i, v=i)
    assert await r.llen("s") == 5

    _, cursor = await bus.read_new("s", 0)
    assert cursor == 2007  # newest ts seen

    # More items flow through the (still capped) head — the old index cursor
    # returned nothing here. The ts cursor must deliver them.
    for i in range(8, 12):
        await _publish(r, "s", 2000 + i, v=i)
    assert await r.llen("s") == 5

    msgs, cursor2 = await bus.read_new("s", cursor)
    assert [m["v"] for m in msgs] == [11, 10, 9, 8]  # newest-first, none missed
    assert cursor2 == 2011


@pytest.mark.asyncio
async def test_read_new_empty_stream(fake_redis):
    msgs, cursor = await bus.read_new("nope", 0)
    assert msgs == []
    assert cursor == 0
