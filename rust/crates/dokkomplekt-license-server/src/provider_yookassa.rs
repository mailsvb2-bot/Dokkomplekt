#![allow(dead_code)]

use crate::providers::{
    CreatePaymentRequest, CreatePaymentResponse, PaymentProvider, ProviderError, ProviderEvent,
};

#[derive(Debug, Clone)]
pub struct YooKassaProvider {
    pub public_base_url: String,
}

impl PaymentProvider for YooKassaProvider {
    fn create_payment(&self, _request: CreatePaymentRequest) -> Result<CreatePaymentResponse, ProviderError> {
        Err(ProviderError::Unsupported)
    }

    fn parse_callback(&self, _raw_body: &[u8]) -> Result<ProviderEvent, ProviderError> {
        Err(ProviderError::Unsupported)
    }
}
