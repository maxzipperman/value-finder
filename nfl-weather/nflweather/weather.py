"""Game-level weather features."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .fetch import load_hourly
from .stadiums import resolve_stadium


def wind_chill(temp_f, wind_mph):
    """NWS wind chill (the thesis formula). Defined only for T <= 50F and
    V > 3 mph; otherwise the air temperature is returned."""
    t = np.asarray(temp_f, dtype=float)
    v = np.asarray(wind_mph, dtype=float)
    vp = np.power(np.clip(v, 0, None), 0.16)
    wc = 35.74 + 0.6215 * t - 35.75 * vp + 0.4275 * t * vp
    return np.where((t <= 50) & (v > 3), wc, t)


def _kick_hour(gametime):
    try:
        h, m = str(gametime).split(":")[:2]
        return int(h) + int(m) / 60
    except ValueError:
        return 13.0


WEATHER_COLS = ("om_temp", "om_wind", "om_gust", "om_rh", "om_feels", "om_wind_dir", "om_wind_game", "om_gust_game",
                "om_temp_game", "om_precip", "om_rain", "om_snow", "om_wcode", "om_precip_day")   # summarize_hourly's keys


def summarize_hourly(h: pd.DataFrame, kick: float) -> dict:
    """Kickoff values (linear interpolation) and in-game aggregates.
    Open-Meteo precipitation at hour H is the total for H-1..H, so the game
    window for accumulations is the four hours after kickoff."""
    h = h.set_index("hour")
    k0 = int(np.floor(kick))
    frac = kick - k0
    k1 = min(k0 + 1, 23)

    def at_kick(col):
        a, b = h.at[k0, col], h.at[k1, col]
        if pd.isna(a) or pd.isna(b):
            return a if pd.notna(a) else b
        return a + (b - a) * frac

    win = h.loc[k0:min(k0 + 3, 23)]
    acc = h.loc[min(k0 + 1, 23):min(k0 + 4, 23)]
    return dict(
        om_temp=at_kick("temperature_2m"),
        om_wind=at_kick("wind_speed_10m"),
        om_gust=at_kick("wind_gusts_10m"),
        om_rh=at_kick("relative_humidity_2m"),
        om_feels=at_kick("apparent_temperature"),
        om_wind_dir=h.at[k0, "wind_direction_10m"],
        om_wind_game=win.wind_speed_10m.mean(),
        om_gust_game=win.wind_gusts_10m.max(),
        om_temp_game=win.temperature_2m.mean(),
        om_precip=acc.precipitation.sum(),
        om_rain=acc.rain.sum(),
        om_snow=acc.snowfall.sum(),
        om_wcode=acc.weather_code.max(),
        om_precip_day=h.precipitation.sum(),
    )


def game_weather(games: pd.DataFrame, kind="openmeteo") -> pd.DataFrame:
    rows = []
    for g in games.itertuples(index=False):
        if g.roof in ("dome", "closed"):
            continue
        key = resolve_stadium(g.stadium_id, g.stadium)
        h = load_hourly(key, g.gameday, kind)
        if h is None or h.temperature_2m.isna().all():
            continue
        rows.append(dict(game_id=g.game_id, **summarize_hourly(h, _kick_hour(g.gametime))))
    if not rows:      # no forecast for any game: keep the columns, so the board can still merge and log every game
        return pd.DataFrame({"game_id": pd.Series(dtype=object), **{c: pd.Series(dtype=float) for c in WEATHER_COLS}})
    return pd.DataFrame(rows)


def previous_forecasts(games: pd.DataFrame) -> pd.DataFrame:
    """Kickoff-time wind/temp and game-window precip/snow as forecast 1 and 3 days out."""
    rows = []
    for g in games.itertuples(index=False):
        if g.roof in ("dome", "closed"):
            continue
        h = load_hourly(resolve_stadium(g.stadium_id, g.stadium), g.gameday, "prevruns")
        if h is None or "wind_speed_10m_previous_day1" not in h or h.wind_speed_10m_previous_day1.isna().all():
            continue
        kick = _kick_hour(g.gametime)
        k0 = int(np.floor(kick))
        hh = h.set_index("hour")
        acc = hh.loc[min(k0 + 1, 23):min(k0 + 4, 23)]
        rows.append(dict(
            game_id=g.game_id,
            fc1_wind=hh.at[k0, "wind_speed_10m_previous_day1"], fc2_wind=hh.at[k0, "wind_speed_10m_previous_day2"],
            fc3_wind=hh.at[k0, "wind_speed_10m_previous_day3"], fc1_gust=hh.at[k0, "wind_gusts_10m_previous_day1"],
            fc1_temp=hh.at[k0, "temperature_2m_previous_day1"], fc3_temp=hh.at[k0, "temperature_2m_previous_day3"],
            fc1_precip=acc.precipitation_previous_day1.sum(), fc3_precip=acc.precipitation_previous_day3.sum(),
            fc1_snow=acc.snowfall_previous_day1.sum(), fc3_snow=acc.snowfall_previous_day3.sum()))
    return pd.DataFrame(rows)


def parse_gamebook_weather(s: pd.Series) -> pd.DataFrame:
    """Flags from the free-text NFL game-book weather string in the pbp data
    (e.g. 'Light Rain Temp: 45° F, Humidity: 90%, Wind: NW 13 mph')."""
    s = s.fillna("").str.lower()
    cond = s.str.split("temp:").str[0]
    # "20% chance of rain", "no rain", "rain expected later" are forecasts, not conditions
    cond = cond.str.replace(r"\d*\s*%?\s*chance (of|for) [a-z ]+|no (rain|snow)|(rain|snow) (later|expected|possible)", " ", regex=True)
    return pd.DataFrame({
        "gb_rain": cond.str.contains(r"rain|shower|drizzle|storm|wet", regex=True),
        "gb_snow": cond.str.contains(r"snow|flurr|sleet|wintry|blizzard", regex=True),
        "gb_humidity": pd.to_numeric(s.str.extract(r"humidity:\s*(\d+)")[0], errors="coerce"),
        "gb_text_wind": pd.to_numeric(s.str.extract(r"wind:\s*[a-z/\s.-]*?(\d+)")[0], errors="coerce"),
        "gb_weather_text": s.str.strip(),
    })
