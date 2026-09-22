#!/usr/bin/env bash
# How many SQL statements does one request actually issue?
#
# Turns on log_statement briefly, replays a fixed request N times against each
# stack and counts what reached the server. The conformance harness proves the
# ten services return the same bytes; this proves whether they ask the database
# the same questions to get there.
set -euo pipefail
cd "$(dirname "$0")/.."
source bench/env.sh
N=${N:-20}
OUT=analysis/statements.json
BODY='{"customerId":4242,"warehouseId":1,"items":[{"sku":"SKU-000101","qty":4},{"sku":"SKU-000202","qty":1}],"couponCode":"BENCH0007"}'

pg() { docker exec pgbench-db psql -U bench -d bench -qc "$1" >/dev/null; }
count() { docker logs pgbench-db 2>&1 | grep -cE 'LOG: +(statement|execute)'; }

./bench/reset.sh >/dev/null 2>&1
pg "ALTER SYSTEM SET log_statement='all'"; pg "SELECT pg_reload_conf()"; sleep 1
trap 'pg "ALTER SYSTEM SET log_statement=none"; pg "SELECT pg_reload_conf()"' EXIT

echo "{" > "$OUT"
first=1
for id in $(jq -r '.[].id' bench/stacks.json); do
  port=$(jq -r --arg i "$id" '.[]|select(.id==$i)|.port' bench/stacks.json)
  ./bench/svc.sh start "$id" >/dev/null 2>&1 || continue
  printf '  %-16s' "$id"
  row=""
  for ep in quote checkout; do
    for _ in $(seq 3); do
      curl -s -o /dev/null -X POST "localhost:$port/api/$ep" \
        -H 'content-type: application/json' -d "$BODY"; done
    b=$(count)
    for _ in $(seq "$N"); do
      curl -s -o /dev/null -X POST "localhost:$port/api/$ep" \
        -H 'content-type: application/json' -d "$BODY"; done
    a=$(count)
    v=$(awk -v d="$((a-b))" -v n="$N" 'BEGIN{printf "%.2f", d/n}')
    printf ' %s=%s' "$ep" "$v"
    row="$row\"$ep\": $v,"
  done
  echo
  [ $first -eq 0 ] && echo "," >> "$OUT"
  printf '  "%s": {%s}' "$id" "${row%,}" >> "$OUT"
  first=0
  ./bench/svc.sh stop "$id"
  ./bench/reset.sh >/dev/null 2>&1
done
printf '\n}\n' >> "$OUT"
echo "wrote $OUT"
