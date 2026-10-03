"""Disabled shared-account recurring-writer GET admission. No authority/bootstrap/recovery is created here.

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
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urlsplit, quote, quote_plus
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
# One fixed account journal, not a caller-selectable ledger/lock domain. Synthetic
# tests replace this constant; production has no configuration switch for it.
ACCOUNT_LEDGER = Path.home() / 'Library/Application Support/ValueFinder/shared-account-state/journal.json'
ROLE_PATHS = {
    **{f'nfl-{role}': r'/v4/sports/americanfootball_nfl/odds' for role in ('alert', 'close', 'trigger')},
    **{f'cfb-{role}': r'/v4/sports/americanfootball_ncaaf/odds' for role in ('alert', 'close', 'trigger')},
    'nfl-props': r'/v4/sports/americanfootball_nfl/events/[^/]+/odds',
    'nba': r'/v4/sports/basketball_nba/odds',
}
LABELS = {'nfl-alert', 'cfb-alert', 'nfl-close', 'cfb-close',
          'nfl-trigger', 'cfb-trigger', 'nfl-props', 'nba'}


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
        if Path(path).is_symlink():
            raise ValueError('Symlink authority rejected')
        raw = Path(path).read_bytes()
        if digest(raw) != expected:
            raise ValueError('Envelope hash changed/revoked')
        c = json.loads(raw)
        if set(c) != {'version', 'source_sha', 'approval', 'month', 'valid_until_utc',
                     'account_fingerprint', 'account_ceiling', 'plan_credits', 'reserve_floor',
                     'ledger', 'shared_writers', 'roles'} or type(c['version']) is not int or c['version'] != 2:
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
        if Path(c['ledger']) != ACCOUNT_LEDGER or ACCOUNT_LEDGER.resolve() != ACCOUNT_LEDGER:
            raise ValueError('Canonical shared account journal required')
        if not isinstance(c['shared_writers'], list) or not c['shared_writers'] or any(
                not isinstance(w, str) or not w for w in c['shared_writers']):
            raise ValueError('Shared writer inventory absent')
        if set(c['shared_writers']) != LABELS or len(c['shared_writers']) != len(LABELS):
            raise ValueError('Exact recurring writer inventory required')
        if set(c['roles']) != LABELS:
            raise ValueError('Collector inventory')
        for scope in c['roles'].values():
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


ALERT_TIMEZONE = 'America/Los_Angeles'
ALERT_LOCAL_TIMES = ((7, 30), (11, 30), (15, 30), (19, 30))


def alert_occurrence(value, *, now=None):
    """Validate an explicit occurrence, never infer one from execution time.

    Syntax/calendar validation is NOT authenticated trigger provenance. A reviewed
    producer/binding is an activation prerequisite; the production hold remains.
    The token expires at the next approved LOCAL occurrence (including overnight
    and DST), so a delayed/coalesced ambiguous prior trigger cannot be guessed.
    This identity clock never replaces the response's actual observed quote clock.
    """
    try:
        if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:00Z', value):
            raise ValueError('Canonical explicit scheduled UTC occurrence required')
        occurrence = utc(value)
        now = now or datetime.now(timezone.utc)
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError('Aware decision clock required')
        now = now.astimezone(timezone.utc)
        zone = ZoneInfo(ALERT_TIMEZONE)
        local = occurrence.astimezone(zone)
        if (local.hour, local.minute) not in ALERT_LOCAL_TIMES or occurrence > now:
            raise ValueError('Not an approved past/current scheduled occurrence')
        following = min(
            datetime.combine(local.date()+timedelta(days=days), datetime.min.time(),zone)
            .replace(hour=hour,minute=minute).astimezone(timezone.utc)
            for days in (0,1) for hour,minute in ALERT_LOCAL_TIMES
            if datetime.combine(local.date()+timedelta(days=days),datetime.min.time(),zone)
            .replace(hour=hour,minute=minute).astimezone(timezone.utc) > occurrence)
        if now >= following:
            raise ValueError('Prior occurrence expired/ambiguous; trigger provenance required')
        return value
    except (ValueError, TypeError, KeyError):
        raise Blocked('Alert occurrence missing/invalid/ambiguous; reviewed trigger provenance required') from None


def close_slot(kickoff_slots, tries, now):
    """Identity for one scheduled close observation, independent of mutable selection/state.

    A next scheduled tick may observe again after a conclusive empty answer;
    pending/failed account state still blocks all later IDs before transport.
    This helper never decides eligibility or updates the registered try count.
    """
    return "close:" + slot(now, 900)


class Response:
    """Minimal sanitized response; carries no authenticated request/URL/exception."""
    def __init__(self, receipt, *, replayed=False):
        self.status_code = receipt["status"]
        self.headers = receipt["headers"]
        self.text = receipt["body"]
        self.ok = 200 <= self.status_code < 400
        self.observed_utc = receipt["observed_utc"]
        self.replayed = replayed

    def json(self):
        return json.loads(self.text)


def require_bridge():
    """Production admission is disabled until a reviewed enforcement bridge exists.

    No config flag, writer inventory, ledger state or approval string can lift this.
    A later implementation must enforce real writer coordination before changing it.
    """
    raise Blocked('Collector installation/send disabled: shared-account enforcement bridge not implemented')


def paid_get(session, url, params, *, label, request_slot, now=None):
    """Named production entry point. Intentionally unreachable transport in this PR."""
    require_bridge()
    return _reservation_get(session, url, params, label=label, request_slot=request_slot, now=now)


def _reservation_get(session, url, params, *, label, request_slot, now=None):
    """Source-only reservation primitive for synthetic tests/future bridge integration.

    Reachable through production entry only after a FUTURE reviewed hold removal.
    Tests alone may replace the hold. Envelope declarations are NOT coordination.
    """
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    c, identity = envelope(now)
    try:
        key = params['apiKey']
        if digest(key.encode())[:12] != c['account_fingerprint']:
            raise ValueError('Account differs')
        parsed = urlsplit(url)
        scope = c['roles'][label]
        public = {k: v for k, v in params.items() if k != 'apiKey'}
        if (parsed.scheme != 'https' or parsed.netloc != 'api.the-odds-api.com' or parsed.query or
                parsed.fragment or not re.fullmatch(scope['path_pattern'], parsed.path) or public != scope['params']):
            raise ValueError('Request outside exact approved scope')
        if label not in LABELS or not re.fullmatch(ROLE_PATHS[label], parsed.path):
            raise ValueError('Caller role/endpoint differs')
        if not isinstance(request_slot, str) or not request_slot:
            raise ValueError('Stable slot required')
        if label in {'nfl-alert', 'cfb-alert'}:
            alert_occurrence(request_slot, now=now)
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
    if (not path.is_file() or path.is_symlink()
            or not path.with_suffix(path.suffix + '.lock').is_file()
            or path.with_suffix(path.suffix + '.lock').is_symlink()):
        raise Blocked('Shared ledger/lock missing; hub reconciliation required')
    protect_logs(key)
    attempt_id = digest((label + ':' + request_slot).encode())
    request_hash = digest(json.dumps([url, public], sort_keys=True).encode())
    with path.with_suffix(path.suffix + '.lock').open('r+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if os.fstat(lock.fileno()).st_ino != path.with_suffix(path.suffix + '.lock').stat().st_ino:
            raise Blocked('Shared lock inode replaced; reconciliation required')
        if path.is_symlink() or path.with_suffix(path.suffix + '.lock').is_symlink() or path.resolve() != ACCOUNT_LEDGER:
            raise Blocked('Canonical journal/lock changed while waiting')
        # Revalidate mutable authority/revocation under the shared lock, before send.
        c2, identity2 = envelope(datetime.now(timezone.utc))
        if identity2 != identity or c2 != c:
            raise Blocked('Authority changed during admission')
        try:
            s = json.loads(path.read_text())
            if set(s) != {'version', 'envelope_sha256', 'baseline_used', 'external_reserved', 'external_state', 'attempts'} or type(s['version']) is not int or s['version'] != 2 or s['envelope_sha256'] != identity:
                raise ValueError('Ledger identity/schema')
            baseline = integer(s['baseline_used'])
            external = integer(s['external_reserved'])
            if s['external_state'] != 'ready':
                raise Blocked('Other account writer pending/uncertain; admission held')
            attempts = s['attempts']
            seen_used = baseline
            if not isinstance(attempts, dict):
                raise ValueError('Attempt map required')
            for a in attempts.values():
                if set(a) != {'label', 'slot', 'request_sha256', 'reserved', 'state', 'receipt_sha256'} or a['label'] not in LABELS:
                    raise ValueError('Attempt schema')
                integer(a['reserved'])
                if a['state'] != 'complete':
                    raise Blocked('Uncertain/failed attempt retained; hub reconciliation required')
            for aid, a in attempts.items():
                approved = c['roles'][a['label']]['params']
                expected_cost = len(approved['markets'].split(',')) * ((len(approved['bookmakers'].split(',')) + 9) // 10)
                if (aid != digest((a['label'] + ':' + a['slot']).encode()) or a['reserved'] != expected_cost
                        or not isinstance(a['receipt_sha256'], str)
                        or not re.fullmatch('[0-9a-f]{64}', a['receipt_sha256'])
                        or not re.fullmatch('[0-9a-f]{64}', a['request_sha256'])):
                    raise ValueError('Receipt identity')
                saved = path.parent / (path.name + '.' + aid + '.receipt.json')
                raw = saved.read_bytes()
                if saved.is_symlink() or digest(raw) != a['receipt_sha256']:
                    raise ValueError('Saved receipt changed/missing')
                receipt = json.loads(raw)
                if (set(receipt) != {'observed_utc', 'status', 'headers', 'body'}
                        or receipt['status'] != 200 or not isinstance(receipt['body'], str)
                        or utc(receipt['observed_utc']) > datetime.now(timezone.utc)):
                    raise ValueError('Saved receipt malformed/future')
                seen_used = max(seen_used, int(receipt['headers']['x-requests-used']))
            if attempt_id in attempts:
                prior = attempts[attempt_id]
                if prior['request_sha256'] != request_hash:
                    raise Blocked('Stable identity conflicts with saved request')
                saved = path.parent / (path.name + '.' + attempt_id + '.receipt.json')
                return Response(json.loads(saved.read_text()), replayed=True)
            if baseline + external + sum(a['reserved'] for a in attempts.values()) + cost > c['account_ceiling']:
                raise Blocked('Shared cumulative ceiling/reserve reached')
            if sum(a['reserved'] for a in attempts.values() if a['label'] == label) + cost > scope['cap']:
                raise Blocked('Collector cumulative cap reached')
        except (OSError, ValueError, TypeError, KeyError):
            raise Blocked('Shared ledger invalid; no automatic repair') from None
        c3, identity3 = envelope(datetime.now(timezone.utc))
        if c3 != c or identity3 != identity:
            raise Blocked('Authority changed before reservation')
        a = dict(label=label, slot=request_slot, request_sha256=request_hash,
                 reserved=cost, state='pending', receipt_sha256=None)
        attempts[attempt_id] = a
        atomic_json(path, s)  # durable BEFORE any HTTP; crash leaves pending reservation
        c4, identity4 = envelope(datetime.now(timezone.utc))
        if c4 != c or identity4 != identity:
            raise Blocked('Authority changed after reservation; retained pending')
        # Exactly one GET; errors propagate, leaving pending and the reservation intact.
        try:
            response = session.get(url, params=params, timeout=60, allow_redirects=False)
        except Exception as e:
            raise Blocked('Uncertain transport attempt: ' + type(e).__name__) from None
        headers = {k.lower(): redact(str(v)) for k, v in response.headers.items()}
        text = response.text
        for secret in sorted({key, quote(key, safe=''), quote_plus(key)}, key=len, reverse=True):
            text = text.replace(secret, 'REDACTED')
        receipt = dict(observed_utc=datetime.now(timezone.utc).isoformat(),
                       status=response.status_code,
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
                    and seen_used <= used <= baseline + external + sum(a['reserved'] for a in attempts.values()))
        except (KeyError, ValueError):
            safe = False
        a['state'] = 'complete' if safe else 'failed'
        atomic_json(path, s)
        if not safe:
            raise Blocked('Response failed billing/status checks; reservation retained')
        return Response(receipt)
