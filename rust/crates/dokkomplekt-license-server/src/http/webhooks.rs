use crate::state::AppState;
use crate::storage::{
    PaymentEventRecord, PaymentEventStatus, PaymentEventWriteOutcome, PaymentProvider, StoreError,
};
use axum::{extract::State, http::StatusCode, routing::post, Json, Router};
use serde::{Deserialize, Serialize};
use time::OffsetDateTime;
use uuid::Uuid;

#[derive(Debug, Deserialize)]
pub struct ProviderCallbackRequest {
    pub order_id: Uuid,
    pub provider_event_id: String,
    pub provider_payment_id: Option<String>,
    pub provider: Option<String>,
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
    let provider = normalize_callback_provider(event.provider.as_deref().unwrap_or("manual")).ok_or(StatusCode::BAD_REQUEST)?;
    if !matches!(&provider, PaymentProvider::Manual) {
        return Err(StatusCode::NOT_IMPLEMENTED);
    }
    let status = normalize_payment_status(&event.status).ok_or(StatusCode::BAD_REQUEST)?;
    let record = PaymentEventRecord {
        id: Uuid::new_v4(),
        order_id: event.order_id,
        provider,
        provider_event_id: event_id.to_string(),
        provider_payment_id: event.provider_payment_id,
        status,
        amount_rub: event.amount_rub,
        received_at: OffsetDateTime::now_utc(),
    };
    let outcome = state.store.record_payment_event_for_order_async(record).await.map_err(store_error_status)?;
    Ok(Json(ProviderCallbackResponse {
        accepted: true,
        duplicate: matches!(outcome, PaymentEventWriteOutcome::Duplicate),
        order_id: event.order_id,
    }))
}

fn store_error_status(error: StoreError) -> StatusCode {
    match error {
        StoreError::Conflict => StatusCode::CONFLICT,
        StoreError::Invalid(_) => StatusCode::BAD_REQUEST,
        StoreError::NotFound => StatusCode::NOT_FOUND,
        StoreError::Poisoned => StatusCode::INTERNAL_SERVER_ERROR,
    }
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

pub fn normalize_callback_provider(value: &str) -> Option<PaymentProvider> {
    match value.trim().to_ascii_lowercase().as_str() {
        "manual" => Some(PaymentProvider::Manual),
        "yookassa" => Some(PaymentProvider::YooKassa),
        "sbp" => Some(PaymentProvider::Sbp),
        "bank_invoice" => Some(PaymentProvider::BankInvoice),
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

    #[test]
    fn callback_provider_values_are_normalized() {
        assert!(matches!(normalize_callback_provider(" manual "), Some(PaymentProvider::Manual)));
        assert!(matches!(normalize_callback_provider("YooKassa"), Some(PaymentProvider::YooKassa)));
        assert!(matches!(normalize_callback_provider("SBP"), Some(PaymentProvider::Sbp)));
        assert!(matches!(normalize_callback_provider("bank_invoice"), Some(PaymentProvider::BankInvoice)));
    }

    #[test]
    fn unknown_callback_provider_is_rejected() {
        assert!(normalize_callback_provider("unknown-pay").is_none());
    }
}
