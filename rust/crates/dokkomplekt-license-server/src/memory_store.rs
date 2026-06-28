use crate::state::{ActivationRecord, MemoryStore, OrderRecord, OrderStatus};
use crate::storage::{AuditEventRecord, LicenseRecord, LicenseStore, PaymentEventRecord, PaymentProvider, StoreError};
use std::mem::discriminant;
use std::sync::{Arc, RwLock};
use uuid::Uuid;

impl LicenseStore for Arc<RwLock<MemoryStore>> {
    fn create_order(&self, record: OrderRecord) -> Result<(), StoreError> {
        let mut store = self.write().map_err(|_| StoreError::Poisoned)?;
        if store.orders.contains_key(&record.id) {
            return Err(StoreError::Conflict);
        }
        store.orders.insert(record.id, record);
        Ok(())
    }

    fn get_order(&self, order_id: Uuid) -> Result<Option<OrderRecord>, StoreError> {
        let store = self.read().map_err(|_| StoreError::Poisoned)?;
        Ok(store.orders.get(&order_id).cloned())
    }

    fn update_order_status(&self, order_id: Uuid, status: OrderStatus) -> Result<(), StoreError> {
        let mut store = self.write().map_err(|_| StoreError::Poisoned)?;
        let order = store.orders.get_mut(&order_id).ok_or(StoreError::NotFound)?;
        order.status = status;
        Ok(())
    }

    fn create_activation(&self, record: ActivationRecord) -> Result<(), StoreError> {
        let mut store = self.write().map_err(|_| StoreError::Poisoned)?;
        if store.activations.contains_key(&record.id) {
            return Err(StoreError::Conflict);
        }
        store.activations.insert(record.id, record);
        Ok(())
    }

    fn record_payment_event(&self, record: PaymentEventRecord) -> Result<(), StoreError> {
        let mut store = self.write().map_err(|_| StoreError::Poisoned)?;
        if store.payment_events.values().any(|existing| {
            same_provider(&existing.provider, &record.provider)
                && existing.provider_event_id == record.provider_event_id
        }) {
            return Err(StoreError::Conflict);
        }
        store.payment_events.insert(record.id, record);
        Ok(())
    }

    fn store_license(&self, _record: LicenseRecord) -> Result<(), StoreError> {
        Ok(())
    }

    fn audit(&self, _record: AuditEventRecord) -> Result<(), StoreError> {
        Ok(())
    }
}

fn same_provider(left: &PaymentProvider, right: &PaymentProvider) -> bool {
    discriminant(left) == discriminant(right)
}
