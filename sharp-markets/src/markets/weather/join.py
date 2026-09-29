"""One row per MLB or soccer game in the 5M-month schedules (data/raw/_schedules/, from `markets odds5m probe`):
venue, roof, and the weather at the kickoff hour, observed (ERA5) and as forecast a day earlier.

Writes data/weather/game_weather.parquet and data/weather/unresolved.csv (games whose venue couldn't be
placed, with the reason and any venue name the source gave).

`markets weather qualifying` then applies the pre-registered triggers (TRIGGERS, from docs/HEAT_HYPOTHESES.md)
to that table and writes data/weather/heat_qualifying.csv: the games whose closes the HB1 and HS1 pulls buy
(config/odds5m.yaml `games_from`). The trigger comes first and the odds second, so the count of qualifying
games is known before a credit is spent on them.

Coordinates: an MLB park takes the MLB Stats API's own coordinates when they're cached (one pair per park,
so every game there shares its weather requests), and the table's otherwise. Where both exist,
coord_gap_km says how far apart they are; `markets weather plan` lists parks more than COORD_FLAG_KM
apart, so the table can be corrected.

No odds and no scores: outcomes are joined only by the pre-registered analysis (docs/HEAT_HYPOTHESES.md),
which also keeps the sealed seasons out.
"""
from __future__ import annotations

import csv
from datetime import date, timedelta
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from ..cache import RawCache
from ..settings import DATA_DIR
from . import openmeteo as om
from .gamevenues import GameVenues, nearest
from .heat import heat_index_f
from .venues import MLB, canonical, distance_km, fixture_venue, home_venue, norm, venues

OUT_DIR = DATA_DIR / "weather"
FIXTURE_SPORTS = {"soccer_fifa_world_cup", "soccer_uefa_european_championship"}
ESPN_ONLY = {"soccer_conmebol_copa_america", "soccer_fifa_club_world_cup", "soccer_concacaf_gold_cup"}
COORD_FLAG_KM = 2.0

# The pre-registered triggers, docs/HEAT_HYPOTHESES.md (S-H1, B-H1; amendment 4 makes both descriptive and
# closes-only). Day-1 forecast at the kickoff hour, `open` venues only, the 2024-25 test seasons. World Cup 2022
# is out as a competition (amendment 1) and every 2026 game is sealed, so the World Cup key is excluded outright.
TRIGGERS = {
    "HS1": {"sport": lambda s: s.startswith("soccer_") and s != "soccer_fifa_world_cup",
            "field": "fc1_heat_index_f", "at_least": 90.0},
    "HB1": {"sport": lambda s: s == MLB, "field": "fc1_temp_f", "at_least": 90.0},
}
TEST_SEASONS = ("2024", "2025")
QUALIFYING_COLS = ["sport", "id", "season", "commence_time", "venue_id", "venue_name", "pull", "trigger", "value"]


def weather_sports(cfg: dict) -> list[str]:
    return [MLB, *cfg["soccer"]]


def _span(cfg: dict, sport: str) -> tuple[date, date]:
    w = cfg["sports"][sport]["windows"]
    return min(x["from"] for x in w), max(x["to"] for x in w)


def fetch_game_venues(cfg: dict, cache: RawCache, sports: list[str], *, leagues_too: bool = False, gv=None) -> dict:
    """Game-level venues (Mac): MLB Stats API for MLB; ESPN for the tournaments without a fixture table,
    and for the leagues too with leagues_too=True (a match-by-match check of the dated home venues)."""
    gv = gv or GameVenues(cache)
    n = {}
    for s in sports:
        lo, hi = _span(cfg, s)
        hi = min(hi, date.today())
        if s == MLB:
            n[s] = len(gv.mlb(lo, hi, fetch=True))
        elif s in ESPN_ONLY or (leagues_too and s not in FIXTURE_SPORTS):
            n[s] = len(gv.espn(s, lo, hi, fetch=True))
    return n


