#!/bin/bash
# ============================================
# Database Backup Script
# Automated PostgreSQL backup with rotation
# ============================================

set -e

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Detect docker-compose
if command -v docker-compose &> /dev/null; then
    DC="docker-compose"
elif command -v docker &> /dev/null && docker compose version &> /dev/null; then
    DC="docker compose"
else
    echo "ERROR: Docker Compose not found!"
    exit 1
fi

# Resolve project root
BASE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$BASE_DIR"

# Configuration
BACKUP_DIR="./backups"
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="backup_${DATE}.sql"
KEEP_DAYS="${KEEP_DAYS:-7}"  # Keep backups for N days (overridable)

echo ""
echo "╔════════════════════════════════════════════╗"
echo "║     DATABASE BACKUP UTILITY                ║"
echo "╚════════════════════════════════════════════╝"
echo ""

# Create backup directory
mkdir -p "$BACKUP_DIR"

echo -e "${BLUE}[1/3] Creating database backup...${NC}"
$DC -f docker-compose.production.yml exec -T db pg_dump -U examuser exam_system > "$BACKUP_DIR/$BACKUP_FILE"

if [ -f "$BACKUP_DIR/$BACKUP_FILE" ]; then
    SIZE=$(du -h "$BACKUP_DIR/$BACKUP_FILE" | cut -f1)
    echo -e "${GREEN}✓ Backup created: $BACKUP_FILE ($SIZE)${NC}"
else
    echo "ERROR: Backup failed!"
    exit 1
fi
echo ""

echo -e "${BLUE}[2/3] Compressing backup...${NC}"
gzip "$BACKUP_DIR/$BACKUP_FILE"
COMPRESSED_SIZE=$(du -h "$BACKUP_DIR/$BACKUP_FILE.gz" | cut -f1)
echo -e "${GREEN}✓ Compressed: $BACKUP_FILE.gz ($COMPRESSED_SIZE)${NC}"
echo ""

echo -e "${BLUE}[3/3] Cleaning old backups (older than $KEEP_DAYS days)...${NC}"
find "$BACKUP_DIR" -name "backup_*.sql.gz" -mtime +$KEEP_DAYS -delete
REMAINING=$(ls -1 "$BACKUP_DIR"/backup_*.sql.gz 2>/dev/null | wc -l)
echo -e "${GREEN}✓ Cleanup complete. $REMAINING backup(s) remaining${NC}"
echo ""

echo "╔════════════════════════════════════════════╗"
echo "║     BACKUP SUCCESSFUL! 🎉                  ║"
echo "╚════════════════════════════════════════════╝"
echo ""
echo "Backup location: $BACKUP_DIR/$BACKUP_FILE.gz"
echo ""
echo "To restore this backup:"
echo "  1. Stop containers: $DC -f docker-compose.production.yml down"
echo "  2. Start DB only:   $DC -f docker-compose.production.yml up -d db"
echo "  3. Restore:         gunzip -c $BACKUP_DIR/$BACKUP_FILE.gz | $DC -f docker-compose.production.yml exec -T db psql -U examuser exam_system"
echo "  4. Start all:       $DC -f docker-compose.production.yml up -d"
echo ""
