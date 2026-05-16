"""
Cointegration scanner using Johansen test.
Finds hedge ratios and z-scores for BTC-ETH spread mean reversion.
"""
import numpy as np
from statsmodels.tsa.vector_ar.vecm import coint_johansen
from statsmodels.tsa.stattools import adfuller
from sqlalchemy import text
from arb.infra.db import engine


class CointegrationScanner:
    def __init__(self) -> None:
        self._hedge_ratio: float = 1.0
        self._spread_mean: float = 0.0
        self._spread_std: float = 1.0
        self._is_cointegrated: bool = False

    async def scan(self, symbol_a: str = "BTC/USDT:USDT", symbol_b: str = "ETH/USDT:USDT") -> dict:
        async with engine.begin() as conn:
            rows_a = await conn.execute(
                text("SELECT mid FROM ticks WHERE symbol=:sym ORDER BY time DESC LIMIT 300"),
                {"sym": symbol_a},
            )
            rows_b = await conn.execute(
                text("SELECT mid FROM ticks WHERE symbol=:sym ORDER BY time DESC LIMIT 300"),
                {"sym": symbol_b},
            )
            prices_a = np.array([r[0] for r in rows_a.fetchall()])[::-1]
            prices_b = np.array([r[0] for r in rows_b.fetchall()])[::-1]

        n = min(len(prices_a), len(prices_b))
        if n < 50:
            return {"cointegrated": False, "hedge_ratio": 1.0, "z_score": 0.0}

        prices_a = prices_a[:n]
        prices_b = prices_b[:n]

        try:
            result = coint_johansen(np.column_stack([prices_a, prices_b]), det_order=0, k_ar_diff=1)
            # Use first eigenvector as hedge ratio
            ev = result.evec[:, 0]
            hedge = -ev[1] / ev[0] if ev[0] != 0 else 1.0
            self._hedge_ratio = hedge

            spread = prices_a - hedge * prices_b
            self._spread_mean = float(np.mean(spread))
            self._spread_std = float(np.std(spread)) or 1.0

            # Check stationarity of spread
            adf = adfuller(spread, maxlag=1)
            self._is_cointegrated = adf[1] < 0.05  # p-value < 5%

            z_score = (spread[-1] - self._spread_mean) / self._spread_std
            return {
                "cointegrated": self._is_cointegrated,
                "hedge_ratio": round(self._hedge_ratio, 4),
                "z_score": round(float(z_score), 3),
                "spread_mean": round(self._spread_mean, 2),
                "spread_std": round(self._spread_std, 2),
                "adf_pvalue": round(float(adf[1]), 4),
            }
        except Exception as e:
            return {"cointegrated": False, "error": str(e)}

    def current_z_score(self, price_a: float, price_b: float) -> float:
        spread = price_a - self._hedge_ratio * price_b
        return (spread - self._spread_mean) / self._spread_std
