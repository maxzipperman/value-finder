"""Does the under's chance in windy games depend on the size of the total?

The Sep 29 audit (reviews/2026-09-29-astra-audit.md, D1) found that Rule B's expected-value gate gave
the same answer at a total of 30 or 60. Before building a gate that varies with the size of the total,
this checks whether the data support one. It uses only the frozen cohorts (outdoor games, observed wind
15+ mph, seasons through 2023) and reports 2024-25 separately as a check, never for fitting.

For each sport:
  * the under rate by quarter of the closing total;
  * a logistic slope of the under on the total, and a linear slope of (final - total) on the total;
  * leave-one-season-out log loss for a kernel in the size of the total, at bandwidths 2 to 12 points,
    against the flat model (one rate for every total);
  * what each of those gates would have rejected at -115 in 2024-25, and how the kept bets did.

Result (Sep 28, 2026): no dependence in either sport. The flat model has the lowest log loss and the
slopes are indistinguishable from zero. No version rejects an NFL game at -115. In CFB the two
narrowest kernels reject 17 and 1 of 145 games, and the 17 went 10-7, so they fit noise. The registered
pricing model is therefore flat in the size of the total (nfl-weather amendment 5, cfb-weather
amendment 3). This tests the under's rate at the closing number, not the spread of the residual.

Variants: 2 (one model-selection test per sport). No downloads and no API calls.

    nfl-weather/.venv/bin/python strategy-research/gate_level_check.py [--no-save]
"""
import argparse
import importlib
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "strategy-research" / "output"
BANDWIDTHS = (2, 3, 4, 6, 8, 12, np.inf)
WIND, LAST_TRAIN, PRICE = 15, 2023, -115


def cohort(project, package, first):
    sys.path.insert(0, str(ROOT / project))
    m = importlib.import_module(f"{package}.market")
    g = m.load_games(first, 2025) if package == "cfbweather" else m.load_games(last=2025)
    sys.path.pop(0)
    for k in [k for k in sys.modules if k.startswith(package)]:
        del sys.modules[k]
    g = g[(g.outdoor == 1) & (g.wx_wind >= WIND) & g.total.notna() & g.total_line.notna()].copy()
    g["d"] = g.total - g.total_line
    return g


def rate_at(train, line, h):
    """Kernel-weighted (win, push) rates for an under at `line`; h = inf is the flat model."""
    w = np.ones(len(train)) if np.isinf(h) else np.exp(-0.5 * ((train.total_line.values - line) / h) ** 2)
    return (w * (train.d.values < 0)).sum() / w.sum(), (w * (train.d.values == 0)).sum() / w.sum()


def loso_log_loss(nz, h):
    out = []
    for s in sorted(nz.season.unique()):
        a, b = nz[nz.season != s], nz[nz.season == s]
        for line, u in zip(b.total_line.values, b.u.values):
            w = np.ones(len(a)) if np.isinf(h) else np.exp(-0.5 * ((a.total_line.values - line) / h) ** 2)
            p = np.clip((w * a.u.values).sum() / w.sum(), 0.02, 0.98)
            out.append(-(u * np.log(p) + (1 - u) * np.log(1 - p)))
    return float(np.mean(out))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-save", action="store_true")
    args = ap.parse_args()
    rows, profit = [], 100 / abs(PRICE)
    for sport, spec in (("NFL", ("nfl-weather", "nflweather", 1999)), ("CFB", ("cfb-weather", "cfbweather", 2006))):
        g = cohort(*spec)
        tr, te = g[g.season <= LAST_TRAIN], g[(g.season > LAST_TRAIN) & (g.d != 0)]
        nz = tr[tr.d != 0].copy()
        nz["u"] = (nz.d < 0).astype(int)
        print(f"\n===== {sport}: frozen cohort n={len(tr)} (through {LAST_TRAIN}); 2024-25 check n={len(te)}")
        q = pd.qcut(nz.total_line, 4, duplicates="drop")
        print(nz.groupby(q, observed=True).agg(games=("u", "size"), under_rate=("u", "mean"),
                                               final_minus_total=("d", "mean")).round(3).to_string())
        lg = sm.Logit(nz.u, sm.add_constant((nz.total_line - nz.total_line.mean()) / 10.0)).fit(disp=0)
        ol = sm.OLS(tr.d, sm.add_constant(tr.total_line - tr.total_line.mean())).fit(cov_type="HC1")
        print(f"logit slope per 10 points of total: {lg.params.iloc[1]:+.3f} (se {lg.bse.iloc[1]:.3f}, "
              f"p {lg.pvalues.iloc[1]:.3f}); final - total per point: {ol.params.iloc[1]:+.3f} "
              f"(se {ol.bse.iloc[1]:.3f}, p {ol.pvalues.iloc[1]:.3f})")
        for h in BANDWIDTHS:
            ev = []
            for line in te.total_line.values:
                pw, pp = rate_at(tr, line, h)
                ev.append(pw * profit - (1 - pw - pp))
            keep = np.array(ev) > 0
            k = te[keep]
            rows.append(dict(sport=sport, model="flat" if np.isinf(h) else f"kernel, bandwidth {h}",
                             cohort_n=len(tr), loso_log_loss=round(loso_log_loss(nz, h), 5),
                             logit_slope_per_10=round(float(lg.params.iloc[1]), 3),
                             logit_slope_p=round(float(lg.pvalues.iloc[1]), 3),
                             check_games=len(te), rejected_at_minus_115=int((~keep).sum()),
                             kept_record=f"{int((k.d < 0).sum())}-{int((k.d > 0).sum())}",
                             p_under_at_36=round(rate_at(tr, 36, h)[0], 3), p_under_at_48=round(rate_at(tr, 48, h)[0], 3),
                             p_under_at_60=round(rate_at(tr, 60, h)[0], 3)))
    res = pd.DataFrame(rows)
    pd.set_option("display.width", 220)
    print("\n" + res.to_string(index=False))
    best = res.loc[res.groupby("sport").loso_log_loss.idxmin(), ["sport", "model"]]
    print("\nlowest leave-one-season-out log loss:", dict(zip(best.sport, best.model)))
    print("break-even at -115 is 53.5%; variants: 2")
    if not args.no_save:
        res.to_csv(OUT / "gate_level_check.csv", index=False)


if __name__ == "__main__":
    main()
