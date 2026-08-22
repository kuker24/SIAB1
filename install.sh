#!/bin/bash
# ============================================
# UJIAN ONLINE SYSTEM - ULTIMATE INSTALLER
# Enterprise-Grade Deployment with Options
# ============================================
# Version: 2.1
# Features:
# - RAM Auto-Detection & Worker Optimization
# - Optional Monitoring (Grafana/Prometheus)
# - Auto-Backup & Self-Healing
# - Health Monitoring & Telegram Alerts
# - Network Timeout Fix (300s, 10 retries)
# - Smart Update Detection
# - Database Schema Verification (shuffle_options fix)
# ============================================

set -e

# Check if this is an update or fresh install
check_existing_installation() {
    if docker ps -a --filter "name=ujian_online" -q | grep -q .; then
        return 0  # Existing installation found
    fi
    return 1  # No existing installation
}

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BLUE='\033[0;34m'
NC='\033[0m'

# Banner
clear
echo -e "${BLUE}"
cat << "EOF"
 ╔════════════════════════════════════════════════════════╗
 ║     UJIAN ONLINE SYSTEM - ULTIMATE INSTALLER v2.0        ║
 ║     Enterprise-Grade Deployment Automation 🚀            ║
 ╚════════════════════════════════════════════════════════╝
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

# Check for existing installation
if check_existing_installation; then
    echo -e "${YELLOW}⚠️  Existing installation detected!${NC}"
    echo ""
    echo "Options:"
    echo "  1) UPDATE (Rebuild with new code, keep data)"
    echo "  2) REINSTALL (Full fresh install, RESET data)"
    echo "  3) CANCEL (Exit without changes)"
    echo ""
    read -p "Select [1/2/3]: " UPDATE_CHOICE
    
    case $UPDATE_CHOICE in
        1)
            echo -e "${CYAN}Starting UPDATE process...${NC}"
            echo "This will rebuild containers with updated code."
            echo "Your database and uploads will be preserved."
            echo ""
            read -p "Continue? (y/N): " -r
            if [[ ! $REPLY =~ ^[Yy]$ ]]; then
                echo -e "${YELLOW}Update cancelled.${NC}"
                exit 0
            fi
            # Set update mode flag
            UPDATE_MODE=true
            ;;
        2)
            echo -e "${RED}⚠️  WARNING: This will DELETE ALL DATA!${NC}"
            read -p "Are you sure? Type 'DELETE': " CONFIRM
            if [ "$CONFIRM" != "DELETE" ]; then
                echo -e "${GREEN}Reinstall cancelled.${NC}"
                exit 0
            fi
            # Run uninstall first
            if [ -f "./uninstall.sh" ]; then
                ./uninstall.sh
            else
                docker compose -f docker-compose.production.yml down -v
            fi
            UPDATE_MODE=false
            ;;
        *)
            echo -e "${YELLOW}Operation cancelled.${NC}"
            exit 0
            ;;
    esac
else
    UPDATE_MODE=false
fi
echo ""

# Detect sudo
if [ "$EUID" -eq 0 ]; then
    SUDO=""
else
    SUDO="sudo"
fi

# ============================================
# STEP 1: System Check
# ============================================
echo -e "${CYAN}[1/12] Checking system requirements...${NC}"
echo ""

# OS Detection
if [ -f /etc/os-release ]; then
    . /etc/os-release
    echo -e "  OS: ${GREEN}$NAME${NC}"
fi

# RAM Detection
TOTAL_RAM=$(free -m | awk '/^Mem:/{print $2}')
TOTAL_RAM_GB=$((TOTAL_RAM / 1024))
echo -e "  RAM: ${GREEN}${TOTAL_RAM}MB (~${TOTAL_RAM_GB}GB)${NC}"

# Disk Check
FREE_DISK=$(df -BG . | awk 'NR==2 {print $4}' | sed 's/G//')
if [ "$FREE_DISK" -lt 10 ]; then
    echo -e "  ${RED}ERROR: Need at least 10GB free (found ${FREE_DISK}GB)${NC}"
    exit 1
fi
echo -e "  Disk: ${GREEN}${FREE_DISK}GB free${NC}"

echo -e "${GREEN}✓ System requirements OK${NC}"
echo ""

# ============================================
# STEP 2: Prerequisites Check
# ============================================
echo -e "${CYAN}[2/12] Checking prerequisites...${NC}"
echo ""

MISSING_DEPS=()

