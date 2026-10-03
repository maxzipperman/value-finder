"""Fixed outcome-blind cached readiness; never a final-look or grading adapter."""
import ast
from collections import Counter, defaultdict
from datetime import timedelta
import fcntl
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
from types import ModuleType, SimpleNamespace

ROOT = 'c7d3ea3d938918735e3ec99f9b56652f67f4f200c93f233385b4d6429fbe1376'
LEDGER = '58b3ee64c6320fb29989b7ae41f2866ae2f9102e9bbfed703b684625187f017c'
REPO = Path(__file__).resolve().parents[2]
PINNED = Path('/private/tmp/vf-pass150-recovery')
ORIGINAL = Path('/private/tmp/vf-captured-path-fix')
RUNTIME = Path.home() / 'Library/Application Support/ValueFinder/football-acquisition-state'
PACKET = PINNED / 'strategy-research/pass150-timeout-recovery-v1/untouched-successor-final'
PILOT = ORIGINAL / 'strategy-research/coverage-pilot-packet-v1/pilot-successor-142'
PROPOSAL = PINNED / 'strategy-research/pass150-timeout-recovery-v1/exact-stop-certificate'
PREP = ORIGINAL / 'strategy-research/coverage-pass-residual-v1/passing-groups-2020-24'
BUNDLE = ORIGINAL / 'strategy-research/football_archive/acquisition/football-archive-v4'
BOOKS = ['pinnacle', 'lowvig', 'betonlineag', 'draftkings', 'fanduel', 'betmgm',
         'williamhill_us', 'fanatics', 'betrivers', 'espnbet']
MARKETS = ['player_rush_yds', 'player_reception_yds', 'player_pass_yds',
           'player_receptions', 'player_field_goals', 'player_kicking_points']


def sha(raw): return hashlib.sha256(raw).hexdigest()
def canonical(obj): return json.dumps(obj, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
def regular(path):
    path = Path(path).absolute()
    if any(p.is_symlink() for p in (path, *path.parents)): raise ValueError('symlink evidence')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode): raise ValueError('nonregular evidence')
        with os.fdopen(fd, 'rb', closefd=False) as stream: return stream.read()
    finally: os.close(fd)


def checked(path, pin):
    raw = regular(path)
    if sha(raw) != pin: raise ValueError('changed pinned input: ' + str(path))
    return raw


def load_pure(path, name, pin):
    raw = checked(path, pin)
    module = ModuleType(name); module.__file__ = str(path)
    sys.modules[name] = module
    exec(compile(raw, str(path), 'exec'), module.__dict__)
    return module


def metrics(result, market, book):
    pairs = {k for k in result['pairs'] if k[0] == market and k[1] == book}
    return {'pairs': len(pairs), 'players': len({k[2] for k in pairs}), 'present': bool(pairs)}


def operations(game, slotmap):
    if not game['stratum'].startswith('older/'): return game['source_opportunities']
    declared = slotmap.get(game['game_id'], {}).get('slots', {})
    return [{**declared.get(k, {'requested_utc': None}),
             'slot': 'EARLY_18_54' if k == 'EARLY' else 'CLOSE_T10'} for k in ('EARLY', 'CLOSE')]


def matches(record, sport, decision, event_id=None):
    if json.loads(record['params_json'])['date'] != decision: return False
    if record['sport'] != sport: raise ValueError('sport mismatch')
    if event_id and not record['url'].endswith('/events/' + event_id + '/odds'): raise ValueError('event mismatch')
    return True


def schema_columns(path, parquet):
    if any(p.is_symlink() for p in (path, *path.parents)): raise ValueError('symlink schema')
    return parquet.ParquetFile(path).schema_arrow.names if path.exists() else []


def describe_ages(body, binding, requested, utc):
    events = body.get('data'); events = events if isinstance(events, list) else [events]
    chosen = [e for e in events if isinstance(e, dict) and e.get('id') == binding.get('event_id')]
    if len(chosen) != 1: return {'reason': 'missing_or_duplicate_event'}
    try:
        snapshot, at = utc(body['timestamp']), utc(requested)
        ages, snapshot_ages, invalid_clocks = [], [], 0
        for b in chosen[0].get('bookmakers', []):
            for m in b.get('markets', []):
                try:
                    updated = utc(m.get('last_update') or b.get('last_update'))
                    ages.append((at - updated).total_seconds())
                    snapshot_ages.append((snapshot - updated).total_seconds())
                except (ValueError, TypeError): invalid_clocks += 1
        return {'snapshot_age_seconds': (at-snapshot).total_seconds(),
                'quote_ages_seconds': ages, 'quote_snapshot_ages_seconds': snapshot_ages,
                'invalid_quote_clocks': invalid_clocks, 'response_kickoff': chosen[0]['commence_time']}
    except (KeyError, ValueError, TypeError): return {'reason': 'missing_clock'}


