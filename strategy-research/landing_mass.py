"""Landing-mass tables for key numbers (issue #52): P(final total = k | market total T), and
P(favorite's margin = k | spread s), and whether they price the closing line better than the registered
residual model.

The registered pricing model (nfl-weather amendment 5, cfb-weather amendment 3; `p_under_at` in each
project's market.py) prices an under from the residual d = final total - market total, pooled over
every total. It is imported here, never copied or edited. It gets pushes right by line type, but its
chance of a push at a whole-number line is the same at 41 as at 42. A landing-mass table lets some
final totals (and margins) be more common than their neighbours.

THE TABLE (primary specification, declared before any out-of-sample result was computed)
  P(final = k | T) is proportional to f(k - T) * g(k):
  * f, the shape: the residuals the residual model itself uses (the same cohort, the same training
    seasons), smoothed with a Gaussian kernel of bandwidth h = 2 points. Smoothing removes the lumps
    that pooling over many totals leaves behind, and lets whole-number and half-point lines share one
    curve.
  * g, the landing multipliers: for each final total k, the number of training games that landed on
    k divided by the number the smooth curve alone expects (O_k / E_k, with E_k summed over each
    game's own market total), shrunk toward 1 by empirical Bayes: g = 1 + B (O/E - 1), with
    B = tau^2 / (tau^2 + 1/E_k) and tau^2 the spread of O/E beyond Poisson noise, over the k with
    E_k >= 10. g is fitted on ALL games in the landing window (NFL 2015 on, after the longer extra
    point; CFB 2006 on, the registered window), and the same g is used for the windy cohort, whose
    shape f comes from windy games only. So the only difference from the residual model is the
    smoothing and the landing multipliers.
  * Margins: the same, in the favorite's orientation (s = |spread|, margin = favorite's points minus
    the underdog's), with g symmetric (a favorite and an underdog winning by 3 share one multiplier).

THE TEST (step 2 of the issue)
  Leave-one-season-out: each season is predicted from a table and a residual model fitted without it.
  Both models see the same training seasons. The residual model trains on its registered window
  (NFL 1999 on, CFB 2006 on) minus the held-out season, on its registered cohort definition:
  all games, or outdoor games with observed wind 15+ mph ("windy").
  Held-out seasons: NFL 2015-2025 (the landing window); CFB 2006-2025. CFB closing totals that sit on
  a quarter point (a split consensus, 5.8% of games) are left out of the test sets of both models.
  Two metrics, at the closing line:
    * P(under wins): binary log loss, every test game (a push counts as not a win);
    * P(push): binary log loss, whole-number closing lines only (a half-point line can't push, and
      both models say so).
  Differences are table minus residual (negative = the table is better), averaged per game, with a
  season-cluster standard error and a 95% interval from resampling seasons (20,000 draws).

DECISION RULE (declared before any result was computed)
  On the primary specification only, for each sport, cohort and metric: the table BEATS the residual
  model when the upper end of the 95% season-bootstrap interval is below zero; it LOSES when the lower
  end is above zero; otherwise NO DIFFERENCE SHOWN. Prices from the table (step 3) are claimed as
  better than the registered model's only for a sport where the table beats it on P(push) over all
  games and does not lose on P(under) over all games. Otherwise they are reported as what the table
  says, as candidates for F2 to test, and nothing more. The sensitivity variants are reported, never
  used to choose.

VARIANTS (each is a model specification on one cohort; each is read on two metrics)
  NFL totals, x2 cohorts (all, windy): primary; h = 1; h = 4; no landing multipliers (g = 1);
    era cut: landing window 1999 on, tested on 1999-2025; pure 2015: shape and landing both 2015 on  12
  CFB totals, x2 cohorts: primary; h = 1; h = 4; g = 1; era cut: landing window 2016 on,
    tested on 2016-2025                                                                               10
  NFL margins, all games: primary (with its Wong-leg calibration readout)                              1
  Registered frozen cohort as-is, windy, trained through 2023, tested on 2024-25: NFL, CFB             2
  Wong teaser legs by closing total (<= 49 and above), descriptive                                     1
  Total                                                                                              26

PRICES (step 3) come from the primary table fitted on every season (NFL shape 1999-2025, landing
2015-2025; CFB 2006-2025). The windy tables use the registered frozen cohort as their shape, so they
are the registered model plus landing multipliers.

Inputs: nfl-weather/data/processed/games.parquet, cfb-weather/data/processed/games.parquet and both
pricing_cohort.json files (read-only). No downloads and no API calls. Seasons stop at 2025.
Outputs (strategy-research/output/): landing_mass_loso.csv, landing_mass_loso_by_season.csv,
landing_mass_multipliers.csv, landing_mass_prices.csv, landing_mass_teasers.csv,
landing_mass_tables.csv, landing_mass.log

    nfl-weather/.venv/bin/python strategy-research/landing_mass.py [--no-save]
"""
import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "strategy-research" / "output"
sys.path.insert(0, str(ROOT / "nfl-weather"))
sys.path.insert(0, str(ROOT / "cfb-weather"))

