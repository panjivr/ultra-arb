use pyo3::prelude::*;

/// One-dimensional Kalman filter update step.
///
/// Parameters:
///   x  - prior state estimate
///   p  - prior estimate covariance
///   z  - measurement (observation)
///   q  - process noise covariance
///   r  - measurement noise covariance
///
/// Returns (x_post, p_post): posterior state and covariance.
#[pyfunction]
pub fn kalman_update(x: f64, p: f64, z: f64, q: f64, r: f64) -> (f64, f64) {
    // Predict
    let x_pred = x;
    let p_pred = p + q;

    // Update
    let k = p_pred / (p_pred + r);  // Kalman gain
    let x_post = x_pred + k * (z - x_pred);
    let p_post = (1.0 - k) * p_pred;

    (x_post, p_post)
}
