use crate::state::{ActivationRecord, MemoryStore, OrderRecord, OrderStatus};
use crate::storage::{
    AuditEventRecord, LicenseRecord, LicenseStore, PaymentEventRecord, PaymentEventStatus,
    PaymentEventWriteOutcome, PaymentProvider, StoreError,
};
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

    fn create_activation_for_order(&self, record: ActivationRecord, max_machines: u32) -> Result<OrderRecord, StoreError> {
        let mut store = self.write().map_err(|_| StoreError::Poisoned)?;
        if store.activations.contains_key(&record.id) {
            return Err(StoreError::Conflict);
        }
        let order = store.orders.get(&record.order_id).ok_or(StoreError::NotFound)?.clone();
        if !matches!(order.status, OrderStatus::Paid | OrderStatus::LicenseIssued) {
            return Err(StoreError::Conflict);
        }
        let active_count = store
            .activations
            .values()
            .filter(|activation| activation.order_id == record.order_id)
            .count() as u32;
        if active_count >= max_machines {
            return Err(StoreError::Conflict);
        }
        store.activations.insert(record.id, record);
        Ok(order)
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

    fn record_payment_event_for_order(&self, record: PaymentEventRecord) -> Result<PaymentEventWriteOutcome, StoreError> {
        let mut store = self.write().map_err(|_| StoreError::Poisoned)?;
        if store.payment_events.values().any(|existing| {
            same_provider(&existing.provider, &record.provider)
                && existing.provider_event_id == record.provider_event_id
        }) {
            return Ok(PaymentEventWriteOutcome::Duplicate);
        }
        let order = store.orders.get_mut(&record.order_id).ok_or(StoreError::NotFound)?;
        if order.amount_rub != record.amount_rub {
            return Err(StoreError::Invalid("amount_mismatch".to_string()));
        }
        if matches!(record.status, PaymentEventStatus::Succeeded) {
            order.status = OrderStatus::Paid;
        }
        store.payment_events.insert(record.id, record);
        Ok(PaymentEventWriteOutcome::Recorded)
    }

    fn store_license(&self, record: LicenseRecord) -> Result<(), StoreError> {
        let mut store = self.write().map_err(|_| StoreError::Poisoned)?;
        if store.licenses.contains_key(&record.id)
            || store.licenses.values().any(|existing| existing.license_id == record.license_id)
        {
            return Err(StoreError::Conflict);
        }
        store.licenses.insert(record.id, record);
        Ok(())
    }

    fn audit(&self, record: AuditEventRecord) -> Result<(), StoreError> {
        let mut store = self.write().map_err(|_| StoreError::Poisoned)?;
        if store.audit_events.contains_key(&record.id) {
            return Err(StoreError::Conflict);
        }
        store.audit_events.insert(record.id, record);
        Ok(())
    }
}

fn same_provider(left: &PaymentProvider, right: &PaymentProvider) -> bool {
    discriminant(left) == discriminant(right)
}

#[cfg(test)]
mod tests {
    use super::*;
    use time::OffsetDateTime;

    fn memory_store() -> Arc<RwLock<MemoryStore>> {
        Arc::new(RwLock::new(MemoryStore::default()))
    }

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

    #[test]
    fn provider_callback_store_method_marks_order_paid_and_deduplicates() {
        let store = memory_store();
        let order_id = Uuid::new_v4();
        store.create_order(order_record(order_id, OrderStatus::WaitingPayment)).unwrap();

        let record = PaymentEventRecord {
            id: Uuid::new_v4(),
            order_id,
            provider: PaymentProvider::Manual,
            provider_event_id: "evt-1".to_string(),
            provider_payment_id: Some("pay-1".to_string()),
            status: PaymentEventStatus::Succeeded,
            amount_rub: 3900,
            received_at: OffsetDateTime::now_utc(),
        };

        assert_eq!(
            store.record_payment_event_for_order(record.clone()).unwrap(),
            PaymentEventWriteOutcome::Recorded,
        );
        assert!(matches!(store.get_order(order_id).unwrap().unwrap().status, OrderStatus::Paid));

        let duplicate = PaymentEventRecord { id: Uuid::new_v4(), ..record };
        assert_eq!(
            store.record_payment_event_for_order(duplicate).unwrap(),
            PaymentEventWriteOutcome::Duplicate,
        );
    }

    #[test]
    fn activation_store_method_checks_paid_order_and_slot_capacity_under_one_write_lock() {
        let store = memory_store();
        let order_id = Uuid::new_v4();
        store.create_order(order_record(order_id, OrderStatus::Paid)).unwrap();

        let first = ActivationRecord {
            id: Uuid::new_v4(),
            order_id,
            machine_hash: "machine-a".to_string(),
            created_at: OffsetDateTime::now_utc(),
        };
        store.create_activation_for_order(first, 1).unwrap();

        let second = ActivationRecord {
            id: Uuid::new_v4(),
            order_id,
            machine_hash: "machine-b".to_string(),
            created_at: OffsetDateTime::now_utc(),
        };
        assert_eq!(store.create_activation_for_order(second, 1).unwrap_err(), StoreError::Conflict);
    }
}
