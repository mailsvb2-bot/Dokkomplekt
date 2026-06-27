use std::collections::BTreeSet;

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct RevocationSet {
    license_ids: BTreeSet<String>,
}

impl RevocationSet {
    pub fn new<I, S>(license_ids: I) -> Self
    where
        I: IntoIterator<Item = S>,
        S: AsRef<str>,
    {
        Self {
            license_ids: license_ids
                .into_iter()
                .map(|item| item.as_ref().trim().to_ascii_lowercase())
                .filter(|item| !item.is_empty())
                .collect(),
        }
    }

    pub fn is_revoked(&self, license_id: &str) -> bool {
        self.license_ids.contains(&license_id.trim().to_ascii_lowercase())
    }
}

pub fn license_revocation_code(license_id: &str, revocations: &RevocationSet) -> Option<&'static str> {
    if revocations.is_revoked(license_id) {
        Some("license_revoked")
    } else {
        None
    }
}
