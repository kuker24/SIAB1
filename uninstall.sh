#!/bin/bash
# ============================================
# UJIAN ONLINE SYSTEM - COMPLETE UNINSTALLER
# Clean removal of all components
# ============================================

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

# Banner
clear
echo -e "${RED}"
cat << "EOF"
╔══════════════════════════════════════════════════════════╗
║     UJIAN ONLINE SYSTEM - COMPLETE UNINSTALLER           ║
║     ⚠️  WARNING: This will DELETE EVERYTHING! ⚠️          ║
╚══════════════════════════════════════════════════════════╝
EOF
echo -e "${NC}"
echo ""

##############################################################################
# AUTO-DETECT PROJECT DIRECTORY
##############################################################################

# Fungsi untuk mencari direktori ujian_online
find_project_dir() {
    local current_dir="$(pwd)"
    local search_dir="$current_dir"
    
    # Cek apakah sudah di ujian_online/ (ada docker-compose.production.yml)
    if [ -f "$search_dir/docker-compose.production.yml" ]; then
        return 0
    fi
    
    # Cek apakah ada subfolder ujian_online/
    if [ -d "$search_dir/ujian_online" ] && [ -f "$search_dir/ujian_online/docker-compose.production.yml" ]; then
        cd "$search_dir/ujian_online"
        return 0
    fi
    
    # Cari di parent directories (max 3 levels)
    for i in {1..3}; do
        search_dir="$search_dir/.."
        if [ -f "$search_dir/docker-compose.production.yml" ]; then
            cd "$search_dir"
            return 0
        fi
        if [ -d "$search_dir/ujian_online" ] && [ -f "$search_dir/ujian_online/docker-compose.production.yml" ]; then
            cd "$search_dir/ujian_online"
            return 0
        fi
    done
    
    return 1
}

# Navigate to project directory
if ! find_project_dir; then
    echo -e "${RED}❌ Error: docker-compose.production.yml not found!${NC}"
    echo -e "${YELLOW}ℹ️  Please run this script from:${NC}"
    echo "   - Ujian-2026/ (root folder)"
    echo "   - Ujian-2026/ujian_online/ (project folder)"
    exit 1
fi

# Simpan direktori project
PROJECT_DIR="$(pwd)"
echo -e "${GREEN}✅ Working directory: $PROJECT_DIR${NC}"
sleep 0.5
echo ""

# Detect sudo
if [ "$EUID" -eq 0 ]; then
    SUDO=""
else
    SUDO="sudo"
fi

# Detect Docker Compose command
if command -v docker-compose &> /dev/null; then
    DC="docker-compose -f docker-compose.production.yml"
elif docker compose version &> /dev/null 2>&1; then
    DC="docker compose -f docker-compose.production.yml"
else
    DC="docker compose -f docker-compose.production.yml"
fi

# ============================================
# Safety Confirmation
# ============================================
echo -e "${YELLOW}This will PERMANENTLY DELETE:${NC}"
echo "  ❌ All Docker containers"
echo "  ❌ All Docker images (ujian_online-*)"
echo "  ❌ All Docker volumes (databases, uploads, cache)"
echo "  ❌ All backups in recovery_sistem/"
echo "  ❌ All log files"
echo "  ❌ All cron jobs (auto-backup, health check, etc)"
echo "  ❌ Environment configuration (.env)"
echo ""
echo -e "${RED}⚠️  THIS CANNOT BE UNDONE! ⚠️${NC}"
echo ""

read -p "Type 'DELETE EVERYTHING' to confirm: " CONFIRM

if [ "$CONFIRM" != "DELETE EVERYTHING" ]; then
    echo -e "${GREEN}Uninstall cancelled. System preserved.${NC}"
    exit 0
fi

echo ""
echo -e "${RED}Starting complete uninstallation...${NC}"
echo ""

# ============================================
# STEP 1: Stop All Services
# ============================================
echo -e "${CYAN}[1/8] Stopping all services...${NC}"

