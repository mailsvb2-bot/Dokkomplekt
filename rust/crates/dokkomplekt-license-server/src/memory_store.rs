use crate::state::{ActivationRecord, MemoryStore, OrderRecord, OrderStatus};
use crate::storage::{AuditEventRecord, LicenseRecord, LicenseStore, PaymentEventRecord, StoreError};
use std::sync::{Arc, RwLock};
use uuid::Uuid;

impl LicenseStore for Arc<RwLock<MemoryStore>> {
    fn create_order(&self, record: OrderRecord) -> Result<(), StoreError> {
        create_order(self, record)
    }

    fn get_order(&self, order_id: Uuid) -> Result<Option<OrderRecord>, StoreError> {
        get_order(self, order_id)
    }

    fn update_order_status(&self, order_id: Uuid, status: OrderStatus) -> Result<(), StoreError> {
        update_order_status(self, order_id, status)
    }

    fn create_activation(&self, record: ActivationRecord) -> Result<(), StoreError> {
        create_activation(self, record)
    }

    fn record_payment_event(&self, record: PaymentEventRecord) -> Result<(), StoreError> {
        record_payment_event(self, record)
    }

    fn store_license(&self, record: LicenseRecord) -> Result<(), StoreError> {
        store_license(self, record)
    }

    fn audit(&self, record: AuditEventRecord) -> Result<(), StoreError> {
        audit(self, record)
    }
}
