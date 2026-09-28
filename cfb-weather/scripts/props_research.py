"""CFB player-prop research, step 1 (same design as nfl-weather/scripts/props_research.py):
do weather effects on player stat lines survive controlling for the market's
implied team points (closing total and spread)? Station weather at kickoff,
2014-2025, player-season / opponent-season / week fixed effects, SEs clustered by game.
Output: output/tables/props_player_effects.csv
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd
import pyfixest as pf
from scipy.stats import norm

from cfbweather.config import PROC, TABLES
from cfbweather.features import BIN_TERMS
from cfbweather.market import load_games
from cfbweather.players import build

pg = build()
g = load_games(2014, 2025)
g = g[g.home_spread.notna()]
rows = []
for side, team_col, opp_col, sign in (("home", "home_team", "away_team", -1), ("away", "away_team", "home_team", 1)):
    t = g[["game_id", "season", "week_fe", "neutral", "playoff", team_col, opp_col] + BIN_TERMS].rename(
        columns={team_col: "team", opp_col: "opp"})
    # home_spread < 0 means home favored: implied home points = total/2 - spread/2
    t["implied_pts"] = g.close_total / 2 + sign * g.home_spread / 2
    t["home_site"] = int(side == "home") * (1 - t.neutral)
    rows.append(t)
tg = pd.concat(rows, ignore_index=True)
d = pg.drop(columns=["season"]).merge(tg, on=["game_id", "team"])
d["player_season"] = d.player_id.astype(str) + "_" + d.season.astype(str)
d["opp_season"] = d.opp.astype(str) + "_" + d.season.astype(str)
BIN = [b for b in BIN_TERMS if b != "roof_open"]
STATS = {"QB": [("pass_yds", "Passing yards"), ("cmp", "Completions"), ("pass_att", "Pass attempts")],
         "RB1": [("rush_att", "Rush attempts"), ("rush_yds", "Rushing yards")],
         "WR1": [("rec_yds", "Receiving yards"), ("rec", "Receptions")]}
out = []
for role, stats in STATS.items():
    s = d[d.role == role]
    for y, lab in stats:
        for spec, extra in [("weather only", []), ("+ implied points", ["implied_pts"])]:
            m = pf.feols(f"{y} ~ {' + '.join(BIN + ['home_site', 'neutral', 'playoff'] + extra)} | player_season + opp_season + week_fe",
                         data=s.dropna(subset=[y]), vcov={"CRV1": "game_id"})
            tt, sd = m.tidy(), float(np.std(m.resid()))
            base = s.loc[s[BIN].sum(axis=1) == 0, y].mean()
            for term in ["wind_15_19", "wind_20p", "rain", "temp_le32"]:
                c = tt.loc[term]
                out.append(dict(role=role, stat=lab, spec=spec, term=term, coef=c["Estimate"], lo=c["2.5%"], hi=c["97.5%"],
                                p=c["Pr(>|t|)"], baseline=base, resid_sd=sd, n=int(m._N), pct_of_baseline=100 * c["Estimate"] / base,
                                p_side_if_line_ignores_weather=norm.cdf(abs(c["Estimate"]) / sd)))
r = pd.DataFrame(out)
r.to_csv(TABLES / "props_player_effects.csv", index=False)
pd.set_option("display.width", 220)
w, o = [r[r.spec == s].set_index(["role", "stat", "term"]) for s in ("+ implied points", "weather only")]
show = pd.DataFrame({"baseline": w.baseline.round(1), "weather_only": o.coef.round(2), "after_market": w.coef.round(2),
                     "pct": w.pct_of_baseline.round(1), "p": w.p.round(3), "share_left": (w.coef / o.coef).round(2),
                     "p_if_ignored": w.p_side_if_line_ignores_weather.round(3), "n": w.n})
print(show[show.index.get_level_values("term").isin(["wind_15_19", "wind_20p", "rain"])].to_string())
