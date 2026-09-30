"""The 5M-month bulk puller (markets.oddsapi.bulk), against mocked Odds API responses. No network."""
import csv
import json
import logging
import random
from argparse import Namespace
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest
import requests

from markets.cache import RawCache, cache_key
from markets.oddsapi import bulk
from markets.oddsapi.normalize import outcome_rows

UTC = timezone.utc
NOW = datetime(2026, 9, 29, 12, tzinfo=UTC)
CFG_YAML = """
books:
  us10: [pinnacle, lowvig, betonlineag, draftkings, fanduel, betmgm, williamhill_us, fanatics, betrivers, espnbet]
  sharp3: [pinnacle, lowvig, betonlineag]
featured: h2h,spreads,totals
sports:
  americanfootball_nfl:
    history_from: 2020-06-06
    sweep_every_days: 2
    windows:
      - {label: "2020", from: 2020-09-08, to: 2020-09-16}
      - {label: "2024", from: 2024-09-01, to: 2024-09-10}
      - {label: "2026", from: 2026-09-01, to: 2027-02-20, sealed: true}
  basketball_nba:
    history_from: 2020-06-27
    sweep_every_days: 1
    windows:
      - {label: "2025-26", from: 2025-10-20, to: 2025-10-23}
pulls:
  F1: {kind: featured, sports: [americanfootball_nfl], schedule: daily_close, books: us10}
  F3: {kind: event, sports: [americanfootball_nfl], books: us10, from: 2023-05-03, offsets: [24, 0],
       markets: "player_pass_yds,player_rush_yds,player_reception_yds,player_receptions,player_kicking_points,player_field_goals"}
  F4: {kind: featured, sports: [americanfootball_nfl], schedule: hourly, books: us10, only_seasons: ["2024"]}
  N1: {kind: featured, sports: [basketball_nba], schedule: 5min, lookback_hours: 2, after_minutes: 15,
       books: sharp3, markets: h2h, cache_as: {sport: nba, source: oddsapi_hist}}
"""


