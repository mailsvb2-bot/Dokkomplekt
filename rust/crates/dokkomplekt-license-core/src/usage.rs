use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq, Default)]
pub struct UsageLedger {
    pub month_counters: BTreeMap<String, UsageCounter>,
    pub trial_created_total: u32,
    pub last_seen_utc: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq, Default)]
pub struct UsageCounter {
    pub created_documents: u32,
}

impl UsageLedger {
    pub fn documents_for_month(&self, month_key: &str) -> u32 {
        self.month_counters
            .get(month_key)
            .map(|counter| counter.created_documents)
            .unwrap_or(0)
    }
}