def resolve(sport: str, g: dict, game_rows: list[dict]) -> tuple[str | None, str, dict]:
    """(venue_id, how, extra) for one schedule game. Extra carries coordinates for an MLB park the
    venue table doesn't know (the Stats API supplies them)."""
    kick, home, away = g["commence_time"], g["home_team"], g["away_team"]
    key = (lambda n: canonical(sport, n))                              # noqa: E731
    hit = nearest(game_rows, home, away, kick, key) if game_rows else None
    if hit and hit.get("venue_id"):
        return hit["venue_id"], "statsapi" if sport == MLB else "espn", {}
    if hit and sport == MLB and hit.get("lat") is not None:
        return None, "statsapi (park not in the table)", {"venue_name": hit["venue_name"], "lat": hit["lat"],
                                                          "lon": hit["lon"]}
    if sport in FIXTURE_SPORTS:
        vid = fixture_venue(sport, home, away, kick)
        return vid, "fixture table" if vid else "not in the fixture table", {}
    if sport in ESPN_ONLY:
        if hit:                                  # ESPN has the match, at a ground the table doesn't know
            name = hit.get("venue_name") or "(no name)"
            return None, f"ESPN venue not in table: {name}", {"venue_name": hit.get("venue_name") or ""}
        return None, "needs ESPN venues (markets weather venues --confirm)", {}
    return (*home_venue(sport, home, kick.date(), away), {})


def statsapi_coords(game_rows: list[dict]) -> dict[str, tuple[float, float]]:
    """venue_id -> the MLB Stats API's coordinates for that park (the first cached pair; they're per park)."""
    out = {}
    for r in game_rows:
        if r.get("venue_id") and r.get("lat") is not None and r.get("lon") is not None:
            out.setdefault(r["venue_id"], (float(r["lat"]), float(r["lon"])))
    return out


def build(cfg: dict, cache: RawCache, *, sports: list[str] | None = None, weather: bool = True,
          gv: GameVenues | None = None, meteo: om.OpenMeteo | None = None) -> tuple[list[dict], list[dict]]:
    from ..oddsapi.bulk import load_schedules
    sports = sports or weather_sports(cfg)
    schedules = load_schedules(cfg, cache.raw_dir, sports)
    gv = gv or GameVenues(cache)
    meteo = meteo or om.OpenMeteo(cache)
    V = venues()
    rows, unresolved = [], []
    for sport in sports:
        games = [g for g in schedules.get(sport, []) if g["season"] is not None]
        if not games:
            continue
        lo, hi = min(g["commence_time"] for g in games).date(), max(g["commence_time"] for g in games).date()
        cached = gv.mlb(lo, hi) if sport == MLB else gv.espn(sport, lo, hi) if sport not in FIXTURE_SPORTS else []
        api = statsapi_coords(cached) if sport == MLB else {}
        for g in games:
            vid, how, extra = resolve(sport, g, cached)
            base = {"sport": sport, "id": g["id"], "season": g["season"], "sealed": g["sealed"],
                    "commence_time": g["commence_time"], "home_team": g["home_team"], "away_team": g["away_team"],
                    "venue_how": how}
            if vid is None and extra.get("lat") is None:
                unresolved.append({**base, "commence_time": g["commence_time"].isoformat(),
                                   "venue_name": extra.get("venue_name", "")})
                continue
            v = V.get(vid)
            row = {**base, "venue_id": vid or "", "venue_name": v.name if v else extra["venue_name"],
                   "roof": v.roof if v else "unknown", "lat": v.lat if v else float(extra["lat"]),
                   "lon": v.lon if v else float(extra["lon"]),
                   "coord_source": "table" if v else "statsapi", "coord_gap_km": None}
            if v and vid in api:                 # the Stats API's own coordinates win; the gap is kept
                row.update(lat=api[vid][0], lon=api[vid][1], coord_source="statsapi",
                           coord_gap_km=round(distance_km(v.lat, v.lon, *api[vid]), 2))
            if weather:
                row.update(kickoff_weather(meteo, vid or f"statsapi:{norm(row['venue_name'])}", row["lat"],
                                           row["lon"], g["commence_time"]))
            rows.append(row)
    return rows, unresolved


