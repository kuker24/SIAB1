#!/usr/bin/env bash
# Collect a bounded, aggregate VPS capacity snapshot without changing services or data.
# Run from the repository root. Output contains no answer text, tokens, or user PII.

set -uo pipefail

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.production.yml}"
INCLUDE_DIRECTORY_SIZES="${INCLUDE_DIRECTORY_SIZES:-false}"

if command -v docker-compose >/dev/null 2>&1; then
    DC=(docker-compose)
elif docker compose version >/dev/null 2>&1; then
    DC=(docker compose)
else
    printf 'ERROR: Docker Compose is not available.\n' >&2
    exit 1
fi

section() {
    printf '\n===== %s =====\n' "$1"
}

run_optional() {
    local label="$1"
    shift
    printf '\n--- %s ---\n' "$label"
    "$@" 2>&1 || printf '[unavailable] %s\n' "$label"
}

compose_exec() {
    "${DC[@]}" -f "$COMPOSE_FILE" exec -T "$@"
}

section "SNAPSHOT METADATA"
printf 'timestamp=%s\n' "$(date -Is)"
printf 'hostname=%s\n' "$(hostname)"
printf 'kernel=%s\n' "$(uname -sr)"
printf 'compose_file=%s\n' "$COMPOSE_FILE"

section "HOST CAPACITY"
run_optional "uptime" uptime
run_optional "cpu count" nproc
run_optional "memory" free -h
run_optional "swap" swapon --show
run_optional "filesystem usage" df -h -x tmpfs -x devtmpfs
run_optional "inode usage" df -i -x tmpfs -x devtmpfs
if command -v vmstat >/dev/null 2>&1; then
    run_optional "short vmstat sample" vmstat 1 3
fi

section "DOCKER SUMMARY"
run_optional "compose services" "${DC[@]}" -f "$COMPOSE_FILE" config --services
run_optional "compose status" "${DC[@]}" -f "$COMPOSE_FILE" ps
run_optional "container resource snapshot" docker stats --no-stream
run_optional "Docker storage summary" docker system df
run_optional "container limits and restart state" docker inspect \
    --format '{{.Name}} memory={{.HostConfig.Memory}} cpu_quota={{.HostConfig.CpuQuota}} restarts={{.RestartCount}} log={{.HostConfig.LogConfig.Type}}/{{json .HostConfig.LogConfig.Config}} health={{if .State.Health}}{{.State.Health.Status}}{{else}}n/a{{end}}' \
    $("${DC[@]}" -f "$COMPOSE_FILE" ps -q)

section "PGBOUNCER"
run_optional "pool state" compose_exec pgbouncer sh -lc \
    'PGPASSWORD="$DB_PASSWORD" psql -h 127.0.0.1 -p 6432 -U "$DB_USER" -d pgbouncer -X -P pager=off -c "SHOW POOLS;"'
run_optional "pool statistics" compose_exec pgbouncer sh -lc \
    'PGPASSWORD="$DB_PASSWORD" psql -h 127.0.0.1 -p 6432 -U "$DB_USER" -d pgbouncer -X -P pager=off -c "SHOW STATS;"'

section "POSTGRESQL AGGREGATES"
run_optional "connection states" compose_exec db psql -U examuser -d siab1 -X -P pager=off -c \
    "SELECT COALESCE(state, 'system') AS state, COALESCE(wait_event_type, 'none') AS wait_type, COUNT(*) AS connections FROM pg_stat_activity WHERE datname = current_database() GROUP BY 1, 2 ORDER BY 3 DESC;"
run_optional "long transactions" compose_exec db psql -U examuser -d siab1 -X -P pager=off -c \
    "SELECT COUNT(*) AS transactions_over_5s, COALESCE(MAX(EXTRACT(EPOCH FROM (clock_timestamp() - xact_start)))::bigint, 0) AS oldest_seconds FROM pg_stat_activity WHERE datname = current_database() AND xact_start IS NOT NULL AND clock_timestamp() - xact_start > interval '5 seconds';"
run_optional "advisory lock pressure" compose_exec db psql -U examuser -d siab1 -X -P pager=off -c \
    "SELECT COUNT(*) FILTER (WHERE granted) AS granted, COUNT(*) FILTER (WHERE NOT granted) AS waiting FROM pg_locks WHERE locktype = 'advisory';"
run_optional "database size" compose_exec db psql -U examuser -d siab1 -X -P pager=off -c \
    "SELECT pg_size_pretty(pg_database_size(current_database())) AS database_size;"
run_optional "largest relations" compose_exec db psql -U examuser -d siab1 -X -P pager=off -c \
    "SELECT relname, pg_size_pretty(pg_total_relation_size(relid)) AS total_size, n_live_tup, n_dead_tup, last_autovacuum FROM pg_stat_user_tables ORDER BY pg_total_relation_size(relid) DESC LIMIT 15;"
run_optional "cache and transaction counters" compose_exec db psql -U examuser -d siab1 -X -P pager=off -c \
    "SELECT xact_commit, xact_rollback, blks_read, blks_hit, temp_files, pg_size_pretty(temp_bytes) AS temp_bytes, deadlocks FROM pg_stat_database WHERE datname = current_database();"

section "REDIS AGGREGATES"
run_optional "memory" compose_exec redis redis-cli INFO memory
run_optional "clients" compose_exec redis redis-cli INFO clients
run_optional "stats" compose_exec redis redis-cli INFO stats
run_optional "persistence" compose_exec redis redis-cli INFO persistence
run_optional "keyspace" compose_exec redis redis-cli INFO keyspace

section "BACKUP AND SCHEDULE EVIDENCE"
run_optional "backup artifacts" find recovery_sistem -maxdepth 1 -type f -name 'backup_*.tar.gz' -printf '%TY-%Tm-%TdT%TH:%TM:%TS %s %f\n'
run_optional "relevant crontab entries" sh -lc \
    'crontab -l 2>/dev/null | grep -E "backup|health-monitor|cache-maintenance|self-healing" || true'
if command -v systemctl >/dev/null 2>&1; then
    run_optional "systemd timers" systemctl list-timers --all --no-pager
fi

if [[ "$INCLUDE_DIRECTORY_SIZES" == "true" ]]; then
    section "OPTIONAL DIRECTORY SIZES"
    printf 'Directory scanning can add disk I/O; it was explicitly enabled.\n'
    for path in logs uploads apk_builds static/apk/builds static/seb/builds recovery_sistem; do
        if [[ -e "$path" ]]; then
            du -sh "$path" 2>&1 || true
        fi
    done
fi

section "END"
printf 'Snapshot completed with read-only aggregate commands.\n'
