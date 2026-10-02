"""Read-only F2 coverage. No executor imports, HTTP clients, key loading or outcome joins."""
import argparse
from collections import Counter, defaultdict
from datetime import datetime
import hashlib
import json
import math
import os
from pathlib import Path
import stat
import sys
sys.dont_write_bytecode = True

F2_ROOT = '059fc135b00bbbc36db208a8bb622d7444a43d42bb2607675d30671ad455f4e4'
SOURCE_ROOT = '4468a94c2b415cd5c53dd58163831f61d379ee44ec1b560f5a9b84be9c7f010d'
RUNTIME_BASE = Path.home() / 'Library/Application Support/ValueFinder/football-acquisition-state'
MARKETS = ('alternate_spreads', 'alternate_totals')
SLOTS = {'T24', 'CLOSE_T10'}


def canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode()


def read_bytes(path):
    # No symlink/FIFO/device reads; use the same opened descriptor for verification.
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise ValueError('Evidence must be a regular file')
        with os.fdopen(fd, 'rb', closefd=False) as handle:
            return handle.read()
    finally:
        os.close(fd)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def sha(path):
    return digest(read_bytes(path))


def ts(value):
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if result.utcoffset() is None:
        raise ValueError('Timezone required')
    return result


def verify_packet(packet, root):
    packet = Path(packet)
    if root != F2_ROOT or packet.is_symlink() or packet.parent.is_symlink():
        raise ValueError('Only the exact paid F2 packet is supported')
    code = list(packet.parent.glob('*.py'))
    files = {f'code/{p.name}': sha(p) for p in code}
    captured = {}
    for p in packet.iterdir():
        if p.is_symlink() or not p.is_file():
            raise ValueError('Frozen packet permits regular files only')
        if p.name != 'FREEZE.json':
            captured[p.name] = read_bytes(p)
            files[p.name] = digest(captured[p.name])
    cert = json.loads(read_bytes(packet / 'FREEZE.json'))
    if cert['root'] != root or files != cert['files'] or digest(canonical(files)) != root:
        raise ValueError('Paid F2 frozen bytes changed')
    m = json.loads(captured['manifest.json'])
    rows = json.loads(captured['requests.json'])
    ops = json.loads(captured['opportunities.json'])
    if (m['pull'] != 'F2' or m['stage'] != 'remainder' or m['request_count'] != len(rows)
            or len(rows) != 1773 or len(ops) != 1774 or m['opportunity_count'] != 1774
            or len(m['books']) != 10 or len(set(m['books'])) != 10
            or digest(canonical(rows)) != m['request_set_sha256']
            or digest(captured['request-list.csv']) != m['request_list_sha256']
            or len({r['request_id'] for r in rows}) != len(rows)
            or len({o['opportunity_id'] for o in ops}) != len(ops)):
        raise ValueError('F2 exact denominator/identity differs')
    return m, rows, ops, json.loads(captured['seed.json'])


def protocol_from(bundle, manifest):
    cert = json.loads(read_bytes(bundle / 'FREEZE.json'))
    data = read_bytes(bundle / 'protocol.json')
    if (cert['bundle_root_sha256'] != SOURCE_ROOT or digest(canonical(cert['file_sha256'])) != SOURCE_ROOT
            or digest(data) != manifest['source_input_sha256']['protocol.json']
            or digest(data) != cert['file_sha256']['protocol.json']):
        raise ValueError('Frozen source protocol changed')
    return json.loads(data)


def ancestor(seed, seen=None):
    seen = set() if seen is None else seen
    if seed['root'] in seen:
        raise ValueError('Ancestor cycle')
    seen.add(seed['root'])
    path = Path(seed['ledger_path'])
    if path != RUNTIME_BASE / seed['root'] / 'spending-ledger.json':
        raise ValueError('Ancestor outside fixed runtime')
    data = read_bytes(path)
    if digest(data) != seed['ledger_sha256']:
        raise ValueError('Ancestor ledger changed')
    state = json.loads(data)
    prior = sum(a['reserved_credits'] for a in state['attempts'].values()) + state['other_usage_reserved']
    if (state['bundle_root_sha256'] != seed['root'] or state['probe_credits'] != 1687
            or seed['probe_credits'] != 1687 or prior != seed['cumulative_debit_without_probe']
            or state['pending'] or state['stopped']
            or state['status'] not in ('event_epoch_complete', 'recent_complete_stopped_before_older')):
        raise ValueError('Ancestor incomplete or debit differs')
    states = [(path, state)]
    if state.get('predecessor_seed'):
        earlier, more = ancestor(state['predecessor_seed'], seen)
        if state['other_usage_reserved'] < earlier:
            raise ValueError('Ancestor debit reduced')
        states.extend(more)
    return prior, states


