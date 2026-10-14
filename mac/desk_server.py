"""The review page, on http://127.0.0.1:8800. Only this Mac can open it (it never listens on the network)."""
import json
import mimetypes
import re
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

HERE = Path(__file__).resolve().parent
UI = HERE / "desk-ui" / "index.html"


def make_handler(store, port):
    hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
    origins = {f"http://{h}" for h in hosts}

    class H(BaseHTTPRequestHandler):
        server_version = "QADesk/0.1"

        def log_message(self, *a):
            pass

        def _ok_host(self):
            return self.headers.get("Host", "") in hosts

        def _send(self, code, body, ctype="application/json", extra=None):
            b = body if isinstance(body, bytes) else body.encode()
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(b)))
            self.send_header("Cache-Control", "no-store")
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(b)

        def _json(self, obj, code=200):
            self._send(code, json.dumps(obj, ensure_ascii=False))

        # ---- reads ----

        def do_GET(self):
            if not self._ok_host():
                return self._send(403, "{}")
            u = urlparse(self.path)
            if u.path in ("/", "/index.html"):
                return self._send(200, UI.read_bytes(), "text/html; charset=utf-8")
            if u.path == "/app.css":
                return self._send(200, (UI.parent / "app.css").read_bytes(), "text/css; charset=utf-8")
            if u.path == "/api/state":
                return self._json(store.state())
            if u.path.startswith("/media/"):
                return self._file(unquote(u.path[len("/media/"):]))
            if u.path == "/api/tray.md":  # the drag-out file: a preview, sending nothing
                game = parse_qs(u.query).get("game", [""])[0]
                tray = next((t for t in store.trays() if t["game"] == game), None)
                if not tray:
                    return self._send(404, "{}")
                return self._send(200, tray["prompt"], "text/markdown; charset=utf-8")
            m = re.fullmatch(r"/api/handoff/(H-\d+)\.md", u.path)
            if m:
                txt = store.handoff_text(m.group(1))
                return self._send(200, txt, "text/markdown; charset=utf-8") if txt else self._send(404, "{}")
            self._send(404, "{}")

        def _file(self, rel):
            base = store.inbox.resolve()
            p = (base / rel).resolve()
            if base not in p.parents or not p.is_file():
                return self._send(404, "{}")
            size = p.stat().st_size
            ctype = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
            rng = re.fullmatch(r"bytes=(\d*)-(\d*)", self.headers.get("Range", ""))
            start, end = 0, size - 1
            if rng and (rng.group(1) or rng.group(2)):
                if rng.group(1):
                    start = int(rng.group(1))
                    end = int(rng.group(2)) if rng.group(2) else size - 1
                else:
                    start = max(0, size - int(rng.group(2)))
                end = min(end, size - 1)
                if start > end:
                    self.send_response(416)
                    self.send_header("Content-Range", f"bytes */{size}")
                    self.end_headers()
                    return
            n = end - start + 1
            self.send_response(206 if rng else 200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(n))
            self.send_header("Accept-Ranges", "bytes")
            if rng:
                self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            self.end_headers()
            try:
                with open(p, "rb") as f:
                    f.seek(start)
                    while n > 0:
                        chunk = f.read(min(1 << 20, n))
                        if not chunk:
                            break
                        self.wfile.write(chunk)
                        n -= len(chunk)
            except (BrokenPipeError, ConnectionResetError):
                pass

        # ---- writes: JSON only, same page only ----

        def do_POST(self):
            if not self._ok_host() or self.headers.get("Origin", next(iter(origins))) not in origins:
                return self._send(403, "{}")
            if not self.headers.get("Content-Type", "").startswith("application/json"):
                return self._send(415, "{}")
            try:
                n = min(int(self.headers.get("Content-Length", "0")), 1 << 20)
                body = json.loads(self.rfile.read(n) or b"{}")
            except Exception:
                return self._send(400, "{}")
            if not isinstance(body, dict):
                return self._json({"error": "Expected a JSON object"}, 400)
            p = urlparse(self.path).path
            if p == "/api/settings":
                try:
                    return self._json({"ok": True, "settings": store.configure(body)})
                except ValueError as exc:
                    return self._json({"error": str(exc)}, 400)

            m = re.fullmatch(r"/api/ticket/([A-Z0-9]+-\d+)", p)
            if m:
                t = store.update_ticket(m.group(1), body)
                return self._json({"ok": bool(t)}, 200 if t else 404)
            m = re.fullmatch(r"/api/ticket/([A-Z0-9]+-\d+)/(approve|reject|review|later)", p)
            if m:
                tid, act = m.groups()
                if body.get("fields"):
                    store.update_ticket(tid, body["fields"])
                if act == "later":
                    t = store.later(tid)
                else:
                    t = store.set_status(tid, {"approve": "approved", "reject": "rejected", "review": "draft"}[act])
                return self._json({"ok": bool(t)}, 200 if t else 409)
            if p == "/api/handoff":
                rec = store.handoff(str(body.get("game", "")), [str(i) for i in body.get("ids", [])])
                return self._json({"ok": bool(rec), "handoff": rec}, 200 if rec else 409)
            m = re.fullmatch(r"/api/handoff/(H-\d+)/undo", p)
            if m:
                rec = store.undo_handoff(m.group(1))
                return self._json({"ok": bool(rec)}, 200 if rec else 409)
            if p == "/api/clip/retry":
                hint = body.get("hint")
                ok = store.retry_clip(str(body.get("clip", "")), hint if isinstance(hint, str) and hint.strip() else None)
                return self._json({"ok": ok}, 200 if ok else 409)
            self._send(404, "{}")

    return H
