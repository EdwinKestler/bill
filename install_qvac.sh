#!/usr/bin/env bash
# Fat linux-x64 tetherto-qvac-sdk into .venv. No GGUF download. No sudo.
set -euo pipefail
cd "$(dirname "$0")"
ROOT="$(pwd)"
VENV="$ROOT/.venv"
ASSETS="https://github.com/tetherto/qvac/releases/expanded_assets/sdk-v0.21.0"

if [[ ! -x "$VENV/bin/python" ]]; then
  echo "Run ./install_python.sh first." >&2
  exit 1
fi

if [[ -n "${QVAC_CACHE_DIR:-}" ]]; then
  mkdir -p "$QVAC_CACHE_DIR"
  export QVAC_CACHE_DIR="$(cd "$QVAC_CACHE_DIR" && pwd)"
else
  mkdir -p "$ROOT/.qvac"
  export QVAC_CACHE_DIR="$ROOT/.qvac"
fi

"$VENV/bin/python" -m pip install --upgrade pip
"$VENV/bin/python" -m pip install --requirement requirements-qvac.txt -f "$ASSETS"
"$VENV/bin/python" scripts/qvac_smoke.py
echo "QVAC_CACHE_DIR=$QVAC_CACHE_DIR"
echo "Activate with: source .venv/bin/activate"
