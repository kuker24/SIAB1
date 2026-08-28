#!/usr/bin/env bash
set -euo pipefail
umask 077

SCRIPT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ROOT_DIR="${SOURCE_RELEASE_ROOT:-$SCRIPT_ROOT}"
if [[ "${BASH_SOURCE[0]}" == "$0" && -n "${1:-}" ]]; then
  ROOT_DIR="$(cd "$1" && pwd)"
fi

source_release_excluded() {
  case "$1" in
    docker/certs/*|static/uploads/*|static/apk/builds/*|static/seb/builds/*)
      return 0
      ;;
    */__pycache__/*|*.pyc|*/.pytest_cache/*|*/node_modules/*|*/.dart_tool/*)
      return 0
      ;;
    *.bak|*.bak-*|*.bak_*|*.pre-*|*.backup|*.log|*.tmp|*.temp)
      return 0
      ;;
  esac
  return 1
}

list_source_release_files() {
  {
    for path in \
      docker-compose.production.yml \
      requirements.txt \
      requirements.runtime.txt \
      requirements.runtime.lock \
      ARCHITECTURE.md
    do
      if [[ -f "$path" ]]; then
        printf '%s\0' "$path"
      fi
    done
    for dir in app bin scripts templates docker monitoring static go; do
      if [[ -d "$dir" ]]; then
        find "$dir" -type f -print0
      fi
    done
  } | sort -z -u | while IFS= read -r -d '' path; do
    if source_release_excluded "$path"; then
      continue
    fi
    printf '%s\0' "$path"
  done
}

if [[ "${BASH_SOURCE[0]}" != "$0" ]]; then
  return 0
fi

cd "$ROOT_DIR"
export LC_ALL=C
TEMP_LISTING="$(mktemp)"
trap 'rm -f "$TEMP_LISTING"' EXIT

if ! list_source_release_files | xargs -0 -r sha256sum > "$TEMP_LISTING"; then
  echo "ERROR: failed to hash source release files." >&2
  exit 1
fi

if [[ ! -s "$TEMP_LISTING" ]]; then
  echo "ERROR: source release fingerprint would be empty." >&2
  exit 1
fi

if [[ -n "${SOURCE_FINGERPRINT_OUT:-}" ]]; then
  install -m 0600 "$TEMP_LISTING" "$SOURCE_FINGERPRINT_OUT"
fi

cat "$TEMP_LISTING"
