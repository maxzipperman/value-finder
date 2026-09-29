"""Every player's weekly stat line, 1999 to date, from nflverse (issue #10 props, kicker props).
player_games.parquet covers only each team's QB, RB1 and WR1, picked without hindsight; this
table covers everyone, kickers included, for outcome joins. It does not pick roles.

    python scripts/build_player_week.py            # downloads missing seasons (about 25 MB, cached)

Writes data/processed/player_week.parquet (committed, so cloud sessions can use it).
Kicking points = 3 x field goals made + extra points made, the sportsbook definition.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

from nflweather import fetch
from nflweather.config import PROC, RAW

KEEP = ["player_id", "player_display_name", "position", "season", "week", "season_type", "game_id", "team",
        "opponent_team", "completions", "attempts", "passing_yards", "passing_tds", "passing_interceptions", "carries",
        "rushing_yards", "rushing_tds", "receptions", "targets", "receiving_yards", "receiving_tds", "fg_made", "fg_att",
        "fg_long", "pat_made", "pat_att"]

if not (RAW / "games.csv").exists():
    fetch.fetch_schedule()
fetch.fetch_player_stats()
frames = [pd.read_parquet(p)[lambda d: [c for c in KEEP if c in d]] for p in sorted((RAW / "player_stats").glob("*.parquet"))]
w = pd.concat(frames, ignore_index=True)
w["kicking_points"] = 3 * w.fg_made.fillna(0) + w.pat_made.fillna(0)
w.loc[w.fg_att.fillna(0) + w.pat_att.fillna(0) == 0, "kicking_points"] = pd.NA
for c in w.select_dtypes("float").columns:
    w[c] = pd.to_numeric(w[c], downcast="float")
w.to_parquet(PROC / "player_week.parquet", index=False)
print(f"{len(w):,} player-weeks, seasons {w.season.min()}-{w.season.max()}; "
      f"{int(w.kicking_points.notna().sum()):,} kicker-games; {(PROC / 'player_week.parquet').stat().st_size / 1e6:.1f} MB")
