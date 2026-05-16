"""
Runs all market data feeds concurrently.
Usage: python -m arb.feeds.feed_runner
"""
import asyncio
from arb.feeds import binance_feed, bybit_feed, polymarket_feed


async def main() -> None:
    print("[feed_runner] Starting all market data feeds...")
    await asyncio.gather(
        binance_feed.run(),
        bybit_feed.run(),
        polymarket_feed.run(),
    )


if __name__ == "__main__":
    asyncio.run(main())
