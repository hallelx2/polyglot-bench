/**
 * Every statement the service issues, in the order spec/SPEC.md prescribes.
 * Bun.sql tagged templates parameterise automatically; `sql(array)` expands an
 * array into an IN-list, which is how Bun wants a set of values passed.
 */
import {
  price, segmentFor, TODAY,
  type Coupon, type CustomerRow, type Invoice, type PriceResult,
  type Product, type Request, type Rule, type TaxRate, type Tier,
} from "../../../shared/pricing.ts";
import { day, n, NotFound, sql, StockError } from "./sql.ts";

/** The pool, a reserved connection and a transaction all accept the same tag. */
type Conn = any;

interface Ref {
  cust: CustomerRow; tier: Tier; products: Map<string, Product>;
  rules: Rule[]; taxes: TaxRate[]; coupon: Coupon | null; ids: number[];
}

async function loadRef(c: Conn, req: Request): Promise<Ref> {
  const cr = await c`
    SELECT c.id, c.region, c.tier_id, t.name, t.points_multiplier,
           t.free_shipping_threshold_cents, t.bonus_points
      FROM customer c JOIN customer_tier t ON t.id = c.tier_id
     WHERE c.id = ${req.customerId}`;
  if (cr.length === 0) throw new NotFound();
  const r0 = cr[0];
  const cust: CustomerRow = { id: n(r0.id), region: r0.region, tierId: n(r0.tier_id) };
  const tier: Tier = {
    id: n(r0.tier_id), name: r0.name, pointsMultiplier: n(r0.points_multiplier),
    freeShipThreshold: n(r0.free_shipping_threshold_cents), bonusPoints: n(r0.bonus_points),
  };

  const skus = req.items.map((i) => i.sku);
  const pr = await c`
    SELECT id, sku, category, unit_price_cents, weight_grams, tax_exempt
      FROM product WHERE sku IN ${c(skus)}`;
  const products = new Map<string, Product>();
  const ids: number[] = [];
  for (const p of pr) {
    products.set(p.sku, {
      id: n(p.id), sku: p.sku, category: p.category,
      unitPriceCents: n(p.unit_price_cents), weightGrams: n(p.weight_grams),
      taxExempt: p.tax_exempt,
    });
    ids.push(n(p.id));
  }
  for (const it of req.items) if (!products.has(it.sku)) throw new NotFound();
  ids.sort((a, b) => a - b);

  const rr = await c`
    SELECT id, scope, tier_id, category, min_qty, sku, percent_bp,
           max_discount_cents, stackable
      FROM discount_rule WHERE active_from <= ${TODAY} AND active_to >= ${TODAY}`;
  const rules: Rule[] = rr.map((r: any) => ({
    id: n(r.id), scope: r.scope, tierId: r.tier_id === null ? null : n(r.tier_id),
    category: r.category, minQty: r.min_qty === null ? null : n(r.min_qty),
    sku: r.sku, percentBp: n(r.percent_bp),
    maxDiscountCents: r.max_discount_cents === null ? null : n(r.max_discount_cents),
    stackable: r.stackable,
  }));

  const tr = await c`SELECT id, category, rate_bp FROM tax_rate WHERE region = ${cust.region}`;
  const taxes: TaxRate[] = tr.map((t: any) => ({
    id: n(t.id), category: t.category, rateBp: n(t.rate_bp),
  }));

  let coupon: Coupon | null = null;
  if (req.couponCode != null) {
    const cp = await c`
      SELECT id, code, percent_bp, max_discount_cents, min_spend_cents,
             max_uses, times_used, expires_on
        FROM coupon WHERE code = ${req.couponCode}`;
    if (cp.length > 0) {
      const x = cp[0];
      coupon = {
        id: n(x.id), code: x.code, percentBp: n(x.percent_bp),
        maxDiscountCents: n(x.max_discount_cents), minSpendCents: n(x.min_spend_cents),
        maxUses: n(x.max_uses), timesUsed: n(x.times_used), expiresOn: day(x.expires_on),
      };
    }
  }
  return { cust, tier, products, rules, taxes, coupon, ids };
}

/** Internal bookkeeping fields never leave the process. */
function strip(p: PriceResult): Invoice {
  const { couponId, ...rest } = p;
  return { ...rest, lines: p.lines.map(({ productId, category, ...l }) => l) };
}

export async function quote(req: Request): Promise<Invoice> {
  const c = await sql.reserve();
  try {
    const r = await loadRef(c, req);
    await c`SELECT product_id, on_hand, reserved FROM inventory
             WHERE warehouse_id = ${req.warehouseId} AND product_id IN ${c(r.ids)}
             ORDER BY product_id`;
    return strip(price(r.cust, r.tier, req.items, r.products, r.rules, r.taxes,
      r.coupon, TODAY));
  } finally { c.release(); }
}

