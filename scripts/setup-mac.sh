#!/bin/bash
# Installs local Python dependencies. --brew also installs the required Mac tools.
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ "$(uname -s)" != Darwin ]]; then
  echo 'QA Desk currently supports macOS laptops and Android phones.' >&2; exit 1
fi
if [[ "${1:-}" == --brew ]]; then
  command -v brew >/dev/null || { echo 'Install Homebrew from https://brew.sh first.' >&2; exit 1; }
  brew install python ffmpeg whisper-cpp openjdk@21
  brew install --cask android-platform-tools
elif [[ $# -ne 0 ]]; then
  echo 'Usage: scripts/setup-mac.sh [--brew]' >&2; exit 1
fi
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
printf '\nPython environment ready. Next: sign in to Codex or Claude Code.\n'
.venv/bin/python scripts/doctor.py || true
