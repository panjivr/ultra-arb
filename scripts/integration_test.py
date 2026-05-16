"""Full integration test — run as: python scripts/integration_test.py"""
import asyncio
import sys
import time
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


async def main():
    from arb.infra.redis_bus import publish, latest
    from arb.risk.sizing import KellyPositionSizer
    from arb.models.hmm import RegimeDetector
    from arb.models.kalman_filter import KalmanSpreadTracker
    from arb.risk.circuit_breakers import DrawdownBreaker
    from hot_paths import kelly_size, spread_bps
    from arb.execution.paper_trader import PaperTradeEngine

    print("=" * 50)
    print("  ULTRA ARB INTEGRATION TEST")
    print("=" * 50)

    # 1. Redis bus
    await publish("arb:signals", {
        "strategy": "CrossExchange", "symbol": "BTC/USDT",
        "probability_score": 0.78, "expected_value": 0.0025,
        "tradeable": True, "regime": 0, "ts": int(time.time() * 1000),
    })
    await publish("arb:signals", {
        "strategy": "FundingRate", "symbol": "ETH/USDT",
        "probability_score": 0.85, "expected_value": 0.12,
        "tradeable": True, "regime": 1, "ts": int(time.time() * 1000),
    })
    signals = await latest("arb:signals", count=5)
    print(f"[1] Redis bus: {len(signals)} signals in stream")
    assert len(signals) >= 2

    # 2. Kelly sizer
    sizer = KellyPositionSizer(account_balance=10_000.0)
    sz = sizer.compute(win_prob=0.65, risk_reward=2.5, regime=0)
    print(f"[2] Kelly sizer: position=${sz['position_usd']:.2f} fraction={sz['fraction']:.4f}")
    assert sz["position_usd"] > 0 and sz["position_usd"] <= 250

    # 3. HMM regime detector
    detector = RegimeDetector()
    detector.fit_synthetic()
    regime = detector.current_regime()
    print(f"[3] HMM regime: {regime} (0=low, 1=med, 2=high vol)")
    assert regime in (0, 1, 2)

    # 4. Kalman filter
    tracker = KalmanSpreadTracker()
    for price in [65000, 65010, 64990, 65005, 65020]:
        state, cov = tracker.update(price)
    print(f"[4] Kalman filter: state={state:.2f} cov={cov:.6f}")
    assert abs(state - 65000) < 100

    # 5. Circuit breaker
    breaker = DrawdownBreaker(max_drawdown_pct=2.0)
    triggered = await breaker.check_pct(-0.005)
    print(f"[5] Circuit breaker: triggered={triggered} (expected False)")
    assert not triggered

    # 6. Rust hot_paths
    ks = kelly_size(0.65, 2.5, 0.025)
    sb = spread_bps(65000, 65010)
    print(f"[6] Rust hot_paths: kelly={ks:.4f} spread={sb:.3f}bps")
    assert ks > 0
    assert sb > 0

    # 7. Paper trader
    engine = PaperTradeEngine(duration_hours=0.1)
    result = await engine.run()
    print(f"[7] Paper trader: {result['trades']} trades, {result['total_pct']:+.2f}% PnL")
    assert result["trades"] > 0

    print()
    print("=" * 50)
    print("  ALL SYSTEMS VERIFIED")
    print("=" * 50)


if __name__ == "__main__":
    asyncio.run(main())
