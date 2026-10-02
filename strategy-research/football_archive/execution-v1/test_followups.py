"""Offline adversarial tests using the real frozen transport/cache/accounting library."""
import copy
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import shutil
import sys

import pytest

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import plan
import epoch
import reconcile
import pilot_coverage as followup_coverage

BUNDLE = HERE.parent / 'acquisition/football-archive-v4'


def deny_network(event, args):
    if event in ('socket.connect', 'socket.getaddrinfo'):
        raise RuntimeError('Offline tests prohibit network')
    if event == 'open' and isinstance(args[0], (str, bytes)):
        name = str(args[0])
        if Path(name).name in ('.env', 'player_week.parquet', 'pricing_cohort.json', 'game_outcomes.parquet') or '/data/forward/' in name:
            raise RuntimeError('Offline tests prohibit credentials and holdout logs')


sys.addaudithook(deny_network)


def approval(root, manifest):
    commit = 'b' * 40
    cost = manifest['new_credits']
    body = (f"APPROVED paid run: list {manifest['request_list_sha256']}, request-set {manifest['request_set_sha256']}, "
            f"budget {cost} credits, commit {commit}\nAPPROVED account ceiling: max-baseline-used 100000, root {root}")
    return {'status': 'approved', 'bundle_root_sha256': root, 'priority': 1, 'max_new_credits': cost,
            'human_authorization_evidence': 'SYNTHETIC OWNER ONLY', 'execution_commit': commit,
            'hub_go_ahead': {'status': 'approved', 'bundle_root_sha256': root,
                            'request_set_sha256': manifest['request_set_sha256'],
                            'request_list_sha256': manifest['request_list_sha256'], 'budget_credits': cost,
                            'commit': commit, 'comment_url': 'https://github.com/maxzipperman/value-finder/pull/99#issuecomment-1',
                            'comment_body': body},
            'account_reconciliation': {'status': 'approved', 'bundle_root_sha256': root,
                'baseline_mode': 'capture_first_free_check', 'reason': 'Synthetic accounting test',
                'owner_note': 'SYNTHETIC ONLY', 'max_baseline_used': 100000,
                'billing_period_utc': datetime.now(timezone.utc).strftime('%Y-%m')}}


class Response:
    def __init__(self, body, headers, status=200):
        self.text, self.headers, self.status_code = body, headers, status


class Session:
    def __init__(self, mode='ok'):
        from requests.adapters import HTTPAdapter
        self.adapters = {'https': HTTPAdapter(max_retries=0)}
        self.used, self.remaining = 84525, 4915475
        self.calls, self.mode = [], mode

    def get(self, url, params=None, **kwargs):
        assert kwargs['allow_redirects'] is False
        self.calls.append(url)
        if url.endswith('/sports'):
            return Response('[]', {'x-requests-last': '0', 'x-requests-used': str(self.used),
                                  'x-requests-remaining': str(self.remaining)})
        if self.mode == 'timeout':
            import requests
            raise requests.Timeout('synthetic failure')
        billed = 10 * len(params['markets'].split(','))
        self.used += billed
        self.remaining -= billed
        headers = {'x-requests-last': str(billed), 'x-requests-used': str(self.used),
                   'x-requests-remaining': str(self.remaining)}
        at = plan.ts(params['date'])
        stamp = at - timedelta(minutes=5)
        if self.mode == 'lag':
            stamp -= timedelta(minutes=10)
        if self.mode == 'future':
            stamp = at + timedelta(minutes=1)
        body = {'timestamp': plan.iso(stamp), 'previous_timestamp': plan.iso(stamp - timedelta(minutes=5)),
                'next_timestamp': plan.iso(stamp + timedelta(minutes=5)),
                'data': {'id': url.split('/')[-2], 'sport_key': plan.NFL, 'bookmakers': []}}
        if self.mode == 'wrong_event':
            body['data']['id'] = 'wrong'
        if self.mode == 'list_body':
            body['data'] = [body['data']]
        if self.mode == 'bad_billing':
            headers.pop('x-requests-last')
        if self.mode == 'overcharge':
            headers['x-requests-last'] = str(billed + 1)
            headers['x-requests-used'] = str(self.used + 1)
        if self.mode == 'external':
            headers['x-requests-used'] = str(self.used + 101)
        if self.mode == 'reset':
            headers['x-requests-used'] = '0'
            headers['x-requests-remaining'] = '5000000'
        if self.mode == 'echo':
            body['echo'] = 'SYNTHETIC_KEY_ONLY'
        status = {'429': 429, '500': 500, '404': 404, '403': 403}.get(self.mode, 200)
        return Response(json.dumps(body), headers, status)

    def close(self):
        pass


