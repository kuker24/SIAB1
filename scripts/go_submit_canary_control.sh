#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MODE="${1:-status}"
COMPOSE_FILE="${COMPOSE_FILE:-$ROOT/docker-compose.production.yml}"
PROJECT="${COMPOSE_PROJECT:-siab1}"
RUNTIME="$ROOT/runtime_control/nginx.submit-canary.conf"
OFF="$ROOT/docker/nginx.submit-canary-off.conf"
MODES=(5pct 10pct 25pct 50pct 75pct 100pct)

compose() {
  docker compose -p "$PROJECT" -f "$COMPOSE_FILE" "$@"
}

reload_nginx() {
  compose exec -T nginx nginx -t
  compose exec -T nginx nginx -s reload
}

mode_file() {
  local name="$1"
  if [ "$name" = "off" ]; then
    printf "%s\n" "$OFF"
    return
  fi
  printf "%s\n" "$ROOT/docker/nginx.submit-canary-${name}.conf"
}

current_mode() {
  if cmp -s "$RUNTIME" "$OFF"; then
    echo "off"
    return
  fi
  local name
  for name in "${MODES[@]}"; do
    if cmp -s "$RUNTIME" "$(mode_file "$name")"; then
      echo "$name"
      return
    fi
  done
  echo "unknown"
}

apply_mode() {
  local name="$1"
  local src
  src="$(mode_file "$name")"
  if [ ! -f "$src" ]; then
    echo "missing $src" >&2
    exit 2
  fi
  cat "$src" > "$RUNTIME"
  reload_nginx
  printf "submit_canary_mode=%s\n" "$(current_mode)"
}

case "$MODE" in
  status)
    printf "submit_canary_mode=%s\n" "$(current_mode)"
    ;;
  off|rollback)
    apply_mode off
    ;;
  5pct|10pct|25pct|50pct|75pct|100pct)
    apply_mode "$MODE"
    ;;
  *)
    echo "usage: $0 status|off|rollback|5pct|10pct|25pct|50pct|75pct|100pct" >&2
    exit 2
    ;;
esac
