#![allow(dead_code)]

use crate::config::ServerConfig;
use crate::state::{ActivationRecord, MemoryStore, OrderRecord, OrderStatus};
use postgres::error::SqlState;
use postgres::{Client, NoTls};
use serde::{Deserialize, Serialize};
use std::sync::{Arc, Mutex, RwLock};
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
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{:?}", self)
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
        match config.database_url.as_deref().map(str::trim).filter(|value| !value.is_empty()) {
            Some(database_url) => Ok(Self::Postgres(PostgresStore::connect(database_url)?)),
            None => Ok(Self::Memory(Arc::new(RwLock::new(MemoryStore::default())))),
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

    fn audit(&self, record: AuditEventRecord) -> Result<(), StoreError> {
        match self {
            Self::Memory(store) => store.audit(record),
            Self::Postgres(store) => store.audit(record),
        }
    }
}

#[derive(Clone)]
pub struct PostgresStore {
    client: Arc<Mutex<Client>>,
}

impl PostgresStore {
    pub fn connect(database_url: &str) -> anyhow::Result<Self> {
        let mut client = Client::connect(database_url, NoTls)?;
        client.batch_execute(SCHEMA_V1)?;
        Ok(Self { client: Arc::new(Mutex::new(client)) })
    }

    fn client(&self) -> Result<std::sync::MutexGuard<'_, Client>, StoreError> {
        self.client.lock().map_err(|_| StoreError::Poisoned)
    }
}

impl LicenseStore for PostgresStore {
    fn create_order(&self, record: OrderRecord) -> Result<(), StoreError> {
        let mut client = self.client()?;
        let amount_rub = amount_to_i64(record.amount_rub)?;
        let status = order_status_to_str(&record.status);
        let machine_hash = record.machine_hash.as_deref();
        client
            .execute(
                "INSERT INTO license_orders (id, plan, amount_rub, status, machine_hash, created_at) VALUES ($1, $2, $3, $4, $5, $6)",
                &[&record.id, &record.plan, &amount_rub, &status, &machine_hash, &record.created_at],
            )
            .map_err(map_postgres_error)?;
        Ok(())
    }

    fn get_order(&self, order_id: Uuid) -> Result<Option<OrderRecord>, StoreError> {
        let mut client = self.client()?;
        let row = client
            .query_opt(
                "SELECT id, plan, amount_rub, status, machine_hash, created_at FROM license_orders WHERE id = $1",
                &[&order_id],
            )
            .map_err(map_postgres_error)?;
        row.map(order_from_row).transpose()
    }

    fn update_order_status(&self, order_id: Uuid, status: OrderStatus) -> Result<(), StoreError> {
        let mut client = self.client()?;
        let status = order_status_to_str(&status);
        let changed = client
            .execute("UPDATE license_orders SET status = $2 WHERE id = $1", &[&order_id, &status])
            .map_err(map_postgres_error)?;
        if changed == 0 {
            return Err(StoreError::NotFound);
        }
        Ok(())
    }

    fn create_activation(&self, record: ActivationRecord) -> Result<(), StoreError> {
        let mut client = self.client()?;
        client
            .execute(
                "INSERT INTO license_machines (id, order_id, machine_hash, created_at) VALUES ($1, $2, $3, $4)",
                &[&record.id, &record.order_id, &record.machine_hash, &record.created_at],
            )
            .map_err(map_postgres_error)?;
        Ok(())
    }

    fn create_activation_for_order(&self, record: ActivationRecord, max_machines: u32) -> Result<OrderRecord, StoreError> {
        let mut client = self.client()?;
        let mut transaction = client.transaction().map_err(map_postgres_error)?;
        let order_row = transaction
            .query_opt(
                "SELECT id, plan, amount_rub, status, machine_hash, created_at FROM license_orders WHERE id = $1 FOR UPDATE",
                &[&record.order_id],
            )
            .map_err(map_postgres_error)?
            .ok_or(StoreError::NotFound)?;
        let order = order_from_row(order_row)?;
        if !matches!(order.status, OrderStatus::Paid | OrderStatus::LicenseIssued) {
            return Err(StoreError::Conflict);
        }
        let active_count: i64 = transaction
            .query_one("SELECT COUNT(*) FROM license_machines WHERE order_id = $1", &[&record.order_id])
            .map_err(map_postgres_error)?
            .get(0);
        if active_count < 0 || active_count as u32 >= max_machines {
            return Err(StoreError::Conflict);
        }
        transaction
            .execute(
                "INSERT INTO license_machines (id, order_id, machine_hash, created_at) VALUES ($1, $2, $3, $4)",
                &[&record.id, &record.order_id, &record.machine_hash, &record.created_at],
            )
            .map_err(map_postgres_error)?;
        transaction.commit().map_err(map_postgres_error)?;
        Ok(order)
    }

