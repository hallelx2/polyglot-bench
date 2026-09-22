use axum::{extract::{Path, State}, http::StatusCode, response::{IntoResponse, Response},
           routing::{get, post}, Json, Router};
use common::{db, domain::Request, error_response, summary};
use deadpool_postgres::Pool;
use std::sync::Arc;

struct App { pool: Pool }

fn err(e: db::Error) -> Response {
    let (status, body) = error_response(&e);
    (StatusCode::from_u16(status).unwrap(),
     [("content-type", "application/json")], body).into_response()
}

async fn health() -> impl IntoResponse {
    ([("content-type", "application/json")], r#"{"ok":true}"#)
}

async fn quote(State(app): State<Arc<App>>, Json(req): Json<Request>) -> Response {
    match db::quote(&app.pool, &req).await {
        Ok(inv) => Json(inv).into_response(),
        Err(e) => err(e),
    }
}

async fn checkout(State(app): State<Arc<App>>, Json(req): Json<Request>) -> Response {
    match db::checkout(&app.pool, &req).await {
        Ok(inv) => Json(inv).into_response(),
        Err(e) => err(e),
    }
}

async fn cust_summary(State(app): State<Arc<App>>, Path(id): Path<i32>) -> Response {
    match summary::summary(&app.pool, id).await {
        Ok(s) => Json(s).into_response(),
        Err(e) => err(e),
    }
}

#[tokio::main]
async fn main() {
    let app = Arc::new(App { pool: db::build_pool() });
    let router = Router::new()
        .route("/health", get(health))
        .route("/api/quote", post(quote))
        .route("/api/checkout", post(checkout))
        .route("/api/customers/:id/summary", get(cust_summary))
        .with_state(app);
    let port = std::env::var("PORT").unwrap_or_else(|_| "8080".into());
    let listener = tokio::net::TcpListener::bind(format!("0.0.0.0:{port}")).await.unwrap();
    axum::serve(listener, router).await.unwrap();
}
