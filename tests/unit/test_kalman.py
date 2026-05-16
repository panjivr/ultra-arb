"""Unit tests for Kalman filter."""
from arb.models.kalman_filter import KalmanSpreadTracker, kalman_update


def test_kalman_update_converges():
    x, p = 0.0, 1.0
    for _ in range(100):
        x, p = kalman_update(x, p, 1.0, 1e-4, 1e-2)
    assert abs(x - 1.0) < 0.01  # should converge to observed value


def test_kalman_tracker():
    tracker = KalmanSpreadTracker()
    for obs in [100.0, 100.5, 99.8, 100.2, 100.1]:
        state, cov = tracker.update(obs)
    assert abs(state - 100.0) < 2.0  # smoothed, close to mean
    assert cov < 1.0                 # uncertainty shrinks


def test_kalman_tracker_initialized():
    tracker = KalmanSpreadTracker()
    state, cov = tracker.update(50.0)
    assert state == 50.0  # first update initializes to observed value
