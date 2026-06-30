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
        let issuer_key_b64 = std::env::var("DOKKOMPLEKT_LICENSE_ISSUER_KEY_B64").ok();
        let default_license_days = std::env::var("DOKKOMPLEKT_DEFAULT_LICENSE_DAYS")
            .ok()
            .and_then(|value| value.parse().ok())
            .unwrap_or(365);
        let payment_provider = normalize_payment_provider(
            &std::env::var("DOKKOMPLEKT_PAYMENT_PROVIDER").unwrap_or_else(|_| "manual".to_string()),
        )
        .unwrap_or_else(|| "manual".to_string());
        let strict_runtime = strict_runtime_required();
        if strict_runtime && payment_provider == "manual" {
            anyhow::bail!("manual payment provider is not allowed for license server runtime");
        }
        let database_url = std::env::var("DATABASE_URL").ok();
        if database_url.as_ref().map(|value| value.trim()).filter(|value| !value.is_empty()).is_none() && strict_runtime {
            anyhow::bail!("PostgreSQL connection is required for license server runtime");
        }
        let storage_mode = match database_url.as_ref().map(|value| value.trim()).filter(|value| !value.is_empty()) {
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
        })
    }
}

fn strict_runtime_required() -> bool {
    for name in ["DOKKOMPLEKT_LICENSE_ENV", "APP_ENV", "RUST_ENV", "ENV"] {
        let value = std::env::var(name).unwrap_or_default().trim().to_ascii_lowercase();
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
        assert_eq!(normalize_payment_provider("bank_invoice").as_deref(), Some("bank_invoice"));
    }

    #[test]
    fn unknown_payment_provider_is_rejected() {
        assert!(normalize_payment_provider("unsupported").is_none());
    }
}
