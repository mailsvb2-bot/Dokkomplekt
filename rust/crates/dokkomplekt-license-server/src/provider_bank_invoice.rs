use crate::providers::{
    CreatePaymentRequest, CreatePaymentResponse, PaymentProvider, ProviderError, ProviderEvent,
    ProviderKind,
};

#[derive(Debug, Clone)]
pub struct BankInvoiceProvider {
    pub public_base_url: String,
    pub recipient: String,
    pub inn: String,
    pub kpp: Option<String>,
    pub account: String,
    pub bank_name: String,
    pub bic: String,
    pub correspondent_account: String,
}

impl BankInvoiceProvider {
    pub fn from_env(public_base_url: &str) -> Result<Self, ProviderError> {
        Ok(Self {
            public_base_url: public_base_url.trim_end_matches('/').to_string(),
            recipient: required_env("DOKKOMPLEKT_BANK_INVOICE_RECIPIENT")?,
            inn: required_env("DOKKOMPLEKT_BANK_INVOICE_INN")?,
            kpp: optional_env("DOKKOMPLEKT_BANK_INVOICE_KPP"),
            account: required_env("DOKKOMPLEKT_BANK_INVOICE_ACCOUNT")?,
            bank_name: required_env("DOKKOMPLEKT_BANK_INVOICE_BANK_NAME")?,
            bic: required_env("DOKKOMPLEKT_BANK_INVOICE_BIC")?,
            correspondent_account: required_env(
                "DOKKOMPLEKT_BANK_INVOICE_CORRESPONDENT_ACCOUNT",
            )?,
        })
    }

    pub fn validate_env() -> Result<(), ProviderError> {
        Self::from_env("https://example.invalid").map(|_| ())
    }

    pub fn payment_purpose(&self, order_id: uuid::Uuid) -> String {
        format!("Оплата лицензии Dokkomplekt. Заказ {order_id}. Без НДС")
    }
}

impl PaymentProvider for BankInvoiceProvider {
    fn create_payment(
        &self,
        request: CreatePaymentRequest,
    ) -> Result<CreatePaymentResponse, ProviderError> {
        if request.amount_rub == 0 {
            return Err(ProviderError::BadRequest(
                "bank invoice amount must be positive".to_string(),
            ));
        }
        Ok(CreatePaymentResponse {
            provider: ProviderKind::BankInvoice,
            provider_payment_id: format!("bank-invoice:{}", request.order_id),
            confirmation_url: format!(
                "{}/api/orders/{}/bank-invoice",
                self.public_base_url, request.order_id
            ),
            qr_url: None,
        })
    }

    fn parse_callback(&self, _raw_body: &[u8]) -> Result<ProviderEvent, ProviderError> {
        Err(ProviderError::Unsupported)
    }
}

fn required_env(name: &str) -> Result<String, ProviderError> {
    optional_env(name).ok_or_else(|| {
        ProviderError::BadRequest(format!("{name} is required for bank_invoice payments"))
    })
}

fn optional_env(name: &str) -> Option<String> {
    std::env::var(name)
        .ok()
        .map(|value| value.trim().to_string())
        .filter(|value| !value.is_empty())
}

#[cfg(test)]
mod tests {
    use super::*;
    use uuid::Uuid;

    #[test]
    fn invoice_payment_url_is_order_scoped() {
        let provider = BankInvoiceProvider {
            public_base_url: "https://lic.example".to_string(),
            recipient: "ООО Доккомплект".to_string(),
            inn: "5250000000".to_string(),
            kpp: Some("525001001".to_string()),
            account: "40702810000000000000".to_string(),
            bank_name: "Тест Банк".to_string(),
            bic: "042202000".to_string(),
            correspondent_account: "30101810000000000000".to_string(),
        };
        let order_id = Uuid::nil();
        let response = provider
            .create_payment(CreatePaymentRequest {
                order_id,
                amount_rub: 3_900,
                description: "Dokkomplekt".to_string(),
                return_url: None,
            })
            .unwrap();
        assert_eq!(response.provider, ProviderKind::BankInvoice);
        assert_eq!(
            response.confirmation_url,
            "https://lic.example/api/orders/00000000-0000-0000-0000-000000000000/bank-invoice"
        );
        assert!(provider.payment_purpose(order_id).contains(&order_id.to_string()));
    }
}