from cfbweather import market as cfbm  # noqa: E402
from nflweather import market as nflm  # noqa: E402

WIND, LAST_FROZEN = 15, 2023              # the registered cohort: observed wind 15+ mph, through 2023
STEP = 0.125                              # every line in the data sits on an eighth-point grid
XGRID = np.arange(-160, 160 + STEP / 2, STEP)
K_TOTAL = np.arange(0, 201)
K_MARGIN = np.arange(-120, 121)
H_PRIMARY = 2.0
N_BOOT, SEED = 20000, 52
NFL_KEY_TOTALS = (37, 41, 44, 47, 51)
NFL_KEY_SPREADS = (3, 6, 7, 10)
LOG = []


def say(*a):
    s = " ".join(str(x) for x in a)
    print(s)
    LOG.append(s)


# --------------------------------------------------------------------------- the table
def smooth(resid, h):
    """Gaussian-kernel density of the residuals on XGRID (normalised to sum to 1)."""
    resid = np.asarray(resid, float)
    idx = np.round((resid - XGRID[0]) / STEP).astype(int)
    assert np.allclose(XGRID[idx], resid), "a residual is off the eighth-point grid"
    hist = np.bincount(idx, minlength=len(XGRID)).astype(float)
    half = int(np.ceil(5 * h / STEP))
    kx = np.arange(-half, half + 1) * STEP
    f = np.convolve(hist, np.exp(-0.5 * (kx / h) ** 2), mode="same")
    return f / f.sum()


def masses(T, f, g, kv):
    """Row i: P(final = k | market line T_i) over k in kv."""
    T = np.asarray(T, float)
    P = np.interp(kv[None, :] - T[:, None], XGRID, f, left=0.0, right=0.0) * g[None, :]
    return P / P.sum(1, keepdims=True)


def fit_g(T, y, f, kv, symmetric=False):
    """Empirical-Bayes landing multipliers g(k) = 1 + B_k (O_k/E_k - 1). Returns g and a frame of the pieces."""
    y = np.asarray(y)
    assert np.all(y == np.round(y)) and y.min() >= kv[0] and y.max() <= kv[-1], "an outcome is outside the table"
    E = masses(T, f, np.ones(len(kv)), kv).sum(0)
    O = np.bincount((y - kv[0]).astype(int), minlength=len(kv)).astype(float)
    if symmetric:                      # pool k with -k (kv is symmetric around 0)
        O, E = O + O[::-1], E + E[::-1]
        O[kv == 0] /= 2
        E[kv == 0] /= 2
    with np.errstate(divide="ignore", invalid="ignore"):
        r = np.where(E > 0, O / E, 1.0)
    ok = E >= 10
    tau2 = max(0.0, float(np.mean((r[ok] - 1) ** 2 - 1 / E[ok])))
    with np.errstate(divide="ignore", invalid="ignore"):
        B = np.where(E > 0, tau2 / (tau2 + 1 / E), 0.0)
    g = 1 + B * (r - 1)
    return g, pd.DataFrame(dict(k=kv, landed=O, expected=E.round(2), ratio=r.round(4), shrink=B.round(3),
                                multiplier=g.round(4), tau2=round(tau2, 5)))


def table_probs(T, f, g, kv):
    """(P(final < T), P(final = T)) at the line T itself, from the table."""
    T = np.asarray(T, float)
    P = masses(T, f, g, kv)
    return (P * (kv[None, :] < T[:, None])).sum(1), (P * np.isclose(kv[None, :], T[:, None])).sum(1)


def line_probs(L, T, f, g, kv):
    """(P(final < L), P(final = L)) for an offered line L when the market line is T, from the table."""
    P = masses(np.atleast_1d(T), f, g, kv)[0]
    return float(P[kv < L].sum()), float(P[np.isclose(kv, L)].sum())


