use crate::config::ServerConfig;
use crate::storage::{AuditEventRecord, LicenseRecord, PaymentEventRecord};
use crate::storage_postgres::StoreBackend;
use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;
use std::sync::{Arc, RwLock};
use time::OffsetDateTime;
use uuid::Uuid;

#[derive(Clone)]
pub struct AppState {
    pub config: ServerConfig,
    pub store: StoreBackend,
}

impl AppState {
    pub fn new(config: ServerConfig) -> Self {
        Self {
            config,
            store: StoreBackend::Memory(Arc::new(RwLock::new(MemoryStore::default()))),
        }
    }

    pub fn from_config(config: ServerConfig) -> anyhow::Result<Self> {
        let store = StoreBackend::from_config(&config)?;
        Ok(Self { config, store })
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
