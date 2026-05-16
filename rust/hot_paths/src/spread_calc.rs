use pyo3::prelude::*;

/// Compute mid-price from bid and ask.
#[pyfunction]
pub fn mid_price(bid: f64, ask: f64) -> f64 {
    (bid + ask) * 0.5
}

/// Spread in basis points: (ask - bid) / mid * 10_000
#[pyfunction]
pub fn spread_bps(bid: f64, ask: f64) -> f64 {
    if bid <= 0.0 || ask <= 0.0 {
        return 0.0;
    }
    let mid = (bid + ask) * 0.5;
    (ask - bid) / mid * 10_000.0
}

/// Vectorized mid-price for a batch of (bid, ask) pairs.
/// Returns a Vec<f64> of mid prices.
#[pyfunction]
pub fn batch_mid(bids: Vec<f64>, asks: Vec<f64>) -> PyResult<Vec<f64>> {
    if bids.len() != asks.len() {
        return Err(pyo3::exceptions::PyValueError::new_err(
            "bids and asks must have the same length",
        ));
    }
    Ok(bids.iter().zip(asks.iter()).map(|(b, a)| (b + a) * 0.5).collect())
}
