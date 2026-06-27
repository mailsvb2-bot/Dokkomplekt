use std::net::SocketAddr;

#[derive(Debug, Clone)]
pub struct ServerConfig {
    pub bind_addr: SocketAddr,
    pub public_base_url: String,
    pub issuer_id: String,
    pub issuer_key_b64: Option<String>,
    pub default_license_days: i64,
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
        Ok(Self { bind_addr, public_base_url, issuer_id, issuer_key_b64, default_license_days })
    }
}
