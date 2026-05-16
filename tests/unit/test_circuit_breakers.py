"""Unit tests for circuit breakers."""
import asyncio
import pytest
from arb.risk.circuit_breakers import DrawdownBreaker, VolatilityBreaker


@pytest.mark.asyncio
async def test_drawdown_breaker_triggers():
    breaker = DrawdownBreaker(max_drawdown_pct=2.0)
    triggered = await breaker.check_pct(-0.025)  # -2.5% loss
    assert triggered is True
    assert breaker.is_halted is True


@pytest.mark.asyncio
async def test_drawdown_breaker_no_trigger():
    breaker = DrawdownBreaker(max_drawdown_pct=2.0)
    triggered = await breaker.check_pct(-0.01)  # -1% loss, within limit
    assert triggered is False
    assert breaker.is_halted is False


@pytest.mark.asyncio
async def test_vol_breaker_triggers():
    # long_window=200 ensures baseline dominates long_vol even after spikes
    breaker = VolatilityBreaker(short_window=10, long_window=200, multiplier=3.0)
    import random
    rng = random.Random(42)
    for _ in range(200):
        breaker.add_return(rng.gauss(0, 0.001))  # baseline: ~0.001 std
    for _ in range(10):
        breaker.add_return(rng.gauss(0, 0.1))    # spike: 100x baseline
    triggered = await breaker.check()
    assert triggered is True


def test_kelly_sizing():
    from arb.risk.sizing import kelly_size
    result = kelly_size(0.6, 1.5, 0.25)
    assert 0.0 < result <= 0.25
    assert kelly_size(0.4, 1.0, 0.25) == 0.0  # negative edge


def test_kelly_sizer():
    from arb.risk.sizing import KellyPositionSizer
    sizer = KellyPositionSizer(account_balance=10_000.0, max_pct_per_trade=0.025)
    result = sizer.compute(win_prob=0.65, risk_reward=2.0, regime=0)
    assert result["position_usd"] > 0
    assert result["position_usd"] <= 250  # max 2.5% of 10k
