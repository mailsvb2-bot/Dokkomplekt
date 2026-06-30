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
    pub environment: String,
    pub provider_callback_secret: Option<String>,
    pub license_issue_secret: Option<String>,
}

impl ServerConfig {
    pub fn from_env() -> anyhow::Result<Self> {
        let environment = normalize_environment(
            &std::env::var("DOKKOMPLEKT_ENV").unwrap_or_else(|_| "development".to_string()),
        );
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
        let payment_provider = normalize_payment_provider(
            &std::env::var("DOKKOMPLEKT_PAYMENT_PROVIDER").unwrap_or_else(|_| "manual".to_string()),
        )
        .unwrap_or_else(|| "manual".to_string());
        let database_url = non_empty_env("DATABASE_URL");
        let provider_callback_secret = non_empty_env("DOKKOMPLEKT_PROVIDER_CALLBACK_SECRET");
        let license_issue_secret = non_empty_env("DOKKOMPLEKT_LICENSE_ISSUE_SECRET");
        if is_production_environment(&environment) {
            if database_url.is_none() {
                anyhow::bail!("DATABASE_URL is required when DOKKOMPLEKT_ENV=production");
            }
            if issuer_key_b64.is_none() {
                anyhow::bail!("DOKKOMPLEKT_LICENSE_ISSUER_KEY_B64 is required when DOKKOMPLEKT_ENV=production");
            }
            if provider_callback_secret.is_none() {
                anyhow::bail!("DOKKOMPLEKT_PROVIDER_CALLBACK_SECRET is required when DOKKOMPLEKT_ENV=production");
            }
            if license_issue_secret.is_none() {
                anyhow::bail!("DOKKOMPLEKT_LICENSE_ISSUE_SECRET is required when DOKKOMPLEKT_ENV=production");
            }
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
            environment,
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

pub fn normalize_environment(value: &str) -> String {
    match value.trim().to_ascii_lowercase().as_str() {
        "prod" | "production" => "production".to_string(),
        "stage" | "staging" => "staging".to_string(),
        "test" | "testing" | "ci" => "test".to_string(),
        _ => "development".to_string(),
    }
}

pub fn is_production_environment(value: &str) -> bool {
    normalize_environment(value) == "production"
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
    use super::{is_production_environment, normalize_environment, normalize_payment_provider};

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

    #[test]
    fn production_environment_aliases_are_strict() {
        assert_eq!(normalize_environment("prod"), "production");
        assert_eq!(normalize_environment(" production "), "production");
        assert!(is_production_environment("production"));
        assert!(!is_production_environment("development"));
    }
}
