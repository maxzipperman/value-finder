"""Read-only, coverage-only handoff for the exact completed 2025 F3a archive.

No generic cache scan, dynamic archive imports, API, outcome join or grading.
The immutable acquisition's CLOSE_T10 label is preserved; it is not silently
replaced by the registered legacy T5 close. Timing amendment remains draft.
"""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
import math
import os
import stat
from pathlib import Path

ROOT = 'f955f28b2fba9f36b3cdcaa7cf29013de9b18b128a629204b0e098f6594259cd'
LEDGER_SHA = '8c8592a437646416d6dfb3b0cb989738a5c6cbf100851e874e35d6ac36ad7ba9'
REPO = Path(__file__).resolve().parents[5]
PACKET = REPO / 'strategy-research/football_archive/union-v1/F3a'
NFL = 'americanfootball_nfl'
PRIMARY = ('player_reception_yds', 'player_rush_yds')
CLOSE = 'CLOSE_T10'


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, default=str).encode()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def regular(path):
    path = Path(path).absolute()
    if any(p.is_symlink() for p in (path, *path.parents)) or not path.is_file():
        raise ValueError('Expected regular nonsymlink evidence file')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise ValueError("Expected regular evidence file")
        with os.fdopen(fd, "rb", closefd=False) as handle:
            return handle.read()
    finally:
        os.close(fd)


def checked(path, expected):
    data = regular(path)
    if digest(data) != expected:
        raise ValueError('Evidence hash mismatch: ' + Path(path).name)
    return data


def stamp(value):
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError('Timestamp lacks timezone')
    return result


def finite(value):
    if isinstance(value, bool):
        return False
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def packet_inputs(packet=PACKET):
    cert = json.loads(regular(packet / 'FREEZE.json'))
    if cert['root'] != ROOT or digest(canonical(cert['files'])) != ROOT:
        raise ValueError('Only the reviewed F3a packet is supported')
    names = ('manifest.json', 'requests.json', 'opportunities.json', 'request-list.csv')
    raw = {n: checked(packet / n, cert['files'][n]) for n in names}
    manifest, requests, opportunities = (json.loads(raw[n]) for n in names[:3])
    if (manifest['scope_seasons'] != [2025] or manifest['sport'] != NFL
            or manifest['sealed_seasons_included'] or len(requests) != 570
            or digest(canonical(requests)) != manifest['request_set_sha256']
            or digest(raw['request-list.csv']) != manifest['request_list_sha256']):
        raise ValueError('Wrong F3a scope/list')
    validate_scope(requests, opportunities)
    return manifest, requests, opportunities


def validate_scope(requests, opportunities):
    """All scope/identity checks finish before any cache or receipt body is opened."""
    ids = {r['request_id'] for r in requests}
    if len(ids) != len(requests):
        raise ValueError('Duplicate request identity')
    op_ids = {o['opportunity_id'] for o in opportunities}
    if len(op_ids) != len(opportunities):
        raise ValueError('Duplicate opportunity identity')
    for row in requests:
        at = stamp(row['requested_utc'])
        if (row['sport'] != NFL or row['seasons'] != [2025] or row['sealed']
                or not datetime(2025, 3, 1, tzinfo=timezone.utc) <= at < datetime(2026, 3, 1, tzinfo=timezone.utc)
                or not set(row['opportunities']) <= op_ids):
            raise ValueError('Sealed or unsupported request scope')
    by_id = {r['request_id']: r for r in requests}
    for op in opportunities:
        if op['season'] != 2025 or op['slot'] not in ('T24', CLOSE):
            raise ValueError('Sealed or unsupported opportunity scope')
        if op['status'] == 'planned':
            row = by_id[op['request_id']]
            if (op['opportunity_id'] not in row['opportunities'] or op['provider_id'] != row['event_id']
                    or op['requested_utc'] != row['requested_utc']):
                raise ValueError('Opportunity binding differs')