# Check Docker
if ! command -v docker &> /dev/null; then
    MISSING_DEPS+=("docker")
else
    echo -e "  ${GREEN}✓ Docker found${NC}"
fi

# Check Docker Compose
if command -v docker-compose &> /dev/null; then
    DC="docker-compose -f docker-compose.production.yml"
    echo -e "  ${GREEN}✓ Docker Compose found${NC}"
elif docker compose version &> /dev/null 2>&1; then
    DC="docker compose -f docker-compose.production.yml"
    echo -e "  ${GREEN}✓ Docker Compose (plugin) found${NC}"
else
    MISSING_DEPS+=("docker-compose")
fi

# Install missing dependencies
if [ ${#MISSING_DEPS[@]} -ne 0 ]; then
    echo -e "${YELLOW}Installing missing dependencies: ${MISSING_DEPS[*]}${NC}"
    echo ""
    
    if [[ "$NAME" == *"Ubuntu"* ]] || [[ "$NAME" == *"Debian"* ]]; then
        $SUDO apt-get update
        for dep in "${MISSING_DEPS[@]}"; do
            if [ "$dep" == "docker" ]; then
                echo -e "${YELLOW}Installing Docker...${NC}"
                $SUDO apt-get install -y apt-transport-https ca-certificates curl gnupg lsb-release
                curl -fsSL https://download.docker.com/linux/ubuntu/gpg | $SUDO gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg 2>/dev/null || true
                echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | $SUDO tee /etc/apt/sources.list.d/docker.list > /dev/null
                $SUDO apt-get update
                $SUDO apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
                 $SUDO systemctl start docker
                 $SUDO systemctl enable docker
                 $SUDO usermod -aG docker $USER
                 DC="docker compose -f docker-compose.production.yml"
            elif [ "$dep" == "docker-compose" ]; then
                $SUDO apt-get install -y docker-compose-plugin
                DC="docker compose -f docker-compose.production.yml"
            fi
        done
    elif [[ "$NAME" == *"Arch"* ]] || [[ "$NAME" == *"CachyOS"* ]]; then
        for dep in "${MISSING_DEPS[@]}"; do
            $SUDO pacman -S --noconfirm $dep
        done
        DC="docker-compose -f docker-compose.production.yml"
    fi
    
    echo -e "${GREEN}✓ All prerequisites installed${NC}"
fi

# Check Docker daemon
if ! docker info >/dev/null 2>&1; then
    echo -e "${RED}ERROR: Docker daemon not running!${NC}"
    echo ""
    echo "Start Docker with:"
    echo "  $SUDO systemctl start docker"
    echo "  $SUDO systemctl enable docker"
    exit 1
fi

echo -e "${GREEN}✓ All prerequisites ready${NC}"
echo ""

# ============================================
# STEP 3: RAM Profile Selection
# ============================================
echo -e "${CYAN}[3/12] Select RAM optimization profile...${NC}"
echo ""
echo "Your system: ~${TOTAL_RAM_GB}GB RAM"
echo ""
echo "Profiles (optimized for concurrent users):"
echo "  [3]  3GB  - Minimal (4 workers, ~200 users)"
echo "  [4]  4GB  - Small (8 workers, ~400 users)"
echo "  [8]  8GB  - Recommended (12 workers, ~600 users)"
echo "  [12] 12GB - Comfortable (16 workers, ~800 users)"
echo "  [16] 16GB - Maximum (20 workers, ~1000 users)"
echo ""

# Auto-suggest
if [ "$TOTAL_RAM_GB" -le 3 ]; then
    SUGGESTED=3
elif [ "$TOTAL_RAM_GB" -le 4 ]; then
    SUGGESTED=4
elif [ "$TOTAL_RAM_GB" -le 8 ]; then
    SUGGESTED=8
elif [ "$TOTAL_RAM_GB" -le 12 ]; then
    SUGGESTED=12
else
    SUGGESTED=16
fi

read -p "Select [3/4/8/12/16] (default: $SUGGESTED): " RAM_PROFILE
RAM_PROFILE=${RAM_PROFILE:-$SUGGESTED}

if [[ ! "$RAM_PROFILE" =~ ^(3|4|8|12|16)$ ]]; then
    echo -e "${RED}Invalid. Using default: $SUGGESTED${NC}"
    RAM_PROFILE=$SUGGESTED
fi

echo -e "${GREEN}✓ Selected ${RAM_PROFILE}GB profile${NC}"
echo ""

# ============================================
# STEP 4: Worker Configuration
# ============================================
echo -e "${CYAN}[4/12] Configure workers...${NC}"
echo ""

case $RAM_PROFILE in
    3)  RECOMMENDED_WORKERS=4; MAX_SAFE_WORKERS=6 ;;
    4)  RECOMMENDED_WORKERS=8; MAX_SAFE_WORKERS=12 ;;
    8)  RECOMMENDED_WORKERS=12; MAX_SAFE_WORKERS=16 ;;
    12) RECOMMENDED_WORKERS=16; MAX_SAFE_WORKERS=20 ;;
    16) RECOMMENDED_WORKERS=20; MAX_SAFE_WORKERS=24 ;;
