#!/usr/bin/env bash
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "ERROR: run this installer as root." >&2
  exit 1
fi

REPO_DIR="${1:-${SIAB1_HOME:-/opt/siab1}}"
BACKUP_ROOT="${BACKUP_ROOT:-${REPO_DIR}/recovery_sistem}"
BACKUP_TIME="${BACKUP_TIME:-01:30}"
DRILL_TIME="${DRILL_TIME:-Sun *-*-* 03:40:00}"
BACKUP_SCRIPT="${REPO_DIR}/bin/backup-comprehensive.sh"
DRILL_SCRIPT="${REPO_DIR}/scripts/drill_disaster_recovery.sh"
SYSTEMD_DIR="/etc/systemd/system"

for required_file in "$BACKUP_SCRIPT" "$DRILL_SCRIPT" "${REPO_DIR}/docker-compose.production.yml"; do
  if [[ ! -f "$required_file" ]]; then
    echo "ERROR: required file not found: $required_file" >&2
    exit 1
  fi
done

install -d -m 0700 "$BACKUP_ROOT" "$BACKUP_ROOT/dr_drill"

cat > "${SYSTEMD_DIR}/siab1-backup.service" <<EOF
[Unit]
Description=SIAB1 comprehensive production backup
After=docker.service
Requires=docker.service

[Service]
Type=oneshot
WorkingDirectory=${REPO_DIR}
Environment=BACKUP_ROOT=${BACKUP_ROOT}
Environment=KEEP_DAYS=30
ExecStart=/bin/bash ${BACKUP_SCRIPT}
User=root
Group=root
UMask=0077
Nice=10
IOSchedulingClass=idle
EOF

cat > "${SYSTEMD_DIR}/siab1-backup.timer" <<EOF
[Unit]
Description=Run SIAB1 backup daily

[Timer]
OnCalendar=*-*-* ${BACKUP_TIME}:00
Persistent=true
RandomizedDelaySec=10m
Unit=siab1-backup.service

[Install]
WantedBy=timers.target
EOF

cat > "${SYSTEMD_DIR}/siab1-restore-drill.service" <<EOF
[Unit]
Description=Verify latest SIAB1 backup with a non-destructive restore drill
After=docker.service
Requires=docker.service

[Service]
Type=oneshot
WorkingDirectory=${REPO_DIR}
Environment=BACKUP_ROOT=${BACKUP_ROOT}
ExecStart=/bin/bash ${DRILL_SCRIPT}
User=root
Group=root
UMask=0077
Nice=15
IOSchedulingClass=idle
EOF

cat > "${SYSTEMD_DIR}/siab1-restore-drill.timer" <<EOF
[Unit]
Description=Run SIAB1 restore drill weekly

[Timer]
OnCalendar=${DRILL_TIME}
Persistent=true
RandomizedDelaySec=20m
Unit=siab1-restore-drill.service

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemctl enable --now siab1-backup.timer siab1-restore-drill.timer
systemctl list-timers --all --no-pager siab1-backup.timer siab1-restore-drill.timer
