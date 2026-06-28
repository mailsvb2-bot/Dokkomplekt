#![allow(dead_code)]

use crate::config::ServerConfig;
use crate::state::{ActivationRecord, MemoryStore, OrderRecord, OrderStatus};
use postgres::error::SqlState;
use postgres::{Client, GenericClient, NoTls, Row};
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
pub enum PaymentProvider { Manual, YooKassa, Sbp, BankInvoice }

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum PaymentEventStatus { Pending, Succeeded, Cancelled, Rejected }

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum PaymentEventWriteOutcome { Recorded, Duplicate }

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
pub enum StoreError { Poisoned, NotFound, Conflict, Invalid(String) }

impl std::fmt::Display for StoreError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result { write!(f, "{:?}", self) }
}
impl std::error::Error for StoreError {}

#[derive(Clone)]
pub enum StoreBackend { Memory(Arc<RwLock<MemoryStore>>), Postgres(PostgresStore) }

impl StoreBackend {
    pub fn from_config(config: &ServerConfig) -> anyhow::Result<Self> {
        Ok(match config.database_url.as_deref().map(str::trim).filter(|value| !value.is_empty()) {
            Some(url) => Self::Postgres(PostgresStore::connect(url)?),
            None => Self::Memory(Arc::new(RwLock::new(MemoryStore::default()))),
        })
    }
}

impl LicenseStore for StoreBackend {
    fn create_order(&self, r: OrderRecord) -> Result<(), StoreError> { match self { Self::Memory(s) => s.create_order(r), Self::Postgres(s) => s.create_order(r) } }
    fn get_order(&self, id: Uuid) -> Result<Option<OrderRecord>, StoreError> { match self { Self::Memory(s) => s.get_order(id), Self::Postgres(s) => s.get_order(id) } }
    fn update_order_status(&self, id: Uuid, st: OrderStatus) -> Result<(), StoreError> { match self { Self::Memory(s) => s.update_order_status(id, st), Self::Postgres(s) => s.update_order_status(id, st) } }
    fn create_activation(&self, r: ActivationRecord) -> Result<(), StoreError> { match self { Self::Memory(s) => s.create_activation(r), Self::Postgres(s) => s.create_activation(r) } }
    fn create_activation_for_order(&self, r: ActivationRecord, max: u32) -> Result<OrderRecord, StoreError> { match self { Self::Memory(s) => s.create_activation_for_order(r, max), Self::Postgres(s) => s.create_activation_for_order(r, max) } }
    fn record_payment_event(&self, r: PaymentEventRecord) -> Result<(), StoreError> { match self { Self::Memory(s) => s.record_payment_event(r), Self::Postgres(s) => s.record_payment_event(r) } }
    fn record_payment_event_for_order(&self, r: PaymentEventRecord) -> Result<PaymentEventWriteOutcome, StoreError> { match self { Self::Memory(s) => s.record_payment_event_for_order(r), Self::Postgres(s) => s.record_payment_event_for_order(r) } }
    fn store_license(&self, r: LicenseRecord) -> Result<(), StoreError> { match self { Self::Memory(s) => s.store_license(r), Self::Postgres(s) => s.store_license(r) } }
    fn audit(&self, r: AuditEventRecord) -> Result<(), StoreError> { match self { Self::Memory(s) => s.audit(r), Self::Postgres(s) => s.audit(r) } }
}

#[derive(Clone)]
pub struct PostgresStore { client: Arc<Mutex<Client>> }

impl PostgresStore {
    pub fn connect(database_url: &str) -> anyhow::Result<Self> {
        let mut client = Client::connect(database_url, NoTls)?;
        client.batch_execute(SCHEMA_V1)?;
        Ok(Self { client: Arc::new(Mutex::new(client)) })
    }
    fn client(&self) -> Result<std::sync::MutexGuard<'_, Client>, StoreError> { self.client.lock().map_err(|_| StoreError::Poisoned) }
}

impl LicenseStore for PostgresStore {
    fn create_order(&self, r: OrderRecord) -> Result<(), StoreError> {
        let mut c = self.client()?;
        let amount = amount_to_i64(r.amount_rub)?;
        let status = order_status_to_str(&r.status);
        let machine_hash = r.machine_hash.as_deref();
        c.execute("INSERT INTO license_orders (id, plan, amount_rub, status, machine_hash, created_at) VALUES ($1, $2, $3, $4, $5, $6)", &[&r.id, &r.plan, &amount, &status, &machine_hash, &r.created_at]).map_err(pg_err)?;
        Ok(())
    }

