"""The fair price and the line conversion, from the repo's registered pricing code. Imported, never copied.

* De-vig: Shin (1993), `devig_shin` in nfl-weather/nflweather/market.py and cfb-weather/cfbweather/market.py
  (the two copies are identical). A two-way price (a, b) becomes the fair probability of side a.
* Totals at another line: the registered pricing model, `p_under_at` over the frozen residual cohort of each
  project (`pricing_cohort`, checked against the hash its PREREGISTRATION.md registers). NFL uses the NFL
  cohort, college football the CFB cohort.

The line conversion (pre-declared; sharp-markets/docs/PRICE_ENGINE_PREREGISTRATION.md). The fair price is
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

import hashlib
import importlib
import json
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
    where the de-vig can't solve (both sides' fair probabilities must sum to 1). The registered bisection solves
    every overround below about 44%, except the single symmetric point at exactly 25% (1.60 / 1.60); real two-way
    markets run about 2% to 10%, so in practice this only catches broken quotes."""
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


# ---------------------------------------------------------------- spreads at another number (grading only)
# A spread close at a number other than the bet's is converted to the bet's number the same way as a total: only
# the probability mass between the two numbers moves, P(cover at L) = q * (1 - push(L0)) + [w(L) - w(L0)], with
# w(x) = P(margin + x > 0) and push(x) = P(margin + x = 0) from the declared margin table below.
#
# The table: every game in the repo's processed tables with a closing spread and a final score, from the seasons
# before the backtest (NFL 1999-2019 from nflverse, CFB 2006-2019 from the cfb-weather table), frozen in
# spread_cohort.json and checked against the hashes here. Each game is counted from both sides: (the side's
# closing spread, the side's final margin). For a reference spread L0, the margins are those of the
# SPREAD_NEIGHBORS cohort entries whose closing spread is nearest L0, ties included, so the key numbers (3 and 7 in
# the NFL) come from games priced near L0. It is used only to grade closes, never to flag a bet.
SPREAD_COHORT = Path(__file__).with_name("spread_cohort.json")
SPREAD_SEASONS = {NFL: (1999, 2019), CFB: (2006, 2019)}
SPREAD_NEIGHBORS = 1000
SPREAD_COHORT_SHA256 = {
    NFL: "19957e80dd193907d693e8bd49fb7bbcd1ef7d90ca6a22d0489c831e2c46506b",     # 5,583 games
    CFB: "63917879c6b5f2615edd243e7fee6ea260bb5ef5abe7b75e9ddc0a5d664a6fd5",     # 9,396 games
}


def spread_cohort_hash(spread, margin) -> str:
    """sha256 over the (home spread, home margin) pairs, sorted, rounded to 4 places, as 64-bit floats."""
    a = np.column_stack([np.asarray(spread, float), np.asarray(margin, float)]).round(4)
    a = a[np.lexsort((a[:, 1], a[:, 0]))]
    return hashlib.sha256(np.ascontiguousarray(a).tobytes()).hexdigest()


def spread_pairs_from_tables(sport: str) -> tuple[np.ndarray, np.ndarray]:
    """(home closing spread, home final margin) for every cohort game, from the processed tables in git."""
    import pandas as pd

    first, last = SPREAD_SEASONS[sport]
    # amendment 1, item 5: filter on the season as the file is read, so no row after the cohort's seasons (and no
    # 2026 row) reaches this code; the season check below stays as a second layer
    seasons = [("season", "in", list(range(first, last + 1)))]
    if sport == NFL:
        g = pd.read_parquet(REPO / "nfl-weather" / "data" / "processed" / "games.parquet", filters=seasons)
        g = g[g.season.between(first, last) & g.spread_line.notna() & g.result.notna()]
        spread, margin = -g.spread_line.to_numpy(float), g.result.to_numpy(float)     # spread_line: home favored by
    else:
        g = pd.read_parquet(REPO / "cfb-weather" / "data" / "processed" / "games.parquet", filters=seasons)
        g = g[g.season.between(first, last) & g.home_spread.notna() & g.result.notna()]
        spread, margin = g.home_spread.to_numpy(float), g.result.to_numpy(float)
    order = np.lexsort((margin, spread))
    return spread[order], margin[order]


