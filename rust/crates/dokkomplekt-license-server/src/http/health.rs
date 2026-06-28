use crate::state::AppState;
use axum::{extract::State, routing::get, Json, Router};
use serde::Serialize;

#[derive(Debug, Serialize)]
struct HealthResponse {
    status: &'static str,
    service: &'static str,
    storage_mode: String,
    storage_backend: &'static str,
    database_configured: bool,
}

pub fn router() -> Router<AppState> {
    Router::new().route("/healthz", get(healthz))
}

async fn healthz(State(state): State<AppState>) -> Json<HealthResponse> {
    Json(HealthResponse {
        status: "ok",
        service: "dokkomplekt-license-server",
        storage_mode: state.config.storage_mode.clone(),
        storage_backend: state.store.backend_name(),
        database_configured: state.config.database_url.is_some(),
    })
}