def response_body(row, record, protocol):
    if (record['cache_key'] != row['cache_key'] or record['sport'] != row['sport']
            or record['source'] != row['source']
            or record['url'] != 'https://api.the-odds-api.com/v4' + row['path']
            or json.loads(record['params_json']) != row['params']):
        raise ValueError('Response identity changed')
    if record['http_status'] != 200:
        return None, f"http_{record['http_status']}"
    headers = json.loads(record['headers_json'])
    for name in ('x-requests-last', 'x-requests-used', 'x-requests-remaining'):
        value = headers.get(name)
        if not isinstance(value, (str, int)) or isinstance(value, bool) or not str(value).isdigit():
            raise ValueError('Response billing missing or invalid')
    try:
        body = json.loads(record['body'])
        if body['data']['id'] != row['event_id'] or body['data']['sport_key'] != row['sport']:
            return None, 'response_event_identity'
        stamp, prev, nxt = [ts(body[k]) for k in ('timestamp', 'previous_timestamp', 'next_timestamp')]
        lag = (ts(row['requested_utc']) - stamp).total_seconds()
        if not prev < stamp < nxt or not 0 <= lag <= protocol['price_row_eligibility']['maximum_snapshot_lag_seconds']:
            return None, 'response_snapshot_clock'
        return body, None
    except (KeyError, TypeError, ValueError, AttributeError):
        return None, 'malformed_response'


def evidence(row, state, ledger_path, ancestors, protocol):
    import pyarrow.parquet as pq
    if row['max_new_credits'] == 0:
        if row['request_id'] not in state['cache_reuse']:
            return {'body': None, 'reason': 'reuse_not_yet_reconciled'}
        if state['cache_reuse'][row['request_id']] != row['cache_sha256']:
            raise ValueError('Reuse ledger differs')
        found = [(p, s['attempts'][row['request_id']]) for p, s in ancestors if row['request_id'] in s['attempts']]
        if len(found) != 1:
            raise ValueError('Reuse must have one paid ancestor receipt')
        prior, attempt = found[0]
        receipt_path = prior.parent / 'receipts' / (row['request_id'] + '.json')
        path, expected = Path(row['cache_source']), row['cache_sha256']
        if attempt['status'] != 'completed' or expected != attempt['response_sha256']:
            raise ValueError('Ancestor reuse response differs')
    else:
        attempt = state['attempts'].get(row['request_id'])
        if attempt is None or attempt['status'] != 'completed':
            return {'body': None, 'reason': 'missing_or_unresolved_response',
                    'attempt_status': (attempt or {}).get('status'),
                    'observed_http_status': (attempt or {}).get('observed_http_status'),
                    'reserved_credits': (attempt or {}).get('reserved_credits')}
        receipt_path = ledger_path.parent / 'receipts' / (row['request_id'] + '.json')
        path, expected = Path(attempt['response_path']), attempt['response_sha256']
    receipt_bytes = read_bytes(receipt_path)
    if digest(receipt_bytes) != attempt['receipt_sha256']:
        raise ValueError('Receipt changed')
    receipt = json.loads(receipt_bytes)
    data = read_bytes(path)
    if digest(data) != expected or receipt['record_sha256'] != expected:
        raise ValueError('Cache changed')
    if receipt['request_id'] != row['request_id'] or receipt['cache_key'] != row['cache_key']:
        raise ValueError('Receipt identity differs')
    # Decode the same bytes whose hash was checked, never reopen a mutable path.
    import pyarrow as pa
    records = pq.read_table(pa.BufferReader(data)).to_pylist()
    if len(records) != 1:
        raise ValueError('Expected one cached response')
    if receipt['record'] != json.loads(json.dumps(records[0], default=str)):
        raise ValueError('Receipt record differs from cache')
    body, reason = response_body(row, records[0], protocol)
    return {'body': body, 'reason': reason, 'cache_sha256': expected,
            'receipt_sha256': digest(receipt_bytes), 'reused': not row['max_new_credits']}


