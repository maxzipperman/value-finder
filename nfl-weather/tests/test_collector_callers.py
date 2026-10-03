"""Actual NFL caller chains on synthetic paths; production must stay disabled."""
import json
from pathlib import Path
import runpy
import sys

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from nflweather import config, fetch, live, oddsapi, quota
from ops import collector_guard

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
KEY = 'NFL_SYNTHETIC_ONLY'


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(config, 'ROOT', tmp_path)
    monkeypatch.setattr(oddsapi, 'ROOT', tmp_path)
    monkeypatch.setattr(oddsapi, 'CACHE', tmp_path / 'raw' / 'oddsapi')
    monkeypatch.setattr(quota, 'STATE', tmp_path / 'quota.json')
    monkeypatch.setattr(oddsapi, 'api_key', lambda: KEY)
    monkeypatch.setenv('ODDS_API_KEY', KEY)
    monkeypatch.setenv('ODDS_API_TIER', 'paid')
    monkeypatch.setenv('ODDS_QUOTA_KIND', 'background')
    # Populated declarations intentionally cannot enable production.
    declared = tmp_path / 'declared.json'
    declared.write_text(json.dumps({'shared_writers':['legacy-writer'], 'external_state':'ready'}))
    monkeypatch.setenv('VF_COLLECTOR_ENVELOPE', str(declared))
    monkeypatch.setenv('VF_COLLECTOR_ENVELOPE_SHA256', collector_guard.digest(declared.read_bytes()))
    calls = []
    events = []
    class R:
        status_code, ok, headers = 200, True, {}
        @property
        def text(self): return json.dumps(events)
        def json(self): return events
    def get(url, **kwargs):
        calls.append(url)
        assert url.endswith('/events'), 'Paid transport must be unreachable'
        return R()
    monkeypatch.setattr(fetch.session, 'get', get)
    return tmp_path, calls, events


def test_actual_tag_poll_cannot_send_with_populated_declarations(isolated):
    root, calls, _ = isolated
    with pytest.raises(oddsapi.OddsAPIUnavailable, match='enforcement bridge not implemented'):
        oddsapi.live(markets=('totals',), tag='poll')
    assert calls == []
    assert not list(root.rglob('*.receipt.json'))


def test_actual_poll_script_routes_tag_to_disabled_admission(isolated, monkeypatch, capsys):
    root, calls, _ = isolated
    kick = (pd.Timestamp.now(tz='UTC') + pd.Timedelta(days=2)).tz_convert('America/New_York')
    fwd = root / 'data' / 'forward'; fwd.mkdir(parents=True)
    pd.DataFrame([dict(snapshot_utc=pd.Timestamp.now(tz='UTC').isoformat(),game_id='synthetic-nfl',
                       gameday=kick.strftime('%Y-%m-%d'),gametime=kick.strftime('%H:%M'),
                       away_team='CHI',home_team='GB',rule_b='negative_ev',wx_wind=16.2,lead_days=2)]).to_csv(fwd/'ledger.csv',index=False)
    monkeypatch.setattr(sys,'argv',['poll_triggers.py'])
    with pytest.raises(SystemExit):runpy.run_path(str(SCRIPTS/'poll_triggers.py'),run_name='__main__')
    assert 'enforcement bridge not implemented' in capsys.readouterr().out
    assert calls == []
    assert not (fwd/'trigger_polls.csv').exists()


def test_actual_props_script_lists_free_events_but_never_sends_due_paid_slot(isolated, monkeypatch, capsys):
    root, calls, events = isolated
    kick = pd.Timestamp.now(tz='UTC') + pd.Timedelta(hours=24) - pd.Timedelta(minutes=5)
    events.append(dict(id='synthetic-props',commence_time=kick.isoformat(),
                       home_team='Green Bay Packers',away_team='Chicago Bears'))
    monkeypatch.setattr(sys,'argv',['log_props.py'])
    runpy.run_path(str(SCRIPTS/'log_props.py'),run_name='__main__')
    output = capsys.readouterr().out
    assert 'enforcement bridge not implemented' in output
    assert 'not automatically resent' in output
    assert len(calls) == 1 and calls[0].endswith('/events')
    assert not (root/'data'/'forward'/'props_state.json').exists()
    assert not list(root.rglob('*_T24.json'))


@pytest.mark.parametrize('role', ['nfl-alert','nfl-close','nfl-trigger',None])
def test_all_nfl_live_roles_are_held_without_test_gate(isolated,role):
    _,calls,_=isolated
    from ops.shared_account_testkit import synthetic_current_occurrence
    with pytest.raises(oddsapi.OddsAPIUnavailable,match='enforcement bridge not implemented'):
        oddsapi.live(markets=('totals',),role=role,request_slot=synthetic_current_occurrence() if role=='nfl-alert' else 'synthetic')
    assert calls==[]


