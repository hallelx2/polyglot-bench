pub mod db;
pub mod domain;
pub mod summary;

/// Shared error -> (status, body) mapping so all three servers answer identically.
pub fn error_response(e: &db::Error) -> (u16, String) {
    match e {
        db::Error::NotFound => (404, r#"{"error":"not_found"}"#.to_string()),
        db::Error::Stock(sku) => (409, format!(
            r#"{{"error":"insufficient_stock","sku":{}}}"#,
            serde_json::to_string(sku).unwrap())),
        db::Error::Db(err) => (500, format!(
            r#"{{"error":{}}}"#, serde_json::to_string(&err.to_string()).unwrap())),
        db::Error::Pool(m) => (500, format!(
            r#"{{"error":{}}}"#, serde_json::to_string(m).unwrap())),
    }
}
