"""Candidate betting rules, each scored the same way:

* vs the closing total, 1999-2025 and by era (1999-2013, 2014-2025, 2020-2025)
* vs the opening total and the open-to-close move, 2007-2021 (Sportsbook Reviews)
* on forecast inputs only, 2024-2026 (Open-Meteo previous runs, 1 and 3 days out)

Rules use fixed thresholds from the literature or from data checks that never
looked at betting results (15 mph: Burke 2012 and our wind bins; rain >= 0.06 in:
chosen to match the NFL game book's "rain" text). Output: output/tables/strategies.csv
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd

from nflweather.config import PROC, TABLES
from nflweather.features import RAIN_IN, SNOW_IN
from nflweather.market import load_games, record

g = load_games(1999, 2026)
cal = json.loads((PROC / "calibration.json").read_text())
tg = pd.read_parquet(PROC / "team_games.parquet")
vis = tg[tg.side == "away"][["game_id", "dome_team", "city_tavg7"]].rename(columns={"dome_team": "v_dome", "city_tavg7": "v_temp7"})
g = g.merge(vis, on="game_id", how="left")
o = g.outdoor == 1
wet = (g.wx_precip >= RAIN_IN) | (g.wx_snow >= SNOW_IN)

RULES = {  # name: (mask on observed weather, bet side)
    "Wind 15+ mph → under": (o & (g.wx_wind >= 15), "under"),
    "Rain → under": (o & (g.rain == 1), "under"),
    "Storm: wind 15+ and rain/snow → under": (o & (g.wx_wind >= 15) & wet, "under"),
    "Wind 15+ or rain → under": (o & ((g.wx_wind >= 15) | (g.rain == 1)), "under"),
    "Snow → under (control)": (o & (g.snow == 1), "under"),
    "Freezing ≤32°F, calm & dry → over (control)": (o & (g.wx_temp <= 32) & (g.wx_wind < 15) & ~wet, "over"),
}
ERAS = {"1999–2025": (1999, 2025), "1999–2013": (1999, 2013), "2014–2025": (2014, 2025), "2020–2025": (2020, 2025)}


def score(d, side, line="total_line"):
    tot = d[line]
    win = (d.total < tot) if side == "under" else (d.total > tot)
    loss = (d.total > tot) if side == "under" else (d.total < tot)
    return record(win.values, loss.values)


rows = []
for name, (mask, side) in RULES.items():
    for era, (a, b) in ERAS.items():
        d = g[mask & g.season.between(a, b)]
        r = score(d, side)
        rows.append(dict(rule=name, test=f"vs close {era}", games=len(d), bets=r["bets"], win_pct=r["win_pct"],
                         win_lo=r["win_lo"], win_hi=r["win_hi"], roi_110=r["roi_110"], p=r["p_vs_breakeven"],
                         mean_miss=(d.total - d.total_line).mean()))
    d = g[mask & g.total_open.notna()]
    r = score(d, side, "total_open")
    move = (d.total_line - d.total_open)
    rows.append(dict(rule=name, test="vs open 2007–2021", games=len(d), bets=r["bets"], win_pct=r["win_pct"],
                     win_lo=r["win_lo"], win_hi=r["win_hi"], roi_110=r["roi_110"], p=r["p_vs_breakeven"],
                     mean_move=move.mean(), share_moved_our_way=((move < 0) if side == "under" else (move > 0)).mean()))

# forecast-only versions (2024-2026 outdoor games with archived forecasts)
f = g[o & g.fc1_wind.notna()].copy()
for lead in (1, 3):
    w = (cal["wind_intercept"] + cal["wind_slope"] * f[f"fc{lead}_wind"]).clip(lower=0)
    fwet = (f[f"fc{lead}_precip"] >= RAIN_IN) | (f[f"fc{lead}_snow"] >= SNOW_IN)
    frain = (f[f"fc{lead}_precip"] >= RAIN_IN) & (f[f"fc{lead}_snow"] < SNOW_IN)
    for name, m in {"Wind 15+ mph → under": w >= 15, "Rain → under": frain,
                    "Storm: wind 15+ and rain/snow → under": (w >= 15) & fwet,
                    "Wind 15+ or rain → under": (w >= 15) | frain}.items():
        d = f[m]
        r = score(d, "under")
        rows.append(dict(rule=name, test=f"forecast {lead}d out, 2024–26", games=len(d), bets=r["bets"],
                         win_pct=r["win_pct"], win_lo=r["win_lo"], win_hi=r["win_hi"], roi_110=r["roi_110"],
                         p=r["p_vs_breakeven"]))

# where the rain edge comes from: forecast rain vs rain nobody forecast (2024-2026)
fr = (f.fc1_precip >= RAIN_IN) & (f.fc1_snow < SNOW_IN)
for name, m in {"Rain split: forecast rain (1d)": fr, "Rain split: rain nobody forecast": ~fr & (f.rain == 1),
                "Rain split: forecast rain that stayed dry": fr & (f.rain == 0),
                "Wind split: observed wind 15+": f.wx_wind >= 15}.items():
    d = f[m]
    r = score(d, "under")
    rows.append(dict(rule=name, test="2024–26 outdoor games", games=len(d), bets=r["bets"], win_pct=r["win_pct"],
                     win_lo=r["win_lo"], win_hi=r["win_hi"], roi_110=r["roi_110"], p=r["p_vs_breakeven"],
                     mean_miss=(d.total - d.total_line).mean()))

# acclimation side bets
cold = o & (g.wx_temp <= 32) & (g.neutral == 0)
warmvis = (g.v_dome == 1) | (g.v_temp7 >= 60)
for name, m in {"Dome/warm visitor in ≤32°F game → home ATS": cold & warmvis,
                "Cold-climate visitor in ≤32°F game → home ATS (control)": cold & (g.v_dome == 0) & (g.v_temp7 < 40)}.items():
    for era, (a, b) in ERAS.items():
        d = g[m & g.season.between(a, b)]
        r = record((d.result > d.spread_line).values, (d.result < d.spread_line).values)
        rows.append(dict(rule=name, test=f"vs close {era}", games=len(d), bets=r["bets"], win_pct=r["win_pct"],
                         win_lo=r["win_lo"], win_hi=r["win_hi"], roi_110=r["roi_110"], p=r["p_vs_breakeven"],
                         mean_miss=(d.result - d.spread_line).mean()))

out = pd.DataFrame(rows)
out.to_csv(TABLES / "strategies.csv", index=False)
pd.set_option("display.width", 250)
pd.set_option("display.max_colwidth", 48)
print(out[["rule", "test", "bets", "win_pct", "win_lo", "win_hi", "roi_110", "p", "mean_miss", "mean_move",
           "share_moved_our_way"]].round(3).to_string(index=False))
