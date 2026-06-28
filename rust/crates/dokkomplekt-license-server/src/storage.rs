#![allow(dead_code)]

mod postgres;

pub use postgres::PostgresStore;

use crate::config::ServerConfig;
use crate::state::{ActivationRecord, MemoryStore, OrderRecord, OrderStatus};
use serde::{Deserialize, Serialize};
use std::sync::{Arc, RwLock};
use time::OffsetDateTime;
use uuid::Uuid;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PaymentEventRecord {
    pub id: Uuid,
    pub order_id: Uuid,
    pub provider: PaymentProvider,
    pub provider_event_id: String,
    pub provider_payment_id: Option<String>,
    pub status: PaymentEventStatus,
    pub amount_rub: u64,
    pub received_at: OffsetDateTime,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum PaymentProvider {
    Manual,
    YooKassa,
    Sbp,
    BankInvoice,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum PaymentEventStatus {
    Pending,
    Succeeded,
    Cancelled,
    Rejected,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum PaymentEventWriteOutcome {
    Recorded,
    Duplicate,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LicenseRecord {
    pub id: Uuid,
    pub order_id: Uuid,
    pub license_id: String,
    pub document_json: String,
    pub issued_at: OffsetDateTime,
    pub revoked_at: Option<OffsetDateTime>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct LicenseIssueOutcome {
    pub record: LicenseRecord,
    pub reused: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AuditEventRecord {
    pub id: Uuid,
    pub entity_id: Uuid,
    pub event_type: String,
    pub happened_at: OffsetDateTime,
    pub details_json: String,
}

pub trait LicenseStore: Send + Sync + 'static {
    fn create_order(&self, record: OrderRecord) -> Result<(), StoreError>;
    fn get_order(&self, order_id: Uuid) -> Result<Option<OrderRecord>, StoreError>;
    fn update_order_status(&self, order_id: Uuid, status: OrderStatus) -> Result<(), StoreError>;
    fn create_activation(&self, record: ActivationRecord) -> Result<(), StoreError>;
    fn create_activation_for_order(&self, record: ActivationRecord, max_machines: u32) -> Result<OrderRecord, StoreError>;
    fn record_payment_event(&self, record: PaymentEventRecord) -> Result<(), StoreError>;
    fn record_payment_event_for_order(&self, record: PaymentEventRecord) -> Result<PaymentEventWriteOutcome, StoreError>;
    fn store_license(&self, record: LicenseRecord) -> Result<(), StoreError>;
    fn issue_license_for_paid_order(&self, record: LicenseRecord) -> Result<LicenseIssueOutcome, StoreError>;
    fn audit(&self, record: AuditEventRecord) -> Result<(), StoreError>;
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum StoreError {
    Poisoned,
    NotFound,
    Conflict,
    Invalid(String),
}

impl std::fmt::Display for StoreError {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(formatter, "{self:?}")
    }
}

impl std::error::Error for StoreError {}

#[derive(Clone)]
pub enum StoreBackend {
    Memory(Arc<RwLock<MemoryStore>>),
    Postgres(PostgresStore),
}

impl StoreBackend {
    pub fn from_config(config: &ServerConfig) -> anyhow::Result<Self> {
        Ok(match config.database_url.as_deref().map(str::trim).filter(|value| !value.is_empty()) {
            Some(url) => Self::Postgres(PostgresStore::connect(url)?),
            None => Self::Memory(Arc::new(RwLock::new(MemoryStore::default()))),
        })
    }

    pub fn backend_name(&self) -> &'static str {
        match self {
            Self::Memory(_) => "memory",
            Self::Postgres(_) => "postgres",
        }
    }

    pub fn database_connected(&self) -> bool {
        matches!(self, Self::Postgres(_))
    }

    pub async fn database_ready_async(&self) -> bool {
        match self {
            Self::Memory(_) => false,
            Self::Postgres(store) => {
                let store = store.clone();
                tokio::task::spawn_blocking(move || store.check_ready().is_ok()).await.unwrap_or(false)
            }
        }
    }

    pub async fn create_order_async(&self, record: OrderRecord) -> Result<(), StoreError> {
        match self {
            Self::Memory(store) => store.create_order(record),
            Self::Postgres(store) => {
                let store = store.clone();
                tokio::task::spawn_blocking(move || store.create_order(record)).await.map_err(|_| StoreError::Poisoned)?
            }
        }
    }

    pub async fn get_order_async(&self, order_id: Uuid) -> Result<Option<OrderRecord>, StoreError> {
        match self {
            Self::Memory(store) => store.get_order(order_id),
            Self::Postgres(store) => {
                let store = store.clone();
                tokio::task::spawn_blocking(move || store.get_order(order_id)).await.map_err(|_| StoreError::Poisoned)?
            }
        }
    }

    pub async fn update_order_status_async(&self, order_id: Uuid, status: OrderStatus) -> Result<(), StoreError> {
        match self {
            Self::Memory(store) => store.update_order_status(order_id, status),
            Self::Postgres(store) => {
                let store = store.clone();
                tokio::task::spawn_blocking(move || store.update_order_status(order_id, status)).await.map_err(|_| StoreError::Poisoned)?
            }
        }
    }

    pub async fn create_activation_for_order_async(&self, record: ActivationRecord, max_machines: u32) -> Result<OrderRecord, StoreError> {
        match self {
            Self::Memory(store) => store.create_activation_for_order(record, max_machines),
            Self::Postgres(store) => {
                let store = store.clone();
                tokio::task::spawn_blocking(move || store.create_activation_for_order(record, max_machines)).await.map_err(|_| StoreError::Poisoned)?
            }
        }
    }

    pub async fn record_payment_event_for_order_async(&self, record: PaymentEventRecord) -> Result<PaymentEventWriteOutcome, StoreError> {
        match self {
            Self::Memory(store) => store.record_payment_event_for_order(record),
            Self::Postgres(store) => {
                let store = store.clone();
                tokio::task::spawn_blocking(move || store.record_payment_event_for_order(record)).await.map_err(|_| StoreError::Poisoned)?
            }
        }
    }

    pub async fn store_license_async(&self, record: LicenseRecord) -> Result<(), StoreError> {
        match self {
            Self::Memory(store) => store.store_license(record),
            Self::Postgres(store) => {
                let store = store.clone();
                tokio::task::spawn_blocking(move || store.store_license(record)).await.map_err(|_| StoreError::Poisoned)?
            }
        }
    }

    pub async fn issue_license_for_paid_order_async(&self, record: LicenseRecord) -> Result<LicenseIssueOutcome, StoreError> {
        match self {
            Self::Memory(store) => store.issue_license_for_paid_order(record),
            Self::Postgres(store) => {
                let store = store.clone();
                tokio::task::spawn_blocking(move || store.issue_license_for_paid_order(record)).await.map_err(|_| StoreError::Poisoned)?
            }
        }
    }
}

impl LicenseStore for StoreBackend {
    fn create_order(&self, record: OrderRecord) -> Result<(), StoreError> {
        match self {
            Self::Memory(store) => store.create_order(record),
            Self::Postgres(store) => store.create_order(record),
        }
    }

    fn get_order(&self, order_id: Uuid) -> Result<Option<OrderRecord>, StoreError> {
        match self {
            Self::Memory(store) => store.get_order(order_id),
            Self::Postgres(store) => store.get_order(order_id),
        }
    }

    fn update_order_status(&self, order_id: Uuid, status: OrderStatus) -> Result<(), StoreError> {
        match self {
            Self::Memory(store) => store.update_order_status(order_id, status),
            Self::Postgres(store) => store.update_order_status(order_id, status),
        }
    }

    fn create_activation(&self, record: ActivationRecord) -> Result<(), StoreError> {
        match self {
            Self::Memory(store) => store.create_activation(record),
            Self::Postgres(store) => store.create_activation(record),
        }
    }

    fn create_activation_for_order(&self, record: ActivationRecord, max_machines: u32) -> Result<OrderRecord, StoreError> {
        match self {
            Self::Memory(store) => store.create_activation_for_order(record, max_machines),
            Self::Postgres(store) => store.create_activation_for_order(record, max_machines),
        }
    }

    fn record_payment_event(&self, record: PaymentEventRecord) -> Result<(), StoreError> {
        match self {
            Self::Memory(store) => store.record_payment_event(record),
            Self::Postgres(store) => store.record_payment_event(record),
        }
    }

    fn record_payment_event_for_order(&self, record: PaymentEventRecord) -> Result<PaymentEventWriteOutcome, StoreError> {
        match self {
            Self::Memory(store) => store.record_payment_event_for_order(record),
            Self::Postgres(store) => store.record_payment_event_for_order(record),
        }
    }

    fn store_license(&self, record: LicenseRecord) -> Result<(), StoreError> {
        match self {
            Self::Memory(store) => store.store_license(record),
            Self::Postgres(store) => store.store_license(record),
        }
    }

    fn issue_license_for_paid_order(&self, record: LicenseRecord) -> Result<LicenseIssueOutcome, StoreError> {
        match self {
            Self::Memory(store) => store.issue_license_for_paid_order(record),
            Self::Postgres(store) => store.issue_license_for_paid_order(record),
        }
    }

    fn audit(&self, record: AuditEventRecord) -> Result<(), StoreError> {
        match self {
            Self::Memory(store) => store.audit(record),
            Self::Postgres(store) => store.audit(record),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::state::{ActivationRecord, OrderRecord, OrderStatus};

    fn order_record(id: Uuid, status: OrderStatus) -> OrderRecord {
        OrderRecord {
            id,
            plan: "doctor_pro".to_string(),
            amount_rub: 3900,
            status,
            machine_hash: None,
            created_at: OffsetDateTime::now_utc(),
        }
    }

    fn payment_event(order_id: Uuid, provider_event_id: String) -> PaymentEventRecord {
        PaymentEventRecord {
            id: Uuid::new_v4(),
            order_id,
            provider: PaymentProvider::Manual,
            provider_event_id,
            provider_payment_id: None,
            status: PaymentEventStatus::Succeeded,
            amount_rub: 3900,
            received_at: OffsetDateTime::now_utc(),
        }
    }

    fn activation(order_id: Uuid, machine_hash: &str) -> ActivationRecord {
        ActivationRecord {
            id: Uuid::new_v4(),
            order_id,
            machine_hash: machine_hash.to_string(),
            created_at: OffsetDateTime::now_utc(),
        }
    }

    fn license_record(order_id: Uuid, license_id: &str) -> LicenseRecord {
        LicenseRecord {
            id: Uuid::new_v4(),
            order_id,
            license_id: license_id.to_string(),
            document_json: format!(r#"{{"license_id":"{license_id}"}}"#),
            issued_at: OffsetDateTime::now_utc(),
            revoked_at: None,
        }
    }

    fn assert_license_store_contract(store: StoreBackend) {
        let order_id = Uuid::new_v4();
        store.create_order(order_record(order_id, OrderStatus::WaitingPayment)).unwrap();
        assert!(matches!(store.get_order(order_id).unwrap().unwrap().status, OrderStatus::WaitingPayment));

        let event_id = format!("evt-{order_id}");
        let event = payment_event(order_id, event_id);
        assert_eq!(store.record_payment_event_for_order(event.clone()).unwrap(), PaymentEventWriteOutcome::Recorded);
        assert_eq!(
            store.record_payment_event_for_order(PaymentEventRecord { id: Uuid::new_v4(), ..event }).unwrap(),
            PaymentEventWriteOutcome::Duplicate,
        );
        assert!(matches!(store.get_order(order_id).unwrap().unwrap().status, OrderStatus::Paid));

        store.create_activation_for_order(activation(order_id, "machine-a"), 1).unwrap();
        assert_eq!(store.create_activation_for_order(activation(order_id, "machine-b"), 1).unwrap_err(), StoreError::Conflict);

        let unpaid_order_id = Uuid::new_v4();
        store.create_order(order_record(unpaid_order_id, OrderStatus::WaitingPayment)).unwrap();
        assert_eq!(store.create_activation_for_order(activation(unpaid_order_id, "machine-c"), 1).unwrap_err(), StoreError::Conflict);

        let license_id = format!("license-{order_id}");
        let license = license_record(order_id, &license_id);
        store.store_license(license.clone()).unwrap();
        assert_eq!(
            store.store_license(LicenseRecord { id: Uuid::new_v4(), ..license }).unwrap_err(),
            StoreError::Conflict,
        );

        let issue_order_id = Uuid::new_v4();
        store.create_order(order_record(issue_order_id, OrderStatus::Paid)).unwrap();
        let issued = store.issue_license_for_paid_order(license_record(issue_order_id, "license-issued")).unwrap();
        assert!(!issued.reused);
        assert_eq!(issued.record.license_id, "license-issued");
        assert!(matches!(store.get_order(issue_order_id).unwrap().unwrap().status, OrderStatus::LicenseIssued));
        let reused = store.issue_license_for_paid_order(license_record(issue_order_id, "license-new-but-ignored")).unwrap();
        assert!(reused.reused);
        assert_eq!(reused.record.license_id, "license-issued");

        let audit = AuditEventRecord {
            id: Uuid::new_v4(),
            entity_id: order_id,
            event_type: "license_store_contract".to_string(),
            happened_at: OffsetDateTime::now_utc(),
            details_json: "{}".to_string(),
        };
        store.audit(audit.clone()).unwrap();
        assert_eq!(store.audit(audit).unwrap_err(), StoreError::Conflict);
    }

    #[test]
    fn memory_backend_obeys_license_store_contract() {
        assert_license_store_contract(StoreBackend::Memory(Arc::new(RwLock::new(MemoryStore::default()))));
    }

    #[test]
    fn postgres_backend_obeys_license_store_contract_when_database_url_is_present() {
        let Ok(database_url) = std::env::var("DATABASE_URL") else { return; };
        let store = StoreBackend::Postgres(PostgresStore::connect(&database_url).unwrap());
        assert_license_store_contract(store);
    }
}
