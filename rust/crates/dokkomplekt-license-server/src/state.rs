use crate::config::ServerConfig;
use crate::storage::{AuditEventRecord, LicenseRecord, PaymentEventRecord, StoreBackend};
use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;
use time::OffsetDateTime;
use uuid::Uuid;

#[derive(Clone)]
pub struct AppState {
    pub config: ServerConfig,
    pub store: StoreBackend,
}

impl AppState {
    pub fn new(config: ServerConfig) -> Self {
        let store = StoreBackend::from_config(&config).expect("license store backend must initialize");
        Self { config, store }
    }
}

#[derive(Debug, Default)]
pub struct MemoryStore {
    pub orders: BTreeMap<Uuid, OrderRecord>,
    pub activations: BTreeMap<Uuid, ActivationRecord>,
    pub payment_events: BTreeMap<Uuid, PaymentEventRecord>,
    pub licenses: BTreeMap<Uuid, LicenseRecord>,
    pub audit_events: BTreeMap<Uuid, AuditEventRecord>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OrderRecord {
    pub id: Uuid,
    pub plan: String,
    pub amount_rub: u64,
    pub status: OrderStatus,
    pub machine_hash: Option<String>,
    pub created_at: OffsetDateTime,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum OrderStatus {
    Draft,
    WaitingPayment,
    Paid,
    LicenseIssued,
    Cancelled,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ActivationRecord {
    pub id: Uuid,
    pub order_id: Uuid,
    pub machine_hash: String,
    pub created_at: OffsetDateTime,
}
