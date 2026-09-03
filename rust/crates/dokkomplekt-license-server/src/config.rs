use crate::provider_bank_invoice::BankInvoiceProvider;
use std::net::SocketAddr;

#[derive(Debug, Clone)]
pub struct ServerConfig {
    pub bind_addr: SocketAddr,
    pub public_base_url: String,
    pub issuer_id: String,
    pub issuer_key_b64: Option<String>,
    pub default_license_days: i64,
    pub payment_provider: String,
    pub storage_mode: String,
    pub database_url: Option<String>,
    pub provider_callback_secret: Option<String>,
    pub license_issue_secret: Option<String>,
}

impl ServerConfig {
    pub fn from_env() -> anyhow::Result<Self> {
        let bind_addr = std::env::var("DOKKOMPLEKT_LICENSE_BIND")
            .unwrap_or_else(|_| "127.0.0.1:8787".to_string())
            .parse()?;
        let public_base_url = std::env::var("DOKKOMPLEKT_LICENSE_PUBLIC_URL")
            .unwrap_or_else(|_| "http://127.0.0.1:8787".to_string());
        let issuer_id = std::env::var("DOKKOMPLEKT_LICENSE_ISSUER")
            .unwrap_or_else(|_| "dokkomplekt-license-server".to_string());
        let issuer_key_b64 = non_empty_env("DOKKOMPLEKT_LICENSE_ISSUER_KEY_B64");
        let default_license_days = std::env::var("DOKKOMPLEKT_DEFAULT_LICENSE_DAYS")
            .ok()
            .and_then(|value| value.parse().ok())
            .unwrap_or(365);
        let payment_provider_raw = std::env::var("DOKKOMPLEKT_PAYMENT_PROVIDER")
            .unwrap_or_else(|_| "manual".to_string());
        let payment_provider = normalize_payment_provider(&payment_provider_raw)
            .ok_or_else(|| anyhow::anyhow!("unsupported DOKKOMPLEKT_PAYMENT_PROVIDER: {payment_provider_raw}"))?;
        let strict_runtime = strict_runtime_required();
        if strict_runtime && payment_provider == "manual" {
            anyhow::bail!("manual payment provider is not allowed for license server runtime");
        }
        let database_url = non_empty_env("DATABASE_URL");
        if database_url
            .as_ref()
            .map(|value| value.trim())
            .filter(|value| !value.is_empty())
            .is_none()
            && strict_runtime
        {
            anyhow::bail!("PostgreSQL connection is required for license server runtime");
        }
        let provider_callback_secret = non_empty_env("DOKKOMPLEKT_PROVIDER_CALLBACK_SECRET");
        let license_issue_secret = non_empty_env("DOKKOMPLEKT_LICENSE_ISSUE_SECRET");
        if strict_runtime && issuer_key_b64.is_none() {
            anyhow::bail!("DOKKOMPLEKT_LICENSE_ISSUER_KEY_B64 is required for license server runtime");
        }
        if strict_runtime && license_issue_secret.is_none() {
            anyhow::bail!("DOKKOMPLEKT_LICENSE_ISSUE_SECRET is required for license server runtime");
        }
        if matches!(payment_provider.as_str(), "yookassa" | "sbp") {
            if non_empty_env("DOKKOMPLEKT_YOOKASSA_SHOP_ID").is_none() {
                anyhow::bail!("DOKKOMPLEKT_YOOKASSA_SHOP_ID is required for YooKassa/SBP payments");
            }
            if non_empty_env("DOKKOMPLEKT_YOOKASSA_SECRET_KEY").is_none() {
                anyhow::bail!("DOKKOMPLEKT_YOOKASSA_SECRET_KEY is required for YooKassa/SBP payments");
            }
        }
        if payment_provider == "bank_invoice" {
            if provider_callback_secret.is_none() {
                anyhow::bail!(
                    "DOKKOMPLEKT_PROVIDER_CALLBACK_SECRET is required for bank_invoice confirmation"
                );
            }
            BankInvoiceProvider::validate_env()
                .map_err(|error| anyhow::anyhow!(error.to_string()))?;
        }

        let storage_mode = match database_url
            .as_ref()
            .map(|value| value.trim())
            .filter(|value| !value.is_empty())
        {
            Some(_) => "postgres".to_string(),
            None => "memory".to_string(),
        };
        Ok(Self {
            bind_addr,
            public_base_url,
            issuer_id,
            issuer_key_b64,
            default_license_days,
            payment_provider,
            storage_mode,
            database_url,
            provider_callback_secret,
            license_issue_secret,
        })
    }
}

fn non_empty_env(name: &str) -> Option<String> {
    std::env::var(name)
        .ok()
        .map(|value| value.trim().to_string())
        .filter(|value| !value.is_empty())
}

fn strict_runtime_required() -> bool {
    for name in [
        "DOKKOMPLEKT_ENV",
        "DOKKOMPLEKT_LICENSE_ENV",
        "APP_ENV",
        "RUST_ENV",
        "ENV",
    ] {
        let value = std::env::var(name)
            .unwrap_or_default()
            .trim()
            .to_ascii_lowercase();
        if matches!(value.as_str(), "production" | "prod") {
            return true;
        }
    }
    false
}

pub fn normalize_payment_provider(value: &str) -> Option<String> {
    match value.trim().to_ascii_lowercase().as_str() {
        "manual" => Some("manual".to_string()),
        "yookassa" => Some("yookassa".to_string()),
        "sbp" => Some("sbp".to_string()),
        "bank_invoice" => Some("bank_invoice".to_string()),
        _ => None,
    }
}

#[cfg(test)]
mod tests {
    use super::normalize_payment_provider;

    #[test]
    fn payment_provider_names_are_normalized() {
        assert_eq!(normalize_payment_provider(" manual ").as_deref(), Some("manual"));
        assert_eq!(normalize_payment_provider("YooKassa").as_deref(), Some("yookassa"));
        assert_eq!(normalize_payment_provider("SBP").as_deref(), Some("sbp"));
        assert_eq!(
            normalize_payment_provider("bank_invoice").as_deref(),
            Some("bank_invoice")
        );
    }

    #[test]
    fn unknown_payment_provider_is_rejected() {
        assert!(normalize_payment_provider("unsupported").is_none());
    }
}
