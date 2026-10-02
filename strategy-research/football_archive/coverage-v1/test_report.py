"""Offline report tests; fake historical bodies only, no credentials or runtime mutation."""
from datetime import datetime, timedelta, timezone
import copy
import json
from pathlib import Path
import shutil
import sys
sys.dont_write_bytecode = True
import pytest
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import report


def deny(event, args):
    if event in ('socket.connect', 'socket.getaddrinfo'): raise RuntimeError('Tests prohibit network')
    if event == 'open' and isinstance(args[0], (str, bytes)):
        path = str(args[0])
        if Path(path).name in ('.env', 'player_week.parquet', 'pricing_cohort.json', 'game_outcomes.parquet') or '/data/forward/' in path:
            raise RuntimeError('Tests prohibit credentials/outcomes/holdout')


sys.addaudithook(deny)
PACKET = HERE.parent / 'execution-v1/F2'
BUNDLE = HERE.parent / 'acquisition/football-archive-v4'
PROTOCOL = json.loads((BUNDLE / 'protocol.json').read_text())


def fixture():
    books = ['pinnacle', 'lowvig']
    m = {'books': books}
    ops, rows, responses = [], [], {}
    for index, slot in enumerate(('T24', 'CLOSE_T10')):
        at = '2025-09-04T00:05:00Z' if slot == 'T24' else '2025-09-04T23:55:00Z'
        row = {'request_id': f'r{index}', 'requested_utc': at}
        op = {'opportunity_id': f'g/{slot}', 'request_id': row['request_id'], 'game_identity': 'g', 'season': 2025,
            'identity_type': 'canonical', 'slot': slot, 'status': 'planned', 'home_team': 'A', 'away_team': 'B',
            'anchor_utc': '2025-09-05T00:05:00Z', 'provider_kickoff_utc': '2025-09-05T00:05:00Z',
            'close_primary_status': 'scheduled_guard_pending_quote_validation', 'requested_utc': at}
        stamp = report.ts(at) - timedelta(minutes=5)
        body = {'timestamp': stamp.isoformat(), 'previous_timestamp': (stamp-timedelta(minutes=5)).isoformat(),
            'next_timestamp': (stamp+timedelta(minutes=5)).isoformat(), 'data': {'commence_time': op['anchor_utc'],
                'home_team': 'A', 'away_team': 'B', 'bookmakers': []}}
        for b in books:
            markets = []
            for key, sides in [('alternate_spreads', ['A','B']), ('alternate_totals', ['Over','Under'])]:
                markets.append({'key': key, 'last_update': body['timestamp'], 'outcomes': [
                    {'name': side, 'point': point, 'price': 1.9} for side in sides for point in [40,42]]})
            body['data']['bookmakers'].append({'key': b, 'markets': markets})
        rows.append(row); ops.append(op); responses[row['request_id']] = {'body': body, 'reason': None}
    return m, rows, ops, responses


def summary(data): return report.summarize(*data, PROTOCOL)


def test_same_book_both_slots_curves_and_denominators():
    result = summary(fixture())
    assert result['denominators']['book_market_cells'] == 8
    assert result['paired_games'][0]['paired_both_markets_books'] == ['pinnacle','lowvig']
    assert all(c['counts']['fresh_curve'] == c['counts']['denominator'] for c in result['book_market_coverage'])
    assert not result['actual_play_certified'] and not result['outcomes_joined'] and not result['purchase_authorized']


def test_different_books_at_each_slot_do_not_pair():
    data = fixture()
    data[3]['r0']['body']['data']['bookmakers'].pop()
    data[3]['r1']['body']['data']['bookmakers'].pop(0)
    result = summary(data)
    assert result['paired_games'][0]['paired_both_markets_books'] == []
    assert len(result['market_exclusions']) == 4


@pytest.mark.parametrize('mode', ['empty', 'missing_market', 'stale', 'future', 'single_point', 'bad_price', 'time_missing', 'duplicate_book', 'duplicate_market', 'malformed_markets', 'malformed_outcomes'])
def test_market_failures_stay_in_denominator(mode):
    data = fixture(); body = data[3]['r0']['body']; book = body['data']['bookmakers'][0]; market = book['markets'][0]
    if mode == 'empty': body['data']['bookmakers'] = []
    if mode == 'missing_market': book['markets'].pop(0)
    if mode == 'stale': market['last_update'] = (report.ts(body['timestamp']) - timedelta(hours=1)).isoformat()
    if mode == 'future': market['last_update'] = (report.ts(body['timestamp']) + timedelta(seconds=1)).isoformat()
    if mode == 'single_point': market['outcomes'] = [o for o in market['outcomes'] if o['point'] == 40]
    if mode == 'bad_price':
        for o in market['outcomes']: o['price'] = float('nan')
    if mode == 'time_missing': market.pop('last_update')
    if mode == 'duplicate_book': body['data']['bookmakers'].append(copy.deepcopy(book))
    if mode == 'duplicate_market': book['markets'].append(copy.deepcopy(market))
    if mode == 'malformed_markets': book['markets'] = {}
    if mode == 'malformed_outcomes': market['outcomes'] = {}
    result = summary(data)
    assert result['denominators']['book_market_cells'] == 8 and result['market_exclusions']
    assert 'pinnacle' not in result['paired_games'][0]['paired_both_markets_books']


