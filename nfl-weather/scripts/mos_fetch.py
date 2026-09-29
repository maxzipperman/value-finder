"""NFL side of the GFS MOS forecast replay (issue #40): map stadiums to MOS stations, then download.

1. Station map: every stadium that hosted an outdoor game gets up to three GFS MOS stations within
   40 km (nearest first) from the NWS MDL station list; stadiums with none (London, Munich,
   Mexico City, Sao Paulo, Frankfurt, ...) are left out, not guessed. Writes
   data/processed/mos_station_map.csv.
2. Download: one request per (MOS station, season) to the Iowa Environmental Mesonet, every run
   from 3 days before the station's first eligible kickoff to 1 day before its last. Cache-first
   and resumable in data/raw/mos/ (a symlink to ~/.cache/value-finder/mos, shared with
   cfb-weather), one request every 7 s at most, backing off on errors. Free, no key.

Eligible games: outdoor (roof "outdoors", as the Rule B evidence), 2004-2025, a closing total
(nflverse total_line) and a final score.

    python scripts/mos_fetch.py --map-only
    python scripts/mos_fetch.py [--seasons 2004-2025] [--plan]
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

from nflweather import mos
from nflweather.config import PROC

SEASONS = (2004, 2025)
MAP = PROC / "mos_station_map.csv"


def parse_seasons(s: str | None) -> tuple[int, int]:
    if not s:
        return SEASONS
    a, _, b = s.partition("-")
    return int(a), int(b or a)


def eligible_games(seasons=SEASONS) -> pd.DataFrame:
    g = pd.read_parquet(PROC / "games.parquet")
    g = g[(g.roof == "outdoors") & g.result.notna() & g.total_line.notna() & g.lat.notna()
          & g.season.between(*seasons)].copy()
    g["start_utc"] = (pd.to_datetime(g.gameday + " " + g.gametime).dt.tz_localize("America/New_York")
                      .dt.tz_convert("UTC"))
    return g


def build_map() -> pd.DataFrame:
    g = eligible_games()
    v = (g.groupby("stadium_key").agg(stadium=("stadium", "last"), lat=("lat", "first"), lon=("lon", "first"),
                                      eligible_games=("game_id", "size")).reset_index())
    v["venue_key"] = v.stadium_key
    near = mos.nearest_mos(v, mos.station_table(), k=3)
    m = v.merge(near, on="venue_key").drop(columns="venue_key")
    cols = ["stadium_key", "stadium", "lat", "lon", "eligible_games", "rank", "icao", "km", "mos_name", "mos_state",
            "mos_lat", "mos_lon"]
    m = m[cols].sort_values(["stadium_key", "rank"])
    m.to_csv(MAP, index=False)
    left = v[~v.stadium_key.isin(m.stadium_key)]
    r0 = m[m["rank"] == 0]
    print(f"stadiums with outdoor games 2004-25: {len(v)}; with a MOS station within {mos.MAX_KM:.0f} km: "
          f"{len(r0)} (median {r0.km.median():.1f} km, max {r0.km.max():.1f} km)")
    print("left out: " + "; ".join(f"{r.stadium} ({r.eligible_games} games)" for r in left.itertuples()))
    print(f"wrote {MAP}")
    return m


def games_with_stations(seasons=SEASONS, rank=0) -> pd.DataFrame:
    g = eligible_games(seasons)
    m = pd.read_csv(MAP)
    m = m[m["rank"] == rank][["stadium_key", "icao", "km"]]
    return g.merge(m, on="stadium_key", how="inner")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seasons", help="e.g. 2023-2025 (default 2004-2025)")
    ap.add_argument("--plan", action="store_true", help="count the requests; fetch nothing")
    ap.add_argument("--map-only", action="store_true", help="rebuild the station map and stop")
    args = ap.parse_args()
    if args.map_only or not MAP.exists():
        build_map()
        if args.map_only:
            return
    seasons = parse_seasons(args.seasons)

    def log(msg):
        print(time.strftime("%Y-%m-%d %H:%M:%S ") + msg, flush=True)

    g0 = games_with_stations(seasons, 0)
    w = mos.season_windows(g0)
    todo = [r for r in w.itertuples() if mos.cached_cover(r.icao, r.sts, r.ets) is None]
    log(f"NFL MOS fetch, seasons {seasons[0]}-{seasons[1]}: {len(g0)} games at {g0.icao.nunique()} stations, "
        f"{len(w)} (station, season) windows, {len(todo)} not cached "
        f"(at least {len(todo) * mos.MIN_INTERVAL_S / 60:.0f} min)")
    if args.plan:
        return
    failed = []
    t0 = time.time()
    for i, r in enumerate(todo, 1):
        try:
            mos.fetch_runs(r.icao, r.sts, r.ets, log=log)
        except mos.RateLimited as e:
            failed.append(str(e))
            log(f"  FAILED {e}")
        if i % 25 == 0 or i == len(todo):
            el = time.time() - t0
            log(f"  {i}/{len(todo)} fetched, {el / 60:.1f} min, about {(len(todo) - i) * el / i / 60:.0f} min left")
    empty = [(r.icao, r.season) for r in w.itertuples()
             if (p := mos.cached_cover(r.icao, r.sts, r.ets)) is not None and mos.read_file(p).empty]
    if empty:
        log(f"  empty at the nearest station: {empty}; trying the next-nearest")
        near0 = g0.set_index("game_id").icao
        g1 = games_with_stations(seasons, 1)
        g1 = g1[[(near0.get(gid), s) in set(empty) for gid, s in zip(g1.game_id, g1.season)]]
        for r in mos.season_windows(g1).itertuples() if len(g1) else []:
            try:
                mos.fetch_runs(r.icao, r.sts, r.ets, log=log)
            except mos.RateLimited as e:
                failed.append(str(e))
    log(f"done: {len(w)} windows; {len(empty)} empty at the nearest station; {len(failed)} failed "
        f"(rerun the same command to retry them)")


if __name__ == "__main__":
    main()
