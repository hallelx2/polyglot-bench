use actix_web::{web, App, HttpResponse, HttpServer, Responder};
use common::{db, domain::Request, error_response, summary};
use deadpool_postgres::Pool;

fn err(e: db::Error) -> HttpResponse {
    let (status, body) = error_response(&e);
    HttpResponse::build(actix_web::http::StatusCode::from_u16(status).unwrap())
        .content_type("application/json").body(body)
}

async fn health() -> impl Responder {
    HttpResponse::Ok().content_type("application/json").body(r#"{"ok":true}"#)
}

async fn quote(pool: web::Data<Pool>, req: web::Json<Request>) -> HttpResponse {
    match db::quote(&pool, &req).await {
        Ok(inv) => HttpResponse::Ok().json(inv),
        Err(e) => err(e),
    }
}

async fn checkout(pool: web::Data<Pool>, req: web::Json<Request>) -> HttpResponse {
    match db::checkout(&pool, &req).await {
        Ok(inv) => HttpResponse::Ok().json(inv),
        Err(e) => err(e),
    }
}

async fn cust_summary(pool: web::Data<Pool>, id: web::Path<i32>) -> HttpResponse {
    match summary::summary(&pool, *id).await {
        Ok(s) => HttpResponse::Ok().json(s),
        Err(e) => err(e),
    }
}

#[actix_web::main]
async fn main() -> std::io::Result<()> {
    let pool = db::build_pool();
    let port: u16 = std::env::var("PORT").unwrap_or_else(|_| "8080".into()).parse().unwrap();
    HttpServer::new(move || {
        App::new()
            .app_data(web::Data::new(pool.clone()))
            .app_data(web::JsonConfig::default().limit(1 << 20))
            .route("/health", web::get().to(health))
            .route("/api/quote", web::post().to(quote))
            .route("/api/checkout", web::post().to(checkout))
            .route("/api/customers/{id}/summary", web::get().to(cust_summary))
    })
    .bind(("0.0.0.0", port))?
    .run()
    .await
}
