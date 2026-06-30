use crate::state::{AppState, OrderRecord, OrderStatus};
use crate::storage::StoreError;
use axum::{extract::State, http::StatusCode, routing::post, Json, Router};
use serde::{Deserialize, Serialize};
use time::OffsetDateTime;
use uuid::Uuid;

#[derive(Debug, Deserialize)]
pub struct CreateOrderRequest {
    pub plan: String,
    /// Optional client echo kept for backward-compatible clients. The server is
    /// the source of truth and rejects a request when this value does not match
    /// the configured tariff table.
    pub amount_rub: Option<u64>,
    pub machine_hash: Option<String>,
}

#[derive(Debug, Serialize)]
pub struct CreateOrderResponse {
    pub order_id: Uuid,
    pub status: OrderStatus,
    pub provider: String,
    pub amount_rub: u64,
    pub payment_url: String,
    pub qr_url: String,
}

pub fn router() -> Router<AppState> {
    Router::new().route("/api/orders", post(create_order))
}

async fn create_order(State(state): State<AppState>, Json(request): Json<CreateOrderRequest>) -> Result<Json<CreateOrderResponse>, StatusCode> {
    let plan = normalize_order_plan(&request.plan).ok_or(StatusCode::BAD_REQUEST)?;
    let amount_rub = tariff_amount_rub(plan).ok_or(StatusCode::BAD_REQUEST)?;
    if matches!(request.amount_rub, Some(client_amount) if client_amount != amount_rub) {
        return Err(StatusCode::BAD_REQUEST);
    }
    let machine_hash = request.machine_hash.map(|value| value.trim().to_string()).filter(|value| !value.is_empty());
    let order_id = Uuid::new_v4();
    let record = OrderRecord {
        id: order_id,
        plan: plan.to_string(),
        amount_rub,
        status: OrderStatus::WaitingPayment,
        machine_hash,
        created_at: OffsetDateTime::now_utc(),
    };
    state.store.create_order_async(record.clone()).await.map_err(store_error_status)?;
    let provider = state.config.payment_provider.clone();
    let payment_url = payment_url_for(&state.config.public_base_url, &provider, order_id);
    let qr_url = qr_url_for(&state.config.public_base_url, &provider, order_id);
    Ok(Json(CreateOrderResponse { order_id, status: record.status, provider, amount_rub, payment_url, qr_url }))
}

fn store_error_status(error: StoreError) -> StatusCode {
    match error {
        StoreError::Conflict => StatusCode::CONFLICT,
        StoreError::Invalid(_) => StatusCode::BAD_REQUEST,
        StoreError::NotFound => StatusCode::NOT_FOUND,
        StoreError::Poisoned => StatusCode::INTERNAL_SERVER_ERROR,
    }
}

pub fn normalize_order_plan(value: &str) -> Option<&'static str> {
    match value.trim().to_ascii_lowercase().as_str() {
        "doctor_start" => Some("doctor_start"),
        "doctor_pro" => Some("doctor_pro"),
        "department" => Some("department"),
        "clinic" => Some("clinic"),
        "enterprise" => Some("enterprise"),
        // Trial is local-only in the desktop app and must not be sold as a paid order.
        "trial" => None,
        _ => None,
    }
}

pub fn tariff_amount_rub(plan: &str) -> Option<u64> {
    match plan {
        "doctor_start" => Some(1_490),
        "doctor_pro" => Some(3_900),
        "department" => Some(14_900),
        "clinic" => Some(49_000),
        "enterprise" => Some(900_000),
        _ => None,
    }
}

pub fn payment_url_for(base_url: &str, provider: &str, order_id: Uuid) -> String {
    format!("{}/pay/{}/{}", base_url.trim_end_matches('/'), provider, order_id)
}

pub fn qr_url_for(base_url: &str, provider: &str, order_id: Uuid) -> String {
    match provider {
        "sbp" => format!("{}/api/orders/{}/qr", base_url.trim_end_matches('/'), order_id),
        _ => "".to_string(),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn yookassa_payment_url_uses_provider_namespace() {
        let order_id = Uuid::nil();
        assert_eq!(
            payment_url_for("https://lic.example/", "yookassa", order_id),
            "https://lic.example/pay/yookassa/00000000-0000-0000-0000-000000000000",
        );
    }

    #[test]
    fn sbp_gets_qr_url_and_manual_does_not() {
        let order_id = Uuid::nil();
        assert_eq!(
            qr_url_for("https://lic.example", "sbp", order_id),
            "https://lic.example/api/orders/00000000-0000-0000-0000-000000000000/qr",
        );
        assert_eq!(qr_url_for("https://lic.example", "manual", order_id), "");
    }

    #[test]
    fn order_tariffs_are_server_side_only() {
        assert_eq!(normalize_order_plan(" Doctor_Pro "), Some("doctor_pro"));
        assert_eq!(tariff_amount_rub("doctor_pro"), Some(3_900));
        assert_eq!(tariff_amount_rub("clinic"), Some(49_000));
        assert!(normalize_order_plan("trial").is_none());
        assert!(normalize_order_plan("unknown").is_none());
    }
}
