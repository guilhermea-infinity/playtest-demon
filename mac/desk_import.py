"""Streaming import for iPhone screen recordings (MOV/MP4) and desktop recordings."""
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from urllib.parse import unquote
from urllib.parse import urlparse

MAX_BYTES = 750 * 1024 * 1024


def capture_options(value):
    """Validate browser-provided trim positions before passing numbers to ffmpeg."""
    if not isinstance(value, dict):
        raise ValueError('Missing browser clip timing')
    bounds = {'start': (0, 90), 'duration': (.2, 211), 'pressed': (0, 30), 'lookback': (0, 30)}
    result = {}
    for name, (low, high) in bounds.items():
        n = value.get(name)
        if isinstance(n, bool) or not isinstance(n, (int, float)) or not math.isfinite(n) or not low <= n <= high:
            raise ValueError('Invalid browser clip timing')
        result[name] = round(n, 3)
    if result['pressed'] > result['duration'] or result['pressed'] > result['lookback'] + .1:
        raise ValueError('Invalid lookback timing')
    url = value.get('url', '')
    if not isinstance(url, str) or len(url) > 2048:
        raise ValueError('Invalid game link')
    try:
        parsed = urlparse(url)
        if url and (parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password):
            raise ValueError('Use an http or https game link without credentials')
    except ValueError:
        raise ValueError('Use an http or https game link without credentials') from None
    result['url'] = url
    return result


def import_recording(store, stream, length, game, filename, platform, capture=None):
    game = ' '.join(game.split())[:80]
    if not game:
        raise ValueError('Choose the game before importing')
    if length <= 0 or length > MAX_BYTES:
        raise ValueError('Choose a recording under 750 MB')
    browser = platform == 'Browser'
    timing = capture_options(capture) if browser else None
    if Path(filename).suffix.lower() not in (('.webm', '.mp4') if browser else ('.mp4', '.mov', '.m4v')):
        raise ValueError('Choose an MP4 or MOV screen recording')
    ffmpeg, probe = shutil.which('ffmpeg'), shutil.which('ffprobe')
    if not ffmpeg or not probe:
        raise ValueError('Install ffmpeg before importing recordings')
    folder = store.inbox / 'Imports'
    folder.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.import-', dir=folder) as temp:
        source = Path(temp) / 'source.mov'
        digest = hashlib.sha256()
        if browser:
            # A buffer can contain several distinct observations. Retry identity includes the trim and game.
            digest.update(json.dumps([game, timing], sort_keys=True).encode())
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
        if not any(s.get('codec_type') == 'video' for s in info.get('streams', [])) or (not browser and not 0 < duration <= 600):
            raise ValueError('Use a video between 1 second and 10 minutes; trim long sessions in Photos first')
        output = Path(temp) / 'clip.mp4'
        trim = ['-ss', str(timing['start']), '-t', str(timing['duration'])] if browser else []
        r = subprocess.run([ffmpeg, '-v', 'error', '-y', '-i', str(source), *trim, '-map', '0:v:0', '-map', '0:a:0?',
                            '-vf', "scale='min(1280,iw)':-2", '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '24',
                            '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-movflags', '+faststart', str(output)], capture_output=True, text=True, timeout=300)
        if r.returncode:
            raise ValueError('Could not convert this recording. Export it from Photos and retry.')
        if browser:
            check = subprocess.run([probe, '-v', 'error', '-show_entries', 'format=duration:stream=codec_type', '-of', 'json', str(output)], capture_output=True, text=True, timeout=30)
            if check.returncode:
                raise ValueError('The browser clip could not be read. Download it and retry.')
            info = json.loads(check.stdout)
            duration = float(info.get('format', {}).get('duration', 0))
            if not .1 <= duration <= 212 or not any(s.get('codec_type') == 'video' for s in info.get('streams', [])):
                raise ValueError('The browser clip is empty or too long. Record another clip.')
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
            if browser:
                meta.update(platform='Browser', device='Laptop browser', gameUrl=timing['url'],
                            pressedAtSecond=min(timing['pressed'], round(duration, 3)), lookbackSeconds=timing['lookback'])
            (store.inbox / rel).with_suffix('.json').write_text(json.dumps(meta))
            with (store.inbox / 'inbox.jsonl').open('a') as log:
                log.write(json.dumps(meta) + '\n'); log.flush(); os.fsync(log.fileno())
            store.sync_inbox()
            from desk_games import games
            games(store.inbox, [game])
            return {'duplicate': False, 'file': rel}
