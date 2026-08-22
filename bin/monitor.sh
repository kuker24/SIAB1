#!/bin/bash
# ============================================
# REAL-TIME MONITORING DASHBOARD
# Live system health monitoring
# ============================================

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

cd "$(dirname "$0")"

# Function to get container stats
display_dashboard() {
    clear
    echo -e "${CYAN}╔══════════════════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${CYAN}║${NC} ${BOLD}${BLUE}       UJIAN ONLINE - REAL-TIME MONITORING DASHBOARD${NC}                   ${CYAN}║${NC}"
    echo -e "${CYAN}╚══════════════════════════════════════════════════════════════════════════╝${NC}"
    echo ""
    echo -e "${YELLOW}⏰ Time: $(date '+%Y-%m-%d %H:%M:%S')${NC}  |  ${CYAN}🖥️  Server: $(hostname)${NC}"
    echo ""
    
    # Container Status
    echo -e "${CYAN}━━━ CONTAINER STATUS ━━━${NC}"
    
    # Check each critical container
    containers=("api" "db" "redis" "nginx" "celery_worker" "celery_beat")
    for container in "${containers[@]}"; do
        status=$($DC -f docker-compose.production.yml ps 2>/dev/null | grep "$container" | grep -i "up" || echo "")
        if [ -n "$status" ]; then
            echo -e "  ${GREEN}●${NC} $container: Running"
        else
            echo -e "  ${RED}●${NC} $container: DOWN"
        fi
    done
    echo ""
    
    # Resource Usage
    echo -e "${CYAN}━━━ RESOURCE USAGE ━━━${NC}"
    docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.MemPerc}}" 2>/dev/null | grep -E "NAME|ujian_online" | head -7
    echo ""
    
    # API Health
    echo -e "${CYAN}━━━ API HEALTH CHECK ━━━${NC}"
    API_START=$(date +%s%N)
    HEALTH=$(curl -s http://localhost:8000/health 2>/dev/null || echo "ERROR")
    API_END=$(date +%s%N)
    
    if [ "$HEALTH" != "ERROR" ]; then
        RESPONSE_MS=$(( (API_END - API_START) / 1000000 ))
        
        if [ "$RESPONSE_MS" -lt 100 ]; then
            COLOR=$GREEN
            STATUS="Excellent"
        elif [ "$RESPONSE_MS" -lt 500 ]; then
            COLOR=$YELLOW
            STATUS="Good"
        else
            COLOR=$RED
            STATUS="Slow"
        fi
        
        echo -e "  ${GREEN}✓${NC} API Status: ${GREEN}Online${NC}"
        echo -e "  ${COLOR}●${NC} Response Time: ${RESPONSE_MS}ms ($STATUS)"
    else
        echo -e "  ${RED}✗${NC} API Status: ${RED}OFFLINE${NC}"
    fi
    echo ""
    
    # Database Activity
    echo -e "${CYAN}━━━ DATABASE ACTIVITY ━━━${NC}"
    
    DB_ACTIVE=$($DC -f docker-compose.production.yml exec -T db psql -U examuser -d exam_system -tAc \
        "SELECT count(*) FROM pg_stat_activity WHERE state = 'active';" 2>/dev/null | tr -d '\n\r' || echo "0")
    
    DB_IDLE=$($DC -f docker-compose.production.yml exec -T db psql -U examuser -d exam_system -tAc \
        "SELECT count(*) FROM pg_stat_activity WHERE state = 'idle';" 2>/dev/null | tr -d '\n\r' || echo "0")
    
    DB_TOTAL=$($DC -f docker-compose.production.yml exec -T db psql -U examuser -d exam_system -tAc \
        "SELECT count(*) FROM pg_stat_activity;" 2>/dev/null | tr -d '\n\r' || echo "0")
    
    if [ "$DB_TOTAL" != "0" ] && [ "$DB_TOTAL" -gt 0 ] 2>/dev/null; then
        echo -e "  ${GREEN}✓${NC} Connections: $DB_TOTAL (Active: $DB_ACTIVE, Idle: $DB_IDLE)"
        
        # Check for slow queries
        SLOW_QUERIES=$($DC -f docker-compose.production.yml exec -T db psql -U examuser -d exam_system -tAc \
            "SELECT count(*) FROM pg_stat_activity WHERE state = 'active' AND (now() - query_start) > interval '2 seconds';" 2>/dev/null | tr -d '\n\r' || echo "0")
        
        if [ "$SLOW_QUERIES" -eq 0 ] 2>/dev/null; then
            echo -e "  ${GREEN}✓${NC} Slow Queries: 0"
        else
            echo -e "  ${YELLOW}⚠${NC} Slow Queries: $SLOW_QUERIES"
        fi
    else
        echo -e "  ${YELLOW}⚠${NC} Database: Cannot retrieve stats"
    fi
    echo ""
    
    # Redis Cache
    echo -e "${CYAN}━━━ REDIS CACHE ━━━${NC}"
    
    REDIS_PING=$($DC -f docker-compose.production.yml exec -T redis redis-cli ping 2>/dev/null | tr -d '\r' || echo "ERROR")
    
    if [ "$REDIS_PING" == "PONG" ]; then
        REDIS_MEM=$($DC -f docker-compose.production.yml exec -T redis redis-cli info memory 2>/dev/null | grep "used_memory_human:" | cut -d: -f2 | tr -d '\r\n ')
        REDIS_CLIENTS=$($DC -f docker-compose.production.yml exec -T redis redis-cli info stats 2>/dev/null | grep "connected_clients:" | cut -d: -f2 | tr -d '\r\n ')
        
        echo -e "  ${GREEN}✓${NC} Status: Connected"
        echo -e "  ${GREEN}●${NC} Memory: $REDIS_MEM"
        echo -e "  ${GREEN}●${NC} Clients: $REDIS_CLIENTS"
    else
        echo -e "  ${RED}✗${NC} Status: ${RED}OFFLINE${NC}"
    fi
    echo ""
    
    # System Resources
    echo -e "${CYAN}━━━ SYSTEM RESOURCES ━━━${NC}"
    
    TOTAL_MEM=$(free -h | awk '/^Mem:/ {print $2}')
    USED_MEM=$(free -h | awk '/^Mem:/ {print $3}')
    MEM_PERCENT=$(free | awk '/^Mem:/ {printf "%.0f", $3/$2 * 100}')
    
    if [ "$MEM_PERCENT" -lt 70 ]; then
        MEM_COLOR=$GREEN
        MEM_STATUS="Normal"
    elif [ "$MEM_PERCENT" -lt 85 ]; then
        MEM_COLOR=$YELLOW
        MEM_STATUS="High"
    else
        MEM_COLOR=$RED
        MEM_STATUS="Critical"
    fi
    
    echo -e "  ${MEM_COLOR}●${NC} Memory: $USED_MEM / $TOTAL_MEM (${MEM_PERCENT}% - $MEM_STATUS)"
    
    DISK_USAGE=$(df -h . | awk 'NR==2 {print $5}' | sed 's/%//')
    DISK_AVAIL=$(df -h . | awk 'NR==2 {print $4}')
    DISK_TOTAL=$(df -h . | awk 'NR==2 {print $2}')
    
    if [ "$DISK_USAGE" -lt 70 ]; then
        DISK_COLOR=$GREEN
        DISK_STATUS="Normal"
    elif [ "$DISK_USAGE" -lt 85 ]; then
        DISK_COLOR=$YELLOW
        DISK_STATUS="High"
    else
        DISK_COLOR=$RED
        DISK_STATUS="Critical"
    fi
    
    echo -e "  ${DISK_COLOR}●${NC} Disk: ${DISK_USAGE}% used ($DISK_AVAIL / $DISK_TOTAL available - $DISK_STATUS)"
    echo ""
    
    # Backup Status
    echo -e "${CYAN}━━━ BACKUP STATUS ━━━${NC}"
    
    if [ -d "recovery_sistem" ]; then
        LAST_BACKUP=$(ls -t recovery_sistem/backup_*.tar.gz 2>/dev/null | head -1)
        
        if [ -n "$LAST_BACKUP" ]; then
            BACKUP_NAME=$(basename "$LAST_BACKUP")
            BACKUP_DATE=$(echo "$BACKUP_NAME" | grep -oP '\d{8}_\d{6}')
            BACKUP_SIZE=$(du -h "$LAST_BACKUP" | cut -f1)
            
            # Parse backup date
            BACKUP_YEAR=${BACKUP_DATE:0:4}
            BACKUP_MONTH=${BACKUP_DATE:4:2}
            BACKUP_DAY=${BACKUP_DATE:6:2}
            BACKUP_HOUR=${BACKUP_DATE:9:2}
            BACKUP_MIN=${BACKUP_DATE:11:2}
            
            FORMATTED_DATE="${BACKUP_YEAR}-${BACKUP_MONTH}-${BACKUP_DAY} ${BACKUP_HOUR}:${BACKUP_MIN}"
            
            # Calculate age
            NOW=$(date +%s)
            BACKUP_TIMESTAMP=$(date -d "$FORMATTED_DATE" +%s 2>/dev/null || date +%s)
            AGE_HOURS=$(( (NOW - BACKUP_TIMESTAMP) / 3600 ))
            
            if [ "$AGE_HOURS" -lt 24 ]; then
                BACKUP_COLOR=$GREEN
                AGE_TEXT="$AGE_HOURS hours ago"
            elif [ "$AGE_HOURS" -lt 48 ]; then
                BACKUP_COLOR=$YELLOW
                AGE_TEXT="$(( AGE_HOURS / 24 )) day ago"
            else
                BACKUP_COLOR=$RED
                AGE_TEXT="$(( AGE_HOURS / 24 )) days ago"
            fi
            
            echo -e "  ${BACKUP_COLOR}✓${NC} Last Backup: $FORMATTED_DATE ($AGE_TEXT)"
            echo -e "  ${GREEN}●${NC} Size: $BACKUP_SIZE"
        else
            echo -e "  ${YELLOW}⚠${NC} No backups found"
        fi
        
        BACKUP_COUNT=$(ls recovery_sistem/backup_*.tar.gz 2>/dev/null | wc -l)
        echo -e "  ${GREEN}●${NC} Total Backups: $BACKUP_COUNT (30-day retention)"
    else
        echo -e "  ${YELLOW}⚠${NC} Backup system not configured"
        echo -e "  ${CYAN}ℹ${NC} Run ${BOLD}./backup-comprehensive.sh${NC} to create first backup"
    fi
    echo ""
    
    # Footer
    echo -e "${CYAN}──────────────────────────────────────────────────────────────────────────${NC}"
    echo -e "Press ${BOLD}${YELLOW}Ctrl+C${NC} to exit  |  Auto-refresh every ${YELLOW}5 seconds${NC}  |  ${CYAN}./deteksi_masalah.sh${NC} for full diagnostic"
    echo ""
}

# Trap Ctrl+C for clean exit
trap 'echo -e "\n${CYAN}Monitoring stopped.${NC}"; exit 0' INT

# Main loop
echo -e "${CYAN}Starting real-time monitoring...${NC}"
sleep 1

while true; do
    display_dashboard
    sleep 5
done
