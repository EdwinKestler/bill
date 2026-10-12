#!/usr/bin/env bash
# Dock-client Python venv (Bleak). No sudo.
# QVAC fat wheel is separate: ./install_qvac.sh (requirements-qvac.txt).
set -euo pipefail
cd "$(dirname "$0")"

if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3.10 or newer is required." >&2
  exit 1
fi

python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install --requirement requirements.txt --requirement requirements-dev.txt
.venv/bin/python -c "from importlib.metadata import version; print('bleak', version('bleak'))"
echo "Activate with: source .venv/bin/activate"
