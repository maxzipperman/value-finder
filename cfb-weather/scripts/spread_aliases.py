"""Write cfbweather/spread_aliases.csv: sportsbook team codes in cfbfastR's spread lines (NIL, NMS,
OHI, ...) that team info doesn't list, each mapped to a team (issue #36).

Before this table, about a fifth of the two-row (game, book) spread pairs named neither team, and
build.home_spreads() dropped them without a count.

How a code gets its team: take every spread row whose code matches neither team in its game (by team
info names or the "away@home" description). The team a code stands for plays in nearly every game
the code appears in, and any other team plays in only a few. A code is kept when it appears in at
least MIN_GAMES games, its modal team plays in at least MIN_SHARE of them, and no other team plays
in more than MAX_RUNNER_UP. The inference only uses which games a code appears in. It never reads
the lines or CFBD, so scripts/spread_audit.py's CFBD cross-check stays independent.

Needs the raw cfbfastR cache (Mac only). Run from cfb-weather/:
    .venv/bin/python scripts/spread_aliases.py
"""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cfbweather.build import ALIASES, schedule_teams, team_names  # noqa: E402
from cfbweather.config import RAW  # noqa: E402

MIN_GAMES, MIN_SHARE, MAX_RUNNER_UP = 3, 0.90, 0.50

b = pd.read_parquet(RAW / "cfbfastr" / "line_odds.parquet")
b = b[(b.market_type == "spread") & b.lines.notna() & b.game_id.notna()]
b = b.assign(game_id=b.game_id.astype("int64")).merge(schedule_teams(), on="game_id")
names = team_names(aliases=False)
b["code"] = b.abbr.astype(str).str.strip().str.lower()
desc = b.game_desc.astype(str).str.lower().str.split("@")
known = [c in names.get(int(h), ()) or c in names.get(int(w), ()) or c in (d[0].strip(), d[-1].strip())
         for c, h, w, d in zip(b.code, b.home_id.fillna(-1), b.away_id.fillna(-1), desc)]
u = b.loc[~pd.Series(known, index=b.index), ["code", "game_id", "home_id", "away_id"]].drop_duplicates(["code", "game_id"])

teams = pd.concat([u[["code", "game_id", "home_id"]].rename(columns={"home_id": "team_id"}),
                   u[["code", "game_id", "away_id"]].rename(columns={"away_id": "team_id"})]).dropna()
per_team = teams.groupby(["code", "team_id"]).game_id.nunique().rename("n").reset_index()
per_team["games"] = per_team.code.map(u.groupby("code").game_id.nunique())
per_team["share"] = per_team.n / per_team.games
per_team = per_team.sort_values(["code", "n"], ascending=[True, False])
top = per_team.drop_duplicates("code").set_index("code")
top["runner_up"] = per_team.groupby("code").share.apply(lambda s: s.iloc[1] if len(s) > 1 else 0.0)
keep = top[(top.games >= MIN_GAMES) & (top.share >= MIN_SHARE) & (top.runner_up <= MAX_RUNNER_UP)].copy()

ti = pd.concat([pd.read_parquet(p) for p in sorted((RAW / "cfbfastr").glob("team_info_*.parquet"))])
school = ti.drop_duplicates("team_id", keep="last").set_index("team_id").school
keep["team_id"] = keep.team_id.astype(int)
keep["school"] = keep.team_id.map(school)
out = keep.reset_index()[["code", "team_id", "school", "games", "share"]].round({"share": 3})
out.to_csv(ALIASES, index=False)

left = top.drop(keep.index)
rows = b.loc[~pd.Series(known, index=b.index)].code.value_counts()
print(f"unmatched codes: {len(top)}; kept {len(keep)} (covering {int(rows.reindex(keep.index).sum()):,} rows); "
      f"left out {len(left)} (covering {int(rows.reindex(left.index).sum()):,} rows)")
print(f"wrote {ALIASES.relative_to(ALIASES.parents[1])}")
print("\nleft out, most rows first (games, modal team's share, runner-up's share):")
left = left.assign(rows=rows.reindex(left.index).values, school=left.team_id.astype(int).map(school))
print(left.sort_values("rows", ascending=False)[["rows", "games", "share", "runner_up", "school"]].head(40).round(3).to_string())