if [ -f "docker-compose.production.yml" ]; then
    $DC down 2>/dev/null || true
    echo -e "${GREEN}✓ Services stopped${NC}"
else
    echo -e "${YELLOW}⚠️  docker-compose.production.yml not found, skipping${NC}"
fi
echo ""

# ============================================
# STEP 2: Remove Docker Containers
# ============================================
echo -e "${CYAN}[2/8] Removing containers...${NC}"

# Remove all ujian_online containers
CONTAINERS=$(docker ps -a --filter "name=ujian_online" -q)
if [ -n "$CONTAINERS" ]; then
    docker rm -f $CONTAINERS 2>/dev/null || true
    echo -e "${GREEN}✓ Containers removed${NC}"
else
    echo -e "${YELLOW}⚠️  No containers found${NC}"
fi
echo ""

# ============================================
# STEP 3: Remove Docker Volumes
# ============================================
echo -e "${CYAN}[3/8] Removing volumes (databases, uploads, cache)...${NC}"

# Remove all ujian_online volumes
VOLUMES=$(docker volume ls --filter "name=ujian_online" -q)
if [ -n "$VOLUMES" ]; then
    docker volume rm $VOLUMES 2>/dev/null || true
    echo -e "${GREEN}✓ Volumes removed${NC}"
else
    echo -e "${YELLOW}⚠️  No volumes found${NC}"
fi
echo ""

# ============================================
# STEP 4: Remove Docker Images
# ============================================
echo -e "${CYAN}[4/8] Removing Docker images...${NC}"

# Remove ujian_online custom images
IMAGES=$(docker images --filter "reference=ujian_online-*" -q)
if [ -n "$IMAGES" ]; then
    docker rmi -f $IMAGES 2>/dev/null || true
    echo -e "${GREEN}✓ Custom images removed${NC}"
else
    echo -e "${YELLOW}⚠️  No custom images found${NC}"
fi

# Ask about base images
echo ""
read -p "Remove base images too? (postgres, redis, nginx, grafana, prometheus) (y/N): " REMOVE_BASE

if [[ $REMOVE_BASE =~ ^[Yy]$ ]]; then
    echo "Removing base images..."
    docker rmi postgres:15-alpine redis:7-alpine nginx:alpine grafana/grafana:latest prom/prometheus:latest python:3.11-slim 2>/dev/null || true
    echo -e "${GREEN}✓ Base images removed${NC}"
fi
echo ""

# ============================================
# STEP 5: Remove Cron Jobs
# ============================================
echo -e "${CYAN}[5/8] Removing cron jobs...${NC}"

# Remove all related cron jobs
(crontab -l 2>/dev/null | grep -v "backup-comprehensive.sh" | grep -v "backup-database.sh" | grep -v "cache-maintenance.sh" | grep -v "health-monitor.sh" | grep -v "self-healing.sh" | grep -v "telegram-notify.sh") | crontab - 2>/dev/null || true

if crontab -l 2>/dev/null | grep -q "ujian"; then
    echo -e "${YELLOW}⚠️  Some cron jobs might remain${NC}"
else
    echo -e "${GREEN}✓ Cron jobs removed${NC}"
fi
echo ""

# ============================================
# STEP 6: Remove Backups & Logs
# ============================================
echo -e "${CYAN}[6/8] Removing backups and logs...${NC}"

read -p "Delete backups in recovery_sistem/? (y/N): " DELETE_BACKUPS

if [[ $DELETE_BACKUPS =~ ^[Yy]$ ]]; then
    rm -rf recovery_sistem/ 2>/dev/null || true
    echo -e "${GREEN}✓ Backups deleted${NC}"
else
    echo -e "${YELLOW}⚠️  Backups preserved in recovery_sistem/${NC}"
fi

# Remove log files
rm -rf logs/ *.log 2>/dev/null || true
echo -e "${GREEN}✓ Log files removed${NC}"

# Remove uploaded files
read -p "Delete uploaded files in static/uploads/? (y/N): " DELETE_UPLOADS