def scheduled_reasons(op, row, body):
    reasons = []
    if op['identity_type'] != 'canonical': reasons.append('independent_schedule_missing_provider_only')
    if op.get('close_primary_status') != 'scheduled_guard_pending_quote_validation': reasons.append('schedule_guard_unverified')
    data = body['data']
    if data.get('home_team') != op.get('home_team') or data.get('away_team') != op.get('away_team'):
        reasons.append('team_orientation_differs')
    try:
        clocks = [ts(op['anchor_utc']), ts(op['provider_kickoff_utc']), ts(data['commence_time'])]
        stamp, decision = ts(body['timestamp']), ts(row['requested_utc'])
        if decision >= min(clocks) or stamp >= min(clocks): reasons.append('at_or_after_scheduled_clock')
        if op['slot'] == 'CLOSE_T10':
            if (max(clocks) - min(clocks)).total_seconds() > 300: reasons.append('close_schedule_discrepancy')
            if not all(300 <= (clock - stamp).total_seconds() <= 1200 for clock in clocks): reasons.append('close_snapshot_window')
    except (KeyError, ValueError, TypeError, AttributeError): reasons.append('schedule_clock_missing_or_invalid')
    return sorted(set(reasons))


def curve_status(market, book, op, row, body, protocol):
    reasons = []
    try:
        update = ts(market.get('last_update') or book['last_update'])
        snap_age = (ts(body['timestamp']) - update).total_seconds()
        decision_age = (ts(row['requested_utc']) - update).total_seconds()
        rules = protocol['price_row_eligibility']
        if not 0 <= snap_age <= rules['maximum_quote_age_at_snapshot_seconds']: reasons.append('quote_age_at_snapshot')
        if not 0 <= decision_age <= rules['maximum_quote_age_at_requested_decision_seconds']: reasons.append('quote_age_at_decision')
    except (KeyError, ValueError, TypeError, AttributeError): reasons.append('quote_time_missing_or_invalid')
    sides = {'Over', 'Under'} if market['key'] == 'alternate_totals' else {op.get('home_team'), op.get('away_team')}
    points = defaultdict(set)
    outcomes = market.get('outcomes', [])
    if not isinstance(outcomes, list): outcomes = []; reasons.append('malformed_outcomes')
    for outcome in outcomes:
        if not isinstance(outcome, dict): continue
        side, price, point = outcome.get('name'), outcome.get('price'), outcome.get('point')
        if (side in sides and side is not None and isinstance(price, (int, float)) and not isinstance(price, bool)
                and isinstance(point, (int, float)) and not isinstance(point, bool)
                and math.isfinite(price) and math.isfinite(point) and price > 1):
            points[side].add(point)
    if None in sides or len(sides) != 2 or any(len(points[s]) < 2 for s in sides):
        reasons.append('insufficient_two_points_per_side')
    return sorted(set(reasons))


