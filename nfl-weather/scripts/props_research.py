"""Player-prop research, step 1: do weather effects on player stat lines survive
controlling for what the betting market already implies for that team's points?

Prop lines are largely anchored to the game total and spread. If weather still
predicts a player's passing/rushing/receiving line after conditioning on the
market's implied team points, a prop built off the total would under-adjust.
This does NOT test prop prices (no prop price history yet); it tests whether
the information the totals market carries already contains the weather effect.

Model per role x stat, 1999-2025:
  stat ~ weather bins + home/neutral/playoff [+ implied team points]
         | player-season + opponent-season + week,   SEs clustered by game
Output: output/tables/props_player_effects.csv
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd
import pyfixest as pf
from scipy.stats import norm

from nflweather.config import PROC, TABLES
from nflweather.features import BIN_TERMS, add_weather_features
from nflweather.players import build

pg_path = PROC / "player_games.parquet"
pg = pd.read_parquet(pg_path) if pg_path.exists() else build()
tg = pd.read_parquet(PROC / "team_games.parquet")
g = pd.read_parquet(PROC / "games.parquet")[["game_id", "total_line", "spread_line"]]
wx = add_weather_features(tg[tg.season.between(1999, 2025)])
wx = wx.drop(columns=["total_line", "spread_line"], errors="ignore").merge(g, on="game_id")
wx["implied_pts"] = wx.total_line / 2 + np.where(wx.side == "home", 1, -1) * wx.spread_line / 2
keep = ["game_id", "side", "season", "week", "opp_franchise", "home", "neutral", "playoff", "implied_pts"] + BIN_TERMS
d = pg.drop(columns=["season"]).merge(wx[keep], on=["game_id", "side"])
d["player_season"] = d.player_id + "_" + d.season.astype(str)
d["opp_season"] = d.opp_franchise + "_" + d.season.astype(str)
d["week_fe"] = d.week.astype(str)
d["home_site"] = d.home * (1 - d.neutral)

STATS = {"QB": [("pass_yds", "Passing yards"), ("cmp", "Completions"), ("pass_att", "Pass attempts")],
         "RB1": [("rush_att", "Rush attempts"), ("rush_yds", "Rushing yards")],
         "WR1": [("rec_yds", "Receiving yards"), ("rec", "Receptions")]}
rows = []
for role, stats in STATS.items():
    s = d[d.role == role]
    for y, lab in stats:
        for spec, extra in [("weather only", []), ("+ implied points", ["implied_pts"])]:
            m = pf.feols(f"{y} ~ {' + '.join(BIN_TERMS + ['home_site', 'neutral', 'playoff'] + extra)}"
                         " | player_season + opp_season + week_fe", data=s.dropna(subset=[y, "implied_pts"]),
                         vcov={"CRV1": "game_id"})
            t = m.tidy()
            sd = float(np.std(m.resid()))
            base = s.loc[(s[BIN_TERMS].sum(axis=1) == 0), y].mean()
            for term in ["wind_15_19", "wind_20p", "rain", "snow", "temp_le32"]:
                c = t.loc[term]
                rows.append(dict(role=role, stat=lab, spec=spec, term=term, coef=c["Estimate"], lo=c["2.5%"],
                                 hi=c["97.5%"], p=c["Pr(>|t|)"], baseline=base, resid_sd=sd, n=int(m._N),
                                 pct_of_baseline=100 * c["Estimate"] / base,
                                 p_side_if_line_ignores_weather=norm.cdf(abs(c["Estimate"]) / sd)))
r = pd.DataFrame(rows)
r.to_csv(TABLES / "props_player_effects.csv", index=False)

pd.set_option("display.width", 220)
w = r[r.spec == "+ implied points"].set_index(["role", "stat", "term"])
o = r[r.spec == "weather only"].set_index(["role", "stat", "term"])
show = pd.DataFrame({"baseline": w.baseline.round(1), "weather_only": o.coef.round(2), "after_market": w.coef.round(2),
                     "pct": w.pct_of_baseline.round(1), "p": w.p.round(3),
                     "share_left": (w.coef / o.coef).round(2), "p_if_ignored": w.p_side_if_line_ignores_weather.round(3),
                     "n": w.n})
print(show[show.index.get_level_values("term").isin(["wind_15_19", "wind_20p", "rain"])].to_string())
