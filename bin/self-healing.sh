#!/bin/bash
# ============================================
# AUTO SELF-HEALING SYSTEM
# Detect & auto-restart failed services
# Alert if multiple failures
# ============================================

set -e

# Configuration
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
STATE_DIR="${SCRIPT_DIR}/recovery_sistem/self-healing"
MAX_RETRIES=3
RETRY_WINDOW=300  # 5 minutes in seconds

# Load telegram notification
source "${SCRIPT_DIR}/telegram-notify.sh" 2>/dev/null || true

# Detect docker compose
if command -v docker-compose &> /dev/null; then
    DC="docker-compose"
elif docker compose version &> /dev/null 2>&1; then
    DC="docker compose"
else
    DC="docker compose"
fi

cd "$SCRIPT_DIR"

# Create state directory
mkdir -p "$STATE_DIR"

# ============================================
# Function: Get service state file
# ============================================
get_state_file() {
    local service=$1
    echo "${STATE_DIR}/${service}.state"
}

# ============================================
# Function: Record restart attempt
# ============================================
record_restart() {
    local service=$1
    local state_file=$(get_state_file "$service")
    local now=$(date +%s)
    
    # Append timestamp
    echo "$now" >> "$state_file"
    
    # Clean old entries (outside 5-min window)
    local cutoff=$((now - RETRY_WINDOW))
    grep -v "^[0-9]*$" "$state_file" > "${state_file}.tmp" 2>/dev/null || true
    awk -v cutoff="$cutoff" '$1 >= cutoff' "$state_file" > "${state_file}.tmp" 2>/dev/null || true
    mv "${state_file}.tmp" "$state_file"
}

# ============================================
# Function: Get retry count in window
# ============================================
get_retry_count() {
    local service=$1
    local state_file=$(get_state_file "$service")
    
    if [ -f "$state_file" ]; then
        wc -l < "$state_file" | tr -d ' '
    else
        echo "0"
    fi
}

# ============================================
# Function: Reset state
# ============================================
reset_state() {
    local service=$1
    local state_file=$(get_state_file "$service")
    rm -f "$state_file"
}

# ============================================
# Function: Check if service is running
# ============================================
is_service_running() {
    local service=$1
    $DC -f docker-compose.production.yml ps 2>/dev/null | grep -q "$service.*Up"
}

# ============================================
# Function: Restart service
# ============================================
restart_service() {
    local service=$1
    
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Restarting ${service}..."
    
    # Record restart attempt
    record_restart "$service"
    
    # Get retry count
    local retry_count=$(get_retry_count "$service")
    
    # Actual restart
    $DC -f docker-compose.production.yml restart "$service" >> "${STATE_DIR}/restart.log" 2>&1
    
    # Wait for service to stabilize
    sleep 10
    
    # Check if restart successful
    if is_service_running "$service"; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] ✓ ${service} restarted successfully (attempt ${retry_count}/${MAX_RETRIES})"
        
        # Send success notification if this was recovery after failures
        if [ "$retry_count" -gt 1 ]; then
            send_telegram "✅ *Service Recovered!*

🔄 Service: \`${service}\`
📊 Server: \`$(hostname)\`
✓ Status: *Running*
🔢 Attempt: ${retry_count}/${MAX_RETRIES}

⏰ Time: $(get_timestamp)

🎉 *Auto-healing successful!*" 2>/dev/null || true
        fi
        
        # Reset state on success
        reset_state "$service"
        return 0
    else
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] ✗ ${service} restart failed (attempt ${retry_count}/${MAX_RETRIES})"
        
        # Check if max retries exceeded
        if [ "$retry_count" -ge "$MAX_RETRIES" ]; then
            echo "[$(date '+%Y-%m-%d %H:%M:%S')] !!! Max retries exceeded for ${service}"
            
            # Send critical alert
            send_telegram "🚨 *CRITICAL: Auto-Healing FAILED!*

❌ Service: \`${service}\`
📊 Server: \`$(hostname)\`
🔢 Retry Count: ${retry_count}/${MAX_RETRIES}
⏱️ Time Window: Last 5 minutes

⏰ Time: $(get_timestamp)

🔧 *MANUAL INTERVENTION REQUIRED:*
• Check logs: docker compose logs ${service}
• Check resources: df -h && free -h
• Manual restart: docker compose restart ${service}
• Or full rebuild: ./rebuild.sh

⚠️ *Service still DOWN after ${MAX_RETRIES} auto-restart attempts!*" 2>/dev/null || true
            
            # Reset state to prevent spam (will retry fresh after window)
            reset_state "$service"
        fi
        
        return 1
    fi
}

# ============================================
# Function: Heal service
# ============================================
heal_service() {
    local service=$1
    
    # Check if already running
    if is_service_running "$service"; then
        # Service is OK, reset any existing state
        local state_file=$(get_state_file "$service")
        if [ -f "$state_file" ]; then
            # Service recovered on its own
            reset_state "$service"
        fi
        return 0
    fi
    
    # Service is down, check retry count
    local retry_count=$(get_retry_count "$service")
    
    # If already hit max retries, don't retry immediately (wait for window to expire)
    if [ "$retry_count" -ge "$MAX_RETRIES" ]; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] ${service} already at max retries, waiting for cooldown..."
        return 1
    fi
    
    # Try to restart
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ${service} is DOWN, initiating auto-heal..."
    restart_service "$service"
}

# ============================================
# Function: Check and heal all services
# ============================================
heal_all_services() {
    local services=("api" "db" "redis" "nginx" "celery_worker" "celery_beat")
    local healed=0
    local failed=0
    
    for service in "${services[@]}"; do
        if ! is_service_running "$service"; then
            echo ""
            echo "=== Healing ${service} ==="
            
            if heal_service "$service"; then
                healed=$((healed + 1))
            else
                failed=$((failed + 1))
            fi
        fi
    done
    
    # Summary
    if [ $healed -gt 0 ] || [ $failed -gt 0 ]; then
        echo ""
        echo "=== Self-Healing Summary ==="
        echo "Healed: $healed services"
        echo "Failed: $failed services"
        echo ""
    fi
}

# ============================================
# Main Execution
# ============================================

# Check if running in Docker environment
if ! $DC -f docker-compose.production.yml ps &>/dev/null; then
    echo "Docker Compose not available or not running"
    exit 0
fi

# Run healing
heal_all_services

# Cleanup old state files (>1 hour)
find "$STATE_DIR" -name "*.state" -mmin +60 -delete 2>/dev/null || true

exit 0
