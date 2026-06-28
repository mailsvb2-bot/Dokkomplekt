use crate::storage::PaymentProvider;

pub fn generic_callback_accepts(provider: &PaymentProvider) -> bool {
    matches!(provider, PaymentProvider::Manual)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn generic_callback_accepts_manual_only() {
        assert!(generic_callback_accepts(&PaymentProvider::Manual));
        assert!(!generic_callback_accepts(&PaymentProvider::YooKassa));
        assert!(!generic_callback_accepts(&PaymentProvider::Sbp));
        assert!(!generic_callback_accepts(&PaymentProvider::BankInvoice));
    }
}