export async function checkout(req: Request): Promise<Invoice> {
  return await sql.begin(async (tx: Conn) => {
    const r = await loadRef(tx, req);

    const want = new Map<number, number>();
    const skuOf = new Map<number, string>();
    for (const it of req.items) {
      const p = r.products.get(it.sku)!;
      want.set(p.id, (want.get(p.id) ?? 0) + it.qty);
      skuOf.set(p.id, p.sku);
    }

    // Locked in product-id order so two concurrent carts cannot deadlock.
    const rows = await tx`
      SELECT product_id, on_hand, reserved FROM inventory
       WHERE warehouse_id = ${req.warehouseId} AND product_id IN ${tx(r.ids)}
       ORDER BY product_id FOR UPDATE`;
    for (const row of rows) {
      const pid = n(row.product_id);
      if (n(row.on_hand) - n(row.reserved) < (want.get(pid) ?? 0)) {
        throw new StockError(skuOf.get(pid)!);
      }
    }

    const p = price(r.cust, r.tier, req.items, r.products, r.rules, r.taxes,
      r.coupon, TODAY);

    const o = await tx`
      INSERT INTO "order" (customer_id, warehouse_id, subtotal_cents, coupon_id,
        coupon_discount_cents, tax_total_cents, shipping_cents, total_cents, points_earned)
      VALUES (${req.customerId}, ${req.warehouseId}, ${p.subtotalCents}, ${p.couponId},
              ${p.couponDiscountCents}, ${p.taxTotalCents}, ${p.shippingCents},
              ${p.totalCents}, ${p.pointsEarned})
      RETURNING id`;
    const orderId = n(o[0].id);
    p.orderId = orderId;

    const itemRows = p.lines.map((l) => ({
      order_id: orderId, product_id: l.productId, sku: l.sku, category: l.category,
      qty: l.qty, unit_price_cents: l.unitPriceCents, discount_cents: l.discountCents,
      net_cents: l.netCents, tax_cents: l.taxCents,
    }));
    await tx`INSERT INTO order_item ${tx(itemRows)}`;

    for (const pid of r.ids) {
      await tx`UPDATE inventory SET reserved = reserved + ${want.get(pid)!}
                WHERE warehouse_id = ${req.warehouseId} AND product_id = ${pid}`;
    }
    await tx`
      INSERT INTO ledger_entry (order_id, account, debit_cents, credit_cents)
      VALUES (${orderId}, 'revenue', ${p.subtotalCents - p.couponDiscountCents}, 0),
             (${orderId}, 'tax_payable', 0, ${p.taxTotalCents})`;
    if (p.couponId !== null) {
      await tx`UPDATE coupon SET times_used = times_used + 1 WHERE id = ${p.couponId}`;
    }
    await tx`
      INSERT INTO loyalty_transaction (customer_id, order_id, points, kind)
      VALUES (${req.customerId}, ${orderId}, ${p.pointsEarned}, 'earn')`;

    return strip(p);
  });
}

export async function summary(customerId: number) {
  const c = await sql.reserve();
  try {
    const cr = await c`
      SELECT t.name FROM customer c JOIN customer_tier t ON t.id = c.tier_id
       WHERE c.id = ${customerId}`;
    if (cr.length === 0) throw new NotFound();

    const or = await c`
      SELECT id, total_cents, created_at FROM "order"
       WHERE customer_id = ${customerId} ORDER BY created_at DESC LIMIT 50`;
    const ids = or.map((r: any) => n(r.id));
    let lifetime = 0;
    for (const r of or) lifetime += n(r.total_cents);
    const orderCount = ids.length;

    const byCat = new Map<string, number>();
    if (ids.length > 0) {
      const ir = await c`
        SELECT category, net_cents FROM order_item WHERE order_id IN ${c(ids)}`;
      for (const r of ir) byCat.set(r.category, (byCat.get(r.category) ?? 0) + n(r.net_cents));
    }
    const topCategories = [...byCat.entries()]
      .map(([category, netCents]) => ({ category, netCents }))
      .sort((a, b) => b.netCents - a.netCents || a.category.localeCompare(b.category))
      .slice(0, 5);

    const lr = await c`
      SELECT points FROM loyalty_transaction WHERE customer_id = ${customerId}
       ORDER BY created_at DESC LIMIT 100`;
    let pointsBalance = 0;
    for (const r of lr) pointsBalance += n(r.points);

    return {
      customerId, tier: cr[0].name, orderCount,
      lifetimeValueCents: lifetime,
      avgOrderValueCents: orderCount > 0 ? Math.floor(lifetime / orderCount) : 0,
      topCategories, pointsBalance,
      segment: segmentFor(lifetime, orderCount),
      lastOrderAt: or.length > 0 ? new Date(or[0].created_at).toISOString() : null,
    };
  } finally { c.release(); }
}
