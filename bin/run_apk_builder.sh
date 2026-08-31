#!/bin/bash
# Linux/macOS launcher for APK Builder GUI

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [ -x "$ROOT/.venv/bin/python" ]; then
    PYTHON_CMD="$ROOT/.venv/bin/python"
elif command -v python3 &> /dev/null; then
    PYTHON_CMD=python3
else
    PYTHON_CMD=python
fi

exec "$PYTHON_CMD" tools/apk_builder_gui.py
