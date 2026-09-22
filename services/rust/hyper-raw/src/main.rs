//! Raw hyper: no router, no framework. Hand-written method+path dispatch.
use bytes::Bytes;
use common::{db, domain::Request, error_response, summary};
use deadpool_postgres::Pool;
use http_body_util::{BodyExt, Full};
use hyper::{body::Incoming, service::service_fn, Method, Response, StatusCode};
use hyper_util::rt::{TokioExecutor, TokioIo};
use hyper_util::server::conn::auto::Builder;
use std::{convert::Infallible, sync::Arc};
use tokio::net::TcpListener;

type Res = Response<Full<Bytes>>;

fn json(status: u16, body: String) -> Res {
    Response::builder()
        .status(StatusCode::from_u16(status).unwrap())
        .header("content-type", "application/json")
        .body(Full::new(Bytes::from(body)))
        .unwrap()
}

async fn route(req: hyper::Request<Incoming>, pool: Arc<Pool>) -> Result<Res, Infallible> {
    let method = req.method().clone();
    let path = req.uri().path().to_string();

    if method == Method::GET && path == "/health" {
        return Ok(json(200, r#"{"ok":true}"#.to_string()));
    }

    if method == Method::POST && (path == "/api/quote" || path == "/api/checkout") {
        let body = match req.into_body().collect().await {
            Ok(b) => b.to_bytes(),
            Err(_) => return Ok(json(400, r#"{"error":"bad_request"}"#.into())),
        };
        let parsed: Request = match serde_json::from_slice(&body) {
            Ok(p) => p,
            Err(_) => return Ok(json(400, r#"{"error":"bad_request"}"#.into())),
        };
        let result = if path == "/api/checkout" {
            db::checkout(&pool, &parsed).await
        } else {
            db::quote(&pool, &parsed).await
        };
        return Ok(match result {
            Ok(inv) => json(200, serde_json::to_string(&inv).unwrap()),
            Err(e) => { let (s, b) = error_response(&e); json(s, b) }
        });
    }

    if method == Method::GET
        && path.starts_with("/api/customers/")
        && path.ends_with("/summary")
    {
        let id_str = &path["/api/customers/".len()..path.len() - "/summary".len()];
        let id: i32 = match id_str.parse() {
            Ok(v) => v,
            Err(_) => return Ok(json(400, r#"{"error":"bad_request"}"#.into())),
        };
        return Ok(match summary::summary(&pool, id).await {
            Ok(s) => json(200, serde_json::to_string(&s).unwrap()),
            Err(e) => { let (st, b) = error_response(&e); json(st, b) }
        });
    }

    Ok(json(404, r#"{"error":"not_found"}"#.into()))
}

#[tokio::main]
async fn main() {
    let pool = Arc::new(db::build_pool());
    let port = std::env::var("PORT").unwrap_or_else(|_| "8080".into());
    let listener = TcpListener::bind(format!("0.0.0.0:{port}")).await.unwrap();
    loop {
        let (stream, _) = listener.accept().await.unwrap();
        let _ = stream.set_nodelay(true);
        let pool = pool.clone();
        tokio::spawn(async move {
            let io = TokioIo::new(stream);
            let _ = Builder::new(TokioExecutor::new())
                .serve_connection(io, service_fn(move |r| route(r, pool.clone())))
                .await;
        });
    }
}
