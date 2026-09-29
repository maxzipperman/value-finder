"""Download CollegeFootballData (lines by sportsbook with openers, team box scores, returning
production, talent; optionally player box scores) and build the processed tables.

    python scripts/fetch_cfbd.py plan                                   # free: how many calls
    python scripts/fetch_cfbd.py pull --confirm                         # 2014-2025, ~250 calls
    python scripts/fetch_cfbd.py pull --confirm --players --max-calls 500
    python scripts/fetch_cfbd.py build                                  # cache -> data/processed/cfbd_*.parquet
                                                                        # (player box -> data/raw/cfbd/, too big for git)

The free tier allows 1,000 calls a month. Everything is cached under data/raw/cfbd/, so reruns
cost nothing; only uncached calls count against --max-calls.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cfbweather import cfbd
from cfbweather.config import PROC

ap = argparse.ArgumentParser()
ap.add_argument("cmd", choices=["plan", "pull", "build"])
ap.add_argument("--seasons", default="2014-2025", help="e.g. 2014-2025 or 2023,2024")
ap.add_argument("--players", action="store_true", help="also pull player box scores (1 call per week)")
ap.add_argument("--max-calls", type=int, default=300)
ap.add_argument("--confirm", action="store_true")
a = ap.parse_args()

if "-" in a.seasons:
    lo, hi = (int(x) for x in a.seasons.split("-"))
    seasons = list(range(lo, hi + 1))
else:
    seasons = [int(x) for x in a.seasons.split(",")]

if a.cmd == "plan":
    total, todo = cfbd.plan(seasons, a.players)
    print(f"{total} calls for {seasons[0]}-{seasons[-1]}{' with player box scores' if a.players else ''}; "
          f"{len(todo)} not cached yet")
elif a.cmd == "pull":
    n = cfbd.pull(seasons, a.players, a.max_calls, a.confirm)
    print(f"done: {n} calls made")
else:
    out = {"cfbd_lines": cfbd.lines_table(), "cfbd_team_box": cfbd.team_box_table(),
           "cfbd_returning": cfbd.season_table("/player/returning"), "cfbd_talent": cfbd.season_table("/talent")}
    for name, df in out.items():
        if len(df):
            df.to_parquet(PROC / f"{name}.parquet", index=False)
        print(f"  {name}: {len(df):,} rows")
    players = cfbd.player_box_table()          # large: kept out of git, under data/raw
    if len(players):
        players.to_parquet(cfbd.CACHE / "cfbd_player_box.parquet", index=False)
        print(f"  cfbd_player_box (data/raw/cfbd, not committed): {len(players):,} rows")
