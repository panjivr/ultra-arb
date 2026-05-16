"""
Kalman filter spread tracker using Rust hot_paths.kalman_update for performance.
Falls back to pure Python if Rust extension not compiled yet.
"""


def _load_rust():
    try:
        from hot_paths import kalman_update as _rust_update
        return _rust_update
    except ImportError:
        return None


_rust_kalman = _load_rust()


def _python_kalman(x: float, p: float, z: float, q: float, r: float) -> tuple[float, float]:
    x_pred = x
    p_pred = p + q
    k = p_pred / (p_pred + r)
    x_post = x_pred + k * (z - x_pred)
    p_post = (1.0 - k) * p_pred
    return x_post, p_post


def kalman_update(x: float, p: float, z: float, q: float, r: float) -> tuple[float, float]:
    if _rust_kalman:
        return _rust_kalman(x, p, z, q, r)
    return _python_kalman(x, p, z, q, r)


class KalmanSpreadTracker:
    """
    Tracks the mid-price of a spread between two instruments using a Kalman filter.
    Outputs a smoothed estimate and covariance — useful for z-score calculation.
    """

    def __init__(self, q: float = 1e-4, r: float = 1e-2) -> None:
        self._x = 0.0
        self._p = 1.0
        self._q = q  # process noise (how fast the "true" spread can drift)
        self._r = r  # measurement noise (how noisy the observed spread is)
        self._initialized = False

    def update(self, observed_spread: float) -> tuple[float, float]:
        """Returns (smoothed_spread, uncertainty_estimate)."""
        if not self._initialized:
            self._x = observed_spread
            self._initialized = True
            return self._x, self._p

        self._x, self._p = kalman_update(self._x, self._p, observed_spread, self._q, self._r)
        return self._x, self._p

    @property
    def state(self) -> float:
        return self._x

    @property
    def covariance(self) -> float:
        return self._p
