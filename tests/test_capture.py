"""Browser recordings must retain voice, trim the rolling buffer and retry safely."""
import io
import json
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from http.server import ThreadingHTTPServer
from urllib.request import Request, urlopen
from urllib.error import HTTPError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'mac'))
from desk_store import Store
from desk_import import import_recording, capture_options
from desk_server import make_handler


class CaptureTests(unittest.TestCase):
    def test_invalid_timing_and_links_are_rejected(self):
        good = dict(start=2, duration=3, pressed=1, lookback=10, url='https://example.com/game')
        for changes in ({'start': -1}, {'start': float('nan')}, {'duration': 0}, {'duration': 500},
                        {'pressed': 4}, {'lookback': True}, {'lookback': 31}, {'url': 'javascript:alert(1)'},
                        {'url': 'https://user:secret@example.com'}, {'url': 'http://['}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                capture_options({**good, **changes})

    @unittest.skipUnless(shutil.which('ffmpeg'), 'ffmpeg not installed')
    def test_browser_webm_trim_audio_retry_and_distinct_observations(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); store = Store(root / 'inbox'); source = root / 'buffer.webm'
            subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'testsrc2=s=160x100:r=10:d=4',
                            '-f', 'lavfi', '-i', 'sine=frequency=440:duration=4', '-c:v', 'libvpx', '-c:a', 'libopus', '-shortest', str(source)], check=True)
            data = source.read_bytes()
            timing = dict(start=1.5, duration=2, pressed=.5, lookback=10, url='https://example.com/game')
            one = import_recording(store, io.BytesIO(data), len(data), 'Browser Game', 'buffer.webm', 'Browser', timing)
            retry = import_recording(store, io.BytesIO(data), len(data), 'Browser Game', 'buffer.webm', 'Browser', timing)
            other = import_recording(store, io.BytesIO(data), len(data), 'Browser Game', 'buffer.webm', 'Browser', {**timing, 'start': 2, 'duration': 1})
            self.assertTrue(retry['duplicate']); self.assertEqual(one['file'], retry['file'])
            self.assertNotEqual(one['file'], other['file'])
            meta = store.clips[one['file']]['meta']
            self.assertEqual(meta['platform'], 'Browser'); self.assertTrue(meta['voice'])
            self.assertEqual(meta['pressedAtSecond'], .5); self.assertEqual(meta['lookbackSeconds'], 10)
            self.assertAlmostEqual(meta['clipSeconds'], 2, delta=.2)
            self.assertEqual(meta['gameUrl'], timing['url']); self.assertEqual(len(store.clips), 2)
            self.assertEqual(store.clips[one['file']]['status'], 'queued')

    def test_browser_route_and_same_origin_upload(self):
        with tempfile.TemporaryDirectory() as temp:
            store = Store(Path(temp))
            server = ThreadingHTTPServer(('127.0.0.1', 0), lambda *args: make_handler(store, server.server_port)(*args))
            worker = threading.Thread(target=server.serve_forever, daemon=True); worker.start()
            try:
                base = f'http://127.0.0.1:{server.server_port}'
                self.assertIn(b'Start playtest session', urlopen(base + '/playtest').read())
                self.assertIn(b'MediaRecorder', urlopen(base + '/playtest.js').read())
                for origin, timing, expected in [('https://evil.example', '{}', 403), (base, '{broken', 400)]:
                    req = Request(base + '/api/import', data=b'bad', headers={'Origin': origin, 'X-Platform': 'Browser', 'X-Capture': timing}, method='POST')
                    with self.assertRaises(HTTPError) as result: urlopen(req)
                    self.assertEqual(result.exception.code, expected)
                    result.exception.close()
                self.assertFalse(store.clips)
            finally:
                server.shutdown(); server.server_close(); worker.join()


if __name__ == '__main__': unittest.main()
