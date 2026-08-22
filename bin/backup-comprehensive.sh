#!/bin/bash
# ============================================
# COMPREHENSIVE BACKUP SCRIPT
# Backup: Database + Exam Data + Results + Configs
# ============================================

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BLUE='\033[0;34m'
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

# Resolve project root and execute from there
BASE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$BASE_DIR"

# Configuration
BACKUP_ROOT="${BACKUP_ROOT:-./recovery_sistem}"
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="$BACKUP_ROOT/backup_$DATE"
KEEP_DAYS="${KEEP_DAYS:-30}"  # Keep backups for N days
UPLOAD_COUNT=0
SEB_COUNT=0
LOG_COUNT=0

# Load environment
if [ -f .env ]; then
    source .env
else
    echo -e "${RED}ERROR: .env file not found${NC}"
    exit 1
fi

echo ""
echo -e "${CYAN}╔══════════════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║${NC} ${BLUE}   COMPREHENSIVE BACKUP - Ujian Online System${NC}                          ${CYAN}║${NC}"
echo -e "${CYAN}╚══════════════════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${YELLOW}Timestamp: $DATE${NC}"
echo ""

# Create backup directory structure
echo -e "${BLUE}[1/7] Creating backup directory structure...${NC}"
mkdir -p "$BACKUP_DIR"/{database,uploads,seb_configs,logs}
echo -e "${GREEN}✓ Directory structure created${NC}"
echo ""

# 1. Database backup
echo -e "${BLUE}[2/7] Backing up database...${NC}"
$DC -f docker-compose.production.yml exec -T db pg_dump -U examuser exam_system > "$BACKUP_DIR/database/exam_system.sql" 2>/dev/null

if [ -f "$BACKUP_DIR/database/exam_system.sql" ]; then
    DB_SIZE=$(du -h "$BACKUP_DIR/database/exam_system.sql" | cut -f1)
    echo -e "${GREEN}✓ Database backup complete: $DB_SIZE${NC}"
else
    echo -e "${RED}✗ Database backup failed${NC}"
    exit 1
fi
echo ""

