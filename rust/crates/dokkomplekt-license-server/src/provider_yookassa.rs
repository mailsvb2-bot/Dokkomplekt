use crate::providers::{
    CreatePaymentRequest, CreatePaymentResponse, PaymentProvider, ProviderError, ProviderEvent,
    ProviderKind, ProviderPaymentStatus,
};
use reqwest::blocking::Client;
use serde_json::{json, Value};
use std::time::Duration;
use uuid::Uuid;

const REQUEST_TIMEOUT_SECONDS: u64 = 20;

#[derive(Debug, Clone)]
pub struct YooKassaProvider {
    shop_id: String,
    secret_key: String,
    api_base_url: String,
    sbp_only: bool,
}

impl YooKassaProvider {
    pub fn from_env(sbp_only: bool) -> Result<Self, ProviderError> {
        let shop_id = required_env("DOKKOMPLEKT_YOOKASSA_SHOP_ID")?;
        let secret_key = required_env("DOKKOMPLEKT_YOOKASSA_SECRET_KEY")?;
        let api_base_url = std::env::var("DOKKOMPLEKT_YOOKASSA_API_BASE_URL")
            .ok()
            .map(|value| value.trim().trim_end_matches('/').to_string())
            .filter(|value| !value.is_empty())
            .unwrap_or_else(|| "https://api.yookassa.ru/v3".to_string());
        Ok(Self {
            shop_id,
            secret_key,
            api_base_url,
            sbp_only,
        })
    }

    fn client(&self) -> Result<Client, ProviderError> {
        Client::builder()
            .timeout(Duration::from_secs(REQUEST_TIMEOUT_SECONDS))
            .build()
            .map_err(|error| {
                ProviderError::Transport(format!(
                    "failed to build YooKassa HTTP client: {error}"
                ))
            })
    }

    fn fetch_payment(&self, payment_id: &str) -> Result<Value, ProviderError> {
        let payment_id = payment_id.trim();
        if payment_id.is_empty() {
            return Err(ProviderError::BadRequest(
                "YooKassa payment id is empty".to_string(),
            ));
        }
        let response = self
            .client()?
            .get(format!("{}/payments/{payment_id}", self.api_base_url))
            .basic_auth(&self.shop_id, Some(&self.secret_key))
            .send()
            .map_err(|error| {
                ProviderError::Transport(format!("YooKassa payment lookup failed: {error}"))
            })?;
        parse_json_response(response, "YooKassa payment lookup")
    }

    fn provider_kind(&self) -> ProviderKind {
        if self.sbp_only {
            ProviderKind::Sbp
        } else {
            ProviderKind::YooKassa
        }
    }
}

impl PaymentProvider for YooKassaProvider {
    fn create_payment(
        &self,
        request: CreatePaymentRequest,
    ) -> Result<CreatePaymentResponse, ProviderError> {
        let return_url = request
            .return_url
            .as_deref()
            .map(str::trim)
            .filter(|value| !value.is_empty())
            .ok_or_else(|| {
                ProviderError::BadRequest("payment return_url is required".to_string())
            })?;
        let mut body = json!({
            "amount": {
                "value": rubles_to_value(request.amount_rub),
                "currency": "RUB"
            },
            "capture": true,
            "confirmation": {
                "type": "redirect",
                "return_url": return_url
            },
            "description": request.description,
            "metadata": {
                "order_id": request.order_id.to_string()
            }
        });
        if self.sbp_only {
            body["payment_method_data"] = json!({"type": "sbp"});
        }

        let response = self
            .client()?
            .post(format!("{}/payments", self.api_base_url))
            .basic_auth(&self.shop_id, Some(&self.secret_key))
            .header("Idempotence-Key", request.order_id.to_string())
            .json(&body)
            .send()
            .map_err(|error| {
                ProviderError::Transport(format!("YooKassa payment creation failed: {error}"))
            })?;
        let payment = parse_json_response(response, "YooKassa payment creation")?;
        let payment_id = required_str(&payment, "id")?;
        let amount_rub = payment_amount_rub(&payment)?;
        if amount_rub != request.amount_rub {
            return Err(ProviderError::BadRequest(
                "YooKassa returned a different payment amount".to_string(),
            ));
        }
        let metadata_order_id = payment_order_id(&payment)?;
        if metadata_order_id != request.order_id {
            return Err(ProviderError::BadRequest(
                "YooKassa returned a different order id".to_string(),
            ));
        }
        if self.sbp_only && payment_method_type(&payment).as_deref() != Some("sbp") {
            return Err(ProviderError::BadRequest(
                "YooKassa returned a non-SBP payment for SBP mode".to_string(),
            ));
        }
        let confirmation_url = payment
            .get("confirmation")
            .and_then(|value| value.get("confirmation_url"))
            .and_then(Value::as_str)
            .map(str::trim)
            .filter(|value| !value.is_empty())
            .ok_or_else(|| {
                ProviderError::BadRequest(
                    "YooKassa response has no confirmation_url".to_string(),
                )
            })?
            .to_string();
        let qr_url = self.sbp_only.then(|| confirmation_url.clone());
        Ok(CreatePaymentResponse {
            provider: self.provider_kind(),
            provider_payment_id: payment_id,
            confirmation_url,
            qr_url,
        })
    }

