"""
Bayesian Beta-Binomial model for win rate estimation.
Updates every 100 trades to refine probability estimates per strategy.
"""
import numpy as np
from sqlalchemy import text
from arb.infra.db import engine


class BayesianWinRateEstimator:
    """
    Beta-Binomial conjugate model.
    Prior: Beta(alpha=2, beta=2) — weakly informative, centered at 0.5
    Posterior updates with observed wins/losses per strategy.
    """

    def __init__(self, prior_alpha: float = 2.0, prior_beta: float = 2.0) -> None:
        self._priors: dict[str, tuple[float, float]] = {}
        self._default_alpha = prior_alpha
        self._default_beta = prior_beta

    def _get_prior(self, strategy: str) -> tuple[float, float]:
        return self._priors.get(strategy, (self._default_alpha, self._default_beta))

    def update(self, strategy: str, wins: int, losses: int) -> dict:
        alpha, beta_ = self._get_prior(strategy)
        alpha_post = alpha + wins
        beta_post = beta_ + losses
        self._priors[strategy] = (alpha_post, beta_post)

        mean = alpha_post / (alpha_post + beta_post)
        var = (alpha_post * beta_post) / ((alpha_post + beta_post) ** 2 * (alpha_post + beta_post + 1))
        ci_low = max(0.0, mean - 1.96 * np.sqrt(var))
        ci_high = min(1.0, mean + 1.96 * np.sqrt(var))

        return {
            "strategy": strategy,
            "win_rate_mean": round(mean, 4),
            "ci_95": (round(ci_low, 4), round(ci_high, 4)),
            "alpha": alpha_post,
            "beta": beta_post,
            "n_trades": wins + losses,
        }

    async def refresh_from_db(self) -> None:
        async with engine.begin() as conn:
            rows = await conn.execute(
                text(
                    "SELECT strategy, "
                    "SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) AS wins, "
                    "SUM(CASE WHEN pnl <= 0 THEN 1 ELSE 0 END) AS losses "
                    "FROM trades WHERE strategy IS NOT NULL "
                    "GROUP BY strategy"
                )
            )
            for row in rows.fetchall():
                strategy, wins, losses = row
                self.update(strategy, int(wins or 0), int(losses or 0))

    def win_rate(self, strategy: str) -> float:
        alpha, beta_ = self._get_prior(strategy)
        return alpha / (alpha + beta_)

    def confidence_interval(self, strategy: str) -> tuple[float, float]:
        alpha, beta_ = self._get_prior(strategy)
        mean = alpha / (alpha + beta_)
        n = alpha + beta_
        std = np.sqrt(mean * (1 - mean) / n)
        return (max(0.0, mean - 1.96 * std), min(1.0, mean + 1.96 * std))