def coord_flags(rows: list[dict]) -> dict[str, float]:
    """venue_id -> km between the table's and the Stats API's coordinates, for parks over COORD_FLAG_KM."""
    return {r["venue_id"]: r["coord_gap_km"] for r in rows
            if r.get("coord_gap_km") is not None and r["coord_gap_km"] > COORD_FLAG_KM}


def kick_hour(kick):
    """The kickoff rounded to the nearest hour (the weather row used), UTC."""
    return (kick + timedelta(minutes=30)).replace(minute=0, second=0, microsecond=0)


def kickoff_weather(meteo: om.OpenMeteo, vid: str, lat: float, lon: float, kick) -> dict:
    out, h = {}, kick_hour(kick)
    for kind, prefix in (("archive", "obs"), ("prev", "fc1")):
        reqs = [r for r in om.month_requests(vid, _LatLon(lat, lon), h.year, h.month) if r.kind == kind]
        vals = om.at_hour(meteo.body(reqs[0]), h) if reqs else {}
        t, rh = vals.get("temperature_2m"), vals.get("relative_humidity_2m")
        out.update({f"{prefix}_temp_f": t, f"{prefix}_rh": rh, f"{prefix}_heat_index_f": heat_index_f(t, rh),
                    f"{prefix}_wind_mph": vals.get("wind_speed_10m"), f"{prefix}_wind_dir": vals.get("wind_direction_10m"),
                    f"{prefix}_precip_in": vals.get("precipitation")})
    return out


class _LatLon:
    def __init__(self, lat, lon):
        self.lat, self.lon = lat, lon


def venue_days(rows: list[dict]) -> dict[tuple[str, date], tuple[float, float]]:
    return {(r["venue_id"] or f"statsapi:{norm(r['venue_name'])}", kick_hour(r["commence_time"]).date()): (r["lat"], r["lon"])
            for r in rows}


def plan(rows: list[dict]) -> list[om.Request]:
    days = venue_days(rows)
    locs = {vid: _LatLon(*ll) for (vid, _), ll in days.items()}
    return om.plan_requests(set(days), locs)


def _num(v):
    return None if v is None or (isinstance(v, float) and v != v) else float(v)


def qualifying(rows: list[dict], seasons=TEST_SEASONS) -> list[dict]:
    """The games whose day-1 forecast meets a trigger in TRIGGERS: `open` venue, an unsealed test season, the
    forecast present. One row per game and trigger, with the trigger value. Nothing else is read."""
    out = []
    for r in rows:
        if r.get("roof") != "open" or r.get("season") not in seasons or r.get("sealed"):
            continue
        for pid, tr in TRIGGERS.items():
            v = _num(r.get(tr["field"]))
            if tr["sport"](r["sport"]) and v is not None and v >= tr["at_least"]:
                out.append({"sport": r["sport"], "id": r["id"], "season": r["season"], "commence_time": r["commence_time"],
                            "venue_id": r.get("venue_id", ""), "venue_name": r.get("venue_name", ""), "pull": pid,
                            "trigger": f"{tr['field']} >= {tr['at_least']:g}", "value": round(v, 1)})
    return sorted(out, key=lambda q: (q["pull"], q["commence_time"], q["id"]))


def qualifying_counts(rows: list[dict], quals: list[dict], seasons=TEST_SEASONS) -> list[dict]:
    """Per trigger and season: games at open venues, of which with a day-1 forecast, of which qualifying."""
    out = []
    for pid, tr in TRIGGERS.items():
        for season in seasons:
            base = [r for r in rows if tr["sport"](r["sport"]) and r.get("season") == season and not r.get("sealed")
                    and r.get("roof") == "open"]
            out.append({"pull": pid, "season": season, "open_venue_games": len(base),
                        "with_day1_forecast": sum(_num(r.get(tr["field"])) is not None for r in base),
                        "qualifying": sum(q["pull"] == pid and q["season"] == season for q in quals)})
    return out


