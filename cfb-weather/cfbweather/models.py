"""Copied from nfl-weather; keep the two in sync.

Thin wrappers around pyfixest for batches of fixed-effects regressions."""
from __future__ import annotations

import warnings

import numpy as np
import pandas as pd
import pyfixest as pf

warnings.filterwarnings("ignore")


def safe_log(x):
    x = pd.to_numeric(x, errors="coerce").astype(float)
    return np.log(x.where(x > 0))


def fit(df, y, x, fe=None, vcov="hetero", method="ols"):
    """One regression -> tidy frame (outcome, term, coef, se, p, lo, hi, n, r2)."""
    cols = [y] + list(x) + (fe or [])
    if isinstance(vcov, dict):
        cols += list(vcov.values())
    d = df[list(dict.fromkeys(cols))].replace([np.inf, -np.inf], np.nan).dropna()
    fml = f"{y} ~ {' + '.join(x)}" + (f" | {' + '.join(fe)}" if fe else "")
    m = pf.feols(fml, data=d, vcov=vcov) if method == "ols" else pf.fepois(fml, data=d, vcov=vcov)
    t = m.tidy().reset_index().rename(columns={
        "Coefficient": "term", "Estimate": "coef", "Std. Error": "se", "Pr(>|t|)": "p",
        "2.5%": "lo", "97.5%": "hi"})
    t = t[["term", "coef", "se", "p", "lo", "hi"]]
    t.insert(0, "outcome", y)
    t["n"] = m._N
    t["r2"] = getattr(m, "_r2", np.nan)
    return t


def fit_many(df, ys, x, fe=None, vcov="hetero", method="ols", **tags):
    out = []
    for y in ys:
        try:
            out.append(fit(df, y, x, fe, vcov, method))
        except Exception as e:  # keep batch going; report which failed
            print(f"  ! {y}: {e}")
    t = pd.concat(out, ignore_index=True)
    for k, v in tags.items():
        t[k] = v
    return t


def stars(p):
    return "***" if p < 0.01 else "**" if p < 0.05 else "*" if p < 0.10 else ""
