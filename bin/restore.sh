#!/bin/bash
# ============================================
# POINT-IN-TIME RESTORE - System Restore
# Interactive restore like Windows System Restore
# ============================================

set -e

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

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "$PROJECT_ROOT"

BACKUP_DIR="${BACKUP_ROOT:-${PROJECT_ROOT}/recovery_sistem}"
BACKUP_SCRIPT="${PROJECT_ROOT}/bin/backup-comprehensive.sh"

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
    
    BACKUPS=($(ls -t "$BACKUP_DIR"/backup_*.tar.gz 2>/dev/null))
    
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
    local now=$(date +%s)
    
    for backup in "${BACKUPS[@]}"; do
        local basename=$(basename "$backup")
        local date_str=$(echo "$basename" | grep -oP '\d{8}_\d{6}')
        
        # Parse date
        local year=${date_str:0:4}
        local month=${date_str:4:2}
        local day=${date_str:6:2}
        local hour=${date_str:9:2}
        local min=${date_str:11:2}
        
        local formatted_date="${year}-${month}-${day} ${hour}:${min}"
        
        # Calculate age
        local backup_time=$(date -d "$formatted_date" +%s 2>/dev/null || echo "$now")
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
        local size=$(du -h "$backup" | cut -f1)
        
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
    local temp_dir=$(mktemp -d)
    
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
    $DC -f docker-compose.production.yml down 2>/dev/null || true
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
    
    # Start DB only
    $DC -f docker-compose.production.yml up -d db
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
    
    # Drop and recreate database
    echo "  Recreating database..."
    $DC -f docker-compose.production.yml exec -T db psql -U examuser -d postgres -c "DROP DATABASE IF EXISTS siab1;" 2>/dev/null || true
    $DC -f docker-compose.production.yml exec -T db psql -U examuser -d postgres -c "CREATE DATABASE siab1;" 2>/dev/null
    
    # Restore from backup
    echo "  Restoring data..."
    cat "$RESTORE_DIR/database/siab1.sql" | \
        $DC -f docker-compose.production.yml exec -T db psql -U examuser -d siab1 > /dev/null 2>&1
    
    echo -e "${GREEN}✓ Database restored${NC}"
    echo ""
}

# ============================================
# Function: Restore Files
# ============================================
restore_files() {
    echo -e "${CYAN}[5/7] Restoring files...${NC}"
    
    # Backup current files first (in case we need to rollback)
    if [ -d "uploads" ]; then
        mv uploads uploads.bak.tmp 2>/dev/null || true
    fi
    if [ -d "seb_configs" ]; then
        mv seb_configs seb_configs.bak.tmp 2>/dev/null || true
    fi
    
    # Restore from backup
    mkdir -p uploads seb_configs
    
    if [ -d "$RESTORE_DIR/uploads" ]; then
        cp -r "$RESTORE_DIR/uploads"/* uploads/ 2>/dev/null || true
        local upload_count=$(find uploads -type f | wc -l)
        echo "  Restored $upload_count files to uploads/"
    fi
    
    if [ -d "$RESTORE_DIR/seb_configs" ]; then
        cp -r "$RESTORE_DIR/seb_configs"/* seb_configs/ 2>/dev/null || true
        local seb_count=$(find seb_configs -type f | wc -l)
        echo "  Restored $seb_count SEB configs"
    fi
    
    # Clean temp backups
    rm -rf uploads.bak.tmp seb_configs.bak.tmp
    
    echo -e "${GREEN}✓ Files restored${NC}"
    echo ""
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
    until curl -sf http://127.0.0.1/health > /dev/null 2>&1 || [ $attempt -eq 20 ]; do
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

# ============================================
# MAIN SCRIPT
# ============================================

show_header

# List backups
list_backups

# Get backup selection
BACKUPS=($(ls -t "$BACKUP_DIR"/backup_*.tar.gz 2>/dev/null))
read -p "Select restore point [1-${#BACKUPS[@]}] (or 'q' to quit): " SELECTION

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
read -p "Continue with restore? (yes/no): " CONFIRM

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
create_safety_backup
stop_services
extract_backup "$SELECTED_BACKUP"
restore_database
restore_files
start_services

if verify_system; then
    cleanup
    
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
    echo -e "${YELLOW}╔══════════════════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${YELLOW}║${NC} ${BOLD}  ⚠️  System restore completed with warnings${NC}                          ${CYAN}║${NC}"
    echo -e "${YELLOW}╚══════════════════════════════════════════════════════════════════════════╝${NC}"
    echo ""
    echo "Some services may need manual attention."
    echo "Check logs: docker-compose -f docker-compose.production.yml logs"
    echo ""
fi
