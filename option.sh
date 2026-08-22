#!/bin/bash

##############################################################################
# SISTEM UJIAN ONLINE - CENTRAL CONTROL PANEL
# Multi-function management script untuk semua operasi sistem
# 
# Catatan: Script ini bisa dijalankan dari folder manapun dalam project tree
#          Script akan otomatis navigate ke ujian_online/
##############################################################################

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
MAGENTA='\033[0;35m'
CYAN='\033[0;36m'
WHITE='\033[1;37m'
NC='\033[0m' # No Color

# Emojis
CHECK="✅"
CROSS="❌"
ROCKET="🚀"
WRENCH="🔧"
CHART="📊"
BACKUP="💾"
TRASH="🗑️"
INFO="ℹ️"
WARNING="⚠️"

# Docker compose file
COMPOSE_FILE="docker-compose.production.yml"

##############################################################################
# AUTO-DETECT PROJECT DIRECTORY
##############################################################################

# Fungsi untuk mencari direktori ujian_online
find_project_dir() {
    local current_dir="$(pwd)"
    local search_dir="$current_dir"
    
    # Cek apakah sudah di ujian_online/
    if [ -f "$search_dir/$COMPOSE_FILE" ]; then
        return 0
    fi
    
    # Cek apakah ada subfolder ujian_online/
    if [ -d "$search_dir/ujian_online" ] && [ -f "$search_dir/ujian_online/$COMPOSE_FILE" ]; then
        cd "$search_dir/ujian_online"
        return 0
    fi
    
    # Cari di parent directories (max 3 levels)
    for i in {1..3}; do
        search_dir="$search_dir/.."
        if [ -f "$search_dir/$COMPOSE_FILE" ]; then
            cd "$search_dir"
            return 0
        fi
        if [ -d "$search_dir/ujian_online" ] && [ -f "$search_dir/ujian_online/$COMPOSE_FILE" ]; then
            cd "$search_dir/ujian_online"
            return 0
        fi
    done
    
    return 1
}

 # Navigate to project directory
 if ! find_project_dir; then
     echo -e "${RED}${CROSS} Error: docker-compose.production.yml not found!${NC}"
     echo -e "${YELLOW}${INFO} Please run this script from:${NC}"
     echo "   - Ujian-2026/ (root folder)"
     echo "   - Ujian-2026/ujian_online/ (project folder)"
     exit 1
 fi

# Simpan direktori project
PROJECT_DIR="$(pwd)"
echo -e "${GREEN}${CHECK} Working directory: $PROJECT_DIR${NC}"
sleep 0.5

##############################################################################
# UTILITY FUNCTIONS
##############################################################################

print_header() {
    clear
    echo -e "${CYAN}╔════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${CYAN}║                                                            ║${NC}"
    echo -e "${CYAN}║         ${WHITE}SISTEM UJIAN ONLINE - CONTROL PANEL${CYAN}           ║${NC}"
    echo -e "${CYAN}║                 ${MAGENTA}Enterprise Management Tool${CYAN}                ║${NC}"
    echo -e "${CYAN}║                                                            ║${NC}"
    echo -e "${CYAN}╚════════════════════════════════════════════════════════════╝${NC}"
    echo ""
}

print_success() {
    echo -e "${GREEN}${CHECK} $1${NC}"
}

print_error() {
    echo -e "${RED}${CROSS} $1${NC}"
}

print_info() {
    echo -e "${BLUE}${INFO} $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}${WARNING} $1${NC}"
}

pause() {
    echo ""
    read -p "Press ENTER to continue..." dummy
}

confirm() {
    read -p "$1 (y/n): " choice
    case "$choice" in
        y|Y ) return 0;;
        * ) return 1;;
    esac
}

##############################################################################
# SERVICE RESTART FUNCTIONS
##############################################################################

