//! Pricing engine — a direct transliteration of spec/SPEC.md §3.
//! Pure: no IO, no clock.

use chrono::NaiveDate;
use serde::{Deserialize, Serialize};

#[derive(Clone, Debug)]
pub struct Tier {
    pub id: i32,
    pub name: String,
    pub points_multiplier: i32,
    pub free_ship_threshold: i32,
    pub bonus_points: i32,
}

#[derive(Clone, Debug)]
pub struct CustomerRow {
    pub id: i32,
    pub region: String,
    pub tier_id: i32,
}

#[derive(Clone, Debug)]
pub struct Product {
    pub id: i32,
    pub sku: String,
    pub category: String,
    pub unit_price_cents: i32,
    pub weight_grams: i32,
    pub tax_exempt: bool,
}

#[derive(Clone, Debug)]
pub struct Rule {
    pub id: i32,
    pub scope: String,
    pub tier_id: Option<i32>,
    pub category: Option<String>,
    pub min_qty: Option<i32>,
    pub sku: Option<String>,
    pub percent_bp: i32,
    pub max_discount_cents: Option<i32>,
    pub stackable: bool,
}

#[derive(Clone, Debug)]
pub struct TaxRate {
    pub id: i32,
    pub category: Option<String>,
    pub rate_bp: i32,
}

#[derive(Clone, Debug)]
pub struct Coupon {
    pub id: i32,
    pub code: String,
    pub percent_bp: i32,
    pub max_discount_cents: i32,
    pub min_spend_cents: i32,
    pub max_uses: i32,
    pub times_used: i32,
    pub expires_on: NaiveDate,
}

#[derive(Deserialize, Debug)]
pub struct ReqItem {
    pub sku: String,
    pub qty: i32,
}

#[derive(Deserialize, Debug)]
#[serde(rename_all = "camelCase")]
pub struct Request {
    pub customer_id: i32,
    pub warehouse_id: i32,
    pub items: Vec<ReqItem>,
    #[serde(default)]
    pub coupon_code: Option<String>,
}

#[derive(Serialize, Debug)]
#[serde(rename_all = "camelCase")]
pub struct Line {
    pub sku: String,
    pub qty: i32,
    pub unit_price_cents: i32,
    pub base_cents: i32,
    pub discount_cents: i32,
    pub net_cents: i32,
    pub tax_cents: i32,
    pub points_earned: i32,
    pub applied_rules: Vec<String>,
    #[serde(skip)]
    pub product_id: i32,
    #[serde(skip)]
    pub category: String,
}

#[derive(Serialize, Debug)]
#[serde(rename_all = "camelCase")]
pub struct Invoice {
    pub order_id: i64,
    pub customer_id: i32,
    pub tier: String,
    pub lines: Vec<Line>,
    pub subtotal_cents: i32,
    pub coupon_applied: bool,
    pub coupon_code: Option<String>,
    pub coupon_rejected_reason: Option<String>,
    pub coupon_discount_cents: i32,
    pub tax_total_cents: i32,
    pub shipping_cents: i32,
    pub total_cents: i32,
    pub points_earned: i32,
    pub total_weight_grams: i32,
    #[serde(skip)]
    pub coupon_id: Option<i32>,
}

#[inline]
fn mul_bp(base: i32, bp: i32) -> i32 {
    ((base as i64 * bp as i64 + 5000) / 10000) as i32
}

fn rule_matches(r: &Rule, tier_id: i32, p: &Product, qty: i32) -> bool {
    match r.scope.as_str() {
        "tier" => r.tier_id == Some(tier_id),
        "category" => r.category.as_deref() == Some(p.category.as_str()),
        "volume" => r.min_qty.map_or(false, |m| qty >= m),
        "sku" => r.sku.as_deref() == Some(p.sku.as_str()),
        _ => false,
    }
}

fn rate_for(taxes: &[TaxRate], p: &Product) -> i32 {
    if p.tax_exempt {
        return 0;
    }
    let mut default = 0;
    for t in taxes {
        match &t.category {
            Some(c) if c == &p.category => return t.rate_bp,
            None => default = t.rate_bp,
            _ => {}
        }
    }
    default
}

fn shipping_for(weight: i32) -> i32 {
    match weight {
        w if w <= 500 => 499,
        w if w <= 2000 => 899,
        w if w <= 10000 => 1499,
        _ => 2499,
    }
}

