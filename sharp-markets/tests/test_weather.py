"""Venue tables, venue resolution, heat index, the Open-Meteo plan and the weather join. No network."""
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
    assert meteo.run(reqs, max_calls=10)["fetched"] == 2
    rows, _ = join.build(cfg, cache, sports=["soccer_usa_mls"], weather=True, gv=gv, meteo=meteo)
    s1 = next(r for r in rows if r["id"] == "s1")
    assert s1["obs_temp_f"] == 97.0 and s1["fc1_temp_f"] == 95.0
    assert s1["fc1_heat_index_f"] == pytest.approx(heat_index_f(95.0, 45.0)) and s1["fc1_heat_index_f"] > 90
    path = join.write(rows, [], tmp_path / "out")
    assert path.exists()


def test_kick_hour_crosses_the_month_boundary():
    assert join.kick_hour(t("2024-07-31T23:40:00Z")) == t("2024-08-01T00:00:00Z")
    assert join.kick_hour(t("2024-07-31T23:20:00Z")) == t("2024-07-31T23:00:00Z")
