"""Pull or refresh every raw input (cached; only new data downloads).

    python scripts/fetch_data.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cfbweather import fetch
from cfbweather.build import lines, schedules, venues
from cfbweather.config import FIRST_SEASON, PROC

print("cfbfastR-data schedules, team info, lines…", flush=True)
fetch.fetch_cfbfastr()

# venues that host games with a betting total (plus this season's home venues)
s = schedules()
tot = lines()
v = venues()
used = s[s.game_id.isin(tot.game_id) | (s.season == fetch.current_season())].venue_id.dropna().astype(int).unique()
v = v[v.venue_id.isin(used) & ~v.dome]
print(f"Meteostat stations for {len(v)} outdoor venues…", flush=True)
st = fetch.stations()
sm = fetch.nearest_stations(v, st, k=3, start=f"{FIRST_SEASON + 2}-01-01", end="2025-12-31")
sm.to_parquet(PROC / "station_map.parquet", index=False)
print(f"  median distance to nearest station {sm[sm['rank'] == 0].km.median():.1f} km; "
      f"{sm.station.nunique()} stations", flush=True)
fetch.fetch_station_hourly(sm[sm["rank"] <= 1].station)
print("done.", flush=True)
