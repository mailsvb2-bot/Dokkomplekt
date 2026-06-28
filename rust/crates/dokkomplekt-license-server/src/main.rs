mod config;
mod http;
mod issuer;
mod provider_manual;
mod provider_yookassa;
mod providers;
mod state;
mod storage;

use anyhow::Context;
use axum::Router;
use config::ServerConfig;
use state::AppState;
use tower_http::trace::TraceLayer;
use tracing_subscriber::{layer::SubscriberExt, util::SubscriberInitExt};

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    tracing_subscriber::registry()
        .with(tracing_subscriber::EnvFilter::try_from_default_env().unwrap_or_else(|_| "info".into()))
        .with(tracing_subscriber::fmt::layer())
        .init();

    let config = ServerConfig::from_env()?;
    let state = AppState::new(config.clone());
    let app = Router::new()
        .merge(http::health::router())
        .merge(http::orders::router())
        .merge(http::activations::router())
        .merge(http::licenses::router())
        .merge(http::webhooks::router())
        .layer(TraceLayer::new_for_http())
        .with_state(state);

    let listener = tokio::net::TcpListener::bind(config.bind_addr)
        .await
        .with_context(|| format!("failed to bind {}", config.bind_addr))?;
    tracing::info!("dokkomplekt service listening on {}", listener.local_addr()?);
    axum::serve(listener, app).await?;
    Ok(())
}
