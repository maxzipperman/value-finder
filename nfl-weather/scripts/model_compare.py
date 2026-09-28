"""Is a more sophisticated betting model better? Walk-forward (refit every
season on prior seasons only, 2006-2025) comparison of P(under) models:

  base      league under rate from prior seasons (no weather)
  logit     the weather-bin logistic model used by the board
  logit_x   + interactions (wind x total, wind x cold, wind x rain) and linear wind
  gbm       gradient-boosted trees on raw weather + the posted total/spread

scored on log loss and Brier, and against the de-vigged closing price where
over/under prices exist. Output: output/tables/model_compare*.csv
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd
import statsmodels.api as sm
from sklearn.ensemble import HistGradientBoostingClassifier

from nflweather.config import TABLES
from nflweather.features import BIN_TERMS
from nflweather.market import load_games, market_p_under, record


def features(g):
    g = g.copy()
    g["tl_c"] = g.total_line - 44
    g["w_lin"] = g.wind_mph
    g["w15_x_tl"] = (g.wind_15_19 + g.wind_20p) * g.tl_c
    g["w15_x_cold"] = (g.wind_15_19 + g.wind_20p) * g.temp_le32
    g["w15_x_rain"] = (g.wind_15_19 + g.wind_20p) * g.rain
    g["abs_spread"] = g.spread_line.abs()
    g["o_wind"] = g.wx_wind.where(g.outdoor == 1, -1)       # -1 marks indoor for the trees
    g["o_temp"] = g.wx_temp.where(g.outdoor == 1, 70)
    g["o_precip"] = g.wx_precip.fillna(0)
    g["o_snow"] = g.wx_snow.fillna(0)
    g["o_gust"] = g.wx_gust.where(g.outdoor == 1, -1).fillna(-1)
    return g


X_LOGIT = BIN_TERMS
X_LOGIT_X = BIN_TERMS + ["w_lin", "tl_c", "w15_x_tl", "w15_x_cold", "w15_x_rain"]
X_GBM = ["o_wind", "o_temp", "o_precip", "o_snow", "o_gust", "indoor", "roof_open", "total_line", "abs_spread", "week", "playoff"]


def fit_logit(tr, x):
    X = sm.add_constant(tr[x].astype(float), has_constant="add")
    return sm.Logit(tr.y, X).fit(disp=0, method="lbfgs", maxiter=500)


def pred_logit(m, te, x):
    return np.asarray(m.predict(sm.add_constant(te[x].astype(float), has_constant="add")))


def walk_forward(g):
    out = []
    for t in range(2006, 2026):
        tr, te = g[g.season < t], g[g.season == t].copy()
        te["p_base"] = tr.y.mean()
        te["p_logit"] = pred_logit(fit_logit(tr, X_LOGIT), te, X_LOGIT)
        te["p_logit_x"] = pred_logit(fit_logit(tr, X_LOGIT_X), te, X_LOGIT_X)
        gbm = HistGradientBoostingClassifier(max_depth=3, learning_rate=0.03, max_iter=250, min_samples_leaf=150,
                                             l2_regularization=1.0, random_state=0)
        gbm.fit(tr[X_GBM].astype(float), tr.y)
        te["p_gbm"] = gbm.predict_proba(te[X_GBM].astype(float))[:, 1]
        out.append(te)
    return pd.concat(out)


def score(p, y):
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return dict(log_loss=float(-(y * np.log(p) + (1 - y) * np.log(1 - p)).mean()), brier=float(((p - y) ** 2).mean()))


if __name__ == "__main__":
    pd.set_option("display.width", 220)
    g = load_games()
    g = g[g.under_win | g.over_win].copy()
    g["y"] = g.under_win.astype(int)
    g = features(g)
    p = walk_forward(g)
    p["p_market"] = market_p_under(p.under_odds, p.over_odds, "shin")
    models = ["p_base", "p_logit", "p_logit_x", "p_gbm"]
    rows = []
    for subset, s in [("All games", p), ("Outdoor games", p[p.outdoor == 1]), ("Outdoor, wind 15+", p[p.wx_wind >= 15]),
                      ("Games with O/U prices", p[p.p_market.notna()])]:
        base = score(s.p_base.values, s.y.values)
        for m in models + (["p_market"] if subset == "Games with O/U prices" else []):
            sc = score(s[m].values, s.y.values)
            rows.append(dict(subset=subset, model=m.replace("p_", ""), games=len(s), **sc,
                             skill_vs_base=1 - sc["brier"] / base["brier"]))
    r = pd.DataFrame(rows)
    r.to_csv(TABLES / "model_compare.csv", index=False)
    print(r.round(5).to_string(index=False))

    bets = []
    for m in ["p_logit", "p_logit_x", "p_gbm"]:
        for thr in (0.53, 0.55):
            u, o = p[p[m] >= thr], p[p[m] <= 1 - thr]
            ru = record(u.under_win.values, u.over_win.values, u.under_profit)
            ro = record(o.over_win.values, o.under_win.values, o.over_profit)
            bets.append(dict(model=m.replace("p_", ""), threshold=thr, side="under", **ru))
            bets.append(dict(model=m.replace("p_", ""), threshold=thr, side="over", **ro))
    b = pd.DataFrame(bets)
    b.to_csv(TABLES / "model_compare_bets.csv", index=False)
    print(b[["model", "threshold", "side", "bets", "win_pct", "win_lo", "roi_110", "roi_actual_odds", "p_vs_breakeven"]].round(3).to_string(index=False))
