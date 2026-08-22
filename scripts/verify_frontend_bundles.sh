#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

REGISTRY_FILE="$ROOT_DIR/scripts/frontend_bundle_registry.csv"
if [[ ! -f "$REGISTRY_FILE" ]]; then
  echo "Bundle registry not found: $REGISTRY_FILE" >&2
  exit 1
fi

if command -v flock >/dev/null 2>&1; then
  lock_file="${TMPDIR:-/tmp}/verify_frontend_bundles.lock"
  exec 9>"$lock_file"
  flock -x 9
fi

declare -A before_hashes=()
declare -A seen_build_scripts=()
declare -a bundle_paths=()
declare -a build_scripts=()

while IFS='|' read -r bundle_path module_glob build_script; do
  bundle_path="${bundle_path%%$'\r'}"
  module_glob="${module_glob%%$'\r'}"
  build_script="${build_script%%$'\r'}"

  if [[ -z "${bundle_path}" || "${bundle_path}" == \#* ]]; then
    continue
  fi

  if [[ ! -f "$bundle_path" ]]; then
    echo "Bundle file from registry not found: $bundle_path" >&2
    exit 1
  fi
  if [[ ! -x "$build_script" ]]; then
    echo "Build script from registry is missing or not executable: $build_script" >&2
    exit 1
  fi
  if [[ "$module_glob" != *"*.js" ]]; then
    echo "Invalid module glob in registry (must end with *.js): $module_glob" >&2
    exit 1
  fi

  before_hashes["$bundle_path"]="$(sha256sum "$bundle_path" | awk '{print $1}')"
  bundle_paths+=("$bundle_path")

  if [[ -z "${seen_build_scripts[$build_script]+x}" ]]; then
    seen_build_scripts["$build_script"]=1
    build_scripts+=("$build_script")
  fi
done < "$REGISTRY_FILE"

if [[ "${#bundle_paths[@]}" -eq 0 ]]; then
  echo "No bundle entries found in registry: $REGISTRY_FILE" >&2
  exit 1
fi

for build_script in "${build_scripts[@]}"; do
  "$build_script"
done

out_of_sync=0
for bundle_path in "${bundle_paths[@]}"; do
  after_hash="$(sha256sum "$bundle_path" | awk '{print $1}')"
  if [[ "${before_hashes[$bundle_path]}" != "$after_hash" ]]; then
    echo "Out of sync bundle: $bundle_path" >&2
    out_of_sync=1
  fi
done

if [[ "$out_of_sync" -ne 0 ]]; then
  echo "Frontend bundles are out of sync with module sources." >&2
  echo "Rebuilt output changed bundle content. Re-run build scripts and commit updated bundles." >&2
  exit 1
fi

echo "Frontend bundle sync check: OK (${#bundle_paths[@]} bundles)"
