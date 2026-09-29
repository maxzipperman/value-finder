"""Hand-check the MOS replay's run selection on real games (issue #40, full 2006-25 run).

For each game below (chosen to cover the edge cases: a noon kickoff, a late-night kickoff that
is the next day in UTC, a Thursday game, lead 3 reaching an early kickoff, a forecast just
under and just over 15 mph, a next-nearest station, a day whose 18Z run is missing, a January
bowl, the weekend summer time ends) this prints every MOS run cached for each day from three
days before kickoff through kickoff day, the run each lead takes, when that run was published
against the last alert run of its day, and the MOS steps and arithmetic behind the wind. The
numbers were checked by hand against this log, and tests/test_mos.py pins them.

It also writes the MOS rows behind each game to tests/fixtures/ (each run's steps from 12 hours
before kickoff to 15 hours after, plus its last step), so the test runs without the cache.

Reads data/processed/mos_replay.parquet and the MOS cache; fetches nothing.

    python scripts/mos_hand_check.py
"""
from __future__ import annotations

import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

from cfbweather import mos
from cfbweather.config import OUT, PROC, ROOT

FIXTURES = ROOT / "tests" / "fixtures"
HOW = "window"          # the CFB rule averages the kickoff hour and the next three
GAMES = [
    (401752822, "noon Saturday, summer time"),
    (401643858, "late kickoff: 11:59 PM Eastern is the next day in UTC; fires"),
    (401525461, "Thursday night"),
    (272510276, "11 AM kickoff: lead 3's run reaches it"),
    (282570248, "11 AM kickoff, lead 3, fires at every lead"),
    (272932711, "13 kt = 14.96 mph at lead 1 (no); 14 kt = 16.11 at lead 2 (fires)"),
    (273140265, "just over 15 mph at lead 1, winter time"),
    (263010120, "next-nearest station: College Park (KCGS) has no runs before 2010; fires"),
    (401635615, "next-nearest station: Chapel Hill (KIGX) has no runs after 2022; 8 PM EST is the next day in UTC"),
    (401247332, "Thanksgiving 2020: the 18Z run is missing, so lead 1 takes that day's 12Z run"),
    (401769076, "January title game"),
    (401760405, "the Saturday before summer time ends"),
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
    lines = ["Hand check of the MOS run selection (no lookahead), CFB. Lead L must use a run from the kickoff's",
             "Eastern date minus L, published (run time + 5 h) before the last alert run that day (7:30 PM Pacific).",
             "Runs from the kickoff date itself are never used. Wind: knots x 1.150779 = mph.", ""]
    rows, games = [], []
    for gid, why in GAMES:
        r = d.loc[gid]
        ranks = smap[smap.venue_id == r.venue_id].sort_values("rank")
        station = r.mos_station
        runs = trim(mos.load_station(station), r.start_utc)
        rows.append(runs.assign(game_id=gid)[["game_id", "runtime", "ftime", "wsp"]])
        games.append(dict(game_id=gid, station=station, start_utc=r.start_utc, how=HOW))
        lines.append(f"{gid} {r.away_team} at {r.home_team}, {r.season} week {r.week} ({why})")
        lines.append(f"  station {station}, {r.mos_km:.1f} km, rank {int(r.mos_rank)} of "
                     + ", ".join(f"{x.icao} {x.km:.1f} km" for x in ranks.itertuples()))
        for x in ranks[ranks["rank"] < r.mos_rank].itertuples():
            p = mos.cached_cover(x.icao, pd.Timestamp(mos.kick_date(r.start_utc) - timedelta(days=3)),
                                 pd.Timestamp(mos.kick_date(r.start_utc) - timedelta(days=1)) + pd.Timedelta(hours=18))
            lines.append(f"  nearer station {x.icao}: {mos.file_status(p) if p else 'not downloaded'} "
                         f"({p.name if p else 'no file'})")
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
