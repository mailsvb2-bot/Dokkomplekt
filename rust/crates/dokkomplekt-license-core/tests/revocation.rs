use dokkomplekt_license_core::revocation::{license_revocation_code, RevocationSet};

#[test]
fn revoked_license_id_returns_block_code() {
    let revocations = RevocationSet::new(["DKK-REVOKED-1"]);
    assert_eq!(license_revocation_code("dkk-revoked-1", &revocations), Some("license_revoked"));
}

#[test]
fn unknown_license_id_is_not_blocked_by_revocation_set() {
    let revocations = RevocationSet::new(["DKK-REVOKED-1"]);
    assert_eq!(license_revocation_code("DKK-ACTIVE-1", &revocations), None);
}
