"""CFB Odds API client (issue #15): responses are cached before parsing, Rule B prices at
Pinnacle then DraftKings while every book is logged, failures fall back quietly, and the
ledger survives new columns. No network: session.get is replaced by a fake."""
import json
import sys
from pathlib import Path

import pandas as pd
import pytest
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cfbweather import board, fetch, quota  # noqa: E402


class Resp:
    def __init__(self, status=200, body=None, remaining=480):
        self.status_code, self._body = status, body if body is not None else []
        self.headers = {"x-requests-remaining": str(remaining), "x-requests-used": "20", "x-requests-last": "1"}

    def json(self):
        return self._body


def totals(book, point, under, over=-110):
    return {"key": book, "markets": [{"key": "totals", "outcomes": [
        {"name": "Over", "price": over, "point": point}, {"name": "Under", "price": under, "point": point}]}]}


def event(eid, *books):
    return {"id": eid, "commence_time": "2026-10-10T19:30:00Z", "home_team": "Iowa Hawkeyes",
            "away_team": "Ohio State Buckeyes", "bookmakers": list(books)}


NAMES = {"Iowa Hawkeyes": "Iowa", "Ohio State Buckeyes": "Ohio State"}


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setenv("ODDS_API_KEY", "test")
    monkeypatch.setattr(fetch, "RAW", tmp_path)
    monkeypatch.setattr(quota, "STATE", tmp_path / "odds_quota.json")
    monkeypatch.delenv("XPC_SERVICE_NAME", raising=False)
    calls = []
    from ops import collector_guard
    monkeypatch.setattr(collector_guard, "paid_get", lambda session, url, params, **kw:
                        session.get(url, params=params, timeout=60))

    def use(resp):
        def get(url, params=None, timeout=None):
            calls.append(params)
            if isinstance(resp, Exception):
                raise resp
            return resp
        monkeypatch.setattr(fetch.session, "get", get)
        return calls
    return use


def test_prices_at_pinnacle_logs_best_book_and_caches(api):
    calls = api(Resp(body=[event("a", totals("draftkings", 45.5, -112), totals("pinnacle", 45.5, -107),
                                 totals("fanduel", 45.5, -104), totals("bovada", 46.5, -110))]))
    df = fetch.odds_api_totals(NAMES)
    assert len(fetch.LIVE_BOOKS) <= 10 and calls[0]["bookmakers"] == ",".join(fetch.LIVE_BOOKS)
    r = df.iloc[0]
    assert (r.line_src, r.mkt_total, r.mkt_under) == ("pinnacle", 45.5, -107)
    assert (r.best_under, r.best_under_book) == (-104, "fanduel")
    assert len(list((fetch.RAW / "oddsapi" / "live").glob("*.json"))) == 1   # cache-first
    assert quota.read()["remaining"] == 480


def test_draftkings_when_pinnacle_is_missing(api):
    api(Resp(body=[event("b", totals("draftkings", 50.5, -110), totals("betmgm", 50.5, -105))]))
    r = fetch.odds_api_totals(NAMES).iloc[0]
    assert (r.line_src, r.mkt_under, r.best_under_book) == ("draftkings", -110, "betmgm")


@pytest.mark.parametrize("resp", [Resp(status=429), Resp(status=401), requests.Timeout("slow")])
def test_failures_return_an_empty_frame(api, resp):
    api(resp)
    assert fetch.odds_api_totals(NAMES).empty


def test_credit_floor_skips_the_call(api, monkeypatch):
    calls = api(Resp(body=[]))
    monkeypatch.setenv("XPC_SERVICE_NAME", "com.cfbweather.alerts")
    quota.STATE.write_text(json.dumps(dict(utc=pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%dT%H:%M:%SZ"), remaining=0)))
    assert fetch.odds_api_totals(NAMES).empty and calls == []


def test_ledger_rewrites_once_when_columns_change(tmp_path, monkeypatch):
    monkeypatch.setattr(board, "ROOT", tmp_path)
    monkeypatch.setattr(board, "OUT", tmp_path)
    path = tmp_path / "data" / "forward" / "ledger.csv"
    path.parent.mkdir(parents=True)
    old_cols = ["snapshot_utc", "rules_version"] + [c for c in board.COLS if not c.startswith("best_")] + ["start_utc"]
    pd.DataFrame([{c: 1 for c in old_cols}]).to_csv(path, index=False)
    up = pd.DataFrame([{c: 2 for c in board.COLS} | {"start_utc": "2026-10-10T19:30:00Z", "best_under_book": "fanduel"}])
    board.save(up)
    board.save(up)
    L = pd.read_csv(path)
    assert len(L) == 3 and "best_under_book" in L and L.best_under_book.isna().iloc[0]
    assert (L.mkt_total == [1, 2, 2]).all()                                   # no column misalignment