restart_api() {
    print_info "Restarting API container..."
    docker compose -f $COMPOSE_FILE restart api
    if [ $? -eq 0 ]; then
        print_success "API container restarted successfully!"
    else
        print_error "Failed to restart API container"
    fi
}

restart_db() {
    print_warning "⚠️  WARNING: This will temporarily interrupt database connections!"
    if confirm "Continue?"; then
        print_info "Restarting database container..."
        docker compose -f $COMPOSE_FILE restart db
        if [ $? -eq 0 ]; then
            print_success "Database container restarted successfully!"
        else
            print_error "Failed to restart database container"
        fi
    fi
}

restart_redis() {
    print_info "Restarting Redis container..."
    docker compose -f $COMPOSE_FILE restart redis
    if [ $? -eq 0 ]; then
        print_success "Redis container restarted successfully!"
    else
        print_error "Failed to restart Redis container"
    fi
}

restart_nginx() {
    print_info "Restarting Nginx container..."
    docker compose -f $COMPOSE_FILE restart nginx
    if [ $? -eq 0 ]; then
        print_success "Nginx container restarted successfully!"
    else
        print_error "Failed to restart Nginx container"
    fi
}

restart_all() {
    print_warning "⚠️  WARNING: This will restart ALL containers!"
    if confirm "Continue?"; then
        print_info "Restarting all containers..."
        docker compose -f $COMPOSE_FILE restart
        if [ $? -eq 0 ]; then
            print_success "All containers restarted successfully!"
        else
            print_error "Failed to restart containers"
        fi
    fi
}

##############################################################################
# UPDATE & REBUILD FUNCTIONS (NEW!)
##############################################################################

update_and_rebuild() {
    print_header
    echo -e "${CYAN}═══════════════════════════════════════════════════════════${NC}"
    echo -e "${WHITE}              UPDATE & REBUILD SERVICES                     ${NC}"
    echo -e "${CYAN}═══════════════════════════════════════════════════════════${NC}"
    echo ""
    print_warning "⚠️  This will rebuild Docker images with updated code!"
    echo ""
    echo "Steps:"
    echo "  1. Stop running containers"
    echo "  2. Rebuild images (no cache)"
    echo "  3. Start containers"
    echo "  4. Health check"
    echo ""
    
    if ! confirm "Continue with update & rebuild?"; then
        print_info "Operation cancelled."
        return
    fi
    
    print_info "Step 1/4: Stopping containers..."
    docker compose -f $COMPOSE_FILE down
    if [ $? -ne 0 ]; then
        print_error "Failed to stop containers"
        return 1
    fi
    print_success "Containers stopped"
    
    print_info "Step 2/4: Rebuilding images (this may take 10-15 minutes)..."
    echo -e "${YELLOW}Building without cache to ensure latest code...${NC}"
    docker compose -f $COMPOSE_FILE build --no-cache
    if [ $? -ne 0 ]; then
        print_error "Failed to rebuild images"
        return 1
    fi
    print_success "Images rebuilt successfully"
    
    print_info "Step 3/4: Starting containers..."
    docker compose -f $COMPOSE_FILE up -d
    if [ $? -ne 0 ]; then
        print_error "Failed to start containers"
        return 1
    fi
    print_success "Containers started"
    
    print_info "Step 4/4: Running health check..."
    sleep 5
    
    # Check API health
    ATTEMPT=0
    MAX=30
    until curl -sf http://localhost:8080/health > /dev/null 2>&1 || [ $ATTEMPT -eq $MAX ]; do
        ATTEMPT=$((ATTEMPT+1))
        echo -e "  ${YELLOW}⏳ Waiting for API... (${ATTEMPT}/${MAX})${NC}"
        sleep 2
    done
    
    if [ $ATTEMPT -eq $MAX ]; then
        print_error "API health check timeout"
        echo ""
        echo "Check logs with: docker compose -f $COMPOSE_FILE logs -f api"
        return 1
    fi
    
    print_success "Update & rebuild completed successfully!"
    echo ""
    echo -e "${GREEN}System is running with updated code.${NC}"
    echo ""
    echo "Next steps:"
    echo "  - Test the application: http://localhost:8080"
    echo "  - View logs: ./option.sh (Menu 4)"
    echo "  - Check status: ./option.sh (Menu 3)"
    
    pause
}

