use crate::config::ServerConfig;
use crate::storage::PaymentEventRecord;
use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;
use std::sync::{Arc, RwLock};
use time::OffsetDateTime;
use uuid::Uuid;

#[derive(Debug, Clone)]
pub struct AppState {
    pub config: ServerConfig,
    pub store: Arc<RwLock<MemoryStore>>,
}

impl AppState {
    pub fn new(config: ServerConfig) -> Self {
        Self { config, store: Arc::new(RwLock::new(MemoryStore::default())) }
    }
}

#[derive(Debug, Default)]
pub struct MemoryStore {
    pub orders: BTreeMap<Uuid, OrderRecord>,
    pub activations: BTreeMap<Uuid, ActivationRecord>,
    pub payment_events: BTreeMap<Uuid, PaymentEventRecord>,
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