    fn parse_callback(&self, raw_body: &[u8]) -> Result<ProviderEvent, ProviderError> {
        let notification: Value = serde_json::from_slice(raw_body).map_err(|error| {
            ProviderError::BadRequest(format!(
                "invalid YooKassa notification JSON: {error}"
            ))
        })?;
        if notification.get("type").and_then(Value::as_str) != Some("notification") {
            return Err(ProviderError::BadRequest(
                "unsupported YooKassa notification type".to_string(),
            ));
        }
        let event_name = notification
            .get("event")
            .and_then(Value::as_str)
            .map(str::trim)
            .filter(|value| !value.is_empty())
            .ok_or_else(|| {
                ProviderError::BadRequest("YooKassa notification has no event".to_string())
            })?;
        let payment_id = notification
            .get("object")
            .and_then(|value| value.get("id"))
            .and_then(Value::as_str)
            .map(str::trim)
            .filter(|value| !value.is_empty())
            .ok_or_else(|| {
                ProviderError::BadRequest(
                    "YooKassa notification has no payment id".to_string(),
                )
            })?;

        // The callback body is only a notification. Payment proof comes from
        // an authenticated server-to-server read from YooKassa itself.
        let payment = self.fetch_payment(payment_id)?;
        let verified_payment_id = required_str(&payment, "id")?;
        if verified_payment_id != payment_id {
            return Err(ProviderError::BadSignature);
        }
        if self.sbp_only && payment_method_type(&payment).as_deref() != Some("sbp") {
            return Err(ProviderError::BadSignature);
        }
        let order_id = payment_order_id(&payment)?;
        let amount_rub = payment_amount_rub(&payment)?;
        let status = payment_status(&payment)?;
        if !event_matches_status(event_name, &status) {
            return Err(ProviderError::BadSignature);
        }
        Ok(ProviderEvent {
            provider: self.provider_kind(),
            provider_event_id: format!("{event_name}:{payment_id}"),
            provider_payment_id: Some(payment_id.to_string()),
            order_id,
            status,
            amount_rub,
        })
    }
}

fn required_env(name: &str) -> Result<String, ProviderError> {
    std::env::var(name)
        .ok()
        .map(|value| value.trim().to_string())
        .filter(|value| !value.is_empty())
        .ok_or_else(|| ProviderError::BadRequest(format!("{name} is not configured")))
}

fn parse_json_response(
    response: reqwest::blocking::Response,
    operation: &str,
) -> Result<Value, ProviderError> {
    let status = response.status();
    let text = response.text().map_err(|error| {
        ProviderError::Transport(format!("{operation} response read failed: {error}"))
    })?;
    if !status.is_success() {
        let safe = text.chars().take(400).collect::<String>();
        return Err(ProviderError::Transport(format!(
            "{operation} returned HTTP {}: {safe}",
            status.as_u16()
        )));
    }
    serde_json::from_str(&text).map_err(|error| {
        ProviderError::BadRequest(format!("{operation} returned invalid JSON: {error}"))
    })
}

fn required_str(value: &Value, key: &str) -> Result<String, ProviderError> {
    value
        .get(key)
        .and_then(Value::as_str)
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .map(str::to_string)
        .ok_or_else(|| ProviderError::BadRequest(format!("YooKassa response has no {key}")))
}

