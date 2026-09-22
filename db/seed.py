#!/usr/bin/env python3
"""Deterministic dataset generator. Emits COPY-friendly TSV into db/data/."""
import os, random, datetime as dt

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
os.makedirs(OUT, exist_ok=True)
R = random.Random(20260921)

N_CUSTOMERS  = 50_000
N_PRODUCTS   = 5_000
N_WAREHOUSES = 2
N_ORDERS     = 200_000
N_COUPONS    = 500

CATEGORIES = ["electronics","apparel","grocery","books","home","toys","beauty","sports","office","garden"]
REGIONS    = ["NG-LA","NG-AB","US-CA","US-NY","US-TX","UK-LDN","DE-BE","FR-PA","KE-NBO","ZA-JHB"]
TIERS = [
    (1,"bronze",  1,  1_000_00,   0),
    (2,"silver",  2,    800_00, 250),
    (3,"gold",    3,    500_00, 750),
    (4,"platinum",5,      0,   2000),
]

def w(name, rows):
    with open(os.path.join(OUT, name), "w") as f:
        for r in rows:
            f.write("\t".join("\\N" if v is None else
                              ("t" if v is True else "f" if v is False else str(v))
                              for v in r) + "\n")

w("customer_tier.tsv", TIERS)

w("customer.tsv", (
    (i, f"user{i}@bench.local", f"Customer {i}", REGIONS[i % len(REGIONS)],
     TIERS[min(3, int(R.paretovariate(1.6)) - 1 if R.random() < 0.9 else 3)][0])
    for i in range(1, N_CUSTOMERS + 1)))

products = []
for i in range(1, N_PRODUCTS + 1):
    cat = CATEGORIES[i % len(CATEGORIES)]
    products.append((i, f"SKU-{i:06d}", f"Product {i}", cat,
                     R.randint(199, 249_99), R.randint(50, 12_000),
                     cat == "grocery" and R.random() < 0.4))
w("product.tsv", products)

w("inventory.tsv", ((wh, p[0], R.randint(5_000, 50_000), 0)
                    for wh in range(1, N_WAREHOUSES + 1) for p in products))

TODAY = dt.date(2026, 9, 21)
FROM, TO = TODAY - dt.timedelta(days=30), TODAY + dt.timedelta(days=180)
rules, rid = [], 0
for t in TIERS:                                    # tier rules
    rid += 1; rules.append((rid,"tier",t[0],None,None,None, 200*t[0], 50_00, False, FROM, TO))
for c in CATEGORIES:                               # category promos
    rid += 1; rules.append((rid,"category",None,c,None,None, R.choice([300,500,700]),
                            R.choice([None, 80_00]), R.random() < 0.5, FROM, TO))
for mq, bp in ((3,300),(5,500),(10,900),(25,1400)):# volume breaks
    rid += 1; rules.append((rid,"volume",None,None,mq,None, bp, 120_00, True, FROM, TO))
for i in range(1, 21):                             # sku specials
    rid += 1; rules.append((rid,"sku",None,None,None, f"SKU-{R.randint(1,N_PRODUCTS):06d}",
                            R.choice([400,800,1200]), 60_00, R.random() < 0.3, FROM, TO))
w("discount_rule.tsv", rules)

taxes, tid = [], 0
for reg in REGIONS:
    tid += 1; taxes.append((tid, reg, None, R.choice([500,750,1000,1500,2000])))
    for c in R.sample(CATEGORIES, 4):
        tid += 1; taxes.append((tid, reg, c, R.choice([0,250,500,1200])))
w("tax_rate.tsv", taxes)

w("coupon.tsv", ((i, f"BENCH{i:04d}", R.choice([500,1000,1500,2000]),
                  R.choice([20_00,50_00,100_00]), R.choice([0,50_00,200_00]),
                  1_000_000_000, 0, TODAY + dt.timedelta(days=90))
                 for i in range(1, N_COUPONS + 1)))

# ---- historical orders so /summary has real work to do -------------------
orders, items, loyalty = [], [], []
oid = 0; iid = 0; lid = 0
base_ts = dt.datetime(2026, 3, 1)
for _ in range(N_ORDERS):
    oid += 1
    cust = R.randint(1, N_CUSTOMERS)
    ts = base_ts + dt.timedelta(minutes=R.randint(0, 290_000))
    nlines = R.randint(1, 5)
    sub = tax = 0
    for _ in range(nlines):
        iid += 1
        p = products[R.randrange(N_PRODUCTS)]
        qty = R.randint(1, 8)
        basec = p[4] * qty
        disc = int(basec * R.choice([0, 0.05, 0.1, 0.15]))
        net = basec - disc
        tx = int(net * R.choice([0, 0.05, 0.075, 0.2]))
        sub += net; tax += tx
        items.append((iid, oid, p[0], p[1], p[3], qty, p[4], disc, net, tx))
    ship = R.choice([0, 499, 899, 1499])
    pts = sub // 100
    orders.append((oid, cust, R.randint(1, N_WAREHOUSES), sub, None, 0, tax, ship,
                   sub + tax + ship, pts, ts.isoformat(sep=" ")))
    lid += 1
    loyalty.append((lid, cust, oid, pts, "earn", ts.isoformat(sep=" ")))
w("order.tsv", orders)
w("order_item.tsv", items)
w("loyalty_transaction.tsv", loyalty)
print(f"customers={N_CUSTOMERS} products={N_PRODUCTS} rules={len(rules)} "
      f"taxes={len(taxes)} orders={len(orders)} items={len(items)}")
