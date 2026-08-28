#!/usr/bin/env bash
set -euo pipefail
umask 077

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
RELEASE_ID="${1:-${RELEASE_ID:-}}"
OUTPUT_DIR="${OUTPUT_DIR:-${ROOT_DIR}/releases}"
RELEASE_MODE="${RELEASE_MODE:-full}"
FINGERPRINT_SCRIPT="${ROOT_DIR}/scripts/source_release_fingerprint.sh"

if [[ -z "$RELEASE_ID" || ! "$RELEASE_ID" =~ ^[A-Za-z0-9._+-]+$ ]]; then
  echo "ERROR: provide a release ID containing only letters, numbers, dot, underscore, plus, or dash." >&2
  exit 1
fi

if [[ "$RELEASE_MODE" != "full" && "$RELEASE_MODE" != "delta" ]]; then
  echo "ERROR: RELEASE_MODE must be full or delta." >&2
  exit 1
fi

mkdir -p "$OUTPUT_DIR"
MANIFEST="${OUTPUT_DIR}/release-${RELEASE_ID}.sha256"
METADATA="${OUTPUT_DIR}/release-${RELEASE_ID}.metadata"
SOURCE_LISTING="${OUTPUT_DIR}/release-${RELEASE_ID}.source-tree.sha256"
TEMP_MANIFEST="$(mktemp)"
TEMP_SOURCE="$(mktemp)"
trap 'rm -f "$TEMP_MANIFEST" "$TEMP_SOURCE"' EXIT

cd "$ROOT_DIR"
export LC_ALL=C

# shellcheck disable=SC1090
source "$FINGERPRINT_SCRIPT"

SOURCE_FINGERPRINT_OUT="$TEMP_SOURCE" bash "$FINGERPRINT_SCRIPT" "$ROOT_DIR" >/dev/null
install -m 0600 "$TEMP_SOURCE" "$SOURCE_LISTING"
SOURCE_TREE_FINGERPRINT="$(sha256sum "$SOURCE_LISTING" | cut -d' ' -f1)"

if [[ "$RELEASE_MODE" == "full" ]]; then
  cp "$TEMP_SOURCE" "$TEMP_MANIFEST"
else
  if [[ -z "${DEPLOYED_PATHS_FILE:-}" || ! -f "$DEPLOYED_PATHS_FILE" ]]; then
    echo "ERROR: delta releases require DEPLOYED_PATHS_FILE." >&2
    exit 1
  fi
  DELTA_LIST="$(mktemp)"
  trap 'rm -f "$TEMP_MANIFEST" "$TEMP_SOURCE" "$DELTA_LIST"' EXIT
  while IFS= read -r path || [[ -n "$path" ]]; do
    [[ -z "$path" ]] && continue
    if source_release_excluded "$path"; then
      echo "ERROR: delta path is excluded from source identity: $path" >&2
      exit 1
    fi
    if [[ ! -f "$path" ]]; then
      echo "ERROR: delta path does not exist: $path" >&2
      exit 1
    fi
    printf '%s\0' "$path"
  done < "$DEPLOYED_PATHS_FILE" | sort -z -u > "$DELTA_LIST"
  if [[ ! -s "$DELTA_LIST" ]]; then
    echo "ERROR: delta release listing would be empty." >&2
    exit 1
  fi
  xargs -0 -r sha256sum < "$DELTA_LIST" > "$TEMP_MANIFEST"
fi

if [[ ! -s "$TEMP_MANIFEST" ]]; then
  echo "ERROR: release manifest would be empty." >&2
  exit 1
fi

install -m 0600 "$TEMP_MANIFEST" "$MANIFEST"

if [[ -d "${ROOT_DIR}/.git" ]]; then
  SOURCE_GIT_SHA="${SOURCE_GIT_SHA:-$(git -C "$ROOT_DIR" rev-parse HEAD)}"
  SOURCE_BRANCH="${SOURCE_BRANCH:-$(git -C "$ROOT_DIR" branch --show-current 2>/dev/null || true)}"
