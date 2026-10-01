"""Read-only exact-manifest inputs for an approved post-coverage price study.

No scoring, schedule replanning, cache publication or HTTP request occurs here.
The stock price-engine run(cfg, calls, cache) can consume as_calls()/ReadOnlyCache
after the hub approves its analysis integration and registration.
"""
import hashlib
import json
from datetime import datetime
from pathlib import Path


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def build_handoff(bundle, root, runtime):
    from validator import verify
    from executor import validate_response
    import pyarrow.parquet as pq
    bundle, runtime = Path(bundle), Path(runtime)
    verify(bundle, root, check_cache=True)
    manifest = json.loads((bundle/'request-manifest.json').read_text())
    protocol = json.loads((bundle/'protocol.json').read_text())
    ledger = json.loads((runtime/'spending-ledger.json').read_text())
    coverage_path = runtime/'coverage-report.json'
    coverage = json.loads(coverage_path.read_text())
    if (ledger['bundle_root_sha256'] != root or ledger['pending'] or ledger['stopped']
        or ledger['status'] != 'recent_complete_stopped_before_older'
        or coverage.get('bundle_root_sha256') != root or coverage.get('outcomes_joined') is not False or not coverage.get('all_recent_requests_completed')):
        raise ValueError('Completed recent slice and outcome-blind coverage required')
    entries = []
    for row in manifest['requests']:
        if row['priority'] != 1:
            continue
        if row['max_new_credits'] == 0:
            path, digest = bundle/row['cache_source'], row['cache_sha256']
            if ledger['cache_reuse'].get(row['request_id']) != digest:
                raise ValueError('Reused response not reconciled')
        else:
            attempt = ledger['attempts'].get(row['request_id'], {})
            if attempt.get('status') == 'missing':
                receipt=runtime/'receipts'/f"{row['request_id']}.json"
                if sha(receipt)!=attempt['receipt_sha256']:raise ValueError('Changed missing receipt')
                if attempt.get('response_path') and sha(Path(attempt['response_path']))!=attempt['response_sha256']:
                    raise ValueError('Changed missing source')
                entries.append({'request':row,'status':'accepted_missing','reason':attempt['missing_reason'],
                                'response_path':None,'response_sha256':None})
                continue
            if attempt.get('status') != 'completed':
                raise ValueError('Paid response not completed')
            path, digest = Path(attempt['response_path']), attempt['response_sha256']
            receipt = runtime/'receipts'/f"{row['request_id']}.json"
            if sha(receipt) != attempt['receipt_sha256']:
                raise ValueError('Changed paid receipt')
        if sha(path) != digest:
            raise ValueError('Changed response bytes')
        validate_response(row, pq.read_table(path).to_pylist()[0], protocol)
        entries.append({'request':row, 'response_path':str(path.resolve()), 'response_sha256':digest})
    return {'bundle_root_sha256':root, 'request_set_sha256':manifest['request_set_sha256'],
            'coverage_report_sha256':sha(coverage_path), 'scope':'recent only; no outcome joins',
            'entries':entries}


def as_calls(handoff, call_type):
    """Supply markets.oddsapi.bulk.Call from the approved analysis runtime."""
    calls = []
    for entry in handoff['entries']:
        row = entry['request']
        call = call_type('F1', row['sport'], row['source'], row['path'],
                         tuple(sorted(row['params'].items())),
                         datetime.fromisoformat(row['requested_utc'].replace('Z','+00:00')),
                         row['max_credits'], False, cache_sport=row['sport'])
        if call.key != row['cache_key']:
            raise ValueError('Reader cache identity differs')
        calls.append(call)
    return calls


class ReadOnlyCache:
    """The lookup interface used by BulkClient.cached and the price-engine loader."""
    def __init__(self, handoff, raw_dir):
        self.raw_dir = Path(raw_dir)
        self.offline = True
        self.index = {}
        for entry in handoff['entries']:
            if entry.get('status')=='accepted_missing':continue
            row = entry['request']; key = row['sport'], row['source'], row['cache_key']
            if key in self.index:
                raise ValueError('Duplicate handoff cache identity')
            self.index[key] = entry

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
