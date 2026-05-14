#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if [ ! -d .venv ]; then
  echo "No .venv found. Running setup first..."
  ./setup.sh
fi
source .venv/bin/activate

# v0.1.5: if a user updates the app without rebuilding the venv,
# install any newly added dependencies before launching.
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
