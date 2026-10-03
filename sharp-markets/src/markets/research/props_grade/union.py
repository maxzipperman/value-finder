"""Exact NFL2023–25 acquired union, quotes/eligibility only; no grading entry point."""
from __future__ import annotations
import argparse
import ast
from collections import Counter, defaultdict
import fcntl
import json
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace

if __package__:
    from . import archive as A
else:
    import archive as A

REPO = Path(__file__).resolve().parents[5]
READINESS = REPO / 'reviews/post151-readiness/readiness.json'
READINESS_SHA = 'acd2009728d88370465ce8da85e16d61ec2ca7489b3491005b304cdd9622530c'
ROOT = 'c7d3ea3d938918735e3ec99f9b56652f67f4f200c93f233385b4d6429fbe1376'
RUNTIME = Path.home() / 'Library/Application Support/ValueFinder/football-acquisition-state'
SEASONS = (2023, 2024, 2025)
DENOMINATORS = {2023: 294, 2024: 308, 2025: 285}
SLOTS = ('T24', 'CLOSE_T10')
# Reviewed logical-input mapping; original absolute paths remain provenance only.
DURABLE_INPUTS = {
    'baseline.json': 'strategy-research/pass150-timeout-recovery-v1/untouched-successor-final/baseline.json',
    'frame.json': 'strategy-research/coverage-pilot-packet-v1/pilot-successor-142/frame.json',
    'denominators.json': 'strategy-research/coverage-pass-residual-v1/passing-groups-2020-24/denominators.json',
    'mappings.json': 'strategy-research/pass150-timeout-recovery-v1/exact-stop-certificate/successor-mappings.json',
    'source/FREEZE.json': 'strategy-research/football_archive/acquisition/football-archive-v4/FREEZE.json',
}
SOURCE_DIR = 'strategy-research/football_archive/acquisition/football-archive-v4'
HOLDS = ('timing_stat_amendment_not_adopted', 'candidate_book_note_inactive',
         'registration_variant_lineage_unresolved', 'roster_game_player_identity_unverified',
         'mainline_selection_not_applied', 'participation_unverified', 'book_settlement_terms_unverified')


def validate_games(games):
    """Validate the entire requested scope before any cache read."""
    ids, opportunities = set(), set()
    for game in games:
        gid, season = game['game_id'], game['season']
        if (season not in SEASONS or game['stratum'] != f'props/{A.NFL}/{season}'
                or not (gid.startswith(f'{A.NFL}/{season}/') or
                        gid.startswith(f'{A.NFL}/provider-only/{season}/'))):
            raise ValueError('Unsupported or sealed union game')
        if gid in ids: raise ValueError('Duplicate game identity')
        ids.add(gid)
        ops = game['source_opportunities']
        if len(ops) != 2 or {o['slot'] for o in ops} != set(SLOTS):
            raise ValueError('Fixed slot denominator differs')
        for op in ops:
            if op['opportunity_id'] in opportunities: raise ValueError('Duplicate opportunity identity')
            opportunities.add(op['opportunity_id'])
            # Jan/Feb playoff decisions belong to the prior season. No2026-season game.
            at = A.stamp(op['requested_utc'])
            date_season = at.year if at.month >= 3 else at.year - 1
            if date_season != season: raise ValueError('Sealed or unsupported decision clock')
    if dict(Counter(g['season'] for g in games)) != DENOMINATORS:
        raise ValueError('Fixed union game denominator differs')


def load_pure(path, name, pin):
    raw = A.checked(path, pin)
    module = ModuleType(name); sys.modules[name] = module
    exec(compile(raw, str(path), 'exec'), module.__dict__)
    return module


def resolved_input(name, provenance, repo=REPO):
    """Use exactly reviewed repo bytes, verified before use; never original tmp paths."""
    if name not in DURABLE_INPUTS: raise ValueError('Undeclared logical input')
    return A.checked(Path(repo) / DURABLE_INPUTS[name], provenance['bound_inputs'][name]['sha256'])


def metadata(runtime):
    evidence = json.loads(A.checked(READINESS, READINESS_SHA))
    if evidence['root'] != ROOT or evidence['grading_enabled'] or evidence['provenance']['native_outcomes_read']:
        raise ValueError('Wrong accepted readiness evidence')
    provenance = evidence['provenance']; bound = provenance['bound_inputs']
    def read(name): return json.loads(resolved_input(name, provenance))
    frame, denoms, maps, baseline, source_freeze = (read(n) for n in
        ('frame.json', 'denominators.json', 'mappings.json', 'baseline.json', 'source/FREEZE.json'))
    selected = {d['game_id'] for d in denoms if d['stratum'].startswith(f'props/{A.NFL}/')}
    games = [g for g in frame if g['game_id'] in selected or g['stratum'] == f'props/{A.NFL}/2025']
    validate_games(games)
    source_dir = REPO / SOURCE_DIR
    canonical = json.loads(A.checked(source_dir / 'canonical-games.json', provenance['canonical_metadata_sha256']))
    observations = json.loads(A.checked(source_dir / 'provider-observations.json', provenance['provider_observations_sha256']))
    pins = source_freeze['file_sha256']
    if pins['canonical-games.json'] != provenance['canonical_metadata_sha256']:
        raise ValueError('Independent schedule pin differs')
    ledgers = {root: json.loads(A.checked(runtime / root / 'spending-ledger.json', pin))
               for root, pin in provenance['ledger_pins'].items()}
    own = ledgers[ROOT]
    if own.get('status') != 'pilot_complete' or own.get('pending') or own.get('stopped'):
        raise ValueError('Accepted successor no longer terminal')
    return evidence, games, {m['game_id']: m for m in maps}, baseline, canonical, observations, ledgers


