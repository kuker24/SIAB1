#!/bin/bash
# ============================================
# TELEGRAM NOTIFICATION HELPER
# Send alerts to Telegram
# ============================================

# Configuration is read from environment to avoid committing secrets.
# Required:
#   TELEGRAM_BOT_TOKEN="..."
#   TELEGRAM_CHAT_IDS="12345,-10012345"
TELEGRAM_TOKEN="${TELEGRAM_BOT_TOKEN:-}"
IFS=',' read -r -a TELEGRAM_CHAT_IDS <<< "${TELEGRAM_CHAT_IDS:-}"

# Function to send message
send_telegram() {
    local message="$1"
    local parse_mode="${2:-Markdown}"
    local success=0

    if [ -z "${TELEGRAM_TOKEN}" ] || [ ${#TELEGRAM_CHAT_IDS[@]} -eq 0 ]; then
        echo "Telegram notification skipped: TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_IDS not configured" >&2
        return 0
    fi

    # Send to all recipients
    for chat_id in "${TELEGRAM_CHAT_IDS[@]}"; do
        if [ -z "${chat_id}" ]; then
            continue
        fi
        curl -s -X POST "https://api.telegram.org/bot${TELEGRAM_TOKEN}/sendMessage" \
            -d chat_id="${chat_id}" \
            -d text="${message}" \
            -d parse_mode="${parse_mode}" > /dev/null 2>&1
        
        if [ $? -eq 0 ]; then
            success=$((success + 1))
        fi
    done
    
    # Return success if at least one succeeded
    if [ $success -gt 0 ]; then
        return 0
    else
        echo "Failed to send Telegram notification to all recipients" >&2
        return 1
    fi
}

# Function to get current timestamp in WIB (UTC+7)
get_timestamp() {
    # Get current time in UTC+7 (WIB/Jakarta timezone)
    TZ='Asia/Jakarta' date '+%Y-%m-%d %H:%M:%S'
}

# If called directly with message
if [ $# -gt 0 ]; then
    send_telegram "$1"
fi
