use crate::provider_bank_invoice::BankInvoiceProvider;
use crate::provider_yookassa::YooKassaProvider;
use crate::providers::{CreatePaymentRequest, PaymentProvider, ProviderError};
use crate::state::{AppState, OrderRecord, OrderStatus};
use crate::storage::StoreError;
use axum::{
    extract::{Path, State},
    http::StatusCode,
    routing::{get, post},
    Json, Router,
};
use serde::{Deserialize, Serialize};
use time::OffsetDateTime;
use uuid::Uuid;

#[derive(Debug, Deserialize)]
pub struct CreateOrderRequest {
    pub plan: String,
    pub amount_rub: Option<u64>,
    pub machine_hash: Option<String>,
}

#[derive(Debug, Serialize)]
pub struct CreateOrderResponse {
    pub order_id: Uuid,
    pub status: OrderStatus,
    pub provider: String,
    pub amount_rub: u64,
    pub payment_ready: bool,
    pub payment_url: String,
    pub qr_url: String,
}

#[derive(Debug, Serialize)]
pub struct PaymentRetryResponse {
    pub order_id: Uuid,
    pub provider: String,
    pub payment_url: String,
    pub qr_url: String,
}

#[derive(Debug, Serialize)]
pub struct BankInvoiceResponse {
    pub order_id: Uuid,
    pub amount_rub: u64,
    pub currency: &'static str,
    pub recipient: String,
    pub inn: String,
    pub kpp: Option<String>,
    pub account: String,
    pub bank_name: String,
    pub bic: String,
    pub correspondent_account: String,
    pub payment_purpose: String,
}

pub fn router() -> Router<AppState> {
    Router::new()
        .route("/api/orders", post(create_order))
        .route("/api/orders/:order_id/payment", post(retry_payment))
        .route("/api/orders/:order_id/bank-invoice", get(bank_invoice))
}

async fn create_order(
    State(state): State<AppState>,
    Json(request): Json<CreateOrderRequest>,
) -> Result<Json<CreateOrderResponse>, StatusCode> {
    let plan = normalize_order_plan(&request.plan).ok_or(StatusCode::BAD_REQUEST)?;
    let amount_rub = tariff_amount_rub(plan).ok_or(StatusCode::BAD_REQUEST)?;
    if matches!(request.amount_rub, Some(client_amount) if client_amount != amount_rub) {
        return Err(StatusCode::BAD_REQUEST);
    }
    let machine_hash = request
        .machine_hash
        .as_deref()
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .map(str::to_string)
        .ok_or(StatusCode::BAD_REQUEST)?;
    let order_id = Uuid::new_v4();
    let record = OrderRecord {
        id: order_id,
        plan: plan.to_string(),
        amount_rub,
        status: OrderStatus::WaitingPayment,
        machine_hash: Some(machine_hash),
        created_at: OffsetDateTime::now_utc(),
    };
    state
        .store
        .create_order_async(record.clone())
        .await
        .map_err(store_error_status)?;
    let provider = state.config.payment_provider.clone();

    // Persist the order before talking to the external provider. If the provider
    // times out after accepting the request, the caller still receives order_id
    // and can safely retry /payment. YooKassa sees the same idempotence key and
    // returns the same payment instead of creating a second one.
    let (payment_ready, payment) = match create_payment_for_order(&state, &record).await {
        Ok(payment) => (true, payment),
        Err(_) if provider != "manual" => (false, PaymentLinks::empty()),
        Err(status) => return Err(status),
    };

    Ok(Json(CreateOrderResponse {
        order_id,
        status: record.status,
        provider,
        amount_rub,
        payment_ready,
        payment_url: payment.payment_url,
        qr_url: payment.qr_url,
    }))
}

async fn retry_payment(
    State(state): State<AppState>,
    Path(order_id): Path<Uuid>,
) -> Result<Json<PaymentRetryResponse>, StatusCode> {
    let order = state
        .store
        .get_order_async(order_id)
        .await
        .map_err(store_error_status)?
        .ok_or(StatusCode::NOT_FOUND)?;
    if !matches!(order.status, OrderStatus::WaitingPayment) {
        return Err(StatusCode::CONFLICT);
    }
    let provider = state.config.payment_provider.clone();
    let payment = create_payment_for_order(&state, &order).await?;
    Ok(Json(PaymentRetryResponse {
        order_id,
        provider,
        payment_url: payment.payment_url,
        qr_url: payment.qr_url,
    }))
}

async fn bank_invoice(
    State(state): State<AppState>,
    Path(order_id): Path<Uuid>,
) -> Result<Json<BankInvoiceResponse>, StatusCode> {
    if state.config.payment_provider != "bank_invoice" {
        return Err(StatusCode::NOT_FOUND);
    }
    let order = state
        .store
        .get_order_async(order_id)
        .await
        .map_err(store_error_status)?
        .ok_or(StatusCode::NOT_FOUND)?;
    if !matches!(order.status, OrderStatus::WaitingPayment) {
        return Err(StatusCode::CONFLICT);
    }
    let provider = BankInvoiceProvider::from_env(&state.config.public_base_url)
        .map_err(provider_error_status)?;
    Ok(Json(BankInvoiceResponse {
        order_id,
        amount_rub: order.amount_rub,
        currency: "RUB",
        recipient: provider.recipient.clone(),
        inn: provider.inn.clone(),
        kpp: provider.kpp.clone(),
        account: provider.account.clone(),
        bank_name: provider.bank_name.clone(),
        bic: provider.bic.clone(),
        correspondent_account: provider.correspondent_account.clone(),
        payment_purpose: provider.payment_purpose(order_id),
    }))
}

