#!/bin/bash
# =============================================================================
# Sync Script - Passwordless Version (matches sync.bat)
# Usage: ./sync-nopass.sh
# =============================================================================

echo "========================================"
echo " SYNC TO UBUNTU SERVER (Passwordless)"
echo "========================================"
echo ""

# Configuration
SSH_PORT=2222
SSH_USER="fahmi"
SSH_HOST="127.0.0.1"
REMOTE_PATH="~/ujian_online"
KEY_PATH="$HOME/.ssh/id_rsa_ujian"

# Check if SSH key exists
if [ ! -f "${KEY_PATH}" ]; then
    echo "❌ SSH key not found!"
    echo ""
    echo "Please run setup first:"
    echo "  ./setup-ssh-key.sh"
    echo ""
    exit 1
fi

echo "📦 Syncing files to ${SSH_USER}@${SSH_HOST}:${REMOTE_PATH}..."
echo ""

# Sync app directory
echo "[1/7] Syncing app folder..."
scp -P ${SSH_PORT} -i ${KEY_PATH} -o StrictHostKeyChecking=no -r app ${SSH_USER}@${SSH_HOST}:${REMOTE_PATH}/

# Sync static directory  
echo "[2/7] Syncing static folder..."
scp -P ${SSH_PORT} -i ${KEY_PATH} -o StrictHostKeyChecking=no -r static ${SSH_USER}@${SSH_HOST}:${REMOTE_PATH}/

# Sync templates directory
echo "[3/7] Syncing templates folder..."
scp -P ${SSH_PORT} -i ${KEY_PATH} -o StrictHostKeyChecking=no -r templates ${SSH_USER}@${SSH_HOST}:${REMOTE_PATH}/

# Sync flutter_client_code (excluding build folder to save time)
echo "[4/7] Syncing flutter_client_code (source only)..."
scp -P ${SSH_PORT} -i ${KEY_PATH} -o StrictHostKeyChecking=no -r flutter_client_code/lib ${SSH_USER}@${SSH_HOST}:${REMOTE_PATH}/flutter_client_code/ 2>/dev/null || echo "  (flutter lib skipped)"
scp -P ${SSH_PORT} -i ${KEY_PATH} -o StrictHostKeyChecking=no -r flutter_client_code/android ${SSH_USER}@${SSH_HOST}:${REMOTE_PATH}/flutter_client_code/ 2>/dev/null || echo "  (flutter android skipped)"
scp -P ${SSH_PORT} -i ${KEY_PATH} -o StrictHostKeyChecking=no flutter_client_code/pubspec.yaml ${SSH_USER}@${SSH_HOST}:${REMOTE_PATH}/flutter_client_code/ 2>/dev/null || echo "  (pubspec.yaml skipped)"

# Sync tools (APK builder GUI)
echo "[5/7] Syncing tools folder..."
scp -P ${SSH_PORT} -i ${KEY_PATH} -o StrictHostKeyChecking=no -r tools ${SSH_USER}@${SSH_HOST}:${REMOTE_PATH}/ 2>/dev/null || echo "  (tools folder skipped)"

# Sync shell scripts (diagnostic, deployment, backup, monitoring)
echo "[6/7] Syncing shell scripts..."
scp -P ${SSH_PORT} -i ${KEY_PATH} -o StrictHostKeyChecking=no deteksi_masalah.sh ${SSH_USER}@${SSH_HOST}:${REMOTE_PATH}/ 2>/dev/null || true
scp -P ${SSH_PORT} -i ${KEY_PATH} -o StrictHostKeyChecking=no deploy.sh ${SSH_USER}@${SSH_HOST}:${REMOTE_PATH}/
scp -P ${SSH_PORT} -i ${KEY_PATH} -o StrictHostKeyChecking=no rebuild.sh ${SSH_USER}@${SSH_HOST}:${REMOTE_PATH}/ 2>/dev/null || true
scp -P ${SSH_PORT} -i ${KEY_PATH} -o StrictHostKeyChecking=no backup-database.sh ${SSH_USER}@${SSH_HOST}:${REMOTE_PATH}/ 2>/dev/null || true
scp -P ${SSH_PORT} -i ${KEY_PATH} -o StrictHostKeyChecking=no backup-comprehensive.sh ${SSH_USER}@${SSH_HOST}:${REMOTE_PATH}/ 2>/dev/null || true
scp -P ${SSH_PORT} -i ${KEY_PATH} -o StrictHostKeyChecking=no monitor.sh ${SSH_USER}@${SSH_HOST}:${REMOTE_PATH}/ 2>/dev/null || true

# Sync configuration files
echo "[7/7] Syncing configuration files..."
scp -P ${SSH_PORT} -i ${KEY_PATH} -o StrictHostKeyChecking=no docker-compose.production.yml ${SSH_USER}@${SSH_HOST}:${REMOTE_PATH}/
scp -P ${SSH_PORT} -i ${KEY_PATH} -o StrictHostKeyChecking=no nginx.production.conf ${SSH_USER}@${SSH_HOST}:${REMOTE_PATH}/
scp -P ${SSH_PORT} -i ${KEY_PATH} -o StrictHostKeyChecking=no init.sql ${SSH_USER}@${SSH_HOST}:${REMOTE_PATH}/

echo ""
echo "========================================"
echo " SYNC COMPLETE!"
echo "========================================"
echo ""
echo "Next: SSH to server and restart if needed:"
echo ""
echo "  ssh -p ${SSH_PORT} -i ${KEY_PATH} ${SSH_USER}@${SSH_HOST} \"cd ${REMOTE_PATH} && docker compose -f docker-compose.production.yml restart\""
echo ""
