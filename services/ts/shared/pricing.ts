// Pricing engine — transliteration of spec/SPEC.md §3. Pure, no IO.

export interface Tier {
  id: number; name: string; pointsMultiplier: number;
  freeShipThreshold: number; bonusPoints: number;
}
export interface CustomerRow { id: number; region: string; tierId: number }
export interface Product {
  id: number; sku: string; category: string;
  unitPriceCents: number; weightGrams: number; taxExempt: boolean;
}
export interface Rule {
  id: number; scope: string; tierId: number | null; category: string | null;
  minQty: number | null; sku: string | null; percentBp: number;
  maxDiscountCents: number | null; stackable: boolean;
}
export interface TaxRate { id: number; category: string | null; rateBp: number }
export interface Coupon {
  id: number; code: string; percentBp: number; maxDiscountCents: number;
  minSpendCents: number; maxUses: number; timesUsed: number; expiresOn: string;
}
export interface ReqItem { sku: string; qty: number }
export interface Request {
  customerId: number; warehouseId: number; items: ReqItem[]; couponCode?: string | null;
}
export interface Line {
  sku: string; qty: number; unitPriceCents: number; baseCents: number;
  discountCents: number; netCents: number; taxCents: number;
  pointsEarned: number; appliedRules: string[];
}
export interface Invoice {
  orderId: number; customerId: number; tier: string; lines: Line[];
  subtotalCents: number; couponApplied: boolean; couponCode: string | null;
  couponRejectedReason: string | null; couponDiscountCents: number;
  taxTotalCents: number; shippingCents: number; totalCents: number;
  pointsEarned: number; totalWeightGrams: number;
}

export const TODAY = "2026-09-21";

/** multiply by basis points, half-up on the final cent */
function mulBP(base: number, bp: number): number {
  return Math.floor((base * bp + 5000) / 10000);
}

function ruleMatches(r: Rule, tierId: number, p: Product, qty: number): boolean {
  switch (r.scope) {
    case "tier": return r.tierId === tierId;
    case "category": return r.category === p.category;
    case "volume": return r.minQty !== null && qty >= r.minQty;
    case "sku": return r.sku === p.sku;
    default: return false;
  }
}

function rateFor(taxes: TaxRate[], p: Product): number {
  if (p.taxExempt) return 0;
  let def = 0;
  for (const t of taxes) {
    if (t.category !== null && t.category === p.category) return t.rateBp;
    if (t.category === null) def = t.rateBp;
  }
  return def;
}

function shippingFor(weight: number): number {
  if (weight <= 500) return 499;
  if (weight <= 2000) return 899;
  if (weight <= 10000) return 1499;
  return 2499;
}

export interface PricedLine extends Line { productId: number; category: string }

export interface PriceResult extends Invoice {
  lines: PricedLine[];
  couponId: number | null;
}

export function price(
  cust: CustomerRow, tier: Tier, items: ReqItem[],
  products: Map<string, Product>, rules: Rule[], taxes: TaxRate[],
  coupon: Coupon | null, today: string,
): PriceResult {
  const lines: PricedLine[] = [];
  let subtotal = 0, weight = 0, points = 0;

  for (const it of items) {
    const p = products.get(it.sku)!;
    const base = p.unitPriceCents * it.qty;

    let bestFixed = 0, bestFixedId = -1, stackSum = 0;
    for (const r of rules) {
      if (!ruleMatches(r, cust.tierId, p, it.qty)) continue;
      let amt = mulBP(base, r.percentBp);
      if (r.maxDiscountCents !== null && amt > r.maxDiscountCents) amt = r.maxDiscountCents;
      if (r.stackable) stackSum += amt;
      else if (amt > bestFixed || bestFixedId === -1) { bestFixed = amt; bestFixedId = r.id; }
    }

    const contributing = rules
      .filter((r) => ruleMatches(r, cust.tierId, p, it.qty) && (r.stackable || r.id === bestFixedId))
      .sort((a, b) => a.id - b.id)
      .map((r) => `${r.scope}:${r.id}`);

    let disc = bestFixed + stackSum;
    const cap = mulBP(base, 6000);
    if (disc > cap) disc = cap;
    const net = base - disc;
    const pts = Math.floor(net / 100) * tier.pointsMultiplier;

    lines.push({
      sku: p.sku, qty: it.qty, unitPriceCents: p.unitPriceCents, baseCents: base,
      discountCents: disc, netCents: net, taxCents: 0, pointsEarned: pts,
      appliedRules: contributing, productId: p.id, category: p.category,
    });
    subtotal += net;
    weight += p.weightGrams * it.qty;
    points += pts;
  }

  let couponId: number | null = null;
  let couponCode: string | null = null;
  let reject: string | null = null;
  let couponDiscount = 0;
  let applied = false;

  if (coupon) {
    couponCode = coupon.code;
    if (today > coupon.expiresOn) reject = "expired";
    else if (coupon.timesUsed >= coupon.maxUses) reject = "exhausted";
    else if (subtotal < coupon.minSpendCents) reject = "min_spend_not_met";
    else {
      applied = true;
      couponDiscount = Math.min(mulBP(subtotal, coupon.percentBp), coupon.maxDiscountCents);
      couponId = coupon.id;
    }
  }

  const shares = new Array(lines.length).fill(0);
  if (applied && couponDiscount > 0 && subtotal > 0) {
    let sum = 0, maxIdx = 0, maxNet = -1;
    for (let i = 0; i < lines.length; i++) {
      shares[i] = Math.floor((couponDiscount * lines[i].netCents) / subtotal);
      sum += shares[i];
      if (lines[i].netCents > maxNet) { maxNet = lines[i].netCents; maxIdx = i; }
    }
    shares[maxIdx] += couponDiscount - sum;
  }

  let taxTotal = 0;
  for (let i = 0; i < lines.length; i++) {
    const taxable = lines[i].netCents - shares[i];
    lines[i].taxCents = mulBP(taxable, rateFor(taxes, products.get(lines[i].sku)!));
    taxTotal += lines[i].taxCents;
  }

  let shipping = shippingFor(weight);
  if (subtotal - couponDiscount >= tier.freeShipThreshold) shipping = 0;
  const total = subtotal - couponDiscount + taxTotal + shipping;
  if (total >= 50000) points += tier.bonusPoints;

  return {
    orderId: 0, customerId: cust.id, tier: tier.name, lines,
    subtotalCents: subtotal, couponApplied: applied, couponCode,
    couponRejectedReason: reject, couponDiscountCents: couponDiscount,
    taxTotalCents: taxTotal, shippingCents: shipping, totalCents: total,
    pointsEarned: points, totalWeightGrams: weight, couponId,
  };
}

export function segmentFor(lifetime: number, orders: number): string {
  if (lifetime >= 500000 && orders >= 20) return "champion";
  if (orders >= 10) return "loyal";
  if (orders >= 3) return "promising";
  return "new";
}