def summarize(manifest, rows, opportunities, responses, protocol):
    by_request = {r['request_id']: r for r in rows}
    cells, exclusions, op_rows = defaultdict(Counter), [], []
    pair_slots = defaultdict(lambda: defaultdict(lambda: defaultdict(set)))
    games = {}
    for op in opportunities:
        group = (op['game_identity'], op['season'], op['identity_type'])
        games[group] = True
        row = by_request.get(op.get('request_id')) if op['status'] == 'planned' else None
        result = responses.get(row['request_id']) if row else None
        body = result.get('body') if result else None
        root_reason = op['status'] if not row else ((result or {}).get('reason') or ('missing_response' if body is None else None))
        safety = scheduled_reasons(op, row, body) if body is not None else [root_reason]
        raw_books = body['data'].get('bookmakers', []) if body else []
        books = defaultdict(list)
        if isinstance(raw_books, list):
            for book in raw_books:
                if isinstance(book, dict) and isinstance(book.get('key'), str): books[book['key']].append(book)
        fresh_by_book = defaultdict(set)
        for book_name in manifest['books']:
            for market_name in MARKETS:
                key = (op['season'], op['slot'], book_name, market_name, op['identity_type'])
                count = cells[key]; count['denominator'] += 1
                reasons, present = [], False
                if root_reason: reasons = [root_reason]
                elif not isinstance(raw_books, list): reasons = ['malformed_bookmakers']
                elif not books[book_name]: reasons = ['missing_book']
                elif len(books[book_name]) != 1: reasons = ['duplicate_book']
                else:
                    book = books[book_name][0]
                    raw_markets = book.get('markets', [])
                    if not isinstance(raw_markets, list): reasons = ['malformed_markets']
                    else:
                        markets = [m for m in raw_markets if isinstance(m, dict) and m.get('key') == market_name]
                        if not markets: reasons = ['missing_market']
                        elif len(markets) > 1: reasons = ['duplicate_market']
                        else:
                            present = True
                            reasons = curve_status(markets[0], book, op, row, body, protocol)
                if present: count['market_present'] += 1
                if not reasons:
                    count['fresh_curve'] += 1
                    fresh_by_book[book_name].add(market_name)
                    if not safety:
                        count['scheduled_safe_fresh_curve'] += 1
                        pair_slots[group][book_name][market_name].add(op['slot'])
                else:
                    exclusions.append({'opportunity_id': op['opportunity_id'], 'request_id': op.get('request_id'),
                                       'book': book_name, 'market': market_name, 'reasons': reasons})
                for reason in reasons: count['exclude/' + reason] += 1
        op_rows.append({'opportunity_id': op['opportunity_id'], 'request_id': op.get('request_id'),
            'game_identity': op['game_identity'], 'season': op['season'], 'slot': op['slot'],
            'identity_type': op['identity_type'], 'binding_status': op['status'],
            'response_valid': body is not None, 'scheduled_safe': not safety,
            'scheduled_exclusions': safety, 'actual_play_certified': False,
            'fresh_curve_books': {b: sorted(ms) for b, ms in sorted(fresh_by_book.items())},
            'binding_observed_utc': op.get('binding_observed_utc'), 'requested_utc': op['requested_utc']})
    paired = []
    for group in sorted(games):
        book_slots = pair_slots[group]
        both = [b for b in manifest['books'] if all(book_slots[b][m] == SLOTS for m in MARKETS)]
        paired.append({'game_identity': group[0], 'season': group[1], 'identity_type': group[2],
            'paired_both_markets_books': both,
            'paired_by_market_books': {m: [b for b in manifest['books'] if book_slots[b][m] == SLOTS] for m in MARKETS},
            'actual_play_certified': False})
    grouped = [{'season': key[0], 'slot': key[1], 'book': key[2], 'market': key[3], 'identity_type': key[4],
                'counts': {name: value.get(name, 0) for name in ('denominator', 'market_present', 'fresh_curve', 'scheduled_safe_fresh_curve')},
                'exclusions': {name.removeprefix('exclude/'): n for name, n in sorted(value.items()) if name.startswith('exclude/')}}
               for key, value in sorted(cells.items())]
    response_counts = Counter('valid' if r.get('body') is not None else r.get('reason', 'missing') for r in responses.values())
    by_season = []
    for season in sorted({op['season'] for op in opportunities}):
        all_games = [g for g in paired if g['season'] == season]
        canonical_games = [g for g in all_games if g['identity_type'] == 'canonical']
        by_season.append({'season': season, 'all_game_denominator': len(all_games), 'canonical_game_denominator': len(canonical_games),
            'paired_canonical_games': sum(bool(g['paired_both_markets_books']) for g in canonical_games)})
    return {'denominators': {'opportunities': len(opportunities), 'request_slots': len(rows),
        'books': len(manifest['books']), 'markets': len(MARKETS), 'book_market_cells': len(opportunities) * len(manifest['books']) * len(MARKETS),
        'all_game_identities': len(paired), 'canonical_game_identities': sum(g['identity_type'] == 'canonical' for g in paired)},
        'opportunity_status': dict(Counter(o['status'] for o in opportunities)), 'response_coverage': dict(response_counts),
        'empty_bookmakers_responses': sum(r.get('body') is not None and r['body']['data'].get('bookmakers') == [] for r in responses.values()),
        'book_market_coverage': grouped, 'opportunities': op_rows, 'market_exclusions': exclusions,
        'paired_games': paired, 'paired_by_season': by_season,
        'actual_play_certified': False, 'scheduled_clock_is_known_asof_independent_feature': False,
        'outcomes_joined': False, 'profits_computed': False, 'strategy_grading_enabled': False,
        'purchase_authorized': False, 'new_analysis_variants': 0}


