"""The registered arithmetic (PREREGISTRATION_PROPS.md, 2.5 and 2.6): the three de-vig methods, the excess under
rate, its two standard errors, the one-sided p-value from the larger, and ROI at the under's price.

De-vig, with decimal odds d_over and d_under and q = 1/d:
  power (graded):           find k > 0 with q_over^k + q_under^k = 1; p = q_under^k
  additive (reported):      p = q_under - (q_over + q_under - 1) / 2
  multiplicative (reported): p = q_under / (q_over + q_under)

Excess under rate: sum(win - p) / n. Plain z: sum(win - p) / sqrt(sum p(1 - p)), so SE = sqrt(sum p(1 - p)) / n.
Clustered by game: SE = sqrt(G/(G-1) * sum_g (sum_{i in g} (win_i - p_i))^2) / n over G games. The game sums are
deliberately NOT centred on the estimated excess (the SE under the null of no excess); this is not statsmodels' CR1.
Every p-value in the decision rule is one-sided, from the larger of the two SEs. ROI: one unit a line at the under's
decimal price, sum(win (d_under - 1) - (1 - win)) / n.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
from scipy.optimize import brentq
from scipy.stats import norm


def power_k(q_over: float, q_under: float) -> float:
    """The k > 0 with q_over^k + q_under^k = 1 (both q in (0, 1))."""
    if not (0 < q_over < 1 and 0 < q_under < 1):
        raise ValueError(f"implied probabilities must be in (0, 1): {q_over}, {q_under}")
    f = lambda k: q_over ** k + q_under ** k - 1.0       # noqa: E731  (strictly decreasing in k: one root)
    lo, hi = 1e-6, 1.0
    while f(hi) > 0:
        hi *= 2.0
    return brentq(f, lo, hi, xtol=1e-15, rtol=1e-15, maxiter=500)


def devig_power(d_over: float, d_under: float) -> float:
    q_o, q_u = 1.0 / d_over, 1.0 / d_under
    return q_u ** power_k(q_o, q_u)


def devig_additive(d_over: float, d_under: float) -> float:
    q_o, q_u = 1.0 / d_over, 1.0 / d_under
    return q_u - (q_o + q_u - 1.0) / 2.0


def devig_multiplicative(d_over: float, d_under: float) -> float:
    q_o, q_u = 1.0 / d_over, 1.0 / d_under
    return q_u / (q_o + q_u)


def clustered_se(resid: np.ndarray, games: np.ndarray) -> float:
    """sqrt(G/(G-1) * sum over games of (the game's sum of residuals)^2) / n; NaN with fewer than two games."""
    n = len(resid)
    sums = pd.Series(resid).groupby(np.asarray(games)).sum().to_numpy()
    g = len(sums)
    if n == 0 or g < 2:
        return float("nan")
    return math.sqrt(g / (g - 1) * float(np.sum(sums ** 2))) / n


def one_sided_p(excess: float, se: float) -> float:
    if not (se > 0) or math.isnan(excess):
        return float("nan")
    return float(norm.sf(excess / se))


def excess_test(df: pd.DataFrame, p_col: str = "p_power") -> dict:
    """The registered statistic on graded lines (columns: win 0/1, p_power, p_add, p_mult, d_under, event_id)."""
    n = len(df)
    out = {"n": n, "games": int(df.event_id.nunique()) if n else 0}
    if n == 0:
        return {**out, **{k: float("nan") for k in ("under_wins", "under_rate", "mean_p", "excess", "se_plain",
                                                    "p_plain", "se_game", "p_game", "se_ratio", "p", "roi",
                                                    "excess_additive", "excess_multiplicative")}}
    win, p = df.win.to_numpy(float), df[p_col].to_numpy(float)
    resid = win - p
    excess = float(resid.sum() / n)
    se_plain = math.sqrt(float(np.sum(p * (1 - p)))) / n
    se_game = clustered_se(resid, df.event_id.to_numpy())
    larger = max(se_plain, se_game) if not math.isnan(se_game) else float("nan")
    roi = float(np.sum(win * (df.d_under.to_numpy(float) - 1) - (1 - win)) / n)
    return {**out, "under_wins": int(win.sum()), "under_rate": float(win.mean()), "mean_p": float(p.mean()),
            "excess": excess, "se_plain": se_plain, "p_plain": one_sided_p(excess, se_plain), "se_game": se_game,
            "p_game": one_sided_p(excess, se_game), "se_ratio": se_game / se_plain if se_plain > 0 else float("nan"),
            "p": one_sided_p(excess, larger), "roi": roi,
            "excess_additive": float((win - df.p_add.to_numpy(float)).sum() / n),
            "excess_multiplicative": float((win - df.p_mult.to_numpy(float)).sum() / n)}
