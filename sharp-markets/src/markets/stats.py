"""Small statistics helpers (OLS with HC1 errors, mean +/- SE). Floats are fine here; money stays DECIMAL."""
from __future__ import annotations

import math

import numpy as np


def normal_p(t: float) -> float:
    """Two-sided p-value under a normal approximation."""
    return math.erfc(abs(t) / math.sqrt(2))


def ols_hc1(y, X, names: list[str]) -> list[dict]:
    """OLS with heteroskedasticity-robust (HC1) standard errors. X excludes the constant."""
    y = np.asarray(y, dtype=float)
    X = np.column_stack([np.ones(len(y)), np.asarray(X, dtype=float)])
    n, k = X.shape
    XtX_inv = np.linalg.pinv(X.T @ X)
    beta = XtX_inv @ X.T @ y
    resid = y - X @ beta
    meat = (X * resid[:, None] ** 2).T @ X
    cov = XtX_inv @ meat @ XtX_inv * n / max(n - k, 1)
    se = np.sqrt(np.clip(np.diag(cov), 0, None))
    out = []
    for name, b, s in zip(["const", *names], beta, se):
        t = b / s if s > 0 else float("nan")
        out.append({"term": name, "coef": float(b), "se": float(s), "t": float(t),
                    "p": normal_p(t) if s > 0 else float("nan"), "n": int(n)})
    return out


def mean_se(values) -> tuple[float, float, int]:
    v = np.asarray([x for x in values if x is not None and not (isinstance(x, float) and math.isnan(x))], dtype=float)
    if len(v) == 0:
        return float("nan"), float("nan"), 0
    se = v.std(ddof=1) / math.sqrt(len(v)) if len(v) > 1 else float("nan")
    return float(v.mean()), float(se), int(len(v))
