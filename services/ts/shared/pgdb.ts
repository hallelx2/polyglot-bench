// node-postgres data layer — used by the Hono/Bun and Fastify/Node services.
import pg from "pg";
import {
  price, segmentFor, TODAY,
  type Coupon, type CustomerRow, type Invoice, type PriceResult,
  type Product, type Request, type Rule, type TaxRate, type Tier,
} from "./pricing.ts";

// keep INT8 as a JS number (all ids here are far below 2^53)
pg.types.setTypeParser(20, (v: string) => parseInt(v, 10));

export class NotFound extends Error { constructor() { super("not_found"); } }
export class StockError extends Error {
  sku: string;
  constructor(sku: string) { super("insufficient_stock"); this.sku = sku; }
}

const POOL_SIZE = parseInt(process.env.DB_POOL_SIZE ?? "20", 10);

export const pool = new pg.Pool({
  connectionString: process.env.DATABASE_URL,
  max: POOL_SIZE,
  min: POOL_SIZE,
  idleTimeoutMillis: 0,
  allowExitOnIdle: false,
});

const Q_CUSTOMER = `SELECT c.id, c.region, c.tier_id, t.name, t.points_multiplier,
   t.free_shipping_threshold_cents, t.bonus_points
   FROM customer c JOIN customer_tier t ON t.id = c.tier_id WHERE c.id = $1`;
const Q_PRODUCTS = `SELECT id, sku, category, unit_price_cents, weight_grams, tax_exempt
   FROM product WHERE sku = ANY($1)`;
const Q_RULES = `SELECT id, scope, tier_id, category, min_qty, sku, percent_bp,
   max_discount_cents, stackable FROM discount_rule
   WHERE active_from <= $1 AND active_to >= $1`;
const Q_TAXES = `SELECT id, category, rate_bp FROM tax_rate WHERE region = $1`;
const Q_COUPON = `SELECT id, code, percent_bp, max_discount_cents, min_spend_cents,
   max_uses, times_used, expires_on FROM coupon WHERE code = $1`;

interface Ref {
  cust: CustomerRow; tier: Tier; products: Map<string, Product>;
  rules: Rule[]; taxes: TaxRate[]; coupon: Coupon | null; ids: number[];
}

async function loadRef(c: pg.PoolClient, req: Request): Promise<Ref> {
  const cr = await c.query(Q_CUSTOMER, [req.customerId]);
  if (cr.rowCount === 0) throw new NotFound();
  const r0 = cr.rows[0];
  const cust: CustomerRow = { id: r0.id, region: r0.region, tierId: r0.tier_id };
  const tier: Tier = {
    id: r0.tier_id, name: r0.name, pointsMultiplier: r0.points_multiplier,
    freeShipThreshold: r0.free_shipping_threshold_cents, bonusPoints: r0.bonus_points,
  };

  const skus = req.items.map((i) => i.sku);
  const pr = await c.query(Q_PRODUCTS, [skus]);
  const products = new Map<string, Product>();
  const ids: number[] = [];
  for (const p of pr.rows) {
    products.set(p.sku, {
      id: p.id, sku: p.sku, category: p.category,
      unitPriceCents: p.unit_price_cents, weightGrams: p.weight_grams,
      taxExempt: p.tax_exempt,
    });
    ids.push(p.id);
  }
  for (const it of req.items) if (!products.has(it.sku)) throw new NotFound();
  ids.sort((a, b) => a - b);

  const rr = await c.query(Q_RULES, [TODAY]);
  const rules: Rule[] = rr.rows.map((r) => ({
    id: r.id, scope: r.scope, tierId: r.tier_id, category: r.category,
    minQty: r.min_qty, sku: r.sku, percentBp: r.percent_bp,
    maxDiscountCents: r.max_discount_cents, stackable: r.stackable,
  }));

  const tr = await c.query(Q_TAXES, [cust.region]);
  const taxes: TaxRate[] = tr.rows.map((t) => ({
    id: t.id, category: t.category, rateBp: t.rate_bp,
  }));

  let coupon: Coupon | null = null;
  if (req.couponCode != null) {
    const cp = await c.query(Q_COUPON, [req.couponCode]);
    if (cp.rowCount! > 0) {
      const x = cp.rows[0];
      coupon = {
        id: x.id, code: x.code, percentBp: x.percent_bp,
        maxDiscountCents: x.max_discount_cents, minSpendCents: x.min_spend_cents,
        maxUses: x.max_uses, timesUsed: x.times_used,
        expiresOn: x.expires_on.toISOString().slice(0, 10),
      };
    }
  }
  return { cust, tier, products, rules, taxes, coupon, ids };
}

function strip(p: PriceResult): Invoice {
  const { couponId, ...rest } = p;
  return { ...rest, lines: p.lines.map(({ productId, category, ...l }) => l) };
}

export async function quote(req: Request): Promise<Invoice> {
  const c = await pool.connect();
  try {
    const r = await loadRef(c, req);
    await c.query(
      `SELECT product_id, on_hand, reserved FROM inventory
       WHERE warehouse_id = $1 AND product_id = ANY($2) ORDER BY product_id`,
      [req.warehouseId, r.ids],
    );
    return strip(price(r.cust, r.tier, req.items, r.products, r.rules, r.taxes,
      r.coupon, TODAY));
  } finally { c.release(); }
}

