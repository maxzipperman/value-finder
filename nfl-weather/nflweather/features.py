"""Weather feature definitions shared by the extended models, the betting
backtests and the weekly forecast tool.

Relative to the thesis:
* domes / closed roofs are not coded as 72F-and-calm; they get their own
  indicator and contribute nothing to the weather slopes;
* wind and air temperature enter separately (no wind chill double counting)
  and as bins, since effects are clearly non-linear;
* precipitation and snow during the game window are added (ERA5).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

RAIN_IN = 0.06   # inches over the 4 game hours; vs game-book "rain" text: ~50% recall, ~50% precision
SNOW_IN = 0.10   # inches of snowfall over the 4 game hours

WIND_TERMS = ["wind_10_14", "wind_15_19", "wind_20p"]
TEMP_TERMS = ["temp_le32", "temp_33_45", "temp_80p"]
PRECIP_TERMS = ["rain", "snow"]
ROOF_TERMS = ["indoor", "roof_open"]
BIN_TERMS = WIND_TERMS + TEMP_TERMS + PRECIP_TERMS + ROOF_TERMS
LIN_TERMS = ["wind_mph", "cold_deg", "heat_deg", "rain", "snow", "indoor", "roof_open"]

LABELS = {
    "wind_10_14": "Wind 10–14 mph", "wind_15_19": "Wind 15–19 mph", "wind_20p": "Wind 20+ mph",
    "temp_le32": "≤32°F", "temp_33_45": "33–45°F", "temp_80p": "80°F+",
    "rain": "Rain", "snow": "Snow", "indoor": "Dome / closed roof", "roof_open": "Retractable, open",
    "wind_mph": "Wind (per mph)", "cold_deg": "Per °F below 50", "heat_deg": "Per °F above 75",
}


def add_weather_features(d: pd.DataFrame) -> pd.DataFrame:
    d = d.copy()
    out = d.wx_src.isin(["gamebook", "era5"]).astype(int)
    w = d.wx_wind.fillna(0)
    t = d.wx_temp.fillna(65)
    d["outdoor"] = out
    d["wind_10_14"] = out * w.between(10, 15, inclusive="left")
    d["wind_15_19"] = out * w.between(15, 20, inclusive="left")
    d["wind_20p"] = out * (w >= 20)
    d["temp_le32"] = out * (t <= 32)
    d["temp_33_45"] = out * t.between(32, 45, inclusive="right")
    d["temp_80p"] = out * (t >= 80)
    snow = d.wx_snow.fillna(0) >= SNOW_IN
    d["snow"] = out * snow
    d["rain"] = out * ((d.wx_precip.fillna(0) >= RAIN_IN) & ~snow)
    d["wind_mph"] = out * w
    d["cold_deg"] = out * np.clip(50 - t, 0, None)
    d["heat_deg"] = out * np.clip(t - 75, 0, None)
    for c in ["wind_10_14", "wind_15_19", "wind_20p", "temp_le32", "temp_33_45", "temp_80p", "rain", "snow"]:
        d[c] = d[c].astype(int)
    return d


def wind_bin(w):
    return pd.cut(w, [-1, 4.99, 9.99, 14.99, 19.99, 200], labels=["0–4", "5–9", "10–14", "15–19", "20+"])
