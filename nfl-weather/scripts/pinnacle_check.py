"""No-hindsight replay of 2024-25 against Pinnacle (needs `odds_api.py backfill`).

For each outdoor game: the forecast as it stood 3 days and 1 day out (Open-Meteo
previous runs), Pinnacle's total at the first snapshot taken after that forecast
was public (oddsapi.decision_time: last game hour - lead + 7h release latency),
and Pinnacle's last total before kickoff. Bets are graded at the entry number.
Limitation: previous-run fields for different game hours come from different
model runs; all of them were published before the decision time, but they are not
one single run. Exact single-run archives only exist from 2024 (ECMWF) / 2026. The weather model (fit on 1999-2023 observed weather) turns
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
g = g.merge(pd.read_csv(RAW / "games.csv")[["game_id", "gameday", "gametime"]], on="game_id", how="left", suffixes=("", "_s"))
g["kick_utc"] = pd.to_datetime(g.gameday + " " + g.gametime).dt.tz_localize("America/New_York").dt.tz_convert("UTC")
rows = []
for lead, fc in [(1, "fc1"), (3, "fc3")]:
    g["decision_utc"] = [oddsapi.decision_time(k, lead) for k in g.kick_utc]
    # first quote at or after the decision time (never before it), and at least an hour before kickoff
    q = L.merge(g[["game_id", "decision_utc", "kick_utc"]], on="game_id")
    q = q[(q.snapshot_utc >= q.decision_utc) & (q.snapshot_utc <= q.kick_utc - pd.Timedelta(hours=1))]
    snap = q.sort_values("snapshot_utc").drop_duplicates("game_id")[["game_id", "total", "snapshot_utc"]]
    d = g.merge(snap.rename(columns={"total": "pin_snap"}), on="game_id").merge(close, on="game_id")
    assert (d.snapshot_utc >= d.decision_utc).all(), "a quote predates its forecast"
    x = add_weather_features(d.assign(
        wx_src="era5", wx_wind=(cal["wind_intercept"] + cal["wind_slope"] * d[f"{fc}_wind"]).clip(lower=0),
        wx_temp=d[f"{fc}_temp"], wx_precip=d[f"{fc}_precip"], wx_snow=d[f"{fc}_snow"]))
    d["p_under"] = predict_under(m, x)
    d["rule_b"] = (x.outdoor == 1) & (x.wx_wind >= 15)
    for side, sel in [("under (model lean)", d.p_under >= LEAN_P), ("over (model lean)", d.p_under <= 1 - LEAN_P),
                      ("under (Rule B wind)", d.rule_b)]:
        s = d[sel]
        under = side.startswith("under")
        clv = (s.pin_snap - s.pin_close) if under else (s.pin_close - s.pin_snap)
        win = (s.total < s.pin_snap) if under else (s.total > s.pin_snap)      # graded at the ENTRY number
        loss = (s.total > s.pin_snap) if under else (s.total < s.pin_snap)
        rec = record(win.values, loss.values)
        se = clv.std(ddof=1) / np.sqrt(len(s)) if len(s) > 1 else np.nan
        rows.append(dict(forecast_lead_days=lead, side=side, games_scored=len(d), bets=len(s), mean_clv_pts=clv.mean(),
                         clv_ci_lo=clv.mean() - 1.96 * se, clv_ci_hi=clv.mean() + 1.96 * se,
                         beat_close=(clv > 0).mean(), win_pct_at_entry=rec["win_pct"], roi_110=rec["roi_110"]))
    d["all_move"] = d.pin_snap - d.pin_close
    rows.append(dict(forecast_lead_days=lead, side="all outdoor games (baseline drift)", games_scored=len(d),
                     bets=len(d), mean_clv_pts=d.all_move.mean(), beat_close=(d.all_move > 0).mean()))
r = pd.DataFrame(rows)
r.to_csv(TABLES / "pinnacle_check.csv", index=False)
pd.set_option("display.width", 200)
print(r.round(3).to_string(index=False))
