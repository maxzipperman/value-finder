"""Live uses (nflweather/live.py) and the quota guard's paid-tier setting. No API calls."""
import json
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nflweather import live, quota  # noqa: E402

NOW = pd.Timestamp("2026-10-09T16:00:00Z")


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(quota, "STATE", tmp_path / "quota.json")
    for v in ("XPC_SERVICE_NAME", "ODDS_QUOTA_KIND", "ODDS_API_TIER", "ODDS_BACKGROUND_FLOOR"):
        monkeypatch.delenv(v, raising=False)


def seen(remaining, used):
    quota.STATE.write_text(json.dumps(dict(utc=pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%dT%H:%M:%SZ"),
                                           remaining=remaining, used=used)))


# ---------------------------------------------------------------- quota: paid-tier setting
def test_existing_runs_behave_as_before_on_the_free_plan():
    seen(100, 400)
    assert quota.tier() == "free" and quota.check() is None
    seen(quota.MANUAL_FLOOR - 1, 441)
    assert "floor" in quota.check()


def test_background_loggers_never_run_on_the_free_plan(monkeypatch):
    monkeypatch.setenv("ODDS_QUOTA_KIND", "background")
    seen(450, 50)
    assert "paid plan" in quota.check()
    quota.STATE.unlink()
    assert "paid plan" in quota.check()          # unknown plan (new month, nothing recorded yet): stay off


def test_background_loggers_on_a_paid_plan_stop_at_their_floor(monkeypatch):
    monkeypatch.setenv("ODDS_QUOTA_KIND", "background")
    seen(4_000_000, 1_000_000)
    assert quota.tier() == "paid" and quota.background_floor() == 100_000 and quota.check() is None
    seen(99_999, 4_900_001)
    assert "background floor 100000" in quota.check()
    seen(15_000, 5_000)                           # the 20K plan: the 2,000 minimum applies
    assert quota.background_floor() == 2_000 and quota.check() is None
    seen(1_999, 18_001)
    assert quota.check() is not None
    monkeypatch.delenv("ODDS_QUOTA_KIND")
    assert quota.check() is None                  # the alerts and manual runs still have their credits


def test_a_response_without_quota_headers_keeps_the_last_quota():
    seen(4_000_000, 1_000_000)

    class R:
        status_code, headers = 502, {}
    quota.record(R(), "nfl-weather")
    assert quota.read()["remaining"] == 4_000_000 and quota.tier() == "paid"


def test_overrides(monkeypatch):
    monkeypatch.setenv("ODDS_QUOTA_KIND", "background")
    monkeypatch.setenv("ODDS_API_TIER", "paid")
    assert quota.check() is None
    monkeypatch.setenv("ODDS_BACKGROUND_FLOOR", "500")
    seen(600, 19_400)
    assert quota.background_floor() == 500 and quota.check() is None
    monkeypatch.setenv("ODDS_API_TIER", "free")
    assert quota.check() is not None


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


# ---------------------------------------------------------------- trigger poller
def ledger():
    rows = [("2026-10-08T11:30:00Z", "g1", "2026-10-11", "13:00", "CHI", "GB", "no_trigger", 9.0),
            ("2026-10-09T11:30:00Z", "g1", "2026-10-11", "13:00", "CHI", "GB", "negative_ev", 16.2),  # latest wins
            ("2026-10-09T11:30:00Z", "g2", "2026-10-11", "13:00", "NYJ", "BUF", "no_trigger", 8.0),
            ("2026-10-09T11:30:00Z", "g3", "2026-10-16", "20:15", "KC", "DEN", "outside_horizon", 20.0),  # too far
            ("2026-10-09T11:30:00Z", "g4", "2026-10-09", "08:00", "LA", "SEA", "SIGNAL", 18.0)]         # kicked off
    return pd.DataFrame(rows, columns=["snapshot_utc", "game_id", "gameday", "gametime", "away_team", "home_team",
                                       "rule_b", "wx_wind"]).assign(lead_days=2)


def test_active_triggers_use_the_latest_ledger_row():
    a = live.active_triggers(ledger(), NOW)
    assert list(a.game_id) == ["g1"] and a.iloc[0].rule_b == "negative_ev"
    assert a.iloc[0].kick_utc == pd.Timestamp("2026-10-11T17:00:00Z")


def test_trigger_rows_match_by_teams_and_kickoff():
    lines = pd.DataFrame([dict(snapshot_utc="2026-10-09T16:00Z", event_id="e1", commence_utc="2026-10-11T17:00:00Z",
                               home="GB", away="CHI", book=b, market="totals", book_update="x", total=41.5,
                               under_price=u, over_price=-105) for b, u in (("pinnacle", -112), ("draftkings", -110))]
                         + [dict(snapshot_utc="2026-10-09T16:00Z", event_id="e9", commence_utc="2026-12-20T18:00:00Z",
                                 home="GB", away="CHI", book="pinnacle", market="totals", book_update="x",
                                 total=38.5, under_price=-110, over_price=-110)])        # the rematch: not this game
    r = live.trigger_rows(live.active_triggers(ledger(), NOW), lines, "2026-10-09T16:00:05Z")
    assert list(r.book) == ["pinnacle", "draftkings"] and set(r.total) == {41.5}
    assert r.iloc[0].rule_b == "negative_ev" and r.iloc[0].kick_utc == "2026-10-11T17:00:00Z"
    assert live.trigger_rows(live.active_triggers(ledger(), NOW), pd.DataFrame(), "x").empty


# ---------------------------------------------------------------- props log
EV = {"id": "e1", "commence_time": "2026-10-11T17:00:00Z", "home_team": "Green Bay Packers",
      "away_team": "Chicago Bears"}


