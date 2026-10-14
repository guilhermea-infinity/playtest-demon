"""Tickets on disk. Everything lives under the inbox folder, so it is plain files you can open in Finder.

  QA-Inbox/Tickets/clips.json        each clip from inbox.jsonl: queued, working, done or failed
  QA-Inbox/Tickets/RL-001/           one folder per ticket: ticket.json + shot-N.png (red box) + shot-N-clean.png
  QA-Inbox/Tickets/.work/<clip>/     the analyst's frames, overview sheet, transcript and raw output
  QA-Inbox/Handoffs/*.md             every prompt you copied for the programmer agent
"""
import datetime
import json
import os
import re
import shutil
import threading
import time
from pathlib import Path

import desk_handoff

KINDS = ("bug", "change", "polish", "crash", "idea")
PRIORITIES = ("high", "normal", "low")
TEXT_FIELDS = ("title", "where", "now", "want", "done_when", "note")


def now_iso():
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")


def read_json(path, default):
    try:
        return json.loads(Path(path).read_text())
    except Exception:
        return default


def write_json(path, obj):
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(obj, indent=1, ensure_ascii=False))
    os.replace(tmp, path)


def prefix_for(game):
    """Ranch Legacy -> RL, Idle Dot Shooter -> IDS, Enigmic -> EN."""
    words = re.findall(r"[A-Za-z0-9]+", game or "")
    if len(words) >= 2:
        return "".join(w[0] for w in words)[:3].upper()
    return (words[0][:2] if words else "QA").upper()


