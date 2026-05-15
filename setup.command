#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
PYTHON_BIN="${PYTHON_BIN:-python3}"
if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "python3 not found. Install Python 3.10+ from https://www.python.org/downloads/macos/ or Homebrew."
  read -r -p "Press Return to close..." _ || true
  exit 1
fi
"$PYTHON_BIN" -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install --no-cache-dir -r requirements.txt
echo
echo "Setup complete. Double-click start.command to launch Character Card Forge."
read -r -p "Press Return to close..." _ || true
