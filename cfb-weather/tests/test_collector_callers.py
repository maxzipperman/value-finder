"""Actual CFB poll script/helper stay disabled; fixtures contain no live data."""
import json
from pathlib import Path
import runpy
import sys

import pandas as pd
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from cfbweather import board, config, fetch, live, quota
from ops import collector_guard

NAMES={'Wyoming Cowboys':'Wyoming','Air Force Falcons':'Air Force'}


@pytest.fixture
def isolated(tmp_path,monkeypatch):
    monkeypatch.setattr(config,'ROOT',tmp_path)
    monkeypatch.setattr(config,'RAW',tmp_path/'raw')
    monkeypatch.setattr(fetch,'RAW',tmp_path/'raw')
    monkeypatch.setattr(quota,'STATE',tmp_path/'quota.json')
    monkeypatch.setenv('ODDS_API_KEY','CFB_SYNTHETIC_ONLY')
    monkeypatch.setenv('ODDS_API_TIER','paid')
    monkeypatch.setenv('ODDS_QUOTA_KIND','background')
    monkeypatch.setattr(board,'odds_team_names',lambda:NAMES)
    declared=tmp_path/'declared.json'
    declared.write_text(json.dumps({'shared_writers':['legacy-writer'],'external_state':'ready'}))
    monkeypatch.setenv('VF_COLLECTOR_ENVELOPE',str(declared))
    monkeypatch.setenv('VF_COLLECTOR_ENVELOPE_SHA256',collector_guard.digest(declared.read_bytes()))
    calls=[]
    def get(*a,**kw):calls.append(a);raise AssertionError('Paid transport must be unreachable')
    monkeypatch.setattr(fetch.session,'get',get)
    return tmp_path,calls


def test_actual_live_totals_cannot_send_with_populated_declarations(isolated):
    root,calls=isolated
    assert 'enforcement bridge not implemented' in live.live_totals(NAMES)
    assert calls==[]
    assert not list(root.rglob('*_poll.json'))


def test_actual_poll_script_routes_to_disabled_admission(isolated,monkeypatch,capsys):
    root,calls=isolated
    fwd=root/'data'/'forward';fwd.mkdir(parents=True)
    kick=pd.Timestamp.now(tz='UTC')+pd.Timedelta(days=2)
    pd.DataFrame([dict(snapshot_utc=pd.Timestamp.now(tz='UTC').isoformat(),game_id='synthetic-cfb',
                       start_utc=kick.isoformat(),away_team='Air Force',home_team='Wyoming',
                       rule_b='no_price',wx_wind=17.5,lead_days=1)]).to_csv(fwd/'ledger.csv',index=False)
    monkeypatch.setattr(sys,'argv',['poll_triggers.py'])
    with pytest.raises(SystemExit):runpy.run_path(str(Path(__file__).resolve().parents[1]/'scripts'/'poll_triggers.py'),run_name='__main__')
    assert 'enforcement bridge not implemented' in capsys.readouterr().out
    assert calls==[]
    assert not (fwd/'trigger_polls.csv').exists()


@pytest.mark.parametrize('role', ['cfb-alert','cfb-close',None])
def test_all_cfb_totals_roles_held_without_test_gate(isolated,role):
    _,calls=isolated
    assert fetch.odds_api_totals(NAMES,role=role,request_slot='synthetic').empty
    assert calls==[]


def test_actual_cfb_roles_reserve_at_common_boundary_and_manual_denied(isolated,monkeypatch):
    from ops.shared_account_testkit import synthetic_account, synthetic_current_occurrence
    root,_=isolated
    params=dict(bookmakers=','.join(fetch.LIVE_BOOKS),markets='totals',oddsFormat='american',dateFormat='iso')
    with synthetic_account(root/'account','CFB_SYNTHETIC_ONLY',params) as (session,state):
        monkeypatch.setattr(fetch,'session',session)
        for role in ('cfb-alert','cfb-close'):
            assert fetch.odds_api_totals(NAMES,role=role,request_slot=synthetic_current_occurrence() if role=='cfb-alert' else 'synthetic-observation').empty
        assert isinstance(live.live_totals(NAMES),pd.DataFrame)
        used_before=quota.read()['used']
        files={p:p.read_bytes() for p in (root/'raw'/'oddsapi'/'live').glob('*.json')}
        fetch.odds_api_totals(NAMES,role='cfb-close',request_slot='synthetic-observation')
        assert len(session.calls)==3
        assert quota.read()['used']==used_before
        assert all(p.read_bytes()==b for p,b in files.items())
        assert fetch.odds_api_totals(NAMES).empty # manual has no role
        assert len(session.calls)==3
        assert {a['label'] for a in state()['attempts'].values()}=={'cfb-alert','cfb-close','cfb-trigger'}


@pytest.mark.parametrize('scheduled,delayed,later',[
    ('2026-10-03T14:30:00Z','2026-10-03T16:01:00Z','2026-10-03T18:30:00Z'),
    ('2026-12-03T15:30:00Z','2026-12-03T16:01:00Z','2026-12-03T19:30:00Z')])
def test_actual_alert_delayed_and_next_occurrence_send_separately_with_stable_replay(isolated,monkeypatch,scheduled,delayed,later):
    from datetime import datetime,timedelta,timezone
    from ops.shared_account_testkit import synthetic_account
    root,_=isolated
    decision=[collector_guard.utc(delayed)]
    class Clock(datetime):
        @classmethod
        def now(cls,tz=None):return decision[0].astimezone(tz or timezone.utc)
    monkeypatch.setattr(collector_guard,'datetime',Clock);monkeypatch.setattr(quota,'check',lambda:None)
    params=dict(bookmakers=','.join(fetch.LIVE_BOOKS),markets='totals',oddsFormat='american',dateFormat='iso')
    with synthetic_account(root/'account','CFB_SYNTHETIC_ONLY',params,now=decision[0],expires_after=timedelta(days=1)) as (session,state):
        monkeypatch.setattr(fetch,'session',session)
        fetch.odds_api_totals(NAMES,role='cfb-alert',request_slot=scheduled)
        decision[0]+=timedelta(seconds=30)
        fetch.odds_api_totals(NAMES,role='cfb-alert',request_slot=scheduled)
        assert len(session.calls)==1
        decision[0]=collector_guard.utc(later)
        fetch.odds_api_totals(NAMES,role='cfb-alert',request_slot=later)
        assert len(session.calls)==2 and len(state()['attempts'])==2
        assert {a['slot'] for a in state()['attempts'].values()}=={scheduled,later}
        stamps={json.loads(p.read_text())['snapshot_utc'] for p in (root/'raw'/'oddsapi'/'live').glob('*.json')}
        assert stamps=={delayed,later}
        assert fetch.odds_api_totals(NAMES,role='cfb-alert').empty
        assert len(session.calls)==2
