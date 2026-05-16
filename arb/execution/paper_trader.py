"""
Paper trading simulation using synthetic data.
Runs a 1-hour backtest of cross-exchange arbitrage logic.
Usage: python -m arb.execution.paper_trader
"""
import asyncio
import time
import random
from arb.risk.sizing import KellyPositionSizer
from arb.risk.circuit_breakers import DrawdownBreaker, VolatilityBreaker
from arb.models.hmm import RegimeDetector


class PaperTradeEngine:
    def __init__(
        self,
        initial_balance: float = 10_000.0,
        duration_hours: float = 1.0,
        tick_interval: float = 0.1,  # simulated seconds per tick
    ) -> None:
        self._balance = initial_balance
        self._initial_balance = initial_balance
        self._duration = duration_hours * 3600
        self._tick_interval = tick_interval
        self._sizer = KellyPositionSizer(initial_balance)
        self._drawdown = DrawdownBreaker()
        self._vol_breaker = VolatilityBreaker()
        self._regime = RegimeDetector()
        self._trades: list[dict] = []
        self._rng = random.Random(42)

    def _simulate_tick(self, t: float) -> dict:
        """Generate synthetic BTC price with occasional cross-exchange inefficiencies."""
        base = 65_000 + 3_000 * (t / self._duration - 0.5)
        noise = self._rng.gauss(0, 20)
        half_spread = 2.0  # $2 half-spread per exchange

        # Inject arbitrage window: ~8% of ticks have a $150-$500 cross-exchange gap
        # At BTC=$65k, 16 bps = $104. Realistic arb window = 0.3-0.8% = $195-$520
        if self._rng.random() < 0.08:
            gap = self._rng.uniform(150, 500)
            direction = 1 if self._rng.random() < 0.5 else -1
        else:
            gap = 0.0
            direction = 1

        binance_bid = base + noise - half_spread
        binance_ask = base + noise + half_spread
        bybit_offset = gap * direction
        bybit_bid = base + noise + bybit_offset - half_spread
        bybit_ask = base + noise + bybit_offset + half_spread
        return {
            "binance_bid": binance_bid,
            "binance_ask": binance_ask,
            "bybit_bid": bybit_bid,
            "bybit_ask": bybit_ask,
        }

    def _compute_edge(self, tick: dict) -> tuple[float, str]:
        spread_ab = (tick["bybit_bid"] - tick["binance_ask"]) / tick["binance_ask"] * 10_000
        spread_ba = (tick["binance_bid"] - tick["bybit_ask"]) / tick["bybit_ask"] * 10_000
        if spread_ab > spread_ba:
            return spread_ab, "BUY_BINANCE_SELL_BYBIT"
        return spread_ba, "BUY_BYBIT_SELL_BINANCE"

    async def run(self) -> dict:
        self._regime.fit_synthetic()
        ticks = int(self._duration / self._tick_interval)
        print(f"[paper_trader] Running {ticks:,} ticks over {self._duration/3600:.1f}h simulation...")

        fee_bps = 14.0  # 7 bps each side x2 legs
        wins = losses = 0

        for i in range(ticks):
            t = i * self._tick_interval
            tick = self._simulate_tick(t)
            edge_bps, direction = self._compute_edge(tick)
            net_edge_bps = edge_bps - fee_bps

            if net_edge_bps > 2.0 and not self._drawdown.is_halted:
                regime = self._regime.current_regime()
                sizing = self._sizer.compute(
                    win_prob=min(0.9, 0.55 + net_edge_bps / 200),
                    risk_reward=net_edge_bps / fee_bps,
                    regime=regime,
                    liquidity_score=0.9,
                )
                position_usd = sizing["position_usd"]
                pnl = position_usd * net_edge_bps / 10_000
                pnl *= 1 if self._rng.random() < 0.65 else -0.3  # 65% win rate

                self._balance += pnl
                if pnl > 0:
                    wins += 1
                else:
                    losses += 1
                self._trades.append({
                    "t": t,
                    "direction": direction,
                    "edge_bps": round(edge_bps, 2),
                    "net_edge_bps": round(net_edge_bps, 2),
                    "position_usd": round(position_usd, 2),
                    "pnl": round(pnl, 4),
                    "balance": round(self._balance, 2),
                })
                daily_pct = (self._balance - self._initial_balance) / self._initial_balance
                await self._drawdown.check_pct(daily_pct)

            if i % (ticks // 10) == 0:
                pct = (self._balance - self._initial_balance) / self._initial_balance * 100
                print(f"  {i/ticks*100:.0f}% | Balance: ${self._balance:,.2f} ({pct:+.2f}%)")

        total_pnl = self._balance - self._initial_balance
        total_pct = total_pnl / self._initial_balance * 100
        n = len(self._trades)

        print(f"\n{'='*50}")
        print(f"Paper Trade Results ({self._duration/3600:.1f}h simulation)")
        print(f"{'='*50}")
        print(f"Total Trades  : {n}")
        print(f"Wins / Losses : {wins} / {losses} ({wins/max(n,1)*100:.1f}% win rate)")
        print(f"Final Balance : ${self._balance:,.2f}")
        print(f"Total PnL     : ${total_pnl:+,.2f} ({total_pct:+.2f}%)")
        if n > 0:
            avg_pnl = total_pnl / n
            print(f"Avg PnL/Trade : ${avg_pnl:+.4f}")
        print(f"{'='*50}")

        return {
            "trades": n,
            "wins": wins,
            "losses": losses,
            "final_balance": round(self._balance, 2),
            "total_pnl": round(total_pnl, 2),
            "total_pct": round(total_pct, 2),
        }


async def main():
    engine = PaperTradeEngine()
    result = await engine.run()
    return result


if __name__ == "__main__":
    asyncio.run(main())
