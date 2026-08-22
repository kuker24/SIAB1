#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_DIR="$ROOT_DIR/android-kiosk"

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
