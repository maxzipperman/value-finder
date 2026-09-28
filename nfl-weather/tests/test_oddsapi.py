"""Odds API client (issue #15): 10 books for one credit, Pinnacle stays the rule's price,
a spent quota or API error never crashes the board, and historical snapshots carry the
API's own capture time. No network: session.get is replaced by a fake."""
import json
import sys
from pathlib import Path

import pandas as pd
import pytest
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nflweather import board, oddsapi  # noqa: E402


class Resp:
    def __init__(self, status=200, body=None, remaining=480, last=1):
        self.status_code, self._body = status, body if body is not None else []
        self.headers = {"x-requests-remaining": str(remaining), "x-requests-used": "20", "x-requests-last": str(last)}

    def json(self):
        return self._body


def totals(book, point, under, over=-110):
    return {"key": book, "markets": [{"key": "totals", "outcomes": [
        {"name": "Over", "price": over, "point": point}, {"name": "Under", "price": under, "point": point}]}]}


EVENT = {"id": "e1", "commence_time": "2026-10-11T17:00:00Z", "home_team": "Chicago Bears",
         "away_team": "Green Bay Packers",
         "bookmakers": [totals("pinnacle", 41.5, -108), totals("fanduel", 41.5, -102), totals("draftkings", 42.5, -110),
                        totals("bovada", 41.5, -115)]}


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setenv("ODDS_API_KEY", "test")
    monkeypatch.setattr(oddsapi, "CACHE", tmp_path / "oddsapi")
    monkeypatch.setattr(oddsapi, "QUOTA", tmp_path / "oddsapi" / "quota.json")
    calls = []

    def use(resp):
        def get(url, params=None, timeout=None):
            calls.append(params)
            if isinstance(resp, Exception):
                raise resp
            return resp
        monkeypatch.setattr(oddsapi.session, "get", get)
        return calls
    return use


def test_ten_books_cost_one_region():
    assert len(oddsapi.LIVE_BOOKS) <= 10 and oddsapi.LIVE_BOOKS[0] == oddsapi.RULE_BOOK == "pinnacle"


def test_live_logs_every_book_but_prices_at_pinnacle(api):
    calls = api(Resp(body=[EVENT]))
    pin = board._pinnacle_live()
    assert calls[0]["bookmakers"] == ",".join(oddsapi.LIVE_BOOKS) and calls[0]["markets"] == "totals"
    assert len(pin) == 1
    row = pin.iloc[0]
    assert (row.pin_total, row.pin_under) == (41.5, -108)                    # the rule's price is Pinnacle's
    assert (row.best_under, row.best_under_book) == (-102, "fanduel")       # best price at the same number
    saved = json.loads(next((oddsapi.CACHE / "live").glob("*.json")).read_text())
    assert len(saved["data"][0]["bookmakers"]) == 4                         # every book is kept on disk
    assert oddsapi.quota_left() == 480


@pytest.mark.parametrize("resp", [Resp(status=429), Resp(status=401), Resp(status=500),
                                  requests.ConnectionError("down")])
def test_api_failure_falls_back_instead_of_crashing(api, resp):
    api(resp)
    assert board._pinnacle_live() is None


def test_credit_floor_protects_the_alerts(api, tmp_path):
    calls = api(Resp(body=[EVENT]))
    oddsapi.QUOTA.parent.mkdir(parents=True, exist_ok=True)
    oddsapi.QUOTA.write_text(json.dumps(dict(month=oddsapi._month(), remaining=50)))
    with pytest.raises(oddsapi.OddsAPIUnavailable):
        oddsapi.live(markets=("totals",), floor=oddsapi.MANUAL_FLOOR)       # hand-run: refused
    assert calls == []
    oddsapi.live(markets=("totals",), floor=0)                               # scheduled alert: still runs
    assert len(calls) == 1
    oddsapi.QUOTA.write_text(json.dumps(dict(month="2000-01", remaining=0)))   # credits reset on the 1st
    oddsapi.live(markets=("totals",), floor=oddsapi.MANUAL_FLOOR)
    assert len(calls) == 2


def test_historical_snapshot_uses_the_api_timestamp(api):
    api(Resp(body={"timestamp": "2024-10-06T16:55:00Z", "previous_timestamp": "2024-10-06T16:50:00Z",
                   "data": [EVENT]}, last=10))
    js = oddsapi.historical(pd.Timestamp("2024-10-06T17:00:00Z"))
    assert js["requested_utc"] == "2024-10-06T17:00:00Z"
    assert js["snapshot_utc"] == "2024-10-06T16:55:00Z"
    assert set(oddsapi.parse(js).snapshot_utc) == {"2024-10-06T16:55:00Z"}


def test_backfill_budget_covers_the_plan():
    import inspect
    assert inspect.signature(oddsapi.backfill).parameters["max_credits"].default >= 8_260
