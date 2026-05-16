"""
Kelly criterion position sizer with regime scaling.
Uses Rust hot_paths.kelly_size for computation, falls back to Python.
"""


def _load_rust():
    try:
        from hot_paths import kelly_size as _rust_kelly
        return _rust_kelly
    except ImportError:
        return None


_rust_kelly = _load_rust()


def _python_kelly(win_prob: float, win_loss_ratio: float, max_fraction: float) -> float:
    if win_loss_ratio <= 0 or win_prob <= 0 or win_prob >= 1:
        return 0.0
    loss_prob = 1.0 - win_prob
    f = (win_prob * win_loss_ratio - loss_prob) / win_loss_ratio
    return max(0.0, min(f, max_fraction))


def kelly_size(win_prob: float, win_loss_ratio: float, max_fraction: float) -> float:
    if _rust_kelly:
        return _rust_kelly(win_prob, win_loss_ratio, max_fraction)
    return _python_kelly(win_prob, win_loss_ratio, max_fraction)


# Regime scale factors: reduce size in high-vol regimes
# Regime 0 = calm, 1 = normal, 2 = volatile
# Previous 0.3 for regime 2 was too aggressive (effective 15% of full Kelly)
REGIME_SCALE = {0: 1.0, 1: 0.80, 2: 0.55}


class KellyPositionSizer:
    def __init__(
        self,
        account_balance: float = 10_000.0,
        max_pct_per_trade: float = 0.025,  # 2.5% max
        half_kelly: bool = True,            # use half-Kelly for safety
    ) -> None:
        self._balance = account_balance
        self._max_pct = max_pct_per_trade
        self._half_kelly = half_kelly

    def update_balance(self, new_balance: float) -> None:
        self._balance = new_balance

    def compute(
        self,
        win_prob: float,
        risk_reward: float,
        regime: int = 1,
        liquidity_score: float = 1.0,
    ) -> dict:
        """Returns position sizing recommendation in USD and fraction of account."""
        max_fraction = self._max_pct
        raw_fraction = kelly_size(win_prob, risk_reward, max_fraction)

        if self._half_kelly:
            raw_fraction *= 0.5

        # Scale down by regime (more conservative in high-vol regimes)
        regime_scale = REGIME_SCALE.get(regime, 0.5)
        # Scale down by liquidity (smaller size in illiquid markets)
        liq_scale = min(1.0, max(0.1, liquidity_score))

        final_fraction = raw_fraction * regime_scale * liq_scale
        position_usd = self._balance * final_fraction

        return {
            "fraction": round(final_fraction, 5),
            "position_usd": round(position_usd, 2),
            "kelly_raw": round(raw_fraction, 5),
            "regime_scale": regime_scale,
            "liquidity_scale": round(liq_scale, 3),
        }