@pytest.fixture
def prepared(tmp_path, monkeypatch):
    base = epoch.source_executor(BUNDLE)
    monkeypatch.setattr(base, 'RUNTIME_BASE', tmp_path / 'state')
    monkeypatch.setattr(epoch, 'ROOT_BASE', tmp_path / 'state')
    monkeypatch.setattr(epoch, 'source_executor', lambda _: base)
    monkeypatch.setattr(epoch, 'checkout_clean', lambda _: None)
    # These inherited transport/accounting tests isolate the real frozen library.
    # Separate stage tests exercise the unmocked pilot and ancestor guards.
    monkeypatch.setattr(epoch, 'stage_guard', lambda *args: None)
    monkeypatch.setattr(base, 'checkout_commit', lambda _: 'b' * 40)
    packet = tmp_path / 'pilot'
    full = tmp_path / 'full'
    plan.build(BUNDLE, full, 'F2')
    plan.pilot(full, packet)
    prior_path = epoch.ROOT_BASE / plan.SOURCE_ROOT / 'spending-ledger.json'
    base.atomic(prior_path, {'bundle_root_sha256': plan.SOURCE_ROOT, 'probe_credits': 1687,
        'attempts': {'old': {'reserved_credits': 82830, 'status': 'completed'}},
        'other_usage_reserved': 1695, 'pending': None, 'stopped': None,
        'status': 'recent_complete_stopped_before_older'})
    monkeypatch.setattr(epoch, 'SEED_HASH', plan.sha(prior_path))
    base.atomic(packet / 'seed.json', {'root': plan.SOURCE_ROOT, 'ledger_path': str(prior_path),
        'ledger_sha256': plan.sha(prior_path), 'cumulative_debit_without_probe': 84525, 'probe_credits': 1687})
    reconcile.reconcile(packet, BUNDLE, [str(tmp_path / 'empty-raw')])
    base.atomic(packet / 'coverage-gate.json', followup_coverage.GATE)
    root = epoch.freeze(packet)
    manifest = json.loads((packet / 'manifest.json').read_text())
    auth = approval(root, manifest)
    return packet, root, auth, base


def run(prepared, session=None, checkpoint=lambda _: None):
    packet, root, auth, _ = prepared
    return epoch.run(packet, root, BUNDLE, auth, key='SYNTHETIC_KEY_ONLY', fake_session=session or Session(), checkpoint=checkpoint)


def ledger(prepared):
    _, root, _, base = prepared
    return json.loads((base.runtime_path(root) / 'spending-ledger.json').read_text())


def test_real_inventory_pilot_and_scope(prepared):
    packet, root, _, _ = prepared
    m, rows = epoch.verify_packet(packet, root)
    epoch.verify_source_plan(packet, BUNDLE, m, rows)
    assert len(rows) == 48 and m['new_credits'] == 960
    assert set(y for r in rows for y in r['seasons']) == {2023, 2024, 2025}
    assert all(r['priority'] == 1 and not r['sealed'] and r['retry_allowance'] == 0 for r in rows)


def test_complete_and_resume_without_rebuy(prepared):
    first = Session()
    result = run(prepared, first)
    assert result['new_billed'] == result['new_reserved'] == 960
    assert result['cumulative_reserved'] == 87172
    assert len(first.calls) == 49
    second = Session()
    second.used, second.remaining = first.used, first.remaining
    assert run(prepared, second)['new_billed'] == 960 and len(second.calls) == 1


@pytest.mark.parametrize('point', ['after_reservation', 'after_transport', 'after_receipt_durability'])
def test_crash_never_resends(prepared, point):
    def crash(at):
        if at == point:
            raise RuntimeError('synthetic crash')
    first = Session()
    with pytest.raises(RuntimeError):
        run(prepared, first, crash)
    state = ledger(prepared)
    assert state['pending'] and sum(a['reserved_credits'] for a in state['attempts'].values()) == 20
    second = Session()
    with pytest.raises(Exception):
        run(prepared, second)
    assert not second.calls
    assert ledger(prepared)['attempts'] == state['attempts']


@pytest.mark.parametrize('mode', ['timeout', 'lag', 'future', 'wrong_event', 'list_body', 'bad_billing',
                                 'overcharge', 'external', 'reset', 'echo', '429', '500', '404', '403'])
