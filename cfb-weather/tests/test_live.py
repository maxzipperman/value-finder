"""CFB trigger poller (cfbweather/live.py) and the quota guard's paid-tier setting. No API calls."""
import json
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cfbweather import fetch, live, quota  # noqa: E402

NOW = pd.Timestamp("2026-10-09T16:00:00Z")
NAMES = {"Wyoming Cowboys": "Wyoming", "Air Force Falcons": "Air Force"}


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(quota, "STATE", tmp_path / "quota.json")
    monkeypatch.setattr(fetch, "RAW", tmp_path / "raw")
    monkeypatch.setenv("ODDS_API_KEY", "test-key")
    for v in ("XPC_SERVICE_NAME", "ODDS_QUOTA_KIND", "ODDS_API_TIER", "ODDS_BACKGROUND_FLOOR"):
        monkeypatch.delenv(v, raising=False)


def seen(remaining, used):
    quota.STATE.write_text(json.dumps(dict(utc=pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%dT%H:%M:%SZ"),
                                           remaining=remaining, used=used)))


def test_background_kind_is_paid_only_and_floored(monkeypatch):
    monkeypatch.setenv("ODDS_QUOTA_KIND", "background")
    seen(450, 50)
    assert "paid plan" in quota.check()
    seen(4_000_000, 1_000_000)
    assert quota.check() is None
    seen(99_999, 4_900_001)
    assert quota.check() is not None
    monkeypatch.delenv("ODDS_QUOTA_KIND")
    seen(100, 400)
    assert quota.check() is None                     # alerts and manual runs: unchanged


def test_a_record_from_another_key_is_ignored(monkeypatch):
    """#33 item 2: sharp-markets writes the shared file with its own key; a different key's plan never
    sets this project's tier or floor. Records carry a fingerprint, never the key."""
    monkeypatch.setenv("ODDS_QUOTA_KIND", "background")
    monkeypatch.setenv("ODDS_API_KEY", "paid-key")

    class R:
        status_code, headers = 200, {"x-requests-remaining": "4000000", "x-requests-used": "1000000"}
    quota.record(R(), "sharp-markets")
    s = json.loads(quota.STATE.read_text())
    assert s["key"] == quota.fingerprint("paid-key") and "paid-key" not in quota.STATE.read_text()
    assert quota.tier() == "paid" and quota.check() is None
    monkeypatch.setenv("ODDS_API_KEY", "free-key")                  # this project still has the free key
    assert quota.read() is None and quota.tier() == "free" and "paid plan" in quota.check()
    seen(4_000_000, 1_000_000)                                       # a record from before fingerprints: still read
    assert quota.tier() == "paid"


def test_free_plan_poller_makes_no_call(monkeypatch):
    monkeypatch.setenv("ODDS_QUOTA_KIND", "background")
    seen(450, 50)
    calls = []
    monkeypatch.setattr(fetch.session, "get", lambda *a, **k: calls.append(a))
    assert "paid plan" in live.live_totals(NAMES) and calls == []


def ledger():
    rows = [("2026-10-08T18:30:00Z", 1, "Air Force", "Wyoming", "2026-10-10 19:00:00+00:00", "no_trigger", 9.0),
            ("2026-10-09T12:30:00Z", 1, "Air Force", "Wyoming", "2026-10-10 19:00:00+00:00", "no_price", 17.5),
            ("2026-10-09T12:30:00Z", 2, "Utah", "Colorado", "2026-10-10 20:00:00+00:00", "not_outdoor", None),
            ("2026-10-09T12:30:00Z", 3, "Iowa", "Nebraska", "2026-10-17 20:00:00+00:00", "outside_horizon", 22.0)]
    return pd.DataFrame(rows, columns=["snapshot_utc", "game_id", "away_team", "home_team", "start_utc", "rule_b",
                                       "wx_wind"]).assign(lead_days=1)


def test_active_triggers_and_rows(monkeypatch):
    a = live.active_triggers(ledger(), NOW)
    assert list(a.game_id) == [1] and a.iloc[0].rule_b == "no_price"
    events = [{"id": "e", "home_team": "Wyoming Cowboys", "away_team": "Air Force Falcons",
               "commence_time": "2026-10-10T19:00:00Z",
               "bookmakers": [{"key": b, "markets": [{"key": "totals", "last_update": "t", "outcomes": [
                   {"name": "Over", "price": -110, "point": 44.5}, {"name": "Under", "price": u, "point": 44.5}]}]}
                   for b, u in (("pinnacle", -108), ("bovada", -105))]}]
    quotes = live.book_rows(events, NAMES, "2026-10-09T16:00:00Z")
    r = live.trigger_rows(a, quotes, "2026-10-09T16:00:05Z")
    assert list(r.book) == ["pinnacle", "bovada"] and list(r.under_price) == [-108, -105]
    assert r.iloc[0].kick_utc == "2026-10-10T19:00:00Z" and r.iloc[0].wx_wind == 17.5


def test_paid_poll_is_cached_first(monkeypatch):
    monkeypatch.setenv("ODDS_QUOTA_KIND", "background")
    seen(4_000_000, 1_000_000)

    class R:
        status_code, headers = 200, {"x-requests-last": "1", "x-requests-remaining": "3999999",
                                     "x-requests-used": "1000001"}

        def json(self):
            return []

    monkeypatch.setattr(fetch.session, "get", lambda *a, **k: R())
    monkeypatch.setattr("cfbweather.config.RAW", fetch.RAW)
    out = live.live_totals(NAMES)
    assert out.empty and quota.read()["remaining"] == 3_999_999
    assert list((fetch.RAW / "oddsapi" / "live").glob("*_poll.json"))


def test_trigger_rows_from_the_2026_season_are_marked_sealed():
    """#33 item 19: the trigger-poll log is holdout data for 2026-season games."""
    assert live.sealed("2026-10-10T19:00:00Z") and live.sealed("2027-01-19T00:30:00Z")
    assert not live.sealed("2026-01-19T00:30:00Z") and not live.sealed("2027-08-29T16:00:00Z")
    quotes = live.book_rows([{"home_team": "Wyoming Cowboys", "away_team": "Air Force Falcons",
                              "commence_time": "2026-10-10T19:00:00Z", "bookmakers": [{"key": "pinnacle", "markets": [
                                  {"key": "totals", "last_update": "x", "outcomes": [
                                      {"name": "Over", "price": -110, "point": 40.5},
                                      {"name": "Under", "price": -110, "point": 40.5}]}]}]}], NAMES, "s")
    rows = live.trigger_rows(live.active_triggers(ledger(), NOW), quotes, "p")
    assert len(rows) == 1 and rows.sealed.tolist() == [True]
