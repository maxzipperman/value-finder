"""Hand-check the MOS replay's run selection on real NFL games (issue #40, full 2004-25 run).

The NFL half of cfb-weather/scripts/mos_hand_check.py. The NFL rule reads its forecast at the
kickoff instant, so each lead is one interpolated value. The games cover a 1 PM Sunday kickoff
that lead 3's run reaches, late-afternoon, Sunday-night, Monday-night and Thursday-night
kickoffs, Christmas, New Year's Day, the Sunday summer time ends, 13 kt (14.96 mph, no signal),
and both next-nearest fallbacks: Washington 2004-09, where College Park (KCGS) has no runs, falls
back to Andrews (KADW); Baltimore, where Inner Harbor (KDMH) has runs but no wind forecast, falls
back to BWI (KBWI). The numbers were checked by hand against this log, and tests/test_mos.py pins them.

It also writes the MOS rows behind each game to tests/fixtures/ (the station used, and a nearer
station that has runs but no wind, each marked in the `station` column), so the test runs without
the cache. Reads data/processed/mos_replay.parquet and the MOS cache; fetches nothing.

    python scripts/mos_hand_check.py
"""
from __future__ import annotations

import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

from nflweather import mos
from nflweather.config import OUT, PROC, ROOT

FIXTURES = ROOT / "tests" / "fixtures"
HOW = "kickoff"         # the NFL rule reads its forecast at the kickoff instant
GAMES = [
    ("2025_01_CIN_CLE", "1 PM Sunday: lead 3's run reaches it; fires at lead 3 only"),
    ("2024_01_DAL_CLE", "4:25 PM Sunday: lead 3's run ends before kickoff"),
    ("2023_01_DAL_NYG", "Sunday night: 8:20 PM Eastern is Monday in UTC"),
    ("2022_02_TEN_BUF", "Monday night: lead 1 is Sunday's run"),
    ("2019_06_NYG_NE", "Thursday night; fires at lead 2 and lead 1"),
    ("2021_16_CLE_GB", "Christmas Saturday, winter time"),
    ("2019_09_WAS_BUF", "the Sunday summer time ends; lead 3's last step is kickoff itself; fires"),
    ("2016_17_NE_MIA", "New Year's Day: 13 kt = 14.96 mph at leads 1 and 2 (no); fires at lead 3"),
    ("2004_16_DEN_TEN", "Christmas night 2004, the first season"),
    ("2009_06_KC_WAS", "next-nearest station: College Park has no runs before 2010, so Andrews"),
    ("2024_02_LV_BAL", "next-nearest station: Baltimore Inner Harbor has runs but no wind forecast, so BWI"),
]


def trim(runs: pd.DataFrame, kick_utc) -> pd.DataFrame:
    """The rows the selection can touch: runs from 4 days before kickoff day through kickoff day, each
    run's steps from 12 h before kickoff to 15 h after, plus its last step (so its reach is kept)."""
    kd = mos.kick_date(kick_utc)
    k0 = pd.Timestamp(kick_utc).tz_convert("UTC").tz_localize(None).floor("h")
    r = runs[(runs.runtime >= pd.Timestamp(kd - timedelta(days=4))) & (runs.runtime < pd.Timestamp(kd + timedelta(days=1)))]
    near = r[(r.ftime >= k0 - pd.Timedelta(hours=12)) & (r.ftime <= k0 + pd.Timedelta(hours=15))]
    last = r.sort_values("ftime").groupby("runtime").tail(1)
    return pd.concat([near, last]).drop_duplicates(["runtime", "ftime"]).sort_values(["runtime", "ftime"])


def main():
    d = pd.read_parquet(PROC / "mos_replay.parquet").set_index("game_id")
    smap = pd.read_csv(PROC / "mos_station_map.csv")
    lines = ["Hand check of the MOS run selection (no lookahead), NFL. Lead L must use a run from the kickoff's",
             "Eastern date minus L, published (run time + 5 h) before the last alert run that day (7:30 PM Pacific).",
             "Runs from the kickoff date itself are never used. The wind is read at the kickoff instant. "
             "Knots x 1.150779 = mph.", ""]
    rows, games = [], []
    for gid, why in GAMES:
        r = d.loc[gid]
        ranks = smap[smap.stadium_key == r.stadium_key].sort_values("rank")
        station = r.mos_station or ranks.icao.iloc[0]
        rank = int(r.mos_rank) if r.mos_station else 0
        runs = trim(mos.load_station(station), r.start_utc)
        cols = ["game_id", "station", "runtime", "ftime", "wsp"]
        rows.append(runs.assign(game_id=gid, station=station)[cols])
        games.append(dict(game_id=gid, station=station, start_utc=r.start_utc, how=HOW))
        lines.append(f"{gid} {r.away_team} at {r.home_team}, {r.season} week {r.week} ({why})")
        lines.append(f"  station {station}, rank {rank} of " + ", ".join(f"{x.icao} {x.km:.1f} km" for x in ranks.itertuples()))
        kd = mos.kick_date(r.start_utc)
        for x in ranks.itertuples():
            if x.icao == station and r.mos_station:
                break
            p = mos.cached_cover(x.icao, pd.Timestamp(kd - timedelta(days=3)),
                                 pd.Timestamp(kd - timedelta(days=1)) + pd.Timedelta(hours=18))
            line = (f"  {'nearer station' if r.mos_station else 'station'} {x.icao}: "
                    f"{mos.file_status(p) if p else 'not downloaded'} ({p.name if p else 'no file'})")
            near = trim(mos.load_station(x.icao), r.start_utc) if p else mos.load_station(x.icao).iloc[0:0]
            if len(near):         # runs but no forecast for this game: kept in the fixture, to show why it was skipped
                rows.append(near.assign(game_id=gid, station=x.icao)[cols])
                line += "; " + ", ".join(f"lead {n}: {mos.lead_status(near, r.start_utc, n, HOW)}" for n in mos.LEADS)
            lines.append(line)
        lines += mos.explain_selection(runs, r.start_utc, how=HOW)
        rep = ", ".join(f"lead {n} {r[f'mos{n}_mph']:.2f}" if pd.notna(r[f"mos{n}_mph"]) else f"lead {n} none"
                        for n in mos.LEADS)
        lines += [f"  replay row (data/processed/mos_replay.parquet): {rep}; signal {bool(r.mos_signal)}", ""]
    FIXTURES.mkdir(parents=True, exist_ok=True)
    pd.concat(rows).to_csv(FIXTURES / "mos_hand_checked_runs.csv", index=False)
    pd.DataFrame(games).to_csv(FIXTURES / "mos_hand_checked_games.csv", index=False)
    lines.append(f"{len(GAMES)} games; fixture rows: {sum(map(len, rows))} "
                 f"(tests/fixtures/mos_hand_checked_runs.csv)")
    text = "\n".join(lines)
    (OUT / "mos_hand_check.log").write_text(text + "\n")
    print(text)


if __name__ == "__main__":
    main()