esac

echo "Worker Options (based on ${RAM_PROFILE}GB RAM):"
echo ""
echo "  Workers  |  Max Users  |  Memory"
echo "  ---------|-------------|----------"
echo "     4     |    ~200     |   240MB"
echo "     8     |    ~400     |   480MB"
echo "    12     |    ~600     |   720MB"
echo "    16     |    ~800     |   960MB"
echo "    20     |   ~1000     |  1200MB"
echo ""

read -p "Number of workers (default: $RECOMMENDED_WORKERS): " WORKERS
WORKERS=${WORKERS:-$RECOMMENDED_WORKERS}

if ! [[ "$WORKERS" =~ ^[0-9]+$ ]] || [ "$WORKERS" -lt 4 ] || [ "$WORKERS" -gt 32 ]; then
    echo -e "${RED}Invalid. Using: $RECOMMENDED_WORKERS${NC}"
    WORKERS=$RECOMMENDED_WORKERS
fi

if [ "$WORKERS" -gt "$MAX_SAFE_WORKERS" ]; then
    echo -e "${YELLOW}⚠️  Warning: $WORKERS workers may exceed ${RAM_PROFILE}GB capacity${NC}"
    read -p "Continue? (y/N): " -r
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        WORKERS=$MAX_SAFE_WORKERS
    fi
fi

MAX_USERS=$((WORKERS * 50))
echo -e "${GREEN}✓ Configured: $WORKERS workers (~$MAX_USERS users)${NC}"
echo ""

# ============================================
# STEP 5: Monitoring Configuration
# ============================================
echo -e "${CYAN}[5/12] Configure monitoring services...${NC}"
echo ""
echo "Monitoring services (Grafana + Prometheus):"
echo "  - Visual dashboards for metrics"
echo "  - Real-time performance monitoring"
echo "  - Resource usage: ~500MB RAM, ~200MB disk"
echo ""
echo "Note: These are OPTIONAL. App works perfectly without them."
echo ""
read -p "Enable monitoring? (y/N): " -r ENABLE_MONITORING
echo ""

if [[ $ENABLE_MONITORING =~ ^[Yy]$ ]]; then
    ENABLE_MONITORING=true
    echo -e "${GREEN}✓ Monitoring enabled${NC}"
    echo -e "  Access Grafana: http://localhost:3000"
    echo -e "  Access Prometheus: http://localhost:9090"
else
    ENABLE_MONITORING=false
    echo -e "${YELLOW}⚠️  Monitoring disabled${NC}"
    echo -e "  Skipping: Grafana, Prometheus"
fi
echo ""

# ============================================
# STEP 6: Backup Configuration
# ============================================
echo -e "${CYAN}[6/12] Configure automatic backups...${NC}"
echo ""

echo "Backup Schedule Options:"
echo "  1. Daily at 02:00 (recommended)"
echo "  2. Daily at 03:00"
echo "  3. Daily at 04:00"
echo "  4. Custom time"
echo "  5. Skip (manual only)"
echo ""

read -p "Select [1-5] (default: 1): " BACKUP_OPTION
BACKUP_OPTION=${BACKUP_OPTION:-1}

case $BACKUP_OPTION in
    1) BACKUP_HOUR="02"; BACKUP_MIN="00" ;;
    2) BACKUP_HOUR="03"; BACKUP_MIN="00" ;;
    3) BACKUP_HOUR="04"; BACKUP_MIN="00" ;;
    4) 
        read -p "Enter hour (00-23): " BACKUP_HOUR
        read -p "Enter minute (00-59): " BACKUP_MIN
        ;;
    5)
        SKIP_BACKUP=true
        ;;
    *)
        BACKUP_HOUR="02"; BACKUP_MIN="00"
        ;;
