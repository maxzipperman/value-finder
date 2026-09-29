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


# ---------------------------------------------------------------- Rule HT (amendment 1, issue #4)
from cfbweather import board  # noqa: E402


def ht(**kw):
    base = dict(mkt_total=64.5, mkt_under=-110.0, ht_threshold=62.6175)
    base.update(kw)
    return SimpleNamespace(**base)


@pytest.mark.parametrize("kw,expected", [
    ({}, "SIGNAL"),
    (dict(mkt_total=62.5), "below_threshold"),
    (dict(mkt_total=63.0), "SIGNAL"),
    (dict(mkt_under=-120.0), "price_too_high"),
    (dict(mkt_total=np.nan), "no_price"),
    (dict(mkt_under=np.nan), "no_price"),
])
def test_rule_ht_status(kw, expected):
    assert board.rule_ht_status(ht(**kw)) == expected


def test_ht_2026_threshold_is_frozen_and_the_recompute_is_recorded(monkeypatch):
    """2026's threshold was frozen at 62.6175 before Week 6 (2025 mean 52.6175 + 10 on the data as it
    stood). The #36 spread fix (Sep 28) rebuilt games.parquet with a third more spread pairs, and the
    same recompute now gives 62.53: the frozen value stays, and this test pins both so a silent drift
    in either would fail."""
    assert board.HT_FROZEN[2026] == pytest.approx(62.6175, abs=1e-3)
    monkeypatch.setattr(board, "HT_FROZEN", {})                   # recompute from the processed data
    assert board.ht_threshold(2026) == pytest.approx(62.53, abs=0.02)


def test_scorer_grades_ht_at_the_last_quote(tmp_path):
    import subprocess

    import pandas as pd
    row = dict(rules_version="cfb-v2-2026-09-28", kick_et="Sat 10-10 15:30", away_team="A", home_team="B",
               venue="V", lead_days=0, wx_src="forecast", wx_wind=5, wx_temp=60, wx_precip=0, line_src="pinnacle",
               mkt_over=-110, ev_under=0.0, rule_b="no_trigger", best_under=None, best_under_book="",
               ht_threshold=62.6175, start_utc="2026-10-10T19:30:00Z")
    led = pd.DataFrame([
        dict(row, snapshot_utc="2026-10-10T11:30:00Z", game_id=1, mkt_total=63.5, mkt_under=-110, rule_ht="SIGNAL"),
        dict(row, snapshot_utc="2026-10-10T15:30:00Z", game_id=1, mkt_total=65.5, mkt_under=-105, rule_ht="SIGNAL"),
        dict(row, snapshot_utc="2026-10-10T11:30:00Z", game_id=2, mkt_total=64.0, mkt_under=-110, rule_ht="SIGNAL"),
        dict(row, snapshot_utc="2026-10-10T15:30:00Z", game_id=2, mkt_total=62.0, mkt_under=-110,
             rule_ht="below_threshold"),
        dict(row, snapshot_utc="2026-10-03T15:30:00Z", game_id=3, mkt_total=70.0, mkt_under=-110, rule_ht="SIGNAL",
             start_utc="2026-10-03T19:30:00Z"),                      # before Week 6: not graded
    ])
    sched = pd.DataFrame([dict(game_id=1, home_points=30, away_points=31), dict(game_id=2, home_points=40,
                                                                                away_points=30),
                          dict(game_id=3, home_points=10, away_points=10)])
    led.to_csv(tmp_path / "ledger.csv", index=False)
    sched.to_csv(tmp_path / "sched.csv", index=False)
    root = Path(__file__).resolve().parents[1]
    out = subprocess.run([sys.executable, str(root / "scripts" / "score_forward.py"), "--ledger",
                          str(tmp_path / "ledger.csv"), "--schedule", str(tmp_path / "sched.csv")],
                         capture_output=True, text=True, check=True).stdout
    assert "RULE_HT: 1 signals at the last quote before kickoff, 1 settled" in out
    assert "record 1-0-0" in out and "+0.95" in out               # game 1 at 65.5 / -105, not the earlier 63.5