def eligibility(op, event, snapshot, requested, quote_time):
    """Scheduled pregame proxy only; never independently certified first play."""
    reasons = []
    try:
        provider, anchor, response_kick = map(stamp, (op['provider_kickoff_utc'], op['anchor_utc'], event['commence_time']))
        if op['identity_type'] != 'canonical':
            reasons.append('unresolved_game_identity')
        if (op.get('schedule_discrepancy_minutes') is None
                or abs(float(op['schedule_discrepancy_minutes'])) > 5
                or abs((response_kick - provider).total_seconds()) > 300):
            reasons.append('kickoff_conflict')
        if stamp(op['binding_observed_utc']) > requested:
            reasons.append('listing_binding_after_decision')
        if max(snapshot, requested) >= min(provider, anchor, response_kick):
            reasons.append('not_scheduled_pregame')
        if op['slot'] == CLOSE and not 300 <= (provider - snapshot).total_seconds() <= 1200:
            reasons.append('outside_close_window')
        if (event.get('home_team'), event.get('away_team')) != (op['home_team'], op['away_team']):
            reasons.append('team_orientation_conflict')
    except (ValueError, KeyError, TypeError):
        reasons.append('missing_schedule_clock')
    if not 0 <= (requested - snapshot).total_seconds() <= 600:
        reasons.append('snapshot_lag')
    try:
        updated = stamp(quote_time)
        if not 0 <= (snapshot - updated).total_seconds() <= 900:
            reasons.append('quote_age_at_snapshot')
        if not 0 <= (requested - updated).total_seconds() <= 1500:
            reasons.append('quote_age_at_decision')
    except (AttributeError, TypeError, ValueError):
        reasons.append('missing_quote_timestamp')
    return sorted(set(reasons))


def quote_rows(row, ops, record, books):
    """Retain offered rows and their eligibility reasons; no missing-side invention."""
    body = json.loads(record['body']);event = body['data']
    if event['id'] != row['event_id'] or event['sport_key'] != NFL:
        raise ValueError('Response event identity differs')
    kickoff = stamp(event['commence_time'])
    if not datetime(2025, 3, 1, tzinfo=timezone.utc) <= kickoff < datetime(2026, 3, 1, tzinfo=timezone.utc):
        raise ValueError('Response belongs to a sealed or unsupported season; prices not traversed')
    snapshot, requested = stamp(body['timestamp']), stamp(row['requested_utc'])
    if not stamp(body['previous_timestamp']) < snapshot < stamp(body['next_timestamp']):
        raise ValueError('Invalid snapshot neighbors')
    if not 0 <= (requested - snapshot).total_seconds() <= 600:
        raise ValueError('Completed response has invalid snapshot clock')
    rows = []
    for op in ops:
        for book in event.get('bookmakers', []):
            for market in book.get('markets', []):
                reasons = eligibility(op, event, snapshot, requested, market.get('last_update') or book.get('last_update'))
                if book['key'] not in books:
                    reasons = [*reasons, 'book_outside_registered_panel']
                for outcome in market.get('outcomes', []):
                    extra = []
                    if not outcome.get('description'): extra.append('missing_player_name')
                    if not finite(outcome.get('point')): extra.append('missing_point')
                    if not finite(outcome.get('price')) or float(outcome['price']) <= 1: extra.append('invalid_price')
                    if outcome.get('name') not in ('Over', 'Under'): extra.append('unsupported_side')
                    rows.append(dict(sport=NFL, season=2025, request_id=row['request_id'],
                        opportunity_id=op['opportunity_id'], game_id=op['game_identity'], event_id=event['id'],
                        role=op['slot'], requested=row['requested_utc'], snapshot=body['timestamp'],
                        book=book['key'], market=market['key'], description=outcome.get('description'),
                        side=outcome.get('name'), point=outcome.get('point'), price=outcome.get('price'),
                        eligibility_reasons=sorted(set(reasons + extra)), actual_play_certified=False))
    return rows