def test_transport_fault_stops_after_one_paid_attempt(prepared, mode):
    session = Session(mode)
    with pytest.raises(Exception):
        run(prepared, session)
    state = ledger(prepared)
    assert len(session.calls) == 2 and state['pending'] and state['stopped']
    assert sum(a['reserved_credits'] for a in state['attempts'].values()) >= 20
    assert state['probe_credits'] + state['other_usage_reserved'] >= 86212


@pytest.mark.parametrize('field', ['request_list_sha256', 'request_set_sha256', 'commit', 'budget_credits'])
def test_exact_approval_tampering_before_key_read(prepared, field):
    packet, root, auth, _ = prepared
    auth['hub_go_ahead'][field] = 'wrong'
    reads = []
    with pytest.raises(Exception):
        epoch.run(packet, root, BUNDLE, auth, key=lambda: reads.append('key'), fake_session=Session())
    assert not reads


def test_changed_predecessor_before_key_read(prepared):
    packet, root, auth, _ = prepared
    seed = json.loads((packet / 'seed.json').read_text())
    Path(seed['ledger_path']).write_text('{}')
    reads = []
    with pytest.raises(Exception, match='Predecessor ledger changed'):
        epoch.run(packet, root, BUNDLE, auth, key=lambda: reads.append('key'), fake_session=Session())
    assert not reads


def test_deleted_runtime_cannot_reset(prepared):
    run(prepared)
    _, root, _, base = prepared
    shutil.rmtree(base.runtime_path(root))
    with pytest.raises(Exception, match='missing'):
        run(prepared)


@pytest.mark.parametrize('filename', ['requests.json', 'opportunities.json', 'manifest.json', 'seed.json', 'cache-reconciliation.json'])
def test_every_packet_input_bound(prepared, filename):
    packet, root, _, _ = prepared
    with (packet / filename).open('ab') as f:
        f.write(b' ')
    with pytest.raises(ValueError, match='frozen bytes'):
        epoch.verify_packet(packet, root)


def test_symlink_packet_refused(prepared):
    packet, _, _, _ = prepared
    (packet / 'extra').symlink_to(packet / 'seed.json')
    with pytest.raises(ValueError, match='regular'):
        epoch.freeze(packet)


def test_later_predecessor_preserves_ancestors_and_blocks_rebuy(prepared):
    run(prepared)
    _, root, _, base = prepared
    path = base.runtime_path(root) / 'spending-ledger.json'
    state = json.loads(path.read_text())
    seed = {'root': root, 'ledger_path': str(path), 'ledger_sha256': plan.sha(path),
            'probe_credits': 1687, 'cumulative_debit_without_probe': 84525 + 960}
    assert epoch.seed_state(seed, []) == 85485
    with pytest.raises(ValueError, match='twice'):
        epoch.seed_state(seed, [{'request_id': 'old', 'max_new_credits': 20}])
    rid = next(iter(state['attempts']))
    with pytest.raises(ValueError, match='twice'):
        epoch.seed_state(seed, [{'request_id': rid, 'max_new_credits': 20}])


def synthetic():
    game = {'canonical_game_id': 'g', 'sport': plan.NFL, 'season': 2025,
            'scheduled_utc': '2025-09-05T00:05:00Z', 'close_anchor_utc': '2025-09-05T00:05:00Z'}
    observation = {'sport': plan.NFL, 'season': 2025, 'canonical_game_id': 'g', 'provider_id': 'p',
                   'returned_utc': '2025-09-01T05:55:00Z', 'provider_kickoff_utc': '2025-09-05T00:05:00Z',
                   'home_team': 'A', 'away_team': 'B', 'source_cache_key': 'key', 'source_body_sha256': 'digest'}
    return game, observation


def test_future_provider_id_and_midnight_do_not_change_entry():
    game, o = synthetic()
    future = dict(o, provider_id='future', returned_utc='2025-09-04T12:00:00Z')
    rows, ops = plan.plan('F2', [game], [o, future], [str(n) for n in range(10)])
    entry = next(op for op in ops if op['slot'] == 'T24')
    assert entry['requested_utc'] == '2025-09-04T00:05:00Z' and entry['provider_id'] == 'p'
    assert len(rows) == 2


def test_simultaneous_provider_ids_remain_denominator():
    game, o = synthetic()
    rows, ops = plan.plan('F2', [game], [o, dict(o, provider_id='other')], list(map(str, range(10))))
    assert not rows and len(ops) == 2
    assert all(op['status'] == 'ambiguous_provider_ids_at_latest_available_sweep' for op in ops)


