"""Read-only historical football cache inventory. Evidence stays local.

Only unsealed historical event-prop bodies are read. Other source metadata is
counted, never treated as reusable prop prices. No network, credential or runtime writes.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import pyarrow.parquet as pq
import plan


def read_inventory(raw_roots, runtime_base):
    ledgers = list(runtime_base.glob('*/spending-ledger.json'))
    before = {str(p): plan.sha(p) for p in ledgers}
    evidence = {}
    for p in ledgers:
        state = json.loads(p.read_text())
        for rid, a in state.get('attempts', {}).items():
            key = a.get('cache_key')
            if key:
                evidence.setdefault(key, []).append((p.parent, rid, a))
    entries = []
    source_counts = Counter()
    hashes_by_key = {}
    paths = set()
    for root in raw_roots:
        for sport in (plan.NFL, plan.CFB):
            for source in ('hist_event_odds', 'event_odds', 'hist_event_markets', 'hist_events'):
                directory = Path(root) / sport / 'oddsapi' / source
                for p in directory.glob('*/*.parquet'):
                    if plan.START[:10] <= p.parent.name < plan.CUTOFF[:10]:
                        paths.add((str(p.resolve()), sport, source))
    for name, sport, source in sorted(paths):
        path = Path(name)
        if path.is_symlink():
            raise ValueError('Symlink cache forbidden')
        source_counts[f'{sport}/{source}'] += 1
        if source != 'hist_event_odds':
            continue
        meta = pq.read_table(path, columns=['cache_key', 'params_json', 'url', 'http_status', 'sport', 'source']).to_pylist()
        if len(meta) != 1:
            raise ValueError('Ambiguous cache rows')
        m = meta[0]
        params = json.loads(m['params_json'])
        markets = params.get('markets', '').split(',')
        if not any(key.startswith('player_') for key in markets):
            continue
        requested = params.get('date')
        if not requested or not plan.ts(plan.START) <= plan.ts(requested) < plan.ts(plan.CUTOFF):
            raise ValueError('Cached props outside unsealed window')
        books = params.get('bookmakers', '').split(',')
        if not books[0] or params.get('dateFormat', 'iso') != 'iso' or params.get('oddsFormat', 'decimal') != 'decimal':
            raise ValueError('Region-only or incompatible-format cache requires separate reconciliation')
        if set(params) - {'date', 'dateFormat', 'oddsFormat', 'bookmakers', 'markets'}:
            raise ValueError('Unreviewed cache parameter semantics')
        identity = {'source': m['source'], 'url': m['url'], 'params': params}
        key = hashlib.sha1(json.dumps(identity, sort_keys=True, default=str).encode()).hexdigest()[:20]
        rid = hashlib.sha256(plan.canonical(identity)).hexdigest()
        if key != m['cache_key'] or path.stem != key or m['sport'] != sport or m['source'] != 'oddsapi/hist_event_odds':
            raise ValueError('Cache identity mismatch')
        digest = plan.sha(path)
        if key in hashes_by_key:
            if hashes_by_key[key] != digest:
                raise ValueError('Conflicting cache copies; block overlapping purchase')
            continue
        hashes_by_key[key] = digest
        parts = m['url'].split('/')
        if len(parts) < 2 or parts[-1] != 'odds' or parts[-3] != 'events':
            raise ValueError('Event URL malformed')
        eid = parts[-2]
        status = 'unverified_blocked'
        matched = [a for a in evidence.get(key, []) if a[1] == rid]
        rec = None
        for root, purchase_id, attempt in matched:
            if attempt['status'] != 'completed':
                continue
            receipt = root / 'receipts' / (purchase_id + '.json')
            if (attempt.get('response_sha256') != digest or not receipt.is_file()
                    or attempt.get('receipt_sha256') != plan.sha(receipt)):
                raise ValueError('Completed receipt/cache changed')
            payload = json.loads(receipt.read_text())
            if payload.get('request_id') != purchase_id or payload.get('record_sha256') != digest:
                raise ValueError('Receipt identity mismatch')
            if rec is None:
                rec = pq.read_table(path).to_pylist()[0]
            if payload['record']['body'] != rec['body'] or json.loads(payload['record']['params_json']) != params:
                raise ValueError('Receipt response differs')
            body = json.loads(rec['body'])
            event = body.get('data')
            if (rec['http_status'] != 200 or not isinstance(event, dict) or event.get('id') != eid
                    or event.get('sport_key') != sport):
                raise ValueError('Completed prop event identity invalid')
            lag = (plan.ts(requested) - plan.ts(body['timestamp'])).total_seconds()
            if not 0 <= lag <= 600 or plan.ts(body['timestamp']) >= plan.ts(event['commence_time']):
                raise ValueError('Cached prop quote clock invalid')
            headers = json.loads(rec['headers_json'])
            last = headers['x-requests-last']
            if isinstance(last, bool) or not str(last).isdigit() or int(last) != attempt.get('billed_credits'):
                raise ValueError('Receipt billing differs')
            status = 'verified_completed'
        entries.append({'sport': sport, 'event_id': eid, 'requested_utc': requested,
                        'books': sorted(set(books)), 'requested_markets': sorted(set(markets)),
                        'status': status, 'cache_source': name, 'cache_sha256': digest, 'request_id': rid,
                        'returned_markets': sorted({x['key'] for b in json.loads(rec['body'])['data'].get('bookmakers', []) for x in b.get('markets', [])}) if rec else [],
                        'returned_books': sorted({b['key'] for b in json.loads(rec['body'])['data'].get('bookmakers', [])}) if rec else []})
    after = {str(p): plan.sha(p) for p in ledgers}
    if before != after:
        raise ValueError('Runtime changed during inventory; repeat stable read-only reconciliation')
    return {'entries': entries, 'source_counts': dict(source_counts), 'ledger_sha256': before,
            'runtime_unchanged': True, 'API_calls': 0, 'outcomes_joined': False,
            'sealed_quote_reads': False}


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--raw-root', type=Path, action='append', required=True)
    p.add_argument('--runtime-base', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    result = read_inventory(a.raw_root, a.runtime_base)
    # Output is preparation evidence, never written into runtime.
    if a.out.resolve().is_relative_to(a.runtime_base.resolve()):
        raise ValueError('Output must be outside runtime')
    a.out.write_bytes(plan.canonical(result) + b'\n')
    print(json.dumps({'entries': len(result['entries']), 'states': dict(Counter(e['status'] for e in result['entries'])),
                      'source_counts': result['source_counts'], 'runtime_unchanged': True}))