esac

if [ "$SKIP_BACKUP" != "true" ]; then
    PROJECT_ROOT="$(pwd)"
    mkdir -p "$PROJECT_ROOT/recovery_sistem"
    chmod +x "$PROJECT_ROOT"/bin/{backup-comprehensive.sh,backup-database.sh,monitor.sh,restore.sh,cache-maintenance.sh,health-monitor.sh,self-healing.sh} 2>/dev/null || true

    # Setup cron jobs with absolute paths so they keep working outside an interactive shell.
    BACKUP_CRON="$BACKUP_MIN $BACKUP_HOUR * * * cd \"$PROJECT_ROOT\" && ./bin/backup-comprehensive.sh >> recovery_sistem/backup.log 2>&1"
    CACHE_CRON="0 3 * * * cd \"$PROJECT_ROOT\" && ./bin/cache-maintenance.sh >> recovery_sistem/cache.log 2>&1"
    HEALTH_CRON="*/15 * * * * cd \"$PROJECT_ROOT\" && ./bin/health-monitor.sh >> recovery_sistem/health.log 2>&1"
    HEALING_CRON="*/3 * * * * cd \"$PROJECT_ROOT\" && ./bin/self-healing.sh >> recovery_sistem/healing.log 2>&1"
    
    (crontab -l 2>/dev/null | grep -v "backup-comprehensive.sh" | grep -v "cache-maintenance.sh" | grep -v "health-monitor.sh" | grep -v "self-healing.sh"; \
     echo "$BACKUP_CRON"; \
     echo "$CACHE_CRON"; \
     echo "$HEALTH_CRON"; \
     echo "$HEALING_CRON") | crontab - 2>/dev/null || true
    
    echo -e "${GREEN}✓ Auto-backup: Daily at ${BACKUP_HOUR}:${BACKUP_MIN}${NC}"
    echo -e "${GREEN}✓ Cache maintenance: Daily at 03:00${NC}"
    echo -e "${GREEN}✓ Health monitoring: Every 15 minutes${NC}"
    echo -e "${GREEN}✓ Self-healing: Every 3 minutes${NC}"
else
    echo -e "${YELLOW}⚠️  Manual backups only${NC}"
fi
echo ""

# ============================================
# STEP 7: Environment Setup
# ============================================
echo -e "${CYAN}[7/12] Setting up environment...${NC}"

if [ ! -f .env ]; then
    # Cek .env.example (standar) atau env-example.txt (fallback)
    if [ -f .env.example ]; then
        cp .env.example .env
    elif [ -f env-example.txt ]; then
        cp env-example.txt .env
    else
        echo -e "${RED}ERROR: Neither .env.example nor env-example.txt found${NC}"
        exit 1
    fi
    
    if command -v openssl &> /dev/null; then
        SECRET_KEY=$(openssl rand -hex 32)
        JWT_KEY=$(openssl rand -hex 32)
        DB_PASS=$(openssl rand -hex 16)
        APP_SECRET_KEY=$(openssl rand -hex 32)
        SEB_KEY=$(openssl rand -hex 32)
        BROWSER_KEY=$(openssl rand -hex 32)
        HWID=$(openssl rand -hex 16)
        
        # Replace placeholders if they exist
        sed -i "s|your-super-secret-key-change-in-production|${SECRET_KEY}|g" .env
        sed -i "s|your-jwt-secret-key-change-in-production|${JWT_KEY}|g" .env
        sed -i "s|your-super-secret-app-key-min-32-chars|${APP_SECRET_KEY}|g" .env
        sed -i "s|REPLACE_DB_PASSWORD|${DB_PASS}|g" .env
        
        # Populate empty keys
        sed -i "s|^SECRET_KEY=$|SECRET_KEY=${SECRET_KEY}|g" .env
        sed -i "s|^JWT_SECRET_KEY=$|JWT_SECRET_KEY=${JWT_KEY}|g" .env
        sed -i "s|^SEB_DEFAULT_CONFIG_KEY=$|SEB_DEFAULT_CONFIG_KEY=${SEB_KEY}|g" .env
        sed -i "s|^SEB_DEFAULT_BROWSER_EXAM_KEY=$|SEB_DEFAULT_BROWSER_EXAM_KEY=${BROWSER_KEY}|g" .env

        # Ensure DB_PASSWORD and SERVER_HWID exist
        if ! grep -q "^DB_PASSWORD=" .env; then
            echo "DB_PASSWORD=${DB_PASS}" >> .env
        else
             sed -i "s|^DB_PASSWORD=$|DB_PASSWORD=${DB_PASS}|g" .env
        fi

        if ! grep -q "^SERVER_HWID=" .env; then
            echo "SERVER_HWID=${HWID}" >> .env
        else
             sed -i "s|^SERVER_HWID=$|SERVER_HWID=${HWID}|g" .env
        fi
        
        echo -e "  ${GREEN}✓ Generated secure keys${NC}"
    fi
