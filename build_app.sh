#!/bin/bash
set -e

echo "📦 Packaging AI Log Analyzer for Linux..."

# Use the current virtual environment's flet and pyinstaller
VENV_BIN="./venv/bin"
if [ ! -f "$VENV_BIN/flet" ]; then
  echo "❌ Error: flet not found in $VENV_BIN. Please install dependencies in your venv first."
  exit 1
fi

# Package as native desktop executable
# --onefile: produce a single executable
# --noconsole: don't show terminal window when running (GUI only)
"$VENV_BIN/flet" pack ui/app_flet.py \
  --name "AI Log Analyzer" \
  --icon assets/icon.png \
  --add-data "agents:agents" \
  --add-data "rag:rag" \
  --add-data "workflows:workflows" \
  --add-data "utils:utils" \
  --add-data "prompts:prompts" \
  --add-data "config.py:." \
  --add-data "requirements.txt:."

echo "✅ Linux build complete! Executable is in the 'dist' folder."