@pytest.mark.parametrize("now,want", [("2026-10-09T17:10:00Z", [48]), ("2026-10-09T17:31:00Z", []),
                                      ("2026-10-10T17:00:00Z", [24]), ("2026-10-11T15:29:00Z", [2]),
                                      ("2026-10-11T16:45:00Z", [0]), ("2026-10-11T16:59:00Z", [])])
def test_props_slots(now, want):
    assert [h for _, h in live.props_due([EV], set(), pd.Timestamp(now))] == want


def test_captured_slots_are_not_repeated():
    assert live.props_due([EV], {"e1:0"}, pd.Timestamp("2026-10-11T16:45:00Z")) == []


def test_props_rows_keep_player_and_line():
    body = {**EV, "bookmakers": [{"key": "fanduel", "markets": [
        {"key": "player_kicking_points", "last_update": "t", "outcomes": [
            {"name": "Under", "description": "Brandon McManus", "point": 7.5, "price": -120}]}]}]}
    r = live.props_rows(body, "2026-10-11T16:45:00Z", 0).iloc[0]
    assert (r.player, r.point, r.price, r.market, r.offset_h) == ("Brandon McManus", 7.5, -120, "player_kicking_points", 0)


def test_props_markets_fit_one_region():
    assert len(live.PROP_BOOKS) <= 10 and len(set(live.PROP_MARKETS)) == 9


def run_log_props(tmp_path, monkeypatch, get):
    """Run scripts/log_props.py against a fake Odds API, with every path under tmp_path."""
    import runpy

    from nflweather import config, oddsapi
    monkeypatch.setattr(config, "ROOT", tmp_path)
    monkeypatch.setattr(oddsapi, "CACHE", tmp_path / "raw" / "oddsapi")
    monkeypatch.setattr(oddsapi, "_get", get)
    monkeypatch.setenv("ODDS_QUOTA_KIND", "background")
    monkeypatch.setenv("ODDS_API_TIER", "paid")
    monkeypatch.setattr(sys, "argv", ["log_props.py"])
    runpy.run_path(str(Path(__file__).resolve().parents[1] / "scripts" / "log_props.py"), run_name="__main__")


def test_props_log_saves_each_slot_before_the_next_and_asks_for_decimal_odds(tmp_path, monkeypatch):
    """#33 items 5 and 6: an error part way through never re-fetches (and re-bills) a slot already paid
    for, the raw text is on disk before parsing, and prices come in decimal odds like F2/F3."""
    kick = (pd.Timestamp.now(tz="UTC") + pd.Timedelta(hours=24) - pd.Timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
    events = [dict(EV, id=i, commence_time=kick) for i in ("e1", "e2")]
    calls = []

    class R:
        headers = {"x-requests-last": "3", "x-requests-remaining": "4000000"}

        def __init__(self, body):
            self.text = json.dumps(body)

        def json(self):
            return json.loads(self.text)

    def get(path, params, fail_on=None):
        calls.append((path, params))
        if path.endswith("/events"):
            return R(events)
        if fail_on and fail_on in path:
            raise RuntimeError("boom")
        return R(dict(EV, id=path.split("/")[-2], bookmakers=[{"key": "pinnacle", "markets": [{"key": "team_totals",
                      "outcomes": [{"name": "Over", "description": "Green Bay Packers", "point": 24.5, "price": 1.91}]}]}]))

    with pytest.raises(RuntimeError):
        run_log_props(tmp_path, monkeypatch, lambda p, q: get(p, q, fail_on="/e2/"))
    state = json.loads((tmp_path / "data" / "forward" / "props_state.json").read_text())
    assert state["captured"] == ["e1:24"]
    (raw,) = (tmp_path / "raw" / "oddsapi" / "props").glob("*_e1_T24.json")
    assert json.loads(json.loads(raw.read_text())["body"])["id"] == "e1"
    assert all(q["oddsFormat"] == "decimal" for p, q in calls if p.endswith("/odds"))
    calls.clear()
    run_log_props(tmp_path, monkeypatch, get)
    assert [p for p, _ in calls if p.endswith("/odds")] == ["/sports/americanfootball_nfl/events/e2/odds"]
    log = pd.read_csv(tmp_path / "data" / "forward" / "props_log.csv")
    assert sorted(log.event_id) == ["e1", "e2"] and set(log.price) == {1.91}


def test_live_rows_from_the_2026_season_are_marked_sealed():
    """#33 item 19: the props and trigger-poll logs are holdout data for 2026-season games."""
    assert live.sealed("2026-10-11T17:00:00Z") and live.sealed("2027-02-08T23:30:00Z")
    assert not live.sealed("2026-02-08T23:30:00Z") and not live.sealed("2027-09-09T00:20:00Z")
    body = dict(EV, bookmakers=[{"key": "pinnacle", "markets": [{"key": "team_totals", "outcomes": [
        {"name": "Over", "description": "Green Bay Packers", "point": 24.5, "price": 1.91}]}]}])
    assert live.props_rows(body, "2026-10-10T17:00:00Z", 24).sealed.tolist() == [True]
    lines = pd.DataFrame([dict(snapshot_utc="2026-10-09T16:00Z", event_id="e1", commence_utc="2026-10-11T17:00:00Z",
                               home="GB", away="CHI", book="pinnacle", market="totals", book_update="x", total=41.5,
                               under_price=-112, over_price=-105)])
    assert live.trigger_rows(live.active_triggers(ledger(), NOW), lines, "x").sealed.tolist() == [True]