class Store:
    def __init__(self, inbox):
        self.inbox = Path(inbox)
        self.root = self.inbox / "Tickets"
        self.handoff_dir = self.inbox / "Handoffs"
        self.work = self.root / ".work"
        for d in (self.root, self.handoff_dir, self.work):
            d.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.flags = {}  # auth state and the like, shown as banners in the page
        self.clips = read_json(self.root / "clips.json", {})
        self.handoffs = read_json(self.root / "handoffs.json", [])
        self.tickets = {}
        for f in self.root.glob("*/ticket.json"):
            t = read_json(f, None)
            if t and t.get("id"):
                self.tickets[t["id"]] = t
        for c in self.clips.values():  # a run cut off by a restart goes back in the queue
            if c.get("status") == "working":
                c["status"] = "queued"
        self._save_clips()

    # ---- clips ----

    def _save_clips(self):
        write_json(self.root / "clips.json", self.clips)

    def sync_inbox(self, skip_existing=False):
        """Queue every clip in inbox.jsonl that hasn't been seen. Returns how many were new."""
        log = self.inbox / "inbox.jsonl"
        try:
            lines = log.read_text().splitlines()
        except FileNotFoundError:
            return 0
        new = 0
        with self.lock:
            for line in lines:
                try:
                    m = json.loads(line)
                except Exception:
                    continue
                rel = m.get("file")
                if not rel or rel in self.clips:
                    continue
                self.clips[rel] = {"status": "skipped" if skip_existing else "queued", "meta": m,
                                   "queuedAt": time.time(), "tickets": []}
                new += 1
            if new:
                self._save_clips()
        return new

    def next_queued(self):
        with self.lock:
            q = [(c.get("queuedAt", 0), rel) for rel, c in self.clips.items() if c.get("status") == "queued"]
            return min(q)[1] if q else None

    def set_clip(self, rel, **kw):
        with self.lock:
            self.clips.setdefault(rel, {}).update(kw)
            self._save_clips()

    def retry_clip(self, rel, hint=None):
        """Queue a clip again. With a hint, the drafts it made are put aside and the analyst is told what was wrong."""
        with self.lock:
            c = self.clips.get(rel)
            if not c:
                return False
            if hint is not None:
                for tid in c.get("tickets", []):
                    t = self.tickets.get(tid)
                    if t and t["status"] == "draft":
                        t["status"] = "rejected"
                        t["rejectedWhy"] = "redone"
                        self.save_ticket(t)
                c["hint"] = hint.strip()[:1000]
            c.update(status="queued", queuedAt=time.time(), error=None)
            self._save_clips()
            return True

    # ---- tickets ----

    def new_ticket_id(self, game):
        p = prefix_for(game)
        with self.lock:
            used = [int(m.group(1)) for k in self.tickets for m in [re.fullmatch(re.escape(p) + r"-(\d+)", k)] if m]
            used += [int(m.group(1)) for d in self.root.iterdir() for m in [re.fullmatch(re.escape(p) + r"-(\d+)", d.name)] if m]
            return f"{p}-{max(used, default=0) + 1:03d}"

    def save_ticket(self, t):
        with self.lock:
            d = self.root / t["id"]
            d.mkdir(exist_ok=True)
            t["updated"] = now_iso()
            write_json(d / "ticket.json", t)
            self.tickets[t["id"]] = t

    def update_ticket(self, tid, fields):
        with self.lock:
            t = self.tickets.get(tid)
            if not t:
                return None
            for k in TEXT_FIELDS:
                if isinstance(fields.get(k), str):
                    t[k] = fields[k][:4000]
            if fields.get("kind") in KINDS:
                t["kind"] = fields["kind"]
            if fields.get("priority") in PRIORITIES:
                t["priority"] = fields["priority"]
            if isinstance(fields.get("steps"), list):
                t["steps"] = [str(s)[:500] for s in fields["steps"] if str(s).strip()][:20]
            if isinstance(fields.get("quote"), str) and isinstance(t.get("quote"), dict):
                t["quote"]["text"] = fields["quote"][:2000]
            if isinstance(fields.get("useShots"), list):
                keep = {str(s) for s in fields["useShots"]}
                for s in t.get("shots", []):
                    s["use"] = s["file"] in keep
            self.save_ticket(t)
            return t

    def set_status(self, tid, status):
        allowed = {"draft": ("approved", "rejected"), "approved": ("draft", "rejected"), "rejected": ("draft",)}
        with self.lock:
            t = self.tickets.get(tid)
            if not t or status not in allowed.get(t["status"], ()):
                return None
            t["status"] = status
            if status == "approved":
                t["approvedAt"] = now_iso()
            if status == "draft":
                t["order"] = time.time()  # back in the queue, at the end
            self.save_ticket(t)
            return t

    def later(self, tid):
        with self.lock:
            t = self.tickets.get(tid)
            if t and t["status"] == "draft":
                t["order"] = time.time()
                self.save_ticket(t)
            return t

    # ---- hand-offs ----

    def trays(self):
        """Approved tickets waiting to go to the programmer, one tray per game."""
        with self.lock:
            by = {}
            for t in sorted(self.tickets.values(), key=lambda t: (t.get("approvedAt") or "", t["id"])):
                if t["status"] == "approved":
                    by.setdefault(t["game"], []).append(t)
            return [{"game": g, "ids": [t["id"] for t in ts], "tickets": [{"id": t["id"], "title": t["title"]} for t in ts],
                     "prompt": desk_handoff.render(ts, self.inbox)}
                    for g, ts in sorted(by.items())]

    def handoff(self, game, ids):
        with self.lock:
            ts = [self.tickets[i] for i in ids if i in self.tickets and self.tickets[i]["status"] == "approved"
                  and self.tickets[i]["game"] == game]
            if not ts:
                return None
            prompt = desk_handoff.render(ts, self.inbox)
            n = len(self.handoffs) + 1
            when = datetime.datetime.now()
            name = f"{when:%Y-%m-%d %H.%M} {game} ({len(ts)}).md"
            (self.handoff_dir / name).write_text(prompt)
            rec = {"id": f"H-{n:03d}", "game": game, "tickets": [t["id"] for t in ts], "file": f"Handoffs/{name}",
                   "at": now_iso(), "titles": [t["title"] for t in ts]}
            self.handoffs.append(rec)
            write_json(self.root / "handoffs.json", self.handoffs)
            for t in ts:
                t["status"] = "sent"
                t["sentIn"] = rec["id"]
                t["sentAt"] = rec["at"]
                self.save_ticket(t)
            return rec

    def undo_handoff(self, hid):
        with self.lock:
            rec = next((h for h in self.handoffs if h["id"] == hid and not h.get("undone")), None)
            if not rec:
                return None
            for tid in rec["tickets"]:
                t = self.tickets.get(tid)
                if t and t["status"] == "sent" and t.get("sentIn") == hid:
                    t["status"] = "approved"
                    t.pop("sentIn", None)
                    t.pop("sentAt", None)
                    self.save_ticket(t)
            rec["undone"] = now_iso()
            write_json(self.root / "handoffs.json", self.handoffs)
            return rec

    def handoff_text(self, hid):
        rec = next((h for h in self.handoffs if h["id"] == hid), None)
        if not rec:
            return None
        try:
            return (self.inbox / rec["file"]).read_text()
        except Exception:
            return None

    # ---- the page's view of everything ----

    def state(self):
        with self.lock:
            ts = list(self.tickets.values())
            drafts = sorted((t for t in ts if t["status"] == "draft"), key=lambda t: (t.get("order", 0), t["id"]))
            rejected = sorted((t for t in ts if t["status"] == "rejected" and t.get("rejectedWhy") != "redone"),
                              key=lambda t: t.get("updated", ""), reverse=True)[:30]
            working = next(({"clip": rel, **{k: c.get(k) for k in ("step", "startedAt", "meta")}}
                            for rel, c in self.clips.items() if c.get("status") == "working"), None)
            failed = [{"clip": rel, "error": c.get("error"), "game": (c.get("meta") or {}).get("app")}
                      for rel, c in self.clips.items() if c.get("status") == "failed"]
            return {
                "drafts": drafts,
                "trays": self.trays(),
                "sent": [h for h in reversed(self.handoffs) if not h.get("undone")][:12],
                "rejected": [{"id": t["id"], "title": t["title"], "game": t["game"]} for t in rejected],
                "working": working,
                "queued": sum(1 for c in self.clips.values() if c.get("status") == "queued"),
                "failed": failed,
                "flags": dict(self.flags),
            }


def remove_tree(path):
    shutil.rmtree(path, ignore_errors=True)
