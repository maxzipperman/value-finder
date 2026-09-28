"""No-hindsight replay of 2024-25 against Pinnacle (needs `odds_api.py backfill`).

For each outdoor game: the forecast as it stood 3 days and 1 day out (Open-Meteo
previous runs), Pinnacle's total at the matching snapshot, and Pinnacle's last
total before kickoff. The weather model (fit on 1999-2023 observed weather) turns
each forecast into P(under); leans are scored on closing-line value and on
results vs the close. Nothing here uses information from after the snapshot.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd

from nflweather import oddsapi
from nflweather.board import LEAN_P
from nflweather.config import PROC, RAW, TABLES
from nflweather.features import add_weather_features
from nflweather.market import fit_under_model, load_games, predict_under, record

L = oddsapi.lines_table(pd.read_csv(RAW / "games.csv"))
if L.empty:
    sys.exit("no Pinnacle snapshots cached: run scripts/odds_api.py backfill --confirm first")
cal = json.loads((PROC / "calibration.json").read_text())
g = pd.read_parquet(PROC / "games.parquet")
g = g[g.result.notna() & (g.roof == "outdoors") & g.fc1_wind.notna()].copy()
m = fit_under_model(load_games(last=2023))

close = L.sort_values("min_to_kick").drop_duplicates("game_id")[["game_id", "total", "min_to_kick"]]
close = close[close.min_to_kick <= 120].rename(columns={"total": "pin_close"})
rows = []
for lead, lo, hi, fc in [(3, 36 * 60, 6 * 24 * 60, "fc3"), (1, 12 * 60, 36 * 60, "fc1")]:
    snap = L[L.min_to_kick.between(lo, hi)].sort_values("min_to_kick").drop_duplicates("game_id")
    d = g.merge(snap[["game_id", "total"]].rename(columns={"total": "pin_snap"}), on="game_id").merge(close, on="game_id")
    x = add_weather_features(d.assign(
        wx_src="era5", wx_wind=(cal["wind_intercept"] + cal["wind_slope"] * d[f"{fc}_wind"]).clip(lower=0),
        wx_temp=d[f"{fc}_temp"], wx_precip=d[f"{fc}_precip"], wx_snow=d[f"{fc}_snow"]))
    d["p_under"] = predict_under(m, x)
    for side, sel in [("under", d.p_under >= LEAN_P), ("over", d.p_under <= 1 - LEAN_P)]:
        s = d[sel]
        clv = (s.pin_snap - s.pin_close) if side == "under" else (s.pin_close - s.pin_snap)
        win = (s.total < s.pin_close) if side == "under" else (s.total > s.pin_close)
        loss = (s.total > s.pin_close) if side == "under" else (s.total < s.pin_close)
        rec = record(win.values, loss.values)
        se = clv.std(ddof=1) / np.sqrt(len(s)) if len(s) > 1 else np.nan
        rows.append(dict(forecast_lead_days=lead, side=side, games_scored=len(d), leans=len(s), mean_clv_pts=clv.mean(),
                         clv_ci_lo=clv.mean() - 1.96 * se, clv_ci_hi=clv.mean() + 1.96 * se,
                         beat_close=(clv > 0).mean(), win_pct_vs_close=rec["win_pct"], roi_110=rec["roi_110"]))
    d["all_move"] = d.pin_snap - d.pin_close
    rows.append(dict(forecast_lead_days=lead, side="all outdoor games (baseline drift)", games_scored=len(d),
                     leans=len(d), mean_clv_pts=d.all_move.mean(), beat_close=(d.all_move > 0).mean()))
r = pd.DataFrame(rows)
r.to_csv(TABLES / "pinnacle_check.csv", index=False)
pd.set_option("display.width", 200)
print(r.round(3).to_string(index=False))
