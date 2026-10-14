#!/usr/bin/env python3
"""QA Desk: the whole Mac side of QA Clip in one window.

  python3 ~/Desktop/qa-clip/mac/qa-desk.py

1. Starts the inbox (qa-inbox.py), which receives clips from the phone.
2. Runs the analyst: every new clip gets frames, a transcript and a Claude Code run that drafts tickets.
3. Serves the review page on http://127.0.0.1:8800 and opens it. Approve tickets one by one; approved tickets
   collect into one prompt per game that you copy or drag into your programmer agent.

Needs ffmpeg, whisper-cli (optional, for your voice) and Claude Code signed in (`claude auth login`).
"""
import argparse
import datetime
import os
import signal
import socket
import subprocess
import sys
import threading
import webbrowser
from http.server import ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import desk_analyst  # noqa: E402
import desk_server  # noqa: E402
from desk_store import Store  # noqa: E402

HERE = Path(__file__).resolve().parent


def say(msg):
    print(f"{datetime.datetime.now():%H:%M:%S}  {msg}", flush=True)


def notify(title, msg):
    esc = lambda s: str(s).replace("\\", "").replace('"', "'")
    subprocess.Popen(["osascript", "-e", f'display notification "{esc(msg)}" with title "{esc(title)}" sound name "Glass"'],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def port_busy(port):
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def start_inbox(inbox):
    if port_busy(8799):
        say("The inbox is already running (port 8799), so I'm using that one.")
        return None
    p = subprocess.Popen([sys.executable, "-u", str(HERE / "qa-inbox.py"), "--inbox", str(inbox)],
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

    def pump():
        for line in p.stdout:
            line = line.rstrip()
            if line and not line.startswith("Leave this window") and not line.startswith("QA Inbox stopped"):
                print(f"          inbox │ {line}", flush=True)

    threading.Thread(target=pump, daemon=True).start()
    return p


def main():
    ap = argparse.ArgumentParser(description="Receive QA clips, draft tickets with Claude, review them.")
    ap.add_argument("--inbox", default="~/Desktop/QA-Inbox")
    ap.add_argument("--port", type=int, default=8800, help="review page port (this Mac only)")
    ap.add_argument("--model", default="opus", help="Claude model for the analyst (default: opus)")
    ap.add_argument("--from-now", action="store_true", help="don't analyse clips that are already in the inbox")
    ap.add_argument("--no-inbox", action="store_true", help="don't start the phone receiver")
    ap.add_argument("--no-open", action="store_true", help="don't open the review page")
    a = ap.parse_args()

    inbox = Path(os.path.expanduser(a.inbox))
    inbox.mkdir(parents=True, exist_ok=True)
    store = Store(inbox)
    tools = desk_analyst.find_tools()

    child = None if a.no_inbox else start_inbox(inbox)
    desk_analyst.Analyst(store, tools, a.model, say, notify, skip_existing=a.from_now).start()

    srv = ThreadingHTTPServer(("127.0.0.1", a.port), desk_server.make_handler(store, a.port))
    srv.daemon_threads = True
    url = f"http://127.0.0.1:{a.port}"
    missing = [n for n, k in (("ffmpeg", "ffmpeg"), ("whisper-cli", "whisper"), ("a whisper model", "whisper_model"),
                              ("claude", "claude")) if not tools[k]]
    print(f"\nQA Desk is on.\n  Review page  {url}\n  Clips        {inbox}\n  Analyst      Claude ({a.model})"
          + (f"\n  Missing      {', '.join(missing)}" if missing else "")
          + "\nLeave this window open while you play. Ctrl+C to stop.\n", flush=True)
    if not a.no_open:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()

    def stop(*_):  # closing the Terminal window (SIGHUP) or a kill (SIGTERM) also stops the inbox
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGHUP, stop)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()
        if child:
            child.terminate()
            try:
                child.wait(5)
            except Exception:
                child.kill()
        print("\nQA Desk stopped.")


if __name__ == "__main__":
    sys.exit(main())
