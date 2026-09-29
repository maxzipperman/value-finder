"""Venue tables, venue resolution, heat index, the Open-Meteo plan and the weather join. No network."""
import csv
import json
from datetime import date, datetime, timezone

import pytest

from markets.cache import Fetched, RawCache
from markets.oddsapi import bulk
from markets.weather import gamevenues, join, openmeteo as om, venues as V
from markets.weather.heat import heat_index_f

UTC = timezone.utc


def t(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def test_tables_are_consistent():
    assert V.check_tables() == []
    parks = [v for v in V.venues().values() if v.venue_id in {r["venue_id"] for r in V.homes() if r["sport_key"] == V.MLB}]
    assert len({r["team"] for r in V.homes() if r["sport_key"] == V.MLB}) == 30 and len(parks) >= 30
    assert V.venues()["coors_field"].roof == "open" and V.venues()["tropicana_field"].roof == "dome"
    assert V.venues()["al_bayt_stadium"].roof == "cooled"


def test_fixtures_carry_no_scores():
    with V.csv_path("tournament_fixtures.csv").open() as f:
        header = f.readline()
    assert "score" not in header and "goal" not in header


def test_heat_index_matches_the_nws_table():
    assert round(heat_index_f(90, 50)) == 95          # NWS chart: 90 F at 50% -> 95
    assert round(heat_index_f(96, 60)) == 116         # NWS chart: 96 F at 60% -> 116
    assert round(heat_index_f(86, 90)) == 105         # NWS chart: 86 F at 90% -> 105 (humid adjustment)
    assert abs(heat_index_f(100, 40) - 109) <= 1      # NWS chart: 100 F at 40% -> 109
    assert heat_index_f(70, 50) < 72 and heat_index_f(None, 50) is None


def test_names_normalize_without_merging_clubs():
    assert V.norm("CF Montréal") == V.norm("CF Montreal")
    assert V.norm("Atlético-MG") != V.norm("Atletico-GO")
    assert V.canonical(V.MLB, "Athletics") == V.canonical(V.MLB, "Oakland Athletics")


@pytest.mark.parametrize("sport,team,day,want", [
    ("soccer_usa_mls", "Seattle Sounders FC", "2020-07-20", "espn_wide_world_of_sports_complex"),   # the bubble
    ("soccer_usa_mls", "Toronto FC", "2020-10-01", "pratt_whitney_stadium"),
    ("soccer_usa_mls", "Toronto FC", "2021-08-01", "bmo_field"),
    ("soccer_usa_mls", "CF Montreal", "2021-05-01", "chase_stadium"),
    ("soccer_brazil_campeonato", "Gremio", "2024-06-01", "couto_pereira"),
    ("soccer_brazil_campeonato", "Atletico Mineiro", "2024-06-01", "arena_mrv"),
    ("baseball_mlb", "Athletics", "2025-06-01", "sutter_health_park"),
    ("baseball_mlb", "Tampa Bay Rays", "2025-06-01", "george_m_steinbrenner_field"),
    ("baseball_mlb", "Toronto Blue Jays", "2021-05-01", "td_ballpark")])
def test_home_venue_by_date(sport, team, day, want):
    assert V.home_venue(sport, team, date.fromisoformat(day))[0] == want


def test_leagues_cup_games_go_to_the_mls_host():
    assert V.home_venue("soccer_concacaf_leagues_cup", "Monterrey", date(2025, 8, 1), "Austin FC") == ("q2_stadium",
                                                                                                    "MLS host")
    assert V.home_venue("soccer_concacaf_leagues_cup", "Monterrey", date(2025, 8, 1), "Pachuca")[0] is None


def test_unknown_teams_are_reported_not_guessed():
    assert V.home_venue("soccer_usa_mls", "Nowhere United", date(2024, 5, 1)) == (None, "unknown home team")
    assert V.home_venue("soccer_usa_mls", "San Diego FC", date(2024, 5, 1)) == (None, "no venue on that date")


def test_tournament_fixture_lookup():
    assert V.fixture_venue("soccer_fifa_world_cup", "Ecuador", "Qatar", t("2022-11-20T16:00:00Z")) == "al_bayt_stadium"
    assert V.fixture_venue("soccer_fifa_world_cup", "Ecuador", "Qatar", t("2022-11-25T16:00:00Z")) is None


def test_open_meteo_plan_is_monthly_and_stable():
    vs = V.venues()
    reqs = om.plan_requests({("coors_field", date(2023, 7, 4)), ("coors_field", date(2023, 7, 20)),
                             ("coors_field", date(2024, 8, 2))}, vs, today=date(2026, 9, 29))
    assert [(r.kind, r.start, r.end) for r in reqs] == [
        ("archive", date(2023, 7, 1), date(2023, 7, 31)),
        ("archive", date(2024, 8, 1), date(2024, 8, 31)), ("prev", date(2024, 8, 1), date(2024, 8, 31))]
    again = om.plan_requests({("coors_field", date(2023, 7, 10))}, vs, today=date(2026, 9, 29))
    assert again[0].key == reqs[0].key                       # adding games never changes the cache key
    recent = om.plan_requests({("coors_field", date(2026, 9, 27))}, vs, today=date(2026, 9, 29))
    assert recent == []                                      # the archive lags; left for a later run


def test_recent_months_wait_until_whole_so_the_join_finds_them():
    """#33 item 1: a month is planned only once it ended 5+ days ago, and always whole, so the key
    `plan` fetched under is the key `kickoff_weather` reads, whatever day each ran."""
    vs = V.venues()
    day = {("coors_field", date(2026, 8, 20))}
    assert om.plan_requests(day, vs, today=date(2026, 8, 30)) == []           # the month isn't over
    assert om.plan_requests(day, vs, today=date(2026, 9, 3)) == []            # over, but only 3 days ago
    reqs = om.plan_requests(day, vs, today=date(2026, 9, 5))
    assert [(r.kind, r.start, r.end) for r in reqs] == [("archive", date(2026, 8, 1), date(2026, 8, 31)),
                                                        ("prev", date(2026, 8, 1), date(2026, 8, 31))]
    later = om.plan_requests(day, vs, today=date(2027, 1, 1))
    assert [r.key for r in later] == [r.key for r in reqs]
    v = vs["coors_field"]
    assert [r.key for r in om.month_requests("coors_field", v, 2026, 8)] == [r.key for r in reqs]


def hourly_body(start, hours, temp, rh, prev=False):
    sfx = "_previous_day1" if prev else ""
    times = [(start.replace(tzinfo=None) + (i * (t("2020-01-01T01:00:00Z") - t("2020-01-01T00:00:00Z"))))
             .strftime("%Y-%m-%dT%H:00") for i in range(hours)]
    return {"hourly": {"time": times, f"temperature_2m{sfx}": [temp] * hours,
                       f"relative_humidity_2m{sfx}": [rh] * hours, f"wind_speed_10m{sfx}": [5.0] * hours,
                       f"wind_direction_10m{sfx}": [180] * hours, f"precipitation{sfx}": [0.0] * hours}}


class Session:
    def __init__(self, routes):
        self.routes, self.calls = routes, []

    def get(self, url, params=None, timeout=None):
        self.calls.append(url)
        body = next(b for k, b in self.routes if k in url)
        return type("R", (), {"status_code": 200, "headers": {}, "text": json.dumps(body)})()


def test_join_places_games_and_reads_cached_weather(tmp_path):
    cfg = bulk.load_config()
    cache = RawCache(tmp_path)
    games = {"baseball_mlb": [
        {"id": "m1", "sport": "baseball_mlb", "commence_time": t("2024-07-10T23:10:00Z"), "home_team": "Texas Rangers",
         "away_team": "Houston Astros"},
        {"id": "m2", "sport": "baseball_mlb", "commence_time": t("2024-06-08T17:10:00Z"),
         "home_team": "New York Mets", "away_team": "Philadelphia Phillies"}],     # the London Series
        "soccer_usa_mls": [
        {"id": "s1", "sport": "soccer_usa_mls", "commence_time": t("2024-07-20T23:30:00Z"), "home_team": "Austin FC",
         "away_team": "LA Galaxy"},
        {"id": "s2", "sport": "soccer_usa_mls", "commence_time": t("2024-07-20T23:30:00Z"), "home_team": "Nowhere FC",
         "away_team": "LA Galaxy"}]}
    for s, g in games.items():
        bulk.save_schedule(tmp_path, s, [{**x, "first_seen": None} for x in g])
    statsapi = {"dates": [{"games": [
        {"gamePk": 1, "gameDate": "2024-06-08T17:10:00Z", "teams": {"home": {"team": {"name": "New York Mets"}},
                                                                      "away": {"team": {"name": "Philadelphia Phillies"}}},
         "venue": {"name": "London Stadium", "location": {"defaultCoordinates": {"latitude": 51.54, "longitude": -0.02}}}}]}]}
    gv = gamevenues.GameVenues(cache, session=Session([("statsapi", statsapi)]), rate_per_sec=1e6)
    gv.mlb(date(2024, 6, 1), date(2024, 6, 30), fetch=True)
    rows, unresolved = join.build(cfg, cache, sports=["baseball_mlb", "soccer_usa_mls"], weather=False, gv=gv)
    by = {r["id"]: r for r in rows}
    assert by["m1"]["venue_id"] == "globe_life_field" and by["m1"]["roof"] == "retractable"
    assert by["m2"]["venue_id"] == "london_stadium" and by["m2"]["venue_how"] == "statsapi"
    assert by["s1"]["venue_id"] == "q2_stadium"
    assert [u["id"] for u in unresolved] == ["s2"] and unresolved[0]["venue_how"] == "unknown home team"
    # weather: serve the planned requests from a fake Open-Meteo and read them back
    reqs = join.plan([by["s1"]])
    body_a = hourly_body(t("2024-07-01T00:00:00Z"), 31 * 24, 97.0, 40.0)
    body_p = hourly_body(t("2024-07-01T00:00:00Z"), 31 * 24, 95.0, 45.0, prev=True)
    meteo = om.OpenMeteo(cache, session=Session([("archive-api", body_a), ("previous-runs", body_p)]), rate_per_sec=1e6)
    assert [r.weight for r in reqs] == [3, 3]                     # 31 days: Open-Meteo counts 3 calls each
    assert meteo.run(reqs, max_calls=5)["fetched"] == 1           # a weighted budget: the second would pass 5
    assert meteo.run(reqs, max_calls=10)["fetched"] == 1          # the first is cached
    rows, _ = join.build(cfg, cache, sports=["soccer_usa_mls"], weather=True, gv=gv, meteo=meteo)
    s1 = next(r for r in rows if r["id"] == "s1")
    assert s1["obs_temp_f"] == 97.0 and s1["fc1_temp_f"] == 95.0
    assert s1["fc1_heat_index_f"] == pytest.approx(heat_index_f(95.0, 45.0)) and s1["fc1_heat_index_f"] > 90
    path = join.write(rows, [], tmp_path / "out")
    assert path.exists()


def test_qualifying_applies_the_registered_triggers(tmp_path):
    """docs/HEAT_HYPOTHESES.md: S-H1 day-1 heat index >= 90 F, B-H1 day-1 temperature >= 90 F, open venues,
    the 2024-25 test seasons, nothing sealed, World Cup out; games without a day-1 forecast can't qualify."""
    def row(gid, sport, season, roof, temp, hi, sealed=False, kick="2024-07-20T23:30:00Z"):
        return {"id": gid, "sport": sport, "season": season, "sealed": sealed, "roof": roof, "commence_time": t(kick),
                "venue_id": "v", "venue_name": "V", "fc1_temp_f": temp, "fc1_heat_index_f": hi}
    rows = [row("m_hot", "baseball_mlb", "2024", "open", 91.0, 99.0),
            row("m_hi_only", "baseball_mlb", "2024", "open", 88.0, 95.0),          # MLB uses temperature, not the index
            row("m_roof", "baseball_mlb", "2025", "retractable", 101.0, 105.0),
            row("m_old", "baseball_mlb", "2023", "open", 95.0, 100.0),
            row("m_nofc", "baseball_mlb", "2025", "open", None, None),
            row("m_nan", "baseball_mlb", "2025", "open", float("nan"), float("nan")),
            row("s_hot", "soccer_usa_mls", "2025", "open", 86.0, 92.0),           # soccer uses the heat index
            row("s_temp_only", "soccer_usa_mls", "2025", "open", 90.5, 89.0),
            row("s_sealed", "soccer_usa_mls", "2026", "open", 95.0, 100.0, sealed=True),
            row("s_wc", "soccer_fifa_world_cup", "2024", "open", 95.0, 100.0),
            row("s_cup", "soccer_fifa_club_world_cup", "2025", "open", 93.0, 96.0)]
    q = join.qualifying(rows)
    assert [(x["pull"], x["id"], x["value"]) for x in q] == [("HB1", "m_hot", 91.0), ("HS1", "s_cup", 96.0), ("HS1", "s_hot", 92.0)]
    assert q[0]["trigger"] == "fc1_temp_f >= 90" and q[1]["trigger"] == "fc1_heat_index_f >= 90"
    counts = {(c["pull"], c["season"]): c for c in join.qualifying_counts(rows, q)}
    assert counts[("HB1", "2024")] == {"pull": "HB1", "season": "2024", "open_venue_games": 2, "with_day1_forecast": 2, "qualifying": 1}
    assert counts[("HB1", "2025")]["open_venue_games"] == 2 and counts[("HB1", "2025")]["with_day1_forecast"] == 0
    path = join.write_qualifying(q, tmp_path)
    with path.open() as f:
        got = list(csv.DictReader(f))
    assert [g["id"] for g in got] == ["m_hot", "s_cup", "s_hot"] and got[0]["sport"] == "baseball_mlb"
    assert list(got[0]) == join.QUALIFYING_COLS and got[0]["commence_time"].startswith("2024-07-20T23:30")
    # the bulk puller reads exactly this file shape
    cfg = bulk.load_config()
    hb1 = {**cfg["pulls"]["HB1"], "games_from": str(path)}
    assert bulk.games_from(hb1, "baseball_mlb") == {"m_hot"} and bulk.games_from(hb1, "soccer_usa_mls") == {"s_hot"}


def test_kick_hour_crosses_the_month_boundary():
    assert join.kick_hour(t("2024-07-31T23:40:00Z")) == t("2024-08-01T00:00:00Z")
    assert join.kick_hour(t("2024-07-31T23:20:00Z")) == t("2024-07-31T23:00:00Z")


def test_open_meteo_weights_requests_as_it_bills_them():
    """#33 item 10: more than 14 days counts as several calls, so the budget and pacing are weighted."""
    v = V.venues()["coors_field"]
    feb, jul = om.month_requests("coors_field", v, 2023, 2), om.month_requests("coors_field", v, 2024, 7)
    assert [r.weight for r in feb] == [2] and [r.weight for r in jul] == [3, 3]
    assert om.Request("archive", "x", 0, 0, date(2024, 1, 1), date(2024, 1, 14)).weight == 1


def test_statsapi_coordinates_win_and_far_table_rows_are_flagged(tmp_path):
    """#33 item 11: prefer the MLB Stats API's park coordinates when cached; flag table rows > 2 km away."""
    cfg, cache = bulk.load_config(), RawCache(tmp_path)
    games = [{"id": "c1", "sport": "baseball_mlb", "commence_time": t("2024-07-04T00:40:00Z"), "home_team": "Colorado Rockies",
              "away_team": "Chicago Cubs"},
             {"id": "c2", "sport": "baseball_mlb", "commence_time": t("2024-07-05T00:40:00Z"), "home_team": "Colorado Rockies",
              "away_team": "Chicago Cubs"},                       # not in the Stats API cache: same park, same coordinates
             {"id": "a1", "sport": "baseball_mlb", "commence_time": t("2024-07-04T23:20:00Z"), "home_team": "Atlanta Braves",
              "away_team": "San Francisco Giants"}]
    bulk.save_schedule(tmp_path, "baseball_mlb", [{**g, "first_seen": None} for g in games])

    def g(pk, when, home, away, venue, lat, lon):
        return {"gamePk": pk, "gameDate": when, "teams": {"home": {"team": {"name": home}}, "away": {"team": {"name": away}}},
                "venue": {"name": venue, "location": {"defaultCoordinates": {"latitude": lat, "longitude": lon}}}}
    statsapi = {"dates": [{"games": [g(1, "2024-07-04T00:40:00Z", "Colorado Rockies", "Chicago Cubs", "Coors Field", 39.9, -104.99),
                                     g(2, "2024-07-04T23:20:00Z", "Atlanta Braves", "San Francisco Giants", "Truist Park",
                                       33.8907, -84.4677)]}]}
    gv = gamevenues.GameVenues(cache, session=Session([("statsapi", statsapi)]), rate_per_sec=1e6)
    gv.mlb(date(2024, 7, 1), date(2024, 7, 31), fetch=True)
    rows, unresolved = join.build(cfg, cache, sports=["baseball_mlb"], weather=False, gv=gv)
    by = {r["id"]: r for r in rows}
    assert not unresolved and (by["c1"]["lat"], by["c2"]["lat"]) == (39.9, 39.9)
    assert by["c1"]["coord_source"] == "statsapi" and 15 < by["c1"]["coord_gap_km"] < 17
    assert by["a1"]["coord_gap_km"] < 0.1                        # the corrected Truist Park row
    assert list(join.coord_flags(rows)) == ["coors_field"]
    assert V.distance_km(33.95389, -84.45472, 33.8908, -84.4678) > 6    # the old GeoJSON point was ~7 km off


def test_espn_games_at_an_unknown_ground_say_so(tmp_path):
    """#33 item 13: an ESPN-sourced game whose ground isn't in the table names it, in unresolved.csv too."""
    cfg, cache = bulk.load_config(), RawCache(tmp_path)
    game = {"id": "ca1", "sport": "soccer_conmebol_copa_america", "commence_time": t("2024-06-21T00:00:00Z"),
            "home_team": "Argentina", "away_team": "Canada"}
    bulk.save_schedule(tmp_path, "soccer_conmebol_copa_america", [{**game, "first_seen": None}])
    espn = {"events": [{"date": "2024-06-21T00:00Z", "competitions": [{
        "competitors": [{"homeAway": "home", "team": {"displayName": "Argentina"}},
                        {"homeAway": "away", "team": {"displayName": "Canada"}}],
        "venue": {"fullName": "Brand New Ground", "address": {"city": "Somewhere"}}}]}]}
    gv = gamevenues.GameVenues(cache, session=Session([("espn", espn)]), rate_per_sec=1e6)
    gv.espn("soccer_conmebol_copa_america", date(2024, 6, 1), date(2024, 6, 30), fetch=True)
    rows, unresolved = join.build(cfg, cache, sports=["soccer_conmebol_copa_america"], weather=False, gv=gv)
    assert rows == [] and unresolved[0]["venue_how"] == "ESPN venue not in table: Brand New Ground"
    join.write(rows, unresolved, tmp_path / "out")
    assert "Brand New Ground" in (tmp_path / "out" / "unresolved.csv").read_text().splitlines()[1]


def test_roof_labels_are_consistent_for_the_heat_sample():
    """#33 item 14 (HEAT_HYPOTHESES.md amendment 1): stands-only roofs are `open`, so Euro 2024 contributes
    games; World Cup 2022 has open-ground matches (Stadium 974), so it is excluded by competition, not by roof."""
    from collections import Counter
    vs = V.venues()
    open_by = Counter((r["sport_key"], r["kickoff_utc"][:4]) for r in V.fixtures() if vs[r["venue_id"]].roof == "open")
    assert open_by[("soccer_uefa_european_championship", "2024")] == 37
    assert open_by[("soccer_fifa_world_cup", "2022")] == 7 and open_by[("soccer_fifa_world_cup", "2026")] == 65
    assert [v.venue_id for v in vs.values() if v.roof == "covered"] == ["sofi_stadium"]
