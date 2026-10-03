"""LOCAL-BECAUSE: credentials. Owner-authorized synthetic free-only experiment.

Collection only; NEVER execute returned source here. Paid tags are refused.
"""
import fcntl
import hashlib
import json
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LIST_HASH = '01a4e1c63a82ee48dee3c610f25ed56d7b39028a050305ae02cd4ca118137f3c'
MODEL = 'stealth/space-bunny-alpha'
ENV = Path('/Users/maxzipperman/code/value-finder/.env')
OUT = ROOT / 'openrouter-space-bunny-alpha'


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise RuntimeError('redirect refused')


def key_from_file():
    values = []
    for line in ENV.read_text().splitlines():
        match = re.match(r'^\s*(?:export\s+)?OPENROUTER_API_KEY\s*=\s*(.*?)\s*$', line)
        if match:
            value = match[1]
            if value[:1] in ('"', "'") and value[-1:] == value[:1]:
                value = value[1:-1]
            else:
                value = value.split(' #', 1)[0].strip()
            values.append(value)
    if len(values) != 1 or not values[0] or any(c.isspace() for c in values[0]):
        raise RuntimeError('one valid OPENROUTER_API_KEY required')
    return values[0]


def main(request_file='openrouter-requests.json', list_hash=LIST_HASH, output='openrouter-space-bunny-alpha', count=7, token_cap=8192):
    out = ROOT / output
    raw = (ROOT / request_file).read_bytes()
    if hashlib.sha256(raw).hexdigest() != list_hash:
        raise RuntimeError('request list changed; review required')
    entries = [item for item in json.loads(raw)['requests'] if item['model'] == MODEL]
    assert len(entries) == count
    for item in entries:
        body = item['body']
        assert body['model'] == MODEL and set(body) == {'model', 'messages', 'stream', 'temperature', 'max_tokens', 'reasoning', 'provider'}
        assert body['provider']['max_price'] == {'prompt': 0, 'completion': 0, 'request': 0, 'image': 0}
        assert body['provider']['allow_fallbacks'] is False and body['max_tokens'] == token_cap
    out.mkdir(exist_ok=True)
    key = key_from_file()
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())

    def call(path, body=None, auth=False, timeout=30):
        assert path in ('/api/v1/models', '/api/v1/chat/completions')
        headers = {'Content-Type': 'application/json'}
        if auth:
            headers['Authorization'] = 'Bearer ' + key
        request = urllib.request.Request('https://openrouter.ai' + path, data=None if body is None else json.dumps(body).encode(), headers=headers)
        with opener.open(request, timeout=timeout) as response:
            data = response.read(4_000_001)
            if len(data) > 4_000_000:
                raise RuntimeError('response size limit')
            return json.loads(data.decode().replace(key, '[REDACTED]'))

    with (ROOT / 'openrouter-space-bunny-alpha' / '.collection.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | (fcntl.LOCK_NB if count == 7 else 0))
        except BlockingIOError:
            print(json.dumps({'status': 'busy'}), flush=True)
            return
        for item in entries:
            task = item['task']
            prefix = out / task
            # A saved request without a terminal artifact is an uncertain attempt.
            if any(Path(str(prefix) + suffix).exists() for suffix in ('-request.json', '-result.json', '-error.json')):
                continue
            catalog = call('/api/v1/models')
            model = next((m for m in catalog['data'] if m['id'] == MODEL), None)
            if model is None or model.get('canonical_slug') != MODEL:
                print(json.dumps({'status': 'model_missing_or_changed'}), flush=True)
                return
            prices = model.get('pricing', {})
            if not {'prompt', 'completion'} <= set(prices) or any(float(value) != 0 for value in prices.values()):
                print(json.dumps({'status': 'not_free'}), flush=True)
                return
            Path(str(prefix) + '-catalog.json').write_text(json.dumps(model, indent=2) + '\n')
            Path(str(prefix) + '-request.json').write_text(json.dumps(item, indent=2) + '\n')
            start = time.monotonic()
            try:
                result = call('/api/v1/chat/completions', item['body'], auth=True, timeout=item['deadline_seconds'])
                result['wall_seconds'] = time.monotonic() - start
                Path(str(prefix) + '-result.json').write_text(json.dumps(result, indent=2) + '\n')
                if 'error' in result or result.get('model') != MODEL:
                    raise RuntimeError('upstream error or unexpected response model; stop')
                cost = result.get('usage', {}).get('cost')
                if cost is None or float(cost) != 0:
                    raise RuntimeError('missing or nonzero billed cost; stop')
                answer = result['choices'][0]['message'].get('content') or ''
                if not isinstance(answer, str):
                    raise RuntimeError('nontext response')
                Path(str(prefix) + '-response.txt').write_text(answer)
                print(json.dumps({'task': task, 'status': 'collected', 'cost': cost, 'seconds': result['wall_seconds'], 'finish': result['choices'][0].get('finish_reason')}), flush=True)
            except Exception as exc:
                error = {'type': type(exc).__name__, 'wall_seconds': time.monotonic() - start}
                if isinstance(exc, urllib.error.HTTPError):
                    error['http_status'] = exc.code
                    error['body'] = exc.read(8192).decode(errors='replace').replace(key, '[REDACTED]')
                else:
                    error['message'] = str(exc).replace(key, '[REDACTED]')
                Path(str(prefix) + '-error.json').write_text(json.dumps(error, indent=2) + '\n')
                print(json.dumps({'task': task, 'status': 'stopped', 'type': error['type'], 'http_status': error.get('http_status')}), flush=True)
                return
        print(json.dumps({'status': 'collection_complete'}), flush=True)


if __name__ == '__main__':
    main()
