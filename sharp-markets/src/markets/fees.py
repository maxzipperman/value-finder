"""Kalshi fee model.

Verified against Kalshi docs (2026-09-27):
- fee types: 'quadratic' (taker only), 'quadratic_with_maker_fees' (maker = 0.25 x taker),
  'quadratic_with_combo_maker_fees' (maker = 0.5 x taker); taker = 0.07 x fee_multiplier x C x P x (1-P).
- Fee Rounding: each fill's trade fee is rounded UP to $0.000001; the balance change is then aligned to the
  member's precision ($0.01 for non-direct members) and a per-order fee accumulator rebates the overpayment,
  so an order's total converges to a single equivalent fill. => default rounding = per_order.
- Series multipliers change over time (GET /series/fee_changes) and events can override (GET /events/fee_changes).
"""
from __future__ import annotations

from datetime import datetime
from decimal import ROUND_CEILING, Decimal

CENT = Decimal("0.01")
MICRO = Decimal("0.000001")
TAKER_RATE = Decimal("0.07")
MAKER_RATIO = {
    "quadratic": Decimal(0),
    "quadratic_with_maker_fees": Decimal("0.25"),
    "quadratic_with_combo_maker_fees": Decimal("0.5"),
}


def D(x) -> Decimal:
    return x if isinstance(x, Decimal) else Decimal(str(x))


def ceil_to(x: Decimal, quantum: Decimal) -> Decimal:
    return (x / quantum).to_integral_value(rounding=ROUND_CEILING) * quantum


def model_fee(contracts, price, *, multiplier=1, fee_type: str = "quadratic", maker: bool = False,
              taker_rate: Decimal = TAKER_RATE) -> Decimal:
    """Unrounded fee from the fee model for one fill."""
    c, p = D(contracts), D(price)
    rate = taker_rate * D(multiplier) * (MAKER_RATIO[fee_type] if maker else 1)
    return rate * c * p * (1 - p)


def order_fee(fills: list[tuple], *, multiplier=1, fee_type: str = "quadratic", maker: bool = False,
              rounding: str = "per_order", precision: Decimal = CENT) -> Decimal:
    """Net fee for one order made of `fills` [(contracts, price), ...].

    per_order: Kalshi's accumulator behaviour (one rounding to balance precision for the whole order).
    per_fill:  every fill rounded to balance precision separately (conservative upper bound).
    none:      raw model fee (no rounding).
    """
    fills = [(D(c), D(p)) for c, p in fills if D(c) > 0]
    if not fills:
        return Decimal(0)
    kw = dict(multiplier=multiplier, fee_type=fee_type, maker=maker)
    if rounding == "none":
        return sum((model_fee(c, p, **kw) for c, p in fills), Decimal(0))
    if rounding == "per_fill":
        return sum((_net_fee(c * p, ceil_to(model_fee(c, p, **kw), MICRO), precision) for c, p in fills), Decimal(0))
    if rounding == "per_order":
        cost = sum((c * p for c, p in fills), Decimal(0))
        trade_fee = sum((ceil_to(model_fee(c, p, **kw), MICRO) for c, p in fills), Decimal(0))
        return _net_fee(cost, trade_fee, precision)
    raise ValueError(f"unknown rounding {rounding!r}")


def _net_fee(cost: Decimal, trade_fee: Decimal, precision: Decimal) -> Decimal:
    """Buyer's balance moves by -ceil(cost + fee) on the precision grid; net fee is the excess over cost."""
    return ceil_to(cost + trade_fee, precision) - cost


def fee_schedule_at(ts: datetime, *, series_fee_type: str, series_multiplier, series_changes: list[dict],
                    event_changes: list[dict] | None = None) -> tuple[str, Decimal, bool]:
    """(fee_type, multiplier, assumed) in force at `ts`.

    `assumed` is True when `ts` precedes every recorded series change, so the pre-change schedule is unknown
    and the current series values are used (flag it; don't hide it).
    """
    def effective(changes, type_key, mult_key):
        past = [c for c in changes if _ts(c["scheduled_ts"]) <= ts and c.get(mult_key) is not None]
        return max(past, key=lambda c: _ts(c["scheduled_ts"])) if past else None

    if event_changes:
        ev = effective(event_changes, "fee_type_override", "fee_multiplier_override")
        if ev:
            return ev["fee_type_override"], D(ev["fee_multiplier_override"]), False
    if series_changes:
        s = effective(series_changes, "fee_type", "fee_multiplier")
        if s:
            return s["fee_type"], D(s["fee_multiplier"]), False
        return series_fee_type, D(series_multiplier), True
    return series_fee_type, D(series_multiplier), False


def _ts(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))
