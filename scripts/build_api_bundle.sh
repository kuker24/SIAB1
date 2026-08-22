#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MODULE_DIR="$ROOT_DIR/static/js/api/modules"
OUT_FILE="$ROOT_DIR/static/js/api.js"

if [ ! -d "$MODULE_DIR" ]; then
  echo "Module directory not found: $MODULE_DIR" >&2
  exit 1
fi

{
  cat <<'HEADER'
/**
 * AUTO-GENERATED FILE.
 * Source modules: static/js/api/modules/*.js
 * Use scripts/build_api_bundle.sh after editing modules.
 */

HEADER

  for module in "$MODULE_DIR"/*.js; do
    [ -f "$module" ] || continue
    printf '/* ===== Module: %s ===== */\n\n' "$(basename "$module")"
    cat "$module"
    printf '\n'
  done
} > "$OUT_FILE"
sed -i '${/^$/d;}' "$OUT_FILE"

echo "Built $OUT_FILE from modules in $MODULE_DIR"
