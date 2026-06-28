use super::{
    AuditEventRecord, LicenseRecord, LicenseStore, PaymentEventRecord, PaymentEventStatus,
    PaymentEventWriteOutcome, StoreError,
};
use crate::state::{ActivationRecord, OrderRecord, OrderStatus};
use postgres::error::SqlState;
use postgres::{Client, GenericClient, NoTls, Row};
use std::sync::{Arc, Mutex};
use uuid::Uuid;

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
        let amount = amount_to_i64(record.amount_rub)?;
        let status = order_status_to_str(&record.status);
        let machine_hash = record.machine_hash.as_deref();
        client.execute(
            "INSERT INTO license_orders (id, plan, amount_rub, status, machine_hash, created_at) VALUES ($1, $2, $3, $4, $5, $6)",
            &[&record.id, &record.plan, &amount, &status, &machine_hash, &record.created_at],
        ).map_err(pg_err)?;
        Ok(())
    }

    fn get_order(&self, order_id: Uuid) -> Result<Option<OrderRecord>, StoreError> {
        let mut client = self.client()?;
        client.query_opt(
            "SELECT id, plan, amount_rub, status, machine_hash, created_at FROM license_orders WHERE id = $1",
            &[&order_id],
        ).map_err(pg_err)?.map(order_from_row).transpose()
    }

    fn update_order_status(&self, order_id: Uuid, status: OrderStatus) -> Result<(), StoreError> {
        let mut client = self.client()?;
        let status = order_status_to_str(&status);
        let changed = client.execute(
            "UPDATE license_orders SET status = $2 WHERE id = $1",
            &[&order_id, &status],
        ).map_err(pg_err)?;
        if changed == 0 { Err(StoreError::NotFound) } else { Ok(()) }
    }

    fn create_activation(&self, record: ActivationRecord) -> Result<(), StoreError> {
        let mut client = self.client()?;
        client.execute(
            "INSERT INTO license_machines (id, order_id, machine_hash, created_at) VALUES ($1, $2, $3, $4)",
            &[&record.id, &record.order_id, &record.machine_hash, &record.created_at],
        ).map_err(pg_err)?;
        Ok(())
    }

    fn create_activation_for_order(&self, record: ActivationRecord, max_machines: u32) -> Result<OrderRecord, StoreError> {
        let mut client = self.client()?;
        let mut tx = client.transaction().map_err(pg_err)?;
        let row = tx.query_opt(
            "SELECT id, plan, amount_rub, status, machine_hash, created_at FROM license_orders WHERE id = $1 FOR UPDATE",
            &[&record.order_id],
        ).map_err(pg_err)?.ok_or(StoreError::NotFound)?;
        let order = order_from_row(row)?;
        if !matches!(order.status, OrderStatus::Paid | OrderStatus::LicenseIssued) {
            return Err(StoreError::Conflict);
        }
        let active_count: i64 = tx.query_one(
            "SELECT COUNT(*) FROM license_machines WHERE order_id = $1",
            &[&record.order_id],
        ).map_err(pg_err)?.get(0);
        if active_count < 0 || active_count as u32 >= max_machines {
            return Err(StoreError::Conflict);
        }
        tx.execute(
            "INSERT INTO license_machines (id, order_id, machine_hash, created_at) VALUES ($1, $2, $3, $4)",
            &[&record.id, &record.order_id, &record.machine_hash, &record.created_at],
        ).map_err(pg_err)?;
        tx.commit().map_err(pg_err)?;
        Ok(order)
    }

    fn record_payment_event(&self, record: PaymentEventRecord) -> Result<(), StoreError> {
        let mut client = self.client()?;
        insert_payment_event(&mut *client, &record)
    }

    fn record_payment_event_for_order(&self, record: PaymentEventRecord) -> Result<PaymentEventWriteOutcome, StoreError> {
        let mut client = self.client()?;
        let mut tx = client.transaction().map_err(pg_err)?;
        let provider = payment_provider_to_str(&record.provider);
        if tx.query_opt(
            "SELECT id FROM billing_events WHERE provider = $1 AND provider_event_id = $2",
            &[&provider, &record.provider_event_id],
        ).map_err(pg_err)?.is_some() {
            return Ok(PaymentEventWriteOutcome::Duplicate);
        }
        let row = tx.query_opt(
            "SELECT id, plan, amount_rub, status, machine_hash, created_at FROM license_orders WHERE id = $1 FOR UPDATE",
            &[&record.order_id],
        ).map_err(pg_err)?.ok_or(StoreError::NotFound)?;
        let order = order_from_row(row)?;
        if order.amount_rub != record.amount_rub {
            return Err(StoreError::Invalid("amount_mismatch".to_string()));
        }
        if matches!(record.status, PaymentEventStatus::Succeeded) {
            let paid = order_status_to_str(&OrderStatus::Paid);
            tx.execute("UPDATE license_orders SET status = $2 WHERE id = $1", &[&record.order_id, &paid]).map_err(pg_err)?;
        }
        insert_payment_event(&mut tx, &record)?;
        tx.commit().map_err(pg_err)?;
        Ok(PaymentEventWriteOutcome::Recorded)
    }

    fn store_license(&self, record: LicenseRecord) -> Result<(), StoreError> {
        let mut client = self.client()?;
        client.execute(
            "INSERT INTO license_documents (id, order_id, license_id, document_json, issued_at, revoked_at) VALUES ($1, $2, $3, $4, $5, $6)",
            &[&record.id, &record.order_id, &record.license_id, &record.document_json, &record.issued_at, &record.revoked_at],
        ).map_err(pg_err)?;
        Ok(())
    }

    fn audit(&self, record: AuditEventRecord) -> Result<(), StoreError> {
        let mut client = self.client()?;
        client.execute(
            "INSERT INTO license_audit_events (id, entity_id, event_type, happened_at, details_json) VALUES ($1, $2, $3, $4, $5)",
            &[&record.id, &record.entity_id, &record.event_type, &record.happened_at, &record.details_json],
        ).map_err(pg_err)?;
        Ok(())
    }
}

fn insert_payment_event(client: &mut impl GenericClient, record: &PaymentEventRecord) -> Result<(), StoreError> {
    let provider = payment_provider_to_str(&record.provider);
    let status = payment_status_to_str(&record.status);
    let amount = amount_to_i64(record.amount_rub)?;
    let provider_ref = record.provider_payment_id.as_deref();
    client.execute(
        "INSERT INTO billing_events (id, order_id, provider, provider_event_id, provider_reference_id, status, amount_rub, received_at) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)",
        &[&record.id, &record.order_id, &provider, &record.provider_event_id, &provider_ref, &status, &amount, &record.received_at],
    ).map_err(pg_err)?;
    Ok(())
}

fn order_from_row(row: Row) -> Result<OrderRecord, StoreError> {
    let amount: i64 = row.get("amount_rub");
    let status: String = row.get("status");
    Ok(OrderRecord {
        id: row.get("id"),
        plan: row.get("plan"),
        amount_rub: amount_from_i64(amount)?,
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

fn payment_provider_to_str(provider: &super::PaymentProvider) -> &'static str {
    match provider {
        super::PaymentProvider::Manual => "manual",
        super::PaymentProvider::YooKassa => "yookassa",
        super::PaymentProvider::Sbp => "sbp",
        super::PaymentProvider::BankInvoice => "bank_invoice",
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

fn pg_err(error: postgres::Error) -> StoreError {
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

const SCHEMA_V1: &str = include_str!("../../migrations/0001_license_schema.sql");
