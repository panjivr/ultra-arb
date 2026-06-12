"""
Regression test for LiveExecutor.

Pins the WRONGTYPE bug: arb:signals is a Redis LIST (publish → LPUSH), but the
old consumer used r.xread() (Streams API), which raised WRONGTYPE on every poll
so no signal was ever executed. The consumer must now read the list and, in
paper mode, emit a PAPER_TRADE order for each tradeable signal.
"""
import asyncio
import json

import pytest
import fakeredis.aioredis

import arb.infra.redis_bus as bus
from arb.config import settings
from arb.execution.live_executor import LiveExecutor
from arb.risk.risk_runner import RiskRunner


@pytest.fixture
def fake_redis(monkeypatch):
    r = fakeredis.aioredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(bus, "_pool", r)
    return r


@pytest.mark.asyncio
async def test_consumer_executes_tradeable_signal_in_paper_mode(fake_redis, monkeypatch):
    monkeypatch.setattr(settings, "paper_trade", True)
    r = fake_redis

    execu = LiveExecutor(RiskRunner())
    task = asyncio.create_task(execu._signal_consumer())
    await asyncio.sleep(0.05)  # let it establish the backlog cursor

    # A real, tradeable signal arrives AFTER startup (consumer ignores backlog).
    await bus.publish("arb:signals", {
        "strategy": "CrossExchange", "strategy_id": "CrossExchange",
        "symbol": "BTC/USDT", "probability_score": 0.72,
        "risk_reward_ratio": 2.5, "regime": 0, "liquidity_score": 0.8,
        "direction": "long", "spread_bps_real": 12.3,
        "tradeable": True,
        "signal_ts": 9_999_999_999_999,
    })
    # A non-tradeable signal must NOT produce an order.
    await bus.publish("arb:signals", {
        "strategy": "CrossExchange", "symbol": "ETH/USDT",
        "probability_score": 0.51, "tradeable": False,
        "signal_ts": 9_999_999_999_998,
    })

    # Give the consumer a couple of poll cycles (it sleeps 0.2s).
    for _ in range(20):
        await asyncio.sleep(0.05)
        if await r.llen("arb:orders") > 0:
            break

    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    orders = [json.loads(x) for x in await r.lrange("arb:orders", 0, -1)]
    paper = [o for o in orders if o.get("event") == "PAPER_TRADE"]
    assert len(paper) == 1, f"expected exactly one paper order, got {orders}"
    o = paper[0]
    assert o["symbol"] == "BTC/USDT"
    assert o["strategy"] == "CrossExchange"
    assert o["size_usd"] > 0  # Kelly sized something for a 0.72 / 2.5RR signal