fi
SOURCE_GIT_SHA="${SOURCE_GIT_SHA:-unknown}"
SOURCE_BRANCH="${SOURCE_BRANCH:-}"

COMPOSE_IDENTITY="missing"
if [[ -f docker-compose.production.yml ]]; then
  COMPOSE_IDENTITY="$(sha256sum docker-compose.production.yml | cut -d' ' -f1)"
fi
NGINX_IDENTITY="missing"
if [[ -f docker/nginx.production.conf ]]; then
  NGINX_IDENTITY="$(sha256sum docker/nginx.production.conf | cut -d' ' -f1)"
fi

RUNTIME_TREE_FINGERPRINT=""
if [[ -n "${RUNTIME_ROOT:-}" ]]; then
  RUNTIME_TREE_FINGERPRINT="$(
    SOURCE_FINGERPRINT_OUT="" bash "$FINGERPRINT_SCRIPT" "$RUNTIME_ROOT" | sha256sum | cut -d' ' -f1
  )"
fi

PREVIOUS_RELEASE_ID="${PREVIOUS_RELEASE_ID:-}"
PREVIOUS_SOURCE_SHA="${PREVIOUS_SOURCE_SHA:-}"
ROLLBACK_REFERENCE="${ROLLBACK_REFERENCE:-${PREVIOUS_RELEASE_ID}}"
BACKUP_PATH="${BACKUP_PATH:-}"
BACKUP_SHA256="${BACKUP_SHA256:-}"
DEPLOYMENT_DESTINATION="${DEPLOYMENT_DESTINATION:-}"
RUNTIME_IMAGE_IDS="${RUNTIME_IMAGE_IDS:-}"
RUNTIME_IMAGE_REVISIONS="${RUNTIME_IMAGE_REVISIONS:-}"
EXCLUDED_PATTERNS="docker/certs/* static/uploads/* static/apk/builds/* static/seb/builds/* runtime_control/ .env* logs/ uploads/ recovery_sistem/ releases/ *.bak *.bak-* *.bak_* *.pre-* __pycache__/ .pytest_cache/ node_modules/"

cat > "$METADATA" <<EOF
release_id=${RELEASE_ID}
source_git_sha=${SOURCE_GIT_SHA}
source_branch=${SOURCE_BRANCH}
release_mode=${RELEASE_MODE}
deployment_timestamp=$(date -Iseconds)
deployment_destination=${DEPLOYMENT_DESTINATION}
previous_release_id=${PREVIOUS_RELEASE_ID}
previous_source_sha=${PREVIOUS_SOURCE_SHA}
backup_path=${BACKUP_PATH}
backup_sha256=${BACKUP_SHA256}
source_tree_fingerprint=${SOURCE_TREE_FINGERPRINT}
runtime_tree_fingerprint=${RUNTIME_TREE_FINGERPRINT}
deployed_files_manifest=$(basename "$MANIFEST")
manifest_file=$(basename "$MANIFEST")
manifest_sha256=$(sha256sum "$MANIFEST" | cut -d' ' -f1)
compose_file_identity=${COMPOSE_IDENTITY}
nginx_config_identity=${NGINX_IDENTITY}
runtime_image_ids=${RUNTIME_IMAGE_IDS}
runtime_image_revisions=${RUNTIME_IMAGE_REVISIONS}
rollback_reference=${ROLLBACK_REFERENCE}
excluded_operational_patterns=${EXCLUDED_PATTERNS}
identity_note=source_release_identity_is_not_runtime_filesystem_identity
hostname=$(hostname)
EOF
chmod 0600 "$METADATA"

echo "Release manifest: $MANIFEST"
echo "Release metadata: $METADATA"
echo "Source tree listing: $SOURCE_LISTING"
echo "Verify with: (cd $ROOT_DIR && sha256sum --check $MANIFEST)"
