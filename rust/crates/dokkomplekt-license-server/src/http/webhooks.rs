use crate::state::{AppState, OrderStatus};
use axum::{extract::State, http::StatusCode, routing::post, Json, Router};
use serde::{Deserialize, Serialize};
use uuid::Uuid;

#[derive(Debug, Deserialize)]
pub struct ProviderCallbackRequest {
    pub order_id: Uuid,
    pub provider_event_id: String,
    pub status: String,
    pub amount_rub: u64,
}

#[derive(Debug, Serialize)]
pub struct ProviderCallbackResponse {
    pub accepted: bool,
    pub order_id: Uuid,
}

pub fn router() -> Router<AppState> {
    Router::new().route("/api/provider/callback", post(provider_callback))
}

async fn provider_callback(State(state): State<AppState>, Json(event): Json<ProviderCallbackRequest>) -> Result<Json<ProviderCallbackResponse>, StatusCode> {
    if event.provider_event_id.trim().is_empty() {
        return Err(StatusCode::BAD_REQUEST);
    }
    let mut store = state.store.write().map_err(|_| StatusCode::INTERNAL_SERVER_ERROR)?;
    let order = store.orders.get_mut(&event.order_id).ok_or(StatusCode::NOT_FOUND)?;
    if order.amount_rub != event.amount_rub {
        return Err(StatusCode::BAD_REQUEST);
    }
    if event.status == "succeeded" {
        order.status = OrderStatus::Paid;
    }
    Ok(Json(ProviderCallbackResponse { accepted: true, order_id: event.order_id }))
}
