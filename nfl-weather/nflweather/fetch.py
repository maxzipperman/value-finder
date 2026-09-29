"""Data collection.

Sources
-------
* nflverse schedules (games.csv): every game since 1999 with the official
  game-book kickoff temperature and wind (the same numbers Pro-Football-Reference
  shows, which is what the 2014 thesis scraped), roof/surface, and closing
  spread / total / moneyline.
* nflverse play-by-play (one parquet per season): used to rebuild team box scores
  plus EPA, CPOE, air yards, expected pass rate, and every field goal.
* Open-Meteo historical archive (ERA5 reanalysis): hourly precipitation, snowfall,
  gusts, humidity, temperature and wind at each stadium for the game window.
  Fills the precipitation gap the thesis flagged and the missing game-book values.
* NOAA GHCN-Daily (NCEI access API): daily highs at each home city's airport,
  used for the visitor's 7-day "practice climate" (acclimation variable).

Everything is cached under data/raw, so re-running only pulls what is new.
"""
from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from io import StringIO

import pandas as pd
import requests

from .config import RAW, USER_AGENT, FIRST_SEASON
from .stadiums import STADIUMS, coords, home_stations, resolve_stadium

SCHEDULE_URL = "https://raw.githubusercontent.com/nflverse/nfldata/master/data/games.csv"
PBP_URL = "https://github.com/nflverse/nflverse-data/releases/download/pbp/play_by_play_{season}.parquet"
STATS_URL = "https://github.com/nflverse/nflverse-data/releases/download/stats_player/stats_player_week_{season}.parquet"
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
NCEI_URL = "https://www.ncei.noaa.gov/access/services/data/v1"

HOURLY_VARS = [
    "temperature_2m", "relative_humidity_2m", "apparent_temperature",
    "precipitation", "rain", "snowfall", "weather_code",
    "wind_speed_10m", "wind_direction_10m", "wind_gusts_10m",
]  # 10 variables = 1 Open-Meteo "call" per single-day request

session = requests.Session()
session.headers["User-Agent"] = USER_AGENT


def _get(url, params=None, tries=5, timeout=120):
    for i in range(tries):
        try:
            r = session.get(url, params=params, timeout=timeout)
            if r.status_code == 429:
                wait = 65 * (i + 1)
                print(f"  rate limited; sleeping {wait}s", flush=True)
                time.sleep(wait)
                continue
            r.raise_for_status()
            return r
        except requests.RequestException as e:
            if i == tries - 1:
                raise
            print(f"  retry {i + 1} after error: {e}", flush=True)
            time.sleep(5 * (i + 1))
    raise RuntimeError(f"failed: {url}")


def download(url, dest, force=False):
    if dest.exists() and not force:
        return dest
    r = _get(url, timeout=600)
    tmp = dest.with_suffix(dest.suffix + ".part")
    tmp.write_bytes(r.content)
    tmp.replace(dest)
    return dest


# --------------------------------------------------------------------------- nflverse
def fetch_schedule(force=True):
    return download(SCHEDULE_URL, RAW / "games.csv", force=force)


def current_season(games=None):
    games = games if games is not None else pd.read_csv(RAW / "games.csv")
    return int(games.loc[games.result.notna(), "season"].max())


def fetch_pbp(seasons=None, workers=4):
    """Download play-by-play parquet files. Past seasons are cached; the current
    season is always refreshed because nflverse updates it nightly."""
    cur = current_season()
    seasons = seasons or range(FIRST_SEASON, cur + 1)

    def one(season):
        dest = RAW / "pbp" / f"play_by_play_{season}.parquet"
        download(PBP_URL.format(season=season), dest, force=(season == cur))
        return season, dest.stat().st_size

    with ThreadPoolExecutor(workers) as ex:
        for season, size in ex.map(one, seasons):
            print(f"  pbp {season}: {size / 1e6:.1f} MB", flush=True)


def fetch_player_stats(seasons=None, workers=4):
    """Download nflverse weekly player stats (every player, kickers included). Past seasons are
    cached; the current season is always refreshed."""
    cur = current_season()
    seasons = seasons or range(FIRST_SEASON, cur + 1)

    def one(season):
        dest = RAW / "player_stats" / f"stats_player_week_{season}.parquet"
        dest.parent.mkdir(parents=True, exist_ok=True)
        download(STATS_URL.format(season=season), dest, force=(season == cur))
        return season, dest.stat().st_size

    with ThreadPoolExecutor(workers) as ex:
        for season, size in ex.map(one, seasons):
            print(f"  player stats {season}: {size / 1e6:.1f} MB", flush=True)


# --------------------------------------------------------------------------- NOAA
def fetch_home_climate(start="1998-07-01", end=None, force=False):
    """Daily TMAX/TMIN/PRCP for every home city's GHCN-D airport station."""
    end = end or date.today().isoformat()
    outdir = RAW / "weather" / "ghcnd"
    outdir.mkdir(parents=True, exist_ok=True)
    for st in home_stations():
        dest = outdir / f"{st}.csv"
        if dest.exists() and not force:
            last = pd.read_csv(dest, usecols=["DATE"]).DATE.max()
            if last >= (date.today() - timedelta(days=3)).isoformat():
                continue
        params = dict(dataset="daily-summaries", stations=st, startDate=start, endDate=end,
                      dataTypes="TMAX,TMIN,PRCP", units="standard", format="csv",
                      includeStationName="true", includeStationLocation="1")
        r = _get(NCEI_URL, params)
        df = pd.read_csv(StringIO(r.text))
        df.to_csv(dest, index=False)
        name = df.NAME.iloc[0] if len(df) else "EMPTY"
        print(f"  {st}: {len(df):>6} days  {name}", flush=True)
        time.sleep(1)


