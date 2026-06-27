use dokkomplekt_license_core::LicenseDocument;
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;

#[pyfunction]
fn native_core_version() -> String {
    "0.1.0".to_string()
}

#[pyfunction]
fn license_plan(license_json: &str) -> PyResult<String> {
    let document: LicenseDocument = serde_json::from_str(license_json)
        .map_err(|err| PyValueError::new_err(err.to_string()))?;
    Ok(format!("{:?}", document.license.payload.plan))
}

#[pymodule]
fn dokkomplekt_license_native(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(native_core_version, module)?)?;
    module.add_function(wrap_pyfunction!(license_plan, module)?)?;
    Ok(())
}
