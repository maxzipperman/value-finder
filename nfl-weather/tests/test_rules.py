"""Regression tests for the audit's alert and pricing probes (Sept 28, 2026 review):
an actionable Rule B signal needs a trigger, the 1-3 day horizon, a posted total,
an acceptable under price, and positive EV at that line and price."""
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nflweather.board import rule_b_status  # noqa: E402
from nflweather.market import ev_under, p_under_at  # noqa: E402

RESID = np.sort(np.random.default_rng(0).normal(-1.5, 13.5, 700).round())  # a windy-cohort-like shape


def game(**kw):
    base = dict(wx_src="era5", wx_wind=18.0, lead_days=2, mkt_total=44.0, mkt_under=-110.0)
    base.update(kw)
    base["ev_under"] = float(ev_under(base["mkt_total"], base["mkt_under"], base["mkt_total"], RESID)[0]) \
        if base["mkt_under"] == base["mkt_under"] and base["mkt_total"] == base["mkt_total"] else np.nan
    return SimpleNamespace(**base)


def test_valid_signal():
    assert rule_b_status(game()) == "SIGNAL"


@pytest.mark.parametrize("kw,expected", [
    (dict(mkt_total=np.nan), "no_price"),          # probe: same-day wind alert with no total
    (dict(mkt_under=np.nan), "no_price"),
    (dict(mkt_under=-160.0), "price_too_high"),    # probe: -160 under still alerted
    (dict(lead_days=0), "outside_horizon"),        # probe: same-day game
    (dict(lead_days=8), "outside_horizon"),        # probe: line lag eight days out
    (dict(wx_wind=12.0), "no_trigger"),
    (dict(wx_src="indoor"), "not_outdoor"),
    (dict(wx_src="open_roof"), "not_outdoor"),
])
def test_no_actionable_signal(kw, expected):
    assert rule_b_status(game(**kw)) == expected


def test_probability_depends_on_the_offered_line():
    """Audit probe: the old model gave the same P(under) at 30 and 60."""
    lines = [30, 40, 44, 50, 60]
    p = [p_under_at(L, 44, RESID)[0] for L in lines]
    assert all(a < b for a, b in zip(p, p[1:]))


def test_price_changes_expected_value():
    assert ev_under(44, -110, 44, RESID)[0] > ev_under(44, -160, 44, RESID)[0]
    assert np.isnan(ev_under(44, np.nan, 44, RESID)[0])


def test_scorer_grades_wind_only_rule_b(tmp_path):
    """Audit probe: a settled wind-rule bet with no model lean was dropped by the scorer."""
    import subprocess

    import pandas as pd
    led = pd.DataFrame([dict(snapshot_utc="2026-10-08T15:00:00Z", rules_version="v2", game_id="TEST_G1",
                             gameday="2026-10-11", gametime="13:00", away_team="A", home_team="B", lead_days=3,
                             wx_src="era5", wx_wind=16, wx_temp=60, wx_precip=0, wx_snow=0, line_src="nflverse",
                             total_line=44, under_odds=-110, over_odds=-110, p_under=0.54, p_market=0.5, lean="",
                             ev_under=0.08, rule_b="SIGNAL")])
    games = pd.DataFrame([dict(game_id="TEST_G1", total=40, total_line=42, gameday="2026-10-11", gametime="13:00",
                               result=3)])
    led.to_csv(tmp_path / "ledger.csv", index=False)
    games.to_csv(tmp_path / "games.csv", index=False)
    root = Path(__file__).resolve().parents[1]
    out = subprocess.run([sys.executable, str(root / "scripts" / "score_forward.py"), "--ledger",
                          str(tmp_path / "ledger.csv"), "--games", str(tmp_path / "games.csv")],
                         capture_output=True, text=True, check=True).stdout
    assert "RULE_B (wind under): 1 signals, 1 settled" in out
    assert "1-0-0" in out and "+2.00" in out   # graded at entry 44 (not the close), CLV 44 - 42


def test_replay_quotes_never_predate_their_forecast():
    """Audit finding: planned 1-day quotes preceded forecast publication by up to 11h."""
    import pandas as pd
    from nflweather import oddsapi
    for kick in pd.to_datetime(["2024-09-08 17:00", "2024-09-08 20:25", "2024-12-01 01:20", "2025-01-12 21:30"], utc=True):
        for lead in oddsapi.FORECAST_LEADS:
            latest_run = kick + pd.Timedelta(hours=oddsapi.GAME_WINDOW_H) - pd.Timedelta(days=lead)
            assert oddsapi.decision_time(kick, lead) >= latest_run + pd.Timedelta(hours=oddsapi.FORECAST_LATENCY_H)
            assert oddsapi.decision_time(kick, lead) < kick


# ---------------------------------------------------------------- timing advice (issue #5)
def test_timing_block_is_identical_in_both_copies():
    root = Path(__file__).resolve().parents[2]
    mark = "# --------------------------------------------------------------------------- execution timing (issue #5)"
    nfl = (root / "nfl-weather/nflweather/market.py").read_text()
    cfb = (root / "cfb-weather/cfbweather/market.py").read_text()
    assert mark in nfl and nfl[nfl.index(mark):] == cfb[cfb.index(mark):]


def test_timing_note_and_cost_of_waiting():
    import pandas as pd
    from nflweather.market import cost_of_waiting, timing_note
    assert timing_note("under").startswith("Timing: bet now") and "later" in timing_note("underdog")
    entries = pd.DataFrame([dict(game_id="G", rule="rule_b", entry_line=44.0, entry_price=-110)])
    fills = pd.DataFrame([dict(game_id="G", rule="rule_b", line=43.0, price=-105)])
    wc = cost_of_waiting(entries, fills).iloc[0]
    assert wc.pts_gained == -1.0                                   # waited and lost a point
    assert wc.profit_gained == pytest.approx(100 / 105 - 100 / 110)


def test_scorer_reports_cost_of_waiting(tmp_path):
    import subprocess

    import pandas as pd
    led = pd.DataFrame([dict(snapshot_utc="2026-10-08T15:00:00Z", rules_version="v2", game_id="TEST_G1",
                             gameday="2026-10-11", gametime="13:00", away_team="A", home_team="B", lead_days=3,
                             wx_src="era5", wx_wind=16, wx_temp=60, wx_precip=0, wx_snow=0, line_src="pinnacle",
                             total_line=44, under_odds=-110, over_odds=-110, p_under=0.54, p_market=0.5, lean="",
                             ev_under=0.08, rule_b="SIGNAL")])
    games = pd.DataFrame([dict(game_id="TEST_G1", total=40, total_line=42, gameday="2026-10-11", gametime="13:00",
                               result=3)])
    fills = pd.DataFrame([dict(fill_utc="2026-10-09T12:00:00Z", game_id="TEST_G1", rule="rule_b", line=43.5,
                               price=-110, book="x")])
    led.to_csv(tmp_path / "ledger.csv", index=False)
    games.to_csv(tmp_path / "games.csv", index=False)
    fills.to_csv(tmp_path / "fills.csv", index=False)
    root = Path(__file__).resolve().parents[1]
    out = subprocess.run([sys.executable, str(root / "scripts" / "score_forward.py"), "--ledger",
                          str(tmp_path / "ledger.csv"), "--games", str(tmp_path / "games.csv")],
                         capture_output=True, text=True, check=True).stdout
    assert "Cost of waiting, RULE_B: 1 paper fills" in out and "-0.50 pts" in out