def build_spread_cohort() -> dict:
    """The contents of spread_cohort.json, rebuilt from the processed tables (python -m ...model --write-spreads)."""
    out = {"definition": "(home closing spread, home final margin) for every game with both, seasons before the "
                         "2020-25 backtest; grading conversion for spread closes at another number "
                         "(sharp-markets/docs/PRICE_ENGINE_PREREGISTRATION.md, section 6)"}
    for sport in SPORTS:
        s, m = spread_pairs_from_tables(sport)
        out[sport] = {"seasons": list(SPREAD_SEASONS[sport]), "games": len(s), "sha256": spread_cohort_hash(s, m),
                      "home_spread": [float(x) for x in s], "home_margin": [int(x) for x in m]}
    return out


@lru_cache
def spread_cohort(sport: str) -> tuple[np.ndarray, np.ndarray]:
    """(the side's closing spread, the side's final margin), each game counted from both sides, from the frozen
    file. Raises if the file isn't the declared one."""
    js = json.loads(SPREAD_COHORT.read_text())[sport]
    s, m = np.asarray(js["home_spread"], float), np.asarray(js["home_margin"], float)
    got = spread_cohort_hash(s, m)
    if got != SPREAD_COHORT_SHA256[sport]:
        raise ValueError(f"{SPREAD_COHORT.name} ({LABEL[sport]}) hashes to {got[:16]}, not the declared "
                         f"{SPREAD_COHORT_SHA256[sport][:16]}")
    return np.r_[s, -s], np.r_[m, -m]


@lru_cache(maxsize=4096)
def _margins_near(sport: str, ref: float) -> np.ndarray:
    """Sorted final margins of the SPREAD_NEIGHBORS cohort entries whose closing spread is nearest `ref`, ties
    included."""
    s, m = spread_cohort(sport)
    d = np.abs(s - ref)
    k = min(SPREAD_NEIGHBORS, len(d)) - 1
    cut = np.partition(d, k)[k]
    return np.sort(m[d <= cut + 1e-9])


def _cover(margins: np.ndarray, x: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """(P(win), P(push)) for a side at its spread x, over sorted margins. A quarter line is half a bet at each
    neighbour, as in the registered totals model."""
    def at(v):
        lo = np.searchsorted(margins, -v, side="left")
        hi = np.searchsorted(margins, -v, side="right")
        n = len(margins)
        return (n - hi) / n, (hi - lo) / n
    quarter = ~np.isclose((x * 2) % 1, 0) & ~np.isclose((x * 2) % 1, 1)
    (w0, p0), (w1, p1) = at(np.where(quarter, x - 0.25, x)), at(np.where(quarter, x + 0.25, x))
    return (w0 + w1) / 2, (p0 + p1) / 2


def cover_at(q_cover, ref_line, line, sport: str) -> np.ndarray:
    """P(side covers | no push) at the side's spread `line`, given P(side covers | no push) `q_cover` at the side's
    spread `ref_line` (a close). Same line: q_cover itself. NaN where any input is missing."""
    q, ref, ln = (np.atleast_1d(np.asarray(v, float)) for v in (q_cover, ref_line, line))
    q, ref, ln = np.broadcast_arrays(q, ref, ln)
    out = np.full(q.shape, np.nan)
    ok = ~(np.isnan(q) | np.isnan(ref) | np.isnan(ln))
    same = ok & np.isclose(ref, ln)
    out[same] = q[same]
    for r in np.unique(ref[ok & ~same]):
        i = ok & ~same & (ref == r)
        margins = _margins_near(sport, float(r))
        w0, u0 = _cover(margins, np.array([r]))
        wl, ul = _cover(margins, ln[i])
        win = np.clip(q[i] * (1 - u0) + (wl - w0), 0.0, 1.0 - ul)
        lose = np.clip(1.0 - win - ul, 0.0, 1.0)
        with np.errstate(divide="ignore", invalid="ignore"):
            out[i] = np.where(win + lose > 0, win / (win + lose), np.nan)
    return out


def ev(p, dec) -> np.ndarray:
    """Expected profit per unit staked on a decided bet: p * d - 1."""
    return np.asarray(p, float) * np.asarray(dec, float) - 1.0


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="Rebuild the frozen spread margin table (spread_cohort.json)")
    ap.add_argument("--write-spreads", action="store_true", help="overwrite the file (the hashes in model.py "
                    "must then be updated, which is a dated amendment to the registered pre-registration)")
    a = ap.parse_args()
    built = build_spread_cohort()
    for sp in SPORTS:
        print(f"{LABEL[sp]}: {built[sp]['games']} games, seasons {built[sp]['seasons']}, sha256 {built[sp]['sha256']}")
    if a.write_spreads:
        SPREAD_COHORT.write_text(json.dumps(built, separators=(",", ":")) + "\n")
        print(f"wrote {SPREAD_COHORT}")
