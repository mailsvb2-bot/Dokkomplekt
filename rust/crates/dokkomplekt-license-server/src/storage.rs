#![allow(dead_code)]

use crate::state::{ActivationRecord, OrderRecord, OrderStatus};
use serde::{Deserialize, Serialize};
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