def test_provider_only_cancelled_contingent_not_silently_excluded():
    _, o = synthetic()
    o['canonical_game_id'] = None
    rows, ops = plan.plan('F2', [], [o], list(map(str, range(10))))
    assert len(rows) == len(ops) == 2 and all(op['identity_type'] == 'provider-only' for op in ops)


def test_conflicting_id_across_games_quarantined():
    game, o = synthetic()
    other_game = dict(game, canonical_game_id='other')
    other_obs = dict(o, canonical_game_id='other')
    rows, ops = plan.plan('F2', [game, other_game], [o, other_obs], list(map(str, range(10))))
    assert not rows and len(ops) == 4
    assert all(op['status'] == 'provider_id_maps_to_multiple_canonical_games' for op in ops)


def test_observed_earlier_provider_kickoff_prevents_inplay_request():
    game, o = synthetic()
    o['provider_kickoff_utc'] = '2025-09-04T23:00:00Z'
    rows, ops = plan.plan('F2', [game], [o], list(map(str, range(10))))
    assert len(rows) == 1
    assert next(op for op in ops if op['slot'] == 'CLOSE_T10')['status'] == 'at_or_after_provider_kickoff_as_observed_before_slot'


def test_sealed_2026_not_in_inventory():
    game, o = synthetic()
    game['season'] = o['season'] = 2026
    assert plan.plan('F2', [game], [o], list(map(str, range(10)))) == ([], [])


def test_new_cache_overlap_stops_before_key(prepared):
    packet, root, auth, _ = prepared
    row = json.loads((packet / 'requests.json').read_text())[0]
    raw = json.loads((packet / 'cache-reconciliation.json').read_text())['raw_roots'][0]
    cache = Path(raw) / row['sport'] / row['source'] / '2026-10-01' / f"{row['cache_key']}.parquet"
    cache.parent.mkdir(parents=True)
    cache.write_bytes(b'synthetic existing key')
    reads = []
    with pytest.raises(Exception, match='overlapping cache'):
        epoch.run(packet, root, BUNDLE, auth, key=lambda: reads.append('key'), fake_session=Session())
    assert not reads


@pytest.mark.parametrize('budget', ['first_tranche_cumulative_credits', 'day_one_cumulative_ceiling', 'broader_cumulative_ceiling'])
def test_prior_debit_counts_against_every_cumulative_cap(prepared, monkeypatch, budget):
    base = prepared[3]
    real_class = epoch.event_ledger(base)
    class Capped(real_class):
        def __init__(self, folder, protocol, *args, **kwargs):
            protocol = copy.deepcopy(protocol)
            protocol['budgets'][budget] = 86211
            super().__init__(folder, protocol, *args, **kwargs)
    monkeypatch.setattr(epoch, 'event_ledger', lambda _: Capped)
    session = Session()
    with pytest.raises(Exception, match='Cumulative budget'):
        run(prepared, session)
    assert not session.calls and ledger(prepared)['other_usage_reserved'] == 84525


def test_account_baseline_ceiling_blocks_paid_calls(prepared):
    session = Session()
    session.used, session.remaining = 100001, 4899999
    with pytest.raises(Exception, match='max_baseline_used'):
        run(prepared, session)
    assert len(session.calls) == 1 and not ledger(prepared)['attempts']


def test_cache_and_receipt_changes_block_resumed_sends(prepared):
    first = Session()
    run(prepared, first)
    state = ledger(prepared)
    receipt = prepared[3].runtime_path(prepared[1]) / 'receipts' / f"{next(iter(state['attempts']))}.json"
    receipt.write_text('{}')
    second = Session()
    second.used, second.remaining = first.used, first.remaining
    with pytest.raises(Exception, match='evidence missing/changed'):
        run(prepared, second)
    assert not second.calls


def test_csv_mismatch_rejected_even_with_updated_digest(prepared):
    packet, _, _, _ = prepared
    path = packet / 'request-list.csv'
    path.write_text(path.read_text().replace('alternate_spreads,alternate_totals', 'alternate_spreads,player_pass_yds', 1))
    m = json.loads((packet / 'manifest.json').read_text())
    m['request_list_sha256'] = plan.sha(path)
    (packet / 'manifest.json').write_bytes(plan.canonical(m))
    root = epoch.freeze(packet)
    with pytest.raises(ValueError, match='CSV differs'):
        epoch.verify_packet(packet, root)


def test_f3a_cannot_expand_to_2024(prepared):
    packet, _, _, _ = prepared
    m = json.loads((packet / 'manifest.json').read_text())
    m['pull'] = 'F3a'
    (packet / 'manifest.json').write_bytes(plan.canonical(m))
    root = epoch.freeze(packet)
    with pytest.raises(ValueError, match='seasons'):
        epoch.verify_packet(packet, root)