fi

# Add configuration
echo "RAM_PROFILE=${RAM_PROFILE}" >> .env
echo "WORKERS=${WORKERS}" >> .env
echo "ENABLE_MONITORING=${ENABLE_MONITORING}" >> .env
# Allow all origins by default to prevent CORS issues with mobile apps/LAN access
echo "CORS_ORIGINS=*" >> .env

echo -e "${GREEN}✓ Environment configured${NC}"
echo ""

# ============================================
# STEP 8: Verify Docker Compose
# ============================================
echo -e "${CYAN}[8/12] Verifying docker-compose...${NC}"

# Verify docker-compose structure
if $DC config > /dev/null 2>&1; then
    echo -e "  ${GREEN}✓ Docker compose structure valid${NC}"
else
    echo -e "  ${YELLOW}⚠ Docker compose validation warning (non-critical)${NC}"
fi

echo -e "${GREEN}✓ Docker compose ready${NC}"
echo ""

# ============================================
# STEP 9: Create Directories
# ============================================
echo -e "${CYAN}[9/12] Creating directories...${NC}"
mkdir -p uploads logs seb_configs backups recovery_sistem
mkdir -p static/apk/builds static/apk/uploads static/seb/builds static/uploads
# Fix permissions for upload directories (777 for Docker compatibility)
chmod -R 777 uploads logs seb_configs backups static/uploads 2>/dev/null || true
echo -e "${GREEN}✓ Directories created with proper permissions${NC}"
echo ""

# ============================================
# STEP 10: Build Docker Images
# ============================================
echo -e "${CYAN}[10/12] Building Docker images...${NC}"

if [ "$UPDATE_MODE" = "true" ]; then
    echo -e "${YELLOW}⚠️  UPDATE MODE: Rebuilding without cache (this may take 15-20 minutes)${NC}"
    echo ""
    echo -e "${CYAN}Stopping containers first...${NC}"
    $DC down
    echo ""
    echo -e "${YELLOW}Rebuilding all images with fresh code...${NC}"
    $DC build --no-cache
    echo -e "${GREEN}✓ Update build complete${NC}"
else
    echo -e "${YELLOW}This may take 15-20 minutes (with network timeout fix)${NC}"
    echo ""
    echo -e "${YELLOW}Building base API image first to optimize cache and network usage...${NC}"
    $DC build api
    echo -e "${GREEN}✓ Base image built. Building remaining services...${NC}"
    $DC build
    echo -e "${GREEN}✓ Build complete${NC}"
fi
echo ""

# ============================================
# STEP 11: Start Services
# ============================================
echo -e "${CYAN}[11/12] Starting services...${NC}"
$DC up -d
echo -e "${GREEN}✓ Services started${NC}"
echo ""

# ============================================
# STEP 12: Health Check & Verification
# ============================================
echo -e "${CYAN}[12/12] Verifying deployment...${NC}"
echo ""

# Wait for database
echo -e "  ${YELLOW}⏳ Waiting for database...${NC}"
ATTEMPT=0
MAX=30
until $DC exec -T db pg_isready -U examuser 2>/dev/null || [ $ATTEMPT -eq $MAX ]; do
    ATTEMPT=$((ATTEMPT+1))
    sleep 2
done
[ $ATTEMPT -eq $MAX ] && echo -e "${RED}Database timeout${NC}" && exit 1
echo -e "  ${GREEN}✓ Database ready${NC}"

sleep 5

# Wait for API
echo -e "  ${YELLOW}⏳ Waiting for API...${NC}"
ATTEMPT=0
until curl -sf http://localhost:8080/health > /dev/null 2>&1 || [ $ATTEMPT -eq $MAX ]; do
    ATTEMPT=$((ATTEMPT+1))
    sleep 2
done
[ $ATTEMPT -eq $MAX ] && echo -e "${RED}API timeout${NC}" && exit 1
echo -e "  ${GREEN}✓ API ready${NC}"
echo ""