fn rubles_to_value(amount_rub: u64) -> String {
    format!("{amount_rub}.00")
}

fn payment_amount_rub(payment: &Value) -> Result<u64, ProviderError> {
    if payment
        .get("amount")
        .and_then(|value| value.get("currency"))
        .and_then(Value::as_str)
        != Some("RUB")
    {
        return Err(ProviderError::BadRequest(
            "YooKassa payment currency is not RUB".to_string(),
        ));
    }
    let raw = payment
        .get("amount")
        .and_then(|value| value.get("value"))
        .and_then(Value::as_str)
        .ok_or_else(|| {
            ProviderError::BadRequest("YooKassa payment has no amount.value".to_string())
        })?;
    let (rubles, kopecks) = raw.split_once('.').unwrap_or((raw, ""));
    if !kopecks.is_empty() && !kopecks.chars().all(|value| value == '0') {
        return Err(ProviderError::BadRequest(
            "YooKassa payment has non-zero kopecks".to_string(),
        ));
    }
    rubles.parse::<u64>().map_err(|_| {
        ProviderError::BadRequest("YooKassa payment amount is invalid".to_string())
    })
}

fn payment_order_id(payment: &Value) -> Result<Uuid, ProviderError> {
    let raw = payment
        .get("metadata")
        .and_then(|value| value.get("order_id"))
        .and_then(Value::as_str)
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .ok_or_else(|| {
            ProviderError::BadRequest("YooKassa payment has no metadata.order_id".to_string())
        })?;
    Uuid::parse_str(raw).map_err(|_| {
        ProviderError::BadRequest("YooKassa metadata.order_id is invalid".to_string())
    })
}

fn payment_method_type(payment: &Value) -> Option<String> {
    payment
        .get("payment_method")
        .and_then(|value| value.get("type"))
        .and_then(Value::as_str)
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .map(str::to_ascii_lowercase)
}

fn payment_status(payment: &Value) -> Result<ProviderPaymentStatus, ProviderError> {
    match payment
        .get("status")
        .and_then(Value::as_str)
        .unwrap_or_default()
        .trim()
        .to_ascii_lowercase()
        .as_str()
    {
        "pending" | "waiting_for_capture" => Ok(ProviderPaymentStatus::Pending),
        "succeeded" => Ok(ProviderPaymentStatus::Succeeded),
        "canceled" | "cancelled" => Ok(ProviderPaymentStatus::Cancelled),
        _ => Err(ProviderError::BadRequest(
            "unsupported YooKassa payment status".to_string(),
        )),
    }
}

fn event_matches_status(event_name: &str, status: &ProviderPaymentStatus) -> bool {
    matches!(
        (event_name, status),
        ("payment.succeeded", ProviderPaymentStatus::Succeeded)
            | ("payment.canceled", ProviderPaymentStatus::Cancelled)
            | (
                "payment.waiting_for_capture",
                ProviderPaymentStatus::Pending
            )
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn ruble_amounts_are_exact_and_non_fractional() {
        let payment = json!({"amount": {"value": "3900.00", "currency": "RUB"}});
        assert_eq!(payment_amount_rub(&payment).unwrap(), 3900);
        let fractional = json!({"amount": {"value": "3900.01", "currency": "RUB"}});
        assert!(payment_amount_rub(&fractional).is_err());
        assert_eq!(rubles_to_value(1490), "1490.00");
    }

    #[test]
    fn order_id_is_read_only_from_metadata() {
        let order_id = Uuid::new_v4();
        let payment = json!({"metadata": {"order_id": order_id.to_string()}});
        assert_eq!(payment_order_id(&payment).unwrap(), order_id);
    }

    #[test]
    fn notification_event_must_match_verified_payment_status() {
        assert!(event_matches_status(
            "payment.succeeded",
            &ProviderPaymentStatus::Succeeded
        ));
        assert!(!event_matches_status(
            "payment.succeeded",
            &ProviderPaymentStatus::Pending
        ));
        assert!(event_matches_status(
            "payment.canceled",
            &ProviderPaymentStatus::Cancelled
        ));
    }
}
