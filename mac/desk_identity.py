"""Stable per-laptop receiver identity. Never distribute this file with the app."""
import fcntl
import json
import os
import secrets
from pathlib import Path


def receiver_identity(path=None):
    path = Path(path or '~/.config/qa-clip/identity.json').expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.with_suffix('.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if path.exists():
            value = json.loads(path.read_text())
            key = value.get('id', '')
            if len(key) != 32 or any(c not in '0123456789abcdef' for c in key):
                raise ValueError('Mac identity is invalid. Preserve identity.json and restore its backup.')
        else:
            key = secrets.token_hex(16)
            with path.open('x') as out:
                os.chmod(path, 0o600)
                json.dump({'id': key}, out); out.flush(); os.fsync(out.fileno())
    code = key[:8].upper()
    return {'id': key, 'code': code[:4] + '-' + code[4:]}
