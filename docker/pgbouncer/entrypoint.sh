#!/usr/bin/env bash
set -euo pipefail

DB_HOST="${DB_HOST:-db}"
DB_PORT="${DB_PORT:-5432}"
DB_NAME="${DB_NAME:-siab1}"
DB_USER="${DB_USER:-examuser}"
DB_PASSWORD="${DB_PASSWORD:-}"

LISTEN_ADDR="${LISTEN_ADDR:-0.0.0.0}"
LISTEN_PORT="${LISTEN_PORT:-6432}"
POOL_MODE="${POOL_MODE:-transaction}"
MAX_CLIENT_CONN="${MAX_CLIENT_CONN:-3000}"
DEFAULT_POOL_SIZE="${DEFAULT_POOL_SIZE:-120}"
MIN_POOL_SIZE="${MIN_POOL_SIZE:-20}"
RESERVE_POOL_SIZE="${RESERVE_POOL_SIZE:-30}"
RESERVE_POOL_TIMEOUT="${RESERVE_POOL_TIMEOUT:-5}"
SERVER_IDLE_TIMEOUT="${SERVER_IDLE_TIMEOUT:-60}"
QUERY_WAIT_TIMEOUT="${QUERY_WAIT_TIMEOUT:-120}"
MAX_DB_CONNECTIONS="${MAX_DB_CONNECTIONS:-0}"
MAX_USER_CONNECTIONS="${MAX_USER_CONNECTIONS:-0}"
SERVER_LIFETIME="${SERVER_LIFETIME:-3600}"
LISTEN_BACKLOG="${LISTEN_BACKLOG:-4096}"

if [[ -z "${DB_PASSWORD}" ]]; then
  echo "DB_PASSWORD is required for PgBouncer." >&2
  exit 1
fi

mkdir -p /etc/pgbouncer

PASS_HASH="$(printf "%s%s" "${DB_PASSWORD}" "${DB_USER}" | md5sum | awk '{print $1}')"
cat > /etc/pgbouncer/userlist.txt <<EOF
"${DB_USER}" "md5${PASS_HASH}"
EOF

cat > /etc/pgbouncer/pgbouncer.ini <<EOF
[databases]
${DB_NAME} = host=${DB_HOST} port=${DB_PORT} dbname=${DB_NAME} user=${DB_USER} password=${DB_PASSWORD}

[pgbouncer]
listen_addr = ${LISTEN_ADDR}
listen_port = ${LISTEN_PORT}
auth_type = md5
auth_file = /etc/pgbouncer/userlist.txt
admin_users = ${DB_USER}
stats_users = ${DB_USER}

pool_mode = ${POOL_MODE}
max_client_conn = ${MAX_CLIENT_CONN}
listen_backlog = ${LISTEN_BACKLOG}
default_pool_size = ${DEFAULT_POOL_SIZE}
min_pool_size = ${MIN_POOL_SIZE}
reserve_pool_size = ${RESERVE_POOL_SIZE}
reserve_pool_timeout = ${RESERVE_POOL_TIMEOUT}
max_db_connections = ${MAX_DB_CONNECTIONS}
max_user_connections = ${MAX_USER_CONNECTIONS}

server_reset_query = DISCARD ALL
server_check_query = SELECT 1
server_check_delay = 10
server_lifetime = ${SERVER_LIFETIME}
server_idle_timeout = ${SERVER_IDLE_TIMEOUT}
query_wait_timeout = ${QUERY_WAIT_TIMEOUT}
ignore_startup_parameters = extra_float_digits
tcp_keepalive = 1

log_connections = 1
log_disconnections = 1
log_pooler_errors = 1
EOF

exec pgbouncer /etc/pgbouncer/pgbouncer.ini
