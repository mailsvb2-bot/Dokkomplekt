use crate::state::{AppState, OrderRecord, OrderStatus};
use crate::storage::{StoreError};
use axum::{extract::State, http::StatusCode, routing::post, Json, Router};
use serde::{Deserialize, Serialize};
use time::OffsetDateTime;
use uuid::Uuid;

#[derive(Debug, Deserialize)]
pub struct CreateOrderRequest {
    pub plan: String,
    pub amount_rub: u64,
    pub machine_hash: Option<String>,
}

#[derive(Debug, Serialize)]
pub struct CreateOrderResponse {
    pub order_id: Uuid,
    pub status: OrderStatus,
    pub provider: String,
    pub payment_url: String,
    pub qr_url: String,
}

pub fn router() -> Router<AppState> {
    Router::new().route("/api/orders", post(create_order))
}

async fn create_order(State(state): State<AppState>, Json(request): Json<CreateOrderRequest>) -> Result<Json<CreateOrderResponse>, StatusCode> {
    let plan = request.plan.trim();
    if plan.is_empty() || request.amount_rub == 0 {
        return Err(StatusCode::BAD_REQUEST);
    }
    if plan == "doctor_start" && request.amount_rub != 1490 {
        return Err(StatusCode::BAD_REQUEST);
    }
    if plan == "doctor_pro" && request.amount_rub != 3900 {
        return Err(StatusCode::BAD_REQUEST);
    }
    if plan == "department" && request.amount_rub != 14900 {
        return Err(StatusCode::BAD_REQUEST);
    }
    if plan == "clinic" && request.amount_rub != 49000 {
        return Err(StatusCode::BAD_REQUEST);
    }
    if plan == "enterprise" && request.amount_rub != 900000 {
        return Err(StatusCode::BAD_REQUEST);
    }
    if !matches!(plan, "doctor_start" | "doctor_pro" | "department" | "clinic" | "enterprise") {
        return Err(StatusCode::BAD_REQUEST);
    }
    let machine_hash = request.machine_hash.as_deref().map(str::trim).filter(|value| !value.is_empty()).map(str::to_string).ok_or(StatusCode::BAD_REQUEST)?;
    let order_id = Uuid::new_v4();
    let record = OrderRecord {
        id: order_id,
        plan: plan.to_string(),
        amount_rub: request.amount_rub,
        status: OrderStatus::WaitingPayment,
        machine_hash: Some(machine_hash),
        created_at: OffsetDateTime::now_utc(),
    };
    state.store.create_order_async(record.clone()).await.map_err(store_error_status)?;
    let provider = state.config.payment_provider.clone();
    let payment_url = payment_url_for(&state.config.public_base_url, &provider, order_id);
    let qr_url = qr_url_for(&state.config.public_base_url, &provider, order_id);
    Ok(Json(CreateOrderResponse { order_id, status: record.status, provider, payment_url, qr_url }))
}

fn store_error_status(error: StoreError) -> StatusCode {
    match error {
        StoreError::Conflict => StatusCode::CONFLICT,
        StoreError::Invalid(_) => StatusCode::BAD_REQUEST,
        StoreError::NotFound => StatusCode::NOT_FOUND,
        StoreError::Poisoned => StatusCode::INTERNAL_SERVER_ERROR,
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
}
