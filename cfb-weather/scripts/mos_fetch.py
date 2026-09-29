"""Download the GFS MOS runs the CFB replay needs from the Iowa Environmental Mesonet (issue #40).

One request per (MOS station, season): every run from 3 days before the station's first
eligible kickoff to 1 day before its last (cfbweather/mos.season_windows). A season in which
the nearest MOS station returned nothing is retried at the next-nearest one within 40 km.

Cache-first and resumable: responses land in data/raw/mos/ (a symlink to
~/.cache/value-finder/mos) before they are parsed, and a rerun skips every window already
cached. Polite: one request every 7 s at most, a project User-Agent, backing off on errors.
Free, no key.

    python scripts/mos_fetch.py --seasons 2023-2025     # the validation sample
    python scripts/mos_fetch.py                         # 2006-2025
    python scripts/mos_fetch.py --plan                  # count the requests, fetch nothing
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

from cfbweather import mos
from cfbweather.config import PROC

SEASONS = (2006, 2025)


def parse_seasons(s: str | None) -> tuple[int, int]:
    if not s:
        return SEASONS
    a, _, b = s.partition("-")
    return int(a), int(b or a)


def games_with_stations(seasons=SEASONS, rank=0) -> pd.DataFrame:
    """Eligible games (scripts/mos_stations.eligible) with the venue's rank-`rank` MOS station."""
    from mos_stations import eligible
    g = pd.read_parquet(PROC / "games.parquet")
    g = g[eligible(g) & g.season.between(*seasons)]
    m = pd.read_csv(PROC / "mos_station_map.csv")
    m = m[m["rank"] == rank][["venue_id", "icao", "km"]]
    return g.merge(m, on="venue_id", how="inner")


def run_windows(w: pd.DataFrame, log) -> list:
    """Fetch each window (skipping cached ones); returns [(icao, season, rows, path)]."""
    todo = [r for r in w.itertuples() if mos.cached_cover(r.icao, r.sts, r.ets) is None]
    log(f"  {len(w)} windows, {len(todo)} not cached; at least {len(todo) * mos.MIN_INTERVAL_S / 60:.0f} min "
        f"at one request every {mos.MIN_INTERVAL_S:.0f} s (IEM's rate limit sets the real pace)")
    t0, failed = time.time(), []
    for i, r in enumerate(todo, 1):
        try:
            mos.fetch_runs(r.icao, r.sts, r.ets, log=log)
        except mos.RateLimited as e:          # keep going; a rerun picks it up
            failed.append(str(e))
            log(f"  FAILED {e}")
        if i % 25 == 0 or i == len(todo):
            el = time.time() - t0
            log(f"  {i}/{len(todo)} fetched, {el / 60:.1f} min, about {(len(todo) - i) * el / i / 60:.0f} min left")
    if failed:
        log(f"  {len(failed)} windows failed; rerun the same command to fetch them")
    out = []
    for r in w.itertuples():
        p = mos.cached_cover(r.icao, r.sts, r.ets)
        out.append((r.icao, r.season, len(mos.read_file(p)) if p else 0, p))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seasons", help="e.g. 2023-2025 (default 2006-2025)")
    ap.add_argument("--plan", action="store_true", help="count the requests; fetch nothing")
    args = ap.parse_args()
    seasons = parse_seasons(args.seasons)

    def log(msg):
        print(time.strftime("%Y-%m-%d %H:%M:%S ") + msg, flush=True)

    g0 = games_with_stations(seasons, rank=0)
    w0 = mos.season_windows(g0)
    log(f"CFB MOS fetch, seasons {seasons[0]}-{seasons[1]}: {len(g0)} games at {g0.icao.nunique()} stations, "
        f"{len(w0)} (station, season) windows")
    if args.plan:
        todo = sum(mos.cached_cover(r.icao, r.sts, r.ets) is None for r in w0.itertuples())
        log(f"  not cached: {todo} requests, about {todo * mos.MIN_INTERVAL_S / 60:.0f} min")
        return
    res = run_windows(w0, log)
    empty = {(icao, s) for icao, s, n, _ in res if n == 0}
    if empty:
        log(f"  empty at the nearest station: {sorted(empty)}; trying the next-nearest within {mos.MAX_KM:.0f} km")
        g1 = games_with_stations(seasons, rank=1)
        near0 = g0.set_index("game_id").icao
        g1 = g1[[(near0.get(gid), s) in empty for gid, s in zip(g1.game_id, g1.season)]]
        if len(g1):
            res1 = run_windows(mos.season_windows(g1), log)
            log(f"  next-nearest: {sum(n > 0 for _, _, n, _ in res1)} of {len(res1)} windows have runs")
    rows = sum(n for _, _, n, _ in res)
    log(f"done: {len(res)} windows, {rows:,} forecast rows; {len(empty)} empty at the nearest station")


if __name__ == "__main__":
    main()