def readers(provenance):
    timing = load_pure(REPO / 'strategy-research/coverage-pilot-v1/timing.py', 'timing', provenance['timing_sha256'])
    classifier = load_pure(REPO / 'strategy-research/coverage-pilot-v1/classifier.py', 'union_classifier', provenance['classifier_sha256'])
    path = REPO / 'strategy-research/coverage-pilot-completion-v1/report.py'
    tree = ast.parse(A.checked(path, provenance['merged_saved_record_source_sha256']))
    functions = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in ('canonical', 'saved_record')]
    namespace = {'json': json}
    exec(compile(ast.Module(body=functions, type_ignores=[]), str(path), 'exec'), namespace)
    diagnostic = REPO / 'reviews/post151-readiness/diagnostic.py'
    tree = ast.parse(A.checked(diagnostic, provenance['diagnostic_sha256']))
    function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'frozen_failures_for_slot')
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(diagnostic), 'exec'), namespace)
    return timing, classifier, namespace['saved_record'], namespace['frozen_failures_for_slot']


def normalize_op(game, op, binding, canonical):
    provider, anchor = binding['provider_kickoff_utc'], canonical['scheduled_utc']
    return dict(op, season=game['season'], provider_id=binding['event_id'], game_identity=game['game_id'],
                identity_type=game['identity_type'], provider_kickoff_utc=provider, anchor_utc=anchor,
                binding_observed_utc=binding['binding_observed_utc'], home_team=binding['home_team'],
                away_team=binding['away_team'], schedule_discrepancy_minutes=
                (A.stamp(provider)-A.stamp(anchor)).total_seconds()/60)


def pair_flags(quotes, accepted):
    """Pair only within authenticated responses. Conflicting duplicate prices stay held."""
    groups = defaultdict(list)
    for row in quotes:
        row['quote_pair_eligible'] = False
        row['grading_enabled'] = False
        if row['eligibility_reasons']: continue
        key = (row['market'], row['book'], row['description'], row['point'])
        groups[key].append(row)
    for key, rows in groups.items():
        prices = defaultdict(set)
        for row in rows: prices[row['side']].add(row['price'])
        conflict = any(len(v) > 1 for v in prices.values())
        for row in rows:
            if conflict: row['eligibility_reasons'].append('conflicting_duplicate_quote')
            row['quote_pair_eligible'] = (key in accepted.get(row['request_id'], set())
                                          and not row['eligibility_reasons'])
            row['grading_enabled'] = False
    return quotes


def read_union(runtime, *, mode='dry-run'):
    if mode not in ('dry-run', 'eligibility'): raise ValueError('No grading/outcome mode exists')
    runtime = Path(runtime).absolute()
    if runtime != RUNTIME.absolute(): raise ValueError('Only accepted shared runtime is supported')
    with (runtime / 'followup-purchase.lock').open('rb') as lock:
        fcntl.flock(lock, fcntl.LOCK_SH | fcntl.LOCK_NB)
        return project(runtime, mode)


