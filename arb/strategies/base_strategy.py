"""
Base arbitrage strategy class for NautilusTrader.
All strategies inherit from this and implement generate_signal().
"""
from __future__ import annotations
from abc import abstractmethod
from dataclasses import dataclass, field
from nautilus_trader.trading.strategy import Strategy
from nautilus_trader.model.data import QuoteTick
from nautilus_trader.model.identifiers import InstrumentId
from arb.infra.redis_bus import publish
import asyncio
import time


@dataclass
class ArbitrageSignal:
    strategy: str
    symbol: str
    probability_score: float        # 0-1
    confidence_interval: tuple      # (low, high)
    risk_reward_ratio: float
    expected_value: float
    liquidity_score: float          # 0-1
    volatility_score: float
    slippage_estimate_bps: float
    correlation_impact: float
    execution_feasibility: float    # 0-1
    failure_probability: float
    regime: int                     # HMM state 0/1/2
    direction: str = "LONG"         # LONG or SHORT
    size_fraction: float = 0.0
    meta: dict = field(default_factory=dict)

    def is_tradeable(self) -> bool:
        return (
            self.probability_score > 0.55
            and self.expected_value > 0
            and self.liquidity_score > 0.3
            and self.execution_feasibility > 0.5
        )

    def to_dict(self) -> dict:
        return {
            "ts": int(time.time() * 1000),
            "strategy": self.strategy,
            "symbol": self.symbol,
            "probability_score": self.probability_score,
            "confidence_low": self.confidence_interval[0],
            "confidence_high": self.confidence_interval[1],
            "risk_reward": self.risk_reward_ratio,
            "expected_value": self.expected_value,
            "liquidity_score": self.liquidity_score,
            "volatility_score": self.volatility_score,
            "slippage_bps": self.slippage_estimate_bps,
            "regime": self.regime,
            "direction": self.direction,
            "size_fraction": self.size_fraction,
            "tradeable": self.is_tradeable(),
            **self.meta,
        }


class ArbitrageStrategy(Strategy):
    """
    Base class for all arbitrage strategies.
    Subclasses implement generate_signal() which is called on each tick.
    Signals are published to Redis arb:signals for downstream consumers.
    """

    def __init__(self, config=None) -> None:
        super().__init__(config)
        self._loop: asyncio.AbstractEventLoop | None = None
        self._current_regime: int = 1  # default: medium volatility

    def set_regime(self, regime: int) -> None:
        self._current_regime = regime

    @abstractmethod
    def generate_signal(self, tick: QuoteTick) -> ArbitrageSignal | None:
        ...

    def on_quote_tick(self, tick: QuoteTick) -> None:
        signal = self.generate_signal(tick)
        if signal:
            if self._loop:
                asyncio.run_coroutine_threadsafe(
                    publish("arb:signals", signal.to_dict()), self._loop
                )
            if signal.is_tradeable():
                self._log.info(
                    f"[{signal.strategy}] SIGNAL {signal.direction} {signal.symbol} "
                    f"EV={signal.expected_value:.4f} P={signal.probability_score:.2f}"
                )
