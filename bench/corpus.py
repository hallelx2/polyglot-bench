#!/usr/bin/env python3
"""Deterministic request corpus: shared by the conformance check and the load
generator, so both exercise exactly the same distribution of work."""
import json, os, random, sys

R = random.Random(777)
N_PRODUCTS, N_CUSTOMERS, N_COUPONS = 5000, 50000, 500

def sku(i): return f"SKU-{i:06d}"

def gen_price_requests(n):
    out = []
    for k in range(n):
        # a spread of cart shapes: single line .. ten lines
        nlines = R.choice([1, 1, 2, 2, 3, 3, 4, 5, 8, 10])
        picked, items = set(), []
        while len(items) < nlines:
            pid = R.randint(1, N_PRODUCTS)
            if pid in picked:
                continue
            picked.add(pid)
            # qty spread straddles every volume break (3, 5, 10, 25)
            items.append({"sku": sku(pid),
                          "qty": R.choice([1, 2, 3, 4, 5, 9, 10, 12, 25, 30])})
        coupon = None
        r = R.random()
        if r < 0.45:
            coupon = f"BENCH{R.randint(1, N_COUPONS):04d}"
        elif r < 0.55:
            coupon = "NO-SUCH-COUPON"
        out.append({
            "customerId": R.randint(1, N_CUSTOMERS),
            "warehouseId": R.choice([1, 2]),
            "items": items,
            "couponCode": coupon,
        })
    return out

def gen_summary_ids(n):
    # bias toward customers that actually have orders
    return [R.randint(1, N_CUSTOMERS) for _ in range(n)]

if __name__ == "__main__":
    size = int(sys.argv[1]) if len(sys.argv) > 1 else 2000
    here = os.path.dirname(os.path.abspath(__file__))
    corpus = {
        "price": gen_price_requests(size),
        "summary": gen_summary_ids(size),
    }
    path = os.path.join(here, "corpus.json")
    with open(path, "w") as f:
        json.dump(corpus, f)
    print(f"wrote {path}: {len(corpus['price'])} price requests, "
          f"{len(corpus['summary'])} summary ids")
