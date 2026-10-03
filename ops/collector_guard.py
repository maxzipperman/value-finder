"""Collector-only GET admission. No authority/bootstrap/recovery is created here.

All participating account writers must use the same ledger + .lock contract.
The hub must supply a reviewed, hash-pinned live envelope and initialized ledger.
A missing/uncertain attempt halts admission; reservations are never released here.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import logging
import os
import re
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit, quote, quote_plus

ROOT = Path(__file__).resolve().parent.parent
LABELS = {'nfl-trigger', 'cfb-trigger', 'nfl-props', 'nba'}


class Blocked(RuntimeError):
    pass


_SECRETS = set()


def redact(text):
    for secret in sorted(_SECRETS, key=len, reverse=True):
        text = str(text).replace(secret, 'REDACTED')
    return text


class SecretFilter(logging.Filter):
    def filter(self, record):
        record.msg, record.args = redact(record.getMessage()), ()
        if record.exc_info:
            record.exc_text = redact(logging.Formatter().formatException(record.exc_info))
            record.exc_info = None
        if record.exc_text:
            record.exc_text = redact(record.exc_text)
        return True


def protect_logs(key):
    _SECRETS.update({key, quote(key, safe=''), quote_plus(key)})
    for name in ('requests', 'urllib3', 'urllib3.connection', 'urllib3.connectionpool',
                 'urllib3.poolmanager', 'urllib3.response'):
        logger = logging.getLogger(name)
        if not any(isinstance(f, SecretFilter) for f in logger.filters):
            logger.addFilter(SecretFilter())


def digest(data):
    return hashlib.sha256(data).hexdigest()


def atomic_json(path, value):
    """Replace + fsync file and parent; errors propagate before another send."""
    path = Path(path)
    fd, name = tempfile.mkstemp(prefix=path.name + '.', dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as f:
            json.dump(value, f, sort_keys=True)
            f.flush()
            os.fsync(f.fileno())
        os.replace(name, path)
        fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def utc(value):
    t = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if t.tzinfo is None or t.utcoffset().total_seconds() != 0:
        raise ValueError('UTC required')
    return t


def integer(value):
    if type(value) is not int or value < 0:
        raise ValueError('Nonnegative integer required')
    return value


def source_sha():
    if subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=no'], cwd=ROOT).strip():
        raise Blocked('Collector source is dirty')
    return subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()


def envelope(now):
    path = os.environ.get('VF_COLLECTOR_ENVELOPE')
    expected = os.environ.get('VF_COLLECTOR_ENVELOPE_SHA256', '')
    if not path or not re.fullmatch('[0-9a-f]{64}', expected):
        raise Blocked('Approved live envelope/shared-account bridge absent')
    try:
        if not Path(path).is_absolute():
            raise ValueError('Absolute envelope path required')
        raw = Path(path).read_bytes()
        if digest(raw) != expected:
            raise ValueError('Envelope hash changed/revoked')
        c = json.loads(raw)
        if set(c) != {'version', 'source_sha', 'approval', 'month', 'valid_until_utc',
                     'account_fingerprint', 'account_ceiling', 'plan_credits', 'reserve_floor',
                     'ledger', 'shared_writers', 'collectors'} or type(c['version']) is not int or c['version'] != 1:
            raise ValueError('Envelope schema')
        if c['source_sha'] != source_sha() or not re.fullmatch('[0-9a-f]{40}', c['source_sha']):
            raise ValueError('Executing commit differs')
        if not isinstance(c['approval'], str) or not c['approval'].strip():
            raise ValueError('Approval reference absent')
        if c['month'] != now.strftime('%Y-%m') or now >= utc(c['valid_until_utc']):
            raise ValueError('Authority expired')
        if not re.fullmatch('[0-9a-f]{12}', c['account_fingerprint']):
            raise ValueError('Account fingerprint')
        for k in ('account_ceiling', 'plan_credits', 'reserve_floor'):
            integer(c[k])
        if not 0 < c['account_ceiling'] <= c['plan_credits'] - c['reserve_floor']:
            raise ValueError('Account ceiling violates reserve')
        if not Path(c['ledger']).is_absolute():
            raise ValueError('Absolute shared ledger required')
        if not isinstance(c['shared_writers'], list) or not c['shared_writers'] or any(
                not isinstance(w, str) or not w for w in c['shared_writers']):
            raise ValueError('Shared writer inventory absent')
        if set(c['collectors']) != LABELS:
            raise ValueError('Collector inventory')
        for scope in c['collectors'].values():
            if set(scope) != {'cap', 'path_pattern', 'params'} or integer(scope['cap']) == 0:
                raise ValueError('Finite scope/cap required')
            if set(scope['params']) != {'bookmakers', 'markets', 'oddsFormat', 'dateFormat'}:
                raise ValueError('Exact request params required')
            if any(not isinstance(v, str) or not v for v in scope['params'].values()):
                raise ValueError('Invalid request params')
            re.compile(scope['path_pattern'])
        return c, expected
    except (OSError, ValueError, TypeError, KeyError, subprocess.SubprocessError) as e:
        raise Blocked('Invalid collector envelope: ' + type(e).__name__) from None


def slot(now, seconds):
    """UTC wall-clock window identity, stable across a crash/restart in the window."""
    return str(int(now.timestamp()) // seconds)


class Response:
    """Minimal sanitized response; carries no authenticated request/URL/exception."""
    def __init__(self, receipt):
        self.status_code = receipt["status"]
        self.headers = receipt["headers"]
        self.text = receipt["body"]
        self.ok = 200 <= self.status_code < 400

    def json(self):
        return json.loads(self.text)


def paid_get(session, url, params, *, label, request_slot, now=None):
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    c, identity = envelope(now)
    try:
        key = params['apiKey']
        if digest(key.encode())[:12] != c['account_fingerprint']:
            raise ValueError('Account differs')
        parsed = urlsplit(url)
        scope = c['collectors'][label]
        public = {k: v for k, v in params.items() if k != 'apiKey'}
        if (parsed.scheme != 'https' or parsed.netloc != 'api.the-odds-api.com' or parsed.query or
                parsed.fragment or not re.fullmatch(scope['path_pattern'], parsed.path) or public != scope['params']):
            raise ValueError('Request outside exact approved scope')
        if not isinstance(request_slot, str) or not request_slot:
            raise ValueError('Stable slot required')
        # Guard only known live endpoints; a scope cannot admit historical/order requests.
        if not re.fullmatch(r'/v4/sports/(americanfootball_nfl|americanfootball_ncaaf|basketball_nba)/(events/[^/]+/)?odds', parsed.path):
            raise ValueError('Not a named live GET endpoint')
        books, markets = public['bookmakers'].split(','), public['markets'].split(',')
        if len(set(books)) != len(books) or len(set(markets)) != len(markets) or '' in books + markets:
            raise ValueError('Invalid market/book list')
        cost = len(markets) * ((len(books) + 9) // 10)
        retry = session.get_adapter(url).max_retries
        if retry.total != 0:
            raise ValueError('Transport retries enabled')
    except (ValueError, KeyError, AttributeError, TypeError):
        raise Blocked('Collector request/transport not admitted') from None
    path = Path(c['ledger'])
    # No automatic initialization: a deleted ledger cannot reset cumulative spend.
    if not path.is_file() or not path.with_suffix(path.suffix + '.lock').is_file():
        raise Blocked('Shared ledger/lock missing; hub reconciliation required')
    protect_logs(key)
    attempt_id = digest((label + ':' + request_slot).encode())
    request_hash = digest(json.dumps([url, public], sort_keys=True).encode())
    with path.with_suffix(path.suffix + '.lock').open('r+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        # Revalidate mutable authority/revocation under the shared lock, before send.
        c2, identity2 = envelope(datetime.now(timezone.utc))
        if identity2 != identity or c2 != c:
            raise Blocked('Authority changed during admission')
        try:
            s = json.loads(path.read_text())
            if set(s) != {'version', 'envelope_sha256', 'baseline_used', 'external_reserved', 'external_state', 'attempts'} or type(s['version']) is not int or s['version'] != 1 or s['envelope_sha256'] != identity:
                raise ValueError('Ledger identity/schema')
            baseline = integer(s['baseline_used'])
            external = integer(s['external_reserved'])
            if s['external_state'] != 'ready':
                raise Blocked('Other account writer pending/uncertain; admission held')
            attempts = s['attempts']
            for a in attempts.values():
                if set(a) != {'label', 'slot', 'request_sha256', 'reserved', 'state', 'receipt_sha256'} or a['label'] not in LABELS:
                    raise ValueError('Attempt schema')
                integer(a['reserved'])
                if a['state'] != 'complete':
                    raise Blocked('Uncertain/failed attempt retained; hub reconciliation required')
            for aid, a in attempts.items():
                approved = c['collectors'][a['label']]['params']
                expected_cost = len(approved['markets'].split(',')) * ((len(approved['bookmakers'].split(',')) + 9) // 10)
                if (aid != digest((a['label'] + ':' + a['slot']).encode()) or a['reserved'] != expected_cost
                        or not isinstance(a['receipt_sha256'], str)
                        or not re.fullmatch('[0-9a-f]{64}', a['receipt_sha256'])
                        or not re.fullmatch('[0-9a-f]{64}', a['request_sha256'])):
                    raise ValueError('Receipt identity')
                saved = path.parent / (path.name + '.' + aid + '.receipt.json')
                if digest(saved.read_bytes()) != a['receipt_sha256']:
                    raise ValueError('Saved receipt changed/missing')
            if attempt_id in attempts:
                raise Blocked('Slot already reserved; never automatically resent')
            if baseline + external + sum(a['reserved'] for a in attempts.values()) + cost > c['account_ceiling']:
                raise Blocked('Shared cumulative ceiling/reserve reached')
            if sum(a['reserved'] for a in attempts.values() if a['label'] == label) + cost > scope['cap']:
                raise Blocked('Collector cumulative cap reached')
        except (OSError, ValueError, TypeError, KeyError):
            raise Blocked('Shared ledger invalid; no automatic repair') from None
        a = dict(label=label, slot=request_slot, request_sha256=request_hash,
                 reserved=cost, state='pending', receipt_sha256=None)
        attempts[attempt_id] = a
        atomic_json(path, s)  # durable BEFORE any HTTP; crash leaves pending reservation
        # Exactly one GET; errors propagate, leaving pending and the reservation intact.
        try:
            response = session.get(url, params=params, timeout=60, allow_redirects=False)
        except Exception as e:
            raise Blocked('Uncertain transport attempt: ' + type(e).__name__) from None
        headers = {k.lower(): redact(str(v)) for k, v in response.headers.items()}
        text = response.text
        for secret in sorted({key, quote(key, safe=''), quote_plus(key)}, key=len, reverse=True):
            text = text.replace(secret, 'REDACTED')
        receipt = dict(status=response.status_code,
                       headers={k: headers.get(k) for k in ('x-requests-last', 'x-requests-used', 'x-requests-remaining')},
                       body=text)
        receipt_path = path.parent / (path.name + '.' + attempt_id + '.receipt.json')
        atomic_json(receipt_path, receipt)  # retain ALL responses, including 429/redirect/error
        a['receipt_sha256'] = digest(receipt_path.read_bytes())
        try:
            def billed(k):
                v = headers[k]
                if not re.fullmatch(r'\d+', v):
                    raise ValueError('Missing/invalid billing')
                return int(v)
            last, used, remaining = (billed(k) for k in ('x-requests-last', 'x-requests-used', 'x-requests-remaining'))
            safe = (response.status_code == 200 and last <= cost and used <= c['account_ceiling']
                    and remaining >= c['reserve_floor'] and used + remaining == c['plan_credits']
                    and baseline <= used <= baseline + external + sum(a['reserved'] for a in attempts.values()))
        except (KeyError, ValueError):
            safe = False
        a['state'] = 'complete' if safe else 'failed'
        atomic_json(path, s)
        if not safe:
            raise Blocked('Response failed billing/status checks; reservation retained')
        return Response(receipt)
