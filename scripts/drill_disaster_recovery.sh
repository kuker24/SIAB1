#!/usr/bin/env bash
# Non-destructive restore drill for an existing comprehensive backup.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
COMPOSE_FILE="${COMPOSE_FILE:-$ROOT_DIR/docker-compose.production.yml}"
BACKUP_ROOT="${BACKUP_ROOT:-$ROOT_DIR/recovery_sistem}"
OUTPUT_DIR="${OUTPUT_DIR:-$BACKUP_ROOT/dr_drill}"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
REPORT_FILE="${OUTPUT_DIR}/drill_${TIMESTAMP}.report.txt"
DRILL_DB="drill_restore_${TIMESTAMP}"
TEMP_DIR="$(mktemp -d)"
CONTAINER_SQL="/tmp/${DRILL_DB}.sql"

mkdir -p "$OUTPUT_DIR"

if [[ -z "${BACKUP_FILE:-}" ]]; then
  BACKUP_FILE="$(find "$BACKUP_ROOT" -maxdepth 1 -type f -name 'backup_*.tar.gz' -printf '%T@ %p\n' | sort -nr | cut -d' ' -f2- | head -n 1)"
fi

if [[ -z "$BACKUP_FILE" || ! -f "$BACKUP_FILE" ]]; then
  echo "ERROR: no comprehensive backup archive found." >&2
  exit 1
fi

cleanup() {
  if [[ -n "${DB_CONTAINER_ID:-}" ]]; then
    docker exec "$DB_CONTAINER_ID" sh -lc \
      "dropdb --if-exists -U \"\${POSTGRES_USER}\" \"${DRILL_DB}\"; rm -f '${CONTAINER_SQL}'" \
      >/dev/null 2>&1 || true
  fi
  rm -rf "$TEMP_DIR"
}
trap cleanup EXIT

echo "== DR drill started at $(date -Iseconds) ==" | tee "$REPORT_FILE"
echo "Compose file: $COMPOSE_FILE" | tee -a "$REPORT_FILE"
echo "Backup file: $BACKUP_FILE" | tee -a "$REPORT_FILE"

if [[ -f "${BACKUP_FILE}.sha256" ]]; then
  (
    cd "$(dirname "$BACKUP_FILE")"
    sha256sum --check "$(basename "${BACKUP_FILE}.sha256")"
  ) | tee -a "$REPORT_FILE"
else
  echo "ERROR: checksum sidecar is missing: ${BACKUP_FILE}.sha256" | tee -a "$REPORT_FILE"
  exit 1
fi

tar -xzf "$BACKUP_FILE" -C "$TEMP_DIR"
SQL_FILE="$(find "$TEMP_DIR" -type f -path '*/database/siab1.sql' -print -quit)"
if [[ -z "$SQL_FILE" || ! -s "$SQL_FILE" ]]; then
  echo "ERROR: backup does not contain a non-empty database/siab1.sql" | tee -a "$REPORT_FILE"
  exit 1
fi

DB_CONTAINER_ID="$(docker compose -f "$COMPOSE_FILE" ps -q db)"
if [[ -z "$DB_CONTAINER_ID" ]]; then
  echo "ERROR: service 'db' is not running." | tee -a "$REPORT_FILE"
  exit 1
fi

echo "DB container is available." | tee -a "$REPORT_FILE"

docker cp "$SQL_FILE" "$DB_CONTAINER_ID:$CONTAINER_SQL"

docker exec "$DB_CONTAINER_ID" sh -lc "
  set -e
  export PGPASSWORD=\"\${POSTGRES_PASSWORD}\"
  createdb -U \"\${POSTGRES_USER}\" \"${DRILL_DB}\"
  psql -v ON_ERROR_STOP=1 -U \"\${POSTGRES_USER}\" -d \"${DRILL_DB}\" -f \"${CONTAINER_SQL}\" >/dev/null
  psql -U \"\${POSTGRES_USER}\" -d \"${DRILL_DB}\" -v ON_ERROR_STOP=1 -c \"
    SELECT
      (SELECT COUNT(*) FROM users) AS users_count,
      (SELECT COUNT(*) FROM exams) AS exams_count,
      (SELECT COUNT(*) FROM exam_sessions) AS sessions_count,
      (SELECT COUNT(*) FROM answers) AS answers_count,
      (SELECT COUNT(*) FROM exam_logs) AS logs_count;
  \"
  dropdb -U \"\${POSTGRES_USER}\" \"${DRILL_DB}\"
" | tee -a "$REPORT_FILE"

echo "Drill report: $REPORT_FILE" | tee -a "$REPORT_FILE"
echo "== DR drill completed at $(date -Iseconds) ==" | tee -a "$REPORT_FILE"