def t(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


@pytest.fixture
def cfg(tmp_path):
    p = tmp_path / "odds5m.yaml"
    p.write_text(CFG_YAML)
    return bulk.load_config(p)


def game(cfg, gid, kick, sport="americanfootball_nfl"):
    return bulk._label(cfg, {"id": gid, "sport": sport, "commence_time": t(kick)})


# ---------------------------------------------------------------- mocked HTTP
class Resp:
    def __init__(self, status, body, headers):
        self.status_code, self.text = status, json.dumps(body) if not isinstance(body, str) else body
        self.headers = headers

    def json(self):
        return json.loads(self.text)


KICKS = {"ev1": "2024-09-06T00:20:00Z", "ev26": "2026-09-10T00:20:00Z"}


class FakeOddsApi:
    """Routes GETs like the Odds API: bills 10 x markets returned x regions for odds, 1 for /events."""

    def __init__(self, remaining=5_000_000, overbill=0, status=200):
        self.calls, self.remaining, self.overbill, self.status = [], remaining, overbill, status

    def get(self, url, params=None, timeout=None):
        self.calls.append((url, dict(params)))
        p = dict(params)
        if url.endswith("/sports"):
            return self._r(200, [{"key": "americanfootball_nfl"}], 0)
        if self.status != 200:
            return self._r(self.status, {"message": "nope"}, 0)
        at = p["date"]
        if url.endswith("/events"):
            kick = "2024-09-06T00:20:00Z" if at < "2024-09-04" else "2024-09-06T00:25:00Z"   # a moved kickoff
            data = [{"id": "ev1", "sport_key": "americanfootball_nfl", "commence_time": kick,
                     "home_team": "Kansas City Chiefs", "away_team": "Baltimore Ravens"}] if "2024" in at < kick else []
            if "2020" in at:
                data = [{"id": "ev20", "commence_time": "2020-09-11T00:20:00Z", "home_team": "A", "away_team": "B"}]
            return self._r(200, {"timestamp": at, "data": data}, 1 if data else 0)
        books = p["bookmakers"].split(",")
        markets = p["markets"].split(",")
        returned = markets[:2] if "player_pass_yds" in markets else markets        # props: only two markets quoted
        eid = url.split("/events/")[1].split("/")[0] if "/events/" in url else "ev1"
        ev = {"id": eid, "commence_time": KICKS.get(eid, KICKS["ev1"]), "home_team": "Kansas City Chiefs",
              "away_team": "Baltimore Ravens",
              "bookmakers": [{"key": b, "markets": [{"key": m, "outcomes": [
                  {"name": "Over", "description": "Patrick Mahomes", "point": 245.5, "price": 1.87},
                  {"name": "Under", "description": "Patrick Mahomes", "point": 245.5, "price": 1.95}]}
                  for m in returned]} for b in books if b != "lowvig"]}
        ts = bulk.iso(t(at) - bulk.FIVE) if t(at).minute % 10 == 5 else at      # older snapshots: 10 minutes apart
        body = {"timestamp": ts, "previous_timestamp": None, "next_timestamp": None,
                "data": ev if "/events/" in url else [ev]}
        cost = 10 * len(returned) * bulk.regions(books) + self.overbill
        return self._r(200, body, cost)

    def _r(self, status, body, cost):
        self.remaining -= cost
        return Resp(status, body, {"X-Requests-Last": str(cost), "X-Requests-Remaining": str(self.remaining),
                                   "X-Requests-Used": str(5_000_000 - self.remaining)})


def client(tmp_path, api=None, **kw):
    return bulk.BulkClient(RawCache(tmp_path / "raw"), max_credits=kw.pop("max_credits", 10_000),
                           session=api or FakeOddsApi(), api_key="SECRETKEY", rate_per_sec=1e6, max_retries=0, **kw)


def args(**kw):
    base = dict(pull="all", sports=None, seasons=None, week_of="auto", confirm=True, max_credits=100_000, floor=0, rate=1e6)
    return Namespace(**{**base, **kw})


# ---------------------------------------------------------------- schedules
def test_close_is_the_last_grid_point_five_minutes_before_kickoff():
    assert bulk.close_time(t("2024-09-08T17:00:00Z")) == t("2024-09-08T16:55:00Z")
    assert bulk.close_time(t("2024-09-08T17:03:00Z")) == t("2024-09-08T16:55:00Z")
    assert bulk.event_snapshots(t("2024-09-08T17:00:00Z"), [24, 2, 0]) == [
        t("2024-09-07T17:00:00Z"), t("2024-09-08T15:00:00Z"), t("2024-09-08T16:55:00Z")]


def test_daily_close_matches_the_budget_grid():
    # odds_budget.grid(at=16): 16:00 UTC inside [kick - 7d, kick], plus the close
    pts = bulk.game_snapshots(t("2024-09-08T17:00:00Z"), {"schedule": "daily_close"})
    assert pts[0] == t("2024-09-02T16:00:00Z") and pts[-2:] == [t("2024-09-08T16:00:00Z"), t("2024-09-08T16:55:00Z")]
    assert len(pts) == 8
    hourly = bulk.game_snapshots(t("2024-09-08T17:00:00Z"), {"schedule": "hourly"})
    assert len(hourly) == 7 * 24 + 1 and hourly[0] == t("2024-09-01T17:00:00Z")
    five = bulk.game_snapshots(t("2025-10-21T23:30:00Z"), {"schedule": "5min", "lookback_hours": 1, "after_minutes": 15})
    assert five[0] == t("2025-10-21T22:30:00Z") and five[-1] == t("2025-10-21T23:45:00Z") and len(five) == 16
    assert bulk.game_snapshots(t("2024-09-08T17:00:00Z"), {"schedule": "close"}) == [t("2024-09-08T16:55:00Z")]
    # F4's incremental cost nets every F1 snapshot: each daily_close point is on the hourly grid, the close included
    for k in ("2024-09-08T17:00:00Z", "2024-09-06T00:20:00Z", "2024-09-08T16:33:00Z"):
        assert set(bulk.game_snapshots(t(k), {"schedule": "daily_close"})) <= set(bulk.game_snapshots(t(k), {"schedule": "hourly"}))


def test_build_schedule_uses_last_sighting_before_kickoff(cfg):
    bodies = [{"timestamp": "2024-09-02T06:00:00Z", "data": [
                  {"id": "a", "commence_time": "2024-09-06T00:20:00Z", "home_team": "H", "away_team": "A"}]},
              {"timestamp": "2024-09-04T06:00:00Z", "data": [
                  {"id": "a", "commence_time": "2024-09-06T00:25:00Z", "home_team": "H", "away_team": "A"}]},
              {"timestamp": "2026-09-09T06:00:00Z", "data": [
                  {"id": "b", "commence_time": "2026-09-11T00:20:00Z", "home_team": "H", "away_team": "A"}]}]
    games = bulk.build_schedule(cfg, "americanfootball_nfl", bodies)
    a, b = games
    assert a["commence_time"] == t("2024-09-06T00:25:00Z") and a["first_seen"] == t("2024-09-02T06:00:00Z")
    assert (a["season"], a["sealed"]) == ("2024", False) and (b["season"], b["sealed"]) == ("2026", True)


def test_plan_unions_snapshots_and_filters_seasons(cfg):
    sched = {"americanfootball_nfl": [game(cfg, "g1", "2024-09-06T00:20:00Z"), game(cfg, "g2", "2024-09-06T00:20:00Z"),
                                      game(cfg, "g3", "2024-09-08T17:00:00Z"), game(cfg, "g4", "2026-09-10T00:20:00Z"),
                                      game(cfg, "g5", "2026-10-04T17:00:00Z"),       # not played yet
                                      game(cfg, "g6", "2020-09-11T00:20:00Z")]}
    f1 = bulk.plan_calls(cfg, "F1", sched, now=NOW)
    times = [c.at for c in f1]
    assert len(times) == len(set(times))                          # one call per snapshot, shared by g1 and g2
    assert not any(c.at > NOW for c in f1)
    assert {c.expected for c in f1} == {30}
    assert all(c.sealed == (c.at.year == 2026) for c in f1)
    assert t("2026-10-04T16:55:00Z") not in times
    f3 = bulk.plan_calls(cfg, "F3", sched, now=NOW)
    assert {c.event_id for c in f3} == {"g1", "g2", "g3", "g4"}   # 2020 is before additional markets (2023-05-03)
    assert {c.expected for c in f3} == {60} and len(f3) == 8
    f4 = bulk.plan_calls(cfg, "F4", sched, now=NOW)
    assert f4 and all(c.at.year == 2024 for c in f4)
    assert not any(c.sealed for c in f4)                           # only_seasons: 2024
    wk = bulk.plan_calls(cfg, "F3", sched, now=NOW, week_of="auto")
    assert {c.event_id for c in wk} == {"g1", "g2", "g3"}          # first week of the latest unsealed season
    sl = bulk.plan_calls(cfg, "F3", sched, now=NOW, seasons=["2024"])   # --seasons: one slice of a pull (F3a)
    assert {c.event_id for c in sl} == {"g1", "g2", "g3"} and not any(c.sealed for c in sl)


def test_games_from_limits_a_close_pull_to_the_listed_games(cfg, tmp_path):
    """HB1/HS1: only the games `markets weather qualifying` listed get a close; a missing list stops the run."""
    sched = {"americanfootball_nfl": [game(cfg, "g1", "2024-09-06T00:20:00Z"), game(cfg, "g3", "2024-09-08T17:00:00Z"),
                                      game(cfg, "g4", "2024-09-08T20:25:00Z")]}
    listing = tmp_path / "q.csv"
    cfg["pulls"]["HX"] = {"id": "HX", "kind": "featured", "sports": ["americanfootball_nfl"], "schedule": "close",
                          "books": "us10", "only_seasons": ["2024"], "games_from": str(listing)}
    with pytest.raises(SystemExit, match="weather qualifying"):
        bulk.plan_calls(cfg, "HX", sched, now=NOW)
    listing.write_text("sport,id,pull\namericanfootball_nfl,g1,HB1\nbasketball_nba,g3,HB1\n")   # g3 is listed for another sport
    calls = bulk.plan_calls(cfg, "HX", sched, now=NOW)
    assert [(c.at, c.expected) for c in calls] == [(t("2024-09-06T00:15:00Z"), 30)]
    assert bulk.games_from(cfg["pulls"]["F1"], "americanfootball_nfl") is None            # pulls without a list are unchanged


def test_groups_expand_and_full_refuses_all(cfg, tmp_path):
    cfg["groups"] = {"day_one": ["F1", "F3"], "gated": ["N1"]}
    assert bulk._pulls(cfg, "day_one,N1") == ["F1", "F3", "N1"]
    assert bulk._pulls(cfg, "gated,N1") == ["N1"]
    assert bulk.group_of(cfg, "F3") == "day_one" and bulk.group_of(cfg, "F4") == "-"
    with pytest.raises(SystemExit, match="unknown pull"):
        bulk._pulls(cfg, "march")
    bulk.save_schedule(tmp_path, "americanfootball_nfl", [{**game(cfg, "ev1", "2024-09-06T00:20:00Z"), "home_team": "H",
                                                             "away_team": "A", "first_seen": None}])
    with pytest.raises(SystemExit, match="name the pulls"):
        bulk.stage_pull(cfg, RawCache(tmp_path), args(pull="all", confirm=False), week=False, now=NOW)
    assert bulk.stage_pull(cfg, RawCache(tmp_path), args(pull="all", confirm=False), week=True, now=NOW) == []


def test_extra_probes_cost_one_featured_close_each(cfg, tmp_path):
    """The review's three coverage checks: NCAAF 2020, MLB 2024, MLS 2024, 30 credits each, skipped when absent."""
    cfg["books"]["soccer10"] = ["pinnacle", "betonlineag", "draftkings", "fanduel", "betmgm", "williamhill_us", "bovada",
                                "unibet_eu", "marathonbet", "betfair_ex_eu"]
    mk = lambda gid, sport, kick, season: {"id": gid, "sport": sport, "commence_time": t(kick), "season": season,  # noqa: E731
                                           "sealed": False}
    sched = {"americanfootball_nfl": [game(cfg, "ev1", "2024-09-06T00:20:00Z"), game(cfg, "ev20", "2020-09-11T00:20:00Z")],
             "americanfootball_ncaaf": [mk("c20", "americanfootball_ncaaf", "2020-09-12T19:30:00Z", "2020")],
             "baseball_mlb": [mk("m24", "baseball_mlb", "2024-07-10T23:10:00Z", "2024")]}
    api = FakeOddsApi()
    rows = bulk.billing_probes(cfg, client(tmp_path, api), sched, NOW)
    by = {r["probe"]: r for r in rows}
    assert len(rows) == 7
    ncaaf, mlb = by["featured americanfootball_ncaaf 2020, us10"], by["featured baseball_mlb 2024, us10"]
    assert (ncaaf["expected_max"], ncaaf["billed"]) == (30, "30") and "pinnacle" in ncaaf["books_returned"]
    assert mlb["expected_max"] == 30 and set(mlb["markets_returned"]) == {"h2h", "spreads", "totals"}
    assert by["featured soccer_usa_mls 2024, soccer10"]["result"].startswith("skipped")
    assert any("americanfootball_ncaaf/odds" in u for u, _ in api.calls) and len(api.calls) == 6


def test_n1_shares_the_nba_pipeline_cache(cfg):
    from markets.oddsapi.client import BASE_URL
    sched = {"basketball_nba": [game(cfg, "n1", "2025-10-21T23:30:00Z", "basketball_nba")]}
    calls = bulk.plan_calls(cfg, "N1", sched, now=NOW)
    c = calls[0]
    assert (c.cache_sport, c.source, c.expected) == ("nba", "oddsapi_hist", 10)
    # the params OddsApiClient.historical_odds sends for sport nba (config/sports/nba.yaml)
    theirs = {"bookmakers": "pinnacle,lowvig,betonlineag", "markets": "h2h", "oddsFormat": "decimal",
              "dateFormat": "iso", "date": c.at.strftime("%Y-%m-%dT%H:%M:%SZ")}
    assert c.key == cache_key("oddsapi_hist", f"{BASE_URL}/historical/sports/basketball_nba/odds", theirs)


# ---------------------------------------------------------------- client safety
def _one_call(cfg):
    sched = {"americanfootball_nfl": [game(cfg, "ev1", "2024-09-06T00:20:00Z")]}
    return bulk.plan_calls(cfg, "F3", sched, now=NOW)


def test_fetch_is_cache_first_logged_and_keeps_the_key_out(cfg, tmp_path):
    api = FakeOddsApi()
    c = client(tmp_path, api)
    res = bulk.run_calls(c, _one_call(cfg))
    assert res["fetched"] == 2 and res["spent"] == 40 and res["stopped"] is None     # 2 of 6 prop markets quoted
    again = bulk.run_calls(client(tmp_path, api), _one_call(cfg))
    assert again["todo"] == 0 and len(api.calls) == 2                                 # resumable, no refetch
    rows = list(csv.DictReader((tmp_path / "raw/_manifest/oddsapi_manifest.csv").open()))
    assert len(rows) == 2 and rows[0]["credits_last"] == "20" and rows[0]["expected_credits"] == "60"
    assert rows[0]["returned_ts"] and rows[0]["requested_ts"] and len(rows[0]["sha256"]) == 64
    assert rows[0]["event_id"] == "ev1" and rows[0]["sealed"] == "False"
    stored = "".join(p.read_bytes().decode("latin-1") for p in (tmp_path / "raw").rglob("*") if p.is_file())
    assert "SECRETKEY" not in stored
    assert list((tmp_path / "raw/americanfootball_nfl/oddsapi/hist_event_odds").glob("*/*.parquet"))


def test_budget_and_floor_stop_before_the_call(cfg, tmp_path):
    api = FakeOddsApi()
    res = bulk.run_calls(client(tmp_path, api, max_credits=70), _one_call(cfg))
    assert res["fetched"] == 1 and "run budget" in res["stopped"]                     # 20 spent + up to 60 > 70
    api2 = FakeOddsApi(remaining=1_000)
    c = client(tmp_path / "b", api2, floor=950)
    c.account()
    res = bulk.run_calls(c, _one_call(cfg))
    assert res["fetched"] == 0 and "floor" in res["stopped"]


def test_circuit_breaker_on_overbilling(cfg, tmp_path):
    api = FakeOddsApi(overbill=50)                                                    # 20 + 50 = 70 > 60
    res = bulk.run_calls(client(tmp_path, api), _one_call(cfg))
    assert res["fetched"] == 1 and "billed 70" in res["stopped"]


def test_key_rejected_and_repeated_errors_stop(cfg, tmp_path):
    res = bulk.run_calls(client(tmp_path, FakeOddsApi(status=401)), _one_call(cfg))
    assert "401" in res["stopped"]
    many = bulk.plan_calls(cfg, "F1", {"americanfootball_nfl": [game(cfg, "ev1", "2024-09-06T00:20:00Z")]}, now=NOW)
    res = bulk.run_calls(client(tmp_path / "b", FakeOddsApi(status=422), max_errors=3), many)
    assert res["fetched"] == 3 and "3 errors in a row" in res["stopped"]
    assert not list((tmp_path / "b/raw").rglob("*.parquet"))                           # errors are not cached


def test_dry_run_calls_nothing(cfg, tmp_path):
    api = FakeOddsApi()
    out = bulk.stage_probe(cfg, RawCache(tmp_path), args(confirm=False), now=NOW, session=api)
    assert out["sweep_calls"] > 0 and api.calls == []
    with pytest.raises(SystemExit):
        bulk._client(RawCache(tmp_path), args(max_credits=0), session=api)


# ---------------------------------------------------------------- stages end to end
def test_probe_then_week_then_check(cfg, tmp_path, monkeypatch):
    monkeypatch.setenv("ODDS_API_KEY", "SECRETKEY")
    cache = RawCache(tmp_path)
    api = FakeOddsApi()
    out = bulk.stage_probe(cfg, cache, args(sports=["americanfootball_nfl"]), now=NOW, session=api)
    assert out["stopped"] is None and out["games"]["americanfootball_nfl"]["2024"] == 1
    sched = bulk.load_schedules(cfg, tmp_path, ["americanfootball_nfl"])["americanfootball_nfl"]
    assert [g["commence_time"] for g in sched if g["id"] == "ev1"] == [t("2024-09-06T00:25:00Z")]  # moved kickoff
    probes = {p["probe"]: p for p in out["probes"]}
    props = probes["event odds NFL props, 10 books"]
    assert props["billed"] == "20" and props["billing_rule"].endswith("= 20")
    assert "lowvig" not in probes["featured NFL 2020, sharp books"]["books_returned"]
    assert probes["featured baseball_mlb 2024, us10"]["result"].startswith("skipped")     # no MLB in this config
    week = bulk.stage_pull(cfg, cache, args(pull="F1,F3", sports=["americanfootball_nfl"]), week=True, now=NOW, session=api)
    assert [w["pull"] for w in week] == ["F1", "F3"] and all(w["stopped"] is None for w in week)
    cov = bulk.stage_check(cfg, cache, args(pull="F3"), now=NOW)[0]
    assert cov["missing_books"] == ["lowvig"] and set(cov["markets"]) == {"player_pass_yds", "player_rush_yds"}


def test_load_rows_leaves_sealed_seasons_out(cfg, tmp_path):
    sched = {"americanfootball_nfl": [game(cfg, "ev1", "2024-09-06T00:20:00Z"), game(cfg, "ev26", "2026-09-10T00:20:00Z")]}
    calls = bulk.plan_calls(cfg, "F3", sched, now=NOW)
    c = client(tmp_path)
    assert bulk.run_calls(c, calls)["fetched"] == 4
    rows = bulk.load_rows(cfg, calls, c.cache)
    assert rows and {r["odds_event_id"] for r in rows} == {"ev1"}
    sealed = bulk.load_rows(cfg, calls, c.cache, include_sealed=True)
    assert {r["odds_event_id"] for r in sealed} == {"ev1", "ev26"}


def test_real_config_matches_the_owners_decisions():
    """Owner decisions, Sep 28: the sealed seasons exactly as below; X3 dropped; the NBA studies 2025-26; and the
    reviewed day-one design adopted on Sep 28 (#38): F2 and F3 at T-24h and the close, no team totals, heat as
    close-only pulls of qualifying games, N1 and F4 gated, H1/N2/F5/F6 in March."""
    real = bulk.load_config()
    sealed = {s: [w["label"] for w in sc["windows"] if w["sealed"]] for s, sc in real["sports"].items()}
    want = {"americanfootball_nfl": ["2026"], "americanfootball_ncaaf": ["2026"], "basketball_nba": ["2026-27"],
            "icehockey_nhl": ["2026-27"], "baseball_mlb": ["2026"], "soccer_fifa_world_cup": ["2026 North America"]}
    for s, labels in sealed.items():
        if s.startswith("soccer_") and s != "soccer_fifa_world_cup":
            # calendar 2026: sealed where the league has a 2026 window, nothing earlier
            assert labels == (["2026"] if any(w["label"] == "2026" for w in real["sports"][s]["windows"]) else []), s
        else:
            assert labels == want[s], s
    assert "X3" not in real["pulls"] and "B1" not in real["pulls"] and "S1" not in real["pulls"]
    assert real["groups"] == {"day_one": ["F1", "F2", "F3", "HB1", "HS1"], "gated": ["N1", "F4"],
                              "march": ["H1", "N2", "F5", "F6"]}
    assert list(real["pulls"]) == [p for g in real["groups"].values() for p in g]
    assert real["pulls"]["F2"]["offsets"] == [24, 0] and real["pulls"]["F2"]["markets"] == "alternate_spreads,alternate_totals"
    assert real["pulls"]["F3"]["offsets"] == [24, 0] and len(real["pulls"]["F3"]["markets"].split(",")) == 6
    for pid in ("HB1", "HS1"):
        h = real["pulls"][pid]
        assert (h["schedule"], h["only_seasons"], h["games_from"]) == ("close", ["2024", "2025"], "weather/heat_qualifying.csv")
    assert real["pulls"]["HS1"]["books"] == "soccer10" and "soccer_fifa_world_cup" in real["pulls"]["HS1"]["sports"]
    assert real["pulls"]["N1"]["only_seasons"] == ["2025-26"]
    assert set(real["books"]) == {"us10", "soccer10", "sharp3"}                  # X3's exchange group is gone
    assert {p["books"] for p in real["pulls"].values()} <= set(real["books"])


# The first 2026 date each sealed window has to cover (published 2026 schedules): season openers for the
# calendar sports, and the start of the 2026-27 NBA and NHL preseason window.
FIRST_2026 = {"baseball_mlb": date(2026, 3, 25), "soccer_usa_mls": date(2026, 2, 21),
              "soccer_mexico_ligamx": date(2026, 1, 9), "soccer_brazil_campeonato": date(2026, 1, 28),
              "soccer_japan_j_league": date(2026, 2, 6), "soccer_korea_kleague1": date(2026, 2, 28),
              "soccer_fifa_world_cup": date(2026, 6, 11), "americanfootball_nfl": date(2026, 9, 10),
              "americanfootball_ncaaf": date(2026, 8, 29)}


def test_sealed_windows_have_the_right_date_boundaries():
    """#33 item 18: the holdout by dates, not just labels. For the calendar sports (MLB, soccer), no unsealed
    window reaches into 2026 and every sealed window lies in 2026 and starts by the first 2026 game; the
    2026-27 NBA and NHL windows start by October 1, 2026, after the unsealed 2025-26 ones end."""
    real = bulk.load_config()
    for s, sc in real["sports"].items():
        open_w = [w for w in sc["windows"] if not w["sealed"]]
        sealed = [w for w in sc["windows"] if w["sealed"]]
        if s == "baseball_mlb" or s.startswith("soccer_"):
            assert all(w["to"] <= date(2025, 12, 31) for w in open_w), s
            assert all(w["from"] >= date(2026, 1, 1) and w["to"] <= date(2026, 12, 31) for w in sealed), s
            assert all(w["from"] <= FIRST_2026[s] for w in sealed), s
        elif s in ("basketball_nba", "icehockey_nhl"):
            (w,) = sealed
            assert w["label"] == "2026-27" and w["from"] <= date(2026, 10, 1)
            assert all(o["to"] < w["from"] for o in open_w), s
        else:                                                        # NFL, CFB: the 2026 season
            (w,) = sealed
            assert w["from"] <= FIRST_2026[s] and all(o["to"] < w["from"] for o in open_w), s


# ---------------------------------------------------------------- audit 2 (Sep 29): fail closed
KEY = "FAKESECRETKEY999"


class Mangled(FakeOddsApi):
    """FakeOddsApi whose paid responses (everything but /sports) lose or garble billing headers; `sports` sets the
    free key check's headers and status instead."""

    def __init__(self, drop=(), put=None, sports=None, sports_status=200, **kw):
        super().__init__(**kw)
        self.drop, self.put, self.sports, self.sports_status = drop, put or {}, sports, sports_status

    def get(self, url, params=None, timeout=None):
        r = super().get(url, params, timeout)
        if url.endswith("/sports"):
            r.status_code = self.sports_status
            if self.sports is not None:
                r.headers = dict(self.sports)
            return r
        for k in self.drop:
            r.headers.pop(k, None)
        r.headers.update(self.put)
        return r


def test_network_failure_stops_the_run_without_showing_the_key(cfg, tmp_path, monkeypatch, capsys, caplog):
    """Finding 1 end to end: an unreachable host stops the run with a STOPPED line, not a traceback holding the key,
    and the key check before a run refuses the same way."""
    from markets import http
    monkeypatch.setattr(http.time, "sleep", lambda s: None)
    monkeypatch.setattr(bulk, "BASE_URL", "https://unresolvable.invalid/v4")
    monkeypatch.setenv("ODDS_API_KEY", KEY)
    caplog.set_level(logging.DEBUG)
    c = bulk.BulkClient(RawCache(tmp_path / "raw"), max_credits=10_000, api_key=KEY, rate_per_sec=1e6, max_retries=1)
    res = bulk.run_calls(c, _one_call(cfg))
    assert res["fetched"] == 0 and "no answer from the Odds API" in res["stopped"]
    assert res["spent"] == 120            # two attempts that got no answer, each counted at its upper bound (60)
    assert not list((tmp_path / "raw").rglob("*.parquet"))                               # nothing cached
    with pytest.raises(SystemExit) as ei:
        bulk._client(RawCache(tmp_path / "raw"), args(max_credits=100))
    assert "STOPPED before the first paid call" in str(ei.value)
    out = capsys.readouterr()
    assert "STOPPED" in out.out and "stopped:" in out.out
    for where, text in {"stopped": res["stopped"], "stdout": out.out, "stderr": out.err, "log": caplog.text,
                        "exit": str(ei.value)}.items():
        assert KEY not in text, where


@pytest.mark.parametrize("bad", [None, "abc", "", "nan", "-5"])
def test_unreadable_credits_last_counts_the_upper_bound_and_stops(cfg, tmp_path, capsys, bad):
    """Findings 2 and 6: a billed (200) response whose x-requests-last is missing or not a number counts the call's
    upper bound and stops the run with a STOPPED line; it never counts zero and never raises ValueError."""
    api = Mangled(drop=("X-Requests-Last",), put={} if bad is None else {"X-Requests-Last": bad})
    res = bulk.run_calls(client(tmp_path, api), _one_call(cfg))
    assert res["fetched"] == 1 and res["spent"] == 60 and len(api.calls) == 1          # upper bound, then stop
    assert "billing could not be read" in res["stopped"]
    assert list((tmp_path / "raw").rglob("*.parquet"))                                  # the response is kept
    assert "STOPPED: the billing could not be read" in capsys.readouterr().out
    row = next(csv.DictReader((tmp_path / "raw/_manifest/oddsapi_manifest.csv").open()))
    assert row["credits_last"] == "" and row["expected_credits"] == "60"                # logged as unknown, not 0


def test_unreadable_balance_stops_the_run_when_a_floor_is_set(cfg, tmp_path):
    """Finding 3: a billed response without a readable x-requests-remaining stops the run while a floor is set;
    and with a floor but no known balance, nothing is fetched at all."""
    api = Mangled(drop=("X-Requests-Remaining",))
    c = client(tmp_path, api, floor=950)
    c.account()
    res = bulk.run_calls(c, _one_call(cfg))
    assert res["fetched"] == 1 and "balance could not be read" in res["stopped"] and len(api.calls) == 2
    assert res["remaining"] == 5_000_000 - 20                   # the estimate: the start less the count
    api2 = FakeOddsApi()
    res = bulk.run_calls(client(tmp_path / "b", api2, floor=950), _one_call(cfg))       # account() never ran
    assert res["fetched"] == 0 and "balance is unknown" in res["stopped"] and api2.calls == []
    api3 = Mangled(drop=("X-Requests-Remaining",))                                       # no floor: the run goes on
    res = bulk.run_calls(client(tmp_path / "c", api3), _one_call(cfg))
    assert res["fetched"] == 2 and res["stopped"] is None


def test_a_404_without_billing_headers_counts_the_upper_bound_and_goes_on(cfg, tmp_path):
    """404s return no data, so the docs don't bill them; unreadable headers still count the upper bound, and the
    known balance is lowered by it so the floor keeps being checked."""
    api = Mangled(status=404, drop=("X-Requests-Last", "X-Requests-Remaining"))
    c = client(tmp_path, api, floor=950)
    start = c.account()["remaining"]
    res = bulk.run_calls(c, _one_call(cfg))
    assert res["stopped"] is None and res["fetched"] == 2 and res["spent"] == 120
    assert c.remaining == start - 120


@pytest.mark.parametrize("sports,status,why", [
    ({}, 200, "did not return a readable balance"),
    ({"X-Requests-Remaining": "lots"}, 200, "did not return a readable balance"),
    ({"X-Requests-Remaining": "1000"}, 200, "1,000 credits left, already below the floor of 531,630"),
    (None, 503, "returned HTTP 503"),
    (None, 401, "rejected the key (401)"),
])
def test_the_key_check_refuses_to_start(tmp_path, monkeypatch, sports, status, why):
    """Finding 3: the free /sports check must return a readable balance at or above the floor, or nothing starts.
    The refusal is a plain message (SystemExit), not a traceback, and no paid call is made."""
    from markets import http
    monkeypatch.setattr(http.time, "sleep", lambda s: None)                              # 503 is retried first
    monkeypatch.setenv("ODDS_API_KEY", KEY)
    api = Mangled(sports=sports, sports_status=status)
    with pytest.raises(SystemExit) as ei:
        bulk._client(RawCache(tmp_path), args(floor=531_630), session=api)
    assert why in str(ei.value) and "nothing spent" in str(ei.value)
    assert {u for u, _ in api.calls} == {bulk.BASE_URL + "/sports"}                      # no paid call


def test_the_probes_stop_at_the_first_stop(cfg, tmp_path, capsys):
    """The probe stage follows the pulls' rules: once one probe stops the run (here the first overbills), no
    further probe is called."""
    sched = {"americanfootball_nfl": [game(cfg, "ev1", "2024-09-06T00:20:00Z"), game(cfg, "ev20", "2020-09-11T00:20:00Z")]}
    api = FakeOddsApi(overbill=50)
    rows = bulk.billing_probes(cfg, client(tmp_path, api), sched, NOW)
    assert len(api.calls) == 1 and rows[0]["stopped"] and "billed 80" in rows[0]["result"]
    assert [r["result"].split(":")[0] for r in rows[1:4]] == ["not run"] * 3
    assert "STOPPED" in capsys.readouterr().out


def test_the_probe_stage_reports_a_probe_stop(cfg, tmp_path, monkeypatch):
    monkeypatch.setenv("ODDS_API_KEY", KEY)
    api = FakeOddsApi(overbill=50)                     # /events sweeps aren't overbilled; the first probe is
    out = bulk.stage_probe(cfg, RawCache(tmp_path), args(sports=["americanfootball_nfl"]), now=NOW, session=api)
    assert out["stopped"].startswith("stopped:") and "billed" in out["stopped"]
    assert sum("/odds" in u for u, _ in api.calls) == 1


def _saved_nfl(cfg, raw):
    games = [game(cfg, f"g{y}", f"{y}-10-12T17:00:00Z") for y in (2023, 2024, 2025)] + [game(cfg, "g26", "2026-09-13T17:00:00Z")]
    bulk.save_schedule(raw, "americanfootball_nfl", [{**g, "home_team": "H", "away_team": "A", "first_seen": None}
                                                     for g in games])


def test_full_refuses_f3_without_seasons_even_in_the_dry_run(tmp_path, capsys):
    """Finding 4: `full --pull F3` without --seasons would buy all of 2023-26 (136,800) instead of the day-one
    slice (34,200). The real config marks F3 require_seasons; `full` refuses, dry run included, and names the
    day-one command. With --seasons the dry run goes ahead as before. Since the Sep 29 follow-up `week` applies
    the same slice rule (final review, finding 12); `plan` and `check` are unchanged."""
    real = bulk.load_config()
    assert real["pulls"]["F3"]["require_seasons"] == {"F3a": "2025", "F3b": "2023,2024,2026"}
    assert [p for p, v in real["pulls"].items() if v.get("require_seasons")] == ["F3"]
    _saved_nfl(real, tmp_path)
    now = datetime(2026, 10, 1, 12, tzinfo=UTC)
    api = FakeOddsApi()
    for pull in ("F3", "F2,F3", "day_one"):
        for confirm in (False, True):
            with pytest.raises(SystemExit) as ei:
                bulk.stage_pull(real, RawCache(tmp_path), args(pull=pull, confirm=confirm), week=False, now=now,
                                session=api)
            msg = str(ei.value)
            assert "F3: refused" in msg and "needs --seasons" in msg
            assert "F3a: uv run markets odds5m full --pull F3 --seasons 2025 --confirm" in msg
            assert "F3b: uv run markets odds5m full --pull F3 --seasons 2023,2024,2026 --confirm" in msg
            if pull == "day_one":
                assert "Run the other pulls by name, without --seasons (F1, F2, HB1, HS1)" in msg
    assert api.calls == []
    assert bulk.stage_pull(real, RawCache(tmp_path), args(pull="F3", seasons=["2025"], confirm=False), week=False,
                           now=now) == []
    assert "F3  2 calls, 2 to fetch, at most 120 credits" in capsys.readouterr().out    # one 2025 game, T-24h + close
    with pytest.raises(SystemExit, match="`week --pull F3` needs --seasons"):
        bulk.stage_pull(real, RawCache(tmp_path), args(pull="F3", confirm=False), week=True, now=now)


def test_a_cache_as_pull_never_plans_a_sealed_call(cfg):
    """Finding 5 (a): N1 lands where `markets build` reads directly, so plan_calls refuses any sealed call for it."""
    cfg["sports"]["basketball_nba"]["windows"].append({"label": "2026-27", "from": date(2026, 10, 1),
                                                       "to": date(2027, 6, 30), "sealed": True})
    sched = {"basketball_nba": [game(cfg, "n1", "2025-10-21T23:30:00Z", "basketball_nba"),
                                game(cfg, "n2", "2026-10-05T23:30:00Z", "basketball_nba")]}
    now = datetime(2026, 10, 10, tzinfo=UTC)
    with pytest.raises(SystemExit, match="must never fetch a sealed season"):
        bulk.plan_calls(cfg, "N1", sched, now=now)
    cfg["pulls"]["N1"]["only_seasons"] = ["2025-26"]                                    # as the real config has it
    calls = bulk.plan_calls(cfg, "N1", sched, now=now)
    assert calls and not any(c.sealed for c in calls)
    real = bulk.load_config()
    real_sched = {"basketball_nba": [game(real, "n2", "2026-10-25T23:30:00Z", "basketball_nba")]}
    assert bulk.plan_calls(real, "N1", real_sched, now=datetime(2026, 11, 1, tzinfo=UTC)) == []


def test_markets_build_leaves_sealed_games_out(tmp_path, monkeypatch):
    """Finding 5 (b): `markets build` reads data/raw/{sport}/oddsapi_hist directly, not through load_rows, so it
    leaves out rows for games in a sealed season of config/odds5m.yaml itself, and counts them."""
    import duckdb

    from markets.build import run
    from markets.cache import write_record
    from markets.sport import load_sport, load_teams
    monkeypatch.setattr(run, "RAW_DIR", tmp_path)

    def ev(eid, kick):
        return {"id": eid, "commence_time": kick, "home_team": "Boston Celtics", "away_team": "New York Knicks",
                "bookmakers": [{"key": "pinnacle", "markets": [{"key": "h2h", "outcomes": [
                    {"name": "Boston Celtics", "price": 1.5}, {"name": "New York Knicks", "price": 2.6}]}]}]}

    def put(sport, name, body):
        write_record(tmp_path / sport / "oddsapi_hist" / "2026-10-05" / f"{name}.parquet", {
            "cache_key": name, "sport": sport, "source": "oddsapi_hist", "data_date": "2026-10-05", "url": "u",
            "params_json": json.dumps({"date": body["timestamp"]}), "fetched_at": NOW, "http_status": 200,
            "headers_json": "{}", "body": json.dumps(body)})

    no_kick = {k: v for k, v in ev("no_kick", None).items() if k != "commence_time"}   # a game with no time
    put("nba", "k1", {"timestamp": "2026-06-09T23:00:00Z", "data": [ev("open", "2026-06-10T00:30:00Z"),       # 2025-26
                                                                     ev("sealed", "2026-10-21T23:30:00Z")]})   # 2026-27
    put("nba", "k3", {"timestamp": "2026-10-21T23:00:00Z", "data": [no_kick, ev("garbled", "not a time")]})
    con, teams = duckdb.connect(), load_teams("nba")
    rows, unknown, left_out, no_time, _ = run.sharp_odds_rows(con, "nba", teams)
    assert {r["odds_event_id"] for r in rows} == {"open"} and dict(left_out) == {"2026-27": 2} and not unknown
    assert no_time == 4                   # audit 2 review: a row whose season can't be told is never kept
    rows, _, left_out, no_time, _ = run.sharp_odds_rows(con, "nba", teams, include_sealed=True)
    assert {r["odds_event_id"] for r in rows} == {"open", "sealed"} and not left_out and no_time == 4
    for sport, key in run.ODDS5M_SPORT_KEY.items():                                     # the explicit map agrees
        assert load_sport(sport).odds_sport_key == key and key in bulk.load_config()["sports"]
    put("nhl", "k2", {"timestamp": "2026-06-09T23:00:00Z", "data": []})
    with pytest.raises(SystemExit, match="ODDS5M_SPORT_KEY"):
        run.sharp_odds_rows(con, "nhl", teams)


def test_normalizer_keeps_point_and_description():
    body = {"timestamp": "2024-09-05T23:55:00Z", "data": {"id": "e", "commence_time": "2024-09-06T00:20:00Z",
            "home_team": "H", "away_team": "A", "bookmakers": [{"key": "draftkings", "markets": [
                {"key": "player_pass_yds", "outcomes": [{"name": "Over", "description": "P. Mahomes", "point": 245.5,
                                                         "price": 1.87}]}]}]}}
    (r,) = outcome_rows(body, "2024-09-06T00:00:00Z")
    assert (r["point"], r["description"], r["price_decimal"], r["market_key"]) == ("245.5", "P. Mahomes", "1.87",
                                                                                    "player_pass_yds")


# ---------------------------------------------------------------- review of the audit-2 fixes (Sep 29)
class Billed(FakeOddsApi):
    """FakeOddsApi whose paid calls are billed on attempts that get no usable answer: the first `bad` attempts of
    each call are billed at the call's real price and then time out (mode "timeout") or answer HTTP 500 ("500").
    `last` overrides every paid response's x-requests-last."""

    def __init__(self, bad=1, mode="timeout", last=None, **kw):
        super().__init__(**kw)
        self.bad, self.mode, self.last, self.seen, self.billed = bad, mode, last, {}, 0

    def _r(self, status, body, cost):
        self.billed += cost
        r = super()._r(status, body, cost)
        if self.last is not None and cost:
            r.headers["X-Requests-Last"] = self.last
        return r

    def get(self, url, params=None, timeout=None):
        if url.endswith("/sports"):
            return super().get(url, params, timeout)
        k = (url, params["date"])
        self.seen[k] = self.seen.get(k, 0) + 1
        r = super().get(url, params, timeout)
        if self.seen[k] <= self.bad:
            if self.mode == "timeout":
                import requests
                raise requests.ReadTimeout("read timed out")
            r.status_code = 500
        return r


def _nfl_calls(cfg, n=4):
    """F3 calls for n 2024 games: 2n calls at an upper bound of 60, each billed 20 by FakeOddsApi."""
    games = [game(cfg, f"ev{i}", f"2024-09-0{2 + i}T00:20:00Z") for i in range(n)]
    return bulk.plan_calls(cfg, "F3", {"americanfootball_nfl": games}, now=NOW)


def _retrying_client(tmp_path, api, monkeypatch, **kw):
    from markets import http
    monkeypatch.setattr(http.time, "sleep", lambda s: None)
    c = client(tmp_path, api, **kw)
    c.max_retries = 6                                                   # the CLI's default
    c.account()
    return c


@pytest.mark.parametrize("mode", ["timeout", "500"])
def test_a_call_billed_on_a_retried_attempt_still_counts(cfg, tmp_path, monkeypatch, mode):
    """Review blocker 1: a first attempt that is billed and then times out (or answers 500), and a retry that
    succeeds, used to count once, so the run went over --max-credits. Now every attempt counts before the retry: an
    attempt with no answer at its upper bound (60), and a 500 at what it reports (20). The budget is checked before
    every retry, so the server never bills more than the budget, and the run never counts less than it billed."""
    api = Billed(mode=mode)
    c = _retrying_client(tmp_path, api, monkeypatch, max_credits=200)
    res = bulk.run_calls(c, _nfl_calls(cfg))
    assert api.billed <= 200 and res["spent"] >= api.billed, (api.billed, res)
    assert "run budget" in res["stopped"]
    per_call = 60 + 20 if mode == "timeout" else 20 + 20
    assert res["fetched"] == (2 if mode == "timeout" else 4) and c.counted == per_call * res["fetched"]
    rows = list(csv.DictReader((tmp_path / "raw/_manifest/oddsapi_manifest.csv").open()))[1:]
    assert [r["http_status"] for r in rows] == (["200"] if mode == "timeout" else ["500", "200"]) * res["fetched"]


def test_many_billed_retries_stop_before_the_budget_or_the_floor(cfg, tmp_path, monkeypatch):
    """Six billed timeouts per call: each retry is checked like a new call, so neither the budget nor the floor is
    crossed (before, a call billed on every attempt went below the floor and far over the budget)."""
    api = Billed(bad=6)
    res = bulk.run_calls(_retrying_client(tmp_path, api, monkeypatch, max_credits=150), _nfl_calls(cfg))
    assert api.billed <= 150 and "no answer and may have been billed" in res["stopped"]
    api2 = Billed(bad=6)
    c2 = _retrying_client(tmp_path / "b", api2, monkeypatch, floor=5_000_000 - 200)
    res = bulk.run_calls(c2, _nfl_calls(cfg))
    assert api2.remaining >= 5_000_000 - 200 and "the floor is" in res["stopped"]


def test_a_zero_or_fractional_cost_never_undercounts(cfg, tmp_path, monkeypatch):
    """Review minors: x-requests-last "0" while the balance drops counts the drop; "19.5" counts 20, not 19. Since
    the Sep 29 follow-up, a response with data that reports 0 also counts its documented cost and stops the run at
    once (final review, finding 1)."""
    api = Billed(bad=0, last="0")
    res = bulk.run_calls(_retrying_client(tmp_path, api, monkeypatch, max_credits=100), _nfl_calls(cfg))
    assert api.billed <= 100 and res["spent"] >= api.billed and "billing cannot be trusted" in res["stopped"]
    assert res["fetched"] == 1
    assert bulk._cost("19.5") == 20 and bulk._cost("20") == 20 and bulk._cost("4999.9", up=False) == 4999


def test_a_full_disk_or_a_body_that_is_not_json_stops_with_the_summary(cfg, tmp_path, monkeypatch, capsys):
    """Review minor: a billed response that can't be kept ends the run with a STOPPED line and the summary, is
    counted and logged in the manifest, and is not cached; before, both ended in a Python error."""
    import errno

    from markets import cache as cache_mod

    def full(path, record):
        raise OSError(errno.ENOSPC, "No space left on device")

    monkeypatch.setattr(cache_mod, "write_record", full)
    res = bulk.run_calls(client(tmp_path, FakeOddsApi()), _one_call(cfg))
    assert "could not be saved (No space left on device): is the disk full?" in res["stopped"]
    assert res["fetched"] == 1 and res["spent"] == 20
    rows = list(csv.DictReader((tmp_path / "raw/_manifest/oddsapi_manifest.csv").open()))
    assert len(rows) == 1 and rows[0]["credits_last"] == "20"
    monkeypatch.undo()

    class Html(FakeOddsApi):
        def _r(self, status, body, cost):
            r = super()._r(status, body, cost)
            if cost:
                r.text = "<html>busy</html>"
            return r
    res = bulk.run_calls(client(tmp_path / "b", Html()), _one_call(cfg))
    # its documented cost can't be worked out, so it counts the larger of the 20 it reported and its upper bound, 60
    assert "body that is not JSON" in res["stopped"] and res["spent"] == 60
    assert not list((tmp_path / "b/raw").rglob("*.parquet"))                          # not cached: a rerun asks again
    out = capsys.readouterr().out
    assert out.count("STOPPED:") == 2 and out.count("stopped: 1 fetched") == 2


def test_an_unexpected_error_still_ends_with_the_summary(cfg, tmp_path, capsys):
    class Broken(FakeOddsApi):
        def get(self, url, params=None, timeout=None):
            raise KeyError(f"boom {params['apiKey']}")
    res = bulk.run_calls(client(tmp_path, Broken()), _one_call(cfg))
    assert res["stopped"].startswith("unexpected error, probably a bug") and "SECRETKEY" not in res["stopped"]
    assert "stopped: 0 fetched" in capsys.readouterr().out


def test_error_bodies_never_show_the_key(cfg, tmp_path, monkeypatch, capsys, caplog):
    """Review major: a server or proxy that echoes the request in an error body would have put the key on screen,
    in the log and (a 404) in the cache. Every body is scrubbed before it is printed, logged, raised or cached."""
    from markets import http
    monkeypatch.setattr(http.time, "sleep", lambda s: None)
    monkeypatch.setenv("ODDS_API_KEY", "SECRETKEY")
    caplog.set_level(logging.DEBUG)

    class Echo(FakeOddsApi):
        def get(self, url, params=None, timeout=None):
            r = super().get(url, params, timeout)
            key = params["apiKey"]
            if url.endswith("/sports"):
                if self.status == 503:
                    r.status_code, r.text = 503, json.dumps({"message": f"down: GET /v4/sports?apiKey={key}"})
                return r
            r.text = json.dumps({"message": f"echo /moved/{key} ?apiKey={key}"})
            return r

    for status in (429, 500, 404):
        bulk.run_calls(client(tmp_path / str(status), Echo(status=status), max_errors=1), _one_call(cfg))
    with pytest.raises(SystemExit) as ei:
        bulk._client(RawCache(tmp_path / "s"), args(), session=Echo(status=503))
    assert list((tmp_path / "404").rglob("*.parquet"))                                  # the 404 is cached, scrubbed
    stored = "".join(p.read_bytes().decode("latin-1") for p in tmp_path.rglob("*") if p.is_file())
    out = capsys.readouterr()
    for where, text in {"stdout": out.out, "stderr": out.err, "log": caplog.text, "files": stored,
                        "exit": str(ei.value)}.items():
        assert "SECRETKEY" not in text, where
    assert "REDACTED" in out.out and "REDACTED" in str(ei.value)


def test_load_rows_judges_a_row_without_a_game_time_by_its_call(cfg, tmp_path):
    """Review major: a row with no commence_time in a call the plan marked sealed used to come back without
    include_sealed; now it is judged by the call's sealed flag."""
    class NoKick(FakeOddsApi):
        def _r(self, status, body, cost):
            if isinstance(body, dict) and isinstance(body.get("data"), dict) and body["data"]["id"] == "ev26":
                body["data"].pop("commence_time")
            return super()._r(status, body, cost)
    sched = {"americanfootball_nfl": [game(cfg, "ev1", "2024-09-06T00:20:00Z"), game(cfg, "ev26", "2026-09-10T00:20:00Z")]}
    calls = bulk.plan_calls(cfg, "F3", sched, now=NOW)
    c = client(tmp_path, NoKick())
    bulk.run_calls(c, calls)
    assert {r["odds_event_id"] for r in bulk.load_rows(cfg, calls, c.cache)} == {"ev1"}
    assert {r["odds_event_id"] for r in bulk.load_rows(cfg, calls, c.cache, include_sealed=True)} == {"ev1", "ev26"}
    assert bulk.game_time("not a time") is None and bulk.game_time(None) is None


def test_full_takes_seasons_only_as_one_declared_slice(tmp_path, capsys):
    """Review minors: `full --pull day_one --seasons 2025` quietly cut F1, F2, HB1 and HS1 to 2025, and F3 took any
    --seasons (all four seasons, or 2099). Now --seasons must name exactly one of F3's slices, and `full` refuses it
    for a pull the plan buys whole. All refusals come before any call, in the dry run too."""
    real = bulk.load_config()
    _saved_nfl(real, tmp_path)
    now = datetime(2026, 10, 1, 12, tzinfo=UTC)
    api = FakeOddsApi()
    refusals = {("day_one", "2025"): "would also narrow F1, F2, HB1, HS1",
                ("F1", "2024"): "would also narrow F1",
                ("F3", "2023,2024,2025,2026"): "is not one of its slices",
                ("F3", "2099"): "is not one of its slices",
                ("F3", "2025,2026"): "is not one of its slices"}
    for (pull, seasons), why in refusals.items():
        for confirm in (False, True):
            with pytest.raises(SystemExit, match=why):
                bulk.stage_pull(real, RawCache(tmp_path), args(pull=pull, seasons=seasons.split(","), confirm=confirm),
                                week=False, now=now, session=api)
    assert api.calls == []
    assert bulk.stage_pull(real, RawCache(tmp_path), args(pull="F3", seasons=["2026", "2023", "2024"], confirm=False),
                           week=False, now=now) == []                                  # F3b, in any order
    capsys.readouterr()
    # `week` lets --seasons pick the week of a pull bought whole (F3 needs a slice there too, since Sep 29)
    bulk.stage_pull(real, RawCache(tmp_path), args(pull="F1", seasons=["2099"], confirm=False), week=True, now=now)
    assert "warning: F1: no game in the saved schedules is in season 2099" in capsys.readouterr().out


def test_balance_reads_the_credits_left_and_spends_nothing(tmp_path, capsys, monkeypatch):
    """Review minor: after a stop, the runbook needs a way to read the balance that can't spend."""
    monkeypatch.setenv("ODDS_API_KEY", KEY)
    api = FakeOddsApi()
    info = bulk.stage_balance({}, RawCache(tmp_path), args(max_credits=0, floor=531_630), session=api)
    assert info["remaining"] == 5_000_000 and [u for u, _ in api.calls] == [bulk.BASE_URL + "/sports"]
    assert "5,000,000 credits remaining" in capsys.readouterr().out
    with pytest.raises(SystemExit, match="dry run"):
        bulk.stage_balance({}, RawCache(tmp_path), args(confirm=False), session=api)
    with pytest.raises(SystemExit, match="already below the floor"):
        bulk.stage_balance({}, RawCache(tmp_path), args(floor=6_000_000), session=api)
    assert len(api.calls) == 2


@pytest.mark.parametrize("bad", [None, "abc", "9.5"])
def test_odds_pull_billing_fails_closed(tmp_path, monkeypatch, bad):
    """Review minor (day-one step 6): odds-pull counted a missing x-requests-last as 0 and crashed on a non-number.
    Now it counts the upper bound and stops with a reason, not a traceback; a fraction counts as a whole credit."""
    from types import SimpleNamespace

    from markets.oddsapi.client import OddsApiClient
    from markets.oddsapi.ingest import pull_snapshots
    monkeypatch.setenv("ODDS_API_KEY", KEY)
    sent = []

    class Api:
        def get(self, url, params=None, timeout=None):
            if url.endswith("/sports"):                  # the free key check (since the Sep 29 follow-up)
                return Resp(200, [], {"x-requests-remaining": "4000", "x-requests-last": "0"})
            sent.append(url)
            h = {"x-requests-remaining": "4000"} | ({} if bad is None else {"x-requests-last": bad})
            return Resp(200, {"timestamp": params["date"], "data": []}, h)

    oc = OddsApiClient("nba", RawCache(tmp_path), max_credits=100, rate_per_sec=1e6)
    oc.session = Api()
    ctx = SimpleNamespace(cfg=SimpleNamespace(odds_sport_key="basketball_nba", bookmakers=("pinnacle",),
                                              odds_markets="h2h"))
    plan = {"est_credits": 30, "todo": [t("2026-01-05T23:00:00Z"), t("2026-01-05T23:05:00Z"), t("2026-01-05T23:10:00Z")]}
    res = pull_snapshots(ctx, plan, 100, client=oc)
    if bad == "9.5":
        assert res["stopped"] is None and res["credits_spent"] == 30 and res["fetched"] == 3
    else:
        assert len(sent) == 1 and res["fetched"] == 1 and res["credits_spent"] == 10
        assert "billing could not be read" in res["stopped"]


# ---------------------------------------------------------------- final review of PR 57 (Sep 29): the follow-up
def _events_call(at="2024-09-03T06:00:00Z"):
    return bulk.Call("P0", "americanfootball_nfl", bulk.SRC_EVENTS, "/historical/sports/americanfootball_nfl/events",
                     (("date", at), ("dateFormat", "iso")), t(at), 1, False, cache_sport="americanfootball_nfl")


def _f1_calls(cfg, kicks=("2024-09-06T00:20:00Z",)):
    sched = {"americanfootball_nfl": [game(cfg, f"g{i}", k) for i, k in enumerate(kicks)]}
    return bulk.plan_calls(cfg, "F1", sched, now=NOW)


class Stale(FakeOddsApi):
    """Reports `last` as the cost of every paid call, and a balance that never moves after the key check."""

    def __init__(self, last="0", **kw):
        super().__init__(**kw)
        self.last, self.billed, self.frozen = last, 0, None

    def _r(self, status, body, cost):
        self.billed += cost
        r = super()._r(status, body, cost)
        self.frozen = self.frozen or r.headers["X-Requests-Remaining"]          # the key check's balance
        r.headers["X-Requests-Remaining"] = self.frozen
        if cost:
            r.headers["X-Requests-Last"] = self.last
        return r


def test_documented_cost_is_worked_out_from_the_call_and_the_body(cfg):
    """Item 1a: 10 x markets returned x regions for odds (featured and event), 1 for /events with data, 0 for an
    empty result, a 404 or a body that isn't JSON. Regions come from the call's books (one per 10)."""
    def body(markets, n_events=1):
        ev = {"id": "e", "bookmakers": [{"key": "pinnacle", "markets": [{"key": m} for m in markets]},
                                        {"key": "draftkings", "markets": [{"key": markets[0]}] if markets else []}]}
        return json.dumps({"timestamp": "x", "data": [ev] * n_events})

    (f1,) = _f1_calls(cfg)[-1:]
    assert f1.expected == 30
    assert bulk.documented_cost(f1, 200, body(["h2h", "spreads", "totals"])) == 30
    assert bulk.documented_cost(f1, 200, body(["h2h"])) == 10           # a market nobody quoted is not counted
    assert bulk.documented_cost(f1, 200, body(["h2h", "h2h_lay"])) == 10   # an exchange's lay prices: billed with h2h
    assert bulk.documented_cost(f1, 200, json.dumps({"data": []})) == 0
    assert bulk.documented_cost(f1, 404, body(["h2h"])) == 0 and bulk.documented_cost(f1, 200, "<html>") == 0
    eleven = bulk.Call("X", "americanfootball_nfl", bulk.SRC_ODDS, f1.path,
                       bulk._odds_params(cfg["books"]["us10"] + ["bovada"], "h2h,spreads", f1.at), f1.at, 40, False)
    assert bulk.documented_cost(eleven, 200, body(["h2h", "spreads"])) == 40      # 11 books = 2 regions
    props = _one_call(cfg)[0]
    one_event = json.dumps({"data": json.loads(body(["player_pass_yds", "player_rush_yds"]))["data"][0]})
    assert bulk.documented_cost(props, 200, one_event) == 20
    ev = _events_call()
    assert bulk.documented_cost(ev, 200, json.dumps({"data": [{"id": "a"}]})) == 1
    assert bulk.documented_cost(ev, 200, json.dumps({"data": []})) == 0


@pytest.mark.parametrize("last", ["0", "10"])
def test_a_response_with_data_never_counts_less_than_its_documented_cost(cfg, tmp_path, capsys, last):
    """Item 1a (final review, finding 1): x-requests-last "0" on a 200 with data, and a balance that never moves,
    counted nothing, so no budget and no floor could stop the run (60,000 billed on a 3,000 budget). Now a response
    with data counts at least its documented cost, and a report below that cost stops the run at once."""
    for calls, doc in ((_f1_calls(cfg), 30), (_one_call(cfg), 20)):     # featured 3 markets; props 2 returned
        api = Stale(last=last)
        c = client(tmp_path / f"{doc}{last}", api, max_credits=3_000, floor=0)
        c.account()
        res = bulk.run_calls(c, calls)
        assert res["fetched"] == 1 and res["spent"] == doc == api.billed, res
        assert "billing cannot be trusted" in res["stopped"] and f"reported {last} credits" in res["stopped"]
    assert "STOPPED: the billing cannot be trusted" in capsys.readouterr().out


def test_an_empty_result_reported_as_free_goes_on(cfg, tmp_path):
    """The docs don't bill an empty result, so a 0 for one is not a billing problem."""
    class Empty(Stale):
        def get(self, url, params=None, timeout=None):
            r = super().get(url, params, timeout)
            if not url.endswith("/sports"):
                r.text = json.dumps({"timestamp": params["date"], "data": []})
            return r
    res = bulk.run_calls(client(tmp_path, Empty(last="0"), floor=0), _f1_calls(cfg))
    assert res["stopped"] is None and res["fetched"] == len(_f1_calls(cfg)) and res["spent"] == 0


class Late(Billed):
    """Billed (each call's first `bad` attempts billed, then timed out), with x-requests-remaining `lag` answered
    responses late, or never moving after the key check when lag is None; the key check reads the true balance."""

    def __init__(self, lag=1, **kw):
        super().__init__(**kw)
        self.lag, self.shown = lag, []

    def get(self, url, params=None, timeout=None):
        r = super().get(url, params, timeout)
        true = r.headers["X-Requests-Remaining"]
        if url.endswith("/sports"):
            self.shown = [true] * (self.lag or 1)
        elif self.lag is None:
            r.headers["X-Requests-Remaining"] = self.shown[0]
        else:
            self.shown.append(true)
            r.headers["X-Requests-Remaining"] = self.shown.pop(0)
        return r


@pytest.mark.parametrize("lag", [1, 2, 3, None])
def test_a_late_balance_and_billed_retries_never_pass_the_budget_or_floor(cfg, tmp_path, monkeypatch, lag):
    """Billed timeouts, with the floor and a late balance. A balance that arrives late, plus attempts billed and then
    timed out, used to let runs go over the budget and under the floor by several calls, and without limit when the
    balance never moves, because a reading cleared the attempts before it showed their bill. Now an attempt with no
    answer counts its upper bound to the end of the run and the balance never clears it, so the run never passes the
    budget or the floor, however late the balance is (lag None: it never moves after the key check)."""
    calls = _f1_calls(cfg, ("2024-09-02T00:20:00Z", "2024-09-05T17:00:00Z", "2024-09-08T17:00:00Z"))   # 17, 30 each
    start = 5_000_000
    for bad in (1, 2, 3):
        for m in range(60, 600, 10):
            api = Late(lag=lag, bad=bad)
            res = bulk.run_calls(_retrying_client(tmp_path / f"b{bad}-{m}", api, monkeypatch, max_credits=m), calls)
            assert res["stopped"] and api.billed <= m, (bad, m, api.billed, res)
            api = Late(lag=lag, bad=bad)
            res = bulk.run_calls(_retrying_client(tmp_path / f"f{bad}-{m}", api, monkeypatch, floor=start - m), calls)
            assert res["stopped"] and api.remaining >= start - m, (bad, m, api.remaining, res)


def test_an_attempt_with_no_answer_stays_counted_to_the_end_of_the_run(cfg, tmp_path, monkeypatch):
    """Rule 2: an attempt with no answer counts its upper bound and stays counted to the end of the run, billed or
    not: no balance reading clears it (the balance never adds to the count)."""
    import requests

    class Unbilled(FakeOddsApi):
        seen = set()

        def get(self, url, params=None, timeout=None):
            if not url.endswith("/sports") and (url, params["date"]) not in self.seen:
                self.seen.add((url, params["date"]))
                raise requests.ReadTimeout("read timed out")          # before any billing
            return super().get(url, params, timeout)

    calls = _nfl_calls(cfg, 2)
    api = Billed(bad=1)                                           # billed 20 of its upper bound of 60, then timed out
    c = _retrying_client(tmp_path / "billed", api, monkeypatch)
    c.fetch(calls[0])
    assert c.unanswered == 60 and c.counted == 60 + 20 and api.billed == 40
    api = Unbilled()
    c = _retrying_client(tmp_path / "unbilled", api, monkeypatch)
    for call in calls:
        c.fetch(call)
    assert c.unanswered == 60 * len(calls) and c.counted == (60 + 20) * len(calls)
    assert c.remaining == 5_000_000 - c.counted                   # the estimate goes by the count, below the truth


class Overcharges(FakeOddsApi):
    """Charges `extra` more than it reports on every paid call; `others` is another user's spend before each."""

    def __init__(self, extra=0, others=0, **kw):
        super().__init__(**kw)
        self.extra, self.others, self.billed = extra, others, 0

    def _r(self, status, body, cost):
        if cost:
            self.remaining -= self.extra + self.others
            self.billed += cost + self.extra
        return super()._r(status, body, cost)


def test_other_users_of_the_key_stop_the_run_only_above_the_margin(cfg, tmp_path, capsys):
    """Rule 8: another job spending on the key lowers the balance but not the count. Below the margin the run goes on;
    once the account has fallen by more than the margin beyond what the run counted, the run stops, names the three
    possible causes and the `headers` stage. The margin is the larger of 5,000 and 10% of --max-credits, or
    --alarm-margin (at least 300). The other spending never counts toward --max-credits."""
    calls = _nfl_calls(cfg, 8)                                    # 16 calls, upper bound 60, charged 20
    for others, margin, stops in ((18, 300, False), (19, 300, True), (60, 300, True),   # 16 x 18 = 288; 16 x 19 = 304
                                  (60, None, False), (312, None, False), (313, None, True)):   # 16 x 313 = 5,008
        api = Overcharges(others=others)
        c = client(tmp_path / f"{others}-{margin}", api, max_credits=6_000, alarm_margin=margin)
        c.account()
        res = bulk.run_calls(c, calls)
        assert c.margin == (margin or 5_000) and c.counted == 20 * res["fetched"]
        if not stops:
            assert res["stopped"] is None and c.unexplained == 16 * others
        else:
            assert "the account has fallen by" in res["stopped"] and c.unexplained > c.margin >= c.unexplained - others
            assert "The cause is one of three" in res["stopped"] and "markets odds5m headers --pull F3" in res["stopped"]
    assert "STOPPED: the account has fallen by" in capsys.readouterr().out
    assert client(tmp_path / "big", max_credits=170_000).margin == 17_000     # 10% of --max-credits when that is more


def test_ctrl_c_ends_the_run_with_stopped_interrupted_and_the_summary(cfg, tmp_path, capsys):
    """Item 2 (final review, finding 4): Ctrl-C ended in a traceback with no summary. Now it ends with
    `STOPPED: interrupted`, the summary line, and the call that was out counted at its upper bound."""
    class CtrlC(FakeOddsApi):
        n = 0

        def get(self, url, params=None, timeout=None):
            if not url.endswith("/sports"):
                self.n += 1
                if self.n == 2:
                    raise KeyboardInterrupt
            return super().get(url, params, timeout)

    c = client(tmp_path, CtrlC())
    c.account()
    try:
        res = bulk.run_calls(c, _nfl_calls(cfg))
    except KeyboardInterrupt:
        pytest.fail("Ctrl-C escaped run_calls: a traceback with no summary line")
    out = capsys.readouterr().out
    assert res["stopped"].startswith("interrupted") and res["interrupted"]
    assert "STOPPED: interrupted" in out and "stopped: 1 fetched" in out and "rerun resumes" in out
    assert res["spent"] == 20 + 60                                # the call that was out, at its upper bound


def test_stop_messages_say_one_credit_and_a_probe_bug_says_tell_the_hub(cfg, tmp_path, capsys):
    """Review of the follow-up, wording: Ctrl-C during a sweep said "counted at its upper bound, 1 credits", and a bug
    in a billing probe didn't say to tell the hub before rerunning, as a bug in a pull does."""
    class CtrlC(FakeOddsApi):
        def get(self, url, params=None, timeout=None):
            if not url.endswith("/sports"):
                raise KeyboardInterrupt
            return super().get(url, params, timeout)

    c = client(tmp_path / "c", CtrlC())
    c.account()
    res = bulk.run_calls(c, [_events_call()])
    assert "counted at its upper bound, 1 credit, and a rerun" in res["stopped"]

    class Buggy(bulk.BulkClient):
        def fetch(self, call):
            raise ValueError("a bug")

    row = bulk._probe_row("p", Buggy(RawCache(tmp_path / "b"), max_credits=10), _events_call(), "x")
    assert row["stopped"] and "unexpected error, probably a bug; tell the hub before rerunning" in row["result"]
    assert "STOPPED: unexpected error, probably a bug; tell the hub before rerunning" in capsys.readouterr().out


def _saved_test_nfl(cfg, raw):
    """Two 2024 NFL games inside the test config's windows: F1 plans 9 featured calls for them."""
    bulk.save_schedule(raw, "americanfootball_nfl", [
        {**game(cfg, g, k), "home_team": "H", "away_team": "A", "first_seen": None}
        for g, k in (("ev1", "2024-09-06T00:20:00Z"), ("ev2", "2024-09-08T17:00:00Z"))])


def _main(cfg, tmp_path, monkeypatch, api, **kw):
    """bulk.main (what `markets odds5m` runs) against a fake API, a scratch cache and the test config."""
    monkeypatch.setenv("ODDS_API_KEY", KEY)
    monkeypatch.setattr(bulk, "load_config", lambda: cfg)
    monkeypatch.setattr(bulk, "RawCache", lambda: RawCache(tmp_path))
    monkeypatch.setattr(bulk, "new_session", lambda: api)
    monkeypatch.setattr(bulk, "utcnow", lambda: NOW)
    base = dict(stage="full", pull="F1", sports=None, seasons=None, week_of="auto", confirm=True, max_credits=100_000,
                floor=0, rate=1e6)
    return bulk.main(Namespace(**{**base, **kw}))


def test_every_stop_exits_with_status_1_and_done_with_0(cfg, tmp_path, monkeypatch, capsys):
    """Item 3: a STOPPED run exited with status 0. Now every stop (budget, floor, circuit breaker, Ctrl-C) exits 1;
    a finished run and a dry run exit 0."""
    class CtrlC(FakeOddsApi):
        def get(self, url, params=None, timeout=None):
            if not url.endswith("/sports"):
                raise KeyboardInterrupt
            return super().get(url, params, timeout)

    _saved_test_nfl(cfg, tmp_path / "dry")
    assert _main(cfg, tmp_path / "dry", monkeypatch, FakeOddsApi(), confirm=False) == 0
    _saved_test_nfl(cfg, tmp_path / "done")
    assert _main(cfg, tmp_path / "done", monkeypatch, FakeOddsApi()) == 0
    for name, api, kw, why in (("budget", FakeOddsApi(), {"max_credits": 40}, "run budget"),
                               ("floor", FakeOddsApi(), {"floor": 5_000_000 - 40}, "the floor is"),
                               ("breaker", FakeOddsApi(overbill=50), {}, "should cost at most"),
                               ("ctrl-c", CtrlC(), {}, "STOPPED: interrupted")):
        _saved_test_nfl(cfg, tmp_path / name)
        capsys.readouterr()
        assert _main(cfg, tmp_path / name, monkeypatch, api, **kw) == 1, name
        out = capsys.readouterr().out
        assert why in out and "stopped: " in out, name


def test_the_cli_returns_the_exit_status(cfg, tmp_path, monkeypatch):
    """`markets` is a console script (sys.exit(main())), so cli.main's return value is the exit status."""
    from markets import cli
    _saved_test_nfl(cfg, tmp_path)
    monkeypatch.setenv("ODDS_API_KEY", KEY)
    monkeypatch.setattr(bulk, "load_config", lambda: cfg)
    monkeypatch.setattr(bulk, "RawCache", lambda: RawCache(tmp_path))
    monkeypatch.setattr(bulk, "new_session", lambda: FakeOddsApi())
    monkeypatch.setattr(bulk, "utcnow", lambda: NOW)
    argv = ["odds5m", "full", "--pull", "F1", "--floor", "0", "--rate", "1000000"]
    assert cli.main(argv) == 0                                     # a dry run
    assert cli.main(argv + ["--confirm", "--max-credits", "40"]) == 1
    assert cli.main(argv + ["--confirm", "--max-credits", "100000"]) == 0


def test_a_full_disk_at_the_key_check_or_anywhere_else_ends_with_a_stopped_line(cfg, tmp_path, monkeypatch, capsys):
    """Item 2 (final review, finding 5): a full disk at the key check ended in a traceback. Now it, and a full disk
    anywhere else in a stage (here the probe's schedule files), ends with a STOPPED line and exit status 1."""
    import errno
    from pathlib import Path
    monkeypatch.setenv("ODDS_API_KEY", KEY)

    def no_space(*a, **k):
        raise OSError(errno.ENOSPC, "No space left on device")

    orig = Path.open
    monkeypatch.setattr(Path, "open", lambda self, *a, **k: no_space() if self.name == "oddsapi_manifest.csv"
                        else orig(self, *a, **k))
    api = FakeOddsApi()
    with pytest.raises(SystemExit) as ei:
        bulk._client(RawCache(tmp_path / "k"), args(max_credits=100), session=api)
    assert "STOPPED before the first paid call" in str(ei.value) and "is the disk full?" in str(ei.value)
    assert [u for u, _ in api.calls] == [bulk.BASE_URL + "/sports"]
    monkeypatch.setattr(Path, "open", orig)
    monkeypatch.setattr(bulk, "save_schedule", no_space)
    capsys.readouterr()
    assert _main(cfg, tmp_path / "p", monkeypatch, FakeOddsApi(), stage="probe", sports="americanfootball_nfl") == 1
    out = capsys.readouterr().out
    assert "STOPPED: a file could not be read or written (No space left on device): is the disk full?" in out


def test_a_probe_that_stops_keeps_the_earlier_schedules_and_names_the_incomplete_sports(cfg, tmp_path, monkeypatch,
                                                                                        capsys):
    """Item 5 (final review, finding 10): a probe that stopped on its budget overwrote the NFL schedule with a partial
    one, and the next `week --pull F3` found 0 calls. Now a sport's schedule is saved only when its sweep finished;
    the probe names the incomplete sports, and a rerun buys only what is missing and prints `P0 done`."""
    monkeypatch.setenv("ODDS_API_KEY", KEY)
    earlier = [{**game(cfg, "old", "2024-09-06T00:20:00Z"), "home_team": "H", "away_team": "A", "first_seen": None}]
    bulk.save_schedule(tmp_path, "americanfootball_nfl", earlier)
    path = bulk.schedule_path(tmp_path, "americanfootball_nfl")
    before = path.read_bytes()
    api = FakeOddsApi()
    out = bulk.stage_probe(cfg, RawCache(tmp_path), args(sports=["americanfootball_nfl"], max_credits=2), now=NOW,
                           session=api)
    printed = capsys.readouterr().out
    assert out["stopped"] and out["incomplete"] == ["americanfootball_nfl"] and path.read_bytes() == before
    assert "incomplete, schedule not saved (any earlier schedule file is kept): americanfootball_nfl" in printed
    assert "P0 stopped" in printed and "until it prints `P0 done`" in printed and not out["probes"]
    n_first = len(api.calls)
    out = bulk.stage_probe(cfg, RawCache(tmp_path), args(sports=["americanfootball_nfl"]), now=NOW, session=api)
    assert out["stopped"] is None and "P0 done" in capsys.readouterr().out and path.read_bytes() != before
    sweeps = len(bulk.sweep_calls(cfg, "americanfootball_nfl", NOW))
    assert sum(u.endswith("/events") for u, _ in api.calls[n_first:]) == sweeps - (n_first - 1)   # only what's missing


@pytest.mark.parametrize("status", [422, 500])
def test_a_sweep_that_keeps_getting_an_error_names_its_date_and_does_not_hold_up_the_probes(cfg, tmp_path, monkeypatch,
                                                                                           capsys, status):
    """Review of the follow-up, major: one /events sweep that always gets an error answer (422, or 500 after the
    retries) left its sport incomplete on every rerun, the STOPPED line didn't say which sweep, the seven billing
    probes never ran, and the runbook said to rerun until `P0 done`, forever. Now the STOPPED line names the sweep's
    date and HTTP status, the probes still run on the sweeps that finished, the summary line says an answer was an
    error, and the probe says to tell the hub if a rerun stops the same way."""
    from markets import http
    monkeypatch.setattr(http.time, "sleep", lambda s: None)
    monkeypatch.setenv("ODDS_API_KEY", KEY)
    bad = "2025-10-21T06:00:00Z"

    class Refuses(FakeOddsApi):
        def get(self, url, params=None, timeout=None):
            if (params or {}).get("date") == bad:
                self.calls.append((url, dict(params)))
                return self._r(status, {"message": "nope"}, 0)
            return super().get(url, params, timeout)

    for attempt in (1, 2):
        api = Refuses()
        out = bulk.stage_probe(cfg, RawCache(tmp_path), args(max_retries=6), now=NOW, session=api)
        printed = capsys.readouterr().out
        assert out["incomplete"] == ["basketball_nba"] and out["stopped"], attempt
        assert (f"STOPPED: the sweeps did not finish for 1 sport(s), so their schedules were not saved: basketball_nba "
                f"(1 sweep answered with an error: 2025-10-21 HTTP {status})") in printed
        assert "(1 answered with an error and not saved; a rerun asks again)" in printed
        assert "If a rerun stops again on the same sweeps with an error answer, don't keep rerunning: tell the hub" in printed
        assert bulk.schedule_path(tmp_path, "americanfootball_nfl").exists()
        assert not bulk.schedule_path(tmp_path, "basketball_nba").exists()
        assert [p["probe"] for p in out["probes"]][:3] == ["featured NFL, 10 books, 3 markets",
                                                          "event odds NFL props, 10 books",
                                                          "event odds NFL props, Pinnacle only"]
        assert not any(p.get("stopped") for p in out["probes"])
    assert sum(u.endswith("/events") for u, _ in api.calls) == (7 if status == 500 else 1)   # only the refused sweep
    status = 401                              # a stop of the run itself: its own STOPPED line, no "tell the hub" hint
    out = bulk.stage_probe(cfg, RawCache(tmp_path / "401"), args(), now=NOW, session=Refuses())
    printed = capsys.readouterr().out
    assert "STOPPED: the Odds API rejected the key (401)" in printed and not out["probes"]
    assert "Rerun the same command" in printed and "If a rerun stops again" not in printed


def test_plan_lists_every_pull_and_says_which_wait_for_the_qualifying_games(tmp_path, monkeypatch, capsys):
    """Item 6 (final review, finding 7): `plan` stopped at HB1 without the qualifying file and never listed N1, F4 or
    the March pulls. Now it lists every pull in group order; HB1 and HS1 get a line saying they wait for `markets
    weather qualifying` and count as 0 calls; it exits 0."""
    real = bulk.load_config()
    monkeypatch.setattr(bulk, "DATA_DIR", tmp_path)
    assert _main(real, tmp_path / "raw", monkeypatch, FakeOddsApi(), stage="plan", pull="all", confirm=False) == 0
    lines = capsys.readouterr().out.splitlines()
    rows = [line for line in lines if line.split()[:1] and line.split()[0] in real["pulls"]]
    assert [r.split()[0] for r in rows] == list(real["pulls"])
    for r in rows:
        waits = r.split()[0] in ("HB1", "HS1")
        assert ("waits for `markets weather qualifying`" in r) == waits and (" 0 calls" in r), r
        assert (str(tmp_path / "weather" / "heat_qualifying.csv") in r) == waits


def test_week_applies_the_slice_rule_and_drops_blank_seasons(tmp_path, monkeypatch, capsys):
    """Item 7 (final review, findings 12 and 13): `week --pull F3 --seasons 2023 --week-of 2023-09-07` planned gated
    F3b data and passed the guard; `--seasons 2025,` was refused with a confusing message. Now `week` applies the
    slice rule before anything is called, and blank entries in --seasons are dropped before the check."""
    real = bulk.load_config()
    _saved_nfl(real, tmp_path)
    now = datetime(2026, 10, 1, 12, tzinfo=UTC)
    api = FakeOddsApi()
    for seasons, why in ((["2023"], "is not one of its slices"), (None, "`week --pull F3` needs --seasons")):
        for confirm in (False, True):
            with pytest.raises(SystemExit, match=why) as ei:
                bulk.stage_pull(real, RawCache(tmp_path), args(pull="F3", seasons=seasons, week_of="2023-09-07",
                                                               confirm=confirm, max_credits=1), week=True, now=now,
                                session=api)
            assert "week --pull F3 --seasons 2025 --confirm" in str(ei.value)
    assert api.calls == []
    assert bulk._list_arg("2025,") == ["2025"] and bulk._list_arg(" ,2025,, ") == ["2025"]
    assert bulk._list_arg(",") is None and bulk._list_arg("") is None and bulk._list_arg(None) is None
    assert bulk._list_arg("2023, 2024 ,2026,") == ["2023", "2024", "2026"]
    assert _main(real, tmp_path, monkeypatch, api, pull="F3", seasons="2025,", confirm=False) == 0
    assert "F3  2 calls, 2 to fetch" in capsys.readouterr().out


def test_each_pull_summary_line_prints_its_own_counts(cfg, tmp_path, monkeypatch, capsys):
    """Item 7 (final review, finding 14): in `week --pull F1,F2` F2's summary line printed the run's fetched count."""
    monkeypatch.setenv("ODDS_API_KEY", KEY)
    sched = [{**game(cfg, "ev1", "2024-09-06T00:20:00Z"), "home_team": "H", "away_team": "A", "first_seen": None}]
    bulk.save_schedule(tmp_path, "americanfootball_nfl", sched)
    out = bulk.stage_pull(cfg, RawCache(tmp_path), args(pull="F1,F3", sports=["americanfootball_nfl"]), week=True,
                          now=NOW, session=FakeOddsApi())
    f1, f3 = out
    assert f3["fetched"] == f3["todo"] == 2 and f3["spent"] == 40 and f3["run_fetched"] == f1["fetched"] + 2
    printed = capsys.readouterr().out
    assert f"done: 2 fetched, credits 40 (this run {f1['spent'] + 40:,})" in printed


# ---------------------------------------------------------------- odds-pull (item 4)
NBA_KEY_SAMPLE = "06dae82fbad834f70cb0"     # main's (e83c7f8) cache key for the 2026-01-05T23:00Z sample-week snapshot


def _oddspull(tmp_path, api, *, n=3, floor=0, max_credits=1_000):
    from types import SimpleNamespace

    from markets.oddsapi.client import OddsApiClient
    oc = OddsApiClient("nba", RawCache(tmp_path), max_credits=max_credits, rate_per_sec=1e6, floor=floor, session=api,
                       api_key=KEY)
    ctx = SimpleNamespace(cfg=SimpleNamespace(odds_sport_key="basketball_nba", bookmakers=("pinnacle", "lowvig",
                                                                                           "betonlineag"),
                                              odds_markets="h2h"))
    plan = {"est_credits": 10 * n, "todo": [t("2026-01-05T23:00:00Z") + (i * bulk.FIVE) for i in range(n)]}
    return oc, ctx, plan


def test_odds_pull_keeps_its_cache_location_and_keys(tmp_path):
    """Item 4: odds-pull now runs through the bulk puller's client, but asks for the same snapshots and caches them
    in the same place under the same keys as before (the sample week's Kalshi data and N1 rely on them)."""
    from markets.oddsapi.ingest import pull_snapshots
    oc, ctx, plan = _oddspull(tmp_path, FakeOddsApi(), n=1)
    call = oc.call_for(sport_key="basketball_nba", at=plan["todo"][0], bookmakers=ctx.cfg.bookmakers, markets="h2h")
    assert call.key == NBA_KEY_SAMPLE and call.cache_sport == "nba" and call.source == "oddsapi_hist"
    assert pull_snapshots(ctx, plan, 1_000, client=oc)["stopped"] is None
    assert [p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*.parquet")] == [
        f"nba/oddsapi_hist/2026-01-05/{NBA_KEY_SAMPLE}.parquet"]


def test_odds_pull_has_the_key_check_floor_and_manifest(tmp_path, monkeypatch, capsys):
    """Item 4: odds-pull had no key check, no floor, no balance tracking and no manifest. Now it checks the key for
    free first and refuses to start below the floor or on an unreadable balance, and logs each paid request."""
    from markets.oddsapi.ingest import pull_snapshots
    api = FakeOddsApi(remaining=500_000)
    oc, ctx, plan = _oddspull(tmp_path / "low", api, floor=531_630)
    res = pull_snapshots(ctx, plan, 1_000, client=oc)
    assert "already below the floor of 531,630" in res["stopped"] and [u for u, _ in api.calls] == [
        bulk.BASE_URL + "/sports"]
    assert "STOPPED before the first paid call, nothing spent" in capsys.readouterr().out
    api = Mangled(sports={})
    oc, ctx, plan = _oddspull(tmp_path / "nobal", api, floor=531_630)
    assert "readable balance" in pull_snapshots(ctx, plan, 1_000, client=oc)["stopped"] and len(api.calls) == 1
    api = FakeOddsApi()
    oc, ctx, plan = _oddspull(tmp_path / "ok", api, floor=531_630)
    res = pull_snapshots(ctx, plan, 1_000, client=oc)
    assert res["stopped"] is None and res["fetched"] == 3 and res["credits_spent"] == 30
    assert api.calls[0][0].endswith("/sports")
    rows = list(csv.DictReader((tmp_path / "ok/_manifest/oddsapi_manifest.csv").open()))
    assert [r["pull"] for r in rows] == ["account", "N0", "N0", "N0"] and {r["credits_last"] for r in rows[1:]} == {"10"}
    assert rows[1]["sealed"] == "False" and rows[1]["source"] == "oddsapi_hist"
    assert KEY not in (tmp_path / "ok/_manifest/oddsapi_manifest.csv").read_text()


def test_odds_pull_counts_retries_the_balance_and_the_documented_cost(tmp_path, monkeypatch):
    """Item 4: a retried call billed twice counted once in odds-pull, and a 0 on a response with data counted 0."""
    from markets.oddsapi.ingest import pull_snapshots
    monkeypatch.setattr(__import__("markets.http", fromlist=["time"]).time, "sleep", lambda s: None)
    api = Billed(bad=1)
    oc, ctx, plan = _oddspull(tmp_path / "retry", api)
    res = pull_snapshots(ctx, plan, 1_000, client=oc)
    assert res["stopped"] is None and res["credits_spent"] == api.billed == 60
    api = Stale(last="0")
    oc, ctx, plan = _oddspull(tmp_path / "zero", api)
    res = pull_snapshots(ctx, plan, 1_000, client=oc)
    assert "billing cannot be trusted" in res["stopped"] and res["credits_spent"] == 10 and res["fetched"] == 1
    api = FakeOddsApi()                                 # the budget is checked before each call, not only up front
    oc, ctx, plan = _oddspull(tmp_path / "budget", api, max_credits=15)
    plan["est_credits"] = 10
    res = pull_snapshots(ctx, plan, 15, client=oc)
    assert "run budget" in res["stopped"] and res["fetched"] == 1


def test_odds_pull_never_caches_a_200_that_is_not_json(tmp_path, capsys):
    """Item 4 (final review, finding 6): odds-pull cached an HTML 200 and crashed on it on every rerun. Now it isn't
    cached, the pull stops with a STOPPED line and the summary, and a rerun asks again."""
    from markets.oddsapi.ingest import pull_snapshots

    class Html(FakeOddsApi):
        def _r(self, status, body, cost):
            r = super()._r(status, body, cost)
            if cost:
                r.text = "<html>busy</html>"
            return r

    for _ in range(2):
        api = Html()
        oc, ctx, plan = _oddspull(tmp_path, api)
        res = pull_snapshots(ctx, plan, 1_000, client=oc)
        assert "body that is not JSON" in res["stopped"] and res["fetched"] == 1
        assert sum("/odds" in u for u, _ in api.calls) == 1
        out = capsys.readouterr().out
        assert "STOPPED: " in out and "stopped: 1 fetched" in out
    assert not list(tmp_path.rglob("*.parquet"))


def test_the_odds_pull_command_exits_1_when_it_stops(tmp_path, monkeypatch):
    """Item 3 for odds-pull: `markets odds-pull` exits 1 when the pull stopped, 0 when it is done or a dry run. It takes
    --alarm-margin (at least 300) like odds5m, and passes it to the client."""
    from types import SimpleNamespace

    from markets import cli
    from markets.oddsapi import ingest
    ctx = SimpleNamespace(games=[], sport="nba", cache=RawCache(tmp_path))
    monkeypatch.setattr(cli, "Context", lambda sport, as_of: ctx)
    monkeypatch.setattr(ingest, "snapshot_plan", lambda ctx, games, schedule: {
        "summary": "", "tiers": {}, "bookmakers": ("pinnacle",), "credits_per_snapshot": 10, "cached": 0, "todo": [1],
        "est_credits": 10})
    seen = {}
    argv = ["odds-pull", "--start", "2026-01-05", "--end", "2026-01-11", "--max-credits", "8000"]
    for stopped, status in (("the run budget", 1), (None, 0)):
        monkeypatch.setattr(ingest, "pull_snapshots", lambda c, p, m, floor, alarm_margin: seen.update(
            floor=floor, margin=alarm_margin) or {"stopped": stopped})
        assert cli.main(argv + ["--confirm"]) == status
        assert cli.main(argv) == 0
    assert seen == {"floor": 531_630, "margin": None}
    assert cli.main(argv + ["--confirm", "--alarm-margin", "400"]) == 0 and seen["margin"] == 400
    assert cli.main(argv + ["--confirm", "--alarm-margin", "23,940"]) == 0 and seen["margin"] == 23_940   # as printed
    with pytest.raises(SystemExit) as ei:                          # argparse refuses a margin below 300
        cli.main(argv + ["--confirm", "--alarm-margin", "299"])
    assert ei.value.code == 2


def test_markets_build_skips_and_counts_a_cached_body_it_cannot_read(tmp_path, monkeypatch):
    """Item 4 (final review, finding 6): `markets build` crashed on a cached odds body that isn't JSON. Now it skips
    it, counts it, and reports it."""
    import duckdb

    from markets.build import run
    from markets.cache import write_record
    from markets.sport import load_teams
    monkeypatch.setattr(run, "RAW_DIR", tmp_path)
    good = {"timestamp": "2026-01-05T23:00:00Z", "data": [{"id": "g", "commence_time": "2026-01-06T00:30:00Z",
            "home_team": "Boston Celtics", "away_team": "New York Knicks", "bookmakers": [{"key": "pinnacle",
            "markets": [{"key": "h2h", "outcomes": [{"name": "Boston Celtics", "price": 1.5},
                                                    {"name": "New York Knicks", "price": 2.6}]}]}]}]}
    for name, body in (("good", json.dumps(good)), ("html", "<html>busy</html>"), ("list", "[1, 2]")):
        write_record(tmp_path / "nba" / "oddsapi_hist" / "2026-01-05" / f"{name}.parquet", {
            "cache_key": name, "sport": "nba", "source": "oddsapi_hist", "data_date": "2026-01-05", "url": "u",
            "params_json": json.dumps({"date": "2026-01-05T23:00:00Z"}), "fetched_at": NOW, "http_status": 200,
            "headers_json": "{}", "body": body})
    rows, unknown, sealed_out, no_kick, unreadable = run.sharp_odds_rows(duckdb.connect(), "nba", load_teams("nba"))
    assert {r["odds_event_id"] for r in rows} == {"g"} and unreadable == 2


# ---------------------------------------------------------------- sealed windows in UTC (item 8)
# The first and last game each sealed season is meant to hold, as UTC kickoffs, with the source (config/odds5m.yaml
# gives each in a comment). A window must start at least a day before the first and end at least a day after the last.
SEALED_GAMES = {
    "americanfootball_nfl": ("2026-09-10T00:20:00Z", "2027-02-14T23:30:00Z"),     # NE at SEA; Super Bowl LXI
    "americanfootball_ncaaf": ("2026-08-29T16:00:00Z", "2027-01-26T00:30:00Z"),   # TCU-UNC, Dublin; CFP title game
    "basketball_nba": ("2026-10-20T19:00:00Z", "2027-06-21T01:00:00Z"),           # opening night, 3 pm ET; Finals G7
    "icehockey_nhl": ("2026-09-29T21:00:00Z", "2027-06-27T00:00:00Z"),            # opening night; Final (as late as 2022)
    "baseball_mlb": ("2026-03-26T00:05:00Z", "2026-11-01T00:00:00Z"),             # Opening Night; World Series Game 7
    "soccer_usa_mls": ("2026-02-21T17:00:00Z", "2026-12-19T01:00:00Z"),           # matchday 1; MLS Cup (Fri Dec 18)
    "soccer_mexico_ligamx": ("2026-01-10T01:00:00Z", "2026-12-28T03:00:00Z"),     # Clausura J1; Apertura final (late)
    "soccer_brazil_campeonato": ("2026-01-28T22:00:00Z", "2026-12-03T00:30:00Z"),  # round 1; round 38
    "soccer_japan_j_league": ("2026-02-06T10:00:00Z", "2026-12-20T10:00:00Z"),    # special league; before the break
    "soccer_korea_kleague1": ("2026-02-28T05:00:00Z", "2026-12-13T05:00:00Z"),    # round 1; promotion play-off leg 2
    "soccer_fifa_world_cup": ("2026-06-11T19:00:00Z", "2026-07-19T19:00:00Z"),    # opener; final
}
@pytest.mark.parametrize("sport,which", [(s, w) for s in SEALED_GAMES for w in ("first", "last")])
def test_every_sealed_window_holds_its_first_and_last_game_in_utc(sport, which):
    """Item 8 (final review, finding 11): every sealed window must start at least a day before its season's first
    game and end at least a day after its last, in UTC. The NHL 2026-27 window starts 2026-09-28 since Sep 29, 2026
    (the hub's decision): the season opened on Sep 29. The one exception is the CFP title game (2027-01-26T00:30Z):
    the NCAAF 2026 window keeps main's end, 2027-01-25, since moving it would add the game to the March pulls, which
    is the hub's decision (review of cc14201, finding A1). The game is in no window, so nothing plans it, and
    load_rows judges any row of it by its call (test_a_game_in_no_window_is_judged_by_its_call)."""
    real = bulk.load_config()
    (w,) = [w for w in real["sports"][sport]["windows"] if w["sealed"]]
    kick = t(SEALED_GAMES[sport][0 if which == "first" else 1])
    if (sport, which) == ("americanfootball_ncaaf", "last"):
        assert w["to"] == date(2027, 1, 25) and bulk.window_for(real, sport, kick) is None
        return
    assert bulk.window_for(real, sport, kick) == w and bulk.is_sealed(real, sport, kick)
    if which == "first":
        assert w["from"] <= (kick - timedelta(days=1)).date(), (w["from"], kick)
    else:
        assert w["to"] >= (kick + timedelta(days=1)).date(), (w["to"], kick)
    assert set(SEALED_GAMES) == {s for s, sc in real["sports"].items() if any(x["sealed"] for x in sc["windows"])}


MAIN_BEFORE_PR63 = "4bf049729337b21b70e60b0c85611ae6c77f6998"     # origin/main when cc14201 was reviewed (Sep 30)


def test_nothing_bought_changed_since_main_but_the_nhl_start(tmp_path):
    """Review of cc14201, finding A1: the branch had moved the NCAAF 2026 window's end from Jan 25 to Jan 27, 2027,
    which put the CFP title game into F1, F4, F5 and F6 in March. Only the NHL change is approved. So the NCAAF window
    ends Jan 25, and against main's config (git show) the only change in a window that a pull buys from is the NHL
    2026-27 start; the MLS and K League 2026 ends moved too, but no pull buys those seasons."""
    import subprocess
    real = bulk.load_config()
    (w,) = [w for w in real["sports"]["americanfootball_ncaaf"]["windows"] if w["label"] == "2026"]
    assert w["to"] == date(2027, 1, 25)
    try:
        text = subprocess.run(["git", "show", f"{MAIN_BEFORE_PR63}:sharp-markets/config/odds5m.yaml"], check=True,
                              cwd=Path(__file__).parent, capture_output=True, text=True).stdout
    except (OSError, subprocess.CalledProcessError):
        pytest.skip(f"main's config at {MAIN_BEFORE_PR63[:7]} is not in this checkout's git history")
    (tmp_path / "main.yaml").write_text(text)
    main = bulk.load_config(tmp_path / "main.yaml")
    assert {k: main[k] for k in ("books", "featured", "pulls", "groups")} == {
        k: real[k] for k in ("books", "featured", "pulls", "groups")}
    changed = set()
    for s, sc in real["sports"].items():
        before = main["sports"][s]
        assert (sc["history_from"], sc["sweep_every_days"]) == (before["history_from"], before["sweep_every_days"])
        assert [x["label"] for x in sc["windows"]] == [x["label"] for x in before["windows"]], s
        changed |= {(s, x["label"], k) for x, y in zip(sc["windows"], before["windows"]) for k in x if x[k] != y[k]}
    assert changed == {("icehockey_nhl", "2026-27", "from"), ("soccer_usa_mls", "2026", "to"),
                       ("soccer_korea_kleague1", "2026", "to")}

    def bought(s, label):
        return any(s in p["sports"] and (not p.get("only_seasons") or label in p["only_seasons"])
                   and label not in p.get("skip_seasons", []) for p in real["pulls"].values())
    assert {c for c in changed if bought(*c[:2])} == {("icehockey_nhl", "2026-27", "from")}


def test_a_game_in_no_window_is_judged_by_its_call(tmp_path, monkeypatch):
    """Review of the follow-up, blocker 2: the NHL 2026-27 season opened on Sep 29, 2026, before its sealed window
    started, so those games had no season and bulk.load_rows returned their rows by default, from the daily-close
    snapshots planned for the sealed games of the next days. The window now starts Sep 28, and the read-side guard
    stays for any game that still falls in no window (here, made-up games on Sep 27): a row whose game falls in no
    season window is judged by its call, as a row with no game time already was: left out (and counted) when the call
    is sealed. `markets build` does the same for a snapshot taken inside a sealed window."""
    import shutil
    from collections import Counter

    import duckdb

    from markets.build import run
    from markets.cache import write_record
    from markets.sport import load_teams
    real = bulk.load_config()
    games = {"sep27a": "2026-09-27T21:00:00Z", "sep27b": "2026-09-27T23:00:00Z", "oct3": "2026-10-03T23:00:00Z"}
    sched = {"icehockey_nhl": [bulk._label(real, {"id": g, "sport": "icehockey_nhl", "commence_time": t(k)})
                               for g, k in games.items()]}
    assert [g["season"] for g in sched["icehockey_nhl"]] == [None, None, "2026-27"]      # the window starts Sep 28
    assert bulk._label(real, {"sport": "icehockey_nhl", "commence_time": t("2026-09-29T21:00:00Z")})["sealed"]

    class Lists(FakeOddsApi):
        """Featured snapshots list every game of the week ahead."""
        def get(self, url, params=None, timeout=None):
            if url.endswith("/sports"):
                return super().get(url, params, timeout)
            at = t(params["date"])
            data = [{"id": g, "commence_time": k, "home_team": "H", "away_team": "A", "bookmakers": [
                {"key": "pinnacle", "markets": [{"key": m, "outcomes": [{"name": "H", "price": 1.9}]}
                                                for m in ("h2h", "spreads", "totals")]}]}
                for g, k in games.items() if at <= t(k) <= at + timedelta(days=8)]
            return self._r(200, {"timestamp": params["date"], "data": data}, 30)

    calls = bulk.plan_calls(real, "H1", sched, now=datetime(2026, 10, 10, tzinfo=UTC))
    assert calls and all(c.sealed for c in calls)                   # planned only for the Oct 3 game
    c = client(tmp_path, Lists(), max_credits=100_000)
    assert bulk.run_calls(c, calls)["stopped"] is None
    left = Counter()
    assert bulk.load_rows(real, calls, c.cache, left_out=left) == []
    assert left["in no season window, sealed call"] > 0 and left["sealed season"] > 0
    assert {r["odds_event_id"] for r in bulk.load_rows(real, calls, c.cache, include_sealed=True)} == set(games)
    unsealed = [bulk.Call(x.pull, x.sport, x.source, x.path, x.params, x.at, x.expected, False, x.event_id,
                          x.cache_sport) for x in calls]
    assert {r["odds_event_id"] for r in bulk.load_rows(real, unsealed, c.cache)} == {"sep27a", "sep27b"}

    monkeypatch.setattr(run, "RAW_DIR", tmp_path / "build")
    monkeypatch.setattr(run, "ODDS5M_SPORT_KEY", {**run.ODDS5M_SPORT_KEY, "nba": "icehockey_nhl"})
    for day, sealed_snapshot in (("2026-09-25", False), ("2026-10-02", True)):
        body = {"timestamp": f"{day}T16:00:00Z", "data": [
            {"id": "sep27b", "commence_time": games["sep27b"], "home_team": "Boston Celtics",
             "away_team": "New York Knicks",
             "bookmakers": [{"key": "pinnacle", "markets": [{"key": "h2h", "outcomes": [
                 {"name": "Boston Celtics", "price": 1.5}, {"name": "New York Knicks", "price": 2.6}]}]}]}]}
        shutil.rmtree(tmp_path / "build", ignore_errors=True)
        write_record(tmp_path / "build" / "nba" / "oddsapi_hist" / day / f"{day}.parquet", {
            "cache_key": day, "sport": "nba", "source": "oddsapi_hist", "data_date": day, "url": "u",
            "params_json": json.dumps({"date": f"{day}T16:00:00Z"}), "fetched_at": NOW, "http_status": 200,
            "headers_json": "{}", "body": json.dumps(body)})
        rows, _, sealed_out, _, _ = run.sharp_odds_rows(duckdb.connect(), "nba", load_teams("nba"))
        assert bool(rows) != sealed_snapshot, day
        assert dict(sealed_out) == ({"2026-27 (game in no window)": 2} if sealed_snapshot else {}), day


# ---------------------------------------------------------------- review of the follow-up, round 2 (Sep 29)
class EchoesTheKey(FakeOddsApi):
    """Puts the request's key where a misbehaving server or proxy might: "paid" into every paid answer's billing
    headers, "sports" into the free key check's balance header, "body" into every paid 200's JSON body."""

    def __init__(self, where, **kw):
        super().__init__(**kw)
        self.where = where

    def get(self, url, params=None, timeout=None):
        r = super().get(url, params, timeout)
        key = params["apiKey"]
        if url.endswith("/sports"):
            if self.where == "sports":
                r.headers["X-Requests-Remaining"] = f"bad-{key}"
            return r
        if self.where == "paid":
            r.headers.update({"X-Requests-Last": f"cost-{key}", "X-Requests-Remaining": f"left-{key}"})
        elif self.where == "body" and r.status_code == 200:
            body = json.loads(r.text)
            body["message"] = f"served GET {url}?apiKey={key} for {key}"
            r.text = json.dumps(body)
        return r


@pytest.mark.parametrize("where", ["paid", "sports", "body"])
def test_a_key_echoed_into_a_billing_header_or_a_body_never_shows(cfg, tmp_path, monkeypatch, capsys, caplog, where):
    """Round 2, blocker: a billing header that carried the key was printed in the STOPPED line (x-requests-last
    'cost-<key>'), in the key check's refusal (x-requests-remaining 'bad-<key>'), and saved in the cache's headers, and
    a 200 body that echoed the request was cached as it came. Now every header value is scrubbed when it arrives, every
    STOPPED line is scrubbed when it is printed, and a 200's body has the key itself blanked, for odds5m (balance,
    probe, full) and odds-pull alike."""
    from markets.oddsapi.ingest import pull_snapshots
    caplog.set_level(logging.DEBUG)
    exits, rcs = [], []
    for stage, kw in (("balance", {}), ("probe", {"sports": "americanfootball_nfl"}), ("full", {})):
        _saved_test_nfl(cfg, tmp_path / stage)
        try:
            rcs.append(_main(cfg, tmp_path / stage, monkeypatch, EchoesTheKey(where), stage=stage, **kw))
        except SystemExit as e:
            exits.append(str(e))
    oc, ctx, plan = _oddspull(tmp_path / "odds-pull", EchoesTheKey(where))
    res = pull_snapshots(ctx, plan, 1_000, client=oc)
    out = capsys.readouterr()
    stored = "".join(p.read_bytes().decode("latin-1") for p in tmp_path.rglob("*") if p.is_file())
    for place, text in {"stdout": out.out, "stderr": out.err, "log": caplog.text, "files": stored,
                        "exits": " ".join(exits), "odds-pull": str(res["stopped"])}.items():
        assert KEY not in text, place
    if where == "paid":
        assert "x-requests-last 'cost-REDACTED'" in out.out and rcs[1:] == [1, 1] and res["stopped"]
    elif where == "sports":
        assert len(exits) == 3 and all("x-requests-remaining is 'bad-REDACTED'" in e for e in exits)
        assert "'bad-REDACTED'" in res["stopped"]
    else:
        assert rcs == [0, 0, 0] and res["stopped"] is None and "REDACTED" in stored


def test_a_cached_probe_answer_prints_its_billing_header_without_the_key(tmp_path):
    """Round 2, blocker: a probe's JSON line printed the cached x-requests-last as it was stored."""
    from markets import http
    from markets.cache import write_record
    http.remember_secret(KEY)
    call = _events_call()
    c = bulk.BulkClient(RawCache(tmp_path), max_credits=0)
    write_record(tmp_path / call.cache_sport / call.source / "2024-09-03" / f"{call.key}.parquet", {
        "cache_key": call.key, "sport": call.cache_sport, "source": call.source, "data_date": "2024-09-03",
        "url": call.url, "params_json": "{}", "fetched_at": NOW, "http_status": 200,
        "headers_json": json.dumps({"x-requests-last": f"cost-{KEY}"}), "body": json.dumps({"data": []})})
    assert bulk._probe_row("p", c, call, "x")["billed"] == "cost-REDACTED"


def _nba_first(cfg):
    """The test config with the NBA swept first (11 daily sweeps, Oct 20-30, 2025), then the NFL."""
    cfg["sports"]["basketball_nba"]["windows"][0]["to"] = date(2025, 10, 30)
    cfg["sports"] = {s: cfg["sports"][s] for s in ("basketball_nba", "americanfootball_nfl")}
    return cfg


class RefusesNba(FakeOddsApi):
    """Answers every NBA /events sweep with `nba_status` (the API's answer to a date outside its history is a 422)."""

    def __init__(self, nba_status, **kw):
        super().__init__(**kw)
        self.nba_status = nba_status

    def get(self, url, params=None, timeout=None):
        if "/basketball_nba/events" in url:
            self.calls.append((url, dict(params)))
            return self._r(self.nba_status, {"message": "INVALID_HISTORICAL_TIMESTAMP"}, 0)
        return super().get(url, params, timeout)


def test_a_sport_whose_sweeps_keep_getting_refused_is_skipped_and_the_others_go_on(cfg, tmp_path, monkeypatch,
                                                                                 capsys):
    """Round 2, major 1: five refused sweeps in a row in one sport stopped the whole probe at the same place on every
    rerun: no schedule was saved for any sport, the sports after it were never swept, and the probes never ran. Now
    the refused sport is skipped after five refusals in a row (the count starts again with each sport), the other
    sports' sweeps and the probes go on, and the STOPPED line and the hint say what happened. A run of server errors
    (HTTP 5xx, each retried first) still stops the probe, and then the probe says to tell the hub."""
    from markets import http
    monkeypatch.setattr(http.time, "sleep", lambda s: None)
    monkeypatch.setenv("ODDS_API_KEY", KEY)
    cfg = _nba_first(cfg)
    for attempt in (1, 2):
        api = RefusesNba(422)
        out = bulk.stage_probe(cfg, RawCache(tmp_path), args(), now=NOW, session=api)
        printed = capsys.readouterr().out
        assert sum("/basketball_nba/events" in u for u, _ in api.calls) == 5, attempt       # then skipped
        assert out["incomplete"] == ["basketball_nba"] and out["skipped"] == {"basketball_nba": 6}
        assert bulk.schedule_path(tmp_path, "americanfootball_nfl").exists()
        assert not bulk.schedule_path(tmp_path, "basketball_nba").exists()
        assert out["probes"][0]["probe"] == "featured NFL, 10 books, 3 markets" and not out["probes"][0].get("stopped")
        assert ("basketball_nba (5 sweeps answered with an error: 2025-10-20 HTTP 422, 2025-10-21 HTTP 422, 2025-10-22 "
                "HTTP 422 and 2 more; 6 sweeps skipped after 5 errors in a row)") in printed
        assert "basketball_nba: 5 errors in a row; the last was HTTP 422" in printed
        assert "If a rerun stops again on the same sweeps with an error answer, don't keep rerunning: tell the hub" in printed
    api = RefusesNba(500)
    out = bulk.stage_probe(cfg, RawCache(tmp_path / "5xx"), args(), now=NOW, session=api)
    printed = capsys.readouterr().out
    assert "STOPPED: 5 errors in a row; the last was HTTP 500" in printed and not out["probes"]
    assert not any("/americanfootball_nfl/" in u for u, _ in api.calls)
    assert "Tell the hub before rerunning" in printed and "Rerun the same command" not in printed


def test_the_probe_says_rerun_only_after_a_stop_a_rerun_cannot_make_worse(cfg, tmp_path, monkeypatch, capsys):
    """Round 2, major 2: after a billing alarm the probe said to rerun until `P0 done`. The rerun bought more, and once
    the alarm's answers were cached it printed `P0 done` with the alarm gone; with sweeps reported as free, following
    the hint never ended. Now a billing alarm or the floor says to tell the hub before rerunning; a budget stop says to
    rerun."""
    monkeypatch.setenv("ODDS_API_KEY", KEY)
    nfl = ["americanfootball_nfl"]
    tell, rerun = "Tell the hub before rerunning", "Rerun the same command until it prints `P0 done`"
    for name, api, kw, why, hint in (
            ("overbilled", FakeOddsApi(overbill=50), {}, "billed 80 credits", tell),
            ("sweeps free", Mangled(put={"X-Requests-Last": "0"}), {}, "the billing cannot be trusted", tell),
            ("floor", FakeOddsApi(), {"floor": 5_000_000 - 20}, "the floor is", tell),
            ("budget", FakeOddsApi(), {"max_credits": 2}, "run budget", rerun)):
        out = bulk.stage_probe(cfg, RawCache(tmp_path / name), args(sports=nfl, **kw), now=NOW, session=api)
        printed = capsys.readouterr().out
        assert why in out["stopped"] and hint in printed, name
        assert (tell if hint == rerun else rerun) not in printed, name


class ToppedUp(Overcharges):
    """Overcharges, and `add` credits land on the account just before the `at`-th paid answer (a top-up or the
    monthly renewal), so that answer's balance is higher than the one before it."""

    def __init__(self, at=0, add=1_000_000, **kw):
        super().__init__(**kw)
        self.at, self.add, self.n = at, add, 0

    def _r(self, status, body, cost):
        if cost:
            self.n += 1
            if self.n == self.at:
                self.remaining += self.add
        return super()._r(status, body, cost)


def test_a_balance_that_rises_mid_run_starts_the_run_again_from_there(cfg, tmp_path, caplog):
    """Rule 6: credits added mid-run (a top-up, the monthly renewal) make a balance higher than the one before it. The
    run logs one warning and starts again from there: the start becomes that balance plus the count so far, and the
    floor is measured from it. The count is untouched: the balance never adds to it or takes from it."""
    api = ToppedUp(at=3)                                          # +1,000,000 lands before the 3rd paid answer
    c = client(tmp_path, api, max_credits=10_000, floor=5_000_000 - 100)
    c.account()
    res = bulk.run_calls(c, _nfl_calls(cfg, 8))                   # 16 calls at 20: the old floor would stop call 4
    assert res["stopped"] is None and res["fetched"] == 16 and c.counted == api.billed == 320
    assert c.start == 6_000_000 and c.remaining == api.remaining == 6_000_000 - 320 and c.unexplained == 0
    assert caplog.text.count("the reported balance rose from 4,999,960 to 5,999,940") == 1


@pytest.mark.parametrize("at", [0, 2, 3])
def test_the_alarm_still_works_after_a_rise(cfg, tmp_path, at):
    """Rule 6 with rule 8: after credits are added (a rise of a million, far above the margin) the unexplained fall is
    measured from the new start, so an API charging more than it reports (120 for a call it reports as 20) still stops
    the run once the account has fallen by more than the margin (300 here, set by --alarm-margin) beyond the count
    after the rise. What went unexplained up to the rise (100 a call) is not counted again: that, the margin and one
    call's extra is what can pass unseen. at=0: no rise (the control)."""
    api = ToppedUp(at=at, extra=100)
    c = client(tmp_path, api, max_credits=6_000, alarm_margin=300)
    c.account()
    res = bulk.run_calls(c, _nfl_calls(cfg, 8))
    assert "the account has fallen by" in res["stopped"]
    assert api.billed - c.counted == 300 + 100 + 100 * at, (api.billed, c.counted)


# ---------------------------------------------------------------- the accounting rule, simplified (Sep 29, round 4)
EVENT3 = {"id": "g", "commence_time": "2024-09-06T00:20:00Z", "home_team": "H", "away_team": "A", "bookmakers": [
    {"key": "pinnacle", "markets": [{"key": m, "outcomes": [{"name": "H", "price": 1.9}]}
                                    for m in ("h2h", "spreads", "totals")]}]}


class Scripted:
    """Answers each paid request with the next of `answers`, (status, x-requests-last, x-requests-remaining), a None
    header left out; a 200 carries one F1 snapshot with its three markets (documented cost 30)."""

    def __init__(self, answers, start=1_000):
        self.answers, self.start, self.paid = list(answers), start, 0

    def get(self, url, params=None, timeout=None):
        if url.endswith("/sports"):
            return Resp(200, [], {"x-requests-remaining": str(self.start), "x-requests-last": "0"})
        self.paid += 1
        status, last, left = self.answers.pop(0)
        body = {"timestamp": params["date"], "data": [EVENT3]} if status == 200 else {"message": "busy"}
        return Resp(status, body, {k: v for k, v in (("x-requests-last", last), ("x-requests-remaining", left)) if v})


def test_every_http_answer_is_counted_before_the_retry_is_decided(cfg, tmp_path, monkeypatch, capsys):
    """Rule 3a (Astra C2): a 429 or 5xx about to be retried is an answer. Its billing headers are read first: a
    readable cost is counted, an unreadable one counts the upper bound, and one above the upper bound stops the run
    with no retry. Astra's case: budget 60, a 500 reporting 300 credits (balance 700), then a 200 reporting 30: the run
    used to retry and buy 30 more; now it stops after the 500, with 300 counted."""
    (call,) = _f1_calls(cfg)[-1:]                                 # upper bound 30
    cases = [([(500, "300", "700"), (200, "30", "670")], 60, 1, 300, "billed 300 credits; it should cost at most 30"),
             ([(500, "30", "970"), (200, "30", "940")], 1_000, 2, 60, None),
             ([(503, None, None), (200, "30", "970")], 1_000, 2, 60, None),     # unreadable: its upper bound
             ([(429, "0", "1000"), (200, "30", "970")], 1_000, 2, 30, None),
             ([(500, "30", "970"), (200, "30", "940")], 50, 1, 30, "retrying")]  # 30 + 30 > 50: no retry
    for i, (answers, budget, sent, counted, why) in enumerate(cases):
        api = Scripted(answers)
        c = _retrying_client(tmp_path / str(i), api, monkeypatch, max_credits=budget)
        res = bulk.run_calls(c, [call])
        assert (api.paid, c.counted) == (sent, counted), i
        assert (res["stopped"] is None) == (why is None) and (why is None or why in res["stopped"]), (i, res["stopped"])
    assert "(HTTP 500, not retried)" in capsys.readouterr().out
    rows = list(csv.DictReader((tmp_path / "1/raw/_manifest/oddsapi_manifest.csv").open()))
    assert [(r["http_status"], r["credits_last"]) for r in rows[1:]] == [("500", "30"), ("200", "30")]


def test_a_call_never_returns_while_the_run_is_past_its_budget(cfg, tmp_path, monkeypatch):
    """Rule 3b: after a call's last answer, a count past --max-credits stops the run with a STOPPED line. Here the
    check before each call is switched off, as if an answer had counted more than the check allowed for."""
    c = client(tmp_path, FakeOddsApi(), max_credits=50)
    monkeypatch.setattr(c, "_precheck", lambda call, what="": None)
    res = bulk.run_calls(c, _f1_calls(cfg))                      # 30 each
    assert res["fetched"] == 2 and "took the count to 60, past the 50-credit run budget" in res["stopped"]


class MemCache(RawCache):
    """The cache in a dict, for runs of thousands of calls (same lookup and get_or_fetch contract; see `fast`). The
    manifest, when a test writes one, goes under `raw_dir`."""

    def __init__(self, raw_dir=Path("/nonexistent")):
        super().__init__(raw_dir)
        self.mem = {}

    def lookup(self, sport, source, key):
        return (self, (sport, source, key)) if (sport, source, key) in self.mem else None

    def get_or_fetch(self, *, sport, source, data_date, url, params, fetch, key_extra=None, cache_statuses=(200, 404),
                     refresh=False):
        k = (sport, source, cache_key(source, url, params))
        if k in self.mem and not refresh:
            return self.mem[k]
        f = fetch()
        rec = {"cache_key": k[2], "http_status": f.status, "body": f.body,
               "headers_json": json.dumps({h: v for h, v in f.headers.items() if h.startswith("x-requests-")})}
        if f.status in cache_statuses:
            self.mem[k] = rec
        return rec


class Ledger:
    """A fast fake API for long runs. Every paid call is an F1 snapshot with its three markets (upper bound and
    documented cost 30), charged `charge` and reported as `report`. `others` credits are spent by another job before
    each call; a share `timeouts` of attempts is charged and then times out. x-requests-remaining is the balance as of
    `lag()` answers ago (0: live), or the key check's balance forever when `frozen`."""
    BODY = json.dumps({"timestamp": "2024-09-01T16:00:00Z", "data": [EVENT3]})

    def __init__(self, lag=lambda: 0, charge=30, report=30, others=0, timeouts=0.0, bill_timeouts=True, frozen=False,
                 seed=0, start=5_000_000, every=0, events=None):
        self.lag, self.charge, self.report, self.others, self.frozen = lag, charge, report, others, frozen
        self.timeouts, self.bill_timeouts, self.every, self.events = timeouts, bill_timeouts, every, events or {}
        self.rnd, self.true, self.billed = random.Random(seed), start, 0
        self.hist = [start]

    def get(self, url, params=None, timeout=None):
        """`every`: the balance is refreshed only every that many answers (the key check reads the same cached value).
        `events`: {paid call number: credits the account gains (a top-up) or loses (another user) just before it}."""
        if url.endswith("/sports"):
            n = len(self.hist) - 1
            shown = self.hist[n - n % self.every] if self.every else self.true
            return Resp(200, "[]", {"x-requests-remaining": str(shown), "x-requests-last": "0"})
        self.true += self.events.get(len(self.hist), 0) - self.others
        timed_out = self.timeouts and self.rnd.random() < self.timeouts
        if not timed_out or self.bill_timeouts:
            self.true -= self.charge
            self.billed += self.charge
        if timed_out:
            raise requests.ReadTimeout("read timed out")
        self.hist.append(self.true)
        n = len(self.hist) - 1
        lag = n if self.frozen else n % self.every if self.every else self.lag()
        shown = self.hist[max(0, n - lag)]
        return Resp(200, self.BODY, {"x-requests-last": str(self.report), "x-requests-remaining": str(shown)})


_F1_5000: list = []


def _f1_5000():
    """5,000 F1 snapshots, 5 minutes apart (upper bound 30 each: a 150,000-credit pull)."""
    if not _F1_5000:
        t0, books = t("2024-09-01T16:00:00Z"), CFG_YAML.split("us10: [")[1].split("]")[0].split(", ")
        _F1_5000.extend(bulk.Call("F1", "americanfootball_nfl", bulk.SRC_ODDS, "/historical/sports/americanfootball_nfl/odds",
                                  bulk._odds_params(books, "h2h,spreads,totals", t0 + i * bulk.FIVE), t0 + i * bulk.FIVE,
                                  30, False, cache_sport="americanfootball_nfl") for i in range(5_000))
    return _F1_5000


@pytest.fixture
def fast(monkeypatch):
    """Runs of thousands of calls in memory: the cache in a dict (MemCache), no manifest file, no rate limit or sleeps,
    and the log quiet. Returns run(api, calls, **client options) -> (client, run_calls result)."""
    import contextlib
    import io

    from markets import http
    monkeypatch.setattr(bulk, "read_record", lambda p: p[0].mem[p[1]])
    monkeypatch.setattr(bulk, "read_status", lambda p: p[0].mem[p[1]]["http_status"], raising=False)
    monkeypatch.setattr(bulk.BulkClient, "_log", lambda self, row: None)
    monkeypatch.setattr(http.RateLimiter, "wait", lambda self: None)
    monkeypatch.setattr(http.time, "sleep", lambda s: None)
    monkeypatch.setattr(bulk.log, "disabled", True)
    monkeypatch.setattr(http.log, "disabled", True)

    def run(api, calls, **kw):
        c = bulk.BulkClient(MemCache(), session=api, api_key=KEY, **{"max_credits": 157_500, "floor": 531_630, **kw})
        c.account()
        with contextlib.redirect_stdout(io.StringIO()):
            return c, bulk.run_calls(c, calls)
    return run


@pytest.mark.parametrize("lag", [1, 2, 3, "0-3 at random"])
def test_an_honest_run_never_stops_on_a_late_balance(fast, lag):
    """Rules 3, 7 and 8: a balance header that is late, by a fixed number of answers or by one drawn at random from
    0-3 for every answer, only keeps the lowest balance above the truth, so an honest 5,000-call pull with its budget
    5% above its upper bound finishes with no stop (100 seeds for the random lag), and counts exactly what it was
    charged. (Round 3's rule counted each apparent rise from a late reading as spending, and stopped every such run.)"""
    for seed in range(100 if lag == "0-3 at random" else 1):
        rnd = random.Random(seed)
        api = Ledger(lag=(lambda: lag) if isinstance(lag, int) else (lambda: rnd.randint(0, 3)), seed=seed)
        c, res = fast(api, _f1_5000())
        assert res["stopped"] is None and res["fetched"] == 5_000, (seed, res["stopped"])
        assert c.counted == api.billed == 150_000 and c.unexplained <= 3 * 30, seed


def test_a_balance_that_never_moves_stops_nothing_and_the_floor_goes_by_the_count(fast):
    """Rule 7: when x-requests-remaining never moves, the lowest balance stays at the start, so the estimate is the
    start less the count: an honest run finishes, and the floor stops a run by the count alone."""
    api = Ledger(frozen=True)
    c, res = fast(api, _f1_5000())
    assert res["stopped"] is None and c.counted == api.billed and c.unexplained == -c.counted
    api = Ledger(frozen=True)
    c, res = fast(api, _f1_5000(), floor=5_000_000 - 3_000)
    assert "the floor is 4,997,000" in res["stopped"] and res["fetched"] == 100 and api.true >= 5_000_000 - 3_000


@pytest.mark.parametrize("lag", [0, 3, "0-3 at random"])
def test_the_floor_holds_with_a_late_balance(fast, lag):
    """Rule 7: the estimate is the lower of the lowest balance reported and the start less the count. A late balance
    only keeps the lowest above the truth, and an out-of-date reading is ignored (rule 6), so the start less the count
    is the truth on an honest API: the run stops before the account goes below --floor, however late the balance is,
    by a fixed number of answers or a varying one. (Round 4's rule 6 restarted the run from a stale reading, so the
    floor stop could come as many answers late as the balance.)"""
    for seed in range(20):
        rnd = random.Random(seed)
        api = Ledger(lag=(lambda: lag) if isinstance(lag, int) else (lambda: rnd.randint(0, 3)), seed=seed)
        c, res = fast(api, _f1_5000(), floor=5_000_000 - 30_000)
        assert "the floor is 4,970,000" in res["stopped"] and api.true >= 5_000_000 - 30_000, seed


@pytest.mark.parametrize("lag", [0, 1, 3, "0-3 at random"])
def test_an_api_charging_ten_times_what_it_reports_trips_the_alarm_within_the_margin_and_the_lag(fast, lag):
    """Rule 8: an API that charges 300 for a call it reports as 30 (as documented) is seen only in the balance. The
    alarm stops the run once the account has fallen by more than the margin (15,750: 10% of 157,500) beyond the count,
    so what is lost beyond the count is at most the margin, the charges of the answers the balance is late by, and one
    call's extra. That holds when the lateness varies too (rule 6 amended: an out-of-date reading no longer restarts
    the run, which let 54 of 100 such runs finish the pull unalarmed in round 4)."""
    for seed in range(20 if lag == "0-3 at random" else 1):
        rnd = random.Random(seed)
        api = Ledger(lag=(lambda: lag) if isinstance(lag, int) else (lambda: rnd.randint(0, 3)), charge=300,
                     report=30, seed=seed)
        c, res = fast(api, _f1_5000())
        k = lag if isinstance(lag, int) else 3
        assert "the account has fallen by" in res["stopped"] and c.margin == 15_750, seed
        assert api.billed - c.counted <= c.margin + k * 300 + 270, (seed, api.billed, c.counted)


def test_a_balance_whose_lateness_varies_no_longer_switches_the_alarm_off(fast):
    """Review round 4, major 2 (the hub's Q2): with the balance late by 0-2 answers at random and the API charging
    twice what it reports, round 4's rule never raised the alarm in 100 of 100 runs (the whole F1 pull paid double).
    With rule 6 amended, every run stops on the alarm within the margin plus the lag."""
    for seed in range(50):
        rnd = random.Random(seed)
        api = Ledger(lag=lambda: rnd.randint(0, 2), charge=60, report=30, seed=seed)
        c, res = fast(api, _f1_5000())
        assert "the account has fallen by" in res["stopped"], seed
        assert api.billed - c.counted <= c.margin + 2 * 60 + 30, (seed, api.billed, c.counted)


@pytest.mark.parametrize("billed", [True, False])
def test_billed_timeouts_count_their_upper_bound_and_never_pass_the_budget(fast, billed):
    """Rule 2: an attempt that times out counts its upper bound for the rest of the run, whether or not it was billed.
    With 2% of attempts timing out, a 5,000-call pull with the usual 5% margin finishes; the count is never below
    what was charged, and a late balance never raises the alarm, because the count only goes up."""
    for seed in range(5):
        rnd = random.Random(seed)
        api = Ledger(timeouts=0.02, bill_timeouts=billed, seed=seed, lag=lambda: rnd.randint(0, 3))
        c, res = fast(api, _f1_5000(), max_retries=6)
        assert res["stopped"] is None and res["fetched"] == 5_000 and c.counted >= api.billed, seed
        assert c.unanswered > 0 and (c.counted == api.billed) == billed
    small = Ledger(timeouts=0.3, seed=1)
    c, res = fast(small, _f1_5000()[:200], max_credits=3_000, max_retries=6)
    assert "run budget" in res["stopped"] and small.billed <= 3_000 <= c.counted + 30


def test_odds_pull_stops_at_the_key_check_or_after_the_first_overcharged_call(tmp_path):
    """Astra C1: two NBA sample-week snapshots expected at 10 credits that report 300 each, with a balance below the
    floor. odds-pull runs on the bulk client, so it refuses at the key check (nothing bought), and with no floor it
    stops after the first call. The hub's Q3: a client that stopped refuses every later attempt with the same stop, so
    a caller that catches each exception and calls again (as a script might) never sends the second call."""
    from markets.oddsapi.ingest import pull_snapshots

    class Astra:
        def __init__(self):
            self.paid = 0

        def get(self, url, params=None, timeout=None):
            if url.endswith("/sports"):
                return Resp(200, [], {"x-requests-remaining": "500000", "x-requests-last": "0"})
            self.paid += 1
            return Resp(200, {"timestamp": params["date"], "data": []},
                        {"x-requests-last": "300", "x-requests-remaining": "500000"})

    api = Astra()
    oc, ctx, plan = _oddspull(tmp_path / "floor", api, n=2, floor=531_630)
    res = pull_snapshots(ctx, plan, 1_000, client=oc)
    assert api.paid == 0 and "already below the floor of 531,630" in res["stopped"]
    api = Astra()
    oc, ctx, plan = _oddspull(tmp_path / "no-floor", api, n=2)
    res = pull_snapshots(ctx, plan, 1_000, client=oc)
    assert api.paid == 1 and res["credits_spent"] == 300 and "billed 300 credits; it should cost at most 10" in res["stopped"]
    api = Astra()
    oc, ctx, plan = _oddspull(tmp_path / "direct", api, n=2)
    stops = []
    for at in plan["todo"]:                                         # a caller that catches each exception
        try:
            oc.historical_odds(sport_key="basketball_nba", at=at, bookmakers=ctx.cfg.bookmakers)
        except bulk.CircuitBreaker as e:
            stops.append(str(e))
    assert api.paid == 1 and oc.counted == 300 and len(stops) == 2 and stops[0] == stops[1]
    assert "billed 300 credits; it should cost at most 10" in stops[1]


@pytest.mark.parametrize("echo", [False, True])
def test_a_body_is_kept_exactly_as_sent_unless_it_holds_the_key(cfg, tmp_path, caplog, echo):
    """Astra C3: every body, HTTP 200 included, has the active key blanked before it is cached, printed, logged or
    raised: its exact value and its URL-encoded forms, and nothing else, so no odds data can change. A body without
    the key is stored byte for byte as the server sent it, even text that looks like a query string; one that held the
    key logs one warning per answer. The manifest's sha256 is of the body as stored."""
    import hashlib
    from urllib.parse import quote, quote_plus
    key = "FAKE/SECRET KEY+999"                                     # URL-encodes two ways (%20 and +)

    class Echo(FakeOddsApi):
        def __init__(self):
            super().__init__()
            self.sent = []

        def get(self, url, params=None, timeout=None):
            r = super().get(url, params, timeout)
            if not url.endswith("/sports"):
                body = json.loads(r.text)
                body["note"] = "see ?apiKey=someone&token=abc"         # looks like a secret, isn't the key
                if echo:
                    body["message"] = f"GET ?apiKey={quote(key, safe='')} {quote_plus(key)} for {params['apiKey']}"
                r.text = json.dumps(body, separators=(",", ":"))
                self.sent.append(r.text)
            return r

    caplog.set_level(logging.WARNING)
    api = Echo()
    c = bulk.BulkClient(RawCache(tmp_path / "raw"), max_credits=10_000, session=api, api_key=key, rate_per_sec=1e6,
                        max_retries=0)
    c.account()
    calls = _one_call(cfg)
    assert bulk.run_calls(c, calls)["stopped"] is None
    stored = [c.cached_record(x)["body"] for x in calls]
    rows = list(csv.DictReader((tmp_path / "raw/_manifest/oddsapi_manifest.csv").open()))[1:]
    assert [r["sha256"] for r in rows] == [hashlib.sha256(b.encode()).hexdigest() for b in stored]
    assert all("?apiKey=someone&token=abc" in b for b in stored)
    if not echo:
        assert stored == api.sent
    else:
        assert quote(key, safe="") != quote_plus(key) and "REDACTED" in stored[0]
        assert all(key not in b and quote(key, safe="") not in b and quote_plus(key) not in b for b in stored)
        assert stored == [s.replace(key, "REDACTED").replace(quote(key, safe=""), "REDACTED").replace(
            quote_plus(key), "REDACTED") for s in api.sent]
    assert caplog.text.count("the API echoed the key") == (2 if echo else 0)


class Gone(FakeOddsApi):
    """Answers event odds for the games in `gone` with a 404 (nothing there, no charge); `fail` answers them 500."""

    def __init__(self, gone=(), fail=False, **kw):
        super().__init__(**kw)
        self.gone, self.fail = set(gone), fail

    def get(self, url, params=None, timeout=None):
        if "/events/" in url and url.split("/events/")[1].split("/")[0] in self.gone:
            self.calls.append((url, dict(params)))
            return self._r(500 if self.fail else 404, {"message": "Event not found"}, 0)
        return super().get(url, params, timeout)


def test_404s_stay_cached_are_counted_and_retry_404_asks_them_again(cfg, tmp_path, monkeypatch, capsys):
    """Astra C4: a 404 stays cached as "nothing there at that time", so a rerun doesn't ask again; errors other than
    404 are never cached. Every run's summary line and the check stage count a pull's cached 404s, and --retry-404
    asks them again under the usual budget and floor, replacing a 404 only with a 200."""
    from markets import http
    monkeypatch.setattr(http.time, "sleep", lambda s: None)
    calls = _nfl_calls(cfg, 2)                                     # ev0 and ev1, two snapshots each
    raw = tmp_path / "raw"

    def run(api, **kw):
        c = bulk.BulkClient(RawCache(raw), max_credits=kw.pop("max_credits", 10_000), session=api, api_key=KEY,
                            rate_per_sec=1e6, max_retries=0)
        c.account()
        return bulk.run_calls(c, calls, **kw), capsys.readouterr().out

    res, out = run(Gone({"ev0"}))
    assert res["cached_404"] == 2 and "cached 404s 2" in out and res["errors"] == 0
    assert bulk.coverage(cfg, calls, RawCache(raw))["cached_404"] == 2
    api = Gone({"ev0"})
    res, out = run(api)                                            # a plain rerun asks nothing
    assert res["todo"] == 0 and api.calls[1:] == [] and "cached 404s 2" in out
    for still in (Gone({"ev0"}), Gone({"ev0"}, fail=True)):        # still missing, or an error: the 404 stays
        res, out = run(still, retry_404=True)
        assert res["todo"] == 2 and "(2 of them cached 404s asked again)" in out and res["cached_404"] == 2
    res, out = run(Gone(), retry_404=True, max_credits=70)        # 20 counted + 60 > 70: the budget still holds
    assert res["fetched"] == 1 and "run budget" in res["stopped"] and res["cached_404"] == 1
    res, out = run(Gone(), retry_404=True)
    assert res["cached_404"] == 0 and "cached 404s 0" in out
    assert bulk.coverage(cfg, calls, RawCache(raw))["cached_ok"] == 4
    with pytest.raises(SystemExit, match="--retry-404 works with week and full, not check"):
        _main(cfg, tmp_path / "cli", monkeypatch, FakeOddsApi(), stage="check", retry_404=True)


def test_ctrl_c_just_after_an_answer_counts_it_at_what_it_cost(cfg, tmp_path, monkeypatch):
    """Review round 3, minor a: Ctrl-C between an answer's arrival and its count left it uncounted and out of the
    manifest, while the STOPPED line said it was counted at its upper bound. Now the answer is counted at what it
    cost and logged, and the line says so: saved (a rerun doesn't buy it again) or not (a rerun does)."""
    from markets import cache as cache_mod

    class InterruptAfterSave(RawCache):
        def get_or_fetch(self, **kw):
            rec = super().get_or_fetch(**kw)
            if len(list(self.raw_dir.rglob("*.parquet"))) == 2:
                raise KeyboardInterrupt
            return rec

    c = bulk.BulkClient(InterruptAfterSave(tmp_path / "a"), max_credits=10_000, session=FakeOddsApi(), api_key=KEY,
                        rate_per_sec=1e6, max_retries=0)
    c.account()
    res = bulk.run_calls(c, _nfl_calls(cfg))
    assert res["interrupted"] and c.counted == 40 and res["fetched"] == 2
    assert "had come back and was saved, so it is counted at what it cost, 20 credits." in res["stopped"]
    rows = list(csv.DictReader((tmp_path / "a/_manifest/oddsapi_manifest.csv").open()))[1:]
    assert [r["credits_last"] for r in rows] == ["20", "20"]
    writes = []

    def interrupted_write(path, record):
        writes.append(path)
        raise KeyboardInterrupt

    monkeypatch.setattr(cache_mod, "write_record", interrupted_write)
    c = client(tmp_path / "b", FakeOddsApi())
    c.account()
    res = bulk.run_calls(c, _nfl_calls(cfg))
    assert c.counted == 20 and "counted at what it cost, 20 credits, and a rerun buys it again." in res["stopped"]


def test_sweeps_answered_404_never_finish_a_sport_with_no_games(cfg, tmp_path, monkeypatch, capsys):
    """Review round 3, minor b: /events sweeps answered 404 are cached, so they counted as a finished sweep: the probe
    saved an empty schedule over one with games and printed `P0 done`. Now a sport whose sweeps list no games while
    some were answered 404, or while the saved schedule has games, is incomplete: its schedule is kept, the probe
    stops, and it says to tell the hub (a rerun won't ask cached 404s again)."""
    monkeypatch.setenv("ODDS_API_KEY", KEY)
    nfl = ["americanfootball_nfl"]
    two = [{**game(cfg, g, k), "home_team": "H", "away_team": "A", "first_seen": None}
           for g, k in (("a", "2024-09-06T00:20:00Z"), ("b", "2024-09-08T17:00:00Z"))]

    class Sweeps(FakeOddsApi):
        def __init__(self, status):
            super().__init__()
            self.status_ = status

        def get(self, url, params=None, timeout=None):
            if url.endswith("/events"):
                self.calls.append((url, dict(params)))
                return self._r(self.status_, {"timestamp": params["date"], "data": []}, 0)
            return super().get(url, params, timeout)

    n = len(bulk.sweep_calls(cfg, nfl[0], NOW))
    for status, why in ((404, f"all {n} sweeps came back but listed no games, and {n} of them were HTTP 404"),
                        (200, "the sweeps listed no games, so the saved schedule of 2 game(s) was kept")):
        bulk.save_schedule(tmp_path / str(status), nfl[0], two)
        path = bulk.schedule_path(tmp_path / str(status), nfl[0])
        before = path.read_bytes()
        out = bulk.stage_probe(cfg, RawCache(tmp_path / str(status)), args(sports=nfl), now=NOW, session=Sweeps(status))
        printed = capsys.readouterr().out
        assert out["stopped"] and out["incomplete"] == nfl and path.read_bytes() == before, status
        assert why in printed and "P0 stopped" in printed and "Tell the hub before rerunning" in printed, status
    api = Sweeps(404)
    bulk.stage_probe(cfg, RawCache(tmp_path / "404"), args(sports=nfl), now=NOW, session=api)
    assert not any(u.endswith("/events") for u, _ in api.calls)    # the 404s are cached: a rerun asks nothing
    out = bulk.stage_probe(cfg, RawCache(tmp_path / "new"), args(sports=nfl), now=NOW, session=Sweeps(200))
    assert out["stopped"] is None and out["games"][nfl[0]] == {}   # nothing saved before, no 404: an empty schedule


# ---------------------------------------------------------------- review round 4 (Sep 29): minors
def test_a_full_disk_at_the_manifest_says_whether_the_answer_was_saved(cfg, tmp_path, monkeypatch):
    """A full disk when an answer's manifest row is written: the STOPPED line said "the response is cached" even for
    an error answer, which is never cached (a 500 about to be retried, or the last one). Now it says so only when the
    answer was saved, and otherwise that it was not saved and a rerun asks for it again."""
    import errno

    from markets import http
    monkeypatch.setattr(http.time, "sleep", lambda s: None)
    log_row = bulk.BulkClient._log

    def full(self, row):
        if row.get("pull") != "account":
            raise OSError(errno.ENOSPC, "No space left on device")
        log_row(self, row)

    monkeypatch.setattr(bulk.BulkClient, "_log", full)
    (call,) = _f1_calls(cfg)[-1:]
    cases = [([(500, "0", "1000"), (200, "30", "970")], 1, False),     # a 500 about to be retried
             ([(500, "0", "1000")], 0, False),                          # the last answer, a 500
             ([(200, "30", "970")], 0, True)]                           # a 200, saved
    for i, (answers, retries, saved) in enumerate(cases):
        api = Scripted(answers)
        c = bulk.BulkClient(RawCache(tmp_path / str(i)), max_credits=1_000, session=api, api_key=KEY, rate_per_sec=1e6,
                            max_retries=retries)
        c.account()
        res = bulk.run_calls(c, [call])
        assert api.paid == 1 and c.is_cached(call) == saved, i
        assert "manifest row could not be written (No space left on device): is the disk full?" in res["stopped"], i
        assert ("the response is cached" in res["stopped"]) == saved, (i, res["stopped"])
        assert ("the answer was not saved (a rerun asks for it again)" in res["stopped"]) == (not saved), i


def test_ctrl_c_while_the_next_request_waits_counts_nothing_more(cfg, tmp_path, monkeypatch):
    """Ctrl-C while no request was out (the backoff before a retry, whose answer was already counted, or the rate
    limiter's wait before a try) counted the call's upper bound and said it may have been billed. Now nothing more is
    counted and the line says no request was out. Ctrl-C while a request is out still counts its upper bound."""
    from markets import http
    (call,) = _f1_calls(cfg)[-1:]                                 # upper bound 30

    def interrupt(*a, **k):
        raise KeyboardInterrupt

    def run(api, where, retries=3):
        c = bulk.BulkClient(RawCache(tmp_path / where), max_credits=1_000, session=api, api_key=KEY, rate_per_sec=1e6,
                            max_retries=retries)
        c.account()
        if where == "limiter":
            monkeypatch.setattr(c.limiter, "wait", interrupt)
        return c, bulk.run_calls(c, [call])

    monkeypatch.setattr(http.time, "sleep", interrupt)              # Ctrl-C in the backoff after a counted 500
    api = Scripted([(500, "20", "980"), (200, "30", "950")])
    c, res = run(api, "backoff")
    assert res["interrupted"] and api.paid == 1 and c.counted == 20 and c.unanswered == 0
    assert "No request was out (the next one was waiting for the rate limit or for a retry)" in res["stopped"]
    monkeypatch.undo()
    api = Scripted([(200, "30", "970")])                            # Ctrl-C in the rate limiter's wait
    c, res = run(api, "limiter")
    assert res["interrupted"] and api.paid == 0 and c.counted == 0 and "No request was out" in res["stopped"]

    class Hangs(Scripted):                                          # Ctrl-C while the request is out
        def get(self, url, params=None, timeout=None):
            if url.endswith("/sports"):
                return super().get(url, params, timeout)
            self.paid += 1
            raise KeyboardInterrupt
    api = Hangs([])
    c, res = run(api, "out")
    assert api.paid == 1 and c.counted == c.unanswered == 30
    assert "may have been billed, so it is counted at its upper bound, 30 credits" in res["stopped"]


def test_out_of_date_readings_are_ignored_and_each_real_rise_is_warned(cfg, tmp_path, caplog):
    """Rule 6 (amended Sep 29): a reading higher than the one before it by the margin or less is out of date. It is
    ignored (the start and the lowest don't move) and tallied, and the tally is logged once when the pull ends. A rise
    by more than the margin is credits added or the month renewed: each gets its own warning, and the run starts again
    from it. (Round 5 restarted the run from every rise and warned only about the first.)"""
    caplog.set_level(logging.INFO)
    calls = _f1_calls(cfg)

    def run(where, shown):
        c = bulk.BulkClient(RawCache(tmp_path / where), max_credits=1_000, session=Scripted(
            [(200, "30", str(b)) for b in shown]), api_key=KEY, rate_per_sec=1e6, max_retries=0, alarm_margin=300)
        c.account()
        return c, bulk.run_calls(c, calls[:len(shown)], "F1")

    c, res = run("stale", (970, 1_000, 940, 970, 910, 940, 880, 850))      # late by 0 or 1 answers: three rises of 30
    assert res["stopped"] is None and c.counted == 240 and c.stale == 3
    assert (c.start, c.lowest, c.unexplained) == (1_000, 850, -90) and "rose from" not in caplog.text
    assert caplog.text.count("F1: 3 readings of the balance came back higher than the one before, by no more than "
                             "the margin of 300: out of date, so ignored") == 1
    c._saw_balance(c.last_seen + 300)                               # a rise of exactly the margin: out of date
    assert c.stale == 4 and c.start == 1_000
    caplog.clear()
    c, res = run("added", (970, 1_000_970, 1_000_940, 2_000_910, 2_000_880))   # a million added, twice
    assert res["stopped"] is None and c.stale == 0 and c.unexplained == 0 and c.start == 2_000_910 + 120
    assert caplog.text.count("during the run, more than the margin of 300: credits were added or the month "
                             "renewed; the run starts again from there") == 2
    assert "rose from 970 to 1,000,970" in caplog.text and "rose from 1,000,940 to 2,000,910" in caplog.text


# ---------------------------------------------------------------- the hub's amended rule (Sep 29, round 6)
def test_a_client_that_stopped_refuses_every_later_attempt(cfg, tmp_path):
    """The hub's Q3: after any stop (here a call billed above its upper bound, then Ctrl-C), the client refuses every
    later attempt with the same stop and sends nothing; a call already cached is still read. The one exception is the
    probe skipping a sport after five refusals in a row, which is not a stop of the run (see
    test_a_sport_whose_sweeps_keep_getting_refused_is_skipped_and_the_others_go_on: the probes still run after it)."""
    calls = _nfl_calls(cfg)
    api = FakeOddsApi(overbill=50)
    c = client(tmp_path / "over", api)
    c.account()
    res = bulk.run_calls(c, calls)
    assert "billed 70 credits" in res["stopped"] and len(api.calls) == 2      # the key check and one paid call
    with pytest.raises(bulk.CircuitBreaker, match="billed 70 credits") as ei:
        c.fetch(calls[1])
    assert ei.value is c.stopped and len(api.calls) == 2 and c.counted == 70
    assert c.fetch(calls[0])["http_status"] == 200                           # cached: read, not asked
    again = bulk.run_calls(c, calls)
    assert again["stopped"] == res["stopped"] and again["fetched"] == 0 and len(api.calls) == 2
    c = client(tmp_path / "ctrl-c", FakeOddsApi())
    c.account()
    c._out, c._sent = calls[0], True
    assert "counted at its upper bound, 60 credits" in c.interrupted()
    with pytest.raises(bulk.Stop, match="interrupted"):
        c.fetch(calls[1])


@pytest.mark.parametrize("where", ["before its count", "between its count and its row", "after its row"])
def test_ctrl_c_inside_the_accounting_of_an_answer_counts_it_once_with_one_manifest_row(cfg, tmp_path, monkeypatch,
                                                                                       where):
    """Review round 5, minor: a Ctrl-C after an answer was counted and before its manifest row was written lost the
    row, and the STOPPED line said no call was out. Now, wherever a Ctrl-C lands while an answer is accounted for,
    the answer is counted once, at what it cost, it has exactly one manifest row, and the line says so."""
    n = [0]
    if where == "before its count":
        account = bulk.BulkClient._account

        def patched(self, *a, **k):
            n[0] += 1
            if n[0] == 3:
                raise KeyboardInterrupt
            return account(self, *a, **k)
        monkeypatch.setattr(bulk.BulkClient, "_account", patched)
    elif where == "between its count and its row":
        saw = bulk.BulkClient._saw_balance

        def patched(self, left):
            saw(self, left)
            n[0] += 1
            if n[0] == 3:
                raise KeyboardInterrupt
        monkeypatch.setattr(bulk.BulkClient, "_saw_balance", patched)
    else:
        log_row = bulk.BulkClient._log

        def patched(self, row):
            log_row(self, row)
            n[0] += row["pull"] != "account"
            if n[0] == 3 and row["pull"] != "account":
                raise KeyboardInterrupt
        monkeypatch.setattr(bulk.BulkClient, "_log", patched)
    api = FakeOddsApi()
    c = client(tmp_path, api)
    c.account()
    res = bulk.run_calls(c, _nfl_calls(cfg))                        # charged 20 each
    paid = [r for r in csv.DictReader((tmp_path / "raw/_manifest/oddsapi_manifest.csv").open()) if r["pull"] != "account"]
    assert res["interrupted"] and c.counted == 60 == 5_000_000 - api.remaining, where
    assert [r["credits_last"] for r in paid] == ["20", "20", "20"], where
    assert "had come back and was saved, so it is counted at what it cost, 20 credits." in res["stopped"], where


def test_every_paid_run_prints_its_alarm_margin_and_alarm_margin_sets_it(cfg, tmp_path, monkeypatch, capsys):
    """Rule 8: the margin is the larger of 5,000 and 10% of --max-credits, unless --alarm-margin sets it (at least 300,
    on probe, week, full and odds-pull). Every paid run prints the margin in force on its first line after the key
    check."""
    from markets import cli
    from markets.oddsapi.ingest import pull_snapshots

    def after_key_check(out):
        lines = out.splitlines()
        return lines[lines.index(next(x for x in lines if x.startswith("key ok:"))) + 1]

    for name, kw, line in (("default", {}, "alarm margin: 10,000 credits (the default: the larger of 5,000 and 10% of "
                                           "--max-credits)"),
                           ("small", {"max_credits": 6_000}, "alarm margin: 5,000 credits (the default"),
                           ("set", {"alarm_margin": 400}, "alarm margin: 400 credits (set by --alarm-margin)")):
        _saved_test_nfl(cfg, tmp_path / name)
        capsys.readouterr()
        assert _main(cfg, tmp_path / name, monkeypatch, FakeOddsApi(), **kw) == 0
        assert after_key_check(capsys.readouterr().out).startswith(line), name
    with pytest.raises(SystemExit, match="--alarm-margin works with probe, week and full, not plan"):
        _main(cfg, tmp_path / "plan", monkeypatch, FakeOddsApi(), stage="plan", alarm_margin=400)
    with pytest.raises(SystemExit) as ei:
        cli.main(["odds5m", "full", "--pull", "F1", "--alarm-margin", "100"])
    assert ei.value.code == 2                                       # argparse: at least 300
    oc, ctx, plan = _oddspull(tmp_path / "odds-pull", FakeOddsApi())
    oc.alarm_margin = 900
    capsys.readouterr()
    assert pull_snapshots(ctx, plan, 1_000, client=oc)["stopped"] is None
    assert after_key_check(capsys.readouterr().out) == "alarm margin: 900 credits (set by --alarm-margin)"


def _logged_run(tmp_path, monkeypatch, api, n=1_000, **kw):
    """n F1 calls (30 each) against `api`, with the cache in memory but a real manifest, for the `headers` stage."""
    from markets import http
    monkeypatch.setattr(bulk, "read_record", lambda p: p[0].mem[p[1]])
    monkeypatch.setattr(bulk, "read_status", lambda p: p[0].mem[p[1]]["http_status"], raising=False)
    monkeypatch.setattr(http.RateLimiter, "wait", lambda self: None)
    c = bulk.BulkClient(MemCache(tmp_path), session=api, api_key=KEY, **{"max_credits": 31_500, "floor": 0, **kw})
    c.account()
    res = bulk.run_calls(c, _f1_5000()[:n], "F1")
    return c, res, list(csv.DictReader(c.manifest.open()))


HEADERS = {"live": "The balance header is live: every charge shows in the answer that made it.",
           "late": "The balance header runs late by up to {} answers.",
           "steps": "The balance header is refreshed in steps, about every {} answers.",
           "fell": ("The balance fell by {:,} credits more than the run counted: something else spent on this key, or "
                    "the API charged more than it reported.")}


@pytest.mark.parametrize("header", ["live", "late by 3", "late by 100", "late by 0-3 at random", "every 50",
                                    "a top-up", "another spender", "overcharging"])
def test_the_headers_stage_reads_how_the_balance_header_behaved(tmp_path, monkeypatch, capsys, header):
    """The free `headers` stage reads the manifest of a pull's latest run, written here by the real client against the
    fake API with each kind of balance header, and says how the header behaved: live; late by a fixed or varying
    number of answers (the longest stretch of charged answers that showed no fall); refreshed in steps; or a fall
    larger than the run counted (another user of the key, or overcharging). A top-up is a rise, listed, and the run is
    measured again from it. The margin it advises is the larger of 5,000 and 2 x the lateness x the cost per call."""
    from markets.oddsapi import headers
    rnd = random.Random(0)
    api = {"live": Ledger, "late by 3": lambda: Ledger(lag=lambda: 3), "late by 100": lambda: Ledger(lag=lambda: 100),
           "late by 0-3 at random": lambda: Ledger(lag=lambda: rnd.randint(0, 3)), "every 50": lambda: Ledger(every=50),
           "a top-up": lambda: Ledger(events={500: 1_000_000}), "another spender": lambda: Ledger(events={500: -1_000}),
           "overcharging": lambda: Ledger(charge=60)}[header]()
    c, res, rows = _logged_run(tmp_path, monkeypatch, api)
    a = headers.analyze(rows, "F1", per_call=30)
    want, lateness = {"live": (HEADERS["live"], 0), "late by 3": (HEADERS["late"].format(3), 3),
                      "late by 100": (HEADERS["late"].format(100), 100),
                      "late by 0-3 at random": (HEADERS["late"].format(3), 3),
                      "every 50": (HEADERS["steps"].format(50), 49), "a top-up": (HEADERS["live"], 0),
                      "another spender": (HEADERS["fell"].format(1_000), 0),
                      "overcharging": (HEADERS["fell"].format(c.unexplained), 0)}[header]
    assert (a["verdict"], a["lateness"]) == (want, lateness), a
    assert a["advised"] == max(5_000, 2 * lateness * 30) and a["counted"] == c.counted and a["requests"] == len(rows) - 1
    if header == "overcharging":                                    # the run's own alarm stopped it first
        assert "the account has fallen by" in res["stopped"] and a["unexplained"] == c.unexplained > c.margin
    else:
        assert res["stopped"] is None and a["counted"] == api.billed == 30_000
    assert (a["rises"] == {999_970: 1}) == (header == "a top-up")
    if header == "late by 100":                                     # per call 60: 2 x 100 x 60
        assert headers.analyze(rows, "F1", per_call=60)["advised"] == 12_000


def test_the_headers_stage_through_the_cli_and_with_no_run(cfg, tmp_path, monkeypatch, capsys):
    """`markets odds5m headers` makes no request and needs no --confirm. It reads the latest run of the pull named
    (P0 by default: the rows after its key check), prints its measures, one verdict and the advised margin, and exits
    0; with no run of that pull it says so; it exits 1 only when the manifest can't be read."""
    none = "There is no run of that pull in the manifest."
    raw = tmp_path / "raw"
    assert _main(cfg, raw, monkeypatch, FakeOddsApi(), stage="headers", pull="all", confirm=False) == 0   # no manifest
    assert capsys.readouterr().out.strip() == none
    assert _main(cfg, raw, monkeypatch, FakeOddsApi(), stage="probe", sports="americanfootball_nfl") == 0
    _saved_test_nfl(cfg, raw)
    assert _main(cfg, raw, monkeypatch, FakeOddsApi(), stage="week", pull="F1") == 0
    capsys.readouterr()
    api = FakeOddsApi()
    assert _main(cfg, raw, monkeypatch, api, stage="headers", pull="all", per_call=60, confirm=False) == 0
    assert api.calls == []
    out = capsys.readouterr().out
    assert "headers, P0: the run after the key check at" in out and "(pulls P0)" in out
    assert "The balance header is live: every charge shows in the answer that made it." in out
    assert "Smallest --alarm-margin advised for a pull whose calls cost up to 60 credits: 5,000" in out
    assert _main(cfg, raw, monkeypatch, api, stage="headers", pull="F1") == 0 and "(pulls F1)" in capsys.readouterr().out
    assert _main(cfg, raw, monkeypatch, api, stage="headers", pull="F4") == 0
    assert capsys.readouterr().out.strip() == none
    (tmp_path / "bad" / "_manifest" / "oddsapi_manifest.csv").mkdir(parents=True)
    assert _main(cfg, tmp_path / "bad", monkeypatch, api, stage="headers") == 1
    assert "headers: the manifest could not be read" in capsys.readouterr().out


def test_a_false_alarm_from_a_cached_balance_is_cleared_the_runbook_way(tmp_path, monkeypatch):
    """Review round 4's blocker, under the amended rule: a balance header cached for 400 answers makes the key check of
    a run started right after another read a balance that hides the other run's last answers (here 200 answers of 30),
    so the account seems to fall further than the new run counted, and the alarm stops that honest run: a header later
    than the margin (5,000). The way out is cheap, as the runbook says: `headers` on the stopped run also takes the
    lateness of the run before it, says the header is refreshed in steps rather than that the balance fell by more
    than counted, and the margin it advises lets the rerun finish."""
    from markets.oddsapi import headers
    api = Ledger(every=400)
    c1, res1, _ = _logged_run(tmp_path, monkeypatch, api, n=1_000)
    assert res1["stopped"] is None and c1.margin == 5_000

    def run(calls, **kw):
        c = bulk.BulkClient(MemCache(tmp_path), session=api, api_key=KEY, max_credits=31_500, floor=0, **kw)
        c.account()
        return c, bulk.run_calls(c, calls, "F1")

    c2, res2 = run(_f1_5000()[1_000:2_000])
    assert "the account has fallen by 6,000 credits more than this run counted" in res2["stopped"]
    assert api.billed == c1.counted + c2.counted                      # honest: nothing charged that wasn't counted
    a = headers.analyze(list(csv.DictReader(c2.manifest.open())), "F1", 30)
    assert (a["kind"], a["lateness_this_run"], a["lateness"], a["advised"]) == ("steps", 199, 399, 23_940), a
    c3, res3 = run(_f1_5000()[1_200:2_000], alarm_margin=a["advised"])
    assert res3["stopped"] is None and c3.margin == 23_940


def test_ctrl_c_while_a_retried_answer_is_accounted_counts_it_at_what_it_cost_with_its_row(cfg, tmp_path, monkeypatch):
    """The same for an HTTP 500 about to be retried (rule 3a): a Ctrl-C while its answer is being accounted counted the
    call's upper bound, said it "may have been billed", and left no manifest row. Now the answer is counted at what it
    reported, with its row, and the line says it came back (not saved, so a rerun asks again); no retry is sent."""
    from markets import http
    monkeypatch.setattr(http.time, "sleep", lambda s: None)
    envelope, n = bulk._envelope, [0]

    def patched(body):
        n[0] += 1
        if n[0] == 1:
            raise KeyboardInterrupt
        return envelope(body)
    monkeypatch.setattr(bulk, "_envelope", patched)
    (call,) = _f1_calls(cfg)[-1:]                                 # upper bound 30
    api = Scripted([(500, "20", "980"), (200, "30", "950")])
    c = bulk.BulkClient(RawCache(tmp_path), max_credits=1_000, session=api, api_key=KEY, rate_per_sec=1e6, max_retries=1)
    c.account()
    res = bulk.run_calls(c, [call])
    rows = [r for r in csv.DictReader(c.manifest.open()) if r["pull"] != "account"]
    assert res["interrupted"] and api.paid == 1 and c.counted == 20 and c.unanswered == 0
    assert [(r["http_status"], r["credits_last"]) for r in rows] == [("500", "20")]
    assert "had come back, so it is counted at what it cost, 20 credits, and a rerun buys it again." in res["stopped"]


# ---------------------------------------------------------------- review of cc14201 (Sep 30)
def test_any_other_error_the_session_raises_counts_the_attempt_and_stops_the_client(cfg, tmp_path, caplog):
    """Review of cc14201, finding A2: a session that raised something other than a network error `requests` knows
    (here a RuntimeError) ended the run as "unexpected error", but the attempt counted nothing and the client took
    the next call. Now the attempt counts its upper bound to the end of the run (rule 2), the run stops, and the
    client refuses every later attempt with that stop. At the key check nothing is counted, and it stops the same."""
    class Raises(FakeOddsApi):
        def get(self, url, params=None, timeout=None):
            if not url.endswith("/sports") and len(self.calls) == 2:            # the second paid call
                self.calls.append((url, dict(params)))
                raise RuntimeError(f"urllib3 surprise {params['apiKey']}")
            return super().get(url, params, timeout)

    calls = _nfl_calls(cfg)                                                     # upper bound 60, billed 20
    api = Raises()
    c = client(tmp_path, api)
    c.account()
    res = bulk.run_calls(c, calls)
    assert res["stopped"].startswith("unexpected error, probably a bug; tell the hub before rerunning (RuntimeError: "
                                     "urllib3 surprise REDACTED)") and not res["rerun"]
    assert "its upper bound, 60 credits, is counted to the end of the run" in res["stopped"]
    assert c.counted == 20 + 60 and c.unanswered == 60 and res["fetched"] == 1
    with pytest.raises(bulk.Stop) as ei:
        c.fetch(calls[2])
    assert ei.value is c.stopped and len(api.calls) == 3 and c.counted == 80
    assert "SECRETKEY" not in caplog.text

    class AtTheKeyCheck(FakeOddsApi):
        def get(self, url, params=None, timeout=None):
            raise RuntimeError("no")
    k = client(tmp_path / "k", AtTheKeyCheck())
    with pytest.raises(bulk.CircuitBreaker, match=r"unexpected error, probably a bug.*RuntimeError: no"):
        k.account()
    assert k.counted == 0 and k.stopped is not None


class Garbled(FakeOddsApi):
    """Answers the second paid call with an HTTP 200 whose body is `body`, reported at the usual 20 credits."""

    def __init__(self, body, **kw):
        super().__init__(**kw)
        self.body = body

    def get(self, url, params=None, timeout=None):
        r = super().get(url, params, timeout)
        if len(self.calls) == 3:                                                # the key check, then two paid calls
            r.text = self.body
        return r


@pytest.mark.parametrize("body", [{"timestamp": "2024-09-01T00:15:00Z", "data": 5}, {"data": "abc"},
                                  {"data": {"id": "ev1", "bookmakers": 5}}])
def test_a_200_it_cannot_interpret_counts_its_upper_bound_gets_its_row_and_stops(cfg, tmp_path, capsys, body):
    """Review of cc14201, finding A2: a 200 whose JSON `data` is a number was cached and then crashed the accounting
    (`_envelope`), so it counted nothing, a rerun found it cached and never counted it, and the client took the next
    call. Now a 200 whose body can't be interpreted counts the larger of what it reported and its upper bound (its
    documented cost can't be worked out), gets its manifest row, isn't cached, and stops the run with a plain STOPPED
    line; the client refuses every later attempt."""
    calls = _nfl_calls(cfg)                                                     # upper bound 60, billed 20
    api = Garbled(json.dumps(body))
    c = client(tmp_path, api)
    c.account()
    res = bulk.run_calls(c, calls)
    assert res["stopped"].startswith(f"{calls[1].path} at {bulk.iso(calls[1].at)}: the API answered HTTP 200 with "
                                     "JSON it cannot read") and res["rerun"]
    assert ("It counted 60 credits, the larger of what it reported and its upper bound (x-requests-last '20')."
            in res["stopped"])
    assert c.counted == 20 + 60 and res["fetched"] == 2
    rows = [r for r in csv.DictReader(c.manifest.open()) if r["pull"] != "account"]
    assert [(r["http_status"], r["credits_last"]) for r in rows] == [("200", "20"), ("200", "20")]
    assert c.is_cached(calls[0]) and not c.is_cached(calls[1])                  # a rerun asks again
    assert "STOPPED: " in capsys.readouterr().out
    with pytest.raises(bulk.Stop) as ei:
        c.fetch(calls[2])
    assert ei.value is c.stopped and len(api.calls) == 3


@pytest.mark.parametrize("where", ["saving the answer", "reading the cache"])
def test_any_other_error_in_a_fetch_counts_what_came_back_and_stops_the_client(cfg, tmp_path, monkeypatch, where):
    """Review of cc14201, finding A2: every stop latches the client, not only a Stop or Ctrl-C. An error that isn't
    one (a bug while the answer is saved, a cache that can't be read) stops the run with the STOPPED line it gives,
    after an answer that had come back is counted, at the larger of what it reported and its upper bound; and the
    client refuses every later attempt with that stop, even once the cause is gone."""
    from markets import cache as cache_mod
    calls = _nfl_calls(cfg)
    api = FakeOddsApi()
    c = client(tmp_path, api)
    c.account()
    c.fetch(calls[0])                                                           # 20 counted

    def fail(*a, **k):
        raise ValueError("a bug") if where == "saving the answer" else PermissionError(13, "Permission denied")
    if where == "saving the answer":
        monkeypatch.setattr(cache_mod, "write_record", fail)
    else:
        monkeypatch.setattr(c.cache, "lookup", fail)
    with pytest.raises(bulk.Stop) as ei:
        c.fetch(calls[1])
    assert ei.value is c.stopped
    if where == "saving the answer":
        assert str(c.stopped).startswith("unexpected error, probably a bug; tell the hub before rerunning (ValueError")
        assert c.counted == 20 + 60 and c.fetched == 2 and len(api.calls) == 3
    else:
        assert str(c.stopped).startswith("a file could not be read or written (Permission denied)")
        assert c.counted == 20 and len(api.calls) == 2
    monkeypatch.undo()
    with pytest.raises(bulk.Stop) as again:
        c.fetch(calls[2])
    assert again.value is c.stopped and len(api.calls) == (3 if where == "saving the answer" else 2)


@pytest.mark.parametrize("error", [TimeoutError("socket timed out"), ConnectionResetError(104, "Connection reset"),
                                   "a URL with the key"])
def test_a_raw_socket_error_from_the_session_is_an_attempt_with_no_answer(cfg, tmp_path, error):
    """Review of cc14201, finding A3: a socket error the session raised without `requests` wrapping it (an OSError,
    such as a raw TimeoutError) was reported as "the cache could not be read ... Nothing was fetched" and counted
    nothing. It is a transport error: the attempt counts its upper bound to the end of the run (rule 2), the line
    says there was no answer, and a rerun asks again. (A full disk keeps its own lines: see
    test_a_full_disk_or_a_body_that_is_not_json_stops_with_the_summary.) Review of the fix, finding 3: "not
    retried" comes first, so an error text that ends in a URL with the key loses only the key."""
    class Raw(FakeOddsApi):
        def get(self, url, params=None, timeout=None):
            if not url.endswith("/sports") and len(self.calls) == 2:            # the second paid call
                self.calls.append((url, dict(params)))
                raise error if isinstance(error, OSError) else TimeoutError(f"timed out: {url}?apiKey={params['apiKey']}")
            return super().get(url, params, timeout)

    calls = _nfl_calls(cfg)                                                     # upper bound 60, billed 20
    api = Raw()
    c = client(tmp_path, api)
    c.account()
    res = bulk.run_calls(c, calls)
    assert res["stopped"].startswith("no answer from the Odds API (not retried; TimeoutError: " if isinstance(
        error, str) else f"no answer from the Odds API (not retried; {type(error).__name__}: ") and res["rerun"]
    assert "the cache could not be read" not in res["stopped"] and "SECRETKEY" not in res["stopped"]
    if isinstance(error, str):
        assert f"{calls[1].path}?apiKey=REDACTED). Nothing was cached" in res["stopped"]
    assert "its upper bound, 60 credits, is counted to the end of the run" in res["stopped"]
    assert c.counted == 20 + 60 and c.unanswered == 60 and res["fetched"] == 1 and not c.is_cached(calls[1])
    with pytest.raises(bulk.Stop) as ei:
        c.fetch(calls[2])
    assert ei.value is c.stopped and len(api.calls) == 3


@pytest.mark.parametrize("stop", ["the alarm", "billed above its upper bound", "a session error"])
def test_the_key_check_of_a_client_that_stopped_is_refused_with_the_same_stop(cfg, tmp_path, stop):
    """Review of cc14201, finding A4 (the hub's Q3 read literally): account() on a stopped client still sent the free
    key check and reset the start and the lowest balance, so the client no longer described the run that stopped.
    Now it is refused with the same stop, sends nothing, and changes nothing."""
    class Raises(Overcharges):
        def get(self, url, params=None, timeout=None):
            if stop == "a session error" and not url.endswith("/sports"):
                raise RuntimeError("boom")
            return super().get(url, params, timeout)

    api = Raises(others=400 if stop == "the alarm" else 0, overbill=50 if stop.startswith("billed") else 0)
    c = client(tmp_path, api, alarm_margin=300)
    c.account()
    res = bulk.run_calls(c, _nfl_calls(cfg))
    assert {"the alarm": "the account has fallen by", "billed above its upper bound": "billed 70 credits",
            "a session error": "unexpected error"}[stop] in res["stopped"] and c.stopped is not None
    before, sent = (c.start, c.lowest, c.counted, c.unexplained), len(api.calls)
    with pytest.raises(bulk.Stop) as ei:
        c.account()
    assert ei.value is c.stopped and len(api.calls) == sent and (c.start, c.lowest, c.counted, c.unexplained) == before


def test_a_cached_404_asked_again_and_answered_with_an_error_shows_on_the_summary_line(cfg, tmp_path, monkeypatch,
                                                                                       capsys):
    """Review of cc14201, finding A5: with --retry-404, a cached 404 asked again and answered 500 kept its 404 (as it
    should) but was left off the pull's line, which said only `cached 404s 2`; only a WARNING showed the 500. The
    line now counts it like any error answer; a 404 asked again that is still a 404 is not an error."""
    from markets import http
    monkeypatch.setattr(http.time, "sleep", lambda s: None)
    calls, raw = _nfl_calls(cfg, 2), tmp_path / "raw"

    def run(api, **kw):
        c = bulk.BulkClient(RawCache(raw), max_credits=10_000, session=api, api_key=KEY, rate_per_sec=1e6,
                            max_retries=0)
        c.account()
        return bulk.run_calls(c, calls, "F3", **kw), capsys.readouterr().out

    run(Gone({"ev0"}))
    res, out = run(Gone({"ev0"}, fail=True), retry_404=True)
    assert res["errors"] == 2 and res["cached_404"] == 2
    assert "done: 2 fetched (2 answered with an error and not saved; a rerun asks again), credits 0" in out
    res, out = run(Gone({"ev0"}), retry_404=True)
    assert res["errors"] == 0 and "answered with an error" not in out and res["cached_404"] == 2


def test_the_headers_stage_and_the_key_check_print_their_counts_plainly(cfg, tmp_path, monkeypatch, capsys):
    """Review of cc14201, C m3 (wording): `headers` printed "the longest stretch in a row: 1 answers", and `key ok:`
    printed the credits used as the raw header (12421) next to formatted figures. One answer is singular now, and
    the credits used are formatted like the other numbers (unknown when the header can't be read)."""
    from markets.oddsapi import headers
    manifest = tmp_path / "m.csv"
    with manifest.open("w", newline="") as f:
        w = csv.DictWriter(f, bulk.MANIFEST_FIELDS)
        w.writeheader()
        w.writerow({"pull": "account", "remaining": 1_000})
        for left in (970, 970, 910):                                            # the second answer shows no fall
            w.writerow({"pull": "F1", "expected_credits": 30, "credits_last": 30, "remaining": left})
    assert headers.stage_headers(manifest, "F1") == 0
    out = capsys.readouterr().out
    assert "requests: 3 answers;" in out and "the longest stretch in a row: 1 answer\n" in out
    assert "the header's lateness: 1 answer (" in out and "The balance header runs late by up to 1 answer." in out
    assert "(the larger of 5,000 and 2 x 1 answer x 30)" in out
    monkeypatch.setenv("ODDS_API_KEY", KEY)
    api = FakeOddsApi(remaining=4_987_579)                                      # 12,421 used
    bulk.stage_balance({}, RawCache(tmp_path), args(), session=api)
    bulk._client(RawCache(tmp_path), args(), session=api)
    out = capsys.readouterr().out
    assert out.count("key ok: HTTP 200, 4,987,579 credits remaining, 12,421 used; floor 0") == 2


@pytest.mark.parametrize("where", ["its row can't be written", "a bug before its row"])
def test_an_answer_counted_before_a_bug_keeps_its_count_and_its_row_or_the_line_says_what_it_held(cfg, tmp_path,
                                                                                                   monkeypatch, where):
    """Review of the fix (finding 1): an answer already counted when an error other than a Stop came (a `timestamp`
    that is a lone surrogate, which the manifest file can't hold; a bug in the accounting after the count) kept its
    count but got no manifest row, and the STOPPED line didn't say so. Now its row is written then if it can be, and
    if it can't, the line says the row is missing and what it would have held, as after a Ctrl-C."""
    class Surrogate(FakeOddsApi):
        def get(self, url, params=None, timeout=None):
            r = super().get(url, params, timeout)
            if len(self.calls) == 3 and where == "its row can't be written":     # the second paid answer
                r.text = json.dumps({**json.loads(r.text), "timestamp": "\ud800"})
            return r

    if where == "a bug before its row":
        saw, n = bulk.BulkClient._saw_balance, [0]

        def buggy(self, left):
            saw(self, left)
            n[0] += 1
            if n[0] == 2:                                                       # the second answer, once counted
                raise ValueError("a bug")
        monkeypatch.setattr(bulk.BulkClient, "_saw_balance", buggy)
    calls = _nfl_calls(cfg)                                                     # billed 20 each
    c = client(tmp_path, Surrogate())
    c.account()
    res = bulk.run_calls(c, calls)
    rows = [r for r in csv.DictReader(c.manifest.open()) if r["pull"] != "account"]
    assert res["stopped"].startswith("unexpected error, probably a bug") and c.counted == 40 and c.is_cached(calls[1])
    if where == "a bug before its row":
        assert len(rows) == 2 and "manifest row" not in res["stopped"]
    else:
        assert len(rows) == 1 and ("The answer that had come back was counted at what it cost, 20 credits. Its "
                                   "manifest row could not be written (" in res["stopped"])
        assert res["stopped"].endswith(f"; it would have held HTTP 200, credits_last 20, cache key {calls[1].key}.")
