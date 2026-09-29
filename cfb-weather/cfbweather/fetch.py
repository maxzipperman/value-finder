"""Data collection for college football. Everything is cached under data/raw.

Sources (all free, no key)
* cfbfastR-data (sportsdataverse, mirrors CollegeFootballData.com): yearly
  schedules with UTC kickoff, venue and scores; yearly team info with each home
  venue's coordinates, elevation, grass and dome flag; betting lines 2006-2025
  (spread / total / moneyline, several books, some opening lines).
* Meteostat bulk hourly station data: one file per station with its whole
  history (temperature, wind, gusts, precipitation, humidity, pressure,
  condition code). Used for every historical game.
* Open-Meteo: forecasts for upcoming games, plus an ERA5 sample to put forecast
  wind on the station scale.
* ESPN scoreboard: current totals for upcoming games (the historical file stops
  at the last completed season).
"""
from __future__ import annotations

import gzip
import json
import re
import time
import unicodedata
from datetime import date, timedelta

import numpy as np
import pandas as pd
import requests

from .config import FIRST_SEASON, RAW, USER_AGENT
from .market import valid_odds

CFBFASTR = "https://raw.githubusercontent.com/sportsdataverse/cfbfastR-data/main"
METEOSTAT = "https://bulk.meteostat.net/v2"
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
ESPN = "https://site.api.espn.com/apis/site/v2/sports/football/college-football/scoreboard"
METEOSTAT_COLS = ["date", "hour", "temp", "dwpt", "rhum", "prcp", "snow", "wdir", "wspd", "wpgt", "pres", "tsun", "coco"]
HOURLY_VARS = ["temperature_2m", "relative_humidity_2m", "precipitation", "rain", "snowfall", "weather_code",
               "wind_speed_10m", "wind_direction_10m", "wind_gusts_10m", "surface_pressure"]

session = requests.Session()
session.headers["User-Agent"] = USER_AGENT


def _get(url, params=None, tries=5, timeout=120):
    for i in range(tries):
        try:
            r = session.get(url, params=params, timeout=timeout)
            if r.status_code == 429:
                time.sleep(65 * (i + 1))
                continue
            r.raise_for_status()
            return r
        except requests.RequestException:
            if i == tries - 1:
                raise
            time.sleep(5 * (i + 1))
    raise RuntimeError(url)


def download(url, dest, force=False):
    if dest.exists() and not force:
        return dest
    r = _get(url, timeout=600)
    tmp = dest.with_suffix(dest.suffix + ".part")
    tmp.write_bytes(r.content)
    tmp.replace(dest)
    return dest


# --------------------------------------------------------------------- cfbfastR-data
def current_season():
    today = date.today()
    return today.year if today.month >= 7 else today.year - 1


def fetch_cfbfastr(seasons=None):
    """Schedules and team info per season, plus the betting-lines file. Past seasons
    are cached; the current season's schedule is refreshed every run."""
    cur = current_season()
    d = RAW / "cfbfastr"
    for s in seasons or range(FIRST_SEASON, cur + 1):
        download(f"{CFBFASTR}/schedules/parquet/cfb_schedules_{s}.parquet", d / f"schedules_{s}.parquet", force=s == cur)
        download(f"{CFBFASTR}/team_info/parquet/cfb_team_info_{s}.parquet", d / f"team_info_{s}.parquet", force=s == cur)
    download(f"{CFBFASTR}/betting/parquet/cfb_line_odds.parquet", d / "line_odds.parquet")
    print(f"  cfbfastR-data: seasons {FIRST_SEASON}-{cur}", flush=True)


# --------------------------------------------------------------------- Meteostat
def stations():
    p = RAW / "meteostat" / "stations.json.gz"
    download(f"{METEOSTAT}/stations/lite.json.gz", p)
    rows = []
    for s in json.load(gzip.open(p)):
        inv = (s.get("inventory") or {}).get("hourly") or {}
        loc = s.get("location") or {}
        if inv.get("start") and loc.get("latitude") is not None:
            rows.append(dict(station=s["id"], lat=loc["latitude"], lon=loc["longitude"], elev=loc.get("elevation"),
                             h_start=inv["start"], h_end=inv["end"], name=(s.get("name") or {}).get("en")))
    return pd.DataFrame(rows)


def nearest_stations(venues: pd.DataFrame, st: pd.DataFrame, k=3, start="2008-01-01", end="2025-12-31"):
    """k nearest stations (great-circle km) whose hourly record spans the study window."""
    st = st[(st.h_start <= start) & (st.h_end >= end)].reset_index(drop=True)
    lat1, lon1 = np.radians(venues.lat.values)[:, None], np.radians(venues.lon.values)[:, None]
    lat2, lon2 = np.radians(st.lat.values)[None, :], np.radians(st.lon.values)[None, :]
    a = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    km = 6371 * 2 * np.arcsin(np.sqrt(a))
    idx = np.argsort(km, axis=1)[:, :k]
    out = []
    for i, vid in enumerate(venues.venue_id.values):
        for rank, j in enumerate(idx[i]):
            out.append(dict(venue_id=vid, rank=rank, station=st.station[j], km=km[i, j]))
    return pd.DataFrame(out)


