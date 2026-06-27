use crate::state::{ActivationRecord, AppState, OrderStatus};
use axum::{extract::{Path, State}, http::StatusCode, routing::{get, post}, Json, Router};
use dokkomplekt_license_core::{evaluate_machine_activation, PlanId};
use serde::{Deserialize, Serialize};
use time::OffsetDateTime;
use uuid::Uuid;

#[derive(Debug, Deserialize)]
pub struct ActivateMachineRequest {
    pub machine_hash: String,
}

#[derive(Debug, Serialize)]
pub struct ActivationResponse {
    pub activation_id: Uuid,
    pub order_id: Uuid,
    pub status: OrderStatus,
    pub message: String,
}

pub fn router() -> Router<AppState> {
    Router::new()
        .route("/api/orders/:order_id/status", get(order_status))
        .route("/api/orders/:order_id/activate-machine", post(activate_machine))
}

async fn order_status(State(state): State<AppState>, Path(order_id): Path<Uuid>) -> Result<Json<ActivationResponse>, StatusCode> {
    let store = state.store.read().map_err(|_| StatusCode::INTERNAL_SERVER_ERROR)?;
    let order = store.orders.get(&order_id).ok_or(StatusCode::NOT_FOUND)?;
    Ok(Json(ActivationResponse { activation_id: Uuid::nil(), order_id, status: order.status.clone(), message: "order status".to_string() }))
}

async fn activate_machine(
    State(state): State<AppState>,
    Path(order_id): Path<Uuid>,
    Json(request): Json<ActivateMachineRequest>,
) -> Result<Json<ActivationResponse>, StatusCode> {
    let machine_hash = request.machine_hash.trim();
    if machine_hash.is_empty() {
        return Err(StatusCode::BAD_REQUEST);
    }
    let mut store = state.store.write().map_err(|_| StatusCode::INTERNAL_SERVER_ERROR)?;
    let order = store.orders.get(&order_id).ok_or(StatusCode::NOT_FOUND)?.clone();
    if !matches!(order.status, OrderStatus::Paid | OrderStatus::LicenseIssued) {
        return Err(StatusCode::CONFLICT);
    }
    let plan = parse_plan(&order.plan).ok_or(StatusCode::BAD_REQUEST)?;
    let active_count = store
        .activations
        .values()
        .filter(|activation| activation.order_id == order_id)
        .count() as u32;
    let decision = evaluate_machine_activation(&plan, active_count, 1);
    if !decision.allowed {
        return Err(StatusCode::CONFLICT);
    }
    let activation_id = Uuid::new_v4();
    store.activations.insert(activation_id, ActivationRecord {
        id: activation_id,
        order_id,
        machine_hash: machine_hash.to_string(),
        created_at: OffsetDateTime::now_utc(),
    });
    Ok(Json(ActivationResponse { activation_id, order_id, status: order.status, message: decision.code.to_string() }))
}

fn parse_plan(value: &str) -> Option<PlanId> {
    match value.trim().to_ascii_lowercase().as_str() {
        "trial" => Some(PlanId::Trial),
        "doctor_start" => Some(PlanId::DoctorStart),
        "doctor_pro" => Some(PlanId::DoctorPro),
        "department" => Some(PlanId::Department),
        "clinic" => Some(PlanId::Clinic),
        "enterprise" => Some(PlanId::Enterprise),
        _ => None,
    }
}