if [[ $DELETE_UPLOADS =~ ^[Yy]$ ]]; then
    rm -rf static/uploads/* 2>/dev/null || true
    echo -e "${GREEN}✓ Uploaded files deleted${NC}"
else
    echo -e "${YELLOW}⚠️  Uploaded files preserved in static/uploads/${NC}"
fi
echo ""

# ============================================
# STEP 7: Remove Configuration Files
# ============================================
echo -e "${CYAN}[7/8] Removing configuration files...${NC}"

read -p "Delete .env configuration? (y/N): " DELETE_ENV

if [[ $DELETE_ENV =~ ^[Yy]$ ]]; then
    rm -f .env 2>/dev/null || true
    echo -e "${GREEN}✓ .env removed${NC}"
else
    echo -e "${YELLOW}⚠️  .env preserved${NC}"
fi

# Remove generated files
rm -f docker-compose.yml.backup 2>/dev/null || true
echo ""

# ============================================
# STEP 8: Clean Docker System
# ============================================
echo -e "${CYAN}[8/8] Final Docker cleanup...${NC}"

read -p "Run Docker system prune (remove unused data)? (y/N): " PRUNE

if [[ $PRUNE =~ ^[Yy]$ ]]; then
    docker system prune -af --volumes 2>/dev/null || true
    echo -e "${GREEN}✓ Docker system cleaned${NC}"
else
    echo -e "${YELLOW}⚠️  Skipped system prune${NC}"
fi
echo ""

# ============================================
# Verification
# ============================================
echo -e "${CYAN}Verifying cleanup...${NC}"
echo ""

# Check containers
REMAINING_CONTAINERS=$(docker ps -a --filter "name=ujian_online" -q | wc -l)
echo "  Containers remaining: $REMAINING_CONTAINERS"

# Check volumes
REMAINING_VOLUMES=$(docker volume ls --filter "name=ujian_online" -q | wc -l)
echo "  Volumes remaining: $REMAINING_VOLUMES"

# Check images
REMAINING_IMAGES=$(docker images --filter "reference=ujian_online-*" -q | wc -l)
echo "  Custom images remaining: $REMAINING_IMAGES"

echo ""

# ============================================
# Success Message
# ============================================
if [ "$REMAINING_CONTAINERS" -eq 0 ] && [ "$REMAINING_VOLUMES" -eq 0 ] && [ "$REMAINING_IMAGES" -eq 0 ]; then
    echo -e "${GREEN}"
    cat << "EOF"
╔══════════════════════════════════════════════════════════╗
║          ✅ UNINSTALLATION COMPLETE! ✅                   ║
╚══════════════════════════════════════════════════════════╝
EOF
    echo -e "${NC}"
    echo ""
    echo -e "${GREEN}System completely removed!${NC}"
    echo ""
    echo "Removed:"
    echo "  ✓ Docker containers"
    echo "  ✓ Docker volumes"
    echo "  ✓ Docker images"
    echo "  ✓ Cron jobs"
    echo "  ✓ Log files"
    
    if [[ $DELETE_BACKUPS =~ ^[Yy]$ ]]; then
        echo "  ✓ Backups"
    fi
    
    if [[ $DELETE_ENV =~ ^[Yy]$ ]]; then
        echo "  ✓ Configuration (.env)"
    fi
    
    echo ""
    echo -e "${CYAN}To reinstall:${NC}"
    echo "  cd $PROJECT_DIR"
    echo "  ./install.sh"
else
    echo -e "${YELLOW}"
    cat << "EOF"
╔══════════════════════════════════════════════════════════╗
║          ⚠️  PARTIAL CLEANUP ⚠️                           ║
╚══════════════════════════════════════════════════════════╝
EOF
    echo -e "${NC}"
    echo ""
    echo -e "${YELLOW}Some components remain. Manual cleanup may be needed.${NC}"
    echo ""
    echo "Check remaining:"
    echo "  docker ps -a | grep ujian"
    echo "  docker volume ls | grep ujian"
    echo "  docker images | grep ujian"
fi

echo ""
echo -e "${GREEN}Goodbye! 👋${NC}"
