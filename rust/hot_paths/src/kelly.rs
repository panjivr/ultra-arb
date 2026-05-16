use pyo3::prelude::*;

/// Kelly criterion fractional position size.
///
/// f = (win_prob * win_loss_ratio - loss_prob) / win_loss_ratio
///
/// Clamped to [0, max_fraction]. Returns 0 if edge is negative.
#[pyfunction]
pub fn kelly_size(win_prob: f64, win_loss_ratio: f64, max_fraction: f64) -> f64 {
    if win_loss_ratio <= 0.0 || win_prob <= 0.0 || win_prob >= 1.0 {
        return 0.0;
    }
    let loss_prob = 1.0 - win_prob;
    let f = (win_prob * win_loss_ratio - loss_prob) / win_loss_ratio;
    f.max(0.0).min(max_fraction)
}
