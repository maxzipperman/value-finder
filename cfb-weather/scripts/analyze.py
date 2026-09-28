"""Does the CFB totals market price the weather? Same tests as nfl-weather:

1. market vs reality: how much weather moves actual points vs the closing total
   (home and away team-season fixed effects plus week)
2. playbook rules scored vs the close, by era, and vs the opener where one exists
3. open-to-close move by weather
4. walk-forward P(under) model refit each season on prior seasons only

Weather is observed station weather at kickoff (an upper bound on what a
forecast-driven bettor could capture). Outputs: output/tables/*.csv
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd

from cfbweather.config import TABLES
from cfbweather.features import BIN_TERMS, RAIN_IN, SNOW_IN
from cfbweather.market import fit_under_model, load_games, predict_under, record
from cfbweather.models import fit

pd.set_option("display.width", 250)
pd.set_option("display.max_colwidth", 46)
g = load_games()
o = g.outdoor == 1
wet = (g.wx_precip >= RAIN_IN) | (g.wx_snow >= SNOW_IN)
print(f"games {len(g):,}; outdoor with weather {int(o.sum()):,}")

# 1. market vs reality ------------------------------------------------------------
rows = []
x = BIN_TERMS + ["playoff", "neutral"]
for y, lab in [("total", "Actual points"), ("total_line", "Closing total")]:
    for era, s in [("All 2006–2025", g), *g.groupby("era")]:
        t = fit(s, y, x, ["home_ts", "away_ts", "week_fe"], "hetero")
        t["series"], t["era"] = lab, era
        rows.append(t)
mv = pd.concat(rows)
mv.to_csv(TABLES / "market_vs_reality.csv", index=False)
print("\nPoints effect vs calm/mild/dry outdoor (team-season FE)\n",
      mv[mv.term.isin(BIN_TERMS)].pivot_table(index=["era", "term"], columns="series", values="coef", sort=False).round(2).to_string())

# 2. rules --------------------------------------------------------------------------
RULES = {
    "Wind 15+ mph → under": (o & (g.wx_wind >= 15), "under"),
    "Wind 20+ mph → under": (o & (g.wx_wind >= 20), "under"),
    "Rain → under": (o & (g.rain == 1), "under"),
    "Storm: wind 15+ and rain/snow → under": (o & (g.wx_wind >= 15) & wet, "under"),
    "Wind 15+ or rain → under": (o & ((g.wx_wind >= 15) | (g.rain == 1)), "under"),
    "Snow → under": (o & (g.snow == 1), "under"),
    "Freezing ≤32°F, calm & dry → over (control)": (o & (g.wx_temp <= 32) & (g.wx_wind < 15) & ~wet, "over"),
    "Calm, mild, dry → under (baseline)": (o & (g.wx_wind < 10) & g.wx_temp.between(46, 79) & ~wet, "under"),
    "Indoor → under (baseline)": (g.indoor == 1, "under"),
}
ERAS = {"2006–2025": (2006, 2025), "2006–2015": (2006, 2015), "2016–2025": (2016, 2025), "2021–2025": (2021, 2025)}


def score(d, side, line="total_line"):
    tot = d[line]
    w = (d.total < tot) if side == "under" else (d.total > tot)
    l = (d.total > tot) if side == "under" else (d.total < tot)
    return record(w.values, l.values)


out = []
for name, (m, side) in RULES.items():
    for era, (a, b) in ERAS.items():
        d = g[m & g.season.between(a, b)]
        r = score(d, side)
        out.append(dict(rule=name, test=f"vs close {era}", bets=r["bets"], win_pct=r["win_pct"], win_lo=r["win_lo"],
                        win_hi=r["win_hi"], roi_110=r["roi_110"], p=r["p_vs_breakeven"], mean_miss=(d.total - d.total_line).mean()))
    d = g[m & g.open_total.notna()]
    r = score(d, side, "open_total")
    mv_ = d.total_line - d.open_total
    out.append(dict(rule=name, test="vs open (2012+)", bets=r["bets"], win_pct=r["win_pct"], win_lo=r["win_lo"],
                    win_hi=r["win_hi"], roi_110=r["roi_110"], p=r["p_vs_breakeven"], mean_move=mv_.mean(),
                    share_moved_our_way=((mv_ < 0) if side == "under" else (mv_ > 0)).mean()))
st = pd.DataFrame(out)
st.to_csv(TABLES / "strategies.csv", index=False)
print("\nRules\n", st[["rule", "test", "bets", "win_pct", "win_lo", "win_hi", "roi_110", "p", "mean_miss", "mean_move",
                         "share_moved_our_way"]].round(3).to_string(index=False))

# 3. walk-forward ---------------------------------------------------------------------
preds = []
for t in range(2010, 2026):
    tr, te = g[g.season < t], g[g.season == t].copy()
    te["p_under"] = predict_under(fit_under_model(tr), te)
    preds.append(te)
p = pd.concat(preds)
wf = []
for k in (0.53, 0.55):
    for era, s in [("2010–2025", p), ("2010–2015", p[p.season <= 2015]), ("2016–2025", p[p.season >= 2016])]:
        u = s[s.p_under >= k]
        r = record(u.under_win.values, u.over_win.values)
        wf.append(dict(threshold=k, era=era, **r))
wf = pd.DataFrame(wf)
wf.to_csv(TABLES / "walkforward.csv", index=False)
by = p[p.p_under >= 0.53].groupby("season").apply(lambda s: pd.Series(record(s.under_win.values, s.over_win.values)))
print("\nWalk-forward (P(under) >= threshold, refit each season)\n",
      wf[["threshold", "era", "bets", "win_pct", "win_lo", "win_hi", "roi_110", "p_vs_breakeven"]].round(3).to_string(index=False))
print("\nBy season (0.53):", {int(s): f"{int(r.wins)}-{int(r.bets - r.wins)}" for s, r in by.iterrows()})
oo = p[(p.p_under >= 0.53) & p.open_total.notna()]
clv = dict(bets_with_open=len(oo), mean_clv_pts=float((oo.open_total - oo.total_line).mean()),
           share_beat_close=float((oo.total_line < oo.open_total).mean()),
           all_outdoor_move=float((g[o & g.open_total.notna()].total_line - g[o & g.open_total.notna()].open_total).mean()),
           seasons_profitable=int((by.roi_110 > 0).sum()), seasons=int(len(by)))
print("CLV:", {k: round(v, 3) if isinstance(v, float) else v for k, v in clv.items()})
(TABLES / "summary.json").write_text(json.dumps(clv))