def build_report(packet, root, bundle, ledger_path, allow_incomplete=False):
    m, rows, ops, seed = verify_packet(packet, root)
    ledger_path = Path(ledger_path)
    if ledger_path != RUNTIME_BASE / root / 'spending-ledger.json': raise ValueError('Fixed F2 ledger path required')
    data = read_bytes(ledger_path); state = json.loads(data)
    if state['bundle_root_sha256'] != root or state['predecessor_seed'] != seed: raise ValueError('Ledger root/seed differs')
    complete = state['status'] == 'event_epoch_complete' and not state['pending'] and not state['stopped']
    if not complete and not allow_incomplete: raise ValueError('F2 is incomplete; no completion certificate')
    paid = {r['request_id']: r for r in rows if r['max_new_credits']}
    reused = {r['request_id']: r['cache_sha256'] for r in rows if not r['max_new_credits']}
    if (not set(state['attempts']) <= set(paid) or not set(state['cache_reuse']) <= set(reused)
            or any(state['cache_reuse'][k] != reused[k] for k in state['cache_reuse'])
            or (complete and (set(state['attempts']) != set(paid) or state['cache_reuse'] != reused))):
        raise ValueError('Ledger allowlist or reuse incomplete/changed')
    if (state['probe_credits'] != 1687 or state['slice_cap'] != m['new_credits']
            or any(a['reserved_credits'] < paid[rid]['max_new_credits'] for rid, a in state['attempts'].items())):
        raise ValueError('Ledger reservation/probe/cap changed')
    prior, ancestors = ancestor(seed)
    if state['other_usage_reserved'] < prior: raise ValueError('Cumulative debit reduced')
    protocol = protocol_from(Path(bundle), m)
    responses = {r['request_id']: evidence(r, state, ledger_path, ancestors, protocol) for r in rows}
    result = summarize(m, rows, ops, responses, protocol)
    result.update({'root': root, 'ledger_sha256': digest(data), 'request_set_sha256': m['request_set_sha256'],
        'request_list_sha256': m['request_list_sha256'], 'acquisition_complete': complete,
        'status': state['status'], 'pending': state['pending'], 'stopped': state['stopped'],
        'accounting': {'new_reserved': sum(a['reserved_credits'] for a in state['attempts'].values()),
            'new_billed': sum(a.get('billed_credits', 0) for a in state['attempts'].values()),
            'cumulative_reserved': 1687 + state['other_usage_reserved'] + sum(a['reserved_credits'] for a in state['attempts'].values()),
            'carried_debit_without_probe': state['other_usage_reserved'], 'provider_used': state['provider_used'],
            'provider_remaining': state['provider_remaining']},
        'response_evidence': [{k: v for k, v in responses[r['request_id']].items() if k != 'body'} | {'request_id': r['request_id']} for r in rows]})
    if sha(ledger_path) != result['ledger_sha256']: raise ValueError('Ledger changed during report; discard snapshot')
    verify_packet(packet, root)
    ancestor(seed)
    return result


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--packet', type=Path, required=True); p.add_argument('--root', required=True)
    p.add_argument('--bundle', type=Path, required=True); p.add_argument('--ledger', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True); p.add_argument('--allow-incomplete', action='store_true')
    a = p.parse_args()
    result = build_report(a.packet, a.root, a.bundle, a.ledger, a.allow_incomplete)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    # Explicit new artifact only; never replace a ledger, cache, receipt or prior report.
    with a.out.open('xb') as handle:
        handle.write(canonical(result) + b'\n'); handle.flush(); os.fsync(handle.fileno())
    print(json.dumps({k: result[k] for k in ('root', 'ledger_sha256', 'acquisition_complete', 'denominators', 'response_coverage', 'paired_by_season', 'accounting')}, indent=2))


if __name__ == '__main__': main()
