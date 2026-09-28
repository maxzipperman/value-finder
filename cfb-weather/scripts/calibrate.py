"""Fit the frozen forecast-to-station calibration (seasons <= 2023 only).

Station wind (airport anemometer) and model grid wind differ in scale. Rule B's
15 mph trigger is on the station scale, so live forecasts are mapped onto it with
station = a + b * ERA5, fit on a random sample of historical outdoor games.

    python scripts/calibrate.py        # ~600 Open-Meteo archive calls, ~8 minutes
"""
import json
import sys
import time
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd

from cfbweather import fetch
from cfbweather.config import PROC
from cfbweather.weather import summarize

CAL_LAST_SEASON = 2023
path = PROC / "calibration.json"
if path.exists() and json.loads(path.read_text()).get("frozen"):
    sys.exit(f"{path} is frozen; delete it to refit deliberately")
g = pd.read_parquet(PROC / "games.parquet")
g = g[(g.wx_src == "station") & g.season.between(2016, CAL_LAST_SEASON)].sample(600, random_state=0)
rows = []
for i, r in enumerate(g.itertuples()):
    day = pd.Timestamp(r.start_utc).tz_convert("UTC").strftime("%Y-%m-%d")
    w = summarize(fetch.om_archive(r.lat, r.lon, day), r.start_utc)
    if w:
        rows.append(dict(game_id=r.game_id, station_wind=r.wx_wind, station_temp=r.wx_temp, **w))
    if i % 100 == 0:
        print(f"  {i}/600", flush=True)
    time.sleep(0.8)
d = pd.DataFrame(rows).dropna(subset=["om_wind", "station_wind"])
ws, wi = np.polyfit(d.om_wind, d.station_wind, 1)
ts, ti = np.polyfit(d.om_temp, d.station_temp, 1)
cal = dict(wind_slope=float(ws), wind_intercept=float(wi), temp_slope=float(ts), temp_intercept=float(ti),
           wind_r=float(np.corrcoef(d.om_wind, d.station_wind)[0, 1]), n=int(len(d)),
           fit_seasons=f"2016-{CAL_LAST_SEASON}", frozen=True, created=date.today().isoformat())
path.write_text(json.dumps(cal, indent=1))
print(json.dumps(cal, indent=1))