    fn record_payment_event(&self, record: PaymentEventRecord) -> Result<(), StoreError> {
        let mut client = self.client()?;
        insert_payment_event(&mut client, &record)?;
        Ok(())
    }

    fn record_payment_event_for_order(&self, record: PaymentEventRecord) -> Result<PaymentEventWriteOutcome, StoreError> {
        let mut client = self.client()?;
        let mut transaction = client.transaction().map_err(map_postgres_error)?;
        let provider = payment_provider_to_str(&record.provider);
        let existing = transaction
            .query_opt(
                "SELECT id FROM billing_events WHERE provider = $1 AND provider_event_id = $2",
                &[&provider, &record.provider_event_id],
            )
            .map_err(map_postgres_error)?;
        if existing.is_some() {
            return Ok(PaymentEventWriteOutcome::Duplicate);
        }
        let order_row = transaction
            .query_opt(
                "SELECT id, plan, amount_rub, status, machine_hash, created_at FROM license_orders WHERE id = $1 FOR UPDATE",
                &[&record.order_id],
            )
            .map_err(map_postgres_error)?
            .ok_or(StoreError::NotFound)?;
        let order = order_from_row(order_row)?;
        if order.amount_rub != record.amount_rub {
            return Err(StoreError::Invalid("amount_mismatch".to_string()));
        }
        if matches!(record.status, PaymentEventStatus::Succeeded) {
            let status = order_status_to_str(&OrderStatus::Paid);
            transaction
                .execute("UPDATE license_orders SET status = $2 WHERE id = $1", &[&record.order_id, &status])
                .map_err(map_postgres_error)?;
        }
        insert_payment_event(&mut transaction, &record)?;
        transaction.commit().map_err(map_postgres_error)?;
        Ok(PaymentEventWriteOutcome::Recorded)
    }

    fn store_license(&self, record: LicenseRecord) -> Result<(), StoreError> {
        let mut client = self.client()?;
        client
            .execute(
                "INSERT INTO license_documents (id, order_id, license_id, document_json, issued_at, revoked_at) VALUES ($1, $2, $3, $4, $5, $6)",
                &[&record.id, &record.order_id, &record.license_id, &record.document_json, &record.issued_at, &record.revoked_at],
            )
            .map_err(map_postgres_error)?;
        Ok(())
    }

    fn audit(&self, record: AuditEventRecord) -> Result<(), StoreError> {
        let mut client = self.client()?;
        client
            .execute(
                "INSERT INTO license_audit_events (id, entity_id, event_type, happened_at, details_json) VALUES ($1, $2, $3, $4, $5)",
                &[&record.id, &record.entity_id, &record.event_type, &record.happened_at, &record.details_json],
            )
            .map_err(map_postgres_error)?;
        Ok(())
    }
}

fn insert_payment_event(client: &mut impl postgres::GenericClient, record: &PaymentEventRecord) -> Result<(), StoreError> {
    let provider = payment_provider_to_str(&record.provider);
    let status = payment_status_to_str(&record.status);
    let amount_rub = amount_to_i64(record.amount_rub)?;
    let provider_reference_id = record.provider_payment_id.as_deref();
    client
        .execute(
            "INSERT INTO billing_events (id, order_id, provider, provider_event_id, provider_reference_id, status, amount_rub, received_at) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)",
            &[
                &record.id,
                &record.order_id,
                &provider,
                &record.provider_event_id,
                &provider_reference_id,
                &status,
                &amount_rub,
                &record.received_at,
            ],
        )
        .map_err(map_postgres_error)?;
    Ok(())
}

