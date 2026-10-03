"""Read-only operational display. No imports of executors, raw quotes or credentials.

Journal figures are reported metadata, not receipt verification or paid authority.
Do not sum predecessor carry, reused responses, reservations and observed charges.
"""
from __future__ import annotations

import json
import os
import re
import stat
from datetime import datetime, timezone
from pathlib import Path

from . import words, status_md
from .readers import Read, Refused, refuse

UTC = timezone.utc
QUEUE = 'STATUS.md'
MAX_BYTES = 20_000_000
MAX_BATCHES = 128
ROOT_ID = re.compile(r'^[a-f0-9]{64}$')
# Labels only: never authorize or select acquisition requests by these prefixes.
LABELS = {
    '4468a94c2b': 'Recent football 2023–2025',
    'cbe125474a': 'NFL alternates · pilot',
    '059fc135b0': 'NFL alternates · original batch',
    '4053703d09': 'NFL alternates · recovery 1',
    '7485bc1230': 'NFL alternates · recovery 2',
    'f955f28b2f': 'NFL 2025 props',
    '03391fd2c0': 'Older football · original batch',
    'f499935c05': 'Coverage pilot · original batch',
    'f490e0daae': 'Coverage pilot · successor',
    'c75ef924f5': 'Passing coverage groups · original batch',
    'c7d3ea3d93': 'Passing coverage groups · successor',
}
COMPLETE = {'event_epoch_complete', 'pilot_complete', 'recent_complete_stopped_before_older',
            'older_epoch_complete', 'metadata_complete'}
RECONCILED = {'event_epoch_partial_reconciled', 'older_epoch_partial_reconciled', 'pilot_partial_reconciled'}


