import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from http.server import ThreadingHTTPServer
from urllib.request import Request, urlopen
from urllib.error import HTTPError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'mac'))
from desk_store import Store
from desk_server import make_handler
from desk_analyst import Analyst, SCHEMA, strict_schema
from jsonschema import validate


class DeskTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.store = Store(self.root)

    def incoming(self, rel='Game/clip.mp4'):
        (self.root / 'inbox.jsonl').write_text(json.dumps({'file': rel, 'app': 'Game'}) + '\n')
        self.store.sync_inbox()
        return rel

    def ticket(self, tid='GA-001'):
        t = {'id': tid, 'game': 'Game', 'clip': 'Game/clip.mp4', 'title': 'A finding', 'status': 'draft',
             'kind': 'bug', 'priority': 'normal', 'shots': [], 'steps': [], 'moment': {}, 'order': 1}
        self.store.save_ticket(t)
        return t

    def test_live_discovery_during_active_analysis(self):
        rel = self.incoming()
        self.store.set_clip(rel, status='working')
        stop = threading.Event()
        watcher = threading.Thread(target=self.store.watch_inbox, args=(stop,))
        watcher.start()
        try:
            with (self.root / 'inbox.jsonl').open('a') as f:
                f.write(json.dumps({'file': 'Game/new.mp4', 'app': 'Game'}) + '\n')
            deadline = time.monotonic() + 3
            while time.monotonic() < deadline and len(self.store.state()['clips']) < 2:
                time.sleep(.05)
            self.assertEqual(len(self.store.state()['clips']), 2)
            self.assertEqual(self.store.clips[rel]['status'], 'working')
        finally:
            stop.set(); watcher.join()

    def test_retry_does_not_requeue_active_or_queued_clip(self):
        rel = self.incoming()
        self.assertFalse(self.store.retry_clip(rel))
        self.store.set_clip(rel, status='working')
        self.assertFalse(self.store.retry_clip(rel, 'hint'))
        self.store.set_clip(rel, status='failed')
        self.assertTrue(self.store.retry_clip(rel))
        self.assertEqual(self.store.clips[rel]['status'], 'queued')

    def test_restart_recovers_work_and_settings(self):
        rel = self.incoming()
        self.store.set_clip(rel, status='working')
        self.store.configure({'provider': 'codex', 'model': 'custom-model', 'paused': True})
        restarted = Store(self.root)
        self.assertEqual(restarted.next_queued(), rel)
        self.assertEqual(restarted.config(), {'provider': 'codex', 'model': 'custom-model', 'paused': True})

    def test_review_edit_approve_reject_undo(self):
        self.ticket()
        self.store.update_ticket('GA-001', {'title': 'Edited', 'steps': ['Do it']})
        self.store.set_status('GA-001', 'approved')
        self.assertEqual(self.store.trays()[0]['tickets'][0]['title'], 'Edited')
        self.store.set_status('GA-001', 'rejected')
        self.store.set_status('GA-001', 'draft')
        self.assertEqual(self.store.state()['drafts'][0]['steps'], ['Do it'])

    def test_handoffs_never_overwrite_each_other(self):
        self.ticket()
        self.store.set_status('GA-001', 'approved')
        one = self.store.handoff('Game', ['GA-001'])
        self.store.undo_handoff(one['id'])
        two = self.store.handoff('Game', ['GA-001'])
        self.assertNotEqual(one['file'], two['file'])
        self.assertTrue((self.root / one['file']).exists())
        self.assertIn('GA-001', self.store.handoff_text(two['id']))

    def test_redo_preserves_approved_tickets(self):
        rel = self.incoming()
        self.ticket(); self.ticket('GA-002')
        self.store.set_status('GA-002', 'approved')
        self.store.set_clip(rel, status='done', tickets=['GA-001', 'GA-002'])
        self.assertTrue(self.store.retry_clip(rel, 'Please focus on the menu'))
        self.assertEqual(self.store.tickets['GA-001']['status'], 'rejected')
        self.assertEqual(self.store.tickets['GA-002']['status'], 'approved')

    def test_state_is_detached_and_includes_every_clip(self):
        rel = self.incoming(); self.ticket()
        state = self.store.state()
        self.assertEqual(state['clips'][0]['draftIds'], ['GA-001'])
        state['clips'][0]['meta']['app'] = 'Changed'
        self.assertEqual(self.store.clips[rel]['meta']['app'], 'Game')

    def test_invalid_settings_do_not_overwrite(self):
        for data in [{'provider': 'unknown'}, {'model': 'bad model'}, {'paused': 'false'}]:
            with self.assertRaises(ValueError):
                self.store.configure(data)
        self.assertEqual(self.store.config()['provider'], 'claude')

    def test_both_cli_adapters_pass_model_and_validate_results(self):
        work = self.root / 'work'; work.mkdir()
        data = {'clip_summary': 'Synthetic clip', 'tickets': []}
        analyst = Analyst(self.store, {'claude': '/bin/claude', 'codex': '/bin/codex'}, print, lambda *_: None)
        def execute(cmd, **kwargs):
            self.assertIn('--model', cmd)
            self.assertEqual(cmd[cmd.index('--model') + 1], 'chosen-model')
            if cmd[0] == '/bin/codex':
                self.assertIn('read-only', cmd)
                (work / 'answer.json').write_text(json.dumps(data))
                output = ''
            else:
                self.assertIn('Read,Glob', cmd)
                output = json.dumps({'structured_output': data})
            return subprocess.CompletedProcess(cmd, 0, output, '')
        with patch.object(analyst, 'run_provider', side_effect=lambda cmd, prompt, work: execute(cmd)):
            for provider in ['claude', 'codex']:
                self.assertEqual(analyst.ask_provider('test', work, provider, 'chosen-model'), data)
        validate(data, strict_schema(SCHEMA))

    def test_provider_failure_does_not_create_tickets(self):
        work = self.root / 'work'; work.mkdir()
        analyst = Analyst(self.store, {'claude': '/bin/claude'}, print, lambda *_: None)
        with patch.object(analyst, 'run_provider', return_value=subprocess.CompletedProcess([], 1, '', 'login required')):
            with self.assertRaisesRegex(RuntimeError, 'login required'):
                analyst.ask_provider('test', work, 'claude', '')
        self.assertFalse(self.store.tickets)

    def test_subprocess_runner_returns_output(self):
        analyst = Analyst(self.store, {}, print, lambda *_: None)
        result = analyst.run_provider([sys.executable, '-c', 'import sys; print(sys.stdin.read())'], 'hello', self.root)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), 'hello')
        self.assertIsNone(analyst.process)

    def test_malformed_arrival_records_do_not_break_discovery(self):
        log = self.root / 'inbox.jsonl'
        log.write_text('[]\n{"file":"../secret.mp4"}\n{"file":33}\n{"file":"Game/ok.mp4"}\n{')
        self.assertEqual(self.store.sync_inbox(), 1)
        self.assertEqual(self.store.next_queued(), 'Game/ok.mp4')

    def test_http_host_origin_range_and_settings(self):
        # Bind first so the allowed host uses the actual ephemeral port.
        server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(self.store, 0))
        port = server.server_port
        server.RequestHandlerClass = make_handler(self.store, port)
        thread = threading.Thread(target=server.serve_forever); thread.start()
        base = f'http://127.0.0.1:{port}'
        try:
            (self.root / 'clip.mp4').write_bytes(b'0123456789')
            req = Request(base + '/media/clip.mp4', headers={'Range': 'bytes=2-4'})
            with urlopen(req) as r:
                self.assertEqual((r.status, r.read()), (206, b'234'))
            for url in ['/media/../outside', '/media/%2e%2e/outside']:
                with self.assertRaises(HTTPError) as ctx: urlopen(base + url)
                ctx.exception.close()
            req = Request(base + '/api/settings', data=b'{"provider":"codex"}', headers={'Content-Type': 'application/json', 'Origin': 'http://evil.test'})
            with self.assertRaises(HTTPError) as ctx: urlopen(req)
            self.assertEqual(ctx.exception.code, 403)
            ctx.exception.close()
            req = Request(base + '/api/settings', data=b'{"provider":"codex","model":"test"}', headers={'Content-Type': 'application/json', 'Origin': base})
            with urlopen(req) as r: self.assertTrue(json.load(r)['ok'])
            req = Request(base + '/api/settings', data=b'[]', headers={'Content-Type': 'application/json'})
            with self.assertRaises(HTTPError) as ctx: urlopen(req)
            self.assertEqual(ctx.exception.code, 400)
            ctx.exception.close()
        finally:
            server.shutdown(); thread.join(); server.server_close()

if __name__ == '__main__':
    unittest.main()