@pytest.mark.parametrize('mode', ['provider_only', 'orientation', 'missing_clock', 'after_clock', 'close_discrepancy'])
def test_scheduled_safety_separate_from_raw_curves(mode):
    data = fixture(); op = data[2][1]; body = data[3]['r1']['body']
    if mode == 'provider_only': op['identity_type'] = 'provider-only'
    if mode == 'orientation': body['data']['home_team'] = 'B'
    if mode == 'missing_clock': body['data'].pop('commence_time')
    if mode == 'after_clock': body['data']['commence_time'] = body['timestamp']
    if mode == 'close_discrepancy': body['data']['commence_time'] = '2025-09-05T00:15:00Z'
    result = summary(data)
    assert not result['opportunities'][1]['scheduled_safe'] and result['opportunities'][1]['fresh_curve_books']
    assert not any(g['paired_both_markets_books'] for g in result['paired_games'])
    assert all(not o['actual_play_certified'] for o in result['opportunities'])


def test_unbound_and_missing_response_are_explicit():
    data = fixture(); data[2][0]['status'] = 'not_bound'; data[3]['r1'] = {'body': None, 'reason': 'missing_or_unresolved_response'}
    result = summary(data)
    assert len(result['market_exclusions']) == 8 and not any(o['response_valid'] for o in result['opportunities'])


def test_actual_frozen_inventory_full_denominators_with_fake_empty_bodies():
    m, rows, ops, seed = report.verify_packet(PACKET, report.F2_ROOT)
    responses = {row['request_id']: {'body': {'data': {'bookmakers': []}, 'timestamp': row['requested_utc']}, 'reason': None} for row in rows}
    result = report.summarize(m, rows, ops, responses, PROTOCOL)
    assert result['denominators']['opportunities'] == 1774 and result['denominators']['request_slots'] == 1773
    assert result['denominators']['books'] == 10 and result['denominators']['book_market_cells'] == 35480
    assert len(result['market_exclusions']) == 35480 and len(result['opportunities']) == 1774
    assert result['empty_bookmakers_responses'] == 1773
    assert sum(c['counts']['denominator'] for c in result['book_market_coverage']) == 35480


@pytest.mark.parametrize('mode', ['code', 'packet', 'symlink', 'unexpected'])
def test_frozen_packet_corruption(tmp_path, mode):
    clone = tmp_path / 'execution-v1'; shutil.copytree(PACKET.parent, clone)
    if mode == 'code': (clone / 'epoch.py').write_text('raise RuntimeError("sentinel")')
    if mode == 'packet': (clone / 'F2/requests.json').write_text('[]')
    if mode == 'symlink':
        (clone / 'plan.py').unlink(); (clone / 'plan.py').symlink_to(PACKET.parent / 'plan.py')
    if mode == 'unexpected': (clone / 'extra.py').write_text('')
    with pytest.raises((ValueError, OSError)): report.verify_packet(clone / 'F2', report.F2_ROOT)


def atomic(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True, default=str))


