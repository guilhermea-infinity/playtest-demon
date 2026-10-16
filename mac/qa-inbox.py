#!/usr/bin/env python3
"""QA Inbox: the Mac half of Playtest Demon. Run it, leave the window open, play on the phone.

  python3 ~/Desktop/qa-clip/mac/qa-inbox.py

- Wi-Fi: advertises itself with Bonjour (_qaclip._tcp), so the phone finds this Mac with no IP typing.
- USB: runs `adb reverse` for any phone or emulator plugged in, for networks that block phone-to-Mac traffic.
- Phones first pair with this Mac’s code and pin its identity. All phone requests carry X-QA-Mac.
- A new phone on Wi-Fi gets a one-time "Allow?" dialog on this Mac. USB trust applies only to the matched destination.
- Clips land in ~/Desktop/QA-Inbox/<Game>/<date time>.mp4, a .json beside each, and one line per clip in
  inbox.jsonl (the list Claude reads to draft tickets).

Standard library only.
"""
import argparse
import datetime
import json
import hashlib
import tempfile
import os
import re
import shutil
import socket
import signal
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote_plus

from desk_games import games, game_name
from desk_identity import receiver_identity

PORT = 8799
TYPE = "_qaclip._tcp"
MAX_BYTES = 4 << 30


def mac_name():
    try:
        return subprocess.run(["scutil", "--get", "ComputerName"], capture_output=True, text=True, timeout=5).stdout.strip() or socket.gethostname()
    except Exception:
        return socket.gethostname()


def safe(s, n=60):
    s = re.sub(r"[^\w .,()'’&+-]", "_", str(s), flags=re.UNICODE).strip(" .")
    return s[:n] or "Unknown"


def applescript_text(s):
    return str(s).replace("\\", "").replace('"', "'")


def notify(title, msg):
    subprocess.Popen(["osascript", "-e", f'display notification "{applescript_text(msg)}" with title "{applescript_text(title)}" sound name "Glass"'],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def say(msg):
    print(f"{datetime.datetime.now():%H:%M:%S}  {msg}", flush=True)


class Devices:
    """Phone keys this Mac has said yes or no to. Unknown keys on Wi-Fi trigger one dialog."""

    def __init__(self, path):
        self.path = path
        self.identity = receiver_identity(path.parent / 'identity.json')
        self.lock = threading.Lock()
        self.asking = set()
        try:
            self.data = json.loads(path.read_text())
        except Exception:
            self.data = {}

    def _save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, indent=1))

    def status(self, key, name, trusted):
        with self.lock:
            d = self.data.get(key)
            if d:
                return d["status"]
            if trusted:
                self.data[key] = {"name": name, "status": "approved", "how": "usb", "at": time.time()}
                self._save()
                say(f"Trusted {name} (USB)")
                return "approved"
            if key not in self.asking:
                self.asking.add(key)
                threading.Thread(target=self._ask, args=(key, name), daemon=True).start()
            return "pending"

    def _ask(self, key, name):
        say(f"{name} wants to send clips. Answer the dialog on this Mac.")
        script = (f'display dialog "Allow “{applescript_text(name)}” to send QA clips to this Mac?" '
                  'buttons {"Don’t Allow", "Allow"} default button "Allow" with title "QA Inbox" giving up after 300')
        try:
            out = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=320).stdout
        except Exception:
            out = ""
        with self.lock:
            self.asking.discard(key)
            if "gave up:true" in out or "button returned:" not in out:
                return  # no answer: ask again next time it knocks
            ok = "button returned:Allow" in out
            self.data[key] = {"name": name, "status": "approved" if ok else "denied", "how": "wifi", "at": time.time()}
            self._save()
        say(f"{name}: {'allowed' if ok else 'not allowed'}")


