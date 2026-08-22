#!/usr/bin/env bash
set -euo pipefail

# Safe repository cleanup helper for refactor cycles.
# Removes only non-source artifacts by default.

MODE="${1:-dry-run}"

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

TARGET_DIRS=(
  ".pytest_cache"
  ".mypy_cache"
  ".ruff_cache"
)

echo "[repo-clean] mode: ${MODE}"
echo "[repo-clean] root: ${ROOT_DIR}"

for d in "${TARGET_DIRS[@]}"; do
  if [[ -d "$d" ]]; then
    if [[ "$MODE" == "apply" ]]; then
      rm -rf "$d"
      echo "removed dir: $d"
    else
      echo "would remove dir: $d"
    fi
  fi
done

PY_CACHE_COUNT="$(find app scripts tests templates static -type d -name '__pycache__' 2>/dev/null | wc -l | tr -d ' ')"
PYC_COUNT="$(find app scripts tests templates static -type f \( -name '*.pyc' -o -name '*.pyo' \) 2>/dev/null | wc -l | tr -d ' ')"

if [[ "$MODE" == "apply" ]]; then
  find app scripts tests templates static -type d -name '__pycache__' -prune -exec rm -rf {} +
  find app scripts tests templates static -type f \( -name '*.pyc' -o -name '*.pyo' \) -delete
  echo "removed __pycache__ dirs: ${PY_CACHE_COUNT}"
  echo "removed bytecode files: ${PYC_COUNT}"
else
  echo "would remove __pycache__ dirs: ${PY_CACHE_COUNT}"
  echo "would remove bytecode files: ${PYC_COUNT}"
fi

echo "[repo-clean] done"
