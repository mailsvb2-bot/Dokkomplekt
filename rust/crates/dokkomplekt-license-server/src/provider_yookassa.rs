#![allow(dead_code)]

use crate::providers::{
    CreatePaymentRequest, CreatePaymentResponse, PaymentProvider, ProviderError, ProviderEvent,
    ProviderKind,
};

#[derive(Debug, Clone)]
pub struct YooKassaProvider {
    pub public_base_url: String,
}

impl PaymentProvider for YooKassaProvider {
    fn create_payment(&self, request: CreatePaymentRequest) -> Result<CreatePaymentResponse, ProviderError> {
        let provider_payment_id = format!("yookassa-{}", request.order_id);
        Ok(CreatePaymentResponse {
            provider: ProviderKind::YooKassa,
            provider_payment_id,
            confirmation_url: format!("{}/pay/yookassa/{}", self.public_base_url, request.order_id),
            qr_url: None,
        })
    }

    fn parse_callback(&self, raw_body: &[u8]) -> Result<ProviderEvent, ProviderError> {
        serde_json::from_slice::<ProviderEvent>(raw_body)
            .map_err(|err| ProviderError::BadRequest(err.to_string()))
    }
}
