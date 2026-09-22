use crate::domain::*;
use chrono::NaiveDate;
use deadpool_postgres::{Config, GenericClient, ManagerConfig, Pool, RecyclingMethod, Runtime};
use std::collections::HashMap;
use tokio_postgres::NoTls;

pub const TODAY: fn() -> NaiveDate = || NaiveDate::from_ymd_opt(2026, 9, 21).unwrap();

#[derive(Debug)]
pub enum Error {
    NotFound,
    Stock(String),
    Db(tokio_postgres::Error),
    Pool(String),
}

impl From<tokio_postgres::Error> for Error {
    fn from(e: tokio_postgres::Error) -> Self { Error::Db(e) }
}
impl From<deadpool_postgres::PoolError> for Error {
    fn from(e: deadpool_postgres::PoolError) -> Self { Error::Pool(format!("{e:?}")) }
}

pub fn build_pool() -> Pool {
    let url = std::env::var("DATABASE_URL").expect("DATABASE_URL");
    let size: usize = std::env::var("DB_POOL_SIZE").ok()
        .and_then(|s| s.parse().ok()).unwrap_or(20);
    let mut cfg = Config::new();
    cfg.url = Some(url);
    cfg.manager = Some(ManagerConfig { recycling_method: RecyclingMethod::Fast });
    cfg.pool = Some(deadpool_postgres::PoolConfig::new(size));
    cfg.create_pool(Some(Runtime::Tokio1), NoTls).expect("pool")
}

const Q_CUSTOMER: &str = "SELECT c.id, c.region, c.tier_id, t.name, t.points_multiplier, \
    t.free_shipping_threshold_cents, t.bonus_points \
    FROM customer c JOIN customer_tier t ON t.id = c.tier_id WHERE c.id = $1";
const Q_PRODUCTS: &str = "SELECT id, sku, category, unit_price_cents, weight_grams, tax_exempt \
    FROM product WHERE sku = ANY($1)";
const Q_RULES: &str = "SELECT id, scope, tier_id, category, min_qty, sku, percent_bp, \
    max_discount_cents, stackable FROM discount_rule WHERE active_from <= $1 AND active_to >= $1";
const Q_TAXES: &str = "SELECT id, category, rate_bp FROM tax_rate WHERE region = $1";
const Q_COUPON: &str = "SELECT id, code, percent_bp, max_discount_cents, min_spend_cents, \
    max_uses, times_used, expires_on FROM coupon WHERE code = $1";

pub struct Ref {
    pub cust: CustomerRow,
    pub tier: Tier,
    pub products: HashMap<String, Product>,
    pub rules: Vec<Rule>,
    pub taxes: Vec<TaxRate>,
    pub coupon: Option<Coupon>,
    pub ids: Vec<i32>,
}

pub async fn load_ref<C: GenericClient + Sync>(c: &C, req: &Request) -> Result<Ref, Error> {
    let st = c.prepare_cached(Q_CUSTOMER).await?;
    let row = c.query_opt(&st, &[&req.customer_id]).await?.ok_or(Error::NotFound)?;
    let cust = CustomerRow { id: row.get(0), region: row.get(1), tier_id: row.get(2) };
    let tier = Tier {
        id: cust.tier_id, name: row.get(3), points_multiplier: row.get(4),
        free_ship_threshold: row.get(5), bonus_points: row.get(6),
    };

    let skus: Vec<&str> = req.items.iter().map(|i| i.sku.as_str()).collect();
    let st = c.prepare_cached(Q_PRODUCTS).await?;
    let rows = c.query(&st, &[&skus]).await?;
    let mut products = HashMap::with_capacity(rows.len());
    let mut ids = Vec::with_capacity(rows.len());
    for r in rows {
        let p = Product {
            id: r.get(0), sku: r.get(1), category: r.get(2),
            unit_price_cents: r.get(3), weight_grams: r.get(4), tax_exempt: r.get(5),
        };
        ids.push(p.id);
        products.insert(p.sku.clone(), p);
    }
    for it in &req.items {
        if !products.contains_key(&it.sku) { return Err(Error::NotFound); }
    }
    ids.sort_unstable();
    ids.dedup();

    let today = TODAY();
    let st = c.prepare_cached(Q_RULES).await?;
    let rules = c.query(&st, &[&today]).await?.into_iter().map(|r| Rule {
        id: r.get(0), scope: r.get(1), tier_id: r.get(2), category: r.get(3),
        min_qty: r.get(4), sku: r.get(5), percent_bp: r.get(6),
        max_discount_cents: r.get(7), stackable: r.get(8),
    }).collect();

    let st = c.prepare_cached(Q_TAXES).await?;
    let taxes = c.query(&st, &[&cust.region]).await?.into_iter().map(|r| TaxRate {
        id: r.get(0), category: r.get(1), rate_bp: r.get(2),
    }).collect();

    let coupon = match &req.coupon_code {
        Some(code) => {
            let st = c.prepare_cached(Q_COUPON).await?;
            c.query_opt(&st, &[code]).await?.map(|r| Coupon {
                id: r.get(0), code: r.get(1), percent_bp: r.get(2),
                max_discount_cents: r.get(3), min_spend_cents: r.get(4),
                max_uses: r.get(5), times_used: r.get(6), expires_on: r.get(7),
            })
        }
        None => None,
    };

    Ok(Ref { cust, tier, products, rules, taxes, coupon, ids })
}

