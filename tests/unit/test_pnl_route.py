"""
Regression test for the /api/pnl route's Redis fallback.

The bug: get_pnl queried the Postgres `trades` table, which NOTHING ever
INSERTs into (the engine writes closed-trade PnL only to the arb:orders Redis
List). So the endpoint 500'd when the DB was unreachable and returned an empty
chart even when it was up. The fix reconstructs the 5-min-bucketed series from
arb:orders — this pins that reconstruction.
"""
import time

import pytest
import fakeredis.aioredis

import arb.infra.redis_bus as bus
from arb.dashboard.api.routes import pnl


@pytest.fixture
def fake_redis(monkeypatch):
    r = fakeredis.aioredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(bus, "_pool", r)
    return r


async def _close(r, ts, pnl_val):
    await bus.publish("arb:orders", {
        "ts": ts, "event": "CLOSE", "pnl": pnl_val,
        "symbol": "BTC/USDT", "strategy": "polymarket",
        "direction": "long", "size_usd": 50, "exit_price": 0.6,
    })


@pytest.mark.asyncio
async def test_pnl_from_redis_reconstructs_and_buckets(fake_redis):
    r = fake_redis
    now = int(time.time() * 1000)
    # Two trades ~1h apart (distinct 5-min buckets) + one non-CLOSE (ignored).
    await _close(r, now - 3_600_000, 1.5)
    await _close(r, now - 1_000, 2.0)
    await bus.publish("arb:orders", {"ts": now, "event": "OPEN", "symbol": "BTC/USDT"})

    data = await pnl._pnl_from_redis("24h")
    assert data, "should reconstruct a series from arb:orders"
    total = sum(d["pnl"] for d in data)
    assert abs(total - 3.5) < 1e-9  # OPEN event excluded
    assert sum(d["trades"] for d in data) == 2
    for d in data:
        assert set(d) == {"time", "pnl", "trades"}
        assert isinstance(d["time"], str)  # ISO timestamp, JSON-serialisable


@pytest.mark.asyncio
async def test_pnl_from_redis_empty_is_safe(fake_redis):
    # No orders at all — must return [] rather than raise.
    assert await pnl._pnl_from_redis("24h") == []


@pytest.mark.asyncio
async def test_pnl_from_redis_respects_window(fake_redis):
    r = fake_redis
    now = int(time.time() * 1000)
    await _close(r, now - 2 * 3_600_000, 5.0)   # 2h ago — inside 24h, outside 1h
    await _close(r, now - 60_000, 1.0)          # 1 min ago — inside both
    day = await pnl._pnl_from_redis("24h")
    hour = await pnl._pnl_from_redis("1h")
    assert abs(sum(d["pnl"] for d in day) - 6.0) < 1e-9
    assert abs(sum(d["pnl"] for d in hour) - 1.0) < 1e-9
