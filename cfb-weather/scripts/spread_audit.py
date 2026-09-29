"""Audit the consensus home spread (issue #36): which (game, book) spread pairs build.home_spreads()
drops, by reason and season, and how the result agrees with CollegeFootballData's lines by sportsbook
(data/processed/cfbd_lines.parquet), which names home and away explicitly for 2014-25.

* Reference: the median CFBD spread across providers per game (negative = home favored, the same
  convention and the same home team as the schedules).
* Agreement: share of games with both spreads that are within 1 point, and within 3. Sign flips: one
  source favors the home team and the other the away team, by at least a point each.
* Coverage: played games with a closing total (games.parquet) where CFBD has a spread, and how many
  of those have a consensus home spread.
* Both versions are scored: home_spread as stored in data/processed/games.parquet, and a fresh
  home_spreads() from the raw lines with this code. They differ until games.parquet is rebuilt.

Needs the raw cfbfastR cache (Mac only). Run from cfb-weather/:
    .venv/bin/python scripts/spread_audit.py | tee output/spread_audit.log
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cfbweather.build import drop_table, home_spreads, schedule_teams, spread_pairs, team_names  # noqa: E402
from cfbweather.config import PROC, RAW  # noqa: E402

pd.set_option("display.width", 250, "display.max_columns", 40)

b = pd.read_parquet(RAW / "cfbfastr" / "line_odds.parquet")
b = b[(b.market_type == "spread") & b.lines.notna()]
print(f"spread rows with a line: {len(b):,}; without a game_id (can't join any game): {int(b.game_id.isna().sum()):,}")
b = b[b.game_id.notna()]
b = b.assign(game_id=b.game_id.astype("int64"))
homes, names = schedule_teams(), team_names()
_, pairs = spread_pairs(b, homes, names)
print("\n(game, book) spread pairs by status and season:")
print(drop_table(pairs).to_string())
fresh = home_spreads(b, homes, names, verbose=False).rename(columns={"home_spread": "fresh"})

g = pd.read_parquet(PROC / "games.parquet", columns=["game_id", "season", "close_total", "result", "home_spread"])
g = g.rename(columns={"home_spread": "stored"}).merge(fresh, on="game_id", how="left")
c = pd.read_parquet(PROC / "cfbd_lines.parquet")
ref = c[c.spread.notna()].groupby("game_id").spread.median().rename("cfbd").reset_index()
g = g.merge(ref, on="game_id", how="left")
g = g[g.season.between(2014, 2025) & g.close_total.notna() & g.result.notna()]


def score(g, col):
    has_ref = g[g.cfbd.notna()]
    d = has_ref[has_ref[col].notna()]
    diff = (d[col] - d.cfbd).abs()
    flip = (np.sign(d[col]) == -np.sign(d.cfbd)) & (d[col].abs() >= 1) & (d.cfbd.abs() >= 1)
    return dict(cfbd_games=len(has_ref), covered=len(d), coverage=len(d) / len(has_ref),
                within_1=(diff <= 1).mean(), within_3=(diff <= 3).mean(), sign_flips=int(flip.sum()))


fmt = dict(index=False, float_format=lambda x: f"{x:.4f}")
for col, lab in (("stored", "games.parquet as stored"), ("fresh", "home_spreads() now")):
    print(f"\n{lab}: agreement with CFBD, played games with a closing total, 2014-25")
    print(pd.DataFrame([dict(season="all", **score(g, col))]
                       + [dict(season=s, **score(d, col)) for s, d in g.groupby("season")]).to_string(**fmt))

both = g[g.stored.notna() & g.fresh.notna()]
print(f"\ngames with both versions: {len(both):,}; identical: {int((both.stored == both.fresh).sum()):,}; "
      f"differ by more than 1 point: {int(((both.stored - both.fresh).abs() > 1).sum()):,}")
