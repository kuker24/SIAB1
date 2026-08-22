#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_DIR="$ROOT_DIR/android-kiosk"

required_signing_vars=(
  SIAB1_SERVER_URL
  SIAB1_RELEASE_KEYSTORE
  SIAB1_RELEASE_STORE_PASSWORD
  SIAB1_RELEASE_KEY_ALIAS
  SIAB1_RELEASE_KEY_PASSWORD
)

for name in "${required_signing_vars[@]}"; do
  if [ -z "${!name:-}" ]; then
    echo "ERROR: $name is required for a signed release APK." >&2
    exit 1
  fi
done

if [ ! -d "$APP_DIR" ]; then
  echo "android-kiosk not found" >&2
  exit 1
fi

cd "$APP_DIR"
if [ -x "./gradlew" ]; then
  ./gradlew :app:assembleRelease
else
  gradle :app:assembleRelease
fi

echo "APK: $APP_DIR/app/build/outputs/apk/release/app-release.apk"
