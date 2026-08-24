#!/usr/bin/env bash
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "ERROR: run this script as root." >&2
  exit 1
fi

REPO_DIR="${1:-${SIAB1_HOME:-/opt/siab1}}"
APP_UID="${APP_UID:-1000}"
OPERATOR_GID="${OPERATOR_GID:-$(stat -c %g "$REPO_DIR")}"
RUNTIME_DIRS=(
  uploads
  logs
  seb_configs
  apk_builds
  static/uploads
  static/apk/builds
  static/seb/builds
)

for relative_path in "${RUNTIME_DIRS[@]}"; do
  path="${REPO_DIR}/${relative_path}"
  install -d -o "$APP_UID" -g "$OPERATOR_GID" -m 2775 "$path"
  chown -R "$APP_UID:$OPERATOR_GID" "$path"
  find "$path" -type d -exec chmod u+rwx,g+rwx,o+rx,g+s {} +
done

install -d -o "$APP_UID" -g "$OPERATOR_GID" -m 2770 "${REPO_DIR}/runtime_control"

echo "Runtime directories prepared for app UID ${APP_UID} and operator GID ${OPERATOR_GID}."
