"""Frozen app entry point; also supports the receiver subprocess without a system Python."""
import argparse
import webbrowser
import os
import signal
import threading
import time
import runpy
import sys
from pathlib import Path

# Static imports let the packager collect their dependencies, including Pillow/jsonschema hooks.
import desk_analyst
import desk_server
import desk_runs
import desk_identity


def main():
    base = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent))
    receiver = len(sys.argv) > 1 and sys.argv[1] == '--receiver'
    if receiver:
        sys.argv.pop(1)
    owner = os.environ.get('PLAYTEST_DEMON_APP_PID')
    if owner and owner.isdigit():
        def watch_owner():
            while True:
                time.sleep(2)
                try:
                    os.kill(int(owner), 0)
                    if not receiver and os.getppid() != int(owner):
                        raise ProcessLookupError
                except ProcessLookupError:
                    os.kill(os.getpid(), signal.SIGTERM)
                    return
        threading.Thread(target=watch_owner, daemon=True).start()
    runpy.run_path(str(base / ('qa-inbox.py' if receiver else 'qa-desk.py')), run_name='__main__')


if __name__ == '__main__':
    main()
