#!/usr/bin/env python3
"""Playtest Demon: the whole Mac side of Playtest Demon in one window.

  python3 ~/Desktop/qa-clip/mac/qa-desk.py

1. Starts the inbox (qa-inbox.py), which receives clips from the phone.
2. Runs the analyst: every new clip gets frames, a transcript and a selected CLI run that drafts tickets.
3. Serves the review page on http://127.0.0.1:8800 and opens it. Approve tickets one by one; approved tickets
   collect into one prompt per game that you copy or drag into your programmer agent.

Needs ffmpeg, optional whisper-cli for voice, and a signed-in Codex or Claude CLI.
"""
import argparse
import datetime
import fcntl
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
import desk_runs
import desk_server  # noqa: E402
from desk_identity import receiver_identity
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
        raise RuntimeError("Port 8799 is occupied. Stop the existing receiver, or use --no-inbox after confirming it writes to this inbox.")
    command = [sys.executable, "--receiver"] if getattr(sys, "frozen", False) else [sys.executable, "-u", str(HERE / "qa-inbox.py")]
    p = subprocess.Popen([*command, "--inbox", str(inbox)],
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, start_new_session=True,
                         env={**os.environ, "PLAYTEST_DEMON_DESK_PID": str(os.getpid())})

    def pump():
        for line in p.stdout:
            line = line.rstrip()
            if line and not line.startswith("Leave this window") and not line.startswith("QA Inbox stopped"):
                print(f"          inbox │ {line}", flush=True)

    threading.Thread(target=pump, daemon=True).start()
    return p


def main():
    ap = argparse.ArgumentParser(description="Receive QA clips, draft tickets with Claude Code or Codex CLI, review them.")
    ap.add_argument("--inbox", default="~/Desktop/QA-Inbox")
    ap.add_argument("--port", type=int, default=8800, help="review page port (this Mac only)")
    ap.add_argument("--provider", choices=("claude", "codex"), help="CLI to analyse clips (saved in this inbox)")
    ap.add_argument("--model", help="Model ID; empty string uses the CLI default")
    ap.add_argument("--paused", action="store_true", help="Receive clips without starting new analyses")
    ap.add_argument("--from-now", action="store_true", help="don't analyse clips that are already in the inbox")
    ap.add_argument("--no-inbox", action="store_true", help="don't start the phone receiver")
    ap.add_argument("--no-open", action="store_true", help="don't open the review page")
    a = ap.parse_args()

    inbox = Path(os.path.expanduser(a.inbox))
    inbox.mkdir(parents=True, exist_ok=True)
    # Hold this descriptor for the lifetime of the process, before touching state.
    inbox_lock = (inbox / ".desk.lock").open("a+")
    try:
        fcntl.flock(inbox_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        ap.error(f"Another Playtest Demon is already using {inbox}")
    store = Store(inbox)
    store.flags['pairing'] = receiver_identity()
    config = {}
    if a.provider:
        config.update(provider=a.provider, model="")
    if a.model is not None:
        config["model"] = a.model
    if a.paused:
        config["paused"] = True
    if config:
        store.configure(config)
    tools = desk_analyst.find_tools()
    store.flags["tools"] = {k: bool(v) for k, v in tools.items()}
    store.sync_inbox(skip_existing=a.from_now)
    stop_event = threading.Event()

    srv = ThreadingHTTPServer(("127.0.0.1", a.port), desk_server.make_handler(store, a.port))
    srv.daemon_threads = True
    child = None if a.no_inbox else start_inbox(inbox)
    def receiver_health():
        while not stop_event.wait(3):
            store.flags["receiverRunning"] = bool(child and child.poll() is None)
    threading.Thread(target=receiver_health, daemon=True).start()
    threading.Thread(target=store.watch_inbox, args=(stop_event,), daemon=True).start()
    analyst = desk_analyst.Analyst(store, tools, say, notify, stop_event)
    analyst.start()
    runner = desk_runs.Runs(store, stop_event)
    runner.start()
    store.flags["receiverRunning"] = bool(child and child.poll() is None)
    url = f"http://127.0.0.1:{a.port}"
    missing = [n for n, k in (("ffmpeg", "ffmpeg"), ("whisper-cli", "whisper"), ("a whisper model", "whisper_model"),
                              (store.config()["provider"], store.config()["provider"])) if not tools[k]]
    print(f"\nPlaytest Demon is on.\n  Review page  {url}\n  Clips        {inbox}\n  Analyst      {store.config()['provider']} ({store.config()['model'] or 'CLI default'})"
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
        stop_event.set()
        analyst.cancel_provider()
        runner.cancel_process()
        srv.server_close()
        if child:
            try:
                os.killpg(child.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                child.wait(5)
            except Exception:
                try:
                    os.killpg(child.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
        print("\nPlaytest Demon stopped.")


if __name__ == "__main__":
    sys.exit(main())
