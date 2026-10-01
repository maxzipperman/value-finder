"""Read-only bounded adapter for the acquired v4 store. Never edits/imports paid execution code.

Completion is tied to the independently audited report digest. This adapter is an analysis change;
it neither changes the frozen acquisition root nor enables registration or another purchase.
"""
from __future__ import annotations

import hashlib
import json
import os
import stat
from collections import defaultdict
from pathlib import Path

import ijson
import pyarrow.parquet as pq

ACQUIRED_ROOT = '4468a94c2b415cd5c53dd58163831f61d379ee44ec1b560f5a9b84be9c7f010d'
COMPLETED_REPORT_SHA256 = 'adb6c303948a18de52b9213bc2afacf7886213598ac3d64e05d45b3f7919d3e3'
CHUNK_BYTES = 1024 * 1024


def regular(path):
    fd = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0))
    if not stat.S_ISREG(os.fstat(fd).st_mode):
        os.close(fd)
        raise ValueError('Not a regular archive file')
    return os.fdopen(fd, 'rb')


def sha(path):
    digest = hashlib.sha256()
    with regular(path) as f:
        for chunk in iter(lambda: f.read(CHUNK_BYTES), b''):
            digest.update(chunk)
    return digest.hexdigest()


def coverage_header(path, root, expected_sha):
    if sha(path) != expected_sha:
        raise ValueError('Changed outcome-blind coverage report')
    wanted = {'bundle_root_sha256': root, 'outcomes_joined': False,
              'all_recent_requests_completed': True}
    # Prefix selection is performed in the C parser: large quote arrays are never materialized.
    # Three streaming passes trade CPU/I/O for a bounded memory footprint on the 9.26 GiB report.
    with regular(path) as f:
        for key, expected in wanted.items():
            f.seek(0)
            found = ijson.items(f, key, use_float=True)
            value = next(found, None)
            if value != expected or type(value) is not type(expected):
                raise ValueError('Incomplete or non-outcome-blind coverage header')
    return expected_sha


def canonical_context(bundle):
    ids = defaultdict(set)
    teams = {}
    for game in json.loads((bundle / 'canonical-games.json').read_text()):
        gid = game['canonical_game_id']
        teams[gid] = frozenset(game['team_keys'])
        for pid in game['provider_ids']:
            ids[game['sport'], pid].add(gid)
    bindings = {key: next(iter(values)) if len(values) == 1 else None for key, values in ids.items()}
    aliases = {(a['sport'], a['provider_name']): a['canonical_team_key']
               for a in json.loads((bundle / 'aliases.json').read_text())}
    return bindings, aliases, teams


def build_handoff(bundle, root, runtime, *, verify, validate_response, report_sha=COMPLETED_REPORT_SHA256):
    bundle, runtime = Path(bundle), Path(runtime)
    verify(bundle, root, check_cache=True)
    manifest = json.loads((bundle / 'request-manifest.json').read_text())
    protocol = json.loads((bundle / 'protocol.json').read_text())
    ledger = json.loads((runtime / 'spending-ledger.json').read_text())
    if (ledger['bundle_root_sha256'] != root or ledger['pending'] or ledger['stopped']
            or ledger['status'] != 'recent_complete_stopped_before_older'):
        raise ValueError('Completed recent ledger required')
    digest = coverage_header(runtime / 'coverage-report.json', root, report_sha)
    entries = []
    recent = [row for row in manifest['requests'] if row['priority'] == 1]
    paid_ids = {row['request_id'] for row in recent if row['max_new_credits']}
    if set(ledger['attempts']) != paid_ids:
        raise ValueError('Completed ledger differs from exact paid allowlist')
    for row in recent:
        rid = row['request_id']
        if not row['max_new_credits']:
            path, expected = bundle / row['cache_source'], row['cache_sha256']
            if ledger['cache_reuse'].get(rid) != expected:
                raise ValueError('Unreconciled probe response')
        else:
            attempt = ledger['attempts'][rid]
            receipt = runtime / 'receipts' / f'{rid}.json'
            if sha(receipt) != attempt['receipt_sha256']:
                raise ValueError('Changed response receipt')
            if attempt['status'] == 'missing':
                if attempt.get('response_path') and sha(attempt['response_path']) != attempt['response_sha256']:
                    raise ValueError('Changed missing-response evidence')
                entries.append({'request': row, 'status': 'accepted_missing',
                                'reason': attempt['missing_reason'], 'response_path': None,
                                'response_sha256': None})
                continue
            if attempt['status'] != 'completed':
                raise ValueError('Unresolved paid response')
            path, expected = Path(attempt['response_path']), attempt['response_sha256']
        if sha(path) != expected:
            raise ValueError('Changed response bytes')
        validate_response(row, pq.read_table(path).to_pylist()[0], protocol)
        entries.append({'request': row, 'response_path': str(path.resolve()), 'response_sha256': expected})
    return {'bundle_root_sha256': root, 'request_set_sha256': manifest['request_set_sha256'],
            'coverage_report_sha256': digest, 'scope': 'recent only; no outcome joins', 'entries': entries}


class ReadOnlyCache:
    """The original cache contract with streaming hashes and frozen canonical context."""
    def __init__(self, handoff, raw_dir, bundle):
        self.raw_dir, self.offline = Path(raw_dir), True
        self.index = {}
        for entry in handoff['entries']:
            if entry.get('status') == 'accepted_missing':
                continue
            row = entry['request']
            key = row['sport'], row['source'], row['cache_key']
            if key in self.index:
                raise ValueError('Duplicate handoff cache identity')
            self.index[key] = entry
        self.canonical_event_map, self.canonical_team_aliases, self.canonical_game_teams = canonical_context(Path(bundle))

    def lookup(self, sport, source, key):
        entry = self.index.get((sport, source, key))
        if entry is None:
            return None
        path = Path(entry['response_path'])
        if sha(path) != entry['response_sha256']:
            raise ValueError('Changed response bytes')
        return path

    def get_or_fetch(self, **kwargs):
        raise RuntimeError('Read-only handoff cannot fetch or write')