def write_qualifying(quals: list[dict], out_dir: Path = OUT_DIR) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "heat_qualifying.csv"
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, QUALIFYING_COLS)
        w.writeheader()
        for q in quals:
            w.writerow({**q, "commence_time": q["commence_time"].isoformat()
                        if hasattr(q["commence_time"], "isoformat") else q["commence_time"]})
    return path


def write(rows: list[dict], unresolved: list[dict], out_dir: Path = OUT_DIR) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    if rows:
        pq.write_table(pa.Table.from_pylist(rows), out_dir / "game_weather.parquet")
    with (out_dir / "unresolved.csv").open("w", newline="") as f:
        cols = ["sport", "id", "season", "sealed", "commence_time", "home_team", "away_team", "venue_how", "venue_name"]
        w = csv.DictWriter(f, cols)
        w.writeheader()
        w.writerows({k: u.get(k) for k in cols} for u in unresolved)
    return out_dir / "game_weather.parquet"


def main(args) -> None:
    """`markets weather <stage>` (docs/ODDS5M_DAY_ONE.md, "Weather joins")."""
    from collections import Counter

    from ..oddsapi.bulk import load_config
    from .venues import check_tables
    cfg, cache = load_config(), RawCache()
    sports = [s.strip() for s in args.sports.split(",")] if args.sports else None
    if args.stage == "check":
        bad = check_tables()
        print(f"{len(venues())} venues; problems: {len(bad)}")
        for b in bad:
            print("  " + b)
        return
    if args.stage == "venues":
        if not args.confirm:
            raise SystemExit("dry run: add --confirm to fetch game-level venues (MLB Stats API, ESPN; free)")
        print(fetch_game_venues(cfg, cache, sports or weather_sports(cfg), leagues_too=args.leagues_too))
        return
    if args.stage == "qualifying":
        table = OUT_DIR / "game_weather.parquet"
        if not table.exists():
            raise SystemExit(f"{table} is missing: run `markets weather join` first")
        rows = pq.read_table(table).to_pylist()
        quals = qualifying(rows)
        for c in qualifying_counts(rows, quals):
            print(f"{c['pull']} {c['season']}: {c['open_venue_games']:,} games at open venues, "
                  f"{c['with_day1_forecast']:,} with a day-1 forecast, {c['qualifying']:,} qualifying")
        path = write_qualifying(quals)
        print(f"wrote {path} ({len(quals):,} rows; the HB1 and HS1 pulls read it). No odds or result was touched.")
        return
    rows, unresolved = build(cfg, cache, sports=sports, weather=args.stage == "join")
    print(f"{len(rows):,} games placed; {len(unresolved):,} unresolved: "
          f"{dict(Counter(u['venue_how'] for u in unresolved))}")
    print("placed by: " + str(dict(Counter(r["venue_how"] for r in rows))))
    far = coord_flags(rows)
    if far:
        print(f"parks whose table coordinates are more than {COORD_FLAG_KM:g} km from the MLB Stats API's "
              f"(the Stats API's are used; correct config/venues/mlb_parks.csv): "
              + ", ".join(f"{vid} {km:.1f} km" for vid, km in far.items()))
    if args.stage in ("plan", "fetch"):
        reqs = plan(rows)
        meteo = om.OpenMeteo(cache)
        todo = [r for r in reqs if not meteo.is_cached(r)]
        print(f"Open-Meteo: {len(reqs):,} requests ({sum(r.kind == 'archive' for r in reqs):,} archive, "
              f"{sum(r.kind == 'prev' for r in reqs):,} previous-run), {len(todo):,} not cached, "
              f"{sum(r.weight for r in todo):,} weighted calls (the free tier allows 10,000 a day)")
        if args.stage == "fetch":
            if not args.confirm:
                raise SystemExit("dry run: add --confirm (and --max-calls) to call Open-Meteo")
            print(meteo.run(reqs, max_calls=args.max_calls))
        return
    path = write(rows, unresolved)
    have = sum(r.get("obs_temp_f") is not None for r in rows)
    print(f"wrote {path} ({have:,} of {len(rows):,} games with observed weather; "
          f"{sum(r.get('fc1_temp_f') is not None for r in rows):,} with a day-1 forecast)")
