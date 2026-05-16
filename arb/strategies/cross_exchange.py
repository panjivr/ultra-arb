"""
Cross-exchange spread arbitrage: Binance vs Bybit BTC perpetuals.
Detects spread anomalies and signals when spread > fee threshold.
"""
from collections import deque
from nautilus_trader.model.data import QuoteTick
from nautilus_trader.model.identifiers import InstrumentId
from arb.strategies.base_strategy import ArbitrageStrategy, ArbitrageSignal

MAKER_FEE_BPS = 2.0   # 0.02% per side
TAKER_FEE_BPS = 5.0   # 0.05% per side
TOTAL_ROUNDTRIP_BPS = (MAKER_FEE_BPS + TAKER_FEE_BPS) * 2
MIN_EDGE_BPS = TOTAL_ROUNDTRIP_BPS + 2.0   # minimum edge above fees

WINDOW = 100  # rolling window for spread statistics


def _edge_to_prob(net_edge_bps: float) -> float:
    """Convert net edge (bps) to realistic win probability.

    Accounts for execution risk: latency, slippage, partial fills.
    Even a 50 bps edge can fail if execution takes 500ms.
    """
    if net_edge_bps < 2:
        return 0.52
    if net_edge_bps < 5:
        return 0.57
    if net_edge_bps < 10:
        return 0.62
    if net_edge_bps < 20:
        return 0.68
    if net_edge_bps < 50:
        return 0.74
    return 0.80  # large spreads still carry meaningful execution risk


class CrossExchangeStrategy(ArbitrageStrategy):
    """
    Monitors bid/ask on Binance and Bybit for the same symbol.
    Signals when: Binance ask < Bybit bid - fees (buy Binance, sell Bybit)
    or vice versa.
    """

    def __init__(self, symbol: str = "BTC/USDT:USDT") -> None:
        super().__init__()
        self._symbol = symbol
        self._binance_bid: float = 0.0
        self._binance_ask: float = 0.0
        self._bybit_bid: float = 0.0
        self._bybit_ask: float = 0.0
        self._spread_history: deque[float] = deque(maxlen=WINDOW)

    def generate_signal(self, tick: QuoteTick) -> ArbitrageSignal | None:
        exchange = tick.instrument_id.venue.value
        bid = float(tick.bid_price)
        ask = float(tick.ask_price)

        if exchange == "BINANCE":
            self._binance_bid = bid
            self._binance_ask = ask
        elif exchange == "BYBIT":
            self._bybit_bid = bid
            self._bybit_ask = ask
        else:
            return None

        if not all([self._binance_bid, self._binance_ask, self._bybit_bid, self._bybit_ask]):
            return None

        # Buy Binance ask, sell Bybit bid
        spread_buy_binance = (self._bybit_bid - self._binance_ask) / self._binance_ask * 10_000
        # Buy Bybit ask, sell Binance bid
        spread_buy_bybit = (self._binance_bid - self._bybit_ask) / self._bybit_ask * 10_000

        best_spread = max(spread_buy_binance, spread_buy_bybit)
        direction = "LONG_BINANCE" if spread_buy_binance > spread_buy_bybit else "LONG_BYBIT"
        self._spread_history.append(best_spread)

        if best_spread < MIN_EDGE_BPS:
            return None

        net_edge = best_spread - TOTAL_ROUNDTRIP_BPS
        # Conservative probability: execution risk grows with spread (slippage, latency)
        # Never assume >80% win rate even on large spreads
        prob = _edge_to_prob(net_edge)

        return ArbitrageSignal(
            strategy="CrossExchange",
            symbol=self._symbol,
            probability_score=prob,
            confidence_interval=(prob - 0.05, min(1.0, prob + 0.05)),
            risk_reward_ratio=net_edge / TOTAL_ROUNDTRIP_BPS,
            expected_value=net_edge,
            liquidity_score=0.9,
            volatility_score=self._vol_score(),
            slippage_estimate_bps=TAKER_FEE_BPS,
            correlation_impact=0.95,
            execution_feasibility=0.85,
            failure_probability=1 - prob,
            regime=self._current_regime,
            direction=direction,
            meta={"spread_bps": round(best_spread, 3), "net_edge_bps": round(net_edge, 3)},
        )

    def _vol_score(self) -> float:
        if len(self._spread_history) < 10:
            return 0.5
        import statistics
        std = statistics.stdev(self._spread_history)
        return max(0.0, min(1.0, 1.0 - std / 20.0))
