"""Read model capabilities from installed CLIs, without sending an inference prompt."""
import json
import os
import queue
import shutil
import subprocess
import tempfile
import threading
import time

_CACHE = {}
_LOCKS = {p: threading.Lock() for p in ('claude', 'codex')}


def catalog(provider, refresh=False):
    if provider not in _LOCKS:
        raise ValueError('Choose Claude Code or Codex CLI')
    with _LOCKS[provider]:
        cached = _CACHE.get(provider)
        if cached and not refresh and time.monotonic() - cached[0] < 300:
            return cached[1]
        try:
            result = {'models': discover(provider), 'source': provider + ' CLI', 'error': None}
        except (OSError, ValueError, KeyError, TypeError, RuntimeError, subprocess.SubprocessError) as exc:
            result = {'models': [], 'source': provider + ' CLI', 'error': str(exc)}
        _CACHE[provider] = (time.monotonic(), result)
        return result


def discover(provider):
    binary = shutil.which(provider)
    if not binary:
        raise RuntimeError(f'{provider} is not installed. Install it and sign in, then refresh.')
    cmd = [binary, 'app-server'] if provider == 'codex' else [binary, '-p', '--input-format', 'stream-json',
        '--output-format', 'stream-json', '--verbose', '--no-session-persistence', '--strict-mcp-config',
        '--setting-sources', '', '--tools', '', '--disable-slash-commands']
    env = dict(os.environ)
    env.pop('CLAUDECODE', None)
    with tempfile.TemporaryDirectory(prefix='qaclip-models-') as cwd:
        p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                             text=True, cwd=cwd, env=env)
        lines = queue.Queue()
        def reader():
            for line in p.stdout:
                lines.put(line)
            lines.put(None)
        thread = threading.Thread(target=reader, daemon=True)
        thread.start()
        def send(obj):
            p.stdin.write(json.dumps(obj) + '\n')
            p.stdin.flush()
        try:
            send({'id': 1, 'method': 'initialize', 'params': {'clientInfo': {'name': 'qa-clip', 'version': '0.3.0'}}}
                 if provider == 'codex' else {'type': 'control_request', 'request_id': 'models', 'request': {'subtype': 'initialize'}})
            deadline, models = time.monotonic() + 25, []
            while time.monotonic() < deadline:
                try:
                    line = lines.get(timeout=max(.01, deadline - time.monotonic()))
                except queue.Empty:
                    break
                if line is None:
                    break
                try:
                    obj = json.loads(line)
                except ValueError:
                    continue
                if obj.get('error'):
                    raise RuntimeError('The CLI could not list models. Check its sign-in and refresh.')
                if provider == 'codex':
                    if obj.get('id') == 1:
                        send({'method': 'initialized'})
                        send({'id': 2, 'method': 'model/list', 'params': {'limit': 100, 'includeHidden': False}})
                    elif obj.get('id') == 2:
                        result = obj.get('result', {})
                        models.extend(result.get('data', []))
                        if result.get('nextCursor'):
                            send({'id': 2, 'method': 'model/list', 'params': {'limit': 100, 'cursor': result['nextCursor']}})
                        else:
                            return normalize(provider, models)
                elif obj.get('type') == 'control_response':
                    response = obj.get('response', {})
                    if response.get('subtype') == 'error':
                        raise RuntimeError('Claude could not list models. Update Claude Code and refresh.')
                    return normalize(provider, response.get('response', {}).get('models', []))
            raise RuntimeError('Model discovery timed out. Check the CLI is signed in, then refresh.')
        finally:
            if p.poll() is None:
                p.terminate()
            try:
                p.wait(timeout=3)
            except subprocess.TimeoutExpired:
                p.kill()
                p.wait()
            thread.join(timeout=1)
            p.stdin.close()
            p.stdout.close()


def normalize(provider, models):
    result = []
    for m in models:
        if provider == 'codex':
            if m.get('hidden') or 'image' not in m.get('inputModalities', ['text', 'image']):
                continue
            result.append({'id': m['model'], 'name': m['displayName'], 'description': m.get('description', ''),
                           'efforts': [e['reasoningEffort'] for e in m.get('supportedReasoningEfforts', [])],
                           'defaultEffort': m.get('defaultReasoningEffort', '')})
        else:
            result.append({'id': m['value'], 'name': m['displayName'], 'resolved': m.get('resolvedModel', ''),
                           'description': m.get('description', ''),
                           'efforts': m.get('supportedEffortLevels', []) if m.get('supportsEffort') else [], 'defaultEffort': ''})
    if not result:
        raise RuntimeError('The CLI returned no vision models. Update it or check your account.')
    return result


def validate_effort(provider, model, effort):
    if not effort:
        return
    if not all(isinstance(v, str) for v in (provider, model, effort)) or provider not in _LOCKS:
        raise ValueError('Choose a provider, model and supported effort level')
    entry = next((m for m in catalog(provider)['models'] if m['id'] == model), None)
    if not entry or effort not in entry['efforts']:
        raise ValueError('Select a listed model and one of its supported effort levels, or use CLI default effort.')