@pytest.fixture
def saved(tmp_path, monkeypatch):
    import pyarrow as pa
    import pyarrow.parquet as pq
    monkeypatch.setattr(report, 'RUNTIME_BASE', tmp_path / 'runtime')
    m, rows, ops, responses = fixture()
    m.update(new_credits=20, request_set_sha256='set', request_list_sha256='csv')
    rows = rows[:1]; ops = ops[:1]
    row = rows[0]; row.update(max_new_credits=20, cache_key='key', sport='americanfootball_nfl',
        source='oddsapi/hist_event_odds', path='/historical/sports/americanfootball_nfl/events/e/odds', params={'date': row['requested_utc']}, event_id='e')
    prior_path = report.RUNTIME_BASE / report.SOURCE_ROOT / 'spending-ledger.json'
    prior = {'bundle_root_sha256': report.SOURCE_ROOT, 'probe_credits':1687, 'status':'recent_complete_stopped_before_older',
        'pending':None,'stopped':None,'attempts':{},'other_usage_reserved':84529}
    atomic(prior_path, prior)
    seed = {'root':report.SOURCE_ROOT,'probe_credits':1687,'ledger_path':str(prior_path),
        'ledger_sha256':report.sha(prior_path),'cumulative_debit_without_probe':84529}
    monkeypatch.setattr(report,'verify_packet',lambda *args:(m,rows,ops,seed))
    monkeypatch.setattr(report,'protocol_from',lambda *args:PROTOCOL)
    body=responses['r0']['body']; body['data'].update(id='e',sport_key=row['sport'])
    record={'cache_key':'key','sport':row['sport'],'source':row['source'],'url':'https://api.the-odds-api.com/v4'+row['path'],
        'params_json':json.dumps(row['params']),'http_status':200,'headers_json':json.dumps({'x-requests-last':'20','x-requests-used':'84549','x-requests-remaining':'4915451'}),
        'body':json.dumps(body),'fetched_at':datetime(2026,10,2,tzinfo=timezone.utc)}
    cache=tmp_path/'cache.parquet'; pq.write_table(pa.Table.from_pylist([record]),cache)
    ledger=report.RUNTIME_BASE/report.F2_ROOT/'spending-ledger.json'
    receipt=ledger.parent/'receipts/r0.json'
    atomic(receipt,{'request_id':'r0','cache_key':'key','record_sha256':report.sha(cache),'record':record})
    attempt={'status':'completed','reserved_credits':20,'billed_credits':20,'response_path':str(cache),
        'response_sha256':report.sha(cache),'receipt_sha256':report.sha(receipt)}
    state={'bundle_root_sha256':report.F2_ROOT,'predecessor_seed':seed,'status':'event_epoch_complete',
        'pending':None,'stopped':None,'attempts':{'r0':attempt},'cache_reuse':{},'probe_credits':1687,
        'slice_cap':20,'other_usage_reserved':84529,'provider_used':84549,'provider_remaining':4915451}
    atomic(ledger,state)
    return ledger,cache,receipt,state


def test_saved_cache_receipt_and_accounting_read_only(saved):
    ledger,cache,receipt,state=saved; hashes=[report.sha(p) for p in (ledger,cache,receipt)]
    result=report.build_report(PACKET,report.F2_ROOT,BUNDLE,ledger)
    assert result['acquisition_complete'] and result['accounting']['cumulative_reserved']==86236
    assert hashes==[report.sha(p) for p in (ledger,cache,receipt)]


@pytest.mark.parametrize('mode',['cache','receipt','ancestor','pending','cap','extra_attempt','debit_reduced'])
def test_integrity_and_completion_failures(saved,mode):
    ledger,cache,receipt,state=saved
    if mode=='cache': cache.write_bytes(b'changed')
    if mode=='receipt': receipt.write_text('{}')
    if mode=='ancestor': Path(state['predecessor_seed']['ledger_path']).write_text('{}')
    if mode=='pending': state.update(pending='r0',status='running'); atomic(ledger,state)
    if mode=='cap': state['slice_cap']=0; atomic(ledger,state)
    if mode=='extra_attempt': state['attempts']['extra']=state['attempts']['r0']; atomic(ledger,state)
    if mode=='debit_reduced': state['other_usage_reserved']-=1; atomic(ledger,state)
    with pytest.raises((ValueError, OSError)): report.build_report(PACKET,report.F2_ROOT,BUNDLE,ledger)


def test_incomplete_404_retains_reservation_and_is_not_completion(saved):
    ledger,cache,receipt,state=saved
    state.update(status='halted',pending='r0',stopped='retain')
    state['attempts']['r0'].update(status='pending',observed_http_status=404)
    atomic(ledger,state); before=report.sha(ledger)
    result=report.build_report(PACKET,report.F2_ROOT,BUNDLE,ledger,allow_incomplete=True)
    assert not result['acquisition_complete'] and result['response_evidence'][0]['observed_http_status']==404
    assert result['accounting']['new_reserved']==20 and before==report.sha(ledger)
    assert len(result['market_exclusions'])==4


def test_snapshot_change_is_rejected(saved,monkeypatch):
    ledger,cache,receipt,state=saved
    original=report.summarize
    def changing(*args):
        result=original(*args); state['provider_used']+=1; atomic(ledger,state); return result
    monkeypatch.setattr(report,'summarize',changing)
    with pytest.raises(ValueError,match='changed during report'): report.build_report(PACKET,report.F2_ROOT,BUNDLE,ledger)
