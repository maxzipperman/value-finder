"""The 5M-month bulk puller (markets.oddsapi.bulk), against mocked Odds API responses. No network."""
import csv
import json
import logging
from argparse import Namespace
from datetime import date, datetime, timezone

import pytest

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
    assert res["fetched"] == 0 and res["spent"] == 0 and "no answer from the Odds API" in res["stopped"]
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
    assert res["remaining"] is None
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
    day-one command. With --seasons the dry run goes ahead as before; `week`, `plan` and `check` are unchanged."""
    real = bulk.load_config()
    assert real["pulls"]["F3"]["require_seasons"] == {"day_one": "2025", "gated": "2023,2024,2026"}
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
            assert "day_one: uv run markets odds5m full --pull F3 --seasons 2025 --confirm" in msg
    assert api.calls == []
    assert bulk.stage_pull(real, RawCache(tmp_path), args(pull="F3", seasons=["2025"], confirm=False), week=False,
                           now=now) == []
    assert "F3  2 calls, 2 to fetch, at most 120 credits" in capsys.readouterr().out    # one 2025 game, T-24h + close
    assert bulk.stage_pull(real, RawCache(tmp_path), args(pull="F3", confirm=False), week=True, now=now) == []


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

    put("nba", "k1", {"timestamp": "2026-06-09T23:00:00Z", "data": [ev("open", "2026-06-10T00:30:00Z"),       # 2025-26
                                                                     ev("sealed", "2026-10-21T23:30:00Z")]})   # 2026-27
    con, teams = duckdb.connect(), load_teams("nba")
    rows, unknown, left_out = run.sharp_odds_rows(con, "nba", teams)
    assert {r["odds_event_id"] for r in rows} == {"open"} and dict(left_out) == {"2026-27": 2} and not unknown
    rows, _, left_out = run.sharp_odds_rows(con, "nba", teams, include_sealed=True)
    assert {r["odds_event_id"] for r in rows} == {"open", "sealed"} and not left_out
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