def bounded(path: Path) -> Read:
    """Fixed local inputs only; reject links including ancestor links and oversized files."""
    try:
        p = refuse(path)
        if any(x.is_symlink() for x in (p, *p.parents)):
            return Read(note='Linked source refused.')
        # Reject known devices/pipes before open; then validate the actual descriptor
        # as well, since the path can be replaced between the check and open.
        if not stat.S_ISREG(p.lstat().st_mode):
            return Read(note='Nonregular source refused.')
        fd = os.open(p, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
        with os.fdopen(fd, 'rb') as f:
            actual = os.fstat(f.fileno())
            if not stat.S_ISREG(actual.st_mode):
                return Read(note='Nonregular source refused.')
            stamp = actual.st_mtime
            raw = f.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            return Read(note='Source exceeds the display size limit.')
        return Read(data=raw.decode('utf-8'), mtime=stamp)
    except (OSError, ValueError, Refused):
        return Read(note='Source is missing or unreadable.')


def freshness(name, at, now, tz, hours=24, kind='Recorded at'):
    age = (now - at).total_seconds() if at else None
    state = 'unknown' if age is None else 'future' if age < -300 else 'stale' if age > hours * 3600 else 'current'
    return {'name': name, 'state': state, 'at': words.when_full(at, tz) if at else 'Not recorded',
            'utc': words.iso_z(at), 'kind': kind,
            'note': {'unknown': 'Freshness not established', 'future': 'Timestamp is ahead of this Mac',
                     'stale': 'Older than the display freshness window; verify before relying on it',
                     'current': 'Within the display freshness window'}[state]}


def document(path, name, now, tz):
    r = bounded(path)
    # File checkout/mtime is not evidence that the facts were reviewed today.
    m = re.search(r'Updated\s+([A-Za-z]+ \d{1,2}, \d{4})', r.data or '', re.I)
    at = None
    if m:
        try:
            at = datetime.strptime(m[1], '%B %d, %Y').replace(tzinfo=tz)
        except ValueError:
            pass
    fresh = freshness(name, at, now, tz, 48, 'Document’s declared update date')
    if at:
        fresh["at"] = at.strftime("%b %d, %Y")
    return r, fresh


def queue_rows(text):
    """Only the adopted three-column Paid data table in STATUS is a queue."""
    body = status_md.section(text, 'Paid data — sole current queue')
    if not body:
        body = status_md.section(text, 'Paid data')
    out = []
    expected = ['Order', 'State / next action', 'Maximum new credits / authority']
    recognized = False
    for line in body.splitlines():
        if not line.startswith('|'):
            recognized = False
            continue
        cols = [words.scrub(words.strip_markdown(x.strip())) for x in line.strip().strip('|').split('|')]
        if cols == expected:
            recognized = True
            continue
        if not recognized or len(cols) != 3 or re.fullmatch(r'[-: ]+', cols[0]):
            continue
        state = 'blocked' if cols[0].lower() == 'held' else 'queued'
        # Preserve the whole action/authority text, including held-cohort restrictions.
        out.append(dict(order=cols[0], name=cols[1], cap=cols[2], detail='', state=state))
    return out


def owner_actions(text, now, tz):
    """Unknown classifications stay visible for review; explicit child choices survive
    resolved/reference parents. Decisions belong in the current Waiting on you section.
    """
    body = status_md.section(text, 'Waiting on you')
    # Flatten explicit nested choices into separate items before classifying parents.
    # Use stable compound IDs so children never share expansion state with the parent.
    lines, ids, parent, child = [], {}, None, 0
    occupied = [int(m[1]) for m in re.finditer(r'^(\d+)\.\s+\*\*', body, re.M)]
    next_id = max(occupied, default=0) + 1
    for line in body.splitlines():
        top = status_md.ITEM.match(line)
        nested = re.match(r'^\s+[-*]\s+(\*\*\[(?:open|review|resolved|reference)\].*)$', line, re.I)
        if top:
            parent, child = int(top[1]), 0
        if nested and parent is not None:
            child += 1
            ids[next_id] = f'{parent}.{child}'
            lines.append(f'{next_id}. {nested[1]}')
            next_id += 1
        else:
            lines.append(line)
    items = status_md.waiting_items('## Waiting on you\n' + '\n'.join(lines), now, tz)
    visible, unclassified = [], 0
    for item in items:
        m = re.match(r'\[(open|review|resolved|reference)\]\s*', item['title'], re.I)
        if not m:
            unclassified += 1
            item['action_state'] = 'review'
        else:
            item['action_state'] = m[1].lower()
            item['title'] = item['title'][m.end():]
        if item['action_state'] in {'resolved', 'reference'}:
            continue
        item['n'] = ids.get(item['n'], item['n'])
        # Preserve full decision context; first sentences can omit unresolved subchoices.
        if item['action_state'] == 'review':
            item['due'], item['due_iso'], item['due_level'] = 'Status needs review', None, 'warn'
        visible.append(item)
    return visible, unclassified


def integer(value):
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def acquisition(home, now, tz):
    base = home / 'Library/Application Support/ValueFinder/football-acquisition-state'
    rows, seen, notes = [], set(), []
    valid_total, latest = True, None
    if not base.is_dir():
        return {'batches': [], 'total': None, 'notes': ['Acquisition journals unavailable here; download state is unknown.'],
                'freshness': freshness('Acquisition journals', None, now, tz, kind='Last journal write')}
    paths = sorted(base.glob('*/spending-ledger.json'))
    if len(paths) > MAX_BATCHES:
        notes.append('Too many journals for a bounded display; totals withheld.')
        valid_total = False
    for path in paths[:MAX_BATCHES]:
        root = path.parent.name
        if not ROOT_ID.fullmatch(root):
            continue
        r = bounded(path)
        try:
            d = json.loads(r.data or '')
            if d.get('bundle_root_sha256') != root or not isinstance(d.get('attempts'), dict):
                raise ValueError('identity/schema')
            attempts = d['attempts']
            counts = {'completed': 0, 'missing': 0, 'pending': 0}
            billed, reserved, unknown_bill = 0, 0, 0
            for rid, a in attempts.items():
                if not ROOT_ID.fullmatch(rid) or not isinstance(a, dict) or a.get('status') not in counts:
                    raise ValueError('attempt schema')
                counts[a['status']] += 1
                if not integer(a.get('reserved_credits')):
                    raise ValueError('reservation')
                reserved += a['reserved_credits']
                if integer(a.get('billed_credits')):
                    billed += a['billed_credits']
                else:
                    unknown_bill += 1
            overlap = seen.intersection(attempts)
            if overlap:
                notes.append('Request identities overlap across journals; aggregate totals withheld to avoid double counting.')
                valid_total = False
            seen.update(attempts)
            state = d.get('status', '')
            status = ('completed' if state in COMPLETE and not counts['pending'] and not d.get('pending') else
                      'reconciled' if state in RECONCILED and not counts['pending'] and not d.get('pending') else
                      'blocked' if state == 'halted' else
                      'running (reported; liveness unverified)' if state == 'running' else
                      'queued' if state == 'prepared' else 'paused' if state == 'pilot_clean_pause' else 'unconfirmed')
            at = datetime.fromtimestamp(r.mtime, UTC) if r.mtime else None
            if at and (latest is None or at > latest):
                latest = at
            if at and at > now and (at - now).total_seconds() > 300:
                valid_total = False
                notes.append('An acquisition journal has a future timestamp; aggregate totals withheld.')
            rows.append({'name': LABELS.get(root[:10], 'Acquisition batch ' + root[:10]), 'root': root,
                         'state': status, 'recorded_state': words.scrub(str(state))[:100],
                         'requests': len(attempts), **counts, 'billed': billed, 'unknown_bill': unknown_bill,
                         'reserved': reserved, 'updated': words.when_full(at, tz), 'updated_utc': words.iso_z(at)})
        except (ValueError, TypeError, AttributeError, OverflowError):
            valid_total = False
            notes.append(f'Journal {root[:10]} could not be read; aggregate totals withheld.')
    rows.sort(key=lambda x: x['updated_utc'] or '', reverse=True)
    total = {k: sum(x[k] for x in rows) for k in ('requests', 'completed', 'missing', 'pending', 'billed', 'unknown_bill')} if valid_total and rows else None
    return {'batches': rows, 'total': total, 'notes': list(dict.fromkeys(notes)),
            'freshness': freshness('Acquisition journals', latest, now, tz, kind='Last journal write')}


def build(cfg, now):
    source = cfg.operations_root or cfg.root
    queue, qfresh = document(source / QUEUE, 'Download plan', now, cfg.tz)
    status, sfresh = queue, dict(qfresh, name='Owner decisions')
    actions, unclassified = owner_actions(status.data or '', now, cfg.tz)
    acquired = acquisition(cfg.home, now, cfg.tz)
    recorded = words.parse_utc(acquired['freshness'].get('utc', ''))
    plan_at = words.parse_utc(qfresh.get('utc', ''))
    if recorded and plan_at and recorded.astimezone(cfg.tz).date() > plan_at.astimezone(cfg.tz).date():
        qfresh.update(state='stale', note='Newer acquisition activity exists; this plan may be superseded')
        acquired['notes'].append('Acquisition records are newer than the plan date. Queued items may already have progressed; hub reconciliation is needed.')
    if not queue_rows(queue.data or ''):
        acquired['notes'].append('Canonical download queue missing or unrecognized; planned work is unknown.')
    return {**acquired, 'collector_outputs': collector_outputs(cfg.root), 'nba_start': str(nba_start(cfg.root) or ''), 'queue': queue_rows(queue.data or ''), 'actions': actions,
            'unclassified_actions': unclassified, 'plan_freshness': qfresh, 'action_freshness': sfresh,
            'queue_source': QUEUE, 'queue_url': 'https://github.com/maxzipperman/value-finder/blob/main/' + QUEUE + '#paid-data--sole-current-queue',
            'notes': acquired['notes'] + ([queue.note] if queue.note else []) + ([status.note] if status.note else [])}


def collector_outputs(root):
    """Only file metadata, never quote/player rows or the NBA database."""
    paths = {
        'com.valuefinder.triggerpoll': ['nfl-weather/data/forward/trigger_polls.csv', 'cfb-weather/data/forward/trigger_polls.csv'],
        'com.valuefinder.propslog': ['nfl-weather/data/forward/props_log.csv'],
        'com.valuefinder.nbacollector': ['sharp-markets/data/collector/nba/runs.csv'],
    }
    out = {}
    for label, files in paths.items():
        stamps = []
        for rel in files:
            p = root / rel
            try:
                if not any(x.is_symlink() for x in (p, *p.parents)) and p.is_file() and p.stat().st_size:
                    stamps.append(p.stat().st_mtime)
            except OSError:
                pass
        out[label] = max(stamps, default=None)
    return out


def nba_start(root):
    text = bounded(root / 'sharp-markets/config/sports/nba.yaml').data or ''
    # Restrict to this existing simple top-level YAML block; no arbitrary YAML evaluation.
    m = re.search(r'^collector:\s*\n((?:[ \t].*\n|\n)*)', text, re.M)
    start = re.search(r'^  start:\s*(\d{4}-\d{2}-\d{2})\s*(?:#.*)?$', m[1], re.M) if m else None
    if not start:
        return None
    try:
        return datetime.strptime(start[1], '%Y-%m-%d').date()
    except ValueError:
        return None
