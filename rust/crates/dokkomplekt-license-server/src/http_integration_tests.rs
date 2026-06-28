use super::{build_app, config::ServerConfig, state::AppState};
use axum::{
    body::{to_bytes, Body},
    http::{header::CONTENT_TYPE, Method, Request, StatusCode},
    Router,
};
use postgres::{Client, NoTls};
use serde_json::{json, Value};
use tower::ServiceExt;

fn postgres_config(database_url: String) -> ServerConfig {
    ServerConfig {
        bind_addr: "127.0.0.1:0".parse().unwrap(),
        public_base_url: "http://127.0.0.1:8787".to_string(),
        issuer_id: "test-issuer".to_string(),
        issuer_key_b64: Some("AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=".to_string()),
        default_license_days: 30,
        payment_provider: "manual".to_string(),
        storage_mode: "postgres".to_string(),
        database_url: Some(database_url),
    }
}

fn assert_schema_version_recorded(database_url: &str) {
    let mut client = Client::connect(database_url, NoTls).unwrap();
    let applied: bool = client
        .query_one(
            "SELECT EXISTS (SELECT 1 FROM schema_migrations WHERE version = '0001_license_schema')",
            &[],
        )
        .unwrap()
        .get(0);
    assert!(applied);
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

#[tokio::test]
async fn postgres_http_order_payment_activation_flow_when_database_url_is_present() {
    let Ok(database_url) = std::env::var("DATABASE_URL") else { return; };
    let state_url = database_url.clone();
    let state = tokio::task::spawn_blocking(move || AppState::try_new(postgres_config(state_url)).unwrap())
        .await
        .unwrap();
    let assertion_url = database_url.clone();
    tokio::task::spawn_blocking(move || assert_schema_version_recorded(&assertion_url)).await.unwrap();
    let app = build_app(state);

    let (status, health) = call(app.clone(), Method::GET, "/healthz".to_string(), None).await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(health["storage_backend"], "postgres");

    let (status, order) = call(
        app.clone(),
        Method::POST,
        "/api/orders".to_string(),
        Some(json!({ "plan": "doctor_pro", "amount_rub": 3900, "machine_hash": "machine-a" })),
    )
    .await;
    assert_eq!(status, StatusCode::OK);
    let order_id = order["order_id"].as_str().unwrap().to_string();
    assert_eq!(order["status"], "waiting_payment");

    let event_id = format!("evt-{order_id}");
    let (status, callback) = call(
        app.clone(),
        Method::POST,
        "/api/provider/callback".to_string(),
        Some(json!({
            "order_id": order_id,
            "provider_event_id": event_id,
            "provider_payment_id": "pay-1",
            "provider": "manual",
            "status": "succeeded",
            "amount_rub": 3900
        })),
    )
    .await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(callback["accepted"], true);
    assert_eq!(callback["duplicate"], false);

    let (status, duplicate) = call(
        app.clone(),
        Method::POST,
        "/api/provider/callback".to_string(),
        Some(json!({
            "order_id": order_id,
            "provider_event_id": event_id,
            "provider_payment_id": "pay-1-duplicate",
            "provider": "manual",
            "status": "succeeded",
            "amount_rub": 3900
        })),
    )
    .await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(duplicate["duplicate"], true);

    let (status, order_status) = call(app.clone(), Method::GET, format!("/api/orders/{order_id}/status"), None).await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(order_status["status"], "paid");

    let (status, activation) = call(
        app.clone(),
        Method::POST,
        format!("/api/orders/{order_id}/activate-machine"),
        Some(json!({ "machine_hash": "machine-a" })),
    )
    .await;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(activation["status"], "paid");

    tokio::task::spawn_blocking(move || drop(app)).await.unwrap();
}
