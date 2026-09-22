#!/usr/bin/env bash
# Rebuild the benchmark database from scratch: schema + bulk COPY of the seed.
set -euo pipefail
cd "$(dirname "$0")/.."
docker compose up -d db
echo "waiting for postgres..."
until docker exec pgbench-db pg_isready -U bench -d bench >/dev/null 2>&1; do sleep 1; done

PSQL=(docker exec -i pgbench-db psql -v ON_ERROR_STOP=1 -U bench -d bench -q)
"${PSQL[@]}" < db/schema.sql

declare -A COLS=(
  [customer_tier]="id,name,points_multiplier,free_shipping_threshold_cents,bonus_points"
  [customer]="id,email,full_name,region,tier_id"
  [product]="id,sku,name,category,unit_price_cents,weight_grams,tax_exempt"
  [inventory]="warehouse_id,product_id,on_hand,reserved"
  [discount_rule]="id,scope,tier_id,category,min_qty,sku,percent_bp,max_discount_cents,stackable,active_from,active_to"
  [tax_rate]="id,region,category,rate_bp"
  [coupon]="id,code,percent_bp,max_discount_cents,min_spend_cents,max_uses,times_used,expires_on"
)
for t in customer_tier customer product inventory discount_rule tax_rate coupon; do
  echo "  COPY $t"
  docker exec -i pgbench-db psql -v ON_ERROR_STOP=1 -U bench -d bench -q \
    -c "COPY $t (${COLS[$t]}) FROM STDIN" < "db/data/$t.tsv"
done
echo "  COPY order"
docker exec -i pgbench-db psql -U bench -d bench -q \
  -c 'COPY "order" (id,customer_id,warehouse_id,subtotal_cents,coupon_id,coupon_discount_cents,tax_total_cents,shipping_cents,total_cents,points_earned,created_at) FROM STDIN' < db/data/order.tsv
echo "  COPY order_item"
docker exec -i pgbench-db psql -U bench -d bench -q \
  -c 'COPY order_item (id,order_id,product_id,sku,category,qty,unit_price_cents,discount_cents,net_cents,tax_cents) FROM STDIN' < db/data/order_item.tsv
echo "  COPY loyalty_transaction"
docker exec -i pgbench-db psql -U bench -d bench -q \
  -c 'COPY loyalty_transaction (id,customer_id,order_id,points,kind,created_at) FROM STDIN' < db/data/loyalty_transaction.tsv

"${PSQL[@]}" <<'EOSQL'
SELECT setval(pg_get_serial_sequence('"order"','id'), (SELECT max(id) FROM "order"));
SELECT setval(pg_get_serial_sequence('order_item','id'), (SELECT max(id) FROM order_item));
SELECT setval(pg_get_serial_sequence('loyalty_transaction','id'), (SELECT max(id) FROM loyalty_transaction));
VACUUM ANALYZE;
EOSQL
echo "database ready"
