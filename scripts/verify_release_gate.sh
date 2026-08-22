#!/usr/bin/env bash
set -euo pipefail

PYTHON_BIN="${PYTHON_BIN:-./.venv/bin/python}"
SKIP_HTTP="${SKIP_HTTP:-0}"
BASE_URL="${BASE_URL:-http://127.0.0.1}"
STRICT_HOST_HARDENING="${STRICT_HOST_HARDENING:-0}"
SKIP_OUTDATED_SECURITY_AUDIT="${SKIP_OUTDATED_SECURITY_AUDIT:-0}"

if [[ ! -x "$PYTHON_BIN" ]]; then
  PYTHON_BIN="python3"
fi

echo "=== Release Gate Validation ==="
echo "Python: $PYTHON_BIN"

echo "[1/3] Full regression tests"
"$PYTHON_BIN" -m pytest -q tests

echo "[2/3] Security dependency audit"
SECURITY_SKIP_OUTDATED_CHECK=0
if [[ "$SKIP_OUTDATED_SECURITY_AUDIT" == "1" ]]; then
  SECURITY_SKIP_OUTDATED_CHECK=1
  echo "      mode: outdated check disabled (SECURITY_SKIP_OUTDATED_CHECK=1)"
fi
if [[ "$STRICT_HOST_HARDENING" == "1" ]]; then
  echo "      mode: strict host hardening (SECURITY_FAIL_ON_TELNET_CLIENT=1)"
  SECURITY_FAIL_ON_TELNET_CLIENT=1 SECURITY_SKIP_OUTDATED_CHECK="$SECURITY_SKIP_OUTDATED_CHECK" \
    "$PYTHON_BIN" scripts/check_security.py
else
  SECURITY_SKIP_OUTDATED_CHECK="$SECURITY_SKIP_OUTDATED_CHECK" "$PYTHON_BIN" scripts/check_security.py
fi

if [[ "$SKIP_HTTP" == "1" ]]; then
  echo "[3/3] HTTP critical path smoke skipped (SKIP_HTTP=1)"
else
  echo "[3/3] HTTP critical path smoke"
  BASE_URL="$BASE_URL" bash scripts/verify_critical_http_paths.sh
fi

echo "=== Release Gate PASS ==="
