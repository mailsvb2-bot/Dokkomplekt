use crate::license_issue::issue_token_matches;
use crate::state::AppState;
use crate::storage::{LicenseRecord, StoreError};
use axum::{
    extract::{Path, State},
    http::StatusCode,
    routing::{get, post},
    Json, Router,
};
use serde::{Deserialize, Serialize};
use time::{format_description::well_known::Rfc3339, OffsetDateTime};

const DEFAULT_STATUS_CACHE_TTL_SECONDS: u32 = 24 * 60 * 60;

#[derive(Debug, Serialize)]
pub struct LicenseStatusResponse {
    pub schema: &'static str,
    pub license_id: String,
    pub status: &'static str,
    pub checked_at: String,
    pub revoked_at: Option<String>,
    pub cache_ttl_seconds: u32,
}

#[derive(Debug, Deserialize)]
pub struct RevokeLicenseRequest {
    pub admin_token: Option<String>,
    pub reason: Option<String>,
}

#[derive(Debug, Serialize)]
pub struct RevokeLicenseResponse {
    pub license_id: String,
    pub status: &'static str,
    pub revoked_at: String,
}

pub fn router() -> Router<AppState> {
    Router::new()
        .route("/api/licenses/:license_id/status", get(license_status))
        .route("/api/licenses/:license_id/revoke", post(revoke_license))
}

async fn license_status(
    State(state): State<AppState>,
    Path(license_id): Path<String>,
) -> Result<Json<LicenseStatusResponse>, StatusCode> {
    let license_id = normalized_license_id(&license_id)?;
    let record = state
        .store
        .get_license_by_id_async(&license_id)
        .await
        .map_err(store_error_status)?
        .ok_or(StatusCode::NOT_FOUND)?;
    Ok(Json(status_response(record, OffsetDateTime::now_utc())?))
}

async fn revoke_license(
    State(state): State<AppState>,
    Path(license_id): Path<String>,
    Json(request): Json<RevokeLicenseRequest>,
) -> Result<Json<RevokeLicenseResponse>, StatusCode> {
    let license_id = normalized_license_id(&license_id)?;
    let configured_admin_secret = state
        .config
        .license_issue_secret
        .as_deref()
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .ok_or(StatusCode::SERVICE_UNAVAILABLE)?;
    if !issue_token_matches(
        Some(configured_admin_secret),
        request.admin_token.as_deref(),
    ) {
        return Err(StatusCode::UNAUTHORIZED);
    }
    if request
        .reason
        .as_deref()
        .map(str::trim)
        .is_some_and(|reason| reason.len() > 500)
    {
        return Err(StatusCode::BAD_REQUEST);
    }
    let record = state
        .store
        .revoke_license_async(&license_id, OffsetDateTime::now_utc())
        .await
        .map_err(store_error_status)?;
    let revoked_at = record.revoked_at.ok_or(StatusCode::INTERNAL_SERVER_ERROR)?;
    Ok(Json(RevokeLicenseResponse {
        license_id: record.license_id,
        status: "revoked",
        revoked_at: format_time(revoked_at)?,
    }))
}

fn status_response(
    record: LicenseRecord,
    checked_at: OffsetDateTime,
) -> Result<LicenseStatusResponse, StatusCode> {
    let revoked_at = record.revoked_at.map(format_time).transpose()?;
    Ok(LicenseStatusResponse {
        schema: "dokkomplekt.license-status.v1",
        license_id: record.license_id,
        status: if revoked_at.is_some() {
            "revoked"
        } else {
            "active"
        },
        checked_at: format_time(checked_at)?,
        revoked_at,
        cache_ttl_seconds: status_cache_ttl_seconds(),
    })
}

fn normalized_license_id(value: &str) -> Result<String, StatusCode> {
    let value = value.trim();
    if value.is_empty() || value.len() > 200 {
        return Err(StatusCode::BAD_REQUEST);
    }
    Ok(value.to_string())
}

fn format_time(value: OffsetDateTime) -> Result<String, StatusCode> {
    value
        .format(&Rfc3339)
        .map_err(|_| StatusCode::INTERNAL_SERVER_ERROR)
}

fn status_cache_ttl_seconds() -> u32 {
    std::env::var("DOKKOMPLEKT_LICENSE_STATUS_CACHE_TTL_SECONDS")
        .ok()
        .and_then(|value| value.trim().parse::<u32>().ok())
        .filter(|value| *value > 0)
        .unwrap_or(DEFAULT_STATUS_CACHE_TTL_SECONDS)
}

fn store_error_status(error: StoreError) -> StatusCode {
    match error {
        StoreError::Conflict => StatusCode::CONFLICT,
        StoreError::Invalid(_) => StatusCode::BAD_REQUEST,
        StoreError::NotFound => StatusCode::NOT_FOUND,
        StoreError::Poisoned => StatusCode::INTERNAL_SERVER_ERROR,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use uuid::Uuid;

    #[test]
    fn status_response_is_revoked_when_revoked_at_exists() {
        let now = OffsetDateTime::now_utc();
        let response = status_response(
            LicenseRecord {
                id: Uuid::new_v4(),
                order_id: Uuid::new_v4(),
                license_id: "license-a".to_string(),
                document_json: "{}".to_string(),
                issued_at: now,
                revoked_at: Some(now),
            },
            now,
        )
        .unwrap();
        assert_eq!(response.status, "revoked");
        assert!(response.revoked_at.is_some());
    }
}
