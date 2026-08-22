#!/usr/bin/env bash
# Non-destructive disaster recovery drill for PostgreSQL backups.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
COMPOSE_FILE="${COMPOSE_FILE:-$ROOT_DIR/docker-compose.production.yml}"
OUTPUT_DIR="${OUTPUT_DIR:-$ROOT_DIR/backups/dr_drill}"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
DUMP_FILE="drill_${TIMESTAMP}.dump"
REPORT_FILE="${OUTPUT_DIR}/drill_${TIMESTAMP}.report.txt"
DRILL_DB="drill_restore_${TIMESTAMP}"

mkdir -p "$OUTPUT_DIR"

echo "== DR drill started at $(date -Iseconds) ==" | tee "$REPORT_FILE"
echo "Compose file: $COMPOSE_FILE" | tee -a "$REPORT_FILE"

DB_CONTAINER_ID="$(docker compose -f "$COMPOSE_FILE" ps -q db)"
if [[ -z "$DB_CONTAINER_ID" ]]; then
  echo "ERROR: service 'db' is not running." | tee -a "$REPORT_FILE"
  exit 1
fi

echo "DB container: $DB_CONTAINER_ID" | tee -a "$REPORT_FILE"

docker exec "$DB_CONTAINER_ID" sh -lc "
  set -e
  export PGPASSWORD=\"\${POSTGRES_PASSWORD}\"
  pg_dump -U \"\${POSTGRES_USER}\" -d \"\${POSTGRES_DB}\" -Fc -f \"/tmp/${DUMP_FILE}\"
  createdb -U \"\${POSTGRES_USER}\" \"${DRILL_DB}\"
  pg_restore -U \"\${POSTGRES_USER}\" -d \"${DRILL_DB}\" \"/tmp/${DUMP_FILE}\"
  psql -U \"\${POSTGRES_USER}\" -d \"${DRILL_DB}\" -v ON_ERROR_STOP=1 -c \"
    SELECT
      (SELECT COUNT(*) FROM users) AS users_count,
      (SELECT COUNT(*) FROM exams) AS exams_count,
      (SELECT COUNT(*) FROM exam_sessions) AS sessions_count,
      (SELECT COUNT(*) FROM answers) AS answers_count,
      (SELECT COUNT(*) FROM exam_logs) AS logs_count;
  \" > \"/tmp/${DUMP_FILE}.check.txt\"
  dropdb -U \"\${POSTGRES_USER}\" \"${DRILL_DB}\"
" | tee -a "$REPORT_FILE"

docker cp "$DB_CONTAINER_ID:/tmp/${DUMP_FILE}" "${OUTPUT_DIR}/${DUMP_FILE}"
docker cp "$DB_CONTAINER_ID:/tmp/${DUMP_FILE}.check.txt" "${OUTPUT_DIR}/${DUMP_FILE}.check.txt"

docker exec "$DB_CONTAINER_ID" sh -lc "rm -f /tmp/${DUMP_FILE} /tmp/${DUMP_FILE}.check.txt"

echo "Drill artifacts:" | tee -a "$REPORT_FILE"
echo "- ${OUTPUT_DIR}/${DUMP_FILE}" | tee -a "$REPORT_FILE"
echo "- ${OUTPUT_DIR}/${DUMP_FILE}.check.txt" | tee -a "$REPORT_FILE"
echo "== DR drill completed at $(date -Iseconds) ==" | tee -a "$REPORT_FILE"
