#!/usr/bin/env bash
# Repository-local PlatformIO. No sudo, no shell-profile edits.
set -euo pipefail
cd "$(dirname "$0")"

if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3.10 or newer is required." >&2
  exit 1
fi

python3 - <<'PY'
import sys
if sys.version_info < (3, 10):
    raise SystemExit("Python 3.10 or newer is required.")
PY

python3 -m venv .venv-platformio
.venv-platformio/bin/python -m pip install --upgrade pip
.venv-platformio/bin/python -m pip install --requirement requirements-platformio.txt
.venv-platformio/bin/pio --version
echo "Use .venv-platformio/bin/pio for builds. VS Code PlatformIO IDE can share this."
