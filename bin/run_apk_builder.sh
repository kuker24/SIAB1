#!/bin/bash
# Linux/macOS launcher for APK Builder GUI

# Ensure we are in the correct directory
cd "$(dirname "$0")"

# Check if python3 is available
if command -v python3 &> /dev/null; then
    PYTHON_CMD=python3
else
    PYTHON_CMD=python
fi

# Run the script
echo "🚀 Launching APK Builder GUI..."
$PYTHON_CMD apk_builder_gui.py
