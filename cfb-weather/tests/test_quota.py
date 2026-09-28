"""The free-tier guard (issue #15) for CFB: failures and a low quota mean "no price", manual runs leave
the alerts' credits alone, and every response is cached (cache-first). Uses fake responses; no API calls."""
import json
import sys
from pathlib import Path

import pandas as pd
import pytest
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cfbweather import fetch, quota  # noqa: E402

NAMES = {"New Mexico State Aggies": "New Mexico State", "Western Kentucky Hilltoppers": "Western Kentucky"}


class Fake:
    def __init__(self, status=200, body=(), remaining="400", last="1"):
        self.status_code, self._body = status, list(body)
        self.headers = {"x-requests-remaining": remaining, "x-requests-used": "100", "x-requests-last": last}

    def json(self):
        return self._body


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(quota, "STATE", tmp_path / "quota.json")
    monkeypatch.setattr(fetch, "RAW", tmp_path / "raw")
    monkeypatch.setenv("ODDS_API_KEY", "test-key")
    monkeypatch.delenv("XPC_SERVICE_NAME", raising=False)


def calls(monkeypatch, response):
    seen = []

    def get(url, params=None, timeout=None):
        seen.append(url)
        if isinstance(response, Exception):
            raise response
        return response

    monkeypatch.setattr(fetch.session, "get", get)
    return seen


@pytest.mark.parametrize("response", [Fake(status=429, remaining="0"), Fake(status=500),
                                      requests.ConnectionError("down")])
def test_failures_become_no_price(monkeypatch, response):
    calls(monkeypatch, response)
    assert fetch.odds_api_totals(NAMES).empty


def test_manual_run_below_floor_makes_no_call(monkeypatch):
    quota.STATE.write_text(json.dumps(dict(utc=pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%dT%H:%M:%SZ"),
                                           remaining=quota.MANUAL_FLOOR - 1)))
    seen = calls(monkeypatch, Fake())
    assert fetch.odds_api_totals(NAMES).empty and seen == []


def test_success_is_cached_and_parsed(monkeypatch):
    body = [{"id": "e1", "home_team": "New Mexico State Aggies", "away_team": "Western Kentucky Hilltoppers",
             "commence_time": "2026-10-02T00:00:00Z",
             "bookmakers": [{"key": "pinnacle", "markets": [{"key": "totals", "outcomes": [
                 {"name": "Over", "price": -108, "point": 55.5}, {"name": "Under", "price": -112, "point": 55.5}]}]}]}]
    calls(monkeypatch, Fake(body=body))
    df = fetch.odds_api_totals(NAMES)
    assert df.iloc[0].line_src == "pinnacle" and df.iloc[0].mkt_total == 55.5 and df.iloc[0].mkt_under == -112
    cached = json.loads(next((fetch.RAW / "oddsapi" / "live").glob("*.json")).read_text())
    assert cached["credits_last"] == "1" and len(cached["data"]) == 1
    assert quota.read()["remaining"] == 400


def test_team_names_match_across_accents_and_punctuation():
    assert fetch.norm_team("San José State Spartans") == fetch.norm_team("San Jose State Spartans")
    assert fetch.norm_team("Hawai'i Rainbow Warriors") == fetch.norm_team("Hawaii Rainbow Warriors")
    assert fetch.norm_team("Louisiana Ragin' Cajuns") == fetch.norm_team("Louisiana Ragin Cajuns")
