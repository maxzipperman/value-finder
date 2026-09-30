"""How often would two F1 calls return the SAME historical snapshot? Kickoff times only (2020-22 seasons, no
prices, no results). Before about Sep 18, 2022 the Odds API kept a snapshot every 10 minutes (sharp-markets/docs/
PLAN.md line 49; strategy-research/odds-api-credits.md line 384) and returns the one at or before the requested time.
Where the 10-minute grid sits is not known here, so both offsets are counted."""
from datetime import datetime, timedelta, timezone

import pandas as pd

from markets.oddsapi import bulk

W = "/Users/maxzipperman/code/value-finder/.claude/worktrees/wf_4496c14b-845-1"
UTC = timezone.utc
END10 = datetime(2022, 9, 18, tzinfo=UTC)
PULL = {"schedule": "daily_close"}


def kicks():
    c = pd.read_parquet(f"{W}/cfb-weather/data/processed/games.parquet", columns=["season", "start_utc"])
    c = c[c.season.between(2020, 2022) & c.start_utc.notna()]
    n = pd.read_parquet(f"{W}/nfl-weather/data/processed/games.parquet")
    cols = [x for x in ("season", "gameday", "gametime") if x in n.columns]
    n = n[n.season.between(2020, 2022)][cols].dropna()
    nk = pd.to_datetime(n.gameday + " " + n.gametime).dt.tz_localize("America/New_York").dt.tz_convert("UTC")
    return {"CFB": pd.to_datetime(c.start_utc, utc=True), "NFL": nk}


def snap(t: datetime, offset: int) -> datetime:
    # the latest 10-minute grid point (minutes = offset mod 10) at or before t
    m = (t.minute - offset) % 10
    return t.replace(second=0, microsecond=0) - timedelta(minutes=m)


for sport, ks in kicks().items():
    times = set()
    for k in ks:
        times |= set(bulk.game_snapshots(k.to_pydatetime(), PULL))
    calls = sorted(t for t in times if t < END10)
    for offset in (0, 5):
        by = {}
        for i, t in enumerate(calls):
            by.setdefault(snap(t, offset), []).append(i)
        dup = {s: ix for s, ix in by.items() if len(ix) > 1}
        same_batch = sum(1 for ix in dup.values() if len({i // 50 for i in ix}) == 1)
        daily = sum(1 for s, ix in dup.items() if any(calls[i].hour == 16 and calls[i].minute == 0 for i in ix))
        print(f"{sport}: {len(calls):,} F1 calls before 2022-09-18; grid at :x{offset}: {len(dup):,} snapshots returned "
              f"to 2+ calls ({same_batch:,} with all copies in one 50-call batch; {daily:,} involve a 16:00 daily call)")
