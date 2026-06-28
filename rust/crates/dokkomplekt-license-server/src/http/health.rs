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
    database_connected: bool,
}

pub fn router() -> Router<AppState> {
    Router::new().route("/healthz", get(healthz))
}

async fn healthz(State(state): State<AppState>) -> Json<HealthResponse> {
    let database_configured = state.config.database_url.as_deref().map(str::trim).is_some_and(|value| !value.is_empty());
    let database_connected = state.store.database_ready_async().await;
    Json(HealthResponse {
        status: "ok",
        service: "dokkomplekt-license-server",
        storage_mode: state.config.storage_mode.clone(),
        storage_backend: state.store.backend_name(),
        database_configured,
        database_connected,
    })
}