def run():
    freeze = json.loads(regular(PACKET / 'FREEZE.json'))
    if freeze['root'] != ROOT or sha(canonical(freeze['files'])) != ROOT: raise ValueError('root mismatch')
    pins = freeze['files']; sources = {}
    def bound(name, path):
        raw = checked(path, pins[name]); sources[name] = {'path': str(path), 'sha256': sha(raw)}
        return json.loads(raw)
    baseline = bound('baseline.json', PACKET / 'baseline.json')
    rows = bound('requests.json', PROPOSAL / 'untouched-requests.json')
    maps = bound('mappings.json', PROPOSAL / 'successor-mappings.json')
    denoms = bound('denominators.json', PREP / 'denominators.json')
    frame = bound('frame.json', PILOT / 'frame.json')
    slots = {g['game_id']: g for g in bound('slot-map.json', PILOT / 'slot-map.json')}
    srcfreeze = bound('source/FREEZE.json', BUNDLE / 'FREEZE.json')
    observations = json.loads(checked(BUNDLE / 'provider-observations.json', srcfreeze['file_sha256']['provider-observations.json']))
    canonical_games = {g['canonical_game_id']: g for g in json.loads(checked(BUNDLE / 'canonical-games.json', srcfreeze['file_sha256']['canonical-games.json']))}
    timing = load_pure(REPO / 'strategy-research/coverage-pilot-v1/timing.py', 'timing', pins['code/timing.py'])
    classifier = load_pure(REPO / 'strategy-research/coverage-pilot-v1/classifier.py', 'readiness_classifier', pins['code/classifier.py'])
    reportpath = REPO / 'strategy-research/coverage-pilot-completion-v1/report.py'
    parsed = ast.parse(checked(reportpath, pins['code/completion_report.py']))
    functions = [n for n in parsed.body if isinstance(n, ast.FunctionDef) and n.name in ('saved_record', 'canonical')]
    ns = {'json': json}
    exec(compile(ast.Module(body=functions, type_ignores=[]), str(reportpath), 'exec'), ns)
    snapshot = dict(baseline['expected_global_snapshot']['ledgers']); snapshot[ROOT] = LEDGER
    ledgers = {r: json.loads(checked(RUNTIME / r / 'spending-ledger.json', h)) for r, h in snapshot.items()}
    own = ledgers[ROOT]
    if own.get('status') != 'pilot_complete' or own.get('pending') or own.get('stopped'): raise ValueError('not terminal')
    if set(own['attempts']) != {r['request_id'] for r in rows}: raise ValueError('request denominator changed')
    index = defaultdict(list)
    for r, ledger in ledgers.items():
        for rid, attempt in ledger['attempts'].items(): index[rid].append((r, attempt))
    references = {m['game_id']: m for m in maps}; by_game = {g['game_id']: g for g in frame}
    selected = {d['game_id'] for d in denoms} | {g['game_id'] for g in frame if g['stratum'] == 'props/americanfootball_nfl/2025'}
    if len(selected) != len(denoms) + 285: raise ValueError('fixed census/denominator changed')
    cache, receipts = {}, {}
    def read(rid):
        if rid in cache: return cache[rid]
        candidates = index.get(rid, [])
        if len(candidates) != 1: return None, 'unavailable_or_duplicate_receipt'
        root, attempt = candidates[0]
        if attempt['status'] not in ('completed', 'missing'): return None, 'uncertain_attempt_no_read'
        path = Path(attempt['response_path'])
        if not path.is_relative_to(RUNTIME / root / 'data/raw') or path.suffix != '.parquet': raise ValueError('unsafe raw path')
        record = ns['saved_record'](RUNTIME / root, rid, attempt,
                                   SimpleNamespace(regular=regular, digest=sha),
                                   legacy=root in baseline['base_snapshot']['ledgers'])
        receipts[rid] = {'root': root, 'status': attempt['status'], 'response_sha256': attempt['response_sha256'], 'receipt_sha256': attempt['receipt_sha256']}
        result = (record, 'terminal_missing') if attempt['status'] == 'missing' else (record, None)
        cache[rid] = result
        return result
    aggregates = defaultdict(lambda: {'game_denominator': 0, 'games_with_pairs': 0, 'complete_pair_keys': 0,
                                     'provider_label_player_games': 0, 'projected_records_requesting_book_games': 0, 'reasons': Counter()})
    exclusions, age_counts, cross, close_horizons = [], Counter(), Counter(), Counter()
    older_pairing = defaultdict(Counter)
    census_listing = {m: {'union': set(), 'pinnacle': set()} for m in MARKETS[:2]}
    for gid in sorted(selected):
        game = by_game[gid]; sport, season = gid.split('/')[0], game['season']
        if season not in (2020, 2021, 2022, 2023, 2024, 2025): raise ValueError('sealed season')
        older = game['stratum'].startswith('older/')
        markets = ['totals'] if older else MARKETS
        mapping = references.get(gid, {})
        forced = [r for k in ('metadata_disposition', 'coverage_disposition')
                  for r in mapping.get(k, {}).get('reasons', []) if mapping.get(k, {}).get('classification') == 'failure']
        ops = operations(game, slots)
        game_pairs = {}
        for op in ops:
            decision, slot = op['requested_utc'], op['slot']
            binding = classifier.bind_asof(observations, gid, decision) if decision else {'status': 'unbound', 'reason': 'no_designated_slot'}
            if decision and slot == 'CLOSE_T10' and gid in canonical_games:
                seconds = int((timing.utc(canonical_games[gid]['scheduled_utc']) - timing.utc(decision)).total_seconds())
                close_horizons['|'.join((sport, str(season), str(seconds)))] += 1
            if older and slot == 'CLOSE_T10' and op.get('binding'):
                b = op['binding']; binding = dict(status='bound', event_id=op['provider_id'],
                    provider_kickoff_utc=b['provider_kickoff_utc'], binding_observed_utc=b['returned_utc'],
                    home_team=b['home_team'], away_team=b['away_team'])
            reasons, pairs, asked_books = [], set(), set()
            rids = ([op['request_id']] if op.get('request_id') else []) if older else list(mapping.get('request_ids', [])) + list(mapping.get('reused_request_ids', [])) + list(game.get('certainty_evidence', {}).get('source_request_ids', []))
            for reuse in mapping.get('reused_slots', []): rids.extend(c['request_id'] for c in reuse['evidence'])
            if forced: reasons.extend('frozen_metadata:' + r for r in forced)
            elif binding.get('status') != 'bound': reasons.append('unbound:' + binding.get('reason', 'unknown'))
            else:
                matched = 0
                for rid in set(rids):
                    # Filter receipt metadata first; never bind an unrelated slot/body.
                    candidates = index.get(rid, [])
                    if len(candidates) != 1: reasons.append('unavailable_or_duplicate_receipt'); continue
                    root, attempt = candidates[0]
                    # Read only designated IDs; exact date/sport/event checked below.
                    record, missing = read(rid)
                    if record is None: reasons.append(missing); continue
                    params = json.loads(record['params_json'])
                    if not matches(record, sport, decision, None if older else op['event_id']): continue
                    asked_books.update(params.get('bookmakers', '').split(','))
                    if missing: matched += 1; reasons.append(missing); continue
                    body = json.loads(record['body']); matched += 1
                    result = classifier.slot_pairs(body, requested=decision, execution=decision, binding=binding,
                         independent_kickoff=canonical_games[gid]['scheduled_utc'], slot=slot, candidate_books=BOOKS, markets=markets)
                    pairs.update(result['pairs']); reasons.extend(result['reasons'])
                    ages = describe_ages(body, binding, decision, timing.utc)
                    lag = ages.get('snapshot_age_seconds')
                    if lag is not None: age_counts['snapshot_' + ('future' if lag < 0 else '0_600' if lag <= 600 else 'over600')] += 1
                    for age in ages.get('quote_ages_seconds', []):
                        age_counts['quote_decision_' + ('future' if age < 0 else '0_1500' if age <= 1500 else 'over1500')] += 1
                    for age in ages.get('quote_snapshot_ages_seconds', []):
                        age_counts['quote_snapshot_' + ('future' if age < 0 else '0_900' if age <= 900 else 'over900')] += 1
                    age_counts['missing_quote_clocks'] += ages.get('invalid_quote_clocks', 0)
                    if gid.startswith('americanfootball_nfl/2025/') and slot == 'CLOSE_T10':
                        events = body['data']; events = events if isinstance(events, list) else [events]
                        for event in events:
                            if event['id'] != binding['event_id']: continue
                            for book in event.get('bookmakers', []):
                                if book['key'] not in BOOKS: continue
                                for market in book.get('markets', []):
                                    if market['key'] not in census_listing: continue
                                    for out in market.get('outcomes', []):
                                        label = out.get('description')
                                        if isinstance(label, str) and label and out.get('point') is not None:
                                            key = (gid, label); census_listing[market['key']]['union'].add(key)
                                            if book['key'] == 'pinnacle': census_listing[market['key']]['pinnacle'].add(key)
                if not matched: reasons.append('no_designated_matching_snapshot')
            game_pairs[slot] = pairs
            if reasons: exclusions.append({'game_id': gid, 'stratum': game['stratum'], 'slot': slot,
                                           'original_classification': game['classification'], 'reasons': sorted(set(reasons))})
            for market in markets:
                for book in BOOKS:
                    key = (sport, season, market, book, slot)
                    row = aggregates[key]; row['game_denominator'] += 1
                    row['projected_records_requesting_book_games'] += book in asked_books
                    value = metrics({'pairs': pairs}, market, book)
                    row['games_with_pairs'] += value['present']; row['complete_pair_keys'] += value['pairs']
                    row['provider_label_player_games'] += value['players']
                    if not value['present']: row['reasons'].update(reasons or ['no_eligible_same_response_pair'])
            if binding.get('status') == 'bound':
                conflict = abs((timing.utc(binding['provider_kickoff_utc']) - timing.utc(canonical_games[gid]['scheduled_utc'])).total_seconds())
                age_counts['provider_independent_' + ('within300' if conflict <= 300 else 'over300')] += 1
                for delay in (30, 120, 300):
                    eligible = timing.scheduled_guard(base_eligible=True, requested=decision, returned=decision,
                        execution=(timing.utc(decision)+timedelta(seconds=delay)).isoformat(),
                        provider_kickoffs=[binding['provider_kickoff_utc']], independent_kickoffs=[canonical_games[gid]['scheduled_utc']])
                    age_counts['delay' + str(delay) + ('_strictly_pregame' if eligible['eligible'] else '_not_pregame')] += 1
        for book in BOOKS:
            early = {k[:3] for k in game_pairs.get('EARLY_18_54' if older else 'T24', set()) if k[1] == book}
            close = {k[:3] for k in game_pairs.get('CLOSE_T10', set()) if k[1] == book}
            for market in markets: cross['|'.join((sport, str(season), market, book))] += sum(k[0] == market for k in early & close)
        if older:
            paired = classifier.older_totals_feasibility({'pairs': game_pairs.get('EARLY_18_54', set())},
                       {'pairs': game_pairs.get('CLOSE_T10', set())}, [b for b in BOOKS if b not in ('pinnacle', 'lowvig', 'betonlineag')])
            older_pairing[game['stratum']].update({'game_denominator': 1, 'same_domestic_plus_reference_both_slots': int(paired['success']),
                                                 'each_book_preserves_own_point_across_slots': int(paired['same_point_success'])})
    # Stat source schema only; no row groups, values, outcome counts or 2026 filtering.
    import pyarrow.parquet as pq
    schema_path = REPO / 'nfl-weather/data/processed/player_week.parquet'
    columns = schema_columns(schema_path, pq)
    settlement_path = REPO / 'sharp-markets/src/markets/research/props_grade/settlement.py'
    module = ast.parse(regular(settlement_path))
    mapping = next(ast.literal_eval(n.value) for n in module.body if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'NFL_COLUMNS' for t in n.targets))
    schema = {m: {'declared_columns': list(c), 'available_schema': bool(columns), 'columns_present': set(c) <= set(columns),
                  'sides': ['Over', 'Under'], 'participation_verified': False, 'book_terms_verified': False,
                  'roster_linkage_verified': False, 'grading_enabled': False} for m, c in mapping.items()}
    totals_schema = {}
    for sport, folder, score_columns in [('americanfootball_nfl', 'nfl-weather', ['home_score', 'away_score']),
                                         ('americanfootball_ncaaf', 'cfb-weather', ['home_points', 'away_points'])]:
        names = schema_columns(REPO / folder / 'data/processed/games.parquet', pq)
        totals_schema[sport] = {'declared_score_columns': score_columns, 'available_schema': bool(names),
                               'columns_present': set(score_columns) <= set(names), 'sides': ['Over', 'Under'],
                               'actual_game_matching_verified': False, 'book_overtime_terms_verified': False,
                               'grading_enabled': False}
    registration_path = REPO / 'sharp-markets/src/markets/research/props_grade/registration.py'
    registration = load_pure(registration_path, 'readiness_registration', sha(regular(registration_path)))
    bar = registration.bar(REPO / 'STATUS.md', REPO / 'nfl-weather/PREREGISTRATION_PROPS.md')
    book, book_reason = registration.noted_book(REPO / 'nfl-weather/PREREGISTRATION_PROPS.md')
    completion_path = Path('/Users/maxzipperman/.codex/.chatgpt-projects/g-p-6abd9b86b9548191a07ce7f1180bc80a/research-lab/acquisition/coverage-pilot-once/completion-successor151.json')
    completion_raw = regular(completion_path); completion = json.loads(completion_raw)
    if completion['root'] != ROOT or completion['ledger_sha256'] != LEDGER: raise ValueError('completion mismatch')
    first_final = Path('/Users/maxzipperman/.codex/.chatgpt-projects/g-p-6abd9b86b9548191a07ce7f1180bc80a/research-lab/acquisition/coverage-pilot-once/final-existing-frame-v1/final-record.json')
    checked(first_final, pins['final-record.json'])  # Integrity only; no final classifications/bounds rerun.
    for r, pin in snapshot.items(): checked(RUNTIME / r / 'spending-ledger.json', pin)
    return {'scope': 'Acquired-data readiness; not a pilot final look or statistical gate', 'grading_enabled': False,
            'timing_basis': 'scheduled_proxy', 'actual_play_certified': False, 'available_quotes_not_fills': True,
            'root': ROOT, 'ledger_sha256': LEDGER, 'denominators': dict(Counter(by_game[g]['stratum'] for g in selected)),
            'original_denominator_classifications': dict(Counter(d['stratum'] + '/' + d['original_classification'] for d in denoms)),
            'coverage': [dict(zip(('sport', 'season', 'market', 'book', 'slot'), key), **dict(row, reasons=dict(row['reasons']))) for key, row in sorted(aggregates.items())],
            'cross_slot_same_label_player_games': dict(cross), 'exclusions': exclusions, 'clock_counts': dict(age_counts),
            'older_paired_readiness': {k: dict(v) for k, v in older_pairing.items()},
            'planned_close_horizons_seconds': dict(close_horizons),
            'settlement_schema': schema, 'source_schema_columns': columns, 'totals_settlement_schema': totals_schema,
            'registration_readiness': {'props_book_note': book, 'props_book_note_reason': book_reason,
                                      'props_count_fields': vars(bar), 'grading_enabled': False,
                                      'price_engine_amendment2_3': 'DRAFT; root unset; not adopted',
                                      'multiplicity_scope_reconciliation_required': True},
            'f3a_book_listing_coverage': {m: {'player_game_union': len(v['union']), 'pinnacle_player_games': len(v['pinnacle']),
                                           'ratio': len(v['pinnacle']) / len(v['union']) if v['union'] else None} for m, v in census_listing.items()},
            'provenance': {'bound_inputs': sources, 'ledger_pins': snapshot, 'receipt_projection': receipts,
                           'completion_sha256': sha(completion_raw), 'original_final_sha256': pins['final-record.json'],
                           'diagnostic_sha256': sha(regular(Path(__file__))),
                           'classifier_sha256': pins['code/classifier.py'], 'timing_sha256': pins['code/timing.py'],
                           'merged_saved_record_source_sha256': pins['code/completion_report.py'],
                           'canonical_metadata_sha256': srcfreeze['file_sha256']['canonical-games.json'],
                           'provider_observations_sha256': srcfreeze['file_sha256']['provider-observations.json'],
                           'registration_reader_sha256': sha(regular(registration_path)),
                           'props_preregistration_sha256': sha(regular(REPO / 'nfl-weather/PREREGISTRATION_PROPS.md')),
                           'price_engine_preregistration_sha256': sha(regular(REPO / 'sharp-markets/docs/PRICE_ENGINE_PREREGISTRATION.md')),
                           'stat_schema_source': str(schema_path.relative_to(REPO)),
                           'python': sys.version, 'pyarrow': __import__('pyarrow').__version__,
                           'settlement_source_sha256': sha(regular(settlement_path)), 'native_outcomes_read': False,
                           'source_commit': 'be40f2536f37e619b02c1f63bea756f69b6d28a4'},
            'held_groups': ['older/americanfootball_ncaaf/2021', 'older/americanfootball_ncaaf/2022',
                            'props/americanfootball_ncaaf/2023', 'props/americanfootball_ncaaf/2024', 'props/americanfootball_ncaaf/2025']}


if __name__ == '__main__':
    with (RUNTIME / 'followup-purchase.lock').open('rb') as lock:
        fcntl.flock(lock, fcntl.LOCK_SH | fcntl.LOCK_NB)
        output = run()
    print(json.dumps(output, indent=2, sort_keys=True))
