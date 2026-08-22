#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://127.0.0.1}"
CURL_TIMEOUT="${CURL_TIMEOUT:-12}"

PASS_COUNT=0
FAIL_COUNT=0

check_endpoint() {
  local method="$1"
  local path="$2"
  local allowed_regex="$3"
  local body="${4:-}"

  local url="${BASE_URL%/}${path}"
  local status

  if [[ -n "$body" ]]; then
    status="$(curl -sS -m "$CURL_TIMEOUT" -o /tmp/critical_http_body.$$ -w '%{http_code}' \
      -X "$method" \
      -H 'Content-Type: application/json' \
      --data "$body" \
      "$url")"
  else
    status="$(curl -sS -m "$CURL_TIMEOUT" -o /tmp/critical_http_body.$$ -w '%{http_code}' \
      -X "$method" \
      "$url")"
  fi

  if [[ "$status" =~ $allowed_regex ]]; then
    echo "[PASS] $method $path -> $status"
    PASS_COUNT=$((PASS_COUNT + 1))
  else
    echo "[FAIL] $method $path -> $status (allowed: $allowed_regex)" >&2
    FAIL_COUNT=$((FAIL_COUNT + 1))
  fi
}

echo "=== Critical HTTP Path Regression ==="
echo "Base URL: $BASE_URL"

# Health + root
check_endpoint "GET" "/health" '^(200)$'
check_endpoint "GET" "/" '^(200)$'

# Auth/login path (allow validation/auth statuses; fail on 5xx/404)
check_endpoint "POST" "/api/auth/login" '^(200|400|401|422)$' '{"username":"invalid","password":"invalid"}'

# Exam critical flow endpoints (start/autosave/submit path should exist, may be unauthorized/validation)
check_endpoint "GET" "/api/exams/list" '^(200|401|403)$'
check_endpoint "POST" "/api/exams/submit-answer" '^(200|400|401|403|405|422)$' '{}'
check_endpoint "POST" "/api/exams/submit" '^(200|400|401|403|405|422)$' '{}'

# Grading + monitoring paths required during exam operations
check_endpoint "GET" "/api/grading/stats" '^(200|401|403)$'
check_endpoint "GET" "/api/monitoring/active-exams" '^(200|401|403)$'
check_endpoint "GET" "/api/monitoring/system/ops-summary" '^(200|401|403)$'

rm -f /tmp/critical_http_body.$$

echo "---"
echo "Passed: $PASS_COUNT"
echo "Failed: $FAIL_COUNT"

if [[ "$FAIL_COUNT" -gt 0 ]]; then
  exit 1
fi
