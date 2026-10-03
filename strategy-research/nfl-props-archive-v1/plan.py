"""Pure, outcome-blind preparation. No transport, keys or runtime writes."""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
from collections import defaultdict, Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

NFL = 'americanfootball_nfl'
BASE = 'https://api.the-odds-api.com/v4'
START = '2023-05-03T05:30:00Z'
CUTOFF = '2026-02-10T00:00:00Z'
REGIONS = ['us', 'us2', 'eu']
OPTIONAL_REGIONS = ['uk', 'au', 'ca', 'fr', 'se', 'fi', 'us_dfs', 'us_ex']
CFB = 'americanfootball_ncaaf'
SLOTS = {'T72': 4320, 'T48': 2880, 'T24': 1440, 'T6': 360, 'T1': 60, 'CLOSE_T10': 10}
FIRST = ('T24', 'CLOSE_T10')
SOURCE_ROOT = '4468a94c2b415cd5c53dd58163831f61d379ee44ec1b560f5a9b84be9c7f010d'


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def ts(value):
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if result.utcoffset() is None:
        raise ValueError('Aware UTC time required')
    return result.astimezone(timezone.utc)


def iso(value):
    return value.astimezone(timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z')


def floor(value):
    return value.replace(minute=value.minute // 5 * 5, second=0, microsecond=0)


def make_request(endpoint, at, books=(), markets=(), event_id=None, sport=NFL):
    if sport not in (NFL, CFB):
        raise ValueError('Football sport required')
    if not ts(START) <= at < ts(CUTOFF):
        raise ValueError('Outside unsealed acquisition window')
    at = floor(at)
    path = f'/historical/sports/{sport}/events'
    params = {'date': iso(at), 'dateFormat': 'iso'}
    source = 'oddsapi/hist_events'
    cap = 1
    if endpoint != 'events':
        if not event_id or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-' for c in event_id):
            raise ValueError('Invalid event identity')
        path += f'/{event_id}/{endpoint}'
        source = 'oddsapi/hist_event_' + endpoint
        if endpoint == 'markets':
            params['regions'] = ','.join(REGIONS)
        elif endpoint == 'odds':
            if not books or not markets or len(books) != len(set(books)) or len(markets) != len(set(markets)):
                raise ValueError('Nonempty distinct books and markets required')
            params.update(bookmakers=','.join(sorted(books)), markets=','.join(sorted(markets)), oddsFormat='decimal')
            cap = 10 * len(markets) * ((len(books) + 9) // 10)
        else:
            raise ValueError('Unknown endpoint')
    identity = {'source': source, 'url': BASE + path, 'params': params}
    return dict(identity, request_id=hashlib.sha256(canonical(identity)).hexdigest(),
                cache_key=hashlib.sha1(json.dumps(identity, sort_keys=True, default=str).encode()).hexdigest()[:20],
                sport=sport, event_id=event_id, requested_utc=iso(at), max_new_credits=cap,
                retry_allowance=0, sealed=False)


def listing_requests(sport=NFL):
    at = ts(START).replace(hour=6, minute=0)
    rows = []
    while at < ts(CUTOFF):
        rows.append(make_request('events', at, sport=sport))
        at += timedelta(days=1)
    return rows


def verify_source(bundle):
    freeze = json.loads((bundle / 'FREEZE.json').read_text())
    if freeze['bundle_root_sha256'] != SOURCE_ROOT or hashlib.sha256(canonical(freeze['file_sha256'])).hexdigest() != SOURCE_ROOT:
        raise ValueError('Wrong source root')
    names = ('canonical-games.json', 'provider-observations.json', 'protocol.json', 'inputs/nfl-weather-game-metadata.json')
    for name in names:
        if sha(bundle / name) != freeze['file_sha256'][name]:
            raise ValueError('Selection source changed: ' + name)
    return {n: freeze['file_sha256'][n] for n in names}


def opportunities(games, observations, phase_metadata, slots=SLOTS, sport=NFL):
    phases = {x['game_id']: x['game_type'] for x in phase_metadata}
    by_game = defaultdict(list)
    unmatched = defaultdict(list)
    id_games = defaultdict(set)
    for o in observations:
        if o['sport'] != sport or o['season'] not in (2023, 2024, 2025):
            continue
        gid = o.get('canonical_game_id')
        if gid:
            by_game[gid].append(o)
            id_games[o['provider_id']].add(gid)
        else:
            unmatched[o['season'], o['provider_id']].append(o)
    inventory = []
    for g in games:
        if g['sport'] == sport and g['season'] in (2023, 2024, 2025):
            inventory.append((g['canonical_game_id'], g['season'], min(ts(g['scheduled_utc']), ts(g['close_anchor_utc'])),
                              by_game[g['canonical_game_id']], phases.get(g['external_game_id'], 'UNKNOWN')))
    for (season, eid), seen in unmatched.items():
        latest = max(seen, key=lambda o: ts(o['returned_utc']))
        inventory.append((f'provider-only/{season}/{eid}', season, ts(latest['provider_kickoff_utc']), seen, 'UNKNOWN'))
    result = []
    for gid, season, anchor, seen, phase in sorted(inventory):
        for slot in slots:
            at = floor(anchor - timedelta(minutes=SLOTS[slot]))
            op = dict(opportunity_id=f'{gid}/{slot}', game_identity=gid, season=season, phase=phase,
                      slot=slot, requested_utc=iso(at), anchor_utc=iso(anchor), status='unbound')
            if not ts(START) <= at < ts(CUTOFF):
                op['status'] = 'outside_window'
                result.append(op)
                continue
            eligible = [o for o in seen if ts(o['returned_utc']) <= at]
            if eligible:
                newest = max(ts(o['returned_utc']) for o in eligible)
                closest = [o for o in eligible if ts(o['returned_utc']) == newest]
                ids = {o['provider_id'] for o in closest}
                clocks = {ts(o['provider_kickoff_utc']) for o in closest}
                teams = {(o['home_team'], o['away_team']) for o in closest}
                if len(ids) != 1 or len(clocks) != 1 or len(teams) != 1:
                    op['status'] = 'ambiguous'
                else:
                    eid = next(iter(ids))
                    if len(id_games[eid]) > 1:
                        op['status'] = 'provider_id_conflict'
                    elif at >= next(iter(clocks)):
                        op['status'] = 'at_or_after_known_kickoff'
                    else:
                        op.update(status='bound', event_id=eid, binding_observed_utc=iso(newest))
            result.append(op)
    return result


def cells(books, markets):
    return {(b, m) for b in books for m in markets}


def residual_requests(event_id, at, wanted, covered=(), blocked=(), sport=NFL):
    """Requested-but-absent coverage is still covered; never claim it is a quote."""
    wanted, covered, blocked = set(wanted), set(covered), set(blocked)
    if wanted & blocked:
        raise ValueError('Prior uncertain/conflicting coverage overlaps; never replace')
    residual = wanted - covered
    by_market = defaultdict(set)
    for book, market in residual:
        by_market[market].add(book)
    groups = defaultdict(list)
    for market, books in by_market.items():
        groups[tuple(sorted(books))].append(market)
    rows = []
    for books, markets in sorted(groups.items()):
        for i in range(0, len(books), 10):
            rows.append(make_request('odds', at, books[i:i+10], sorted(markets), event_id, sport=sport))
    return sorted(rows, key=lambda r: r['request_id'])


def target_inventory(ops):
    targets = {}
    for op in ops:
        if op['status'] == 'bound':
            key = op['event_id'], op['requested_utc']
            targets.setdefault(key, []).append(op['opportunity_id'])
    return targets


def price_requests(ops, catalog, books, cache_inventory, sport=NFL):
    covered, blocked = defaultdict(set), defaultdict(set)
    for entry in cache_inventory:
        if entry.get('sport', NFL) != sport:
            continue
        key = entry['event_id'], entry['requested_utc']
        bucket = covered if entry['status'] == 'verified_completed' else blocked
        bucket[key].update(cells(entry['books'], entry['requested_markets']))
    rows = []
    deductions = 0
    for (eid, when), ids in sorted(target_inventory(ops).items()):
        wanted = cells(books, catalog)
        deductions += len(wanted & covered[eid, when])
        for row in residual_requests(eid, ts(when), wanted, covered[eid, when], blocked[eid, when], sport=sport):
            row['opportunities'] = ids
            rows.append(row)
    return rows, deductions


def all_book_requests(ops, availability, cache_inventory, sport=NFL):
    """Availability is authenticated per-slot discovery output, never guessed."""
    targets = target_inventory(ops)
    available = {}
    for item in availability:
        key = item['event_id'], item['requested_utc']
        if item.get('status') != 'verified_completed' or key in available:
            raise ValueError('Unverified or duplicate availability')
        available[key] = {(b, m) for b, ms in item['book_markets'].items() for m in ms if m.startswith('player_')}
    if set(available) != set(targets):
        raise ValueError('Complete exact-slot availability required')
    covered, blocked = defaultdict(set), defaultdict(set)
    for item in cache_inventory:
        if item.get('sport', NFL) != sport:
            continue
        bucket = covered if item['status'] == 'verified_completed' else blocked
        bucket[item['event_id'], item['requested_utc']].update(cells(item['books'], item['requested_markets']))
    rows = []
    for key, wanted in sorted(available.items()):
        for row in residual_requests(key[0], ts(key[1]), wanted, covered[key], blocked[key], sport=sport):
            row['opportunities'] = targets[key]
            rows.append(row)
    return rows


def write_list(folder, rows):
    folder.mkdir(parents=True, exist_ok=True)
    (folder / 'requests.json').write_bytes(canonical(rows) + b'\n')
    with (folder / 'request-list.csv').open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=['request_id', 'requested_utc', 'event_id', 'source', 'max_new_credits', 'params_json'])
        writer.writeheader()
        for r in rows:
            writer.writerow({k: json.dumps(r['params'], sort_keys=True) if k == 'params_json' else r[k] for k in writer.fieldnames})
    summary = {'status': 'prepared_not_authorized', 'request_count': len(rows),
               'max_new_credits': sum(r['max_new_credits'] for r in rows),
               'request_list_sha256': sha(folder / 'request-list.csv'),
               'request_set_sha256': hashlib.sha256(canonical(rows)).hexdigest(), 'API_calls': 0}
    (folder / 'manifest.json').write_bytes(canonical(summary) + b'\n')
    return summary


def build(bundle, out, cache_inventory):
    inputs = verify_source(bundle)
    games = json.loads((bundle / 'canonical-games.json').read_text())
    obs = json.loads((bundle / 'provider-observations.json').read_text())
    phases = json.loads((bundle / 'inputs/nfl-weather-game-metadata.json').read_text())
    books = json.loads((bundle / 'protocol.json').read_text())['book_panel']
    report = {'status': 'NOT_READY_COMPREHENSIVE', 'source_inputs': inputs, 'sports': {}}
    for sport, catname in [(NFL, 'catalog.json'), (CFB, 'cfb-catalog.json')]:
        markets = json.loads((Path(__file__).parent / catname).read_text())['markets']
        ops = opportunities(games, obs, phases if sport == NFL else [], sport=sport)
        first = [o for o in ops if o['slot'] in FIRST]
        later = [o for o in ops if o['slot'] not in FIRST]
        known = sum(g['sport'] == sport and g['season'] in (2023, 2024, 2025) for g in games)
        result = {'known_canonical_games': known,
                  'games_by_year': dict(Counter(g['season'] for g in games if g['sport'] == sport and g['season'] in (2023, 2024, 2025))),
                  'phase_slots': dict(Counter(o['phase'] for o in ops)), 'opportunity_status': dict(Counter(o['status'] for o in ops)),
                  'all_book_price_cap': None, 'all_book_price_cap_reason': 'Slot-level historical availability not acquired',
                  'blockers': ['complete provider universe and phases', 'domestic/sharp historical slot availability',
                               'independent executor review and exact hub authority']}
        sportout = out / sport
        result['listing_discovery'] = write_list(sportout / 'listing-discovery-gross', listing_requests(sport))
        for name, selected in [('first-two-times', first), ('four-earlier-times', later)]:
            rows, deducted = price_requests(selected, markets, books, cache_inventory, sport)
            result[name] = write_list(sportout / ('benchmark-ten-books-' + name), rows)
            result[name].update(coverage_cells_reused=deducted, status='bounded_ten_book_benchmark_NOT_COMPREHENSIVE')
            discovery = [make_request('markets', ts(when), event_id=eid, sport=sport) for eid, when in sorted(target_inventory(selected))]
            result['domestic-sharp-availability-' + name] = write_list(sportout / ('availability-' + name), discovery)
        (sportout / 'opportunities.json').write_bytes(canonical(ops) + b'\n')
        result['cadence_gross'] = {str(n): {'ten_book_max_credits': known * n * len(markets) * 10,
                                         'twenty_book_max_credits': known * n * len(markets) * 20}
                                  for n in (2, 6, 9, 25, 289)}
        report['sports'][sport] = result
    out.mkdir(parents=True, exist_ok=True)
    (out / 'report.json').write_bytes(canonical(report) + b'\n')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--bundle', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--cache-inventory', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.bundle, args.out, json.loads(args.cache_inventory.read_text())['entries']), indent=2))
