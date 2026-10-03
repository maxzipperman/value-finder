"""Owner-approved October3 paid synthetic requests; first-round cap $0.50.

Max explicitly waived hub approval and authorized up to $1 for tests.
This collector permits only the declared21 paid requests, never executes output.
"""
import fcntl
import hashlib
import json
import math
import time
import urllib.error
import urllib.request
from pathlib import Path
from openrouter_free import ROOT, LIST_HASH, NoRedirect, key_from_file

MODELS = {'deepseek/deepseek-v4.1-flash', 'z-ai/glm-5.3-flash', 'xiaomi/mimo-v2.6-flash'}
OUT = ROOT / 'openrouter-paid'
CAP = 0.50


def number(value):
    if isinstance(value, bool):
        raise RuntimeError('invalid billing value')
    result = float(value)
    if not math.isfinite(result) or result < 0:
        raise RuntimeError('invalid billing value')
    return result


def reservation(item):
    body = item['body']
    prices = body['provider']['max_price']
    # UTF8-byte upper estimate + framing allowance, no cache discount.
    return ((len(body['messages'][0]['content'].encode()) + 256) * prices['prompt'] + body['max_tokens'] * prices['completion']) / 1_000_000


def main():
    raw = (ROOT / 'openrouter-requests.json').read_bytes()
    if hashlib.sha256(raw).hexdigest() != LIST_HASH:
        raise RuntimeError('request list changed; review required')
    entries = [x for x in json.loads(raw)['requests'] if x['model'] in MODELS]
    assert len(entries) == 21 and sum(reservation(x) for x in entries) < CAP
    for item in entries:
        body = item['body']
        assert body['model'] == item['model'] and set(body) == {'model', 'messages', 'stream', 'temperature', 'max_tokens', 'reasoning', 'provider', 'seed'}
        assert body['max_tokens'] == 8192 and body['seed'] == 42 and body['temperature'] == 0
        assert body['provider']['allow_fallbacks'] is False and body['provider']['require_parameters'] is True
        assert body['provider']['max_price']['request'] == body['provider']['max_price']['image'] == 0
    OUT.mkdir(exist_ok=True)
    if any(OUT.glob('*/*-error.json')):
        print(json.dumps({'status': 'saved_error_requires_review'}), flush=True)
        return
    key = key_from_file()
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())

    def call(path, body=None, auth=False, timeout=30):
        assert path in ('/api/v1/key', '/api/v1/credits', '/api/v1/models', '/api/v1/chat/completions')
        headers = {'Content-Type': 'application/json'}
        if auth:
            headers['Authorization'] = 'Bearer ' + key
        request = urllib.request.Request('https://openrouter.ai' + path, data=None if body is None else json.dumps(body).encode(), headers=headers)
        with opener.open(request, timeout=timeout) as response:
            data = response.read(4_000_001)
            if len(data) > 4_000_000:
                raise RuntimeError('response size limit')
            return json.loads(data.decode().replace(key, '[REDACTED]'))

    def billing():
        credits = call('/api/v1/credits', auth=True)['data']
        usage = call('/api/v1/key', auth=True)['data']
        return {'account_usage': number(credits['total_usage']), 'account_credits': number(credits['total_credits']), 'key_usage': number(usage['usage'])}

    # Share the free collector's lock: no competing OpenRouter inference.
    with (ROOT / 'openrouter-space-bunny-alpha' / '.collection.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        free = ROOT / 'openrouter-space-bunny-alpha'
        if not (free / 'hard-review-result.json').exists() and not any(free.glob('*-error.json')):
            print(json.dumps({'status': 'free_round_incomplete'}), flush=True)
            return
        ledger_path = OUT / 'billing.json'
        ledger = json.loads(ledger_path.read_text()) if ledger_path.exists() else {'cap_usd': CAP, 'owner_cap_usd': 1, 'list_sha256': LIST_HASH, 'initial': billing(), 'attempts': []}
        if ledger['list_sha256'] != LIST_HASH or ledger['cap_usd'] != CAP:
            raise RuntimeError('billing ledger mismatch')
        if any(x['status'] != 'completed' for x in ledger['attempts']):
            print(json.dumps({'status': 'uncertain_attempt_requires_review'}), flush=True)
            return
        ledger_path.write_text(json.dumps(ledger, indent=2) + '\n')
        for item in entries:
            folder = OUT / item['model'].replace('/', '--')
            folder.mkdir(exist_ok=True)
            prefix = folder / item['task']
            if any(Path(str(prefix) + suffix).exists() for suffix in ('-request.json', '-result.json', '-error.json')):
                continue
            model = next((m for m in call('/api/v1/models')['data'] if m['id'] == item['model']), None)
            frozen = next(m for m in json.loads((ROOT / 'openrouter-inventory.json').read_text()) if m['id'] == item['model'])
            if model is None or model['canonical_slug'] != frozen['canonical_slug']:
                raise RuntimeError('checkpoint changed or missing')
            costs = model.get('pricing', {})
            if not {'prompt', 'completion'} <= set(costs):
                raise RuntimeError('missing token prices')
            for name, value in costs.items():
                ceiling = item['body']['provider']['max_price'].get(name, item['body']['provider']['max_price']['prompt'] if name == 'input_cache_read' else 0)
                if number(value) * 1_000_000 > ceiling:
                    raise RuntimeError('catalog price exceeds approved ceiling')
            before = billing()
            reserved = sum(number(a['accounted_usd']) for a in ledger['attempts'])
            amount = reservation(item)
            # Balance/delta are separate alarms, not additions to billed usage.
            if reserved + amount > CAP or before['account_credits'] - before['account_usage'] < amount:
                raise RuntimeError('budget or balance stop')
            if before['account_usage'] - ledger['initial']['account_usage'] > reserved + 0.01:
                raise RuntimeError('account usage exceeds counted attempts; review required')
            attempt = {'model': item['model'], 'task': item['task'], 'status': 'reserved', 'maximum_estimate_usd': amount, 'accounted_usd': amount, 'before': before}
            ledger['attempts'].append(attempt)
            ledger_path.write_text(json.dumps(ledger, indent=2) + '\n')
            Path(str(prefix) + '-request.json').write_text(json.dumps(item, indent=2) + '\n')
            Path(str(prefix) + '-catalog.json').write_text(json.dumps(model, indent=2) + '\n')
            start = time.monotonic()
            try:
                result = call('/api/v1/chat/completions', item['body'], auth=True, timeout=item['deadline_seconds'])
                result['wall_seconds'] = time.monotonic() - start
                Path(str(prefix) + '-result.json').write_text(json.dumps(result, indent=2) + '\n')
                if 'error' in result or result.get('model') not in (item['model'], frozen['canonical_slug']):
                    raise RuntimeError('upstream error or unexpected response model')
                cost = number(result['usage']['cost'])
                attempt['reported_usd'] = cost
                attempt['accounted_usd'] = max(cost, amount)
                if cost > amount + 1e-8 or sum(a['accounted_usd'] for a in ledger['attempts']) > CAP:
                    raise RuntimeError('reported cost exceeds reservation or cap')
                answer = result['choices'][0]['message'].get('content') or ''
                if not isinstance(answer, str):
                    raise RuntimeError('nontext response')
                Path(str(prefix) + '-response.txt').write_text(answer)
                attempt['after'] = billing()
                if attempt['after']['account_usage'] - ledger['initial']['account_usage'] > sum(a['accounted_usd'] for a in ledger['attempts']) + 0.01:
                    raise RuntimeError('account usage exceeds counted attempts')
                attempt['status'] = 'completed'
                ledger_path.write_text(json.dumps(ledger, indent=2) + '\n')
                print(json.dumps({'model': item['model'], 'task': item['task'], 'cost': cost, 'seconds': result['wall_seconds'], 'finish': result['choices'][0].get('finish_reason')}), flush=True)
            except Exception as exc:
                error = {'type': type(exc).__name__, 'wall_seconds': time.monotonic() - start}
                if isinstance(exc, urllib.error.HTTPError):
                    error['http_status'] = exc.code
                    error['body'] = exc.read(8192).decode(errors='replace').replace(key, '[REDACTED]')
                else:
                    error['message'] = str(exc).replace(key, '[REDACTED]')
                attempt['status'] = 'stopped'
                Path(str(prefix) + '-error.json').write_text(json.dumps(error, indent=2) + '\n')
                ledger_path.write_text(json.dumps(ledger, indent=2) + '\n')
                print(json.dumps({'status': 'stopped', 'type': error['type'], 'http_status': error.get('http_status')}), flush=True)
                return
        print(json.dumps({'status': 'collection_complete', 'reported_usd': sum(a.get('reported_usd', 0) for a in ledger['attempts']), 'accounted_usd': sum(a['accounted_usd'] for a in ledger['attempts'])}), flush=True)


if __name__ == '__main__':
    main()