    fn get_order(&self, id: Uuid) -> Result<Option<OrderRecord>, StoreError> {
        let mut c = self.client()?;
        c.query_opt("SELECT id, plan, amount_rub, status, machine_hash, created_at FROM license_orders WHERE id = $1", &[&id]).map_err(pg_err)?.map(order_from_row).transpose()
    }

    fn update_order_status(&self, id: Uuid, st: OrderStatus) -> Result<(), StoreError> {
        let mut c = self.client()?;
        let status = order_status_to_str(&st);
        let n = c.execute("UPDATE license_orders SET status = $2 WHERE id = $1", &[&id, &status]).map_err(pg_err)?;
        if n == 0 { Err(StoreError::NotFound) } else { Ok(()) }
    }

    fn create_activation(&self, r: ActivationRecord) -> Result<(), StoreError> {
        let mut c = self.client()?;
        c.execute("INSERT INTO license_machines (id, order_id, machine_hash, created_at) VALUES ($1, $2, $3, $4)", &[&r.id, &r.order_id, &r.machine_hash, &r.created_at]).map_err(pg_err)?;
        Ok(())
    }

    fn create_activation_for_order(&self, r: ActivationRecord, max: u32) -> Result<OrderRecord, StoreError> {
        let mut c = self.client()?;
        let mut tx = c.transaction().map_err(pg_err)?;
        let row = tx.query_opt("SELECT id, plan, amount_rub, status, machine_hash, created_at FROM license_orders WHERE id = $1 FOR UPDATE", &[&r.order_id]).map_err(pg_err)?.ok_or(StoreError::NotFound)?;
        let order = order_from_row(row)?;
        if !matches!(order.status, OrderStatus::Paid | OrderStatus::LicenseIssued) { return Err(StoreError::Conflict); }
        let count: i64 = tx.query_one("SELECT COUNT(*) FROM license_machines WHERE order_id = $1", &[&r.order_id]).map_err(pg_err)?.get(0);
        if count < 0 || count as u32 >= max { return Err(StoreError::Conflict); }
        tx.execute("INSERT INTO license_machines (id, order_id, machine_hash, created_at) VALUES ($1, $2, $3, $4)", &[&r.id, &r.order_id, &r.machine_hash, &r.created_at]).map_err(pg_err)?;
        tx.commit().map_err(pg_err)?;
        Ok(order)
    }

    fn record_payment_event(&self, r: PaymentEventRecord) -> Result<(), StoreError> {
        let mut c = self.client()?;
        insert_payment_event(&mut *c, &r)
    }

    fn record_payment_event_for_order(&self, r: PaymentEventRecord) -> Result<PaymentEventWriteOutcome, StoreError> {
        let mut c = self.client()?;
        let mut tx = c.transaction().map_err(pg_err)?;
        let provider = payment_provider_to_str(&r.provider);
        if tx.query_opt("SELECT id FROM billing_events WHERE provider = $1 AND provider_event_id = $2", &[&provider, &r.provider_event_id]).map_err(pg_err)?.is_some() {
            return Ok(PaymentEventWriteOutcome::Duplicate);
        }
        let row = tx.query_opt("SELECT id, plan, amount_rub, status, machine_hash, created_at FROM license_orders WHERE id = $1 FOR UPDATE", &[&r.order_id]).map_err(pg_err)?.ok_or(StoreError::NotFound)?;
        let order = order_from_row(row)?;
        if order.amount_rub != r.amount_rub { return Err(StoreError::Invalid("amount_mismatch".to_string())); }
        if matches!(r.status, PaymentEventStatus::Succeeded) {
            let paid = order_status_to_str(&OrderStatus::Paid);
            tx.execute("UPDATE license_orders SET status = $2 WHERE id = $1", &[&r.order_id, &paid]).map_err(pg_err)?;
        }
        insert_payment_event(&mut tx, &r)?;
        tx.commit().map_err(pg_err)?;
        Ok(PaymentEventWriteOutcome::Recorded)
    }

    fn store_license(&self, r: LicenseRecord) -> Result<(), StoreError> {
        let mut c = self.client()?;
        c.execute("INSERT INTO license_documents (id, order_id, license_id, document_json, issued_at, revoked_at) VALUES ($1, $2, $3, $4, $5, $6)", &[&r.id, &r.order_id, &r.license_id, &r.document_json, &r.issued_at, &r.revoked_at]).map_err(pg_err)?;
        Ok(())
    }

    fn audit(&self, r: AuditEventRecord) -> Result<(), StoreError> {
        let mut c = self.client()?;
        c.execute("INSERT INTO license_audit_events (id, entity_id, event_type, happened_at, details_json) VALUES ($1, $2, $3, $4, $5)", &[&r.id, &r.entity_id, &r.event_type, &r.happened_at, &r.details_json]).map_err(pg_err)?;
        Ok(())
    }
}

