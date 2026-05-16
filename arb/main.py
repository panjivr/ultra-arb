"""
Ultra AI Arbitrage System — main entrypoint.
Starts all subsystems concurrently:
  - Market data feeds (Binance, Bybit, Polymarket)
  - ML model runner (HMM, Cointegration, Bayesian)
  - Risk engine (circuit breakers, position manager)
  - Signal-driven executor (paper or live)
  - Strategy runners (funding rate, Polymarket arb)

Usage: python -m arb.main
"""
import asyncio
import signal
from arb.feeds.feed_runner import main as feeds_main
from arb.models.model_runner import ModelRunner
from arb.risk.risk_runner import RiskRunner
from arb.execution.live_executor import LiveExecutor
from arb.strategies.funding_rate import FundingRateStrategy
from arb.strategies.polymarket_arb import PolymarketArbStrategy
from arb.config import settings


async def main() -> None:
    print("=" * 60)
    print("  ULTRA AI ARBITRAGE SYSTEM")
    print(f"  Mode: {'PAPER TRADE' if settings.paper_trade else '⚡ LIVE TRADING'}")
    print("=" * 60)

    model_runner = ModelRunner()
    risk_runner = RiskRunner()
    executor = LiveExecutor(risk_runner)
    funding_strategy = FundingRateStrategy()
    poly_strategy = PolymarketArbStrategy()

    tasks = [
        asyncio.create_task(feeds_main(), name="feeds"),
        asyncio.create_task(model_runner.start(), name="models"),
        asyncio.create_task(risk_runner.start(), name="risk"),
        asyncio.create_task(executor.start(), name="executor"),
        asyncio.create_task(funding_strategy.run(), name="funding_rate"),
        asyncio.create_task(poly_strategy.run(), name="polymarket_arb"),
    ]

    print(f"[main] {len(tasks)} subsystems started.")

    loop = asyncio.get_event_loop()

    def _shutdown():
        print("\n[main] Shutdown signal received. Stopping...")
        for t in tasks:
            t.cancel()

    loop.add_signal_handler(signal.SIGINT, _shutdown)
    loop.add_signal_handler(signal.SIGTERM, _shutdown)

    try:
        await asyncio.gather(*tasks, return_exceptions=True)
    finally:
        await executor.stop()
        print("[main] All subsystems stopped.")


if __name__ == "__main__":
    asyncio.run(main())