quick_restart() {
    print_info "Quick restart (stop + start, no rebuild)..."
    docker compose -f $COMPOSE_FILE restart
    if [ $? -eq 0 ]; then
        print_success "Quick restart completed!"
    else
        print_error "Quick restart failed"
    fi
}

##############################################################################
# MONITORING FUNCTIONS
##############################################################################

show_system_status() {
    print_header
    echo -e "${CYAN}═══════════════════════════════════════════════════════════${NC}"
    echo -e "${WHITE}                   SYSTEM STATUS                           ${NC}"
    echo -e "${CYAN}═══════════════════════════════════════════════════════════${NC}"
    echo ""
    
    docker compose -f $COMPOSE_FILE ps
    
    echo ""
    print_info "Container Resource Usage:"
    docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.NetIO}}"
    
    pause
}

show_real_time_monitor() {
    print_info "Starting real-time monitor... (Press Ctrl+C to exit)"
    sleep 2
    
    if [ -f "./monitor.sh" ]; then
        ./monitor.sh
    else
        # Fallback to docker stats
        docker stats
    fi
}

show_health_check() {
    print_info "Running health check..."
    
    if [ -f "./health-monitor.sh" ]; then
        ./health-monitor.sh
    else
        # Manual health check
        echo ""
        echo -e "${YELLOW}═══ API Health ═══${NC}"
        curl -s http://localhost:8080/health | jq . 2>/dev/null || curl -s http://localhost:8080/health
        
        echo ""
        echo -e "${YELLOW}═══ Database Connection ═══${NC}"
        docker compose -f $COMPOSE_FILE exec db pg_isready -U examuser
        
        echo ""
        echo -e "${YELLOW}═══ Redis Connection ═══${NC}"
        docker compose -f $COMPOSE_FILE exec redis redis-cli ping
    fi
    
    pause
}

detect_problems() {
    print_info "Detecting system problems..."
    
    if [ -f "./deteksi_masalah.sh" ]; then
        ./deteksi_masalah.sh
    else
        print_warning "deteksi_masalah.sh not found"
    fi
    
    pause
}

##############################################################################
# LOG VIEWER FUNCTIONS
##############################################################################

view_logs() {
    print_header
    echo -e "${CYAN}═══════════════════════════════════════════════════════════${NC}"
    echo -e "${WHITE}                   VIEW LOGS                               ${NC}"
    echo -e "${CYAN}═══════════════════════════════════════════════════════════${NC}"
    echo ""
    echo "  1) API logs"
    echo "  2) Database logs"
    echo "  3) Redis logs"
    echo "  4) Nginx logs"
    echo "  5) All logs (combined)"
    echo "  0) Back to main menu"
    echo ""
    read -p "Select service: " log_choice
    
    case $log_choice in
        1) docker compose -f $COMPOSE_FILE logs -f --tail=100 api ;;
        2) docker compose -f $COMPOSE_FILE logs -f --tail=100 db ;;
        3) docker compose -f $COMPOSE_FILE logs -f --tail=100 redis ;;
        4) docker compose -f $COMPOSE_FILE logs -f --tail=100 nginx ;;
        5) docker compose -f $COMPOSE_FILE logs -f --tail=100 ;;
        0) return ;;
        *) print_error "Invalid choice" ;;
    esac
}

##############################################################################
# BACKUP & RESTORE FUNCTIONS
##############################################################################

