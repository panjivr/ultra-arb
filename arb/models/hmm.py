"""
Hidden Markov Model for market regime detection.
3 states: 0=low volatility, 1=medium volatility, 2=high volatility.
Refits every 15 minutes on last 500 returns from TimescaleDB.
"""
import numpy as np
from hmmlearn.hmm import GaussianHMM
from sqlalchemy import text
from arb.infra.db import engine
import asyncio


class RegimeDetector:
    def __init__(self, n_states: int = 3, symbol: str = "BTC/USDT:USDT") -> None:
        self._n = n_states
        self._symbol = symbol
        self._model = GaussianHMM(
            n_components=n_states,
            covariance_type="full",
            n_iter=100,
            random_state=42,
        )
        self._fitted = False
        self._current_regime = 1
        self._regime_labels: dict[int, int] = {}  # HMM state → volatility rank

    def fit_synthetic(self, n: int = 500) -> None:
        rng = np.random.default_rng(42)
        # Three regime segments
        low = rng.normal(0, 0.003, n // 3)
        med = rng.normal(0, 0.010, n // 3)
        high = rng.normal(0, 0.025, n // 3)
        returns = np.concatenate([low, med, high]).reshape(-1, 1)
        self._fit(returns)

    async def fit_from_db(self) -> None:
        async with engine.begin() as conn:
            rows = await conn.execute(
                text(
                    "SELECT mid FROM ticks WHERE symbol=:sym ORDER BY time DESC LIMIT 500"
                ),
                {"sym": self._symbol},
            )
            prices = [r[0] for r in rows.fetchall()]

        if len(prices) < 50:
            self.fit_synthetic()
            return

        prices = np.array(prices[::-1])
        returns = np.diff(np.log(prices)).reshape(-1, 1)
        self._fit(returns)

    def _fit(self, returns: np.ndarray) -> None:
        self._model.fit(returns)
        self._fitted = True
        # Label states by volatility (std of each state)
        stds = {i: np.sqrt(self._model.covars_[i][0][0]) for i in range(self._n)}
        ranked = sorted(stds, key=stds.get)
        self._regime_labels = {ranked[i]: i for i in range(self._n)}
        self._update_current(returns)

    def _update_current(self, returns: np.ndarray) -> None:
        if not self._fitted or len(returns) == 0:
            return
        hidden = self._model.predict(returns)
        raw = int(hidden[-1])
        self._current_regime = self._regime_labels.get(raw, 1)

    def current_regime(self) -> int:
        return self._current_regime

    async def update(self) -> int:
        await self.fit_from_db()
        return self._current_regime