# --------------------------------------------------------------------------- data
def registered_hash(project, package):
    txt = (ROOT / project / package / "board.py").read_text()
    return re.search(r'PRICING_COHORT_SHA256\s*=\s*"([0-9a-f]{64})"', txt).group(1)


def load():
    n = nflm.load_games(first=1999, last=2025)
    n = n[n.total.notna() & n.total_line.notna() & n.result.notna() & n.spread_line.notna()].copy()
    n["windy"] = (n.outdoor == 1) & (n.wx_wind >= WIND)
    nfl_tot = n[["game_id", "season", "total", "total_line", "windy"]].copy()
    sgn = np.where(n.spread_line >= 0, 1, -1)
    nfl_mar = pd.DataFrame(dict(game_id=n.game_id, season=n.season, total=n.result * sgn,
                                total_line=n.spread_line.abs(), windy=False, closing_total=n.total_line))
    c = cfbm.load_games(2006, 2025)
    c = c[c.total.notna() & c.total_line.notna()].copy()
    c["windy"] = (c.outdoor == 1) & (c.wx_wind >= WIND)
    cfb_tot = c[["game_id", "season", "total", "total_line", "windy"]].copy()
    return nfl_tot, nfl_mar, cfb_tot


def check_registered(mod, d, project, package):
    """The windy cohort through 2023, built here, must hash to the registered frozen cohort."""
    reg = registered_hash(project, package)
    frozen = mod.pricing_cohort(reg)
    mine = mod.cohort_residuals(d[d.season <= LAST_FROZEN], d[d.season <= LAST_FROZEN].windy)
    ok = mod.cohort_hash(mine) == reg
    say(f"{package}: registered cohort n={len(frozen)}, rebuilt here n={len(mine)}, hashes match: {ok}")
    assert ok, "the windy cohort definition here is not the registered one"
    return frozen


# --------------------------------------------------------------------------- leave-one-season-out
@dataclass
class Spec:
    name: str
    h: float = H_PRIMARY
    use_g: bool = True
    f_from: int = 0          # first season of the shape's training data (0 = the registered window)
    g_from: int = 0          # first season of the landing window
    eval_from: int = 0
    eval_to: int = 2025


def is_testable(T):
    return np.isclose((np.asarray(T, float) * 2) % 1, 0)       # whole or half point


def loso(d, mod, sport, market, cohort, spec, base_from, kv, symmetric, legs=None):
    rows, gcache = [], {}
    for s in range(spec.eval_from, spec.eval_to + 1):
        tr = d[(d.season != s) & (d.season >= base_from)]
        te = d[(d.season == s) & is_testable(d.total_line)]
        cmask_tr = tr.windy if cohort == "windy" else np.ones(len(tr), bool)
        if cohort == "windy":
            te = te[te.windy]
        if te.empty:
            continue
        resid = mod.cohort_residuals(tr, cmask_tr)
        T = te.total_line.to_numpy(float)
        pr_u, pr_p = (np.atleast_1d(v) for v in mod.p_under_at(T, T, resid))
        f_from = spec.f_from or base_from
        fr = tr[tr.season >= f_from]
        fmask = fr.windy if cohort == "windy" else np.ones(len(fr), bool)
        f = smooth((fr.total - fr.total_line)[fmask], spec.h)
        if spec.use_g:
            key = (s, spec.h, spec.g_from)
            if key not in gcache:
                gw = tr[tr.season >= spec.g_from]
                gcache[key] = fit_g(gw.total_line, gw.total, smooth(gw.total - gw.total_line, spec.h), kv, symmetric)[0]
            g = gcache[key]
        else:
            g = np.ones(len(kv))
        pt_u, pt_p = table_probs(T, f, g, kv)
        rows.append(pd.DataFrame(dict(sport=sport, market=market, cohort=cohort, variant=spec.name, season=s,
                                      game_id=te.game_id.values, line=T, final=te.total.values,
                                      whole=np.isclose(T % 1, 0), under=te.total.values < T,
                                      push=te.total.values == T, table_under=pt_u, table_push=pt_p,
                                      resid_under=pr_u, resid_push=pr_p)))
        if legs is not None:
            legs.append(wong_leg_preds(te, f, g, kv, resid, mod, s))
    return pd.concat(rows, ignore_index=True)