fn order_from_row(row: postgres::Row) -> Result<OrderRecord, StoreError> {
    let amount_rub: i64 = row.get("amount_rub");
    let status: String = row.get("status");
    Ok(OrderRecord {
        id: row.get("id"),
        plan: row.get("plan"),
        amount_rub: amount_from_i64(amount_rub)?,
        status: order_status_from_str(&status)?,
        machine_hash: row.get("machine_hash"),
        created_at: row.get("created_at"),
    })
}

fn amount_to_i64(amount: u64) -> Result<i64, StoreError> {
    i64::try_from(amount).map_err(|_| StoreError::Invalid("amount_overflow".to_string()))
}

fn amount_from_i64(amount: i64) -> Result<u64, StoreError> {
    u64::try_from(amount).map_err(|_| StoreError::Invalid("amount_negative".to_string()))
}

fn order_status_to_str(status: &OrderStatus) -> &'static str {
    match status {
        OrderStatus::Draft => "draft",
        OrderStatus::WaitingPayment => "waiting_payment",
        OrderStatus::Paid => "paid",
        OrderStatus::LicenseIssued => "license_issued",
        OrderStatus::Cancelled => "cancelled",
    }
}

fn order_status_from_str(value: &str) -> Result<OrderStatus, StoreError> {
    match value {
        "draft" => Ok(OrderStatus::Draft),
        "waiting_payment" => Ok(OrderStatus::WaitingPayment),
        "paid" => Ok(OrderStatus::Paid),
        "license_issued" => Ok(OrderStatus::LicenseIssued),
        "cancelled" => Ok(OrderStatus::Cancelled),
        other => Err(StoreError::Invalid(format!("unknown_order_status:{other}"))),
    }
}

fn payment_provider_to_str(provider: &PaymentProvider) -> &'static str {
    match provider {
        PaymentProvider::Manual => "manual",
        PaymentProvider::YooKassa => "yookassa",
        PaymentProvider::Sbp => "sbp",
        PaymentProvider::BankInvoice => "bank_invoice",
    }
}

fn payment_status_to_str(status: &PaymentEventStatus) -> &'static str {
    match status {
        PaymentEventStatus::Pending => "pending",
        PaymentEventStatus::Succeeded => "succeeded",
        PaymentEventStatus::Cancelled => "cancelled",
        PaymentEventStatus::Rejected => "rejected",
    }
}

fn map_postgres_error(error: postgres::Error) -> StoreError {
    if let Some(db_error) = error.as_db_error() {
        if db_error.code() == &SqlState::UNIQUE_VIOLATION {
            return StoreError::Conflict;
        }
        if db_error.code() == &SqlState::FOREIGN_KEY_VIOLATION {
            return StoreError::NotFound;
        }
    }
    StoreError::Invalid(error.to_string())
}

pub const SCHEMA_V1: &str = include_str!("../migrations/0001_license_schema.sql");

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn postgres_store_roundtrip_when_database_url_is_present() {
        let Ok(database_url) = std::env::var("DATABASE_URL") else {
            return;
        };
        let store = PostgresStore::connect(&database_url).unwrap();
        let order_id = Uuid::new_v4();
        let order = OrderRecord {
            id: order_id,
            plan: "doctor_pro".to_string(),
            amount_rub: 3900,
            status: OrderStatus::WaitingPayment,
            machine_hash: None,
            created_at: OffsetDateTime::now_utc(),
        };
        store.create_order(order).unwrap();
        assert!(matches!(store.get_order(order_id).unwrap().unwrap().status, OrderStatus::WaitingPayment));

        let event = PaymentEventRecord {
            id: Uuid::new_v4(),
            order_id,
            provider: PaymentProvider::Manual,
            provider_event_id: format!("evt-{order_id}"),
            provider_payment_id: None,
            status: PaymentEventStatus::Succeeded,
            amount_rub: 3900,
            received_at: OffsetDateTime::now_utc(),
        };
        assert_eq!(store.record_payment_event_for_order(event).unwrap(), PaymentEventWriteOutcome::Recorded);
        assert!(matches!(store.get_order(order_id).unwrap().unwrap().status, OrderStatus::Paid));
    }
}
