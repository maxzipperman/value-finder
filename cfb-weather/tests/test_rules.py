"""Same alert/pricing probes as nfl-weather/tests/test_rules.py, for the CFB rule."""
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cfbweather.board import rule_b_status  # noqa: E402
from cfbweather.market import ev_under, p_under_at  # noqa: E402

RESID = np.sort(np.random.default_rng(0).normal(-1.0, 16.0, 900).round())


def game(**kw):
    base = dict(wx_src="forecast", wx_wind=18.0, lead_days=2, mkt_total=52.5, mkt_under=-110.0)
    base.update(kw)
    ok = base["mkt_under"] == base["mkt_under"] and base["mkt_total"] == base["mkt_total"]
    base["ev_under"] = float(ev_under(base["mkt_total"], base["mkt_under"], base["mkt_total"], RESID)[0]) if ok else np.nan
    return SimpleNamespace(**base)


def test_valid_signal():
    assert rule_b_status(game()) == "SIGNAL"


@pytest.mark.parametrize("kw,expected", [
    (dict(mkt_total=np.nan), "no_price"), (dict(mkt_under=-160.0), "price_too_high"),
    (dict(lead_days=0), "outside_horizon"), (dict(lead_days=8), "outside_horizon"),
    (dict(wx_wind=12.0), "no_trigger"), (dict(wx_src="indoor"), "not_outdoor"), (dict(wx_src="time_tbd"), "time_tbd"),
])
def test_no_actionable_signal(kw, expected):
    assert rule_b_status(game(**kw)) == expected


def test_probability_depends_on_line():
    p = [p_under_at(L, 52.5, RESID)[0] for L in (40, 50, 52.5, 55, 65)]
    assert all(a < b for a, b in zip(p, p[1:]))