def test_actual_nfl_roles_reserve_at_common_boundary_then_replay_original_clock(isolated,monkeypatch):
    from ops.shared_account_testkit import synthetic_account, synthetic_current_occurrence
    root,_,_=isolated
    params=dict(bookmakers=','.join(oddsapi.LIVE_BOOKS),markets='totals',oddsFormat='american',dateFormat='iso')
    with synthetic_account(root/'account',KEY,params) as (session,state):
        monkeypatch.setattr(oddsapi,'session',session)
        for role in ('nfl-alert','nfl-close','nfl-trigger'):
            oddsapi.live(markets=('totals',),role=role,request_slot=synthetic_current_occurrence() if role=='nfl-alert' else 'synthetic-observation',tag='poll' if role=='nfl-trigger' else None)
        used_before=quota.read()['used']
        first_files={p:p.read_bytes() for p in (oddsapi.CACHE/'live').glob('*.json')}
        oddsapi.live(markets=('totals',),role='nfl-close',request_slot='synthetic-observation')
        assert len(session.calls)==3
        assert quota.read()['used']==used_before
        assert {a['label'] for a in state()['attempts'].values()}=={'nfl-alert','nfl-close','nfl-trigger'}
        assert all(p.read_bytes()==b for p,b in first_files.items())
        with pytest.raises(oddsapi.OddsAPIUnavailable):
            oddsapi.live(markets=('totals',)) # manual cannot invent a role
        with pytest.raises(oddsapi.OddsAPIUnavailable):
            oddsapi.historical(pd.Timestamp('2025-01-01T00:00Z')) # no authority/adapter
        assert len(session.calls)==3


def test_actual_props_boundary_reserves_nine_markets(isolated,monkeypatch):
    from ops.shared_account_testkit import synthetic_account, synthetic_current_occurrence
    root,_,_=isolated
    params=dict(bookmakers=','.join(live.PROP_BOOKS),markets=','.join(live.PROP_MARKETS),
                oddsFormat=live.PROP_ODDS_FORMAT,dateFormat='iso')
    with synthetic_account(root/'account',KEY,params) as (session,state):
        monkeypatch.setattr(oddsapi,'session',session)
        oddsapi._get(f'/sports/{oddsapi.SPORT}/events/synthetic/odds',params,
                     collector_label='nfl-props',request_slot='synthetic:24')
        a=next(iter(state()['attempts'].values()))
        assert a['label']=='nfl-props' and a['reserved']==len(live.PROP_MARKETS)
        assert len(session.calls)==1


def test_board_helper_explicitly_forwards_alert_role(isolated,monkeypatch):
    from nflweather import board
    seen=[]
    monkeypatch.setattr(oddsapi,'live',lambda **kwargs:(seen.append(kwargs) or pd.DataFrame()))
    assert board._pinnacle_live(role='nfl-alert') is None
    assert seen==[{'markets':('totals',),'role':'nfl-alert','request_slot':None}]


@pytest.mark.parametrize('scheduled,delayed,later',[
    ('2026-10-03T14:30:00Z','2026-10-03T16:01:00Z','2026-10-03T18:30:00Z'),
    ('2026-12-03T15:30:00Z','2026-12-03T16:01:00Z','2026-12-03T19:30:00Z')])
def test_actual_alert_delayed_and_next_occurrence_send_separately_with_stable_replay(isolated,monkeypatch,scheduled,delayed,later):
    from datetime import datetime,timedelta,timezone
    from ops.shared_account_testkit import synthetic_account
    root,_,_=isolated
    decision=[collector_guard.utc(delayed)]
    class Clock(datetime):
        @classmethod
        def now(cls,tz=None):return decision[0].astimezone(tz or timezone.utc)
    monkeypatch.setattr(collector_guard,'datetime',Clock)
    monkeypatch.setattr(quota,'check',lambda:None)
    params=dict(bookmakers=','.join(oddsapi.LIVE_BOOKS),markets='totals',oddsFormat='american',dateFormat='iso')
    with synthetic_account(root/'account',KEY,params,now=decision[0],expires_after=timedelta(days=1)) as (session,state):
        monkeypatch.setattr(oddsapi,'session',session)
        oddsapi.live(markets=('totals',),role='nfl-alert',request_slot=scheduled)
        decision[0]+=timedelta(seconds=30)
        oddsapi.live(markets=('totals',),role='nfl-alert',request_slot=scheduled)
        assert len(session.calls)==1
        decision[0]=collector_guard.utc(later)
        oddsapi.live(markets=('totals',),role='nfl-alert',request_slot=later)
        assert len(session.calls)==2 and len(state()['attempts'])==2
        assert {a['slot'] for a in state()['attempts'].values()}=={scheduled,later}
        stamps={json.loads(p.read_text())['snapshot_utc'] for p in (oddsapi.CACHE/'live').glob('*.json')}
        assert stamps=={pd.Timestamp(delayed).strftime('%Y-%m-%dT%H%MZ'),pd.Timestamp(later).strftime('%Y-%m-%dT%H%MZ')}
        with pytest.raises(oddsapi.OddsAPIUnavailable):oddsapi.live(markets=('totals',),role='nfl-alert')
        assert len(session.calls)==2