pub fn price(
    cust: &CustomerRow,
    tier: &Tier,
    items: &[ReqItem],
    products: &std::collections::HashMap<String, Product>,
    rules: &[Rule],
    taxes: &[TaxRate],
    coupon: Option<&Coupon>,
    today: NaiveDate,
) -> Invoice {
    let mut lines: Vec<Line> = Vec::with_capacity(items.len());
    let (mut subtotal, mut weight, mut points) = (0i32, 0i32, 0i32);

    for it in items {
        let p = &products[&it.sku];
        let base = p.unit_price_cents * it.qty;

        let mut best_fixed = 0i32;
        let mut best_fixed_id: i32 = -1;
        let mut stack_sum = 0i32;

        for r in rules {
            if !rule_matches(r, cust.tier_id, p, it.qty) {
                continue;
            }
            let mut amt = mul_bp(base, r.percent_bp);
            if let Some(m) = r.max_discount_cents {
                amt = amt.min(m);
            }
            if r.stackable {
                stack_sum += amt;
            } else if amt > best_fixed || best_fixed_id == -1 {
                best_fixed = amt;
                best_fixed_id = r.id;
            }
        }

        // Contributing rules: every stackable match plus the single winning
        // non-stackable one, ascending by id.
        let mut final_rules: Vec<(i32, &str)> = rules
            .iter()
            .filter(|r| {
                rule_matches(r, cust.tier_id, p, it.qty)
                    && (r.stackable || r.id == best_fixed_id)
            })
            .map(|r| (r.id, r.scope.as_str()))
            .collect();
        final_rules.sort_by_key(|(id, _)| *id);

        let mut disc = best_fixed + stack_sum;
        let cap = mul_bp(base, 6000);
        if disc > cap {
            disc = cap;
        }
        let net = base - disc;
        let pts = (net / 100) * tier.points_multiplier;

        lines.push(Line {
            sku: p.sku.clone(),
            qty: it.qty,
            unit_price_cents: p.unit_price_cents,
            base_cents: base,
            discount_cents: disc,
            net_cents: net,
            tax_cents: 0,
            points_earned: pts,
            applied_rules: final_rules
                .iter()
                .map(|(id, s)| format!("{}:{}", s, id))
                .collect(),
            product_id: p.id,
            category: p.category.clone(),
        });
        subtotal += net;
        weight += p.weight_grams * it.qty;
        points += pts;
    }

    let mut coupon_id = None;
    let mut coupon_code = None;
    let mut reject: Option<String> = None;
    let mut coupon_discount = 0i32;
    let mut applied = false;

    if let Some(c) = coupon {
        coupon_code = Some(c.code.clone());
        if today > c.expires_on {
            reject = Some("expired".into());
        } else if c.times_used >= c.max_uses {
            reject = Some("exhausted".into());
        } else if subtotal < c.min_spend_cents {
            reject = Some("min_spend_not_met".into());
        } else {
            applied = true;
            coupon_discount = mul_bp(subtotal, c.percent_bp).min(c.max_discount_cents);
            coupon_id = Some(c.id);
        }
    }

    let mut shares = vec![0i32; lines.len()];
    if applied && coupon_discount > 0 && subtotal > 0 {
        let (mut sum, mut max_idx, mut max_net) = (0i32, 0usize, -1i32);
        for (i, l) in lines.iter().enumerate() {
            shares[i] = ((coupon_discount as i64 * l.net_cents as i64) / subtotal as i64) as i32;
            sum += shares[i];
            if l.net_cents > max_net {
                max_net = l.net_cents;
                max_idx = i;
            }
        }
        shares[max_idx] += coupon_discount - sum;
    }

    let mut tax_total = 0i32;
    for (i, l) in lines.iter_mut().enumerate() {
        let taxable = l.net_cents - shares[i];
        let p = &products[&l.sku];
        l.tax_cents = mul_bp(taxable, rate_for(taxes, p));
        tax_total += l.tax_cents;
    }

    let mut shipping = shipping_for(weight);
    if subtotal - coupon_discount >= tier.free_ship_threshold {
        shipping = 0;
    }
    let total = subtotal - coupon_discount + tax_total + shipping;
    if total >= 50000 {
        points += tier.bonus_points;
    }

    Invoice {
        order_id: 0,
        customer_id: cust.id,
        tier: tier.name.clone(),
        lines,
        subtotal_cents: subtotal,
        coupon_applied: applied,
        coupon_code,
        coupon_rejected_reason: reject,
        coupon_discount_cents: coupon_discount,
        tax_total_cents: tax_total,
        shipping_cents: shipping,
        total_cents: total,
        points_earned: points,
        total_weight_grams: weight,
        coupon_id,
    }
}
