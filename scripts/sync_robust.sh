#!/bin/bash
# =============================================================================
# ENTERPRISE SYNC SCRIPT (RSYNC)
# Robust, resumable, and configuration-driven synchronization
# =============================================================================

# Load configuration from .env if available
if [ -f .env ]; then
    export $(grep -v '^#' .env | xargs)
fi

# Defaults (Override these in .env)
SYNC_TARGET_USER=${SYNC_TARGET_USER:-"root"}
SYNC_TARGET_HOST=${SYNC_TARGET_HOST:-"ujian-vps"}
SYNC_TARGET_PORT=${SYNC_TARGET_PORT:-22}
SYNC_TARGET_PATH=${SYNC_TARGET_PATH:-"~/ujian_online"}
SSH_KEY_PATH=${SSH_KEY_PATH:-"$HOME/.ssh/id_ed25519"}

SYNC_TARGET="${SYNC_TARGET_USER}@${SYNC_TARGET_HOST}"
if [ "${SYNC_TARGET_HOST}" = "ujian-vps" ]; then
    # Use SSH alias directly to avoid user@alias parsing quirks on some clients.
    SYNC_TARGET="${SYNC_TARGET_HOST}"
fi

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}🚀 Starting Enterprise Sync...${NC}"
echo -e "Target: ${YELLOW}${SYNC_TARGET}:${SYNC_TARGET_PORT}${NC}"
echo -e "Path:   ${YELLOW}${SYNC_TARGET_PATH}${NC}"
echo ""

# 1. Check SSH Connection
echo -e "[1/4] Checking connectivity..."
if ssh -q -p $SYNC_TARGET_PORT -i "$SSH_KEY_PATH" -o ConnectTimeout=5 "$SYNC_TARGET" exit; then
    echo -e "${GREEN}✓ Connection OK${NC}"
else
    echo -e "${RED}✗ Cannot connect to server. Check IP, Port, and SSH Key.${NC}"
    exit 1
fi

# 2. Perform RSYNC (Dry Run first? No, we do it live but carefully)
echo -e "[2/4] Syncing files (RSYNC)..."

# Common excludes
EXCLUDES=(
    "--exclude=.env"
    "--exclude=.git/"
    "--exclude=__pycache__/"
    "--exclude=*.pyc"
    "--exclude=node_modules/"
    "--exclude=venv/"
    "--exclude=.venv/"
    "--exclude=db_data/"
    "--exclude=redis_data/"
    "--exclude=grafana_data/"
    "--exclude=apk_builds/"
    "--exclude=recovery_sistem/"
)

# Run Rsync
rsync -avz --progress -e "ssh -p $SYNC_TARGET_PORT -i $SSH_KEY_PATH -o StrictHostKeyChecking=no" \
    "${EXCLUDES[@]}" \
    ./ \
    "${SYNC_TARGET}:${SYNC_TARGET_PATH}/"

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ Files synchronized successfully.${NC}"
else
    echo -e "${RED}✗ Sync failed.${NC}"
    exit 1
fi

# 3. Post-Sync Actions
echo -e "[3/4] Fixing permissions on remote..."
ssh -p $SYNC_TARGET_PORT -i "$SSH_KEY_PATH" "${SYNC_TARGET}" \
    "chmod +x ${SYNC_TARGET_PATH}/*.sh ${SYNC_TARGET_PATH}/scripts/*.sh"

# 4. Restart Services (Optional)
read -p "Do you want to restart Docker services on remote? (y/n) " -n 1 -r
echo ""
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo -e "[4/4] Restarting remote services..."
    ssh -p $SYNC_TARGET_PORT -i "$SSH_KEY_PATH" "${SYNC_TARGET}" \
        "cd ${SYNC_TARGET_PATH} && docker compose -f docker-compose.production.yml restart"
    echo -e "${GREEN}✓ Services restarted.${NC}"
fi

echo ""
echo -e "${GREEN}✅ Synchronization Complete!${NC}"