def make_handler(inbox, devices, name):
    log = inbox / "inbox.jsonl"
    log_lock = threading.Lock()
    # The arrival log is the commit record: recover transfer identities after an ack/process loss.
    uploads = {}
    if log.exists():
        for line in log.read_text().splitlines():
            try:
                record = json.loads(line)
                if record.get('uploadHash'):
                    uploads[record['uploadHash']] = record['file']
            except (ValueError, AttributeError, KeyError):
                pass

    class H(BaseHTTPRequestHandler):
        server_version = "QAInbox/0.1"

        def log_message(self, *a):
            pass

        def _json(self, code, obj):
            b = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(b)))
            self.end_headers()
            self.wfile.write(b)

        def _who(self):
            key = self.headers.get("X-QA-Key", "")
            dev = safe(unquote_plus(self.headers.get("X-QA-Device", "phone")), 40)
            if not re.fullmatch(r"[0-9a-f]{32}", key):
                return "denied", dev
            usb = self.client_address[0] in ("127.0.0.1", "::1", "::ffff:127.0.0.1")
            status = devices.status(key, dev, trusted=usb)
            if status == "approved":
                with log_lock:
                    target = inbox / ".receiver.json"
                    temp = target.with_suffix(".tmp")
                    temp.write_text(json.dumps({"lastSeen": time.time(), "device": dev, "transport": "USB" if usb else "Wi-Fi"}))
                    os.replace(temp, target)
            return status, dev

        def _target(self):
            if self.headers.get('X-QA-Mac') != devices.identity['id']:
                self._json(409, {'ok': False, 'error': 'Pair this phone with this Mac using its pairing code.', 'code': 'wrong-mac'})
                return False
            return True

        def do_GET(self):
            if self.path == '/identity':
                return self._json(200, {**devices.identity, 'name': name})
            if not self._target():
                return
            if self.path == '/games':
                st, _ = self._who()
                if st != 'approved':
                    return self._json(403, {'ok': False})
                return self._json(200, {'games': games(inbox)})
            if self.path.startswith("/ping"):
                st, _ = self._who()
                return self._json(200, {"ok": True, "name": name, "status": st})
            self._json(404, {"ok": False})

        def do_POST(self):
            if not self._target():
                return
            if self.path == '/games':
                st, _ = self._who()
                if st != 'approved':
                    return self._json(403, {'ok': False})
                try:
                    n = int(self.headers.get('Content-Length', '0'))
                    if not 0 < n <= 16384:
                        raise ValueError('Invalid game request size')
                    body = json.loads(self.rfile.read(n))
                    names = body.get('games') if isinstance(body, dict) else None
                    if not isinstance(names, list) or len(names) > 100:
                        raise ValueError('Expected up to 100 game names')
                    return self._json(200, {'games': games(inbox, names)})
                except (ValueError, TypeError) as exc:
                    return self._json(400, {'error': str(exc)})
            if not self.path.startswith("/clip"):
                return self._json(404, {"ok": False})
            st, dev = self._who()
            if st != "approved":
                return self._json(403, {"ok": False, "status": st})
            try:
                n = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                n = 0
            if n <= 0 or n > MAX_BYTES:
                return self._json(400, {"ok": False, "error": "size"})
            try:
                meta = json.loads(unquote_plus(self.headers.get("X-QA-Meta", "{}")))
                if not isinstance(meta, dict):
                    meta = {}
            except Exception:
                meta = {}

            if meta.get('receiverId') and meta['receiverId'] != devices.identity['id']:
                return self._json(409, {'ok': False, 'error': 'This saved clip belongs to another Mac.', 'code': 'wrong-mac'})

            try:
                chosen = game_name(meta.get('game') or meta.get('appLabel') or meta.get('app') or 'Unknown app')
            except ValueError:
                chosen = 'Unknown app'
            names = games(inbox, [chosen])
            chosen = next(n for n in names if n.casefold() == chosen.casefold())
            meta['game'] = chosen
            game = safe(chosen)
            try:
                when = datetime.datetime.fromisoformat(str(meta.get("pressedAt")))
            except Exception:
                when = datetime.datetime.now()
            folder = inbox / game
            folder.mkdir(parents=True, exist_ok=True)
            handle, temp_name = tempfile.mkstemp(prefix='.upload-', suffix='.part', dir=folder)
            os.close(handle)
            part = Path(temp_name)
            digest = hashlib.sha256()
            digest.update(self.headers.get('X-QA-Key', '').encode())
            digest.update(self.headers.get('X-QA-Name', '').encode())
            got = 0
            try:
                with open(part, "wb") as f:
                    while got < n:
                        chunk = self.rfile.read(min(1 << 20, n - got))
                        if not chunk:
                            break
                        f.write(chunk)
                        digest.update(chunk)
                        got += len(chunk)
            except Exception:
                pass
            if got != n:
                part.unlink(missing_ok=True)
                return self._json(400, {"ok": False, "error": "short", "bytes": got})
            upload_hash = digest.hexdigest()
            with log_lock:
                existing = uploads.get(upload_hash)
                if existing and (inbox / existing).is_file():
                    part.unlink(missing_ok=True)
                    return self._json(200, {"ok": True, "bytes": got, "file": existing, "duplicate": True})
                stem = f"{when:%Y-%m-%d %H.%M.%S}"
                k = 2
                while (folder / f"{stem}.mp4").exists():
                    stem = f"{when:%Y-%m-%d %H.%M.%S} ({k})"
                    k += 1
                mp4 = folder / f"{stem}.mp4"
                part.rename(mp4)
                rel = str(mp4.relative_to(inbox))
                meta.update({"file": rel, "fromDevice": dev, "receivedAt": datetime.datetime.now().astimezone().isoformat(timespec="seconds"), "bytes": got, "uploadHash": upload_hash})
                (folder / f"{stem}.json").write_text(json.dumps(meta, indent=1, ensure_ascii=False))
                with open(log, "a") as f:
                    f.write(json.dumps({"file": rel, "game": chosen, "app": game, "version": meta.get("appVersion"), "pressedAt": meta.get("pressedAt"),
                                        "pressedAtSecond": meta.get("pressedAtSecond"), "clipSeconds": meta.get("clipSeconds"), "uploadHash": upload_hash,
                                        "voice": meta.get("voice"), "receivedAt": meta["receivedAt"]}, ensure_ascii=False) + "\n")
                    f.flush(); os.fsync(f.fileno())
                uploads[upload_hash] = rel
            secs = meta.get("clipSeconds")
            say(f"Clip in: {rel}  ({secs} s, {got / 1e6:.1f} MB)")
            notify("QA clip in", f"{game} · {secs} s")
            self._json(200, {"ok": True, "bytes": got, "file": rel})

    return H


