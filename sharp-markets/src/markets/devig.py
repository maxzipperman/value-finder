"""De-vig and multi-book blending (pattern from reference/data/odds.py, adapted).

Proportional (multiplicative) de-vig per book; the blend renormalizes weights over the books present
and reports the cross-book standard deviation.
"""
from __future__ import annotations

import math


def devig_proportional(decimal_prices: dict[str, float]) -> dict[str, float] | None:
    """{outcome: decimal price} -> {outcome: fair probability}. None if any price is unusable."""
    if len(decimal_prices) < 2 or any(p is None or p <= 1.0 for p in decimal_prices.values()):
        return None
    implied = {k: 1.0 / p for k, p in decimal_prices.items()}
    total = sum(implied.values())
    return {k: v / total for k, v in implied.items()}


def blend(per_book: dict[str, float], weights: dict[str, float]) -> tuple[float, float, list[str]] | None:
    """Weighted blend of one outcome's fair prob across books; weights renormalized over books present."""
    used = {b: w for b, w in weights.items() if b in per_book and per_book[b] is not None}
    total_w = sum(used.values())
    if total_w <= 0:
        return None
    value = sum(per_book[b] * w for b, w in used.items()) / total_w
    vals = [per_book[b] for b in used]
    std = math.sqrt(sum((v - sum(vals) / len(vals)) ** 2 for v in vals) / (len(vals) - 1)) if len(vals) > 1 else 0.0
    return value, std, sorted(used)