backup_menu() {
    print_header
    echo -e "${CYAN}═══════════════════════════════════════════════════════════${NC}"
    echo -e "${WHITE}                BACKUP & RESTORE                           ${NC}"
    echo -e "${CYAN}═══════════════════════════════════════════════════════════${NC}"
    echo ""
    echo "  1) ${BACKUP} Comprehensive backup (DB + uploads + configs)"
    echo "  2) ${BACKUP} Database-only backup"
    echo "  3) 🔙 Restore from backup"
    echo "  4) 📋 List available backups"
    echo "  0) Back to main menu"
    echo ""
    read -p "Select option: " backup_choice
    
    case $backup_choice in
        1)
            if [ -f "./backup-comprehensive.sh" ]; then
                ./backup-comprehensive.sh
            else
                print_error "backup-comprehensive.sh not found"
            fi
            ;;
        2)
            if [ -f "./backup-database.sh" ]; then
                ./backup-database.sh
            else
                print_error "backup-database.sh not found"
            fi
            ;;
        3)
            if [ -f "./restore.sh" ]; then
                ./restore.sh
            else
                print_error "restore.sh not found"
            fi
            ;;
        4)
            if [ -d "./recovery_sistem" ]; then
                ls -lh ./recovery_sistem/
            else
                print_warning "No backups directory found"
            fi
            ;;
        0) return ;;
        *) print_error "Invalid choice" ;;
    esac
    
    pause
}

##############################################################################
# DATABASE OPERATIONS
##############################################################################

database_menu() {
    print_header
    echo -e "${CYAN}═══════════════════════════════════════════════════════════${NC}"
    echo -e "${WHITE}              DATABASE OPERATIONS                          ${NC}"
    echo -e "${CYAN}═══════════════════════════════════════════════════════════${NC}"
    echo ""
    echo "  1) 🔍 Check database size"
    echo "  2) 📊 List all tables"
    echo "  3) 🔗 Open PostgreSQL shell (psql)"
    echo "  4) 👥 Show active connections"
    echo "  5) 🧹 Vacuum database (optimize)"
    echo "  6) 🔄 Run shuffle_options migration (for v2.1 upgrade)"
    echo "  0) Back to main menu"
    echo ""
    read -p "Select option: " db_choice
    
    case $db_choice in
        1)
            print_info "Database size:"
            docker compose -f $COMPOSE_FILE exec db psql -U examuser -d exam_system \
                -c "SELECT pg_size_pretty(pg_database_size('exam_system'));"
            ;;
        2)
            print_info "Tables in database:"
            docker compose -f $COMPOSE_FILE exec db psql -U examuser -d exam_system -c "\dt"
            ;;
        3)
            print_info "Opening PostgreSQL shell... (type 'exit' to quit)"
            docker compose -f $COMPOSE_FILE exec db psql -U examuser -d exam_system
            ;;
        4)
            print_info "Active database connections:"
            docker compose -f $COMPOSE_FILE exec db psql -U examuser -d exam_system \
                -c "SELECT pid, usename, application_name, client_addr, state FROM pg_stat_activity WHERE datname='exam_system';"
            ;;
        5)
            if confirm "Run VACUUM on database?"; then
                print_info "Running VACUUM..."
                docker compose -f $COMPOSE_FILE exec db psql -U examuser -d exam_system -c "VACUUM VERBOSE;"
                print_success "VACUUM completed!"
            fi
            ;;
        6)
            if [ -f "./migrate-shuffle-options.sh" ]; then
                ./migrate-shuffle-options.sh
            else
                print_error "migrate-shuffle-options.sh not found"
            fi
            ;;
        0) return ;;
        *) print_error "Invalid choice" ;;
    esac
    
    pause
}

##############################################################################
# CACHE OPERATIONS
##############################################################################

