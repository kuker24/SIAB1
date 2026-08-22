#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MODULE_DIR="$ROOT_DIR/static/js/exam"
OUT_FILE="$ROOT_DIR/static/js/exam-system.js"

if [ ! -d "$MODULE_DIR" ]; then
  echo "Module directory not found: $MODULE_DIR" >&2
  exit 1
fi

ORDER=(
  core.js
  bridge.js
  autosave.js
  security.js
  reconnect.js
  timer.js
  navigation.js
)

{
  cat <<'HEADER'
/**
 * AUTO-GENERATED FILE.
 * Source modules: static/js/exam/*.js
 * Use scripts/build_exam_system_bundle.sh after editing modules.
 */

HEADER

  for name in "${ORDER[@]}"; do
    module="$MODULE_DIR/$name"
    if [ ! -f "$module" ]; then
      echo "Missing module: $module" >&2
      exit 1
    fi
    printf '/* ===== Module: %s ===== */\n\n' "$name"
    cat "$module"
    printf '\n'
  done
} > "$OUT_FILE"
sed -i '${/^$/d;}' "$OUT_FILE"

echo "Built $OUT_FILE from modules in $MODULE_DIR"
