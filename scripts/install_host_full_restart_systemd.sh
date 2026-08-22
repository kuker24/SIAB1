#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="${1:-${SIAB1_HOME:-/opt/siab1}}"
CONTROL_DIR="${SYSTEM_FULL_RESTART_HOST_CONTROL_DIR:-${REPO_DIR}/runtime_control}"
COMPOSE_FILE="${SYSTEM_FULL_RESTART_HOST_COMPOSE_FILE:-${REPO_DIR}/docker-compose.production.yml}"
WORKER_SCRIPT="${REPO_DIR}/scripts/host_full_restart_worker.py"
SERVICE_NAME="ujian-host-full-restart"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
PATH_FILE="/etc/systemd/system/${SERVICE_NAME}.path"

mkdir -p "${CONTROL_DIR}"
chown 1000:1000 "${CONTROL_DIR}"
chmod 770 "${CONTROL_DIR}"

cat > "${SERVICE_FILE}" <<EOF
[Unit]
Description=SIAB1 Host-Controlled Full Restart Worker
After=docker.service
Requires=docker.service

[Service]
Type=oneshot
Environment=SYSTEM_FULL_RESTART_HOST_CONTROL_DIR=${CONTROL_DIR}
Environment=SYSTEM_FULL_RESTART_HOST_COMPOSE_FILE=${COMPOSE_FILE}
ExecStart=/usr/bin/python3 ${WORKER_SCRIPT}
WorkingDirectory=${REPO_DIR}
User=root
Group=root
EOF

cat > "${PATH_FILE}" <<EOF
[Unit]
Description=Watch full restart requests from API containers

[Path]
PathExists=${CONTROL_DIR}/system_full_restart.request.json
PathChanged=${CONTROL_DIR}/system_full_restart.request.json
Unit=${SERVICE_NAME}.service

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now "${SERVICE_NAME}.path"
systemctl restart "${SERVICE_NAME}.path"

echo "Installed ${SERVICE_NAME}.path"
systemctl --no-pager --full status "${SERVICE_NAME}.path" || true
