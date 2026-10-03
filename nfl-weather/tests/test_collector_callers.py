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
