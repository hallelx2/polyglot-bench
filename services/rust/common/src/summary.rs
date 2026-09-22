use crate::db::Error;
use chrono::{DateTime, Utc};
use deadpool_postgres::Pool;
use serde::Serialize;
use std::collections::HashMap;

#[derive(Serialize)]
pub struct CategorySpend {
    pub category: String,
    #[serde(rename = "netCents")]
    pub net_cents: i32,
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
pub struct Summary {
    pub customer_id: i32,
    pub tier: String,
    pub order_count: i32,
    pub lifetime_value_cents: i32,
    pub avg_order_value_cents: i32,
    pub top_categories: Vec<CategorySpend>,
    pub points_balance: i32,
    pub segment: String,
    pub last_order_at: Option<DateTime<Utc>>,
}

pub async fn summary(pool: &Pool, customer_id: i32) -> Result<Summary, Error> {
    let c = pool.get().await.map_err(|e| Error::Pool(format!("{e:?}")))?;

    let st = c.prepare_cached(
        "SELECT t.name FROM customer c JOIN customer_tier t ON t.id = c.tier_id WHERE c.id = $1").await?;
    let tier: String = c.query_opt(&st, &[&customer_id]).await?
        .ok_or(Error::NotFound)?.get(0);

    let st = c.prepare_cached(
        "SELECT id, total_cents, created_at FROM \"order\" \
         WHERE customer_id = $1 ORDER BY created_at DESC LIMIT 50").await?;
    let rows = c.query(&st, &[&customer_id]).await?;
    let mut ids: Vec<i64> = Vec::with_capacity(rows.len());
    let mut lifetime = 0i32;
    let mut last_order_at = None;
    for (i, r) in rows.iter().enumerate() {
        ids.push(r.get(0));
        lifetime += r.get::<_, i32>(1);
        if i == 0 { last_order_at = Some(r.get::<_, DateTime<Utc>>(2)); }
    }
    let order_count = ids.len() as i32;
    let avg = if order_count > 0 { lifetime / order_count } else { 0 };

    let mut by_cat: HashMap<String, i32> = HashMap::with_capacity(12);
    if !ids.is_empty() {
        let st = c.prepare_cached(
            "SELECT category, net_cents FROM order_item WHERE order_id = ANY($1)").await?;
        for r in c.query(&st, &[&ids]).await? {
            *by_cat.entry(r.get(0)).or_insert(0) += r.get::<_, i32>(1);
        }
    }
    let mut cats: Vec<CategorySpend> = by_cat.into_iter()
        .map(|(category, net_cents)| CategorySpend { category, net_cents }).collect();
    cats.sort_by(|a, b| b.net_cents.cmp(&a.net_cents).then(a.category.cmp(&b.category)));
    cats.truncate(5);

    let st = c.prepare_cached(
        "SELECT points FROM loyalty_transaction WHERE customer_id = $1 \
         ORDER BY created_at DESC LIMIT 100").await?;
    let mut points_balance = 0i32;
    for r in c.query(&st, &[&customer_id]).await? {
        points_balance += r.get::<_, i32>(0);
    }

    let segment = if lifetime >= 500_000 && order_count >= 20 { "champion" }
        else if order_count >= 10 { "loyal" }
        else if order_count >= 3 { "promising" }
        else { "new" }.to_string();

    Ok(Summary {
        customer_id, tier, order_count, lifetime_value_cents: lifetime,
        avg_order_value_cents: avg, top_categories: cats, points_balance,
        segment, last_order_at,
    })
}
