#!/usr/bin/env bash
# Return the database to its seeded state so every run faces identical data.
set -euo pipefail
docker exec -i pgbench-db psql -v ON_ERROR_STOP=1 -U bench -d bench -q <<'SQL'
DELETE FROM order_item          WHERE order_id > 200000;
DELETE FROM ledger_entry        WHERE order_id > 200000;
DELETE FROM loyalty_transaction WHERE order_id > 200000;
DELETE FROM "order"             WHERE id       > 200000;
UPDATE inventory SET reserved = 0 WHERE reserved <> 0;
UPDATE coupon    SET times_used = 0 WHERE times_used <> 0;
SELECT setval(pg_get_serial_sequence('"order"','id'), 200000);
SELECT setval(pg_get_serial_sequence('order_item','id'), (SELECT max(id) FROM order_item));
SELECT setval(pg_get_serial_sequence('loyalty_transaction','id'), (SELECT max(id) FROM loyalty_transaction));
SQL

# Reclaim the deleted rows now, deterministically, rather than letting
# autovacuum decide to do it halfway through the next measurement.
docker exec -i pgbench-db psql -v ON_ERROR_STOP=1 -U bench -d bench -q <<'SQL'
VACUUM (ANALYZE) "order", order_item, ledger_entry, loyalty_transaction, inventory, coupon;
SQL
