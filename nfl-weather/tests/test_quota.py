"""The free-tier guard (issue #15): an Odds API failure or a low quota must mean "no price", never a
crashed alert run, and manual runs must leave the alerts' credits alone. Uses fake responses; no API calls."""
import json
import sys
from pathlib import Path

import pandas as pd
import pytest
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nflweather import board, oddsapi, quota  # noqa: E402


class Fake:
    def __init__(self, status=200, body=(), remaining="400", last="1"):
        self.status_code, self._body = status, list(body)
        self.ok = 200 <= status < 300
        self.headers = {"x-requests-remaining": remaining, "x-requests-used": "100", "x-requests-last": last}

    def json(self):
        return self._body


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(quota, "STATE", tmp_path / "quota.json")
    monkeypatch.setattr(oddsapi, "CACHE", tmp_path / "oddsapi")
    monkeypatch.setenv("ODDS_API_KEY", "test-key")
    monkeypatch.delenv("XPC_SERVICE_NAME", raising=False)


def calls(monkeypatch, response):
    seen = []

    def get(url, params=None, timeout=None):
        seen.append(url)
        if isinstance(response, Exception):
            raise response
        return response

    monkeypatch.setattr(oddsapi.session, "get", get)
    return seen


@pytest.mark.parametrize("status", [429, 500, 503])
def test_http_errors_become_no_price(monkeypatch, status):
    calls(monkeypatch, Fake(status=status, remaining="0"))
    with pytest.raises(SystemExit):
        oddsapi.live(markets=("totals",))
    assert board._pinnacle_live() is None  # the board falls back to nflverse lines instead of crashing
    assert quota.read()["remaining"] == 0


def test_network_error_becomes_no_price(monkeypatch):
    calls(monkeypatch, requests.ConnectionError("down"))
    assert board._pinnacle_live() is None


def test_manual_run_below_floor_makes_no_call(monkeypatch):
    quota.STATE.write_text(json.dumps(dict(utc=pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%dT%H:%M:%SZ"),
                                           remaining=quota.MANUAL_FLOOR - 1)))
    seen = calls(monkeypatch, Fake())
    assert board._pinnacle_live() is None
    assert seen == []


def test_scheduled_run_still_calls_below_manual_floor(monkeypatch):
    monkeypatch.setenv("XPC_SERVICE_NAME", "com.nflweather.alerts")
    quota.STATE.write_text(json.dumps(dict(utc=pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%dT%H:%M:%SZ"),
                                           remaining=5)))
    seen = calls(monkeypatch, Fake(remaining="4"))
    oddsapi.live(markets=("totals",))
    assert len(seen) == 1
    quota.STATE.write_text(json.dumps(dict(utc=pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%dT%H:%M:%SZ"),
                                           remaining=0)))
    with pytest.raises(SystemExit):  # nothing left at all: skip rather than collect a 429
        oddsapi.live(markets=("totals",))
    assert len(seen) == 1


def test_last_months_quota_is_ignored(monkeypatch):
    quota.STATE.write_text(json.dumps(dict(utc="2020-01-15T00:00:00Z", remaining=0)))
    assert quota.read() is None and quota.check() is None


def test_success_is_cached_with_credit_headers(monkeypatch):
    body = [{"id": "e1", "home_team": "Dallas Cowboys", "away_team": "Tampa Bay Buccaneers",
             "commence_time": "2026-10-09T00:15:00Z",
             "bookmakers": [{"key": "pinnacle", "markets": [{"key": "totals", "last_update": "x", "outcomes": [
                 {"name": "Over", "price": -105, "point": 47.5}, {"name": "Under", "price": -115, "point": 47.5}]}]}]}]
    calls(monkeypatch, Fake(body=body))
    df = oddsapi.live(markets=("totals",))
    assert df.iloc[0].total == 47.5 and df.iloc[0].under_price == -115
    cached = json.loads(next((oddsapi.CACHE / "live").glob("*.json")).read_text())
    assert cached["credits_last"] == "1" and cached["credits_remaining"] == "400"
