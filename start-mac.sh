#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
export PYTHONDONTWRITEBYTECODE=1
find . -type d -name __pycache__ -prune -exec rm -rf {} + 2>/dev/null || true
find . -type f -name "*.pyc" -delete 2>/dev/null || true
if [ ! -d .venv ]; then
  echo "No .venv found. Running setup first..."
  ./setup.command
fi
source .venv/bin/activate
python - <<'PYDEP'
import importlib.util
import subprocess
import sys

required = {
    "webview": "pywebview",
    "qtpy": "qtpy",
    "PyQt6": "PyQt6",
    "PIL": "Pillow",
}
missing = [pkg for module, pkg in required.items() if importlib.util.find_spec(module) is None]
if missing:
    print("Installing missing dependencies:", ", ".join(missing))
    subprocess.check_call([sys.executable, "-m", "pip", "install", "--no-cache-dir", "-r", "requirements.txt"])
PYDEP
python app.py
