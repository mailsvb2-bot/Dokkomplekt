use std::net::SocketAddr;

#[derive(Debug, Clone)]
pub struct ServerConfig {
    pub bind_addr: SocketAddr,
    pub public_base_url: String,
}

impl ServerConfig {
    pub fn from_env() -> anyhow::Result<Self> {
        let bind_addr = std::env::var("DOKKOMPLEKT_LICENSE_BIND")
            .unwrap_or_else(|_| "127.0.0.1:8787".to_string())
            .parse()?;
        let public_base_url = std::env::var("DOKKOMPLEKT_LICENSE_PUBLIC_URL")
            .unwrap_or_else(|_| "http://127.0.0.1:8787".to_string());
        Ok(Self { bind_addr, public_base_url })
    }
}