export async function checkout(req: Request): Promise<Invoice> {
  const c = await pool.connect();
  try {
    await c.query("BEGIN");
    const r = await loadRef(c, req);

    const want = new Map<number, number>();
    const skuOf = new Map<number, string>();
    for (const it of req.items) {
      const p = r.products.get(it.sku)!;
      want.set(p.id, (want.get(p.id) ?? 0) + it.qty);
      skuOf.set(p.id, p.sku);
    }

    const inv0 = await c.query(
      `SELECT product_id, on_hand, reserved FROM inventory
       WHERE warehouse_id = $1 AND product_id = ANY($2)
       ORDER BY product_id FOR UPDATE`,
      [req.warehouseId, r.ids],
    );
    for (const row of inv0.rows) {
      if (row.on_hand - row.reserved < (want.get(row.product_id) ?? 0)) {
        throw new StockError(skuOf.get(row.product_id)!);
      }
    }

    const p = price(r.cust, r.tier, req.items, r.products, r.rules, r.taxes,
      r.coupon, TODAY);

    const o = await c.query(
      `INSERT INTO "order" (customer_id, warehouse_id, subtotal_cents, coupon_id,
        coupon_discount_cents, tax_total_cents, shipping_cents, total_cents, points_earned)
       VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9) RETURNING id`,
      [req.customerId, req.warehouseId, p.subtotalCents, p.couponId,
        p.couponDiscountCents, p.taxTotalCents, p.shippingCents, p.totalCents,
        p.pointsEarned],
    );
    const orderId = o.rows[0].id as number;
    p.orderId = orderId;

    const vals: string[] = [];
    const args: unknown[] = [];
    p.lines.forEach((l, i) => {
      const b = i * 9;
      vals.push(`($${b+1},$${b+2},$${b+3},$${b+4},$${b+5},$${b+6},$${b+7},$${b+8},$${b+9})`);
      args.push(orderId, l.productId, l.sku, l.category, l.qty,
        l.unitPriceCents, l.discountCents, l.netCents, l.taxCents);
    });
    await c.query(
      `INSERT INTO order_item (order_id, product_id, sku, category, qty,
        unit_price_cents, discount_cents, net_cents, tax_cents) VALUES ${vals.join(",")}`,
      args,
    );

    for (const pid of r.ids) {
      await c.query(
        `UPDATE inventory SET reserved = reserved + $1
         WHERE warehouse_id = $2 AND product_id = $3`,
        [want.get(pid), req.warehouseId, pid],
      );
    }
    await c.query(
      `INSERT INTO ledger_entry (order_id, account, debit_cents, credit_cents)
       VALUES ($1,'revenue',$2,0), ($1,'tax_payable',0,$3)`,
      [orderId, p.subtotalCents - p.couponDiscountCents, p.taxTotalCents],
    );
    if (p.couponId !== null) {
      await c.query(`UPDATE coupon SET times_used = times_used + 1 WHERE id = $1`,
        [p.couponId]);
    }
    await c.query(
      `INSERT INTO loyalty_transaction (customer_id, order_id, points, kind)
       VALUES ($1,$2,$3,'earn')`,
      [req.customerId, orderId, p.pointsEarned],
    );
    await c.query("COMMIT");
    return strip(p);
  } catch (e) {
    await c.query("ROLLBACK").catch(() => {});
    throw e;
  } finally { c.release(); }
}

export async function summary(customerId: number) {
  const c = await pool.connect();
  try {
    const cr = await c.query(
      `SELECT t.name FROM customer c JOIN customer_tier t ON t.id = c.tier_id
       WHERE c.id = $1`, [customerId]);
    if (cr.rowCount === 0) throw new NotFound();

    const or = await c.query(
      `SELECT id, total_cents, created_at FROM "order"
       WHERE customer_id = $1 ORDER BY created_at DESC LIMIT 50`, [customerId]);
    const ids = or.rows.map((r) => r.id);
    let lifetime = 0;
    for (const r of or.rows) lifetime += r.total_cents;
    const orderCount = ids.length;

    const byCat = new Map<string, number>();
    if (ids.length > 0) {
      const ir = await c.query(
        `SELECT category, net_cents FROM order_item WHERE order_id = ANY($1)`, [ids]);
      for (const r of ir.rows) byCat.set(r.category, (byCat.get(r.category) ?? 0) + r.net_cents);
    }
    const topCategories = [...byCat.entries()]
      .map(([category, netCents]) => ({ category, netCents }))
      .sort((a, b) => b.netCents - a.netCents || a.category.localeCompare(b.category))
      .slice(0, 5);

    const lr = await c.query(
      `SELECT points FROM loyalty_transaction WHERE customer_id = $1
       ORDER BY created_at DESC LIMIT 100`, [customerId]);
    let pointsBalance = 0;
    for (const r of lr.rows) pointsBalance += r.points;

    return {
      customerId, tier: cr.rows[0].name, orderCount,
      lifetimeValueCents: lifetime,
      avgOrderValueCents: orderCount > 0 ? Math.floor(lifetime / orderCount) : 0,
      topCategories, pointsBalance,
      segment: segmentFor(lifetime, orderCount),
      lastOrderAt: or.rows.length > 0 ? or.rows[0].created_at.toISOString() : null,
    };
  } finally { c.release(); }
}