fn insert_payment_event(c: &mut impl GenericClient, r: &PaymentEventRecord) -> Result<(), StoreError> {
    let provider = payment_provider_to_str(&r.provider);
    let status = payment_status_to_str(&r.status);
    let amount = amount_to_i64(r.amount_rub)?;
    let provider_ref = r.provider_payment_id.as_deref();
    c.execute("INSERT INTO billing_events (id, order_id, provider, provider_event_id, provider_reference_id, status, amount_rub, received_at) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)", &[&r.id, &r.order_id, &provider, &r.provider_event_id, &provider_ref, &status, &amount, &r.received_at]).map_err(pg_err)?;
    Ok(())
}

fn order_from_row(row: Row) -> Result<OrderRecord, StoreError> {
    let amount: i64 = row.get("amount_rub");
    let status: String = row.get("status");
    Ok(OrderRecord { id: row.get("id"), plan: row.get("plan"), amount_rub: amount_from_i64(amount)?, status: order_status_from_str(&status)?, machine_hash: row.get("machine_hash"), created_at: row.get("created_at") })
}

fn amount_to_i64(amount: u64) -> Result<i64, StoreError> { i64::try_from(amount).map_err(|_| StoreError::Invalid("amount_overflow".to_string())) }
fn amount_from_i64(amount: i64) -> Result<u64, StoreError> { u64::try_from(amount).map_err(|_| StoreError::Invalid("amount_negative".to_string())) }

fn order_status_to_str(status: &OrderStatus) -> &'static str {
    match status { OrderStatus::Draft => "draft", OrderStatus::WaitingPayment => "waiting_payment", OrderStatus::Paid => "paid", OrderStatus::LicenseIssued => "license_issued", OrderStatus::Cancelled => "cancelled" }
}

fn order_status_from_str(value: &str) -> Result<OrderStatus, StoreError> {
    match value { "draft" => Ok(OrderStatus::Draft), "waiting_payment" => Ok(OrderStatus::WaitingPayment), "paid" => Ok(OrderStatus::Paid), "license_issued" => Ok(OrderStatus::LicenseIssued), "cancelled" => Ok(OrderStatus::Cancelled), other => Err(StoreError::Invalid(format!("unknown_order_status:{other}"))) }
}

fn payment_provider_to_str(provider: &PaymentProvider) -> &'static str {
    match provider { PaymentProvider::Manual => "manual", PaymentProvider::YooKassa => "yookassa", PaymentProvider::Sbp => "sbp", PaymentProvider::BankInvoice => "bank_invoice" }
}

fn payment_status_to_str(status: &PaymentEventStatus) -> &'static str {
    match status { PaymentEventStatus::Pending => "pending", PaymentEventStatus::Succeeded => "succeeded", PaymentEventStatus::Cancelled => "cancelled", PaymentEventStatus::Rejected => "rejected" }
}

fn pg_err(error: postgres::Error) -> StoreError {
    if let Some(db) = error.as_db_error() {
        if db.code() == &SqlState::UNIQUE_VIOLATION { return StoreError::Conflict; }
        if db.code() == &SqlState::FOREIGN_KEY_VIOLATION { return StoreError::NotFound; }
    }
    StoreError::Invalid(error.to_string())
}

pub const SCHEMA_V1: &str = include_str!("../migrations/0001_license_schema.sql");

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn postgres_store_roundtrip_when_database_url_is_present() {
        let Ok(url) = std::env::var("DATABASE_URL") else { return; };
        let store = PostgresStore::connect(&url).unwrap();
        let order_id = Uuid::new_v4();
        store.create_order(OrderRecord { id: order_id, plan: "doctor_pro".to_string(), amount_rub: 3900, status: OrderStatus::WaitingPayment, machine_hash: None, created_at: OffsetDateTime::now_utc() }).unwrap();
        assert!(matches!(store.get_order(order_id).unwrap().unwrap().status, OrderStatus::WaitingPayment));
        store.record_payment_event_for_order(PaymentEventRecord { id: Uuid::new_v4(), order_id, provider: PaymentProvider::Manual, provider_event_id: format!("evt-{order_id}"), provider_payment_id: None, status: PaymentEventStatus::Succeeded, amount_rub: 3900, received_at: OffsetDateTime::now_utc() }).unwrap();
        assert!(matches!(store.get_order(order_id).unwrap().unwrap().status, OrderStatus::Paid));
    }
}
