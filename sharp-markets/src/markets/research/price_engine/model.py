"""The fair price and the line conversion, from the repo's registered pricing code. Imported, never copied.

* De-vig: Shin (1993), `devig_shin` in nfl-weather/nflweather/market.py and cfb-weather/cfbweather/market.py
  (the two copies are identical). A two-way price (a, b) becomes the fair probability of side a.
* Totals at another line: the registered pricing model, `p_under_at` over the frozen residual cohort of each
  project (`pricing_cohort`, checked against the hash its PREREGISTRATION.md registers). NFL uses the NFL
  cohort, college football the CFB cohort.

The line conversion (pre-declared; strategy-research/price-engine-preregistration-draft.md). The fair price is
Pinnacle's no-vig probability q that the under wins at Pinnacle's own total L0. A two-way price ignores pushes,
so q is the chance of an under given no push. At another total L:

    P(under wins at L) = q * (1 - push0) + [w(L) - w(L0)]
    P(push at L)       = push(L)
    P(over wins at L)  = 1 - P(under wins at L) - P(push at L)

where w(.) and push(.) are the registered model's win and push chances with the reference total set to L0. Only
the probability mass the model puts between the two lines is used, not its level: the cohort is games with 15+
mph wind, whose unders win more often than the market's, and that level must not leak into a price engine that
takes Pinnacle's price as the truth. Every probability returned here is conditional on no push, like a two-way
price: P(under | no push) = P(under wins) / (P(under wins) + P(over wins)). The expected value of a bet at decimal
price d is then p * d - 1 per unit staked on bets that are decided (a push returns the stake).
"""
from __future__ import annotations

import importlib
import sys
from functools import lru_cache
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[5]      # .../value-finder (this file is sharp-markets/src/markets/research/...)
NFL, CFB = "americanfootball_nfl", "americanfootball_ncaaf"
SPORTS = (NFL, CFB)
LABEL = {NFL: "NFL", CFB: "CFB"}
# (package, project folder, the cohort hash each project registers: board.PRICING_COHORT_SHA256)
REGISTERED = {
    NFL: ("nflweather", "nfl-weather", "897a61b6846b077b71c324dc0c2f4b2e28bda963aa69d0cc4a89f181eb039556"),
    CFB: ("cfbweather", "cfb-weather", "c49a6649c3f86ac1280ed488f675c14859b23073c1aa8e18aab63060b38bff67"),
}


@lru_cache
def registered(sport: str):
    """(the project's market module, its registered residual cohort). Raises if the cohort file isn't the
    registered one, so the backtest can't price from a cohort nobody registered."""
    pkg, folder, sha = REGISTERED[sport]
    path = str(REPO / folder)
    if path not in sys.path:
        sys.path.append(path)
    mod = importlib.import_module(f"{pkg}.market")
    return mod, mod.pricing_cohort(sha)


def shin(dec_a, dec_b, sport: str = NFL) -> np.ndarray:
    """Fair probability of side a from two decimal prices (Shin de-vig). NaN where a price is missing or <= 1, or
    where the de-vig can't solve (both sides' fair probabilities must sum to 1; the registered bisection covers
    margins far beyond any real two-way market, about 30% and more, so this only catches broken quotes)."""
    a, b = np.asarray(dec_a, float), np.asarray(dec_b, float)
    ok = (a > 1) & (b > 1)
    mod, _ = registered(sport)
    with np.errstate(divide="ignore", invalid="ignore"):
        pa, pb = np.where(ok, 1 / a, 0.5), np.where(ok, 1 / b, 0.5)
        qa, qb = mod.devig_shin(pa, pb), mod.devig_shin(pb, pa)
    return np.where(ok & (np.abs(qa + qb - 1) < 1e-6), qa, np.nan)


def under_at(q_under, ref_line, line, sport: str) -> np.ndarray:
    """P(under | no push) at total `line`, given the fair P(under | no push) `q_under` at the reference total
    `ref_line` (Pinnacle's). Same line: q_under itself. NaN where any input is missing."""
    q, ref, ln = (np.atleast_1d(np.asarray(v, float)) for v in (q_under, ref_line, line))
    q, ref, ln = np.broadcast_arrays(q, ref, ln)
    out = np.full(q.shape, np.nan)
    ok = ~(np.isnan(q) | np.isnan(ref) | np.isnan(ln))
    same = ok & np.isclose(ref, ln)
    out[same] = q[same]
    move = ok & ~same
    if move.any():
        mod, resid = registered(sport)
        w0, u0 = (np.atleast_1d(v) for v in mod.p_under_at(ref[move], ref[move], resid))
        wl, ul = (np.atleast_1d(v) for v in mod.p_under_at(ln[move], ref[move], resid))
        win = np.clip(q[move] * (1 - u0) + (wl - w0), 0.0, 1.0 - ul)
        lose = np.clip(1.0 - win - ul, 0.0, 1.0)
        with np.errstate(divide="ignore", invalid="ignore"):
            out[move] = np.where(win + lose > 0, win / (win + lose), np.nan)
    return out


def ev(p, dec) -> np.ndarray:
    """Expected profit per unit staked on a decided bet: p * d - 1."""
    return np.asarray(p, float) * np.asarray(dec, float) - 1.0
