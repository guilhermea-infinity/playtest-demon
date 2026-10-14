#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"
if [[ ! -x .venv/bin/python ]]; then
  echo 'First run: bash scripts/setup-mac.sh --brew (see README.md).'
  exit 1
fi
exec .venv/bin/python mac/qa-desk.py "$@"
