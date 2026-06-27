use pyo3::prelude::*;

#[pyfunction]
fn native_core_version() -> String {
    "0.1.0".to_string()
}

#[pymodule]
fn dokkomplekt_license_native(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(native_core_version, module)?)?;
    Ok(())
}