# --------------------------------------------------------------------------- Open-Meteo
def weather_needed(games):
    """(stadium_key, date) pairs that need game-time weather: every played or
    upcoming game that is not in a fixed dome / closed roof."""
    g = games.copy()
    g["stadium_key"] = [resolve_stadium(a, b) for a, b in zip(g.stadium_id, g.stadium)]
    g = g[~g.roof.isin(["dome", "closed"])]
    g = g[g.stadium_key.map(lambda k: k in STADIUMS)]
    return g[["stadium_key", "gameday"]].drop_duplicates()


def _om_cache(key, day):
    d = RAW / "weather" / "openmeteo"
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{key}_{day}.json"


def fetch_game_weather(games, per_minute=75, max_calls=None):
    """Hourly ERA5 weather for each outdoor/retractable game day.

    Open-Meteo's free tier allows 600/min, 5,000/hour and 10,000/day; a
    single-day, 10-variable request is one call, so ~75/min keeps us under the
    hourly cap. Cached per stadium-day, so the job is resumable.
    """
    today = date.today()
    need = weather_needed(games)
    need = need[pd.to_datetime(need.gameday).dt.date <= today - timedelta(days=6)]
    todo = [(k, d) for k, d in need.itertuples(index=False) if not _om_cache(k, d).exists()]
    print(f"  Open-Meteo archive: {len(need)} stadium-days, {len(todo)} to fetch", flush=True)
    gap = 60.0 / per_minute
    for i, (key, day) in enumerate(todo[:max_calls] if max_calls else todo):
        lat, lon = coords(key)
        params = dict(latitude=lat, longitude=lon, start_date=day, end_date=day,
                      hourly=",".join(HOURLY_VARS), temperature_unit="fahrenheit",
                      wind_speed_unit="mph", precipitation_unit="inch",
                      timezone="America/New_York")
        t0 = time.time()
        r = _get(ARCHIVE_URL, params)
        _om_cache(key, day).write_text(r.text)
        if i % 250 == 0:
            print(f"  {i}/{len(todo)} {key} {day}", flush=True)
        time.sleep(max(0.0, gap - (time.time() - t0)))


def fetch_forecasts(games, days_ahead=10):
    """Forecast weather for upcoming games (Open-Meteo forecast API, same
    variables/units as the archive). Cached per stadium-day, refreshed each run."""
    today = date.today()
    need = weather_needed(games[games.result.isna()])
    dd = pd.to_datetime(need.gameday).dt.date
    need = need[(dd >= today) & (dd <= today + timedelta(days=days_ahead))]
    outdir = RAW / "weather" / "forecast"
    outdir.mkdir(parents=True, exist_ok=True)
    for key, day in need.itertuples(index=False):
        lat, lon = coords(key)
        params = dict(latitude=lat, longitude=lon, start_date=day, end_date=day,
                      hourly=",".join(HOURLY_VARS), temperature_unit="fahrenheit",
                      wind_speed_unit="mph", precipitation_unit="inch",
                      timezone="America/New_York")
        r = _get(FORECAST_URL, params)
        (outdir / f"{key}_{day}.json").write_text(r.text)
    print(f"  forecasts: {len(need)} stadium-days", flush=True)


PREV_URL = "https://previous-runs-api.open-meteo.com/v1/forecast"
PREV_VARS = [
    "wind_speed_10m_previous_day1", "wind_speed_10m_previous_day2", "wind_speed_10m_previous_day3",
    "wind_gusts_10m_previous_day1", "temperature_2m_previous_day1", "temperature_2m_previous_day3",
    "precipitation_previous_day1", "precipitation_previous_day3",
    "snowfall_previous_day1", "snowfall_previous_day3",
]


def fetch_previous_forecasts(games, start="2024-01-01", per_minute=60):
    """What the forecast said 1-3 days before kickoff (Open-Meteo previous-runs
    archive, available from 2024). Used to measure how much of the realized-weather
    edge survives when you only have a forecast."""
    today = date.today()
    need = weather_needed(games)
    dd = pd.to_datetime(need.gameday).dt.date
    need = need[(dd >= date.fromisoformat(start)) & (dd <= today - timedelta(days=1))]
    outdir = RAW / "weather" / "prevruns"
    outdir.mkdir(parents=True, exist_ok=True)
    todo = [(k, d) for k, d in need.itertuples(index=False) if not (outdir / f"{k}_{d}.json").exists()]
    print(f"  previous-run forecasts: {len(need)} stadium-days, {len(todo)} to fetch", flush=True)
    for key, day in todo:
        lat, lon = coords(key)
        params = dict(latitude=lat, longitude=lon, start_date=day, end_date=day, hourly=",".join(PREV_VARS),
                      temperature_unit="fahrenheit", wind_speed_unit="mph", precipitation_unit="inch",
                      timezone="America/New_York")
        t0 = time.time()
        r = _get(PREV_URL, params)
        (outdir / f"{key}_{day}.json").write_text(r.text)
        time.sleep(max(0.0, 60.0 / per_minute - (time.time() - t0)))


def load_hourly(key, day, kind="openmeteo"):
    p = RAW / "weather" / kind / f"{key}_{day}.json"
    if not p.exists():
        return None
    js = json.loads(p.read_text())
    if "hourly" not in js:
        return None
    h = pd.DataFrame(js["hourly"])
    h["hour"] = pd.to_datetime(h.time).dt.hour
    return h
