"""Synthetic-only repair tests. No real outcomes, runtime, credentials or API."""
from argparse import Namespace
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from markets.research.props_grade import archive as A, settlement as S
from markets.research.props_grade import grade, lines as L, fixture, run, roster


def sample():
    row = dict(request_id='request', event_id='event', requested_utc='2025-10-01T16:50:00Z',
               sport=A.NFL, seasons=[2025], sealed=False, opportunities=['op'])
    op = dict(opportunity_id='op', request_id='request', provider_id='event', season=2025,
              slot=A.CLOSE, status='planned', game_identity='game', identity_type='canonical',
              provider_kickoff_utc='2025-10-01T17:00:00Z', anchor_utc='2025-10-01T17:00:00Z',
              requested_utc=row['requested_utc'], binding_observed_utc='2025-09-30T00:00:00Z',
              schedule_discrepancy_minutes=0, home_team='Home', away_team='Away')
    event = dict(id='event', sport_key=A.NFL, commence_time='2025-10-01T17:00:00Z', home_team='Home', away_team='Away',
                 bookmakers=[dict(key='draftkings', last_update='2025-10-01T16:48:00Z', markets=[
                     dict(key=A.PRIMARY[0], outcomes=[dict(name='Over', description='Player', point=50.5, price=1.91)])])])
    record = dict(body=json.dumps(dict(timestamp=row['requested_utc'], previous_timestamp='2025-10-01T16:45:00Z',
                                      next_timestamp='2025-10-01T16:55:00Z', data=event)))
    return row, op, record


def test_t10_preserved_and_single_side_not_invented():
    row, op, record = sample()
    quotes = A.quote_rows(row, [op], record, {'draftkings', 'pinnacle'})
    assert len(quotes) == 1 and quotes[0]['role'] == 'CLOSE_T10'
    assert quotes[0]['side'] == 'Over' and quotes[0]['eligibility_reasons'] == []
    assert not quotes[0]['actual_play_certified']


@pytest.mark.parametrize('change,reason', [
    ('old_quote', 'quote_age_at_snapshot'), ('future_quote', 'quote_age_at_snapshot'),
    ('missing_quote', 'missing_quote_timestamp'), ('moved', 'not_scheduled_pregame'),
    ('conflict', 'kickoff_conflict'), ('late_binding', 'listing_binding_after_decision'),
])
def test_clocks_are_exclusions_not_silent_drops(change, reason):
    row, op, record = sample(); body = json.loads(record['body'])
    if change == 'old_quote': body['data']['bookmakers'][0]['last_update'] = '2025-10-01T16:20:00Z'
    if change == 'future_quote': body['data']['bookmakers'][0]['last_update'] = '2025-10-01T16:51:00Z'
    if change == 'missing_quote': body['data']['bookmakers'][0].pop('last_update')
    if change == 'moved': op['anchor_utc'] = row['requested_utc']
    if change == 'conflict': op['schedule_discrepancy_minutes'] = 6
    if change == 'late_binding': op['binding_observed_utc'] = '2025-10-01T16:51:00Z'
    record['body'] = json.dumps(body)
    quotes = A.quote_rows(row, [op], record, {'draftkings'})
    assert len(quotes) == 1 and reason in quotes[0]['eligibility_reasons']


def test_quote_age_both_clocks():
    _, op, record = sample(); event = json.loads(record['body'])['data']
    reasons = A.eligibility(op, event, A.stamp('2025-10-01T16:40:00Z'), A.stamp('2025-10-01T16:50:00Z'), '2025-10-01T16:24:59Z')
    assert {'quote_age_at_snapshot', 'quote_age_at_decision'} <= set(reasons)


def test_future_snapshot_refused():
    row, op, record = sample();body = json.loads(record['body']);body['timestamp'] = '2025-10-01T16:51:00Z'
    record['body'] = json.dumps(body)
    with pytest.raises(ValueError, match='snapshot clock'): A.quote_rows(row, [op], record, {'draftkings'})


def test_scope_refused_before_receipts(monkeypatch, tmp_path):
    row, op, _ = sample();row['seasons'] = [2026]
    with pytest.raises(ValueError, match='scope'): A.validate_scope([row], [op])
    row, op, _ = sample();op['season'] = 2026
    with pytest.raises(ValueError, match='scope'): A.validate_scope([row], [op])
    with pytest.raises(ValueError, match='Duplicate request'): A.validate_scope([row, row], [op])


