import importlib.util
import json
from concurrent.futures import ThreadPoolExecutor
from http.server import ThreadingHTTPServer
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from urllib.parse import quote_plus

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'mac'))
from desk_games import games
from desk_models import normalize, validate_effort
from desk_store import Store

spec = importlib.util.spec_from_file_location('inbox', Path(__file__).resolve().parents[1] / 'mac/qa-inbox.py')
inbox = importlib.util.module_from_spec(spec)
spec.loader.exec_module(inbox)


class GamesModelsTests(unittest.TestCase):
    def test_games_merge_across_processes_and_deduplicate(self):
        with tempfile.TemporaryDirectory() as root:
            games(root, ['  Pocket   Garden  '])
            commands = [[sys.executable, '-c', 'import sys; from desk_games import games; games(sys.argv[1], [sys.argv[2]])', root, n]
                        for n in ['pocket garden', 'Orbit Runner', 'Tiny Workshop', 'New Game']]
            with ThreadPoolExecutor() as pool:
                results = list(pool.map(lambda cmd: subprocess.run(cmd, cwd=Path(inbox.__file__).parent, capture_output=True), commands))
            self.assertTrue(all(r.returncode == 0 for r in results))
            self.assertEqual(games(root), ['New Game', 'Orbit Runner', 'Pocket Garden', 'Tiny Workshop'])
            for name in ['', 'x'*81, 'bad\nname', None]:
                with self.assertRaises(ValueError): games(root, [name])
            self.assertEqual(len(games(root)), 4)

    def test_phone_game_sync_and_explicit_clip_attribution(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            devices = inbox.Devices(root / 'devices.json')
            server = ThreadingHTTPServer(('127.0.0.1', 0), inbox.make_handler(root, devices, 'Test Mac'))
            thread = threading.Thread(target=server.serve_forever); thread.start()
            url = f'http://127.0.0.1:{server.server_port}'
            headers = {'X-QA-Key': 'a'*32, 'X-QA-Mac': devices.identity['id'], 'Content-Type': 'application/json'}
            try:
                with self.assertRaises(HTTPError) as exc: urlopen(Request(url + '/games', headers={'X-QA-Mac': devices.identity['id']}))
                self.assertEqual(exc.exception.code, 403); exc.exception.close()
                req = Request(url+'/games', data=json.dumps({'games':['My Game']}).encode(), headers=headers)
                with urlopen(req) as response: self.assertEqual(json.load(response)['games'], ['My Game'])
                games(root, ['From Desktop'])
                with urlopen(Request(url+'/games', headers=headers)) as response:
                    self.assertEqual(json.load(response)['games'], ['From Desktop', 'My Game'])
                meta = {'game': 'my game', 'appLabel': 'Android Launcher', 'pressedAtSecond': 0, 'lookbackSeconds': 0}
                headers['X-QA-Meta'] = quote_plus(json.dumps(meta))
                with patch.object(inbox, 'notify'):
                    with urlopen(Request(url+'/clip', data=b'synthetic-video', headers=headers)) as response:
                        rel = json.load(response)['file']
                    with urlopen(Request(url+'/clip', data=b'synthetic-video', headers=headers)) as response:
                        repeated = json.load(response)
                    self.assertTrue(repeated['duplicate'])
                    self.assertEqual(repeated['file'], rel)
                    self.assertEqual(len((root/'inbox.jsonl').read_text().splitlines()), 1)
                saved = json.loads((root / rel).with_suffix('.json').read_text())
                self.assertEqual(saved['game'], 'My Game')
                self.assertEqual(saved['appLabel'], 'Android Launcher')
                self.assertEqual(saved['pressedAtSecond'], 0)
                store = Store(root); store.sync_inbox()
                self.assertEqual(store.state()['clips'][0]['meta']['game'], 'My Game')
            finally:
                server.shutdown(); thread.join(); server.server_close()

    def test_model_capabilities_and_effort_survive_restart(self):
        models = normalize('codex', [dict(model='vision', displayName='Vision', inputModalities=['image'],
            supportedReasoningEfforts=[{'reasoningEffort':'low'}, {'reasoningEffort':'high'}], defaultReasoningEffort='low'),
            dict(model='text-only', displayName='Text', inputModalities=['text'])])
        self.assertEqual([m['id'] for m in models], ['vision'])
        self.assertEqual(normalize('claude', [dict(value='small',displayName='Small',supportsEffort=False)])[0]['efforts'], [])
        with tempfile.TemporaryDirectory() as root, patch('desk_models.catalog', return_value={'models': models}):
            store = Store(root)
            store.configure({'provider':'codex','model':'vision','effort':'high'})
            self.assertEqual(Store(root).config()['effort'], 'high')
            with self.assertRaises(ValueError): store.configure({'effort':'max'})
            self.assertEqual(store.config()['effort'], 'high')
            store.configure({'paused': True})
            self.assertEqual(store.config()['effort'], 'high')
            store.configure({'model':'other'})
            self.assertEqual(store.config()['effort'], '')

    def test_upgrade_preserves_game_names_and_existing_tickets(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            store = Store(root)
            (root / 'Sanitized Game').mkdir()
            rel = 'Sanitized Game/clip.mp4'
            (root / rel).with_suffix('.json').write_text(json.dumps({'appLabel':'Game: Original'}))
            store.set_clip(rel, status='done', meta={'app':'Sanitized Game'})
            store.save_ticket({'id':'GO-001','clip':rel,'game':'Game: Original','title':'Keep me','status':'draft'})
            restored = Store(root)
            self.assertEqual(restored.state()['clips'][0]['meta']['game'], 'Game: Original')
            self.assertEqual(restored.state()['games'], ['Game: Original'])
            self.assertEqual(restored.state()['drafts'][0]['title'], 'Keep me')

    def test_slow_model_lookup_does_not_block_arrivals(self):
        with tempfile.TemporaryDirectory() as root:
            store = Store(root)
            started, finish = threading.Event(), threading.Event()
            def slow(*args): started.set(); finish.wait(2)
            with patch('desk_store.validate_effort', side_effect=slow):
                t = threading.Thread(target=store.configure, args=({'model':'vision','effort':'high'},));t.start()
                self.assertTrue(started.wait(1))
                before = __import__('time').monotonic()
                store.state()
                self.assertLess(__import__('time').monotonic() - before, .5)
                finish.set();t.join()
