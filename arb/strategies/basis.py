"""
Spot-perpetual basis arbitrage.
Exploits the price difference between spot BTC and BTC perpetual futures.
When basis > funding rate cost, the trade is profitable.
"""
import time
from collections import deque
from nautilus_trader.model.data import QuoteTick
from arb.strategies.base_strategy import ArbitrageStrategy, ArbitrageSignal

ANNUAL_CARRY_THRESHOLD = 0.10  # 10% annualized minimum basis to trade
FUNDING_PERIODS_PER_YEAR = 3 * 365


class BasisStrategy(ArbitrageStrategy):
    """
    Monitors spot vs perp prices. When perp > spot by more than funding costs,
    signals: buy spot, short perp (cash-and-carry).
    """

    def __init__(self) -> None:
        super().__init__()
        self._spot_mid: float = 0.0
        self._perp_mid: float = 0.0
        self._basis_history: deque[float] = deque(maxlen=50)

    def generate_signal(self, tick: QuoteTick) -> ArbitrageSignal | None:
        symbol = tick.instrument_id.symbol.value
        mid = (float(tick.bid_price) + float(tick.ask_price)) / 2

        if "SPOT" in symbol or "BTC-USD" in symbol:
            self._spot_mid = mid
        elif "PERP" in symbol or ":USDT" in symbol:
            self._perp_mid = mid

        if self._spot_mid <= 0 or self._perp_mid <= 0:
            return None

        basis_pct = (self._perp_mid - self._spot_mid) / self._spot_mid
        annualized = basis_pct * FUNDING_PERIODS_PER_YEAR
        self._basis_history.append(basis_pct)

        if annualized < ANNUAL_CARRY_THRESHOLD:
            return None

        prob = min(0.88, 0.6 + annualized * 0.5)
        return ArbitrageSignal(
            strategy="Basis",
            symbol="BTC",
            probability_score=prob,
            confidence_interval=(prob - 0.08, min(1.0, prob + 0.05)),
            risk_reward_ratio=annualized / 0.05,
            expected_value=annualized,
            liquidity_score=0.85,
            volatility_score=0.7,
            slippage_estimate_bps=5.0,
            correlation_impact=1.0,
            execution_feasibility=0.75,
            failure_probability=1 - prob,
            regime=self._current_regime,
            direction="LONG_SPOT_SHORT_PERP",
            meta={"basis_pct": round(basis_pct, 6), "annualized_yield": round(annualized, 4)},
        )
