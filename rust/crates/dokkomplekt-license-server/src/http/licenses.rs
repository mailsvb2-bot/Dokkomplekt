use crate::issuer::{issue_license, IssueLicenseInput};
use crate::state::{AppState, OrderStatus};
use axum::{extract::{Path, State}, http::StatusCode, routing::post, Json, Router};
use dokkomplekt_license_core::models::PlanId;
use serde::Deserialize;
use uuid::Uuid;

#[derive(Debug, Deserialize)]
pub struct IssueRequest {
    pub owner_name: Option<String>,
    pub organization_name: Option<String>,
    pub machine_hash: String,
}

pub fn router() -> Router<AppState> {
    Router::new().route("/api/orders/:order_id/license", post(issue_for_order))
}

async fn issue_for_order(
    State(state): State<AppState>,
    Path(order_id): Path<Uuid>,
    Json(request): Json<IssueRequest>,
) -> Result<Json<dokkomplekt_license_core::LicenseDocument>, StatusCode> {
    if request.machine_hash.trim().is_empty() {
        return Err(StatusCode::BAD_REQUEST);
    }
    let order = {
        let store = state.store.read().map_err(|_| StatusCode::INTERNAL_SERVER_ERROR)?;
        store.orders.get(&order_id).ok_or(StatusCode::NOT_FOUND)?.clone()
    };
    if !matches!(order.status, OrderStatus::Paid | OrderStatus::LicenseIssued) {
        return Err(StatusCode::CONFLICT);
    }
    let plan = parse_plan(&order.plan).ok_or(StatusCode::BAD_REQUEST)?;
    let issuer_key = state.config.issuer_key_b64.clone().ok_or(StatusCode::SERVICE_UNAVAILABLE)?;
    let document = issue_license(
        IssueLicenseInput {
            order_id,
            plan,
            owner_name: request.owner_name,
            organization_name: request.organization_name,
            allowed_machines: vec![request.machine_hash],
            valid_days: state.config.default_license_days,
        },
        &state.config.issuer_id,
        &issuer_key,
    )
    .map_err(|_| StatusCode::INTERNAL_SERVER_ERROR)?;
    {
        let mut store = state.store.write().map_err(|_| StatusCode::INTERNAL_SERVER_ERROR)?;
        if let Some(order) = store.orders.get_mut(&order_id) {
            order.status = OrderStatus::LicenseIssued;
        }
    }
    Ok(Json(document))
}

fn parse_plan(value: &str) -> Option<PlanId> {
    match value.trim() {
        "trial" => Some(PlanId::Trial),
        "doctor_start" => Some(PlanId::DoctorStart),
        "doctor_pro" => Some(PlanId::DoctorPro),
        "department" => Some(PlanId::Department),
        "clinic" => Some(PlanId::Clinic),
        "enterprise" => Some(PlanId::Enterprise),
        _ => None,
    }
}
