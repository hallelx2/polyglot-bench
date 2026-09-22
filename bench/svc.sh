#!/usr/bin/env bash
# Start / stop a single stack by id, pinned to the service cpuset.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
source "$ROOT/bench/env.sh"

: "${SVC_CPUS:=3-5}"
RUNDIR="${RUNDIR:-$ROOT/.run}"
mkdir -p "$RUNDIR"

stack_field() { jq -r --arg id "$1" '.[] | select(.id==$id) | '"$2" "$ROOT/bench/stacks.json"; }

# A variant is a stack plus environment overrides (bench/variants.json).
# "<stack>@<strategy>" selects one; a bare stack id runs it unmodified.
resolve_variant() {
  local v="$1" reg="$ROOT/bench/variants.json"
  VARIANT_STACK="$v"; VARIANT_ENV=()
  [[ "$v" != *@* || ! -f "$reg" ]] && return 0
  jq -e --arg v "$v" 'has($v)' "$reg" >/dev/null || return 0
  VARIANT_STACK="$(jq -r --arg v "$v" '.[$v].stack' "$reg")"
  while IFS= read -r kv; do VARIANT_ENV+=("$kv"); done < <(
    jq -r --arg v "$v" '.[$v].env // {} | to_entries[] | "\(.key)=\(.value)"' "$reg")
}

start() {
  local variant="$1" id
  resolve_variant "$variant"; id="$VARIANT_STACK"
  local port; port="$(stack_field "$id" .port)"
  mapfile -t cmd < <(stack_field "$id" '.cmd[]')
  cmd[0]="$( [[ "${cmd[0]}" == services/* ]] && echo "$ROOT/${cmd[0]}" || echo "${cmd[0]}" )"
  # rewrite relative script paths to absolute
  for i in "${!cmd[@]}"; do
    [[ "${cmd[$i]}" == services/* ]] && cmd[$i]="$ROOT/${cmd[$i]}"
  done
  PORT="$port" env "${VARIANT_ENV[@]}" setsid taskset -c "$SVC_CPUS" "${cmd[@]}" \
      >"$RUNDIR/$variant.log" 2>&1 &
  echo $! > "$RUNDIR/$variant.pid"
  for _ in $(seq 120); do
    curl -sf "http://127.0.0.1:$port/health" >/dev/null 2>&1 && { echo "$variant up on $port"; return 0; }
    sleep 0.25
  done
  echo "FAILED to start $variant" >&2; tail -20 "$RUNDIR/$variant.log" >&2; return 1
}

stop() {
  local id="$1"
  if [[ -f "$RUNDIR/$id.pid" ]]; then
    local pid; pid="$(cat "$RUNDIR/$id.pid")"
    kill -TERM -- "-$pid" 2>/dev/null || kill -TERM "$pid" 2>/dev/null || true
    for _ in $(seq 40); do kill -0 "$pid" 2>/dev/null || break; sleep 0.1; done
    kill -KILL -- "-$pid" 2>/dev/null || true
    rm -f "$RUNDIR/$id.pid"
  fi
}

stop_all() { jq -r '.[].id' "$ROOT/bench/stacks.json" | while read -r id; do stop "$id"; done; }

case "${1:-}" in
  start) start "$2" ;;
  stop) stop "$2" ;;
  stop-all) stop_all ;;
  *) echo "usage: svc.sh {start|stop} <stack-id> | svc.sh stop-all" >&2; exit 2 ;;
esac
