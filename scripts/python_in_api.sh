#!/usr/bin/env bash
set -euo pipefail

CONTAINER_NAME="${PYTHON_IN_API_CONTAINER:-siab1-api-1}"

if ! command -v docker >/dev/null 2>&1; then
  echo "docker command not found" >&2
  exit 1
fi

ENV_FORWARD_VARS=(
  "SECURITY_FAIL_ON_TELNET_CLIENT"
  "SECURITY_SKIP_OUTDATED_CHECK"
  "SECURITY_ACCEPTLIST_FILE"
)

DOCKER_ENV_ARGS=()
for var_name in "${ENV_FORWARD_VARS[@]}"; do
  value="${!var_name:-}"
  if [[ -n "$value" ]]; then
    DOCKER_ENV_ARGS+=("-e" "${var_name}=${value}")
  fi
done

exec docker exec -i "${DOCKER_ENV_ARGS[@]}" "$CONTAINER_NAME" python "$@"