# 2. Uploads (exam files, media, attachments)
echo -e "${BLUE}[3/7] Backing up uploads directory...${NC}"
if [ -d "uploads" ] && [ "$(ls -A uploads 2>/dev/null)" ]; then
    cp -r uploads/* "$BACKUP_DIR/uploads/" 2>/dev/null || true
    UPLOAD_COUNT=$(find "$BACKUP_DIR/uploads" -type f | wc -l)
    UPLOAD_SIZE=$(du -sh "$BACKUP_DIR/uploads" | cut -f1)
    echo -e "${GREEN}✓ Uploads backup complete: $UPLOAD_COUNT files ($UPLOAD_SIZE)${NC}"
else
    echo -e "${YELLOW}⚠ No uploads to backup${NC}"
fi
echo ""

# 3. SEB Configurations
echo -e "${BLUE}[4/7] Backing up SEB configurations...${NC}"
if [ -d "seb_configs" ] && [ "$(ls -A seb_configs 2>/dev/null)" ]; then
    cp -r seb_configs/* "$BACKUP_DIR/seb_configs/" 2>/dev/null || true
    SEB_COUNT=$(find "$BACKUP_DIR/seb_configs" -type f | wc -l)
    echo -e "${GREEN}✓ SEB configs backup complete: $SEB_COUNT files${NC}"
else
    echo -e "${YELLOW}⚠ No SEB configs to backup${NC}"
fi
echo ""

# 4. Application logs (last 7 days)
echo -e "${BLUE}[5/7] Backing up recent logs...${NC}"
if [ -d "logs" ]; then
    find logs -type f -mtime -7 -exec cp {} "$BACKUP_DIR/logs/" \; 2>/dev/null || true
    LOG_COUNT=$(find "$BACKUP_DIR/logs" -type f | wc -l)
    if [ "$LOG_COUNT" -gt 0 ]; then
        echo -e "${GREEN}✓ Logs backup complete: $LOG_COUNT files${NC}"
    else
        echo -e "${YELLOW}⚠ No recent logs found${NC}"
    fi
else
    echo -e "${YELLOW}⚠ No logs directory${NC}"
fi
echo ""

# 5. Create backup manifest
echo -e "${BLUE}[6/7] Creating backup manifest...${NC}"
cat > "$BACKUP_DIR/MANIFEST.txt" <<EOF
═══════════════════════════════════════════════════════════════
UJIAN ONLINE SYSTEM - BACKUP MANIFEST
═══════════════════════════════════════════════════════════════

Backup Date: $(date '+%Y-%m-%d %H:%M:%S')
Backup ID: $DATE

Contents:
1. Database: exam_system.sql ($DB_SIZE)
2. Uploads: $UPLOAD_COUNT files
3. SEB Configs: $SEB_COUNT files
4. Logs: $LOG_COUNT files (last 7 days)

System Info:
- Server: $(hostname)
- Docker Compose: $($DC version --short 2>/dev/null || echo "unknown")
- RAM Profile: ${RAM_PROFILE:-unknown}

Restore Instructions:
1. Extract: tar -xzf backup_${DATE}.tar.gz
2. Stop containers: docker compose -f docker-compose.production.yml down
3. Restore DB:
   docker compose -f docker-compose.production.yml up -d db
   cat backup_${DATE}/database/exam_system.sql | docker compose -f docker-compose.production.yml exec -T db psql -U examuser exam_system
4. Restore uploads: cp -r backup_${DATE}/uploads/* ./uploads/
5. Restore SEB configs: cp -r backup_${DATE}/seb_configs/* ./seb_configs/
6. Start all: docker compose -f docker-compose.production.yml up -d

═══════════════════════════════════════════════════════════════
EOF

echo -e "${GREEN}✓ Manifest created${NC}"
echo ""

# 6. Compress backup
echo -e "${BLUE}[7/7] Compressing backup...${NC}"
cd "$BACKUP_ROOT"
tar -czf "backup_${DATE}.tar.gz" "backup_${DATE}" 2>/dev/null

if [ -f "backup_${DATE}.tar.gz" ]; then
    COMPRESSED_SIZE=$(du -h "backup_${DATE}.tar.gz" | cut -f1)
    echo -e "${GREEN}✓ Backup compressed: $COMPRESSED_SIZE${NC}"

    # Remove uncompressed directory
    rm -rf "backup_${DATE}"

    # Create/update latest symlink
    ln -sf "backup_${DATE}.tar.gz" "latest_backup.tar.gz" 2>/dev/null || true
else
    echo -e "${RED}✗ Compression failed${NC}"
    cd - > /dev/null
    exit 1
fi

cd - > /dev/null
echo ""

# 7. Cleanup old backups
echo -e "${CYAN}Cleaning up old backups (older than $KEEP_DAYS days)...${NC}"
find "$BACKUP_ROOT" -name "backup_*.tar.gz" -mtime +$KEEP_DAYS -delete 2>/dev/null || true
REMAINING=$(ls -1 "$BACKUP_ROOT"/backup_*.tar.gz 2>/dev/null | wc -l)
echo -e "${GREEN}✓ Cleanup complete. $REMAINING backup(s) retained${NC}"
echo ""

# Summary
echo -e "${CYAN}╔══════════════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║${NC} ${GREEN}                    BACKUP SUCCESSFUL! 🎉${NC}                                 ${CYAN}║${NC}"
echo -e "${CYAN}╚══════════════════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${YELLOW}Backup Information:${NC}"
echo -e "  Location: $BACKUP_ROOT/backup_${DATE}.tar.gz"
echo -e "  Size: $COMPRESSED_SIZE"
echo -e "  Contains: Database + Uploads + SEB Configs + Logs"
echo -e "  Total backups: $REMAINING (retention: $KEEP_DAYS days)"
echo ""
echo -e "${CYAN}Quick Restore:${NC}"
echo -e "  cd $BACKUP_ROOT && tar -xzf backup_${DATE}.tar.gz"
echo -e "  See backup_${DATE}/MANIFEST.txt for detailed instructions"
echo ""
