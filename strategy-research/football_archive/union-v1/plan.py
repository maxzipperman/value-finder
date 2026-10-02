"""Outcome-blind event-odds lists from the frozen provider observation inventory.

No key, network, results, pricing cohort or played-game-only universe. Listing observations can
exclude ambiguous requests, never establish that an unseen listing was never offered.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

BASE = 'https://api.the-odds-api.com/v4'
NFL = 'americanfootball_nfl'
SOURCE_ROOT = '4468a94c2b415cd5c53dd58163831f61d379ee44ec1b560f5a9b84be9c7f010d'
SPECS = {
    'F2': ((2023, 2024, 2025), 'alternate_spreads,alternate_totals', 48000),
    'F3a': ((2025,), 'player_pass_yds,player_rush_yds,player_reception_yds,player_receptions,player_kicking_points,player_field_goals', 36000),
}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode()


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def ts(value):
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if result.utcoffset() is None:
        raise ValueError('Timezone required')
    return result


def iso(value):
    return value.isoformat(timespec='seconds').replace('+00:00', 'Z')


def verify_source(bundle):
    cert = json.loads((bundle / 'FREEZE.json').read_text())
    if cert['bundle_root_sha256'] != SOURCE_ROOT or hashlib.sha256(canonical(cert['file_sha256'])).hexdigest() != SOURCE_ROOT:
        raise ValueError('Source freeze root mismatch')
    # Verify selection inputs only; a paid runner separately verifies all frozen execution bytes/reuse.
    for name in ('canonical-games.json', 'provider-observations.json', 'protocol.json', 'request-manifest.json'):
        if sha(bundle / name) != cert['file_sha256'][name]:
            raise ValueError('Selection source changed')
    return {name: cert['file_sha256'][name] for name in ('canonical-games.json', 'provider-observations.json', 'protocol.json')}


def request(sport, provider_id, at, markets, books):
    path = f'/historical/sports/{sport}/events/{provider_id}/odds'
    params = {'bookmakers': ','.join(books), 'markets': markets, 'oddsFormat': 'decimal',
              'dateFormat': 'iso', 'date': iso(at)}
    identity = {'source': 'oddsapi/hist_event_odds', 'url': BASE + path, 'params': params}
    return {'request_id': hashlib.sha256(canonical(identity)).hexdigest(),
            'cache_key': hashlib.sha1(json.dumps(identity, sort_keys=True, default=str).encode()).hexdigest()[:20],
            'sport': sport, 'source': identity['source'], 'path': path, 'params': params,
            'requested_utc': iso(at), 'event_id': provider_id, 'max_credits': 10 * len(markets.split(',')),
            'max_new_credits': 10 * len(markets.split(',')), 'retry_allowance': 0,
            'priority': 1,
            'sealed': False, 'cache_source': None, 'cache_sha256': None, 'opportunities': []}


def plan(pid, games, observations, books):
    seasons, markets, cap = SPECS[pid]
    game_metadata = {g['canonical_game_id']: g for g in games}
    by_game, unmatched = defaultdict(list), defaultdict(list)
    id_games = defaultdict(set)
    for observation in observations:
        if observation.get('canonical_game_id'):
            id_games[observation['sport'], observation['provider_id']].add(observation['canonical_game_id'])
    conflicted = {key for key, ids in id_games.items() if len(ids) > 1}
    for observation in observations:
        if observation['sport'] != NFL or observation['season'] not in seasons:
            continue
        gid = observation.get('canonical_game_id')
        if gid:
            by_game[gid].append(observation)
        else:
            unmatched[observation['season'], observation['provider_id']].append(observation)
    inventory = []
    for game in games:
        if game['sport'] == NFL and game['season'] in seasons:
            # Later clocks are safety restrictions, not decision-time inputs. Their role is disclosed.
            anchor = min(ts(game['scheduled_utc']), ts(game['close_anchor_utc']))
            inventory.append((game['canonical_game_id'], game['season'], anchor,
                              by_game.get(game['canonical_game_id'], []), 'canonical'))
    # Retain contingent/cancelled/unmatched provider events: do not select on a played-game match.
    for (season, eid), seen in unmatched.items():
        latest = max(seen, key=lambda o: ts(o['returned_utc']))
        inventory.append((f'provider-only/{NFL}/{season}/{eid}', season,
                          ts(latest['provider_kickoff_utc']), seen, 'provider-only'))
    rows, opportunities = {}, []
    for gid, season, anchor, seen, kind in sorted(inventory):
        for slot, delta in (('T24', timedelta(hours=24)), ('CLOSE_T10', timedelta(minutes=10))):
            at = anchor - delta
            op = {'opportunity_id': f'{gid}/{slot}', 'game_identity': gid, 'identity_type': kind,
                  'season': season, 'slot': slot, 'requested_utc': iso(at), 'anchor_utc': iso(anchor),
                  'timing_claim': 'retrospective scheduled safety restriction; not actual-play certified'}
            metadata = game_metadata.get(gid, {})
            op['close_primary_status'] = metadata.get('close_primary_status', 'independent_schedule_missing')
            op['schedule_discrepancy_minutes'] = metadata.get('schedule_discrepancy_minutes')
            eligible = [o for o in seen if ts(o['returned_utc']) <= at]
            if not eligible:
                op['status'] = 'not_bound_in_available_sweeps_before_slot'
            else:
                newest = max(ts(o['returned_utc']) for o in eligible)
                closest = [o for o in eligible if ts(o['returned_utc']) == newest]
                ids = {o['provider_id'] for o in closest}
                op['binding_observed_utc'] = iso(newest)
                if len(ids) != 1:
                    op['status'] = 'ambiguous_provider_ids_at_latest_available_sweep'
                else:
                    eid = next(iter(ids))
                    clocks = [ts(o['provider_kickoff_utc']) for o in closest]
                    orientations = {(o['home_team'], o['away_team']) for o in closest}
                    if (NFL, eid) in conflicted:
                        op['status'] = 'provider_id_maps_to_multiple_canonical_games'
                    elif len(orientations) != 1 or len(set(clocks)) != 1:
                        op['status'] = 'conflicting_provider_clock_or_orientation'
                    elif at >= min(clocks):
                        op['status'] = 'at_or_after_provider_kickoff_as_observed_before_slot'
                    else:
                        row = request(NFL, eid, at, markets, books)
                        row['opportunities'] = [op['opportunity_id']]
                        row['seasons'] = [season]
                        existing = rows.setdefault(row['request_id'], row)
                        if op['opportunity_id'] not in existing['opportunities']:
                            existing['opportunities'].append(op['opportunity_id'])
                        op.update(status='planned', request_id=row['request_id'], provider_id=eid,
                                  provider_kickoff_utc=iso(clocks[0]), home_team=closest[0]['home_team'],
                                  away_team=closest[0]['away_team'],
                                  binding_evidence=[{'cache_key': o['source_cache_key'], 'body_sha256': o['source_body_sha256']}
                                                    for o in closest])
            opportunities.append(op)
    requests = sorted(rows.values(), key=lambda row: (row['requested_utc'], row['request_id']))
    cost = sum(row['max_new_credits'] for row in requests)
    if cost > cap:
        raise ValueError(f'{pid} exact list exceeds approved planning ceiling: {cost} > {cap}')
    return requests, opportunities


def write_packet(out, manifest, requests, opportunities):
    out.mkdir(parents=True, exist_ok=True)
    (out / 'requests.json').write_bytes(canonical(requests) + b'\n')
    (out / 'opportunities.json').write_bytes(canonical(opportunities) + b'\n')
    with (out / 'request-list.csv').open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=['request_id', 'sport', 'event_id', 'requested_utc', 'markets', 'bookmakers', 'max_new_credits'])
        writer.writeheader()
        for row in requests:
            writer.writerow({key: row[key] if key not in ('markets', 'bookmakers') else row['params'][key]
                             for key in writer.fieldnames})
    counts = defaultdict(int)
    for op in opportunities:
        counts[op['status']] += 1
    manifest.update(request_count=len(requests), request_set_sha256=hashlib.sha256(canonical(requests)).hexdigest(),
                    request_list_sha256=sha(out / 'request-list.csv'), new_credits=sum(r['max_new_credits'] for r in requests),
                    opportunity_count=len(opportunities), opportunity_status=dict(counts),
                    provider_only_opportunities=sum(o['identity_type'] == 'provider-only' for o in opportunities))
    (out / 'manifest.json').write_bytes(canonical(manifest) + b'\n')
    return manifest


def build(bundle, out, pid):
    inputs = verify_source(bundle)
    cfg = json.loads((bundle / 'protocol.json').read_text())
    if len(cfg['book_panel']) != 10 or len(set(cfg['book_panel'])) != 10:
        raise ValueError('Exactly ten distinct books required')
    requests, opportunities = plan(pid, json.loads((bundle / 'canonical-games.json').read_text()),
                                   json.loads((bundle / 'provider-observations.json').read_text()), cfg['book_panel'])
    manifest = {'status': 'prepared_not_authorized', 'pull': pid, 'source_bundle_root': SOURCE_ROOT,
                'source_input_sha256': inputs, 'scope_seasons': list(SPECS[pid][0]), 'sport': NFL, 'books': cfg['book_panel'],
                'planning_ceiling': SPECS[pid][2],
                'close_policy_proposal': 'scheduled-safe T-10; amendment/list review required before paid send',
                'cache_reconciliation': 'PENDING: no reuse assumed until cross-store hashes verified',
                'API_calls': 0, 'outcomes_joined': False, 'sealed_seasons_included': False}
    return write_packet(out, manifest, requests, opportunities)


def pilot_subset(rows, ops):
    selected = set()
    for year in SPECS['F2'][0]:
        games = {o['game_identity']: o['anchor_utc'] for o in ops
                 if o['season'] == year and o['identity_type'] == 'canonical' and
                 ts(o['anchor_utc']) >= ts(f'{year}-09-01T00:00:00Z')}
        selected.update(sorted(games, key=lambda gid: (games[gid], gid))[:8])
    ops = [o for o in ops if o['game_identity'] in selected]
    op_ids = {o['opportunity_id'] for o in ops}
    rows = [dict(r, opportunities=[o for o in r['opportunities'] if o in op_ids]) for r in rows if set(r['opportunities']) & op_ids]
    return rows, ops


def pilot(full, out):
    manifest = json.loads((full / 'manifest.json').read_text())
    if manifest['pull'] != 'F2':
        raise ValueError('Pilot is F2 only')
    rows, ops = pilot_subset(json.loads((full / 'requests.json').read_text()),
                             json.loads((full / 'opportunities.json').read_text()))
    manifest.update(stage='pilot', pilot_selection='first 8 canonical games after Sep 1 per season; both slots',
                    parent_request_set_sha256=manifest['request_set_sha256'], gate='coverage.json criteria; no outcomes')
    return write_packet(out, manifest, rows, ops)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--bundle', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--pull', choices=SPECS, required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.bundle, args.out, args.pull), indent=2))


if __name__ == '__main__':
    main()
