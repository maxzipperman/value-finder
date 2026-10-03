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

from nflweather import board, oddsapi, quota  # noqa: E402


class Resp:
    def __init__(self, status=200, body=None, remaining=480, last=1):
        self.status_code, self._body = status, body if body is not None else []
        self.headers = {"x-requests-remaining": str(remaining), "x-requests-used": "20", "x-requests-last": str(last)}
        self.ok = status < 400

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
    monkeypatch.setattr(quota, "STATE", tmp_path / "odds_quota.json")
    monkeypatch.delenv("XPC_SERVICE_NAME", raising=False)
    calls = []
    monkeypatch.setattr(oddsapi, "paid_get", lambda session, url, params, **kw:
                        session.get(url, params=params, timeout=60))

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
    assert quota.read()["remaining"] == 480


@pytest.mark.parametrize("resp", [Resp(status=429), Resp(status=401), Resp(status=500),
                                  requests.ConnectionError("down")])
def test_api_failure_falls_back_instead_of_crashing(api, resp):
    api(resp)
    assert board._pinnacle_live() is None


def test_credit_floor_protects_the_alerts(api, monkeypatch):
    calls = api(Resp(body=[EVENT]))
    now = pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%dT%H:%M:%SZ")
    quota.STATE.write_text(json.dumps(dict(utc=now, remaining=50)))
    with pytest.raises(oddsapi.OddsAPIUnavailable):
        oddsapi.live(markets=("totals",))                                    # hand-run: refused below 60
    assert calls == []
    monkeypatch.setenv("XPC_SERVICE_NAME", "com.nflweather.alerts")
    oddsapi.live(markets=("totals",))                                        # scheduled alert: still runs
    assert len(calls) == 1
    monkeypatch.delenv("XPC_SERVICE_NAME")
    quota.STATE.write_text(json.dumps(dict(utc="2000-01-15T00:00:00Z", remaining=0)))   # reset on the 1st
    oddsapi.live(markets=("totals",))
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


def test_same_minute_snapshots_never_overwrite_and_polls_stay_out_of_the_lines_table(api, tmp_path, monkeypatch):
    """#33 item 4: the alerts, close capture and the trigger poller can call in the same minute."""
    monkeypatch.setattr(oddsapi, "PROC", tmp_path / "proc")
    (tmp_path / "proc").mkdir()
    api(Resp(body=[EVENT]))
    # Downstream filename/row test only; production collector admission stays disabled.
    monkeypatch.setattr(oddsapi, "paid_get", lambda session, url, params, **kw:
                        session.get(url, params=params, timeout=60))
    t0 = pd.Timestamp("2026-10-11T12:00:05Z")
    for sec, tag in ((0, None), (20, None), (65, "poll")):
        monkeypatch.setattr(pd.Timestamp, "now", classmethod(lambda cls, tz=None, s=sec: t0 + pd.Timedelta(seconds=s)))
        oddsapi.live(markets=("totals",), tag=tag)
    names = sorted(f.name for f in (oddsapi.CACHE / "live").glob("*.json"))
    assert names == ["2026-10-11T120005Z.json", "2026-10-11T120025Z.json", "2026-10-11T120110Z_poll.json"]
    assert json.loads((oddsapi.CACHE / "live" / names[2]).read_text())["snapshot_utc"] == "2026-10-11T1201Z"
    games = pd.DataFrame([dict(game_id="2026_06_GB_CHI", home_team="CHI", away_team="GB", gameday="2026-10-11")])
    L = oddsapi.lines_table(games)
    assert list(L.snapshot_utc.dt.strftime("%H:%M")) == ["12:00"]     # the 12:01 poll file is left out