def frozen_check(d, mod, sport, frozen, g_from, kv):
    """The registered file as it is, against the table trained through 2023, on windy 2024-25 games."""
    tr = d[(d.season >= g_from) & (d.season <= LAST_FROZEN)]
    g = fit_g(tr.total_line, tr.total, smooth(tr.total - tr.total_line, H_PRIMARY), kv)[0]
    f = smooth(frozen, H_PRIMARY)
    te = d[(d.season > LAST_FROZEN) & d.windy & is_testable(d.total_line)]
    T = te.total_line.to_numpy(float)
    pr_u, pr_p = mod.p_under_at(T, T, frozen)
    pt_u, pt_p = table_probs(T, f, g, kv)
    return pd.DataFrame(dict(sport=sport, market="total", cohort="windy", variant="frozen file, 2024-25",
                             season=te.season.values, game_id=te.game_id.values, line=T, final=te.total.values,
                             whole=np.isclose(T % 1, 0), under=te.total.values < T, push=te.total.values == T,
                             table_under=pt_u, table_push=pt_p, resid_under=pr_u, resid_push=pr_p))


def ll(p, o):
    p = np.clip(np.asarray(p, float), 1e-9, 1 - 1e-9)
    o = np.asarray(o, bool)
    return -np.where(o, np.log(p), np.log(1 - p))


def compare(sub, metric, rng, by_game=False):
    if metric == "push":
        sub = sub[sub.whole]
        o, pt, pr = sub.push, sub.table_push, sub.resid_push
    else:
        o, pt, pr = sub.under, sub.table_under, sub.resid_under
    lt, lr = ll(pt, o), ll(pr, o)
    dd = pd.DataFrame(dict(season=sub.season.values, d=lt - lr, lt=lt, lr=lr))
    N = len(dd)
    mean = dd.d.mean()
    by = dd.groupby("season").agg(D=("d", "sum"), n=("d", "size"), lt=("lt", "mean"), lr=("lr", "mean"))
    S = len(by)
    if by_game or S < 5:           # too few seasons to resample: resample games instead
        se = dd.d.std(ddof=1) / np.sqrt(N)
        idx = rng.integers(0, N, (N_BOOT, N))
        boot = dd.d.to_numpy()[idx].mean(1)
        unit = "games"
    else:
        se = np.sqrt(S / (S - 1) * ((by.D - by.n * mean) ** 2).sum()) / N
        idx = rng.integers(0, S, (N_BOOT, S))
        boot = by.D.to_numpy()[idx].sum(1) / by.n.to_numpy()[idx].sum(1)
        unit = "seasons"
    lo, hi = np.percentile(boot, [2.5, 97.5])
    verdict = "table beats" if hi < 0 else "table loses" if lo > 0 else "no difference shown"
    out = dict(games=N, events=int(o.sum()), seasons=S, ll_table=lt.mean(), ll_resid=lr.mean(), diff=mean,
               diff_pct=100 * mean / lr.mean(), se=se, ci_lo=lo, ci_hi=hi, resampled=unit,
               p_two_sided=2 * stats.norm.sf(abs(mean / se)) if se > 0 else np.nan,
               seasons_table_better=int((by.D < 0).sum()), verdict=verdict)
    return out, by.reset_index().assign(metric=metric)


# --------------------------------------------------------------------------- prices
def fair_american(p_win, p_push):
    """No-vig American price at which the bet has zero expected value (pushes return the stake)."""
    b = (1 - p_win - p_push) / p_win
    return -100 / b if b < 1 else 100 * b


def cents(a):
    """Distance from even money in 'cents' (-110 -> -10, +105 -> +5)."""
    return a + 100 if a < 0 else a - 100


def total_ladder(sport, cohort, Ks, f, g, kv, resid, mod, raw):
    rows = []
    for K in Ks:
        for model in ("table", "residual"):
            prev = None
            for L in np.arange(K - 1.5, K + 1.51, 0.5):
                if model == "table":
                    pu, pp = line_probs(L, K, f, g, kv)
                else:
                    pu, pp = (float(np.atleast_1d(v)[0]) for v in mod.p_under_at(L, K, resid))
                po = 1 - pu - pp
                fu, fo = fair_american(pu, pp), fair_american(po, pp)
                row = dict(sport=sport, market="total", cohort=cohort, key=K, market_line=K, model=model, line=L,
                           p_under_win=round(pu, 4), p_push=round(pp, 4), p_over_win=round(po, 4),
                           fair_under=round(fu), fair_over=round(fo),
                           half_point_below_worth_cents=round(cents(prev) - cents(fu), 1) if prev is not None else np.nan)
                prev = fu
                rows.append(row)
        n_raw = raw[(raw.total_line >= K - 0.5) & (raw.total_line <= K + 0.5)]
        rows.append(dict(sport=sport, market="total", cohort=cohort, key=K, market_line=K, model="raw frequency",
                         line=K, p_push=round(float((n_raw.total == K).mean()), 4), raw_games=len(n_raw),
                         raw_landed=int((n_raw.total == K).sum())))
    return rows