cache_menu() {
    print_header
    echo -e "${CYAN}═══════════════════════════════════════════════════════════${NC}"
    echo -e "${WHITE}               CACHE OPERATIONS                            ${NC}"
    echo -e "${CYAN}═══════════════════════════════════════════════════════════${NC}"
    echo ""
    echo "  1) 📊 Show Redis info"
    echo "  2) 💾 Show Redis memory usage"
    echo "  3) 🗑️  Flush all cache (DANGEROUS!)"
    echo "  4) 🔧 Open Redis CLI"
    echo "  5) 🧹 Run cache maintenance script"
    echo "  0) Back to main menu"
    echo ""
    read -p "Select option: " cache_choice
    
    case $cache_choice in
        1)
            print_info "Redis information:"
            docker compose -f $COMPOSE_FILE exec redis redis-cli INFO
            ;;
        2)
            print_info "Redis memory usage:"
            docker compose -f $COMPOSE_FILE exec redis redis-cli INFO memory
            ;;
        3)
            print_warning "⚠️  WARNING: This will DELETE ALL cached data!"
            if confirm "Are you ABSOLUTELY sure?"; then
                docker compose -f $COMPOSE_FILE exec redis redis-cli FLUSHALL
                print_success "All cache flushed!"
            else
                print_info "Operation cancelled"
            fi
            ;;
        4)
            print_info "Opening Redis CLI... (type 'exit' to quit)"
            docker compose -f $COMPOSE_FILE exec redis redis-cli
            ;;
        5)
            if [ -f "./cache-maintenance.sh" ]; then
                ./cache-maintenance.sh
            else
                print_error "cache-maintenance.sh not found"
            fi
            ;;
        0) return ;;
        *) print_error "Invalid choice" ;;
    esac
    
    pause
}

##############################################################################
# DEPLOYMENT OPERATIONS
##############################################################################

deployment_menu() {
    print_header
    echo -e "${CYAN}═══════════════════════════════════════════════════════════${NC}"
    echo -e "${WHITE}            DEPLOYMENT OPERATIONS                          ${NC}"
    echo -e "${CYAN}═══════════════════════════════════════════════════════════${NC}"
    echo ""
    echo "  1) ${ROCKET} Full deploy (start all services)"
    echo "  2) ${ROCKET} Rebuild and deploy (no cache)"
    echo "  3) ${TRASH} Stop all services"
    echo "  4) ${TRASH} Full undeploy (remove containers)"
    echo "  5) ${WRENCH} Full rebuild (RESET EVERYTHING)"
    echo "  0) Back to main menu"
    echo ""
    read -p "Select option: " deploy_choice
    
    case $deploy_choice in
        1)
            if [ -f "./deploy.sh" ]; then
                ./deploy.sh
            else
                print_info "Running docker compose up..."
                docker compose -f $COMPOSE_FILE up -d
            fi
            ;;
        2)
            print_warning "This will rebuild all Docker images without cache"
            if confirm "Continue?"; then
                docker compose -f $COMPOSE_FILE down
                docker compose -f $COMPOSE_FILE build --no-cache
                docker compose -f $COMPOSE_FILE up -d
                print_success "Rebuild and deploy completed!"
            fi
            ;;
        3)
            print_info "Stopping all services..."
            docker compose -f $COMPOSE_FILE down
            print_success "All services stopped!"
            ;;
        4)
            if [ -f "./undeploy.sh" ]; then
                ./undeploy.sh
            else
                print_warning "This will remove all containers"
                if confirm "Continue?"; then
                    docker compose -f $COMPOSE_FILE down -v
                    print_success "Undeploy completed!"
                fi
            fi
            ;;
        5)
            if [ -f "./rebuild.sh" ]; then
                print_error "⚠️  DANGER: This will DELETE ALL DATA!"
                ./rebuild.sh
            else
                print_error "rebuild.sh not found"
            fi
            ;;
        0) return ;;
        *) print_error "Invalid choice" ;;
    esac
    
    pause
}

##############################################################################
# SYSTEM INFO
##############################################################################