def fetch_station_hourly(station_ids):
    d = RAW / "meteostat" / "hourly"
    d.mkdir(parents=True, exist_ok=True)
    for i, s in enumerate(sorted(set(station_ids))):
        download(f"{METEOSTAT}/hourly/{s}.csv.gz", d / f"{s}.csv.gz")
        if i % 25 == 0:
            print(f"  meteostat {i}/{len(set(station_ids))}", flush=True)


def load_station_hourly(station):
    p = RAW / "meteostat" / "hourly" / f"{station}.csv.gz"
    if not p.exists():
        return None
    h = pd.read_csv(p, header=None, names=METEOSTAT_COLS)
    h["ts"] = pd.to_datetime(h.date) + pd.to_timedelta(h.hour, unit="h")
    return h.set_index("ts")


# --------------------------------------------------------------------- Open-Meteo
def _om(url, lat, lon, day, kind):
    dest = RAW / "openmeteo" / kind / f"{lat:.3f}_{lon:.3f}_{day}.json"
    if dest.exists() and kind == "archive":
        return json.loads(dest.read_text())
    dest.parent.mkdir(parents=True, exist_ok=True)
    r = _get(url, dict(latitude=lat, longitude=lon, start_date=day, end_date=day, hourly=",".join(HOURLY_VARS),
                       temperature_unit="fahrenheit", wind_speed_unit="mph", precipitation_unit="inch", timezone="UTC"))
    dest.write_text(r.text)
    return r.json()


def om_archive(lat, lon, day):
    return _om(ARCHIVE_URL, lat, lon, day, "archive")


def om_forecast(lat, lon, day):
    return _om(FORECAST_URL, lat, lon, day, "forecast")


# --------------------------------------------------------------------- ESPN (live totals)
def espn_week_odds(days_ahead=8):
    """Current DraftKings total and over/under prices for upcoming FBS games, via ESPN.
    ESPN sometimes refuses scripted clients (403); then this returns no rows and the
    board falls back to The Odds API (if a key is set) or shows games without a price."""
    def num(x):
        try:
            return float(str(x).replace("o", "").replace("u", ""))
        except (TypeError, ValueError):
            return np.nan

    rows = []
    for k in range(days_ahead + 1):
        day = (date.today() + timedelta(days=k)).strftime("%Y%m%d")
        try:
            r = session.get(ESPN, params=dict(dates=day, groups=80, limit=400), timeout=30)
            status = r.status_code
        except requests.RequestException as e:
            r, status = None, type(e).__name__
        if status != 200:
            print(f"  ESPN unavailable ({status}); no ESPN prices this run", flush=True)
            return pd.DataFrame(columns=["game_id", "mkt_total", "mkt_under", "mkt_over", "line_src", "quote_utc"])
        for e in r.json().get("events", []):
            c = e["competitions"][0]
            o = (c.get("odds") or [{}])[0]
            tot = o.get("total") or {}
            cur_u, cur_o = (tot.get("under") or {}).get("close") or {}, (tot.get("over") or {}).get("close") or {}
            rows.append(dict(game_id=int(e["id"]), mkt_total=num(o.get("overUnder")),
                             mkt_under=num(cur_u.get("odds")), mkt_over=num(cur_o.get("odds")),
                             line_src=(o.get("provider") or {}).get("name"),
                             quote_utc=pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%dT%H:%M:%SZ")))
    return pd.DataFrame(rows).drop_duplicates("game_id")


ODDS_API = "https://api.the-odds-api.com/v4/sports/americanfootball_ncaaf/odds"
# <= 10 books = 1 region = 1 credit. All on the free plan. Rule B prices at RULE_BOOKS (first listed wins);
# the rest are logged for line shopping.
LIVE_BOOKS = ("pinnacle", "draftkings", "lowvig", "betonlineag", "fanduel", "betmgm", "betrivers", "bovada",
              "espnbet", "hardrockbet")
RULE_BOOKS = ("pinnacle", "draftkings")
LAST_UNMAPPED: list[str] = []    # odds-feed team names the last call couldn't match (for the run record)


def norm_team(name: str) -> str:
    """Match team names across sources that differ only in accents or punctuation
    ("San José State" / "San Jose State", "Hawai'i" / "Hawaii", "Ragin' Cajuns" / "Ragin Cajuns")."""
    ascii_ = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return " ".join(re.sub(r"[^a-z0-9 ]", "", ascii_.lower()).split())


def odds_api_totals(team_names: dict):
    """Live CFB totals from The Odds API (1 credit per call) at LIVE_BOOKS. Rule B's price is
    Pinnacle when it lists the game, else DraftKings; `best_under` is the best under price any
    logged book offers at that same total. `team_names` maps "School Mascot" -> cfbfastR school.
    Every response is written to data/raw/oddsapi/live/ before it is parsed. Returns an empty
    frame when no key is set, quota.check() says credits are too low, or the call fails."""
    from . import quota
    from .notify import _env
    key = _env("ODDS_API_KEY")
    cols = ["home_team", "away_team", "commence_utc", "mkt_total", "mkt_under", "mkt_over", "line_src", "quote_utc",
            "quote_update", "best_under", "best_under_book", "best_line", "best_line_under", "best_line_book"]
    empty = pd.DataFrame(columns=cols)
    if not key:
        return empty
    why = quota.check()
    if why:
        print(f"  {why}", flush=True)
        return empty
    try:
        r = session.get(ODDS_API, params=dict(apiKey=key, bookmakers=",".join(LIVE_BOOKS), markets="totals",
                                              oddsFormat="american", dateFormat="iso"), timeout=60)
    except requests.RequestException as e:
        print(f"  Odds API unreachable ({type(e).__name__})", flush=True)
        return empty
    quota.record(r, "cfb-weather")
    if r.status_code != 200:
        print(f"  Odds API unavailable ({r.status_code})", flush=True)
        return empty
    stamp = pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%dT%H:%M:%SZ")
    # cache first: keep every response, as the NFL client does
    dest = RAW / "oddsapi" / "live" / f"{stamp.replace(':', '')}.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps({"snapshot_utc": stamp, "credits_last": r.headers.get("x-requests-last"),
                                "credits_remaining": r.headers.get("x-requests-remaining"), "data": r.json()}))
    return parse_odds_api(r.json(), team_names, stamp)[cols]


