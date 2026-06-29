use crate::issuer::{issue_license, IssueLicenseInput};
use crate::state::{AppState, OrderStatus};
use crate::storage::{LicenseRecord, StoreError};
use axum::{extract::{Path, State}, http::StatusCode, routing::post, Json, Router};
use dokkomplekt_license_core::models::{LicenseDocument, PlanId};
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
) -> Result<Json<LicenseDocument>, StatusCode> {
    if request.machine_hash.trim().is_empty() {
        return Err(StatusCode::BAD_REQUEST);
    }
    let order = state.store.get_order_async(order_id).await.map_err(store_error_status)?.ok_or(StatusCode::NOT_FOUND)?;
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
    let record = LicenseRecord {
        id: Uuid::new_v4(),
        order_id,
        license_id: document.license.payload.license_id.clone(),
        document_json: serde_json::to_string(&document).map_err(|_| StatusCode::INTERNAL_SERVER_ERROR)?,
        issued_at: document.license.payload.issued_at,
        revoked_at: None,
    };
    let outcome = state.store.issue_license_for_paid_order_async(record).await.map_err(store_error_status)?;
    let response = serde_json::from_str(&outcome.record.document_json).map_err(|_| StatusCode::INTERNAL_SERVER_ERROR)?;
    Ok(Json(response))
}

fn store_error_status(error: StoreError) -> StatusCode {
    match error {
        StoreError::Conflict => StatusCode::CONFLICT,
        StoreError::Invalid(_) => StatusCode::BAD_REQUEST,
        StoreError::NotFound => StatusCode::NOT_FOUND,
        StoreError::Poisoned => StatusCode::INTERNAL_SERVER_ERROR,
    }
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