def test_receipt_hash_and_symlink_refused(tmp_path):
    p = tmp_path/'receipt.json';p.write_text('{}')
    with pytest.raises(ValueError, match='hash'): A.checked(p, '0'*64)
    q = tmp_path/'link';q.symlink_to(p)
    with pytest.raises(ValueError, match='nonsymlink'): A.regular(q)


def test_coverage_counts_presence_once_and_keeps_missing_opportunities():
    row, op, record = sample();q = A.quote_rows(row, [op], record, {'draftkings', 'pinnacle'})
    # Duplicate sides/quotes and stale quotes do not select a different presence denominator.
    q = q + q + [dict(q[0], side='Under', eligibility_reasons=['quote_age_at_snapshot'])]
    report = A.summary(q, [op, dict(op, opportunity_id='missing')], {'request':'completed','other':'missing'}, {'draftkings','pinnacle'})
    assert report['coverage'][A.PRIMARY[0]] == {'pinnacle_player_games':0,'any_panel_player_games':1}
    assert report['opportunities_without_quote_rows'] == 1 and report['request_status']['missing'] == 1
    assert report['proposed_book'] == 'draftkings' and not report['grading_enabled']


@pytest.mark.parametrize('side,value,win,profit', [('Over',60,1,.9),('Under',60,0,-1),('Over',40,0,-1),('Under',40,1,.9)])
def test_side_uses_own_offered_price(side, value, win, profit):
    got = S.settle(side=side,line=50,decimal_price=1.9,value=value,participation='eligible',terms_verified=True)
    assert got.status == 'settled' and got.win == win and got.profit_per_unit == pytest.approx(profit)


@pytest.mark.parametrize('value,participation,status', [(50,'eligible','push'),(None,'void','void'),(None,'eligible','missing_statistic'),(0,'unknown','unknown_participation'),(float('inf'),'eligible','missing_statistic')])
def test_push_void_unknown_and_missing_separate(value, participation, status):
    got = S.settle(side='Under',line=50,decimal_price=2,value=value,participation=participation,terms_verified=True)
    assert got.status == status and got.win is None


def test_explicit_zero_kicking_and_unsupported_cfb():
    assert S.statistic(S.NFL,'player_kicking_points',{'fg_made':0,'pat_made':0}) == (0., '')
    assert S.statistic(S.NFL,'player_kicking_points',{'fg_made':1,'pat_made':2}) == (5., '')
    assert S.statistic(S.NFL,'player_kicking_points',{'fg_made':1}) == (None,'missing_statistic')
    assert S.statistic(S.CFB,'player_rush_yds',{'rushing_yards':100}) == (None,'unsupported_sport_or_market')
    assert S.statistic(S.NFL,'player_unknown',{}) == (None,'unsupported_sport_or_market')
    assert S.settle(side='Under',line=1,decimal_price=2,value=0,participation='eligible').status == 'unverified_settlement_terms'
    assert S.settle(side='Yes',line=1,decimal_price=2,value=0,participation='eligible',terms_verified=True).status == 'unsupported_side'


def test_dependence_key_excludes_price_side_book_time():
    k = S.exposure_key(sport=S.NFL,season=2025,game_id='g',player_id='p',market='player_rush_yds')
    assert len(k) == 5
    with pytest.raises(ValueError, match='sealed'): S.exposure_key(sport=S.NFL,season=2026,game_id='g',player_id='p',market='m')


def test_archive_cli_cannot_join_outcomes(monkeypatch):
    monkeypatch.setattr(A,'read_archive',lambda *_: pytest.fail('must refuse before quote reads'))
    with pytest.raises(ValueError, match='coverage only'):
        run.main(Namespace(archive_runtime='unused', fixture=False, book_recorded='draftkings', out=None))