def test_empty_quote_coverage_fails_without_outcomes(prepared):
    run(prepared)
    packet, root, _, base = prepared
    result = followup_coverage.report(packet, root, BUNDLE, base.runtime_path(root) / 'spending-ledger.json')
    assert not result['remainder_gate_passed'] and result['paired_canonical_games'] == 0
    assert result['response_and_quote_coverage']['valid_responses'] == 48
    assert not result['outcomes_joined'] and not result['profits_computed']


def curve_context():
    op = {'home_team': 'A', 'away_team': 'B'}
    row = {'requested_utc': '2025-09-05T00:00:00Z'}
    body = {'timestamp': '2025-09-04T23:55:00Z'}
    market = {'key': 'alternate_totals', 'last_update': body['timestamp'],
              'outcomes': [{'name': side, 'point': line, 'price': 1.9} for side in ('Over', 'Under') for line in (40, 42)]}
    protocol = json.loads((BUNDLE / 'protocol.json').read_text())
    return market, {}, op, row, body, protocol


def test_fresh_curves_and_stale_curves_are_distinguished():
    args = curve_context()
    assert followup_coverage.market_curve(*args)
    args[0]['last_update'] = '2025-09-04T23:39:59Z'
    assert not followup_coverage.market_curve(*args)
    args[0]['last_update'] = '2025-09-04T23:55:01Z'
    assert not followup_coverage.market_curve(*args)


def test_single_line_is_not_an_alternate_curve():
    args = curve_context()
    args[0]['outcomes'] = [o for o in args[0]['outcomes'] if o['point'] == 40]
    assert not followup_coverage.market_curve(*args)


def test_quote_missing_time_not_imputed_from_snapshot():
    args = curve_context()
    del args[0]['last_update']
    assert not followup_coverage.market_curve(*args)


def test_fresh_paired_curves_pass_gate_without_strategy_grade(prepared):
    packet, root, _, base = prepared
    ops = json.loads((packet / 'opportunities.json').read_text())
    by_key = {(o['provider_id'], o['requested_utc']): o for o in ops if o['status'] == 'planned'}
    class Curves(Session):
        def get(self, url, params=None, **kwargs):
            response = super().get(url, params, **kwargs)
            if url.endswith('/sports'):
                return response
            body = json.loads(response.text)
            op = by_key[body['data']['id'], params['date']]
            body['data'].update(commence_time=op['provider_kickoff_utc'], home_team=op['home_team'], away_team=op['away_team'])
            markets = []
            for key, sides, points in [('alternate_spreads', (op['home_team'], op['away_team']), (-3, -5)),
                                       ('alternate_totals', ('Over', 'Under'), (40, 42))]:
                markets.append({'key': key, 'last_update': body['timestamp'],
                                'outcomes': [{'name': side, 'point': point, 'price': 1.9} for side in sides for point in points]})
            body['data']['bookmakers'] = [{'key': 'pinnacle', 'markets': markets}]
            response.text = json.dumps(body)
            return response
    run(prepared, Curves())
    result = followup_coverage.report(packet, root, BUNDLE, base.runtime_path(root) / 'spending-ledger.json')
    assert result['remainder_gate_passed'] and result['paired_canonical_games'] >= 12
    assert all(result['paired_by_season'][y] >= 4 for y in (2023, 2024, 2025))
    assert not result['profits_computed'] and not result['outcomes_joined'] and not result['purchase_authorized']


@pytest.mark.parametrize('mode', ['ceiling_tamper', 'debit_override', 'global_pending', 'global_stopped'])
def test_extension_offline_account_and_global_guards(prepared, mode):
    packet, root, auth, base = prepared
    if mode == 'ceiling_tamper': auth['account_reconciliation']['max_baseline_used'] = 300000
    if mode == 'debit_override': auth['account_reconciliation']['pre_run_other_usage_budget_debit'] = 0
    if mode.startswith('global_'):
        base.atomic(epoch.ROOT_BASE / ('a' * 64) / 'spending-ledger.json',
            {'pending': 'other' if mode == 'global_pending' else None,
             'stopped': 'unresolved' if mode == 'global_stopped' else None})
    reads = []; session = Session()
    with pytest.raises(Exception):
        epoch.run(packet, root, BUNDLE, auth, key=lambda: reads.append(1), fake_session=session)
    assert not reads and not session.calls
