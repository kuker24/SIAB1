#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="${COMPOSE_FILE:-${REPO_DIR}/docker-compose.production.yml}"
PROJECT_NAME="${PROJECT_NAME:-siab1}"
LOG_FILE="${LOG_FILE:-${REPO_DIR}/logs/autoheal-unhealthy-apis.log}"
LOCK_FILE="${LOCK_FILE:-/tmp/ujian_autoheal_unhealthy_apis.lock}"

mkdir -p "$(dirname "${LOG_FILE}")"
exec 9>"${LOCK_FILE}"
if ! flock -n 9; then
  exit 0
fi

timestamp() {
  date '+%Y-%m-%d %H:%M:%S %Z'
}

log() {
  printf '[%s] %s\n' "$(timestamp)" "$*" >>"${LOG_FILE}"
}

if [[ ! -f "${COMPOSE_FILE}" ]]; then
  log "skip: compose file not found at ${COMPOSE_FILE}"
  exit 0
fi

mapfile -t unhealthy_rows < <(
  docker ps \
    --filter "label=com.docker.compose.project=${PROJECT_NAME}" \
    --filter "health=unhealthy" \
    --format '{{.Names}}\t{{.Label "com.docker.compose.service"}}'
)

if [[ ${#unhealthy_rows[@]} -eq 0 ]]; then
  exit 0
fi

declare -A service_to_container=()
for row in "${unhealthy_rows[@]}"; do
  container_name="${row%%$'\t'*}"
  service_name="${row##*$'\t'}"

  # Only auto-heal API replicas, not stateful services (db/redis/pgbouncer).
  if [[ "${service_name}" =~ ^api[0-9]*$ ]]; then
    service_to_container["${service_name}"]="${container_name}"
  fi
done

if [[ ${#service_to_container[@]} -eq 0 ]]; then
  exit 0
fi

for service_name in "${!service_to_container[@]}"; do
  container_name="${service_to_container[${service_name}]}"
  log "detected unhealthy service=${service_name} container=${container_name}; restarting"
  if docker compose -f "${COMPOSE_FILE}" restart "${service_name}" >>"${LOG_FILE}" 2>&1; then
    log "restart success service=${service_name}"
  else
    log "restart failed service=${service_name}"
  fi
done