show_system_info() {
    print_header
    echo -e "${CYAN}═══════════════════════════════════════════════════════════${NC}"
    echo -e "${WHITE}                  SYSTEM INFORMATION                       ${NC}"
    echo -e "${CYAN}═══════════════════════════════════════════════════════════${NC}"
    echo ""
    
    # OS Info
    echo -e "${YELLOW}═══ Operating System ═══${NC}"
    uname -a
    echo ""
    
    # Docker Info
    echo -e "${YELLOW}═══ Docker Version ═══${NC}"
    docker --version
    docker compose version
    echo ""
    
    # Disk Usage
    echo -e "${YELLOW}═══ Disk Usage ═══${NC}"
    df -h | grep -E "Filesystem|/$|/home"
    echo ""
    
    # Memory Usage
    echo -e "${YELLOW}═══ Memory Usage ═══${NC}"
    free -h
    echo ""
    
    # Docker Images
    echo -e "${YELLOW}═══ Docker Images ═══${NC}"
    docker images --format "table {{.Repository}}\t{{.Tag}}\t{{.Size}}"
    echo ""
    
    # Environment
    echo -e "${YELLOW}═══ Environment ═══${NC}"
    if [ -f ".env" ]; then
        echo "RAM_PROFILE: $(grep -E '^RAM_PROFILE=' .env | cut -d'=' -f2)"
        echo "WORKERS: $(grep -E '^WORKERS=' .env | cut -d'=' -f2)"
        echo "APP_ENV: $(grep -E '^APP_ENV=' .env | cut -d'=' -f2)"
        echo "DEBUG: $(grep -E '^DEBUG=' .env | cut -d'=' -f2)"
    else
        print_warning ".env file not found"
    fi
    
    pause
}

##############################################################################
# POWER CONTROL FUNCTIONS
##############################################################################

turn_on_docker() {
    print_header
    echo -e "${CYAN}═══════════════════════════════════════════════════════════${NC}"
    echo -e "${WHITE}                 STARTING SYSTEM                           ${NC}"
    echo -e "${CYAN}═══════════════════════════════════════════════════════════${NC}"
    echo ""
    print_info "Starting Ujian Online System (Docker)..."
    
    # Fix upload directory permissions before starting
    print_info "Fixing upload directory permissions..."
    mkdir -p static/uploads uploads logs
    chmod -R 777 static/uploads uploads logs 2>/dev/null || true
    
    if [ -f "./deploy.sh" ]; then
        print_info "Using deploy.sh..."
        ./deploy.sh
    else
        docker compose -f $COMPOSE_FILE up -d
    fi
    
    if [ $? -eq 0 ]; then
        print_success "System STARTED successfully!"
        echo ""
        print_info "Web App: http://localhost:8080"
        print_info "Admin:   http://localhost:8080/admin/"
    else
        print_error "Failed to start system."
    fi
    pause
}

turn_off_docker() {
    print_header
    echo -e "${CYAN}═══════════════════════════════════════════════════════════${NC}"
    echo -e "${WHITE}                 STOPPING SYSTEM                           ${NC}"
    echo -e "${CYAN}═══════════════════════════════════════════════════════════${NC}"
    echo ""
    print_warning "⚠️  WARNING: This will STOP all containers (docker compose down)"
    echo "Services will be unavailable until you start them again."
    echo ""
    
    if confirm "Are you sure you want to Turn OFF the system?"; then
        print_info "Stopping system..."
        docker compose -f $COMPOSE_FILE down
        
        if [ $? -eq 0 ]; then
            print_success "System STOPPED successfully!"
        else
            print_error "Failed to stop system."
        fi
    else
        print_info "Operation cancelled."
    fi
    pause
}

##############################################################################
# RESTART MENU
##############################################################################