def summary(rows, opportunities, request_status, books):
    """Registered book coverage is offered-line presence, not winning/eligible-line selection."""
    coverage = {}
    for market in PRIMARY:
        offered = defaultdict(set)
        for r in rows:
            if (r['role'] == CLOSE and r['market'] == market and r['book'] in books
                    and r['description'] and finite(r['point'])):
                offered[(r['event_id'], r['description'])].add(r['book'])
        numerator = sum('pinnacle' in b for b in offered.values())
        coverage[market] = {'pinnacle_player_games': numerator, 'any_panel_player_games': len(offered)}
    book = None
    if any(x['any_panel_player_games'] for x in coverage.values()):
        book = 'pinnacle' if all(x['any_panel_player_games'] and
            x['pinnacle_player_games'] / x['any_panel_player_games'] >= .8 for x in coverage.values()) else 'draftkings'
    return dict(packet_root=ROOT, ledger_sha256=LEDGER_SHA, request_status=dict(Counter(request_status.values())),
        opportunity_status=dict(Counter(o['status'] for o in opportunities)), opportunity_count=len(opportunities),
        opportunities_by_role=dict(Counter(o['slot'] for o in opportunities)),
        opportunities_without_quote_rows=len({o['opportunity_id'] for o in opportunities} - {r['opportunity_id'] for r in rows}),
        offered_quote_rows=len(rows), eligibility_reasons=dict(Counter(x for r in rows for x in r['eligibility_reasons'])),
        coverage=coverage, proposed_book=book, close_role=CLOSE, timing_amendment_status='DRAFT',
        grading_enabled=False, outcomes_read=False, actual_play_certified=False,
        denominator_note='Offered player-game names with a finite point at any registered-panel book; missing requests and no-offer opportunities remain in separate opportunity denominators. T10 acquisition coverage does not imply T5 coverage or actual-play certification.')


def read_archive(runtime, packet=PACKET):
    manifest, requests, opportunities = packet_inputs(packet)
    runtime = Path(runtime).absolute()
    ledger_bytes = checked(runtime / 'spending-ledger.json', LEDGER_SHA)
    ledger = json.loads(ledger_bytes)
    if (ledger['bundle_root_sha256'] != ROOT or ledger['pending'] or ledger['stopped']
            or ledger['status'] != 'event_epoch_complete'
            or set(ledger['attempts']) != {r['request_id'] for r in requests}):
        raise ValueError('F3a completion differs')
    by_request = defaultdict(list)
    for op in opportunities:
        if op['status'] == 'planned': by_request[op['request_id']].append(op)
    from io import BytesIO
    import pyarrow.parquet as pq
    rows, statuses = [], {}
    for row in requests:
        rid = row['request_id'];attempt = ledger['attempts'][rid]
        receipt = json.loads(checked(runtime / 'receipts' / (rid + '.json'), attempt['receipt_sha256']))
        path = runtime / 'data/raw' / NFL / row['source'] / row['requested_utc'][:10] / (row['cache_key'] + '.parquet')
        if Path(attempt['response_path']).absolute() != path:
            raise ValueError('Cache path escapes exact authorized slot')
        cached = checked(path, attempt['response_sha256'])
        records = pq.read_table(BytesIO(cached)).to_pylist()
        if len(records) != 1: raise ValueError('Expected one raw response')
        record = records[0]
        # Existing cache serializes fetched_at as a datetime; receipt canonicalization uses str().
        if (receipt['request_id'] != rid or receipt['cache_key'] != row['cache_key']
                or receipt['record_sha256'] != digest(cached)
                or canonical(receipt['record']) != canonical(record)):
            raise ValueError('Receipt/cache content differs')
        if (record['cache_key'] != row['cache_key'] or record['sport'] != NFL or record['source'] != row['source']
                or record['url'] != 'https://api.the-odds-api.com/v4' + row['path']
                or json.loads(record['params_json']) != row['params']):
            raise ValueError('Cached request identity differs')
        statuses[rid] = attempt['status']
        if attempt['status'] == 'missing':
            if receipt.get('status') != 'missing': raise ValueError('Missing classification differs')
            continue  # pinned immutable ledger and receipt bind the original exact missing policy
        if attempt['status'] != 'completed' or record['http_status'] != 200:
            raise ValueError('Nonterminal or invalid response')
        rows.extend(quote_rows(row, by_request[rid], record, set(manifest['books'])))
    # Detect concurrent runtime change; never update, reserve, initialize or repair anything.
    checked(runtime / 'spending-ledger.json', LEDGER_SHA)
    return rows, summary(rows, opportunities, statuses, set(manifest['books']))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, required=True)
    args = parser.parse_args()
    _, report = read_archive(args.runtime)
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
