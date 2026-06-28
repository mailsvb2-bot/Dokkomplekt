use std::net::SocketAddr;

#[derive(Debug, Clone)]
pub struct ServerConfig {
    pub bind_addr: SocketAddr,
    pub public_base_url: String,
    pub issuer_id: String,
    pub issuer_key_b64: Option<String>,
    pub default_license_days: i64,
    pub payment_provider: String,
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
        Ok(Self { bind_addr, public_base_url, issuer_id, issuer_key_b64, default_license_days, payment_provider })
    }
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
        assert!(normalize_payment_provider("cash-under-table").is_none());
    }
}