pub async fn quote(pool: &Pool, req: &Request) -> Result<Invoice, Error> {
    let client = pool.get().await.map_err(|e| Error::Pool(format!("{e:?}")))?;
    let r = load_ref(&client, req).await?;
    let st = client.prepare_cached(
        "SELECT product_id, on_hand, reserved FROM inventory \
         WHERE warehouse_id = $1 AND product_id = ANY($2) ORDER BY product_id").await?;
    let _ = client.query(&st, &[&req.warehouse_id, &r.ids]).await?;
    Ok(price(&r.cust, &r.tier, &req.items, &r.products, &r.rules, &r.taxes,
             r.coupon.as_ref(), TODAY()))
}

pub async fn checkout(pool: &Pool, req: &Request) -> Result<Invoice, Error> {
    let mut client = pool.get().await.map_err(|e| Error::Pool(format!("{e:?}")))?;
    let tx = client.transaction().await?;

    let r = load_ref(&tx, req).await?;

    let mut want: HashMap<i32, i32> = HashMap::with_capacity(req.items.len());
    let mut sku_of: HashMap<i32, String> = HashMap::with_capacity(req.items.len());
    for it in &req.items {
        let p = &r.products[&it.sku];
        *want.entry(p.id).or_insert(0) += it.qty;
        sku_of.insert(p.id, p.sku.clone());
    }

    let st = tx.prepare_cached(
        "SELECT product_id, on_hand, reserved FROM inventory \
         WHERE warehouse_id = $1 AND product_id = ANY($2) ORDER BY product_id FOR UPDATE").await?;
    for row in tx.query(&st, &[&req.warehouse_id, &r.ids]).await? {
        let pid: i32 = row.get(0);
        let on_hand: i32 = row.get(1);
        let reserved: i32 = row.get(2);
        if on_hand - reserved < *want.get(&pid).unwrap_or(&0) {
            return Err(Error::Stock(sku_of[&pid].clone()));
        }
    }

    let mut inv = price(&r.cust, &r.tier, &req.items, &r.products, &r.rules, &r.taxes,
                        r.coupon.as_ref(), TODAY());

    let st = tx.prepare_cached(
        "INSERT INTO \"order\" (customer_id, warehouse_id, subtotal_cents, coupon_id, \
         coupon_discount_cents, tax_total_cents, shipping_cents, total_cents, points_earned) \
         VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9) RETURNING id").await?;
    let order_id: i64 = tx.query_one(&st, &[
        &req.customer_id, &req.warehouse_id, &inv.subtotal_cents, &inv.coupon_id,
        &inv.coupon_discount_cents, &inv.tax_total_cents, &inv.shipping_cents,
        &inv.total_cents, &inv.points_earned]).await?.get(0);
    inv.order_id = order_id;

    // one multi-row insert for the lines
    let mut sql = String::from(
        "INSERT INTO order_item (order_id, product_id, sku, category, qty, \
         unit_price_cents, discount_cents, net_cents, tax_cents) VALUES ");
    let mut params: Vec<&(dyn tokio_postgres::types::ToSql + Sync)> =
        Vec::with_capacity(inv.lines.len() * 9);
    for (i, l) in inv.lines.iter().enumerate() {
        if i > 0 { sql.push(','); }
        let b = i * 9;
        sql.push_str(&format!("(${},${},${},${},${},${},${},${},${})",
            b+1,b+2,b+3,b+4,b+5,b+6,b+7,b+8,b+9));
        params.push(&order_id);
        params.push(&l.product_id);
        params.push(&l.sku);
        params.push(&l.category);
        params.push(&l.qty);
        params.push(&l.unit_price_cents);
        params.push(&l.discount_cents);
        params.push(&l.net_cents);
        params.push(&l.tax_cents);
    }
    let st = tx.prepare_cached(&sql).await?;
    tx.execute(&st, &params).await?;

    let st = tx.prepare_cached(
        "UPDATE inventory SET reserved = reserved + $1 WHERE warehouse_id = $2 AND product_id = $3").await?;
    for pid in &r.ids {
        tx.execute(&st, &[&want[pid], &req.warehouse_id, pid]).await?;
    }

    let st = tx.prepare_cached(
        "INSERT INTO ledger_entry (order_id, account, debit_cents, credit_cents) \
         VALUES ($1,'revenue',$2,0), ($1,'tax_payable',0,$3)").await?;
    let revenue = inv.subtotal_cents - inv.coupon_discount_cents;
    tx.execute(&st, &[&order_id, &revenue, &inv.tax_total_cents]).await?;

    if let Some(cid) = inv.coupon_id {
        let st = tx.prepare_cached(
            "UPDATE coupon SET times_used = times_used + 1 WHERE id = $1").await?;
        tx.execute(&st, &[&cid]).await?;
    }

    let st = tx.prepare_cached(
        "INSERT INTO loyalty_transaction (customer_id, order_id, points, kind) \
         VALUES ($1,$2,$3,'earn')").await?;
    tx.execute(&st, &[&req.customer_id, &order_id, &inv.points_earned]).await?;

    tx.commit().await?;
    Ok(inv)
}
