"""
Edge Detection Engine — runs all 6 edge scanners in parallel.

Strategies:
  1. YES/NO sum arbitrage     — math certainty when prices don't sum to $1
  2. Smart money copy-trade   — mirror top Polymarket wallets
  3. Time-decay arbitrage     — near-expiry price convergence
  4. Related markets          — probability ordering violations
  5. News-reaction speed      — bet on high-impact news within seconds
  6. Basis carry              — funding-rate APR opportunities

Run: python scripts/edge_runner.py
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from arb.edges.yesno_arb import run_yesno_arb_loop
from arb.edges.smart_money import run_smart_money_loop
from arb.edges.time_decay import run_time_decay_loop
from arb.edges.related_markets import run_related_arb_loop
from arb.edges.news_reaction import run_news_reaction_loop
from arb.edges.basis_carry import run_basis_carry_loop
from arb.edges.onchain_intel import run_onchain_intel_loop
from arb.edges.copy_leaders import run_copy_leaders


async def main():
    print("[edge_runner] starting edge scanners + leader copy-trade in parallel")
    print("  • Copy-trade TOP 1-10 Polymarket leaders")
    print("  • YES/NO sum arbitrage (30s)")
    print("  • Smart money copy-trade (120s)")
    print("  • Time-decay arbitrage (30s)")
    print("  • Related markets arb (60s)")
    print("  • News reaction (15s)")
    print("  • Basis carry (120s)")
    print("  • On-chain intelligence (60s)")
    print()

    await asyncio.gather(
        run_copy_leaders(),
        run_yesno_arb_loop(interval_s=30),
        run_smart_money_loop(interval_s=120),
        run_time_decay_loop(interval_s=30),
        run_related_arb_loop(interval_s=60),
        run_news_reaction_loop(interval_s=15),
        run_basis_carry_loop(interval_s=120),
        run_onchain_intel_loop(interval_s=60),
    )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[edge_runner] stopped")