def test_registered_grader_unknown_stat_never_becomes_zero(tmp_path):
    fx = fixture.build(tmp_path)
    games = L.schedule(fx.cfg, fx.cache);calls=L.f3_calls(fx.cfg,games,now=fixture.NOW)
    loaded=L.load(fx.cfg,calls,fx.cache,games)
    paths=run.Paths(fx.roster,fx.games,fx.player_week,fx.status,fx.prereg,check_git=False,out=tmp_path/'report')
    # Only synthetic parquet, not real outcomes.
    pw=pd.read_parquet(fx.player_week)
    pw.loc[pw.player_id=='00-D2','rushing_yards']=np.nan
    pw.to_parquet(fx.player_week)
    df,_,_=run.join(loaded.rows,fx.book,paths)
    target=df[(df.description=='Javonte Williams') & (df.market=='player_rush_yds')]
    assert not target.empty and set(target.status)=={L.MISSING_STAT} and target.win.isna().all()
    assert grade.season_medians(pw).query("player_id == '00-D2' and market == 'player_rush_yds'")['median'].isna().all()


def test_full_synthetic_handoff_binds_receipt_cache_and_exact_path(tmp_path, monkeypatch):
    import pyarrow as pa
    import pyarrow.parquet as pq
    row, op, record = sample()
    row.update(cache_key='key', source='oddsapi/hist_event_odds', path='/historical/sports/americanfootball_nfl/events/event/odds', params={'date':row['requested_utc']})
    record.update(cache_key='key', sport=A.NFL, source=row['source'], url='https://api.the-odds-api.com/v4'+row['path'],
                  params_json=json.dumps(row['params']), http_status=200)
    path=tmp_path/'data/raw'/A.NFL/row['source']/row['requested_utc'][:10]/'key.parquet'
    path.parent.mkdir(parents=True);pq.write_table(pa.Table.from_pylist([record]),path)
    receipt=dict(request_id='request',cache_key='key',record_sha256=A.digest(path.read_bytes()),record=record)
    receipts=tmp_path/'receipts';receipts.mkdir();rp=receipts/'request.json';rp.write_bytes(A.canonical(receipt))
    attempt=dict(status='completed',response_path=str(path),response_sha256=A.digest(path.read_bytes()),receipt_sha256=A.digest(rp.read_bytes()))
    state=dict(bundle_root_sha256=A.ROOT,pending=None,stopped=None,status='event_epoch_complete',attempts={'request':attempt})
    lp=tmp_path/'spending-ledger.json';lp.write_bytes(A.canonical(state))
    monkeypatch.setattr(A,'LEDGER_SHA',A.digest(lp.read_bytes()))
    monkeypatch.setattr(A,'packet_inputs',lambda *_: ({'books':['draftkings','pinnacle']},[row],[op]))
    quotes,report=A.read_archive(tmp_path)
    assert len(quotes)==1 and report['request_status']=={'completed':1}
    rp.write_text('{}')
    with pytest.raises(ValueError,match='hash'): A.read_archive(tmp_path)
    rp.write_bytes(A.canonical(receipt));path.write_bytes(b'changed response')
    with pytest.raises(ValueError,match='hash'): A.read_archive(tmp_path)


def test_primary_conflicting_rows_are_not_summed(tmp_path):
    fx=fixture.build(tmp_path)
    pw=pd.read_parquet(fx.player_week)
    other=pw[pw.player_id=='00-D2'].copy();other['rushing_yards']=99
    pd.concat([pw,other],ignore_index=True).to_parquet(fx.player_week)
    games=L.schedule(fx.cfg,fx.cache)
    loaded=L.load(fx.cfg,L.f3_calls(fx.cfg,games,now=fixture.NOW),fx.cache,games)
    paths=run.Paths(fx.roster,fx.games,fx.player_week,fx.status,fx.prereg,check_git=False,out=tmp_path/'report')
    df,_,_=run.join(loaded.rows,fx.book,paths)
    assert set(df[df.description=='Javonte Williams'].status)=={L.MISSING_STAT}


def test_real_committed_packet_metadata_only():
    manifest,requests,opportunities=A.packet_inputs()
    assert len(requests)==570 and Counter(o['slot'] for o in opportunities)=={'T24':285,'CLOSE_T10':285}
    assert manifest['scope_seasons']==[2025]


def test_response_season_refused_before_prices():
    row,op,record=sample();body=json.loads(record['body'])
    body['data']['commence_time']='2026-09-01T00:00:00Z'
    body['data']['bookmakers']=None  # traversal would fail with TypeError, not the explicit seal refusal
    record['body']=json.dumps(body)
    with pytest.raises(ValueError,match='sealed'): A.quote_rows(row,[op],record,{'draftkings'})
