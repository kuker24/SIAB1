#!/bin/bash
# ============================================
# HEALTH MONITORING WITH TELEGRAM ALERTS
# Auto-check system health & send alerts
# ============================================

set -e

# Load telegram notification function
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
BACKUP_DIR="${BACKUP_ROOT:-${PROJECT_ROOT}/recovery_sistem}"
source "${SCRIPT_DIR}/telegram-notify.sh"

# Detect docker compose
if command -v docker-compose &> /dev/null; then
    DC="docker-compose"
elif docker compose version &> /dev/null 2>&1; then
    DC="docker compose"
else
    DC="docker compose"
fi

cd "$PROJECT_ROOT"

# Thresholds
DISK_THRESHOLD=85
MEMORY_THRESHOLD=90
BACKUP_AGE_HOURS=26  # Alert if backup >26 hours old

ALERT_SENT=false

# ============================================
# Check Disk Space
# ============================================
check_disk() {
    DISK_USAGE=$(df -h / | awk 'NR==2 {print $5}' | sed 's/%//')
    
    if [ "$DISK_USAGE" -gt "$DISK_THRESHOLD" ]; then
        DISK_AVAIL=$(df -h / | awk 'NR==2 {print $4}')
        
        send_telegram "⚠️ *ALERT: Disk Space Critical!*

📊 Server: \`$(hostname)\`
💾 Disk Usage: *${DISK_USAGE}%*
📂 Available: ${DISK_AVAIL}

⏰ Time: $(get_timestamp)

🔧 *Action Required:*
• Check /var/log for large files
• Run cleanup scripts
• Consider expanding disk"
        
        ALERT_SENT=true
    fi
}

# ============================================
# Check Memory Usage
# ============================================
check_memory() {
    TOTAL_MEM=$(free -m | awk '/^Mem:/{print $2}')
    USED_MEM=$(free -m | awk '/^Mem:/{print $3}')
    MEM_PERCENT=$(free | awk '/^Mem:/ {printf "%.0f", $3/$2 * 100}')
    
    if [ "$MEM_PERCENT" -gt "$MEMORY_THRESHOLD" ]; then
        send_telegram "⚠️ *ALERT: Memory Critical!*

📊 Server: \`$(hostname)\`
🧠 Memory Usage: *${MEM_PERCENT}%*
📈 Used: ${USED_MEM}MB / ${TOTAL_MEM}MB

⏰ Time: $(get_timestamp)

🔧 *Action Required:*
• Check for memory leaks
• Restart heavy services
• Consider adding RAM"
        
        ALERT_SENT=true
    fi
}

# ============================================
# Check Docker Services
# ============================================
check_services() {
    services=("api" "db" "redis" "nginx")
    DOWN_SERVICES=""
    
    for service in "${services[@]}"; do
        if ! $DC -f docker-compose.production.yml ps 2>/dev/null | grep -q "$service.*Up"; then
            DOWN_SERVICES="${DOWN_SERVICES}
• ${service}"
        fi
    done
    
    if [ -n "$DOWN_SERVICES" ]; then
        send_telegram "🚨 *ALERT: Services DOWN!*

📊 Server: \`$(hostname)\`
❌ *Services Not Running:*${DOWN_SERVICES}

⏰ Time: $(get_timestamp)

🔧 *Action Required:*
• Check logs: docker compose logs
• Restart: ./rebuild.sh
• Check disk space"
        
        ALERT_SENT=true
    fi
}

# ============================================
# Check API Health
# ============================================
check_api() {
    API_STATUS=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1/health 2>/dev/null || echo "000")
    
    if [ "$API_STATUS" != "200" ]; then
        send_telegram "🚨 *ALERT: API Not Responding!*

📊 Server: \`$(hostname)\`
🌐 Status Code: ${API_STATUS}
❌ API Health Check: *FAILED*

⏰ Time: $(get_timestamp)

🔧 *Action Required:*
• Check API logs
• Restart API container
• Check database connection"
        
        ALERT_SENT=true
    fi
}

# ============================================
# Check Last Backup
# ============================================
check_backup() {
    if [ -d "$BACKUP_DIR" ]; then
        LAST_BACKUP=$(ls -t "$BACKUP_DIR"/backup_*.tar.gz 2>/dev/null | head -1)
        
        if [ -n "$LAST_BACKUP" ]; then
            BACKUP_TIME=$(stat -c %Y "$LAST_BACKUP" 2>/dev/null || stat -f %m "$LAST_BACKUP" 2>/dev/null)
            CURRENT_TIME=$(date +%s)
            AGE_HOURS=$(( (CURRENT_TIME - BACKUP_TIME) / 3600 ))
            
            if [ "$AGE_HOURS" -gt "$BACKUP_AGE_HOURS" ]; then
                send_telegram "⚠️ *ALERT: Backup Overdue!*

📊 Server: \`$(hostname)\`
⏰ Last Backup: ${AGE_HOURS} hours ago
📦 Expected: Every 24 hours

🔧 *Action Required:*
• Check backup logs
• Run manual: ./bin/backup-comprehensive.sh
• Check cron: crontab -l | grep backup"
                
                ALERT_SENT=true
            fi
        else
            send_telegram "⚠️ *ALERT: No Backup Found!*

📊 Server: \`$(hostname)\`
❌ No backup files in recovery_sistem/

🔧 *Action Required:*
• Run: ./bin/backup-comprehensive.sh
• Check backup cron job"
            
            ALERT_SENT=true
        fi
    fi
}

# ============================================
# Daily Health Report (if no alerts)
# ============================================
send_daily_report() {
    # Only send if no alerts sent
    if [ "$ALERT_SENT" = false ] && [ "$1" = "daily" ]; then
        DISK_USAGE=$(df -h / | awk 'NR==2 {print $5}')
        DISK_AVAIL=$(df -h / | awk 'NR==2 {print $4}')
        MEM_PERCENT=$(free | awk '/^Mem:/ {printf "%.0f", $3/$2 * 100}')
        UPTIME=$(uptime | awk -F'up ' '{print $2}' | awk -F',' '{print $1}')
        
        # Count backups
        BACKUP_COUNT=$(find "$BACKUP_DIR" -maxdepth 1 -type f -name 'backup_*.tar.gz' 2>/dev/null | wc -l)

        # Last backup time
        LAST_BACKUP=$(ls -t "$BACKUP_DIR"/backup_*.tar.gz 2>/dev/null | head -1)
        if [ -n "$LAST_BACKUP" ]; then
            BACKUP_NAME=$(basename "$LAST_BACKUP")
            BACKUP_DATE=$(echo "$BACKUP_NAME" | grep -oP '\d{8}_\d{6}')
            BACKUP_TIME="${BACKUP_DATE:0:4}-${BACKUP_DATE:4:2}-${BACKUP_DATE:6:2} ${BACKUP_DATE:9:2}:${BACKUP_DATE:11:2}"
        else
            BACKUP_TIME="No backups"
        fi
        
        send_telegram "✅ *Daily Health Report*

📊 Server: \`$(hostname)\`
🕐 Time: $(get_timestamp)

*System Status:* 🟢 Healthy

💾 *Disk:* ${DISK_USAGE} (${DISK_AVAIL} free)
🧠 *Memory:* ${MEM_PERCENT}%
⏱️ *Uptime:* ${UPTIME}

📦 *Backups:*
• Total: ${BACKUP_COUNT}
• Latest: ${BACKUP_TIME}

✨ *All systems operational!*"
    fi
}

# ============================================
# Main Execution
# ============================================

# Run all checks
check_disk
check_memory
check_services
check_api
check_backup

# Send daily report if requested
if [ "$1" = "daily" ]; then
    send_daily_report "daily"
fi

# Exit
if [ "$ALERT_SENT" = true ]; then
    exit 1  # Alert was sent
else
    exit 0  # All OK
fi
