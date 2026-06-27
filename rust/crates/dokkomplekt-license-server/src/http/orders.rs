use crate::state::{AppState, OrderRecord, OrderStatus};
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
    pub payment_url: String,
    pub qr_url: String,
}

pub fn router() -> Router<AppState> {
    Router::new().route("/api/orders", post(create_order))
}

async fn create_order(State(state): State<AppState>, Json(request): Json<CreateOrderRequest>) -> Result<Json<CreateOrderResponse>, StatusCode> {
    if request.plan.trim().is_empty() || request.amount_rub == 0 {
        return Err(StatusCode::BAD_REQUEST);
    }
    let order_id = Uuid::new_v4();
    let record = OrderRecord {
        id: order_id,
        plan: request.plan.trim().to_string(),
        amount_rub: request.amount_rub,
        status: OrderStatus::WaitingPayment,
        machine_hash: request.machine_hash,
        created_at: OffsetDateTime::now_utc(),
    };
    state.store.write().map_err(|_| StatusCode::INTERNAL_SERVER_ERROR)?.orders.insert(order_id, record.clone());
    let payment_url = format!("{}/pay/{}", state.config.public_base_url, order_id);
    let qr_url = format!("{}/api/orders/{}/qr", state.config.public_base_url, order_id);
    Ok(Json(CreateOrderResponse { order_id, status: record.status, payment_url, qr_url }))
}
