"""Betting helpers shared by the backtests and the weekly board."""
from __future__ import annotations

import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy import stats

from .config import PROC
from .features import BIN_TERMS, add_weather_features, wind_bin

WIN_110 = 100 / 110  # profit per unit risked on a -110 winner
BREAKEVEN_110 = 110 / 210
FRANCHISE = {"OAK": "LV", "SD": "LAC", "STL": "LA"}


def american_to_profit(odds):
    odds = np.asarray(pd.to_numeric(pd.Series(odds), errors="coerce"), dtype=float)
    return np.where(odds > 0, odds / 100, 100 / np.abs(odds))


def american_to_prob(odds):
    odds = np.asarray(pd.to_numeric(pd.Series(odds), errors="coerce"), dtype=float)
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(odds < 0, np.abs(odds) / (np.abs(odds) + 100), 100 / (odds + 100))


def devig_proportional(p1, p2):
    total = p1 + p2
    return p1 / total


def devig_shin(p1, p2, iters=60):
    """Shin (1993) de-vig, vectorized bisection on z (share of insider money).
    Same method as the sharp-markets backtests; if proportional and Shin disagree,
    treat it as a measurement artifact rather than edge."""
    p1, p2 = np.asarray(p1, float), np.asarray(p2, float)
    total = p1 + p2

    def pi(z, p):
        return (np.sqrt(z * z + 4 * (1 - z) * p * p / total) - z) / (2 * (1 - z))

    lo, hi = np.full_like(p1, 1e-9), np.full_like(p1, 0.5 - 1e-9)
    for _ in range(iters):
        mid = (lo + hi) / 2
        f = pi(mid, p1) + pi(mid, p2) - 1
        flo = pi(lo, p1) + pi(lo, p2) - 1
        go_hi = flo * f < 0
        hi = np.where(go_hi, mid, hi)
        lo = np.where(go_hi, lo, mid)
    out = pi((lo + hi) / 2, p1)
    return np.where(total > 1, out, p1 / total)


def market_p_under(under_odds, over_odds, method="shin"):
    pu, po = american_to_prob(under_odds), american_to_prob(over_odds)
    return devig_shin(pu, po) if method == "shin" else devig_proportional(pu, po)


def wilson(k, n, z=1.96):
    if n == 0:
        return (np.nan, np.nan)
    p = k / n
    den = 1 + z * z / n
    c = (p + z * z / (2 * n)) / den
    h = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return c - h, c + h


def record(win, loss, price_profit=None):
    """Flat 1-unit bets. win/loss boolean arrays (pushes are neither)."""
    win, loss = np.asarray(win, bool), np.asarray(loss, bool)
    w, l = int(win.sum()), int(loss.sum())
    n = w + l
    lo, hi = wilson(w, n)
    out = dict(bets=n, wins=w, win_pct=w / n if n else np.nan, win_lo=lo, win_hi=hi,
               roi_110=(w * WIN_110 - l) / n if n else np.nan,
               p_vs_breakeven=stats.binomtest(w, n, BREAKEVEN_110, alternative="greater").pvalue if n else np.nan)
    if price_profit is not None:
        pp = np.asarray(price_profit, dtype=float)
        m = (win | loss) & ~np.isnan(pp)
        if m.sum():
            out["roi_actual_odds"] = np.where(win[m], pp[m], -1.0).mean()
            out["bets_with_odds"] = int(m.sum())
    return out


def load_games(first=1999, last=2025):
    g = pd.read_parquet(PROC / "games.parquet")
    g = g[g.result.notna() & g.season.between(first, last)].copy()
    g = add_weather_features(g)
    g["resid_total"] = g.total - g.total_line
    g["under_win"] = g.total < g.total_line
    g["over_win"] = g.total > g.total_line
    g["under_profit"] = american_to_profit(g.under_odds)
    g["over_profit"] = american_to_profit(g.over_odds)
    g["home_ts"] = g.home_team.replace(FRANCHISE) + "_" + g.season.astype(str)
    g["away_ts"] = g.away_team.replace(FRANCHISE) + "_" + g.season.astype(str)
    g["week_fe"] = g.week.astype(str)
    g["era"] = np.where(g.season <= 2013, "1999–2013", "2014–2025")
    g["wbin"] = wind_bin(g.wx_wind.where(g.outdoor == 1))
    return g


def fit_under_model(tr, x=BIN_TERMS):
    """Logistic model of P(under | weather) on non-push games. The average miss vs.
    the total is positive (scores are right-skewed) while unders still win ~50%,
    so a mean-residual model would lean over for no reason: model the bet itself."""
    tr = tr[tr.under_win | tr.over_win]
    X = sm.add_constant(tr[x].astype(float), has_constant="add")
    return sm.Logit(tr.under_win.astype(int), X).fit(disp=0)


def predict_under(m, df, x=BIN_TERMS):
    return np.asarray(m.predict(sm.add_constant(df[x].astype(float), has_constant="add")))
