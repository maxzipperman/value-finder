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