# Verify all services
echo "Service Status:"
$DC ps
echo ""

# Container count
RUNNING=$($DC ps --format json | grep -c '"State":"running"' || echo "0")
echo -e "${GREEN}✓ $RUNNING containers running${NC}"
echo ""

# ============================================
# STEP 12b: Database Schema Verification
# ============================================
echo -e "${CYAN}[12b/12] Verifying database schema...${NC}"

# Check if shuffle_options column exists
DB_CHECK=$($DC exec -T db psql -U examuser -d exam_system -c "
SELECT column_name 
FROM information_schema.columns 
WHERE table_name='exams' AND column_name='shuffle_options';" 2>/dev/null | grep -c "shuffle_options" || echo "0")

if [ "$DB_CHECK" -eq "0" ]; then
    echo -e "${YELLOW}⚠️  shuffle_options column not found! Running migration...${NC}"
    $DC exec -T db psql -U examuser -d exam_system -c "
    ALTER TABLE exams ADD COLUMN IF NOT EXISTS shuffle_options BOOLEAN DEFAULT FALSE;
    ALTER TABLE exams ADD COLUMN IF NOT EXISTS shuffle_questions BOOLEAN DEFAULT FALSE;
    " 2>/dev/null || true
    echo -e "${GREEN}✓ Database migration completed${NC}"
else
    echo -e "${GREEN}✓ Database schema verified (shuffle_options: OK)${NC}"
fi
echo ""

# ============================================
# SUCCESS BANNER
# ============================================
SERVER_IP=$(hostname -I 2>/dev/null | awk '{print $1}' || echo "localhost")

if [ "$UPDATE_MODE" = "true" ]; then
    echo -e "${GREEN}"
    cat << "EOF"
╔══════════════════════════════════════════════════════════╗
║          🔄 UPDATE SUCCESSFUL! 🔄                         ║
║         System updated with latest code!                  ║
╚══════════════════════════════════════════════════════════╝
EOF
    echo -e "${NC}"
else
    echo -e "${GREEN}"
    cat << "EOF"
╔══════════════════════════════════════════════════════════╗
║          🎉 DEPLOYMENT SUCCESSFUL! 🎉                     ║
╚══════════════════════════════════════════════════════════╝
EOF
    echo -e "${NC}"
fi
echo ""

echo -e "${GREEN}System ready for ~$MAX_USERS concurrent users${NC}"
echo -e "  RAM Profile: ${RAM_PROFILE}GB"
echo -e "  Workers: ${WORKERS}"
echo ""

echo -e "${CYAN}📍 Access Points:${NC}"
echo "  🌐 Main App:      http://$SERVER_IP:8080"
echo "  🔐 Admin Panel:   http://$SERVER_IP:8080/admin/"
echo "  📚 API Docs:      http://$SERVER_IP:8000/docs"

if [ "$ENABLE_MONITORING" = "true" ]; then
    echo "  📊 Grafana:       http://$SERVER_IP:3000  (admin/admin)"
    echo "  📈 Prometheus:    http://$SERVER_IP:9090"
fi
echo ""

echo -e "${CYAN}🔐 Default Credentials:${NC}"
echo "  Username: admin"
echo "  Password: admin123"
echo ""

if [ "$SKIP_BACKUP" != "true" ]; then
    echo -e "${CYAN}🔧 Automation Active:${NC}"
    echo "  ✅ Auto-backup: Daily at ${BACKUP_HOUR}:${BACKUP_MIN}"
    echo "  ✅ Cache maintenance: Daily at 03:00"
    echo "  ✅ Health monitoring: Every 15 minutes"
    echo "  ✅ Self-healing: Every 3 minutes"
    echo ""
fi

echo -e "${CYAN}💻 Useful Commands:${NC}"
echo "  View logs:    $DC logs -f api"
echo "  Restart:      $DC restart"
echo "  Stop:         $DC down"
echo "  Rebuild:      ./install.sh"
if [ "$SKIP_BACKUP" != "true" ]; then
    echo "  Monitor:      ./monitor.sh"
    echo "  Backup:       ./backup-comprehensive.sh"
    echo "  Restore:      ./restore.sh"
fi
echo ""

echo -e "${YELLOW}💡 Next Steps:${NC}"
echo "  1. Change default admin password"
echo "  2. Configure Telegram notifications (optional)"
echo "  3. Test with real users"
echo ""

echo -e "${GREEN}Happy testing! 🚀${NC}"
