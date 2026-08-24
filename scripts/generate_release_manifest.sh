#!/usr/bin/env bash
set -euo pipefail
umask 077

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
RELEASE_ID="${1:-${RELEASE_ID:-}}"
OUTPUT_DIR="${OUTPUT_DIR:-${ROOT_DIR}/releases}"

if [[ -z "$RELEASE_ID" || ! "$RELEASE_ID" =~ ^[A-Za-z0-9._+-]+$ ]]; then
  echo "ERROR: provide a release ID containing only letters, numbers, dot, underscore, plus, or dash." >&2
  exit 1
fi

mkdir -p "$OUTPUT_DIR"
MANIFEST="${OUTPUT_DIR}/release-${RELEASE_ID}.sha256"
METADATA="${OUTPUT_DIR}/release-${RELEASE_ID}.metadata"
TEMP_MANIFEST="$(mktemp)"
trap 'rm -f "$TEMP_MANIFEST"' EXIT

cd "$ROOT_DIR"
{
  printf '%s\0' docker-compose.production.yml requirements.txt
  find app bin scripts templates docker monitoring -type f \
    ! -path '*/__pycache__/*' \
    ! -path 'docker/certs/*' \
    -print0
  find static -type f \
    ! -path 'static/uploads/*' \
    ! -path 'static/apk/builds/*' \
    ! -path 'static/seb/builds/*' \
    -print0
} | sort -z -u | xargs -0 sha256sum > "$TEMP_MANIFEST"

if [[ ! -s "$TEMP_MANIFEST" ]]; then
  echo "ERROR: release manifest would be empty." >&2
  exit 1
fi

install -m 0600 "$TEMP_MANIFEST" "$MANIFEST"
cat > "$METADATA" <<EOF
release_id=${RELEASE_ID}
created_at=$(date -Iseconds)
hostname=$(hostname)
manifest_file=$(basename "$MANIFEST")
manifest_sha256=$(sha256sum "$MANIFEST" | cut -d' ' -f1)
EOF
chmod 0600 "$METADATA"

echo "Release manifest: $MANIFEST"
echo "Release metadata: $METADATA"
echo "Verify with: (cd $ROOT_DIR && sha256sum --check $MANIFEST)"
