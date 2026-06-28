use crate::state::{AppState, OrderStatus};
use crate::storage::{PaymentEventRecord, PaymentEventStatus, PaymentProvider};
use axum::{extract::State, http::StatusCode, routing::post, Json, Router};
use serde::{Deserialize, Serialize};
use time::OffsetDateTime;
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
    pub duplicate: bool,
    pub order_id: Uuid,
}

pub fn router() -> Router<AppState> {
    Router::new().route("/api/provider/callback", post(provider_callback))
}

async fn provider_callback(State(state): State<AppState>, Json(event): Json<ProviderCallbackRequest>) -> Result<Json<ProviderCallbackResponse>, StatusCode> {
    let event_id = event.provider_event_id.trim();
    if event_id.is_empty() || event.amount_rub == 0 {
        return Err(StatusCode::BAD_REQUEST);
    }
    let mut store = state.store.write().map_err(|_| StatusCode::INTERNAL_SERVER_ERROR)?;
    if store.payment_events.values().any(|record| record.provider_event_id == event_id) {
        return Ok(Json(ProviderCallbackResponse { accepted: true, duplicate: true, order_id: event.order_id }));
    }
    let order = store.orders.get_mut(&event.order_id).ok_or(StatusCode::NOT_FOUND)?;
    if order.amount_rub != event.amount_rub {
        return Err(StatusCode::BAD_REQUEST);
    }
    let status = normalize_payment_status(&event.status).ok_or(StatusCode::BAD_REQUEST)?;
    if matches!(status, PaymentEventStatus::Succeeded) {
        order.status = OrderStatus::Paid;
    }
    let record_id = Uuid::new_v4();
    store.payment_events.insert(record_id, PaymentEventRecord {
        id: record_id,
        order_id: event.order_id,
        provider: PaymentProvider::Manual,
        provider_event_id: event_id.to_string(),
        provider_payment_id: None,
        status,
        amount_rub: event.amount_rub,
        received_at: OffsetDateTime::now_utc(),
    });
    Ok(Json(ProviderCallbackResponse { accepted: true, duplicate: false, order_id: event.order_id }))
}

pub fn normalize_payment_status(value: &str) -> Option<PaymentEventStatus> {
    match value.trim().to_ascii_lowercase().as_str() {
        "succeeded" => Some(PaymentEventStatus::Succeeded),
        "pending" => Some(PaymentEventStatus::Pending),
        "cancelled" | "canceled" => Some(PaymentEventStatus::Cancelled),
        "rejected" => Some(PaymentEventStatus::Rejected),
        _ => None,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn payment_status_values_are_normalized() {
        assert!(matches!(normalize_payment_status("succeeded"), Some(PaymentEventStatus::Succeeded)));
        assert!(matches!(normalize_payment_status(" pending "), Some(PaymentEventStatus::Pending)));
        assert!(matches!(normalize_payment_status("canceled"), Some(PaymentEventStatus::Cancelled)));
        assert!(matches!(normalize_payment_status("cancelled"), Some(PaymentEventStatus::Cancelled)));
        assert!(matches!(normalize_payment_status("rejected"), Some(PaymentEventStatus::Rejected)));
    }

    #[test]
    fn unknown_payment_status_is_rejected() {
        assert!(normalize_payment_status("unexpected-state").is_none());
    }
}
