#!/usr/bin/env python3
"""Read-only prerequisite checks; never reads or prints login tokens."""
import argparse
import importlib.util
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'mac'))
from desk_analyst import find_tools


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--provider', choices=['claude', 'codex'], default='claude')
    args = parser.parse_args()
    tools = find_tools()
    checks = [('macOS', platform.system() == 'Darwin', True)]
    checks += [(name, bool(tools[name]), True) for name in ['ffmpeg', 'ffprobe', args.provider]]
    checks += [(name, importlib.util.find_spec(name) is not None, True) for name in ['PIL', 'jsonschema']]
    checks += [('Voice transcription', bool(tools['whisper'] and tools['whisper_model']), False)]
    adb = shutil.which('adb') or str(Path.home() / 'Library/Android/sdk/platform-tools/adb')
    checks += [('GitHub CLI for fix runs', bool(shutil.which('gh')), False), ('Git for fix runs', bool(shutil.which('git')), False)]
    checks += [('Android USB tools', Path(adb).is_file(), False)]
    if tools[args.provider]:
        command = ['auth', 'status'] if args.provider == 'claude' else ['login', 'status']
        try:
            r = subprocess.run([tools[args.provider], *command], capture_output=True, timeout=20)
            checks += [('CLI signed in', r.returncode == 0, True)]
        except subprocess.TimeoutExpired:
            checks += [('CLI sign-in check timed out', False, True)]
    for label, ok, required in checks:
        print(f'{"OK" if ok else "MISSING" if required else "OPTIONAL":8} {label}')
    print('\nSee docs/INSTALL-AGENT.md for installation and phone verification.')
    return int(any(not ok and required for _, ok, required in checks))

if __name__ == '__main__':
    sys.exit(main())
