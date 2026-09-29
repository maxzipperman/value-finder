"""Betting helpers shared by the backtests and the weekly board."""
from __future__ import annotations

import hashlib
import json

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


# --------------------------------------------------------------------------- line- and price-aware pricing
# The logistic P(under) above describes finishing below the *closing* total. It says
# nothing about a different number or a bad price (it returns the same value for an
# under 30 and an under 60). For an actionable bet, price the offered line and odds:
# P(total < L) = P(resid < L - market_total), with resid = final total - market
# total drawn from historical games in the same weather cohort. The empirical
# distribution keeps the right skew and the key-number pushes that a normal curve would miss.

MIN_UNDER_ODDS = -115  # playbook price ceiling: never lay more than -115 on a weather under


def cohort_residuals(hist, mask):
    """Sorted (final total - closing total) for historical games matching `mask`."""
    return np.sort((hist.total - hist.total_line)[mask].dropna().to_numpy())


def pricing_cohort():
    """The frozen residuals behind the pricing model: final total minus closing total for outdoor games
    with 15+ mph observed wind, through 2023. They come from a committed file, so rebuilding the games
    table can't move the model (data/processed/pricing_cohort.json, written once by
    scripts/freeze_pricing_cohort.py; its sha256 is registered in PREREGISTRATION.md)."""
    js = json.loads((PROC / "pricing_cohort.json").read_text())
    return np.sort(np.asarray(js["residuals"], float))


def cohort_hash(resid_sorted) -> str:
    return hashlib.sha256(np.sort(np.asarray(resid_sorted, float)).round(4).tobytes()).hexdigest()


def _mid(resid_sorted, t):
    """G(t) = P(d < t) + P(d = t) / 2 over the cohort residuals d: ties are split evenly."""
    t = np.asarray(t, float)
    below = np.searchsorted(resid_sorted, t, side="left")
    upto = np.searchsorted(resid_sorted, t, side="right")
    return (below + upto) / (2 * len(resid_sorted))


def p_under_at(line, market_total, resid_sorted):
    """(P(win), P(push)) for an under at the offered `line`, against the reference total `market_total`.
    This is the registered pricing model (PREREGISTRATION.md, "the pricing model").

    The final total is the reference plus a residual drawn from the frozen cohort, and it is a whole
    number. With x = line - reference:
      * a half-point line can't push: P(win) = G(x);
      * a whole-number line wins below it, pushes on it and loses above it:
        P(win) = G(x - 1/2), P(push) = G(x + 1/2) - G(x - 1/2).
    The residual does not depend on the size of the total. That was tested on the frozen cohort and the
    flat model scored best (strategy-research/gate_level_check.py), so the offered number matters only
    through x and through whole-number versus half-point lines."""
    line = np.asarray(line, float)
    x = line - np.asarray(market_total, float)
    whole = np.isclose(line % 1, 0)
    lo, mid, hi = _mid(resid_sorted, x - 0.5), _mid(resid_sorted, x), _mid(resid_sorted, x + 0.5)
    return np.where(whole, lo, mid), np.where(whole, hi - lo, 0.0)


def ev_under(line, odds, market_total, resid_sorted):
    """Expected profit per unit staked on the under at the offered `line` and American `odds`, against
    the reference total `market_total` (pushes return the stake). NaN when the line, the reference or
    the price is missing."""
    p_win, p_push = p_under_at(line, market_total, resid_sorted)
    profit = american_to_profit(odds)
    ev = p_win * profit - (1 - p_win - p_push)
    bad = np.zeros(1, bool)
    for v in (odds, line, market_total):
        bad = bad | pd.isna(pd.Series(np.atleast_1d(v))).to_numpy()
    return np.where(bad, np.nan, ev)


# --------------------------------------------------------------------------- execution timing (issue #5)
# When to place each kind of bet, from the open->close drift in strategy-research/README.md
# ("Structure and timing"). NFL 2007-21: lines moved toward the favorite in 46.8% of games and
# away in 34.4%; totals fell in 48.8% and rose in 38.8%. CFB totals in 15+ mph wind fell 1.4
# points by kickoff, and CFB totals >= the season mean + 10 rose 0.95 points. Moves don't predict
# results beyond the close, so this is advice on execution, not a signal. Identical in the
# nfl-weather and cfb-weather copies of this file.
TIMING = {
    "favorite": ("now", "lines drift toward favorites before kickoff"),
    "underdog": ("later", "lines drift toward favorites, so underdogs get more points near kickoff"),
    "under": ("now", "totals drift down before kickoff"),
    "over": ("later", "totals drift down before kickoff"),
    "high_total_under": ("at the close", "CFB high totals rise about a point before kickoff"),
}


def timing_note(side):
    """One line of execution advice for a bet on `side` (a TIMING key)."""
    when, why = TIMING[side]
    return f"Timing: bet {when}; {why}."


def cost_of_waiting(entries, fills):
    """Paper fills (data/forward/fills.csv: game_id, rule, line, price) joined to each rule's
    alert-time entry (game_id, rule, entry_line, entry_price). For unders, pts_gained > 0 and
    profit_gained > 0 mean the fill beat the alert-time quote."""
    f = fills.merge(entries, on=["game_id", "rule"], how="inner")
    return f.assign(pts_gained=f.line - f.entry_line,
                    profit_gained=american_to_profit(f.price) - american_to_profit(f.entry_price))
