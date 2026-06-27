//! PostgreSQL storage boundary for the license server.
//!
//! The first implementation step keeps this module dependency-free and checked
//! into the repository with the SQL schema. A follow-up step can add `sqlx`
//! behind this boundary without touching HTTP routes, provider adapters or the
//! signing core.

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct PostgresConfig {
    pub database_url: String,
    pub max_connections: u32,
}

impl PostgresConfig {
    pub fn from_env() -> Option<Self> {
        let database_url = std::env::var("DOKKOMPLEKT_LICENSE_DATABASE_URL").ok()?;
        let max_connections = std::env::var("DOKKOMPLEKT_LICENSE_DB_MAX_CONNECTIONS")
            .ok()
            .and_then(|value| value.parse().ok())
            .unwrap_or(10);
        Some(Self {
            database_url,
            max_connections,
        })
    }
}

pub const SCHEMA_V1: &str = include_str!("../migrations/0001_license_server_schema.sql");
