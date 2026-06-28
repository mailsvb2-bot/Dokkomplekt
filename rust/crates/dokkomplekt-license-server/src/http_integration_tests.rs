use super::{build_app, config::ServerConfig, state::AppState, storage::PostgresStore};
use axum::{body::{to_bytes, Body}, http::{header::CONTENT_TYPE, Method, Request, StatusCode}, Router};
use postgres::{Client, NoTls};
use serde_json::{json, Value};
use tower::ServiceExt;

fn base_config(database_url: Option<String>) -> ServerConfig {
    ServerConfig {
        bind_addr: "127.0.0.1:0".parse().unwrap(),
        public_base_url: "http://127.0.0.1:8787".to_string(),
        issuer_id: "test-issuer".to_string(),
        issuer_key_b64: None,
        default_license_days: 30,
        payment_provider: "manual".to_string(),
        storage_mode: if database_url.is_some() { "postgres" } else { "memory" }.to_string(),
        database_url,
    }
}

async fn call(app: Router, method: Method, uri: String, body: Option<Value>) -> (StatusCode, Value) {
    let mut builder = Request::builder().method(method).uri(uri);
    let request_body = match body {
        Some(value) => {
            builder = builder.header(CONTENT_TYPE, "application/json");
            Body::from(value.to_string())
        }
        None => Body::empty(),
    };
    let response = app.oneshot(builder.body(request_body).unwrap()).await.unwrap();
    let status = response.status();
    let bytes = to_bytes(response.into_body(), usize::MAX).await.unwrap();
    let body = if bytes.is_empty() { Value::Null } else { serde_json::from_slice(&bytes).unwrap() };
    (status, body)
}

async fn assert_order_payment_activation_flow(app: Router, expected_backend: &str) {
    let (status, health) = call(app.clone(), Method::GET, "/healthz".to_string(), None).await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(health["storage_backend"], expected_backend);

    let (status, order) = call(app.clone(), Method::POST, "/api/orders".to_string(), Some(json!({ "plan": "doctor_pro", "amount_rub": 3900, "machine_hash": "machine-a" }))).await;
    assert_eq!(status, StatusCode::OK);
    let order_id = order["order_id"].as_str().unwrap().to_string();
    assert_eq!(order["status"], "waiting_payment");

    let event_id = format!("evt-{order_id}");
    let callback = json!({ "order_id": order_id, "provider_event_id": event_id, "provider_payment_id": "pay-1", "provider": "manual", "status": "succeeded", "amount_rub": 3900 });
    let (status, body) = call(app.clone(), Method::POST, "/api/provider/callback".to_string(), Some(callback)).await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(body["duplicate"], false);

    let duplicate = json!({ "order_id": order_id, "provider_event_id": event_id, "provider_payment_id": "pay-1-dup", "provider": "manual", "status": "succeeded", "amount_rub": 3900 });
    let (status, body) = call(app.clone(), Method::POST, "/api/provider/callback".to_string(), Some(duplicate)).await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(body["duplicate"], true);

    let (status, body) = call(app.clone(), Method::GET, format!("/api/orders/{order_id}/status"), None).await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(body["status"], "paid");

    let (status, body) = call(app.clone(), Method::POST, format!("/api/orders/{order_id}/activate-machine"), Some(json!({ "machine_hash": "machine-a" }))).await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(body["status"], "paid");
}

#[tokio::test]
async fn memory_http_order_payment_activation_flow() {
    let app = build_app(AppState::try_new(base_config(None)).unwrap());
    assert_order_payment_activation_flow(app, "memory").await;
}

#[tokio::test]
async fn postgres_http_order_payment_activation_flow_when_database_url_is_present() {
    let Ok(database_url) = std::env::var("DATABASE_URL") else { return; };
    let app = tokio::task::spawn_blocking(move || build_app(AppState::try_new(base_config(Some(database_url))).unwrap()))
        .await
        .unwrap();
    assert_order_payment_activation_flow(app.clone(), "postgres").await;
    std::mem::forget(app);
}

#[test]
fn postgres_runtime_migration_records_schema_version_when_database_url_is_present() {
    let Ok(database_url) = std::env::var("DATABASE_URL") else { return; };
    let store = PostgresStore::connect(&database_url).unwrap();
    assert_eq!(store.pool_size(), 4);
    let mut client = Client::connect(&database_url, NoTls).unwrap();
    let applied: bool = client.query_one("SELECT EXISTS (SELECT 1 FROM schema_migrations WHERE version = '0001_license_schema')", &[]).unwrap().get(0);
    assert!(applied);
}
