#!/bin/bash
# ============================================
# POINT-IN-TIME RESTORE - System Restore
# Interactive restore like Windows System Restore
# ============================================

set -euo pipefail

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BLUE='\033[0;34m'
BOLD='\033[1m'
NC='\033[0m'

# Detect docker compose
if command -v docker-compose &> /dev/null; then
    DC="docker-compose"
elif docker compose version &> /dev/null 2>&1; then
    DC="docker compose"
else
    echo -e "${RED}ERROR: Docker Compose not found${NC}"
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "$PROJECT_ROOT"

BACKUP_DIR="${BACKUP_ROOT:-${PROJECT_ROOT}/recovery_sistem}"
BACKUP_SCRIPT="${PROJECT_ROOT}/bin/backup-comprehensive.sh"
RESTORE_HEALTH_URL="${RESTORE_HEALTH_URL:-http://127.0.0.1:8080/health}"
DATABASE_SWAPPED=false
UPLOADS_SWAPPED=false
SEB_CONFIGS_SWAPPED=false
UPLOADS_ORIGINAL_PRESENT=false
SEB_CONFIGS_ORIGINAL_PRESENT=false
RESTORE_FILE_STAGING=""
RESTORE_FILE_PREVIOUS=""

# ============================================
# Function: Display Header
# ============================================
show_header() {
    clear
    echo ""
    echo -e "${CYAN}╔══════════════════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${CYAN}║${NC} ${BOLD}${BLUE}       SIAB1 - POINT-IN-TIME SYSTEM RESTORE${NC}                           ${CYAN}║${NC}"
    echo -e "${CYAN}╚══════════════════════════════════════════════════════════════════════════╝${NC}"
    echo ""
}

