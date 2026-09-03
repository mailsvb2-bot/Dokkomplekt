use crate::core_error::{CoreError, CoreResult};
use crate::models::LicensePayload;
use serde::{Deserialize, Serialize};
use time::{Duration, OffsetDateTime};

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum RevocationState {
    Active,
    Revoked,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct LicenseStatusCache {
    pub license_id: String,
    pub state: RevocationState,
    #[serde(with = "time::serde::rfc3339")]
    pub checked_at: OffsetDateTime,
    #[serde(default, with = "time::serde::rfc3339::option")]
    pub revoked_at: Option<OffsetDateTime>,
    pub cache_ttl_seconds: u32,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum RevocationDecision {
    Allowed,
    Denied,
    RefreshRequired,
}

pub fn evaluate_revocation_cache(
    payload: &LicensePayload,
    cache: Option<&LicenseStatusCache>,
    now: OffsetDateTime,
    online_status_configured: bool,
) -> CoreResult<RevocationDecision> {
    let Some(cache) = cache else {
        return Ok(if online_status_configured {
            RevocationDecision::RefreshRequired
        } else {
            RevocationDecision::Allowed
        });
    };
    if cache.license_id.trim() != payload.license_id.trim() {
        return Err(CoreError::BadRevocationCache(
            "license_id_mismatch".to_string(),
        ));
    }
    if matches!(cache.state, RevocationState::Revoked) {
        return Ok(RevocationDecision::Denied);
    }
    if !online_status_configured {
        return Ok(RevocationDecision::Allowed);
    }
    let ttl = Duration::seconds(i64::from(cache.cache_ttl_seconds.max(1)));
    if now <= cache.checked_at + ttl {
        return Ok(RevocationDecision::Allowed);
    }
    let grace = Duration::days(i64::from(payload.grace_days));
    if payload.grace_days > 0 && now <= cache.checked_at + ttl + grace {
        return Ok(RevocationDecision::Allowed);
    }
    Ok(RevocationDecision::RefreshRequired)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::models::{PlanId, WatermarkMode};
    use std::collections::BTreeMap;

    fn payload(now: OffsetDateTime) -> LicensePayload {
        LicensePayload {
            license_id: "license-a".to_string(),
            order_id: None,
            plan: PlanId::DoctorPro,
            owner_name: None,
            organization_name: None,
            seats: 1,
            allowed_machines: Vec::new(),
            valid_from: now - Duration::days(1),
            valid_until: now + Duration::days(365),
            document_limit_month: 3_000,
            template_limit: 150,
            profile_limit: 3,
            features: Vec::new(),
            grace_days: 7,
            watermark_mode: WatermarkMode::None,
            issued_by: "test".to_string(),
            issued_at: now - Duration::days(1),
            metadata: BTreeMap::new(),
        }
    }

    #[test]
    fn revoked_cache_denies_even_while_fresh() {
        let now = OffsetDateTime::now_utc();
        let cache = LicenseStatusCache {
            license_id: "license-a".to_string(),
            state: RevocationState::Revoked,
            checked_at: now,
            revoked_at: Some(now),
            cache_ttl_seconds: 3_600,
        };
        assert_eq!(
            evaluate_revocation_cache(&payload(now), Some(&cache), now, true).unwrap(),
            RevocationDecision::Denied
        );
    }

    #[test]
    fn stale_cache_uses_license_grace_then_requires_refresh() {
        let now = OffsetDateTime::now_utc();
        let cache = LicenseStatusCache {
            license_id: "license-a".to_string(),
            state: RevocationState::Active,
            checked_at: now - Duration::days(2),
            revoked_at: None,
            cache_ttl_seconds: 3_600,
        };
        assert_eq!(
            evaluate_revocation_cache(&payload(now), Some(&cache), now, true).unwrap(),
            RevocationDecision::Allowed
        );
        let very_old = LicenseStatusCache {
            checked_at: now - Duration::days(20),
            ..cache
        };
        assert_eq!(
            evaluate_revocation_cache(&payload(now), Some(&very_old), now, true).unwrap(),
            RevocationDecision::RefreshRequired
        );
    }
}
