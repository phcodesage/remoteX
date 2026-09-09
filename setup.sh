#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

if [[ ! -x .venv/bin/python ]]; then
  echo "Creating project virtual environment at $PROJECT_DIR/.venv"
  python3 -m venv .venv
fi

echo "Installing remoteX dependencies into $PROJECT_DIR/.venv"
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install --only-binary=av -r requirements.txt

echo
echo "remoteX is ready. Start it with:"
echo "  .venv/bin/python run.py"