def bonjour(name, port):
    if not shutil.which("dns-sd"):
        return None
    return subprocess.Popen(["dns-sd", "-R", name, TYPE, "local", str(port)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def adb_path():
    for p in (shutil.which("adb"), os.path.expanduser("~/Library/Android/sdk/platform-tools/adb")):
        if p and os.path.exists(p):
            return p
    return None


def usb_loop(port):
    adb = adb_path()
    if not adb:
        return
    done = set()
    while True:
        try:
            out = subprocess.run([adb, "devices"], capture_output=True, text=True, timeout=10).stdout
            now = {l.split()[0] for l in out.splitlines()[1:] if l.strip().endswith("\tdevice")}
            for s in now - done:
                r = subprocess.run([adb, "-s", s, "reverse", f"tcp:{port}", f"tcp:{port}"], capture_output=True, timeout=10)
                if r.returncode == 0:
                    done.add(s)
                    say(f"USB: {s} can reach this Mac")
            done &= now
        except Exception:
            pass
        time.sleep(4)


def watch_desk_owner(server, finished):
    """A managed receiver must not outlive its desk, even after SIGKILL.

    Standalone receiver launches have no desk owner and keep their normal lifecycle.
    Check the actual parent relationship, so a reused PID cannot keep an orphan alive.
    """
    value = os.environ.get('PLAYTEST_DEMON_DESK_PID', '')
    if not value.isdigit() or int(value) <= 1:
        return
    owner = int(value)

    def watch():
        while not finished.wait(1):
            if os.getppid() != owner:
                server.shutdown()
                return
    threading.Thread(target=watch, daemon=True).start()


def main():
    ap = argparse.ArgumentParser(description="Receive Playtest Demon videos from Android phones.")
    ap.add_argument("--inbox", default="~/Desktop/QA-Inbox")
    ap.add_argument("--port", type=int, default=PORT)
    ap.add_argument("--devices", default="~/.config/qa-clip/devices.json", help="approved phones")
    ap.add_argument("--no-usb", action="store_true", help="skip adb reverse")
    ap.add_argument("--no-bonjour", action="store_true", help="skip Wi-Fi advertisement (isolated tests)")
    a = ap.parse_args()

    inbox = Path(os.path.expanduser(a.inbox))
    inbox.mkdir(parents=True, exist_ok=True)
    devices = Devices(Path(os.path.expanduser(a.devices)))
    name = mac_name()

    srv = ThreadingHTTPServer(("0.0.0.0", a.port), make_handler(inbox, devices, name))
    srv.daemon_threads = True
    dns = None if a.no_bonjour else bonjour(name, a.port)
    if not a.no_usb:
        threading.Thread(target=usb_loop, args=(a.port,), daemon=True).start()

    print(f"\nQA Inbox is on.\n  Clips go to  {inbox}\n  Wi-Fi        {name} (Bonjour, port {a.port})"
          f"\n  USB          {'any phone or emulator plugged in' if adb_path() and not a.no_usb else 'off'}"
          f"\nLeave this window open while you play. Ctrl+C to stop.\n", flush=True)
    def stop(*_):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGHUP, stop)
    finished = threading.Event()
    watch_desk_owner(srv, finished)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        finished.set()
        if dns:
            dns.terminate()
            try:
                dns.wait(timeout=3)
            except subprocess.TimeoutExpired:
                dns.kill()
        srv.server_close()
        print("\nQA Inbox stopped.")


if __name__ == "__main__":
    sys.exit(main())