struct PaymentLinks {
    payment_url: String,
    qr_url: String,
}

impl PaymentLinks {
    fn empty() -> Self {
        Self {
            payment_url: String::new(),
            qr_url: String::new(),
        }
    }
}

async fn create_payment_for_order(
    state: &AppState,
    order: &OrderRecord,
) -> Result<PaymentLinks, StatusCode> {
    match state.config.payment_provider.as_str() {
        "manual" => Ok(PaymentLinks {
            payment_url: payment_url_for(&state.config.public_base_url, "manual", order.id),
            qr_url: String::new(),
        }),
        "yookassa" | "sbp" => {
            let provider = YooKassaProvider::from_env(state.config.payment_provider == "sbp")
                .map_err(provider_error_status)?;
            let return_url = format!(
                "{}/api/orders/{}/status",
                state.config.public_base_url.trim_end_matches('/'),
                order.id
            );
            let request = CreatePaymentRequest {
                order_id: order.id,
                amount_rub: order.amount_rub,
                description: format!("Dokkomplekt: {}", order.plan),
                return_url: Some(return_url),
            };
            let response = tokio::task::spawn_blocking(move || provider.create_payment(request))
                .await
                .map_err(|_| StatusCode::INTERNAL_SERVER_ERROR)?
                .map_err(provider_error_status)?;
            Ok(PaymentLinks {
                payment_url: response.confirmation_url,
                qr_url: response.qr_url.unwrap_or_default(),
            })
        }
        "bank_invoice" => {
            let provider = BankInvoiceProvider::from_env(&state.config.public_base_url)
                .map_err(provider_error_status)?;
            let request = CreatePaymentRequest {
                order_id: order.id,
                amount_rub: order.amount_rub,
                description: format!("Dokkomplekt: {}", order.plan),
                return_url: None,
            };
            let response = provider.create_payment(request).map_err(provider_error_status)?;
            Ok(PaymentLinks {
                payment_url: response.confirmation_url,
                qr_url: response.qr_url.unwrap_or_default(),
            })
        }
        _ => Err(StatusCode::SERVICE_UNAVAILABLE),
    }
}

fn provider_error_status(error: ProviderError) -> StatusCode {
    match error {
        ProviderError::BadRequest(_) => StatusCode::SERVICE_UNAVAILABLE,
        ProviderError::BadSignature => StatusCode::BAD_GATEWAY,
        ProviderError::Transport(_) => StatusCode::BAD_GATEWAY,
        ProviderError::Unsupported => StatusCode::NOT_IMPLEMENTED,
    }
}

fn store_error_status(error: StoreError) -> StatusCode {
    match error {
        StoreError::Conflict => StatusCode::CONFLICT,
        StoreError::Invalid(_) => StatusCode::BAD_REQUEST,
        StoreError::NotFound => StatusCode::NOT_FOUND,
        StoreError::Poisoned => StatusCode::INTERNAL_SERVER_ERROR,
    }
}

pub fn normalize_order_plan(value: &str) -> Option<&'static str> {
    match value.trim().to_ascii_lowercase().as_str() {
        "doctor_start" => Some("doctor_start"),
        "doctor_pro" => Some("doctor_pro"),
        "department" => Some("department"),
        "clinic" => Some("clinic"),
        "enterprise" => Some("enterprise"),
        "trial" => None,
        _ => None,
    }
}

pub fn tariff_amount_rub(plan: &str) -> Option<u64> {
    match plan {
        "doctor_start" => Some(1_490),
        "doctor_pro" => Some(3_900),
        "department" => Some(14_900),
        "clinic" => Some(49_000),
        "enterprise" => Some(900_000),
        _ => None,
    }
}

pub fn payment_url_for(base_url: &str, provider: &str, order_id: Uuid) -> String {
    format!(
        "{}/pay/{}/{}",
        base_url.trim_end_matches('/'),
        provider,
        order_id
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn manual_payment_url_uses_local_provider_namespace() {
        let order_id = Uuid::nil();
        assert_eq!(
            payment_url_for("https://lic.example/", "manual", order_id),
            "https://lic.example/pay/manual/00000000-0000-0000-0000-000000000000",
        );
    }

    #[test]
    fn order_tariffs_are_server_side_only() {
        assert_eq!(normalize_order_plan(" Doctor_Pro "), Some("doctor_pro"));
        assert_eq!(tariff_amount_rub("doctor_pro"), Some(3_900));
        assert_eq!(tariff_amount_rub("clinic"), Some(49_000));
        assert!(normalize_order_plan("trial").is_none());
        assert!(normalize_order_plan("unknown").is_none());
    }

    #[test]
    fn failed_external_payment_can_return_a_retryable_order() {
        let payment = PaymentLinks::empty();
        assert!(payment.payment_url.is_empty());
        assert!(payment.qr_url.is_empty());
    }
}