def parse_odds_api(events, team_names, stamp, min_odds=-115):
    """One row per event: the rule's quote, the best under price at that same total, and the best line
    (the highest total any logged book offers the under at, at `min_odds` or better; logging only).
    The rule's quote comes from the first of RULE_BOOKS with a complete under quote (a total and a price)."""
    lookup = {norm_team(k): v for k, v in team_names.items()}
    LAST_UNMAPPED[:] = sorted({n for ev in events for n in (ev["home_team"], ev["away_team"])
                               if norm_team(n) not in lookup})
    if LAST_UNMAPPED:
        print(f"  odds feed team names with no match (their games arrive unpriced): {LAST_UNMAPPED}", flush=True)
    rows = []
    for ev in events:
        quotes, updated = {}, {}
        for b in ev.get("bookmakers", []):
            mk = next((m for m in b.get("markets", []) if m["key"] == "totals"), None)
            if mk:
                quotes[b["key"]] = {x["name"].lower(): x for x in mk["outcomes"]}
                updated[b["key"]] = mk.get("last_update") or b.get("last_update") or ""
        unders = {k: (q["under"]["point"], q["under"]["price"]) for k, q in quotes.items()
                  if q.get("under", {}).get("point") is not None and valid_odds(q.get("under", {}).get("price"))}
        if not unders:
            continue
        # no rule book quoting: the game has no rule price, and its best line is still logged
        rule = next((k for k in RULE_BOOKS if k in unders), None)
        o = quotes.get(rule, {})
        total = o.get("under", {}).get("point", np.nan)
        same = [(price, k) for k, (point, price) in unders.items() if point == total]
        best = max(same) if same else (np.nan, "")
        lines = [(point, price, k) for k, (point, price) in unders.items() if price >= min_odds]
        top = max(lines) if lines else (np.nan, np.nan, "")
        rows.append(dict(home_team=lookup.get(norm_team(ev["home_team"])),
                         away_team=lookup.get(norm_team(ev["away_team"])),
                         commence_utc=ev["commence_time"], mkt_total=total,
                         mkt_under=o.get("under", {}).get("price", np.nan),
                         mkt_over=o.get("over", {}).get("price", np.nan), line_src=rule or "", quote_utc=stamp,
                         quote_update=updated.get(rule, ""), best_under=best[0], best_under_book=best[1],
                         best_line=top[0], best_line_under=top[1], best_line_book=top[2]))
    return pd.DataFrame(rows, columns=["home_team", "away_team", "commence_utc", "mkt_total", "mkt_under", "mkt_over",
                                       "line_src", "quote_utc", "quote_update", "best_under", "best_under_book",
                                       "best_line", "best_line_under", "best_line_book"])
