from datetime import datetime, timezone
from decimal import Decimal as D

from markets.fees import fee_schedule_at, model_fee, order_fee


def test_kalshi_doc_worked_example():
    # Kalshi "Fee Rounding" doc: buy with -$0.055 revenue and model fee $0.00363825 -> balance moves -$0.06,
    # so trade fee + rounding fee = $0.005.
    cost, model = D("0.055"), D("0.00363825")
    from markets.fees import MICRO, _net_fee, ceil_to
    assert ceil_to(model, MICRO) == D("0.003639")
    assert _net_fee(cost, ceil_to(model, MICRO), D("0.01")) == D("0.005")


def test_marketsbot_examples_taker():
    assert order_fee([(100, "0.50")]) == D("1.75")          # 0.07 * 100 * 0.25
    assert order_fee([(1, "0.50")]) == D("0.02")            # 0.0175 rounds up to 2c


def test_per_order_vs_per_fill_rounding():
    fills = [(1, "0.50")] * 3                               # three 1-lot fills in one order
    assert order_fee(fills, rounding="per_fill") == D("0.06")
    assert order_fee(fills, rounding="per_order") == D("0.06")  # 0.0525 -> 0.06 once
    fills = [(10, "0.50")] * 3                              # 0.175 each; per-fill 0.18*3 vs per-order ceil(0.525)
    assert order_fee(fills, rounding="per_fill") == D("0.54")
    assert order_fee(fills, rounding="per_order") == D("0.53")
    assert order_fee(fills, rounding="none") == D("0.525")


def test_multiplier_and_maker():
    assert model_fee(100, "0.5", multiplier=D("0.5")) == D("0.875")
    assert model_fee(100, "0.5", fee_type="quadratic_with_maker_fees", maker=True) == D("0.4375")
    assert model_fee(100, "0.5", fee_type="quadratic", maker=True) == D("0")


def test_fee_schedule_asof():
    changes = [{"scheduled_ts": "2025-10-04T07:00:00Z", "fee_multiplier": 1, "fee_type": "quadratic_with_maker_fees"},
               {"scheduled_ts": "2026-08-07T04:59:45Z", "fee_multiplier": 0.5, "fee_type": "quadratic_with_maker_fees"}]
    kw = dict(series_fee_type="quadratic_with_maker_fees", series_multiplier=0.5, series_changes=changes)
    t = lambda s: datetime.fromisoformat(s).replace(tzinfo=timezone.utc)
    assert fee_schedule_at(t("2026-01-01T00:00:00"), **kw) == ("quadratic_with_maker_fees", D("1"), False)
    assert fee_schedule_at(t("2026-09-01T00:00:00"), **kw) == ("quadratic_with_maker_fees", D("0.5"), False)
    assert fee_schedule_at(t("2025-06-01T00:00:00"), **kw)[2] is True          # before first change: assumed
    ev = [{"scheduled_ts": "2026-10-01T02:00:00Z", "fee_type_override": "quadratic_with_maker_fees", "fee_multiplier_override": 1}]
    assert fee_schedule_at(t("2026-10-01T01:59:00"), **kw, event_changes=ev)[1] == D("0.5")   # pre-game: series
    assert fee_schedule_at(t("2026-10-01T02:00:00"), **kw, event_changes=ev)[1] == D("1")     # in-game: override
