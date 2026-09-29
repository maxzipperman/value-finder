"""Map every CFB venue with coordinates to its nearest GFS MOS stations (issue #40).

MOS stations come from the NWS MDL GFS MOS station list (cfbweather/mos.station_table). Up to
three stations within 40 km of each venue are kept, nearest first; a venue with none is left
out, not guessed. Each row also names the venue's nearest observation station (the Meteostat
station the observed-wind backtests used, data/processed/station_map.parquet rank 0) and
whether it is the same airport.

Writes data/processed/mos_station_map.csv. Needs the Meteostat station list for the ICAO ids
of the observation stations (data/raw/meteostat/stations.json.gz, from scripts/fetch_data.py).

    python scripts/mos_stations.py
"""
from __future__ import annotations

import gzip
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

from cfbweather import mos
from cfbweather.config import PROC, RAW

OUT = PROC / "mos_station_map.csv"


def meteostat_icao() -> dict:
    p = RAW / "meteostat" / "stations.json.gz"
    return {s["id"]: ((s.get("identifiers") or {}).get("icao") or "") for s in json.load(gzip.open(p))}


def eligible(g: pd.DataFrame) -> pd.Series:
    """FBS-involved, outdoor, venue coordinates, known kickoff, a closing total and a final score."""
    fbs = g.home_division.astype(str).str.lower().eq("fbs") | g.away_division.astype(str).str.lower().eq("fbs")
    return (fbs & ~g.dome.astype(bool) & g.lat.notna() & g.lon.notna() & ~g.tbd.astype(bool)
            & g.total.notna() & g.close_total.notna())


def main():
    g = pd.read_parquet(PROC / "games.parquet")
    g["eligible"] = eligible(g)
    v = (g[g.lat.notna()].groupby("venue_id")
         .agg(venue=("venue", "last"), lat=("lat", "first"), lon=("lon", "first"), dome=("dome", "first"),
              eligible_games=("eligible", "sum"))
         .reset_index())
    v["venue_key"] = v.venue_id.astype(int)
    near = mos.nearest_mos(v, mos.station_table(), k=3)
    sm = pd.read_parquet(PROC / "station_map.parquet")
    obs = sm[sm["rank"] == 0][["venue_id", "station", "km"]].rename(columns={"station": "obs_station", "km": "obs_km"})
    icao = meteostat_icao()
    obs["obs_icao"] = obs.obs_station.map(icao).fillna("")
    m = v.merge(near, left_on="venue_key", right_on="venue_key").merge(obs, on="venue_id", how="left")
    m["same_as_obs"] = m.icao.eq(m.obs_icao)
    m["obs_km"] = m.obs_km.round(2)
    m["venue_id"] = m.venue_id.astype(int)
    cols = ["venue_id", "venue", "lat", "lon", "dome", "eligible_games", "rank", "icao", "km", "mos_name", "mos_state",
            "mos_lat", "mos_lon", "obs_station", "obs_icao", "obs_km", "same_as_obs"]
    m = m[cols].sort_values(["venue_id", "rank"])
    m.to_csv(OUT, index=False)

    outdoor = v[~v.dome.astype(bool)]
    mapped = set(m.venue_id)
    left_out = outdoor[~outdoor.venue_id.isin(mapped)]
    r0 = m[(m["rank"] == 0) & ~m.dome.astype(bool)]
    print(f"venues with coordinates: {len(v)} ({len(outdoor)} outdoor, "
          f"{int(outdoor.eligible_games.gt(0).sum())} with eligible games)")
    print(f"outdoor venues with a MOS station within {mos.MAX_KM:.0f} km: {len(outdoor) - len(left_out)}; "
          f"left out: {len(left_out)} ({int(left_out.eligible_games.sum())} eligible games)")
    print(f"nearest MOS station: median {r0.km.median():.1f} km, max {r0.km.max():.1f} km; "
          f"same airport as the observation station: {int(r0.same_as_obs.sum())} of {len(r0)}")
    if len(left_out):
        print("left out:", "; ".join(f"{r.venue} ({int(r.eligible_games)} games)" for r in left_out.itertuples()))
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
