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
CHECK=0
[ "${1:-}" = "--check" ] && CHECK=1
BODY='{"customerId":4242,"warehouseId":1,"items":[{"sku":"SKU-000101","qty":4},{"sku":"SKU-000202","qty":1}],"couponCode":"BENCH0007"}'

pg() { docker exec pgbench-db psql -U bench -d bench -qc "$1" >/dev/null; }
count() { docker logs pgbench-db 2>&1 | grep -cE 'LOG: +(statement|execute)'; }

./bench/reset.sh >/dev/null 2>&1
pg "ALTER SYSTEM SET log_statement='all'"; pg "SELECT pg_reload_conf()"; sleep 1
trap 'pg "ALTER SYSTEM SET log_statement=none"; pg "SELECT pg_reload_conf()"' EXIT

echo "{" > "$OUT"
first=1
for id in $(jq -r 'to_entries[]|select(.key|startswith("_")|not)|.key' bench/variants.json); do
  stack=$(jq -r --arg v "$id" '.[$v].stack' bench/variants.json)
  port=$(jq -r --arg i "$stack" '.[]|select(.id==$i)|.port' bench/stacks.json)
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

# ---- oracle -------------------------------------------------------------
# A variant only counts as implementing its strategy if it issues exactly the
# statements that strategy is defined to issue. Output equality is not enough:
# phase 1's GORM row returned identical bytes from a different query plan.
if [ "$CHECK" = "1" ]; then
  python3 - "$OUT" bench/expected_statements.json bench/variants.json <<'EOPY'
import json, sys
measured, expected, variants = (json.load(open(p)) for p in sys.argv[1:4])
strategies = expected["strategies"]
fail = []
for name, spec in ((k, v) for k, v in variants.items() if not k.startswith("_")):
    want = strategies.get(spec["strategy"])
    if want is None:
        fail.append(f"{name}: unknown strategy {spec['strategy']!r}"); continue
    got = measured.get(name)
    if got is None:
        fail.append(f"{name}: never measured (variant did not start?)"); continue
    for ep in ("quote", "checkout"):
        if abs(got[ep] - want[ep]) > 1e-9:
            fail.append(f"{name}: {ep} issued {got[ep]:g}, {spec['strategy']} must issue {want[ep]}")
print()
if fail:
    print(f"STATEMENT ORACLE FAIL ({len(fail)}):")
    for f in fail: print("   ", f)
    sys.exit(1)
print(f"STATEMENT ORACLE PASS — {sum(1 for k in variants if not k.startswith(chr(95)))} variants match their strategy")
EOPY
fi