def project(runtime, mode):
    evidence, games, maps, baseline, canonical, observations, ledgers = metadata(runtime)
    provenance = evidence['provenance']; canonical = {g['canonical_game_id']: g for g in canonical}
    timing, classifier, saved_record, frozen_failures = readers(provenance)
    cache, statuses, coverage = {}, Counter(), defaultdict(Counter)
    all_quotes = []
    for game in games:
        gid = game['game_id']; mapping = maps.get(gid, {})
        rids = set(mapping.get('request_ids', []) + mapping.get('reused_request_ids', []) +
                   game.get('certainty_evidence', {}).get('source_request_ids', []))
        for reuse in mapping.get('reused_slots', []): rids.update(c['request_id'] for c in reuse['evidence'])
        for op in game['source_opportunities']:
            statuses['fixed_opportunities'] += 1
            for market in A.PRIMARY:
                for book in evidence_book_panel():
                    coverage[(game['season'], op['slot'], market, book)]['game_denominator'] += 1
            if game['identity_type'] != 'canonical' or gid not in canonical:
                statuses['unresolved_identity_opportunities'] += 1
                continue
            forced = frozen_failures(mapping, op['slot'])
            if forced:
                statuses['frozen_ineligible_opportunities'] += 1
                continue
            binding = classifier.bind_asof(observations, gid, op['requested_utc'])
            cell = (game['season'], op['slot'])
            coverage[cell]['game_denominator'] += 1
            if binding['status'] != 'bound': statuses['unbound_opportunities'] += 1; continue
            if mode == 'dry-run': continue
            quotes, accepted, matched = [], {}, 0
            for rid in sorted(rids):
                claim = provenance['receipt_projection'].get(rid)
                if not claim: continue  # Explicit missing opportunity below, never cache-scan a substitute.
                if rid not in cache:
                    root = claim['root']; attempt = ledgers[root]['attempts'][rid]
                    if (attempt['status'] not in ('completed', 'missing') or
                            any(attempt[k] != claim[k] for k in ('status', 'receipt_sha256', 'response_sha256'))):
                        raise ValueError('Accepted receipt projection differs')
                    path = Path(attempt['response_path']).absolute()
                    if not path.is_relative_to(runtime / root / 'data/raw') or path.suffix != '.parquet':
                        raise ValueError('Raw record path escapes accepted root')
                    cache[rid] = (saved_record(runtime / root, rid, attempt,
                        SimpleNamespace(regular=A.regular, digest=A.digest),
                        legacy=root in baseline['base_snapshot']['ledgers']), attempt['status'])
                record, status = cache[rid]
                params = json.loads(record['params_json'])
                if params['date'] != op['requested_utc']: continue
                if record['sport'] != A.NFL or not record['url'].endswith('/events/'+binding['event_id']+'/odds'):
                    raise ValueError('Fixed slot cached request identity differs')
                matched += 1
                if status == 'missing': statuses['terminal_missing_records'] += 1; continue
                if record['http_status'] != 200: raise ValueError('Completed record is not HTTP200')
                body = json.loads(record['body'])
                norm = normalize_op(game, op, binding, canonical[gid])
                request = dict(request_id=rid, event_id=binding['event_id'], requested_utc=op['requested_utc'], seasons=[game['season']])
                # Scope checked by generalized trusted archive reader before quote traversal.
                offered = A.quote_rows(request, [norm], record, set(evidence_book_panel()), season=game['season'])
                result = classifier.slot_pairs(body, requested=op['requested_utc'], execution=op['requested_utc'],
                    binding=binding, independent_kickoff=canonical[gid]['scheduled_utc'], slot=op['slot'],
                    candidate_books=evidence_book_panel(), markets=A.PRIMARY)
                accepted[rid] = result['pairs']
                for row in offered:
                    if row['market'] not in A.PRIMARY: continue
                    if (row['market'], row['book'], row['description'], row['point']) not in result['pairs']:
                        row['eligibility_reasons'].append('no_eligible_same_response_pair')
                    quotes.append(row)
            if not matched: statuses['missing_designated_opportunities'] += 1
            quotes = pair_flags(quotes, accepted)
            if not quotes: statuses['opportunities_without_offered_primary_rows'] += 1
            for market in A.PRIMARY:
                for book in evidence_book_panel():
                    rows = [r for r in quotes if r['market']==market and r['book']==book]
                    eligible = {(r['description'], r['point']) for r in rows if r['quote_pair_eligible']}
                    c = coverage[(game['season'], op['slot'], market, book)]
                    c['games_with_quote_pairs'] += bool(eligible)
                    c['provider_label_games_with_quote_pairs'] += len({p[0] for p in eligible})
                    c['complete_pair_keys'] += len(eligible)
            all_quotes.extend(quotes)
    for root, pin in provenance['ledger_pins'].items(): A.checked(runtime / root / 'spending-ledger.json', pin)
    summary = dict(mode=mode, fixed_games=DENOMINATORS, fixed_opportunities=sum(DENOMINATORS.values())*2,
        statuses=dict(statuses), authenticated_records=len(cache), accepted_readiness_sha256=READINESS_SHA,
        ledger_pins=provenance['ledger_pins'], durable_input_mapping=DURABLE_INPUTS,
        original_input_provenance=provenance['bound_inputs'], classifier_sha256=provenance['classifier_sha256'],
        timing_sha256=provenance['timing_sha256'], original_final_sha256=provenance['original_final_sha256'],
        reader_sha256=A.digest(A.regular(Path(__file__))), archive_reader_sha256=A.digest(A.regular(Path(A.__file__))),
        grading_enabled=False, outcomes_read=False, actual_play_certified=False, book='draftkings',
        book_status='conditional candidate, not active selection', holds=list(HOLDS),
        raw_quote_rows_exported=False, eligible_quote_rows=sum(r['quote_pair_eligible'] for r in all_quotes),
        row_exclusions=dict(Counter(reason for r in all_quotes for reason in r['eligibility_reasons'])),
        coverage=[dict(season=k[0],slot=k[1],market=k[2],book=k[3],**v) for k,v in sorted(coverage.items()) if len(k)==4])
    return all_quotes, summary


def evidence_book_panel():
    return ['pinnacle','lowvig','betonlineag','draftkings','fanduel','betmgm','williamhill_us','fanatics','betrivers','espnbet']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=('dry-run', 'eligibility'), default='dry-run')
    args = parser.parse_args()
    _, report = read_union(RUNTIME, mode=args.mode)
    print(json.dumps(report, indent=2, sort_keys=True))

if __name__ == '__main__': main()
