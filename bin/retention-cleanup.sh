#!/bin/bash
# ============================================
# Retention Cleanup Script (Safe Housekeeping)
# ============================================

set -euo pipefail

BASE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
BACKUP_DIR="$BASE_DIR/backups"
RECOVERY_DIR="$BASE_DIR/recovery_sistem"
PRECHANGE_DIR="/root/prechange_backups"

DB_KEEP_DAYS="${DB_KEEP_DAYS:-14}"
RECOVERY_KEEP_DAYS="${RECOVERY_KEEP_DAYS:-14}"
PHASE_KEEP_DAYS="${PHASE_KEEP_DAYS:-60}"
PRECHANGE_KEEP_DAYS="${PRECHANGE_KEEP_DAYS:-14}"

echo "== Retention cleanup started: $(date '+%Y-%m-%d %H:%M:%S') =="
echo "Policy: db=$DB_KEEP_DAYS days, recovery=$RECOVERY_KEEP_DAYS days, prechange=$PRECHANGE_KEEP_DAYS days, phase_final=$PHASE_KEEP_DAYS days"

cleanup_files() {
    local target_dir="$1"
    local pattern="$2"
    local keep_days="$3"
    local label="$4"

    if [ ! -d "$target_dir" ]; then
        echo "[skip] $label: directory not found ($target_dir)"
        return
    fi

    local before_count
    local after_count
    before_count=$(find "$target_dir" -type f -name "$pattern" | wc -l)
    find "$target_dir" -type f -name "$pattern" -mtime +"$keep_days" -delete
    after_count=$(find "$target_dir" -type f -name "$pattern" | wc -l)
    echo "[ok] $label: before=$before_count after=$after_count"
}

cleanup_files "$BACKUP_DIR" "backup_*.sql.gz" "$DB_KEEP_DAYS" "database backups"
cleanup_files "$RECOVERY_DIR" "backup_*.tar.gz" "$RECOVERY_KEEP_DAYS" "comprehensive backups"
cleanup_files "$BACKUP_DIR" "phase*_final_*.sql.gz" "$PHASE_KEEP_DAYS" "phase final snapshots"

if [ -d "$PRECHANGE_DIR" ]; then
    before_prechange=$(find "$PRECHANGE_DIR" -mindepth 1 -maxdepth 1 -type d | wc -l)
    find "$PRECHANGE_DIR" -mindepth 1 -maxdepth 1 -type d -mtime +"$PRECHANGE_KEEP_DAYS" -exec rm -rf {} +
    after_prechange=$(find "$PRECHANGE_DIR" -mindepth 1 -maxdepth 1 -type d | wc -l)
    echo "[ok] prechange backups: before=$before_prechange after=$after_prechange"
else
    echo "[skip] prechange backups: directory not found ($PRECHANGE_DIR)"
fi

echo "== Retention cleanup finished =="
