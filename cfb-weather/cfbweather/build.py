"""Assemble data/processed/games.parquet: one row per game with kickoff weather
from the nearest Meteostat station, the consensus closing total (median across
books), opening total where available, and the result."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .config import FIRST_SEASON, PROC, RAW
from .features import RAIN_IN, SNOW_IN
from .fetch import load_station_hourly

KMH_TO_MPH = 0.621371
RAIN_CODES = {7, 8, 9, 10, 11, 17, 18, 25, 26}
SNOW_CODES = {12, 13, 14, 15, 16, 19, 20, 21, 22}


def schedules():
    d = RAW / "cfbfastr"
    s = pd.concat([pd.read_parquet(p) for p in sorted(d.glob("schedules_*.parquet"))], ignore_index=True)
    # yearly files disagree on types (numbers stored as strings in some seasons)
    for c in ["home_points", "away_points", "home_post_win_prob", "away_post_win_prob", "home_pregame_elo",
              "away_pregame_elo", "home_postgame_elo", "away_postgame_elo", "excitement_index", "attendance", "week"]:
        if c in s:
            s[c] = pd.to_numeric(s[c], errors="coerce")
    for c in s.columns[s.dtypes == object]:
        if c not in ("start_date",):
            s[c] = s[c].where(s[c].isna(), s[c].astype(str))
    s["start_utc"] = pd.to_datetime(s.start_date, utc=True)
    s["tbd"] = s.start_time_tbd.astype(str).str.lower().isin(["true", "1", "1.0"])
    return s.drop_duplicates("game_id")


def venues():
    """Venue coordinates from team info (each team's home venue), newest season wins."""
    d = RAW / "cfbfastr"
    t = pd.concat([pd.read_parquet(p).assign(info_season=int(p.stem.split("_")[-1])) for p in sorted(d.glob("team_info_*.parquet"))])
    v = t.dropna(subset=["venue_id", "latitude", "longitude"]).sort_values("info_season")
    v = v.drop_duplicates("venue_id", keep="last")
    v = v.rename(columns={"latitude": "lat", "longitude": "lon"})
    v["venue_id"] = v.venue_id.astype(int)
    v["dome"] = v.dome.fillna(False).astype(bool)
    return v[["venue_id", "venue_name", "city", "state", "lat", "lon", "elevation", "grass", "dome", "timezone"]]


def lines():
    """Consensus closing and opening totals per game (median across books)."""
    b = pd.read_parquet(RAW / "cfbfastr" / "line_odds.parquet")
    b = b[(b.market_type == "total") & b.lines.notna()]
    per_book = b.groupby(["game_id", "book"]).agg(line=("lines", "median"), open_line=("opening_lines", "median")).reset_index()
    g = per_book.groupby("game_id").agg(close_total=("line", "median"), open_total=("open_line", "median"),
                                        n_books=("book", "nunique"), total_sd=("line", "std")).reset_index()
    pin = per_book[per_book.book.str.upper().str.contains("PINNACLE")].groupby("game_id").line.median().rename("pin_total")
    g = g.merge(pin, on="game_id", how="left")
    g["game_id"] = g.game_id.astype("int64")
    return g


def _window(h: pd.DataFrame, kick: pd.Timestamp):
    k0 = kick.floor("h").tz_localize(None)
    at = h.loc[k0] if k0 in h.index else None
    win = h.loc[k0:k0 + pd.Timedelta(hours=3)]
    acc = h.loc[k0 + pd.Timedelta(hours=1):k0 + pd.Timedelta(hours=4)]
    if at is None or pd.isna(at.temp) or pd.isna(at.wspd):
        return None
    codes = set(win.coco.dropna().astype(int))
    return dict(
        wx_temp=at.temp * 9 / 5 + 32,
        wx_wind=win.wspd.mean() * KMH_TO_MPH,
        wx_wind_kick=at.wspd * KMH_TO_MPH,
        wx_gust=win.wpgt.max() * KMH_TO_MPH if win.wpgt.notna().any() else np.nan,
        wx_wdir=at.wdir,
        wx_rh=at.rhum,
        wx_pres=at.pres,
        wx_precip=acc.prcp.sum() / 25.4 if acc.prcp.notna().any() else np.nan,
        wx_rain_code=int(bool(codes & RAIN_CODES)),
        wx_snow_code=int(bool(codes & SNOW_CODES)),
    )


def game_weather(g: pd.DataFrame, station_map: pd.DataFrame) -> pd.DataFrame:
    """Weather for each outdoor game from its venue's nearest station, falling back
    to the 2nd/3rd nearest when the nearest has no reading at kickoff."""
    need = g[~g.dome & ~g.tbd & g.lat.notna()][["game_id", "venue_id", "start_utc"]]
    sm = station_map.sort_values(["venue_id", "rank"])
    out = {}
    cache = {}
    for rank in (0, 1, 2):
        todo = need[~need.game_id.isin(out)]
        todo = todo.merge(sm[sm["rank"] == rank][["venue_id", "station", "km"]], on="venue_id")
        for st, grp in todo.groupby("station"):
            if st not in cache:
                cache[st] = load_station_hourly(st)
            h = cache[st]
            if h is None:
                continue
            for r in grp.itertuples():
                w = _window(h, r.start_utc)
                if w:
                    out[r.game_id] = dict(game_id=r.game_id, wx_station=st, wx_station_km=r.km, wx_station_rank=rank, **w)
        cache.clear()
    return pd.DataFrame(out.values())


def build(verbose=True):
    s = schedules()
    v = venues()
    g = s.merge(v, on="venue_id", how="left")
    g["dome"] = g.dome.fillna(False).astype(bool)
    g = g.merge(lines(), on="game_id", how="left")
    sm = pd.read_parquet(PROC / "station_map.parquet") if (PROC / "station_map.parquet").exists() else None
    if sm is not None:
        w = game_weather(g[g.season.between(FIRST_SEASON, 2025)], sm)
        g = g.merge(w, on="game_id", how="left")
    g["total"] = g.home_points + g.away_points
    g["result"] = g.home_points - g.away_points
    g["wx_src"] = np.where(g.dome, "indoor", np.where(g.get("wx_temp", pd.Series(np.nan, index=g.index)).notna(), "station", "missing"))
    g["roof"] = np.where(g.dome, "dome", "outdoors")
    # snow: a snow condition code during the game, or measurable precipitation at <= 33F
    precip = g.get("wx_precip", pd.Series(np.nan, index=g.index)).fillna(0)
    snowish = (g.get("wx_snow_code", 0) == 1) | ((precip >= SNOW_IN) & (g.get("wx_temp", 99) <= 33))
    g["wx_snow"] = np.where(snowish, np.maximum(precip, SNOW_IN), 0.0)
    g["wx_precip"] = precip
    g.to_parquet(PROC / "games.parquet", index=False)
    if verbose:
        played = g[g.home_points.notna() & g.season.le(2025)]
        print(f"  games {len(g):,}; played with a closing total {played.close_total.notna().sum():,}; "
              f"with station weather {int((g.wx_src == 'station').sum()):,}; indoor {int(g.dome.sum()):,}")
    return g