def spread_ladder(Ks, f, g, kv, resid, mod, raw):
    """Favorite's lines around each key margin K, when the market spread is K (favorite -K)."""
    rows = []
    for K in Ks:
        for model in ("table", "residual"):
            prev = None
            for L in np.arange(K - 1.5, K + 1.51, 0.5):
                if model == "table":
                    pdog, pp = line_probs(L, K, f, g, kv)
                else:
                    pdog, pp = (float(np.atleast_1d(v)[0]) for v in mod.p_under_at(L, K, resid))
                pfav = 1 - pdog - pp
                ff, fd = fair_american(pfav, pp), fair_american(pdog, pp)
                rows.append(dict(sport="NFL", market="spread", cohort="all", key=K, market_line=K, model=model, line=L,
                                 p_favorite_covers=round(pfav, 4), p_push=round(pp, 4), p_underdog_covers=round(pdog, 4),
                                 fair_favorite=round(ff), fair_underdog=round(fd),
                                 half_point_below_worth_cents=round(cents(ff) - cents(prev), 1) if prev is not None else np.nan))
                prev = ff
        for lab, lo, hi in (("raw 2015-2025", 2015, 2025), ("raw 2015-2019", 2015, 2019), ("raw 2020-2025", 2020, 2025),
                            ("raw 1999-2014", 1999, 2014)):
            r = raw[raw.season.between(lo, hi) & (raw.total_line >= K - 0.5) & (raw.total_line <= K + 0.5)]
            rows.append(dict(sport="NFL", market="spread", cohort="all", key=K, market_line=K, model=lab, line=K,
                             p_push=round(float((r.total == K).mean()), 4), raw_games=len(r),
                             raw_landed=int((r.total == K).sum())))
    return rows


WONG = [("favorite", s, s - 6) for s in (7.5, 8.0, 8.5)] + [("underdog", s, s + 6) for s in (1.5, 2.0, 2.5)]


def leg_outcome(side, m, L):
    return np.where(m == L, "push", np.where((m > L) if side == "favorite" else (m < L), "win", "loss"))


def wong_leg_preds(te, f, g, kv, resid, mod, season):
    rows = []
    for side, s, L in WONG:
        x = te[np.isclose(te.total_line, s)]
        if x.empty:
            continue
        pb, pp = line_probs(L, s, f, g, kv)
        rb, rp = (float(np.atleast_1d(v)[0]) for v in mod.p_under_at(L, s, resid))
        tw, rw = ((1 - pb - pp, 1 - rb - rp) if side == "favorite" else (pb, rb))
        rows.append(pd.DataFrame(dict(season=season, side=side, spread=s, teased_to=L, outcome=leg_outcome(side, x.total.values, L),
                                      table_win=tw, table_push=pp, resid_win=rw, resid_push=rp)))
    return pd.concat(rows) if rows else pd.DataFrame()


def breakeven(decimal_payout, legs):
    return decimal_payout ** (-1 / legs)


def dec(american):
    return 1 + (100 / abs(american) if american < 0 else american / 100)


