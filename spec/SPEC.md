# Benchmark contract

Every service in `services/` MUST implement this exactly. The conformance harness
(`bench/verify.sh`) replays a fixed corpus of requests against every service and
diffs the canonical JSON — any divergence fails the run, so a stack cannot win by
doing less work.

## Shared rules

- Money is **integer minor units** (cents). No floats anywhere in pricing.
- All rounding is **half-up on the final cent** of each computed component.
- JSON keys are emitted in the order given below; the harness canonicalises anyway.
- Connection pool size: read from `DB_POOL_SIZE` (harness sets it identically).
- Listen on `PORT`. No logging on the hot path. No response compression.
- `GET /health` -> `{"ok":true}`.

---

## 1. `POST /api/quote` — read-only pricing engine

Body: `{"customerId":int,"warehouseId":int,"items":[{"sku":string,"qty":int}],"couponCode":string|null}`

Database reads (exactly these, in this order):

1. `customer` joined to `customer_tier` by `tier_id`.
2. `product` for every SKU in the request (single query, `sku = ANY($1)`).
3. `inventory` for (warehouse, product) pairs (single query).
4. `discount_rule` rows that are active today (single query).
5. `tax_rate` rows for the customer's region (single query).
6. `coupon` by code, only when `couponCode` is non-null.

Then run the **pricing engine** (pure CPU, no further IO) described in §3 and
return the invoice of §4. Nothing is written.

## 2. `POST /api/checkout` — the full write transaction

Same body as `/api/quote`. Runs inside **one** serialisable-read-committed
transaction:

1. `BEGIN`
2. All six reads of §1, except `inventory` is `SELECT ... FOR UPDATE`
   ordered by `product_id` (deadlock avoidance).
3. Availability check: every line needs `on_hand - reserved >= qty`, else roll
   back and return `409` with `{"error":"insufficient_stock","sku":...}`.
4. Pricing engine (§3).
5. Writes, in this order:
   - `INSERT INTO "order" (...) RETURNING id`
   - `INSERT INTO order_item` — one multi-row insert for all lines
   - `UPDATE inventory SET reserved = reserved + $qty` per line
   - `INSERT INTO ledger_entry` — two rows (debit revenue, credit tax payable)
   - `UPDATE coupon SET times_used = times_used + 1` when a coupon applied
   - `INSERT INTO loyalty_transaction` for points earned
6. `COMMIT`

Returns the §4 invoice plus `"orderId"`.

## 3. Pricing engine (identical in all ten implementations)

For each line, in SKU order as supplied:

1. `base = product.unit_price_cents * qty`
2. **Candidate discounts** — evaluate every active `discount_rule` whose scope
   matches the line, producing a candidate cent amount each:
   - `scope='tier'`   : matches when `rule.tier_id = customer.tier_id`
   - `scope='category'`: matches when `rule.category = product.category`
   - `scope='volume'` : matches when `qty >= rule.min_qty`
   - `scope='sku'`    : matches when `rule.sku = product.sku`
   - amount = `base * rule.percent_bp / 10000` (basis points), capped at
     `rule.max_discount_cents` when that is non-null.
3. **Stacking**: rules carry `stackable`. Take the single largest
   non-stackable candidate, then add every stackable candidate. The line
   discount is the sum, capped at 60% of `base`.
4. `line_net = base - line_discount`
5. **Tax**: pick the `tax_rate` row matching the product category, else the
   row with `category IS NULL` (the region default). If the product is
   `tax_exempt`, the rate is 0. `line_tax = round_half_up(line_net * rate_bp / 10000)`.
6. **Loyalty**: `points = floor(line_net / 100) * tier.points_multiplier`.

Order level, after all lines:

7. `subtotal = sum(line_net)`
8. **Coupon** (when supplied and valid — not expired, `times_used < max_uses`,
   `subtotal >= min_spend_cents`): `coupon_discount = min(subtotal * percent_bp / 10000,
   max_discount_cents)`. An invalid coupon is *not* an error; it is reported as
   `"couponApplied": false` with a `couponRejectedReason`.
   The coupon discount is spread across lines **pro rata by `line_net`**, with the
   remainder cents assigned to the largest line, and the per-line tax is
   **recomputed** on the reduced amount.
9. **Shipping**: total weight = `sum(product.weight_grams * qty)`. Bands:
   `<= 500g` 499c, `<= 2000g` 899c, `<= 10000g` 1499c, above 2499c.
   Free when `subtotal - coupon_discount >= tier.free_shipping_threshold_cents`.
10. `tax_total = sum(recomputed line_tax)`, `total = subtotal - coupon_discount + tax_total + shipping`
11. `points_earned = sum(line points)`, plus `tier.bonus_points` when
    `total >= 50000`.

## 4. Invoice response shape

```json
{
  "orderId": 1234,
  "customerId": 7,
  "tier": "gold",
  "lines": [{"sku":"...","qty":2,"unitPriceCents":1999,"baseCents":3998,
             "discountCents":400,"netCents":3598,"taxCents":288,"pointsEarned":35,
             "appliedRules":["tier:3","volume:11"]}],
  "subtotalCents": 3598, "couponApplied": true, "couponCode": "SAVE10",
  "couponRejectedReason": null, "couponDiscountCents": 359,
  "taxTotalCents": 259, "shippingCents": 499, "totalCents": 3997,
  "pointsEarned": 35, "totalWeightGrams": 1200
}
```

`appliedRules` lists `"<scope>:<rule id>"` for every rule that contributed,
sorted ascending by rule id.

## 5. `GET /api/customers/:id/summary` — read-heavy aggregation

Four queries, then in-process aggregation:

1. customer + tier
2. last 50 orders (`ORDER BY created_at DESC LIMIT 50`)
3. order items for those orders (single query, `order_id = ANY($1)`)
4. loyalty transactions for the customer, last 100

Returns lifetime value, order count, average order value, the top 5 categories
by net spend (ties broken by category name), the current points balance, and a
`segment` derived as: `champion` when lifetime >= 500000c and orders >= 20,
`loyal` when orders >= 10, `promising` when orders >= 3, else `new`.
