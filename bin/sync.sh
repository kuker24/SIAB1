#!/bin/bash
# =============================================================================
# Sync Script - Transfer code changes to Ubuntu server
# IMPROVED: Uses sshpass for single password entry
# Usage: ./sync.sh (from Git Bash/WSL)
# =============================================================================

echo "🚀 Starting sync to Ubuntu server..."
echo ""

# Configuration
SSH_PORT=2222
SSH_USER="fahmi"
SSH_HOST="127.0.0.1"
REMOTE_PATH="~/ujian_online/"
LOCAL_PATH="/mnt/c/Users/Administrator/Documents/UJIAN/Beta v3/ujian_online/"

# Check if sshpass is installed
if ! command -v sshpass &> /dev/null; then
    echo "⚠️  Installing sshpass for password caching..."
    echo ""
    
    # Install sshpass (works for WSL Ubuntu)
    if command -v apt-get &> /dev/null; then
        sudo apt-get update -qq && sudo apt-get install -y sshpass
    elif command -v yum &> /dev/null; then
        sudo yum install -y sshpass
    else
        echo "❌ Cannot install sshpass automatically."
        echo "Please install it manually: sudo apt-get install sshpass"
        exit 1
    fi
fi

# Prompt for password ONCE
echo "🔐 Please enter SSH password for ${SSH_USER}@${SSH_HOST}:"
read -s SSH_PASSWORD
echo ""

# Export password for sshpass
export SSHPASS="$SSH_PASSWORD"

echo "📦 Syncing files to server..."
echo ""

# Sync files with rsync using sshpass
sshpass -e rsync -avz --progress -e "ssh -p ${SSH_PORT} -o StrictHostKeyChecking=no" \
  --exclude='.env' \
  --exclude='uploads/' \
  --exclude='logs/' \
  --exclude='__pycache__/' \
  --exclude='*.pyc' \
  --exclude='.git/' \
  --exclude='node_modules/' \
  --exclude='.pytest_cache/' \
  --exclude='*.egg-info/' \
  --exclude='.venv/' \
  --exclude='venv/' \
  "${LOCAL_PATH}" \
  "${SSH_USER}@${SSH_HOST}:${REMOTE_PATH}"

# Check if sync was successful
if [ $? -eq 0 ]; then
    echo ""
    echo "✅ Sync complete!"
    echo ""
    echo "🔄 Restarting services on server..."
    
    # Auto-restart services using same password
    sshpass -e ssh -p ${SSH_PORT} -o StrictHostKeyChecking=no ${SSH_USER}@${SSH_HOST} \
        "cd ~/ujian_online && docker compose -f docker-compose.production.yml restart"
    
    echo ""
    echo "✅ All done! Server restarted successfully."
    echo ""
else
    echo ""
    echo "❌ Sync failed! Check your connection and try again."
    exit 1
fi

# Clear password from environment
unset SSHPASS
