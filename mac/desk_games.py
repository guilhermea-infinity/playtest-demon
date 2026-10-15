"""Shared game names. File locking coordinates the receiver and the desk processes."""
import fcntl
import json
import os
import threading
from pathlib import Path

_LOCK = threading.RLock()


def game_name(value):
    if not isinstance(value, str) or any(ord(c) < 32 for c in value):
        raise ValueError("Enter a game name")
    value = " ".join(value.split())
    if not value or len(value) > 80:
        raise ValueError("Use a game name between 1 and 80 characters")
    return value


def games(inbox, additions=(), rename=None):
    names = [game_name(n) for n in additions]
    path = Path(inbox) / "games.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    with _LOCK, open(path.with_suffix('.lock'), 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        current = json.loads(path.read_text()) if path.exists() else []
        if rename:
            old, new = map(game_name, rename)
            current = [new if n == old else n for n in current]
        known = {n.casefold(): n for n in current}
        for name in names:
            known.setdefault(name.casefold(), name)
        result = sorted(known.values(), key=str.casefold)
        if result != current or rename:
            tmp = path.with_suffix('.tmp')
            tmp.write_text(json.dumps(result, ensure_ascii=False, indent=2))
            os.replace(tmp, path)
        return result
