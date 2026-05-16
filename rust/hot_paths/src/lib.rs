use pyo3::prelude::*;

mod spread_calc;
mod kelly;
mod kalman;

#[pymodule]
fn hot_paths(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(spread_calc::mid_price, m)?)?;
    m.add_function(wrap_pyfunction!(spread_calc::spread_bps, m)?)?;
    m.add_function(wrap_pyfunction!(spread_calc::batch_mid, m)?)?;
    m.add_function(wrap_pyfunction!(kelly::kelly_size, m)?)?;
    m.add_function(wrap_pyfunction!(kalman::kalman_update, m)?)?;
    Ok(())
}