# --------------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-save", action="store_true")
    args = ap.parse_args()
    pd.set_option("display.width", 250)
    pd.set_option("display.max_columns", 40)
    rng = np.random.default_rng(SEED)
    nfl_tot, nfl_mar, cfb_tot = load()
    say(f"NFL games 1999-2025: {len(nfl_tot)} ({int(nfl_tot.windy.sum())} windy). "
        f"CFB games 2006-2025: {len(cfb_tot)} ({int(cfb_tot.windy.sum())} windy); "
        f"quarter-point CFB closes left out of every test set: {int((~is_testable(cfb_tot.total_line)).sum())}")
    nfl_frozen = check_registered(nflm, nfl_tot, "nfl-weather", "nflweather")
    cfb_frozen = check_registered(cfbm, cfb_tot, "cfb-weather", "cfbweather")

    nfl_specs = [Spec("primary", g_from=2015, eval_from=2015), Spec("h = 1", h=1, g_from=2015, eval_from=2015),
                 Spec("h = 4", h=4, g_from=2015, eval_from=2015), Spec("no landing multipliers", use_g=False, eval_from=2015),
                 Spec("era: landing 1999 on, tested 1999-2025", g_from=1999, eval_from=1999),
                 Spec("pure 2015: shape and landing 2015 on", f_from=2015, g_from=2015, eval_from=2015)]
    cfb_specs = [Spec("primary", g_from=2006, eval_from=2006), Spec("h = 1", h=1, g_from=2006, eval_from=2006),
                 Spec("h = 4", h=4, g_from=2006, eval_from=2006), Spec("no landing multipliers", use_g=False, eval_from=2006),
                 Spec("era: landing 2016 on, tested 2016-2025", g_from=2016, eval_from=2016)]
    preds, legs = [], []
    for cohort in ("all", "windy"):
        for sp in nfl_specs:
            preds.append(loso(nfl_tot, nflm, "NFL", "total", cohort, sp, 1999, K_TOTAL, False))
        for sp in cfb_specs:
            preds.append(loso(cfb_tot, cfbm, "CFB", "total", cohort, sp, 2006, K_TOTAL, False))
    preds.append(loso(nfl_mar, nflm, "NFL", "spread", "all", Spec("primary", g_from=2015, eval_from=2015), 1999,
                      K_MARGIN, True, legs=legs))
    preds.append(frozen_check(nfl_tot, nflm, "NFL", nfl_frozen, 2015, K_TOTAL))
    preds.append(frozen_check(cfb_tot, cfbm, "CFB", cfb_frozen, 2006, K_TOTAL))
    P = pd.concat(preds, ignore_index=True)

    res, seasons = [], []
    for (sport, market, cohort, variant), sub in P.groupby(["sport", "market", "cohort", "variant"], sort=False):
        for metric in ("under", "push"):
            o, by = compare(sub, metric, rng)
            res.append(dict(sport=sport, market=market, cohort=cohort, variant=variant, metric=metric,
                            tested=f"{sub.season.min()}-{sub.season.max()}", **o))
            seasons.append(by.assign(sport=sport, market=market, cohort=cohort, variant=variant))
    R = pd.DataFrame(res)
    S = pd.concat(seasons, ignore_index=True)
    show = R.assign(ll_table=R.ll_table.round(5), ll_resid=R.ll_resid.round(5), diff=(R["diff"] * 1000).round(3),
                    diff_pct=R.diff_pct.round(2), se=(R.se * 1000).round(3), ci_lo=(R.ci_lo * 1000).round(3),
                    ci_hi=(R.ci_hi * 1000).round(3), p_two_sided=R.p_two_sided.round(4))
    say("\n===== Leave-one-season-out log loss at the closing line (diff, se, ci in thousandths; negative = table better)")
    say(show.drop(columns=["resampled"]).to_string(index=False))

    # Wong legs, held-out seasons
    L = pd.concat(legs, ignore_index=True)
    say("\n===== Wong teaser legs in held-out seasons 2015-2025 (margin table vs residual analog, both left-one-season-out)")
    wl = []
    for side, x in list(L.groupby("side")) + [("both", L)]:
        w, p, lo_ = (x.outcome == "win").sum(), (x.outcome == "push").sum(), (x.outcome == "loss").sum()
        tw = (x.table_win / (1 - x.table_push)).mean()
        rw = (x.resid_win / (1 - x.resid_push)).mean()
        wl.append(dict(side=side, legs=len(x), won=int(w), pushed=int(p), lost=int(lo_), actual_win_rate=w / (w + lo_),
                       table_predicted=tw, residual_predicted=rw))
    say(pd.DataFrame(wl).round(4).to_string(index=False))

    # ---------------- full fits for the prices
    kvt, kvm = K_TOTAL, K_MARGIN
    mult = []
    gw = nfl_tot[nfl_tot.season >= 2015]
    g_nfl, gt = fit_g(gw.total_line, gw.total, smooth(gw.total - gw.total_line, H_PRIMARY), kvt)
    mult.append(gt.assign(sport="NFL", market="total", window="2015-2025"))
    gw = cfb_tot
    g_cfb, gt = fit_g(gw.total_line, gw.total, smooth(gw.total - gw.total_line, H_PRIMARY), kvt)
    mult.append(gt.assign(sport="CFB", market="total", window="2006-2025"))
    gw = nfl_mar[nfl_mar.season >= 2015]
    g_mar, gt = fit_g(gw.total_line, gw.total, smooth(gw.total - gw.total_line, H_PRIMARY), kvm, symmetric=True)
    mult.append(gt.assign(sport="NFL", market="margin", window="2015-2025"))
    M = pd.concat(mult, ignore_index=True)
    say("\n===== Landing multipliers (full data), NFL totals 30-60")
    say(M[(M.sport == "NFL") & (M.market == "total") & M.k.between(30, 60)][["k", "landed", "expected", "ratio", "multiplier"]]
        .to_string(index=False))
    say("\n===== Landing multipliers, NFL margins 0-21 (favorite's view, pooled with the underdog's)")
    say(M[(M.market == "margin") & M.k.between(0, 21)][["k", "landed", "expected", "ratio", "multiplier"]].to_string(index=False))
    say("\n===== Landing multipliers, CFB totals 35-80")
    say(M[(M.sport == "CFB") & M.k.between(35, 80)][["k", "landed", "expected", "ratio", "multiplier"]].to_string(index=False))
    say(f"tau^2: NFL totals {M[(M.sport == 'NFL') & (M.market == 'total')].tau2.iloc[0]}, "
        f"NFL margins {M[M.market == 'margin'].tau2.iloc[0]}, CFB totals {M[M.sport == 'CFB'].tau2.iloc[0]}")

    f_nfl_all = smooth(nfl_tot.total - nfl_tot.total_line, H_PRIMARY)
    r_nfl_all = nflm.cohort_residuals(nfl_tot, np.ones(len(nfl_tot), bool))
    f_nfl_w = smooth(nfl_frozen, H_PRIMARY)
    f_cfb_all = smooth(cfb_tot.total - cfb_tot.total_line, H_PRIMARY)
    r_cfb_all = cfbm.cohort_residuals(cfb_tot, np.ones(len(cfb_tot), bool))
    f_cfb_w = smooth(cfb_frozen, H_PRIMARY)
    f_mar = smooth(nfl_mar.total - nfl_mar.total_line, H_PRIMARY)
    r_mar = nflm.cohort_residuals(nfl_mar, np.ones(len(nfl_mar), bool))
    raw_n = nfl_tot[nfl_tot.season >= 2015]
    raw_c = cfb_tot
    rows = []
    rows += total_ladder("NFL", "all", range(30, 61), f_nfl_all, g_nfl, kvt, r_nfl_all, nflm, raw_n)
    rows += total_ladder("NFL", "windy", range(30, 61), f_nfl_w, g_nfl, kvt, nfl_frozen, nflm, raw_n[raw_n.windy])
    rows += total_ladder("CFB", "all", range(35, 81), f_cfb_all, g_cfb, kvt, r_cfb_all, cfbm, raw_c)
    rows += total_ladder("CFB", "windy", range(35, 81), f_cfb_w, g_cfb, kvt, cfb_frozen, cfbm, raw_c[raw_c.windy])
    rows += spread_ladder(range(1, 18), f_mar, g_mar, kvm, r_mar, nflm, nfl_mar)
    PR = pd.DataFrame(rows)

    def at_key(sport, market, cohort, Ks):
        x = PR[(PR.sport == sport) & (PR.market == market) & (PR.cohort == cohort) & PR.key.isin(Ks) & (PR.line == PR.key)]
        return x.pivot_table(index="key", columns="model", values="p_push", aggfunc="first")

    for sport, cohort, Ks in (("NFL", "all", NFL_KEY_TOTALS), ("NFL", "windy", NFL_KEY_TOTALS)):
        say(f"\n===== {sport} {cohort}: P(final = K | market total K)")
        say(at_key(sport, "total", cohort, Ks).round(4).to_string())
    say("\n===== NFL spreads: P(favorite wins by exactly K | favorite -K)")
    say(at_key("NFL", "spread", "all", NFL_KEY_SPREADS).round(4).to_string())
    say("\n===== Half-point worth in cents of fair (no-vig) price, at a market line on the key number K:"
        "\n      'onto' = K-0.5 to K for an under (K+0.5 to K for a favorite); 'off' = K to K+0.5 for an under (K to K-0.5 for a favorite)")
    for (sport, market, cohort), x in PR[PR.model.isin(["table", "residual"])].groupby(["sport", "market", "cohort"], sort=False):
        keys = NFL_KEY_TOTALS if (sport == "NFL" and market == "total") else NFL_KEY_SPREADS if market == "spread" else (45, 48, 51, 52, 55)
        out = []
        for K in keys:
            for model in ("table", "residual"):
                y = x[(x.key == K) & (x.model == model)].set_index("line").half_point_below_worth_cents
                out.append(dict(key=K, model=model, onto=y.get(K + 0.5 if market == "spread" else K),
                                off=y.get(K if market == "spread" else K + 0.5)))
        say(f"-- {sport} {market} {cohort}")
        say(pd.DataFrame(out).pivot_table(index="key", columns="model", values=["onto", "off"]).to_string())

    # ---------------- Wong teaser legs, full table and raw 2015-2025
    tz = []
    for side, s, Lt in WONG:
        pb, pp = line_probs(Lt, s, f_mar, g_mar, kvm)
        tw = 1 - pb - pp if side == "favorite" else pb
        for lab, sel in (("all totals", nfl_mar.closing_total > 0), ("closing total <= 49", nfl_mar.closing_total <= 49),
                         ("closing total > 49", nfl_mar.closing_total > 49)):
            x = nfl_mar[(nfl_mar.season >= 2015) & np.isclose(nfl_mar.total_line, s) & sel]
            oc = leg_outcome(side, x.total.values, Lt)
            w, p, lo_ = (oc == "win").sum(), (oc == "push").sum(), (oc == "loss").sum()
            tz.append(dict(side=side, spread=s, teased_to=Lt, totals=lab, table_win=round(tw, 4), table_push=round(pp, 4),
                           table_win_ex_push=round(tw / (1 - pp), 4), legs_2015_2025=len(x), won=int(w), pushed=int(p),
                           lost=int(lo_), actual_win_ex_push=round(w / (w + lo_), 4) if w + lo_ else np.nan))
    TZ = pd.DataFrame(tz)
    say("\n===== Wong teaser legs: the table (full fit) and the raw record 2015-2025")
    say(TZ.to_string(index=False))
    for lab in ("all totals", "closing total <= 49", "closing total > 49"):
        x = TZ[TZ.totals == lab]
        say(f"pooled, {lab}: {x.won.sum()}-{x.lost.sum()} ({x.pushed.sum()} pushes), "
            f"{x.won.sum() / (x.won.sum() + x.lost.sum()):.4f}")
    be = {f"2-team {a}": breakeven(dec(a), 2) for a in (-110, -120, -130, -140)}
    be.update({f"3-team {a:+d}": breakeven(dec(a), 3) for a in (140, 150, 160, 180)})
    say("leg break-evens: " + ", ".join(f"{k} {v:.4f}" for k, v in be.items()))

    # ---------------- the tables themselves (long format, the useful range)
    tabs = []
    for sport, market, cohort, f, g, kv, Tg, klo, khi in (
            ("NFL", "total", "all", f_nfl_all, g_nfl, kvt, np.arange(30, 60.01, 0.5), 10, 90),
            ("NFL", "total", "windy", f_nfl_w, g_nfl, kvt, np.arange(30, 60.01, 0.5), 10, 90),
            ("CFB", "total", "all", f_cfb_all, g_cfb, kvt, np.arange(35, 80.01, 0.5), 5, 130),
            ("CFB", "total", "windy", f_cfb_w, g_cfb, kvt, np.arange(35, 80.01, 0.5), 5, 130),
            ("NFL", "margin", "all", f_mar, g_mar, kvm, np.arange(0, 20.01, 0.5), -40, 60)):
        Pm = masses(Tg, f, g, kv)
        keep = (kv >= klo) & (kv <= khi)
        wide = pd.DataFrame(Pm[:, keep].round(5), columns=[str(k) for k in kv[keep]])
        wide.insert(0, "market_line", Tg)
        wide.insert(0, "cohort", cohort)
        wide.insert(0, "market", market)
        wide.insert(0, "sport", sport)
        tabs.append(wide)
    TAB = pd.concat(tabs, ignore_index=True)

    say("\nvariants: 26 (see the docstring); running count before this script: 200")
    if not args.no_save:
        R.to_csv(OUT / "landing_mass_loso.csv", index=False)
        S.to_csv(OUT / "landing_mass_loso_by_season.csv", index=False)
        M.to_csv(OUT / "landing_mass_multipliers.csv", index=False)
        PR.to_csv(OUT / "landing_mass_prices.csv", index=False)
        TZ.to_csv(OUT / "landing_mass_teasers.csv", index=False)
        TAB.to_csv(OUT / "landing_mass_tables.csv", index=False)
        (OUT / "landing_mass.log").write_text("\n".join(LOG) + "\n")


if __name__ == "__main__":
    main()