restart_menu() {
    print_header
    echo -e "${CYAN}═══════════════════════════════════════════════════════════${NC}"
    echo -e "${WHITE}              RESTART & UPDATE SERVICES                    ${NC}"
    echo -e "${CYAN}═══════════════════════════════════════════════════════════${NC}"
    echo ""
    echo "  ${WRENCH}  BASIC RESTART (Fast, keeps current code)"
    echo "     1) Restart API (FastAPI)"
    echo "     2) Restart Database (PostgreSQL)"
    echo "     3) Restart Cache (Redis)"
    echo "     4) Restart Web Server (Nginx)"
    echo "     5) Quick restart ALL (stop + start)"
    echo ""
    echo "  ${ROCKET} UPDATE & REBUILD (Apply code changes)"
    echo "     6) 🔥 Update & Rebuild (rebuild images with new code)"
    echo ""
    echo "  0) Back to main menu"
    echo ""
    read -p "Select option: " restart_choice
    
    case $restart_choice in
        1) restart_api ;;
        2) restart_db ;;
        3) restart_redis ;;
        4) restart_nginx ;;
        5) quick_restart ;;
        6) update_and_rebuild ;;
        0) return ;;
        *) print_error "Invalid choice" ;;
    esac
    
    pause
}

##############################################################################
# MONITORING MENU
##############################################################################

monitoring_menu() {
    print_header
    echo -e "${CYAN}═══════════════════════════════════════════════════════════${NC}"
    echo -e "${WHITE}              SYSTEM MONITORING                            ${NC}"
    echo -e "${CYAN}═══════════════════════════════════════════════════════════${NC}"
    echo ""
    echo "  1) ${CHART} System status & resource usage"
    echo "  2) ${CHART} Real-time monitoring dashboard"
    echo "  3) ${CHECK} Health check (all services)"
    echo "  4) 🔍 Detect problems"
    echo "  5) 📝 View logs"
    echo "  0) Back to main menu"
    echo ""
    read -p "Select option: " monitor_choice
    
    case $monitor_choice in
        1) show_system_status ;;
        2) show_real_time_monitor ;;
        3) show_health_check ;;
        4) detect_problems ;;
        5) view_logs ;;
        0) return ;;
        *) print_error "Invalid choice" ;;
    esac
}

##############################################################################
# MAIN MENU
##############################################################################

main_menu() {
    while true; do
        print_header
        echo -e "${CYAN}═══════════════════════════════════════════════════════════${NC}"
        echo -e "${WHITE}                    MAIN MENU                             ${NC}"
        echo -e "${CYAN}═══════════════════════════════════════════════════════════${NC}"
        echo ""
        echo "  ${WRENCH}  SERVICE MANAGEMENT"
        echo "     1) Restart services"
        echo "     2) Deployment operations"
        echo ""
        echo "  ${CHART}  MONITORING & LOGS"
        echo "     3) System monitoring"
        echo "     4) View logs"
        echo ""
        echo "  ${BACKUP}  DATA MANAGEMENT"
        echo "     5) Backup & restore"
        echo "     6) Database operations"
        echo "     7) Cache operations"
        echo ""
        echo "  ${INFO}  SYSTEM INFO"
        echo "     8) System information"
        echo ""
        echo "  ⚡ POWER CONTROL"
        echo "     9) ${ROCKET} TURN ON DOCKER (Hidupkan)"
        echo "     10) 🔴 TURN OFF DOCKER (Matikan)"
        echo ""
        echo "  0) ${CROSS} Exit"
        echo ""
        echo -e "${CYAN}═══════════════════════════════════════════════════════════${NC}"
        echo ""
        read -p "Enter your choice: " choice
        
        case $choice in
            1) restart_menu ;;
            2) deployment_menu ;;
            3) monitoring_menu ;;
            4) view_logs ;;
            5) backup_menu ;;
            6) database_menu ;;
            7) cache_menu ;;
            8) show_system_info ;;
            9) turn_on_docker ;;
            10) turn_off_docker ;;
            0)
                print_info "Goodbye! 👋"
                exit 0
                ;;
            *)
                print_error "Invalid choice. Please try again."
                sleep 1
                ;;
        esac
    done
}

##############################################################################
# MAIN EXECUTION
##############################################################################

# Directory check already done at the top (auto-detection)
# Run main menu
main_menu
