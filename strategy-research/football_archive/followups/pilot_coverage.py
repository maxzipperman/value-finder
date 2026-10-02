"""Outcome-blind F2 pilot gate: clock, identity, curve and paired-book coverage only."""
import argparse
from collections import Counter, defaultdict
import json
import math
from pathlib import Path

import epoch
import plan

GATE = {'minimum_valid_response_fraction': 0.90, 'minimum_paired_canonical_games': 12,
        'minimum_paired_games_per_season': 4, 'seasons': [2023, 2024, 2025],
        'pair': 'same named book, both alternate markets, two points on each side, both slots; fresh and scheduled-safe',
        'all_opportunities_accounted_for': True, 'profit_or_outcome_gate': False,
        'no_automatic_remainder_purchase': True}


def market_curve(market, book, op, row, body, protocol):
    snap, decision = plan.ts(body['timestamp']), plan.ts(row['requested_utc'])
    try:
        update = plan.ts(market.get('last_update') or book['last_update'])
        if not (0 <= (snap - update).total_seconds() <= protocol['price_row_eligibility']['maximum_quote_age_at_snapshot_seconds'] and
                0 <= (decision - update).total_seconds() <= protocol['price_row_eligibility']['maximum_quote_age_at_requested_decision_seconds']):
            return False
    except (KeyError, ValueError, TypeError):
        return False
    sides = {'Over', 'Under'} if market['key'] == 'alternate_totals' else {op['home_team'], op['away_team']}
    points = defaultdict(set)
    for outcome in market.get('outcomes', []):
        price, point, side = outcome.get('price'), outcome.get('point'), outcome.get('name')
        if side not in sides or isinstance(price, bool) or isinstance(point, bool):
            continue
        if not isinstance(price, (float, int)) or not isinstance(point, (float, int)):
            continue
        if math.isfinite(price) and price > 1 and math.isfinite(point):
            points[side].add(point)
    return all(len(points[side]) >= 2 for side in sides)


def scheduled_safe(op, row, body):
    data = body['data']
    try:
        snap, decision = plan.ts(body['timestamp']), plan.ts(row['requested_utc'])
        clocks = [plan.ts(op['anchor_utc']), plan.ts(op['provider_kickoff_utc']), plan.ts(data['commence_time'])]
        if decision >= min(clocks) or snap >= min(clocks):
            return False
        if op['identity_type'] != 'canonical' or op['close_primary_status'] != 'scheduled_guard_pending_quote_validation':
            return False
        if data['home_team'] != op['home_team'] or data['away_team'] != op['away_team']:
            return False
        if op['slot'] == 'CLOSE_T10' and (max(clocks) - min(clocks)).total_seconds() > 300:
            return False
        if op['slot'] == 'CLOSE_T10' and not all(300 <= (clock - snap).total_seconds() <= 1200 for clock in clocks):
            return False
        return True
    except (KeyError, TypeError, ValueError):
        return False


def report(packet, root, bundle, ledger_path):
    manifest, rows = epoch.verify_packet(packet, root)
    if manifest['pull'] != 'F2' or manifest.get('stage') != 'pilot':
        raise ValueError('Only the frozen F2 pilot coverage gate is implemented')
    if json.loads((packet / 'coverage-gate.json').read_text()) != GATE:
        raise ValueError('Coverage gate differs')
    base = epoch.source_executor(bundle)
    _, read_record, *_ = base.vendor_imports(bundle, packet)
    protocol = json.loads((bundle / 'protocol.json').read_text())
    ledger = json.loads(ledger_path.read_text())
    if ledger['bundle_root_sha256'] != root:
        raise ValueError('Wrong coverage ledger')
    ops = json.loads((packet / 'opportunities.json').read_text())
    by_id = {o['opportunity_id']: o for o in ops}
    records, counts, pairs = {}, Counter(), defaultdict(lambda: defaultdict(set))
    exclusions = []
    for row in rows:
        attempt = ledger['attempts'].get(row['request_id'])
        if row['max_new_credits'] == 0:
            if ledger['cache_reuse'].get(row['request_id']) != row['cache_sha256']:
                raise ValueError('Reuse not reconciled in ledger')
            path, digest = Path(row['cache_source']), row['cache_sha256']
        elif not attempt or attempt['status'] != 'completed':
            counts['missing_or_unresolved_response'] += 1
            exclusions.append({'request_id': row['request_id'], 'reason': 'missing_or_unresolved_response'})
            continue
        else:
            path, digest = Path(attempt['response_path']), attempt['response_sha256']
            receipt = ledger_path.parent / 'receipts' / f"{row['request_id']}.json"
            if plan.sha(receipt) != attempt['receipt_sha256']:
                raise ValueError('Receipt changed')
        if plan.sha(path) != digest:
            raise ValueError('Cached response changed')
        record = read_record(path)
        epoch.event_valid(row, record, base, protocol)
        counts['valid_responses'] += 1
        body = json.loads(record['body'])
        for oid in row['opportunities']:
            op = by_id[oid]
            if not scheduled_safe(op, row, body):
                exclusions.append({'opportunity_id': oid, 'reason': 'identity_or_scheduled_timing_guard'})
                continue
            for book in body['data'].get('bookmakers', []):
                if book['key'] not in manifest['books']:
                    continue
                curves = {m['key'] for m in book.get('markets', [])
                          if m['key'] in ('alternate_spreads', 'alternate_totals') and
                          market_curve(m, book, op, row, body, protocol)}
                for market in curves:
                    counts[f"{op['season']}/{op['slot']}/{book['key']}/{market}"] += 1
                if curves == {'alternate_spreads', 'alternate_totals'}:
                    pairs[op['game_identity'], op['season']][book['key']].add(op['slot'])
    paired = [(gid, year) for (gid, year), books in pairs.items()
              if any(slots == {'T24', 'CLOSE_T10'} for slots in books.values())]
    by_season = Counter(year for _, year in paired)
    reasons = []
    if ledger['status'] != 'event_epoch_complete' or ledger['pending'] or ledger['stopped']:
        reasons.append('epoch_not_complete')
    if counts['valid_responses'] < len(rows) * GATE['minimum_valid_response_fraction']:
        reasons.append('valid_response_fraction')
    if len(paired) < GATE['minimum_paired_canonical_games']:
        reasons.append('paired_games')
    if any(by_season[y] < GATE['minimum_paired_games_per_season'] for y in GATE['seasons']):
        reasons.append('paired_games_by_era')
    return {'root': root, 'request_set_sha256': manifest['request_set_sha256'], 'ledger_sha256': plan.sha(ledger_path),
            'opportunity_count': len(ops), 'opportunity_status': manifest['opportunity_status'],
            'response_and_quote_coverage': dict(counts), 'paired_canonical_games': len(paired),
            'paired_by_season': dict(by_season), 'exclusions': exclusions,
            'actual_play_certified': False, 'outcomes_joined': False, 'profits_computed': False,
            'remainder_gate_passed': not reasons, 'gate_failures': reasons,
            'purchase_authorized': False, 'gate': GATE}


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--packet', type=Path, required=True)
    p.add_argument('--root', required=True)
    p.add_argument('--bundle', type=Path, required=True)
    p.add_argument('--ledger', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    result = report(a.packet, a.root, a.bundle, a.ledger)
    a.out.write_bytes(plan.canonical(result) + b'\n')
    print(json.dumps(result, indent=2))
