"""Streaming import for iPhone screen recordings (MOV/MP4) and desktop recordings."""
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from urllib.parse import unquote

MAX_BYTES = 750 * 1024 * 1024


def import_recording(store, stream, length, game, filename, platform):
    game = ' '.join(game.split())[:80]
    if not game:
        raise ValueError('Choose the game before importing')
    if length <= 0 or length > MAX_BYTES:
        raise ValueError('Choose a recording under 750 MB')
    if Path(filename).suffix.lower() not in ('.mp4', '.mov', '.m4v'):
        raise ValueError('Choose an MP4 or MOV screen recording')
    ffmpeg, probe = shutil.which('ffmpeg'), shutil.which('ffprobe')
    if not ffmpeg or not probe:
        raise ValueError('Install ffmpeg before importing recordings')
    folder = store.inbox / 'Imports'
    folder.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.import-', dir=folder) as temp:
        source = Path(temp) / 'source.mov'
        digest = hashlib.sha256()
        left = length
        with source.open('wb') as f:
            while left:
                part = stream.read(min(left, 1 << 20))
                if not part:
                    raise ValueError('Upload was interrupted. Try again.')
                digest.update(part); f.write(part); left -= len(part)
        key = digest.hexdigest()
        with store.lock:
            existing = next((rel for rel, c in store.clips.items() if c.get('meta', {}).get('importHash') == key and c.get('status') != 'deleted'), None)
            if existing:
                return {'duplicate': True, 'file': existing}
        r = subprocess.run([probe, '-v', 'error', '-show_entries', 'format=duration:stream=codec_type', '-of', 'json', str(source)], capture_output=True, text=True, timeout=30)
        if r.returncode:
            raise ValueError('This file is not a readable recording')
        info = json.loads(r.stdout)
        duration = float(info.get('format', {}).get('duration', 0))
        if not any(s.get('codec_type') == 'video' for s in info.get('streams', [])) or not 0 < duration <= 600:
            raise ValueError('Use a video between 1 second and 10 minutes; trim long sessions in Photos first')
        output = Path(temp) / 'clip.mp4'
        r = subprocess.run([ffmpeg, '-v', 'error', '-y', '-i', str(source), '-map', '0:v:0', '-map', '0:a:0?',
                            '-vf', "scale='min(1280,iw)':-2", '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '24',
                            '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-movflags', '+faststart', str(output)], capture_output=True, text=True, timeout=300)
        if r.returncode:
            raise ValueError('Could not convert this recording. Export it from Photos and retry.')
        with store.lock:
            # Concurrent submissions of the same recording get one queue item.
            existing = next((rel for rel, c in store.clips.items() if c.get('meta', {}).get('importHash') == key and c.get('status') != 'deleted'), None)
            if existing:
                return {'duplicate': True, 'file': existing}
            rel = f'Imports/{time.time_ns()}-{key[:8]}.mp4'
            os.replace(output, store.inbox / rel)
            meta = {'file': rel, 'game': game, 'appLabel': game, 'platform': 'iOS' if platform == 'iOS' else 'Imported',
                    'device': 'iPhone / iPad' if platform == 'iOS' else 'Imported recording', 'originalName': Path(filename).name[:150],
                    'importHash': key, 'clipSeconds': round(duration, 1), 'pressedAtSecond': 0, 'lookbackSeconds': 0,
                    'voice': any(s.get('codec_type') == 'audio' for s in info['streams'])}
            (store.inbox / rel).with_suffix('.json').write_text(json.dumps(meta))
            with (store.inbox / 'inbox.jsonl').open('a') as log:
                log.write(json.dumps(meta) + '\n'); log.flush(); os.fsync(log.fileno())
            store.sync_inbox()
            from desk_games import games
            games(store.inbox, [game])
            return {'duplicate': False, 'file': rel}