# ============================================
# Function: List Available Backups
# ============================================
list_backups() {
    if [ ! -d "$BACKUP_DIR" ]; then
        echo -e "${RED}ERROR: Backup directory not found${NC}"
        echo "Run ./bin/backup-comprehensive.sh first to create backups"
        exit 1
    fi
    
    mapfile -t BACKUPS < <(ls -t "$BACKUP_DIR"/backup_*.tar.gz 2>/dev/null)
    
    if [ ${#BACKUPS[@]} -eq 0 ]; then
        echo -e "${YELLOW}No backups found${NC}"
        echo ""
        echo "Create your first backup:"
        echo "  ./bin/backup-comprehensive.sh"
        exit 0
    fi
    
    echo -e "${CYAN}Available Restore Points:${NC}"
    echo ""
    
    local index=1
    local now
    now=$(date +%s)
    
    for backup in "${BACKUPS[@]}"; do
        local basename
        local date_str
        basename=$(basename "$backup")
        date_str=$(grep -oP '\d{8}_\d{6}' <<< "$basename")
        
        # Parse date
        local year=${date_str:0:4}
        local month=${date_str:4:2}
        local day=${date_str:6:2}
        local hour=${date_str:9:2}
        local min=${date_str:11:2}
        
        local formatted_date="${year}-${month}-${day} ${hour}:${min}"
        
        # Calculate age
        local backup_time
        backup_time=$(date -d "$formatted_date" +%s 2>/dev/null || echo "$now")
        local age_seconds=$((now - backup_time))
        local age_days=$((age_seconds / 86400))
        local age_hours=$(( (age_seconds % 86400) / 3600 ))
        
        # Age text
        if [ $age_days -eq 0 ]; then
            if [ $age_hours -eq 0 ]; then
                age_text="< 1 hour ago"
            else
                age_text="${age_hours}h ago"
            fi
        elif [ $age_days -eq 1 ]; then
            age_text="Yesterday"
        else
            age_text="${age_days} days ago"
        fi
        
        # Size
        local size
        size=$(du -h "$backup" | cut -f1)
        
        # Latest marker
        local marker=""
        if [ $index -eq 1 ]; then
            marker=" ${GREEN}← Latest${NC}"
        fi
        
        printf "  ${YELLOW}[%2d]${NC} %s  (%-6s) - %s%b\n" "$index" "$formatted_date" "$size" "$age_text" "$marker"
        
        index=$((index + 1))
    done
    
    echo ""
    echo -e "${CYAN}Total restore points: ${BOLD}${#BACKUPS[@]}${NC}"
    echo ""
}

# ============================================
# Function: Preview Backup Contents
# ============================================
preview_backup() {
    local backup_file=$1
    local temp_dir
    temp_dir=$(mktemp -d)
    
    echo -e "${CYAN}Preview Backup Contents:${NC}"
    echo ""
    
    # Extract manifest only
    tar -xzf "$backup_file" -C "$temp_dir" --wildcards "*/MANIFEST.txt" 2>/dev/null || true

    local manifest
    manifest=$(find "$temp_dir" -type f -name MANIFEST.txt -print -quit)
    if [ -n "$manifest" ]; then
        # Show key info from manifest
        echo -e "${BLUE}Backup Information:${NC}"
        grep "Backup Date:" "$manifest" | sed 's/^/  /'
        echo ""
        
        echo -e "${BLUE}Contents:${NC}"
        grep -A 4 "Contents:" "$manifest" | tail -4 | sed 's/^/  /'
        echo ""
        
        echo -e "${BLUE}System Info:${NC}"
        grep -A 3 "System Info:" "$manifest" | tail -3 | sed 's/^/  /'
    else
        # Fallback: list files
        echo "  Files:"
        tar -tzf "$backup_file" | head -20 | sed 's/^/    /'
        echo "  ..."
    fi
    
    rm -rf "$temp_dir"
    echo ""
}

# ============================================
# Function: Create Safety Backup
# ============================================
create_safety_backup() {
    echo -e "${CYAN}[1/7] Creating safety backup...${NC}"
    echo "  Creating pre-restore snapshot for safety..."
    
    # Abort before destructive actions unless the safety backup succeeds.
    if ! BACKUP_ROOT="$BACKUP_DIR" "$BACKUP_SCRIPT" > /dev/null 2>&1; then
        echo -e "${RED}✗ Could not create safety backup${NC}"
        echo "  Restore aborted before stopping services or replacing data."
        return 1
    fi

    echo -e "${GREEN}✓ Safety backup created${NC}"
    echo ""
}

# ============================================
# Function: Stop Services
# ============================================
stop_services() {
    echo -e "${CYAN}[2/7] Stopping services...${NC}"
    if ! $DC -f docker-compose.production.yml down; then
        echo -e "${RED}✗ Could not stop all services${NC}"
        return 1
    fi
    echo -e "${GREEN}✓ Services stopped${NC}"
    echo ""
}

# ============================================
# Function: Extract Backup
# ============================================
extract_backup() {
    local backup_file=$1
    local extract_dir="${BACKUP_DIR}/restore_temp"
    
    echo -e "${CYAN}[3/7] Extracting backup...${NC}"
    
    # Clean old temp
    rm -rf "$extract_dir"
    mkdir -p "$extract_dir"
    
    # Extract
    tar -xzf "$backup_file" -C "$extract_dir"
    
    # Find actual backup dir (handles nested structure)
    RESTORE_DIR=$(find "$extract_dir" -type d -name "backup_*" | head -1)
    
    if [ -z "$RESTORE_DIR" ]; then
        echo -e "${RED}✗ Failed to extract backup${NC}"
        return 1
    fi
    
    echo -e "${GREEN}✓ Backup extracted${NC}"
    echo ""
}

# ============================================
# Function: Restore Database
# ============================================
restore_database() {
    echo -e "${CYAN}[4/7] Restoring database...${NC}"
    local dump_file="$RESTORE_DIR/database/siab1.sql"
    local required_table_count

    if [ ! -s "$dump_file" ]; then
        echo -e "${RED}✗ Database dump is missing or empty${NC}"
        return 1
    fi

    # Start DB only
    if ! $DC -f docker-compose.production.yml up -d db; then
        echo -e "${RED}✗ Database container failed to start${NC}"
        return 1
    fi
    sleep 5
    
    # Wait for DB ready
    local attempt=0
    until $DC -f docker-compose.production.yml exec -T db pg_isready -U examuser 2>/dev/null || [ $attempt -eq 20 ]; do
        attempt=$((attempt + 1))
        echo "  Waiting for database... ($attempt/20)"
        sleep 2
    done
    
    if [ $attempt -eq 20 ]; then
        echo -e "${RED}✗ Database failed to start${NC}"
        return 1
    fi
    
    echo "  Preparing staging database..."
    if ! $DC -f docker-compose.production.yml exec -T db \
        psql -v ON_ERROR_STOP=1 -U examuser -d postgres \
        -c "DROP DATABASE IF EXISTS siab1_restore_staging;"; then
        return 1
    fi
    if ! $DC -f docker-compose.production.yml exec -T db \
        psql -v ON_ERROR_STOP=1 -U examuser -d postgres \
        -c "CREATE DATABASE siab1_restore_staging;"; then
        return 1
    fi

    echo "  Restoring and validating staged data..."
    if ! $DC -f docker-compose.production.yml exec -T db \
        psql -v ON_ERROR_STOP=1 --single-transaction -U examuser \
        -d siab1_restore_staging < "$dump_file" > /dev/null; then
        $DC -f docker-compose.production.yml exec -T db \
            psql -v ON_ERROR_STOP=1 -U examuser -d postgres \
            -c "DROP DATABASE IF EXISTS siab1_restore_staging;" || true
        echo -e "${RED}✗ Database import failed; current database was not changed${NC}"
        return 1
    fi

    required_table_count=$(
        $DC -f docker-compose.production.yml exec -T db \
            psql -v ON_ERROR_STOP=1 -At -U examuser -d siab1_restore_staging \
            -c "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public' AND table_name IN ('users', 'exams', 'exam_sessions', 'answers', 'questions');"
    )
    required_table_count=$(printf '%s' "$required_table_count" | tr -d '[:space:]')
    if [ "$required_table_count" != "5" ]; then
        $DC -f docker-compose.production.yml exec -T db \
            psql -v ON_ERROR_STOP=1 -U examuser -d postgres \
            -c "DROP DATABASE IF EXISTS siab1_restore_staging;" || true
        echo -e "${RED}✗ Staged database is missing required tables${NC}"
        return 1
    fi

    echo "  Activating staged database..."
    if ! $DC -f docker-compose.production.yml exec -T db \
        psql -v ON_ERROR_STOP=1 -U examuser -d postgres \
        -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname IN ('siab1', 'siab1_restore_previous') AND pid <> pg_backend_pid();"; then
        return 1
    fi
    if ! $DC -f docker-compose.production.yml exec -T db \
        psql -v ON_ERROR_STOP=1 -U examuser -d postgres \
        -c "DROP DATABASE IF EXISTS siab1_restore_previous;"; then
        return 1
    fi
    if ! $DC -f docker-compose.production.yml exec -T db \
        psql -v ON_ERROR_STOP=1 -U examuser -d postgres \
        -c "ALTER DATABASE siab1 RENAME TO siab1_restore_previous;"; then
        return 1
    fi
    if ! $DC -f docker-compose.production.yml exec -T db \
        psql -v ON_ERROR_STOP=1 -U examuser -d postgres \
        -c "ALTER DATABASE siab1_restore_staging RENAME TO siab1;"; then
        $DC -f docker-compose.production.yml exec -T db \
            psql -v ON_ERROR_STOP=1 -U examuser -d postgres \
            -c "ALTER DATABASE siab1_restore_previous RENAME TO siab1;" || true
        echo -e "${RED}✗ Could not activate staged database${NC}"
        return 1
    fi
    DATABASE_SWAPPED=true
    
    echo -e "${GREEN}✓ Database restored${NC}"
    echo ""
}

# ============================================
# Function: Restore Files
# ============================================
restore_files() {
    echo -e "${CYAN}[5/7] Restoring files...${NC}"
    RESTORE_FILE_STAGING="${PROJECT_ROOT}/.restore_files_staging"
    RESTORE_FILE_PREVIOUS="${PROJECT_ROOT}/.restore_files_previous"
    rm -rf "$RESTORE_FILE_STAGING" "$RESTORE_FILE_PREVIOUS"
    mkdir -p "$RESTORE_FILE_STAGING" "$RESTORE_FILE_PREVIOUS" || return 1

    if [ -d "$RESTORE_DIR/uploads" ]; then
        mkdir -p "$RESTORE_FILE_STAGING/uploads" || return 1
        if ! cp -a "$RESTORE_DIR/uploads/." "$RESTORE_FILE_STAGING/uploads/"; then
            echo -e "${RED}✗ Failed to stage uploaded files; current files were not changed${NC}"
            rm -rf "$RESTORE_FILE_STAGING" "$RESTORE_FILE_PREVIOUS"
            return 1
        fi
    fi

    if [ -d "$RESTORE_DIR/seb_configs" ]; then
        mkdir -p "$RESTORE_FILE_STAGING/seb_configs" || return 1
        if ! cp -a "$RESTORE_DIR/seb_configs/." "$RESTORE_FILE_STAGING/seb_configs/"; then
            echo -e "${RED}✗ Failed to stage SEB configs; current files were not changed${NC}"
            rm -rf "$RESTORE_FILE_STAGING" "$RESTORE_FILE_PREVIOUS"
            return 1
        fi
    fi

    if [ -d "$RESTORE_FILE_STAGING/uploads" ]; then
        UPLOADS_ORIGINAL_PRESENT=false
        if [ -e "${PROJECT_ROOT}/uploads" ]; then
            UPLOADS_ORIGINAL_PRESENT=true
            mv "${PROJECT_ROOT}/uploads" "$RESTORE_FILE_PREVIOUS/uploads" || return 1
        fi
        UPLOADS_SWAPPED=true
        if ! mv "$RESTORE_FILE_STAGING/uploads" "${PROJECT_ROOT}/uploads"; then
            rollback_files
            return 1
        fi
        local upload_count
        upload_count=$(find "${PROJECT_ROOT}/uploads" -type f | wc -l)
        echo "  Restored $upload_count files to uploads/"
    fi

    if [ -d "$RESTORE_FILE_STAGING/seb_configs" ]; then
        SEB_CONFIGS_ORIGINAL_PRESENT=false
        if [ -e "${PROJECT_ROOT}/seb_configs" ]; then
            SEB_CONFIGS_ORIGINAL_PRESENT=true
            mv "${PROJECT_ROOT}/seb_configs" "$RESTORE_FILE_PREVIOUS/seb_configs" || {
                rollback_files
                return 1
            }
        fi
        SEB_CONFIGS_SWAPPED=true
        if ! mv "$RESTORE_FILE_STAGING/seb_configs" "${PROJECT_ROOT}/seb_configs"; then
            rollback_files
            return 1
        fi
        local seb_count
        seb_count=$(find "${PROJECT_ROOT}/seb_configs" -type f | wc -l)
        echo "  Restored $seb_count SEB configs"
    fi

    echo -e "${GREEN}✓ Files restored${NC}"
    echo ""
}

rollback_files() {
    if [ "$UPLOADS_SWAPPED" = true ]; then
        rm -rf "${PROJECT_ROOT}/uploads"
        if [ "$UPLOADS_ORIGINAL_PRESENT" = true ]; then
            mv "$RESTORE_FILE_PREVIOUS/uploads" "${PROJECT_ROOT}/uploads" || return 1
        fi
        UPLOADS_SWAPPED=false
    fi

    if [ "$SEB_CONFIGS_SWAPPED" = true ]; then
        rm -rf "${PROJECT_ROOT}/seb_configs"
        if [ "$SEB_CONFIGS_ORIGINAL_PRESENT" = true ]; then
            mv "$RESTORE_FILE_PREVIOUS/seb_configs" "${PROJECT_ROOT}/seb_configs" || return 1
        fi
        SEB_CONFIGS_SWAPPED=false
    fi

    rm -rf "$RESTORE_FILE_STAGING" "$RESTORE_FILE_PREVIOUS"
}

rollback_database() {
    if [ "$DATABASE_SWAPPED" != true ]; then
        return 0
    fi

    $DC -f docker-compose.production.yml up -d db || return 1
    sleep 5
    $DC -f docker-compose.production.yml exec -T db \
        psql -v ON_ERROR_STOP=1 -U examuser -d postgres \
        -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = 'siab1' AND pid <> pg_backend_pid();" || return 1
    $DC -f docker-compose.production.yml exec -T db \
        psql -v ON_ERROR_STOP=1 -U examuser -d postgres \
        -c "DROP DATABASE siab1;" || return 1
    $DC -f docker-compose.production.yml exec -T db \
        psql -v ON_ERROR_STOP=1 -U examuser -d postgres \
        -c "ALTER DATABASE siab1_restore_previous RENAME TO siab1;" || return 1
    DATABASE_SWAPPED=false
}

rollback_restore() {
    local rollback_ok=true

    echo -e "${YELLOW}Restore failed verification; rolling back all changes...${NC}"
    stop_services || rollback_ok=false
    rollback_database || rollback_ok=false
    rollback_files || rollback_ok=false
    start_services || rollback_ok=false

    if [ "$rollback_ok" != true ]; then
        echo -e "${RED}✗ Automatic rollback needs manual attention${NC}"
        return 1
    fi
    echo -e "${GREEN}✓ Previous database and files restored${NC}"
}

finalize_restore() {
    if [ "$DATABASE_SWAPPED" = true ]; then
        $DC -f docker-compose.production.yml exec -T db \
            psql -v ON_ERROR_STOP=1 -U examuser -d postgres \
            -c "DROP DATABASE siab1_restore_previous;" || return 1
        DATABASE_SWAPPED=false
    fi
    rm -rf "$RESTORE_FILE_STAGING" "$RESTORE_FILE_PREVIOUS"
    UPLOADS_SWAPPED=false
    SEB_CONFIGS_SWAPPED=false
}

# ============================================
# Function: Start Services
# ============================================
start_services() {
    echo -e "${CYAN}[6/7] Starting all services...${NC}"
    $DC -f docker-compose.production.yml up -d
    sleep 5
    echo -e "${GREEN}✓ Services started${NC}"
    echo ""
}

# ============================================
# Function: Verify System
# ============================================
verify_system() {
    echo -e "${CYAN}[7/7] Verifying system...${NC}"
    
    # Wait for API
    local attempt=0
    until curl -sf "$RESTORE_HEALTH_URL" > /dev/null 2>&1 || [ $attempt -eq 20 ]; do
        attempt=$((attempt + 1))
        echo "  Waiting for API... ($attempt/20)"
        sleep 2
    done
    
    if [ $attempt -eq 20 ]; then
        echo -e "${RED}✗ API health check failed${NC}"
        return 1
    fi
    
    # Check services
    local all_ok=true
    services=("api" "db" "redis" "nginx")
    for svc in "${services[@]}"; do
        if $DC -f docker-compose.production.yml ps | grep -q "$svc.*Up"; then
            echo -e "  ${GREEN}✓${NC} $svc"
        else
            echo -e "  ${RED}✗${NC} $svc"
            all_ok=false
        fi
    done
    
    echo ""
    
    if [ "$all_ok" = true ]; then
        echo -e "${GREEN}✓ System verification passed${NC}"
        return 0
    else
        echo -e "${YELLOW}⚠ Some services are not running${NC}"
        return 1
    fi
}

# ============================================
# Function: Cleanup
# ============================================
cleanup() {
    rm -rf "${BACKUP_DIR}/restore_temp" 2>/dev/null || true
}

run_restore() {
    local backup_file=$1

    create_safety_backup || return 1
    stop_services || return 1

    if ! extract_backup "$backup_file"; then
        start_services || true
        cleanup
        return 1
    fi
    if ! restore_database; then
        start_services || true
        cleanup
        return 1
    fi
    if ! restore_files; then
        rollback_restore || true
        cleanup
        return 1
    fi
    if ! start_services; then
        rollback_restore || true
        cleanup
        return 1
    fi
    if ! verify_system; then
        rollback_restore || true
        cleanup
        return 1
    fi
    if ! finalize_restore; then
        cleanup
        return 1
    fi

    cleanup
    return 0
}

# ============================================
# MAIN SCRIPT
# ============================================
main() {
show_header

# List backups
list_backups

# Get backup selection
mapfile -t BACKUPS < <(ls -t "$BACKUP_DIR"/backup_*.tar.gz 2>/dev/null)
read -r -p "Select restore point [1-${#BACKUPS[@]}] (or 'q' to quit): " SELECTION

if [[ "$SELECTION" == "q" ]] || [[ "$SELECTION" == "Q" ]]; then
    echo "Cancelled."
    exit 0
fi

if ! [[ "$SELECTION" =~ ^[0-9]+$ ]] || [ "$SELECTION" -lt 1 ] || [ "$SELECTION" -gt "${#BACKUPS[@]}" ]; then
    echo -e "${RED}Invalid selection${NC}"
    exit 1
fi

SELECTED_BACKUP="${BACKUPS[$((SELECTION - 1))]}"
BACKUP_NAME=$(basename "$SELECTED_BACKUP")

echo ""
echo -e "${CYAN}Selected: ${BOLD}$BACKUP_NAME${NC}"
echo ""

# Preview
preview_backup "$SELECTED_BACKUP"

# Warning
echo -e "${YELLOW}╔════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${YELLOW}║  ⚠️  WARNING: System Restore                                   ║${NC}"
echo -e "${YELLOW}╚════════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo "This will:"
echo "  • Stop all running services"
echo "  • Restore database to selected point"
echo "  • Restore all files and configurations"
echo "  • Restart all services"
echo ""
echo "A safety backup will be created first."
echo ""
read -r -p "Continue with restore? (yes/no): " CONFIRM

if [[ "$CONFIRM" != "yes" ]]; then
    echo "Restore cancelled."
    exit 0
fi

echo ""
echo -e "${CYAN}╔══════════════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║${NC} ${BOLD}Starting System Restore...${NC}                                              ${CYAN}║${NC}"
echo -e "${CYAN}╚══════════════════════════════════════════════════════════════════════════╝${NC}"
echo ""

# Execute restore steps
if run_restore "$SELECTED_BACKUP"; then
    echo ""
    echo -e "${CYAN}╔══════════════════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${CYAN}║${NC} ${GREEN}${BOLD}              🎉 SYSTEM RESTORE SUCCESSFUL! 🎉${NC}                          ${CYAN}║${NC}"
    echo -e "${CYAN}╚══════════════════════════════════════════════════════════════════════════╝${NC}"
    echo ""
    echo -e "${GREEN}System has been restored to:${NC}"
    echo "  Backup: $BACKUP_NAME"
    echo ""
    echo -e "${CYAN}Access your system:${NC}"
    SERVER_IP=$(hostname -I 2>/dev/null | awk '{print $1}' || echo "localhost")
    echo "  🌐 http://$SERVER_IP:8080"
    echo ""
    echo -e "${CYAN}Monitor system:${NC}"
    echo "  ./bin/monitor.sh"
    echo ""
else
    echo ""
    echo -e "${RED}╔══════════════════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${RED}║${NC} ${BOLD}  System restore failed; success was not reported${NC}                    ${RED}║${NC}"
    echo -e "${RED}╚══════════════════════════════════════════════════════════════════════════╝${NC}"
    echo ""
    echo "The script attempted to preserve or restore the previous system state."
    echo "Check logs: docker-compose -f docker-compose.production.yml logs"
    echo ""
    return 1
fi
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    main "$@"
fi
