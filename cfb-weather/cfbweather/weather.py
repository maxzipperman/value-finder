"""Kickoff-window summaries of Open-Meteo hourly data (requested in UTC)."""
from __future__ import annotations

import numpy as np
import pandas as pd


def summarize(js: dict, kick_utc: pd.Timestamp) -> dict | None:
    """Wind = mean over the kickoff hour and the next 3; temperature at kickoff;
    precipitation and snowfall summed over the 4 hours after kickoff (Open-Meteo
    accumulations at hour H cover H-1..H)."""
    if not js or "hourly" not in js:
        return None
    h = pd.DataFrame(js["hourly"])
    h["ts"] = pd.to_datetime(h.time)
    h = h.set_index("ts")
    k0 = pd.Timestamp(kick_utc).tz_convert("UTC").tz_localize(None).floor("h")
    if k0 not in h.index or pd.isna(h.at[k0, "temperature_2m"]):
        return None
    win = h.loc[k0:k0 + pd.Timedelta(hours=3)]
    acc = h.loc[k0 + pd.Timedelta(hours=1):k0 + pd.Timedelta(hours=4)]
    return dict(om_wind=win.wind_speed_10m.mean(), om_temp=h.at[k0, "temperature_2m"],
                om_precip=acc.precipitation.sum(), om_snow=acc.snowfall.sum(), om_gust=win.wind_gusts_10m.max())
