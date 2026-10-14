#!/bin/bash
# Installs local Python dependencies. --brew also installs the required Mac tools.
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ "$(uname -s)" != Darwin ]]; then
  echo 'Playtest Demon currently supports macOS laptops with Android recording or iOS imports.' >&2; exit 1
fi
QA_INSTALL_BREW=false
QA_ANDROID_TOOLS=true
for QA_SETUP_ARG in "$@"; do
  case "$QA_SETUP_ARG" in
    --brew) QA_INSTALL_BREW=true ;;
    --ios) QA_ANDROID_TOOLS=false ;;
    *) echo 'Usage: scripts/setup-mac.sh [--brew] [--ios]' >&2; exit 1 ;;
  esac
done
if $QA_INSTALL_BREW; then
  command -v brew >/dev/null || { echo 'Install Homebrew from https://brew.sh first.' >&2; exit 1; }
  brew install python ffmpeg whisper-cpp gh
  if $QA_ANDROID_TOOLS; then
    brew install openjdk@21
    brew install --cask android-platform-tools
  fi
fi
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
printf '\nPython environment ready. Next: sign in to Codex or Claude Code.\n'
.venv/bin/python scripts/doctor.py || true
