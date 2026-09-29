"""The forecast replay (scripts/forecast_replay.py) must not use hindsight: no quote may predate
the forecast it is paired with, and forecasts go through the frozen calibration and the board's gates."""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import forecast_replay as fr  # noqa: E402

REPLAY = ROOT / "data" / "processed" / "forecast_replay.parquet"


def test_decision_time_is_after_the_forecast_run_publishes():
    kick = pd.Timestamp("2025-10-04T19:30:00Z")
    assert fr.decision_time(kick, 1) == pd.Timestamp("2025-10-04T06:30:00Z")   # kick + 4h - 1d + 7h
    assert fr.decision_time(kick, 3) == pd.Timestamp("2025-10-02T06:30:00Z")
    assert fr.decision_time(pd.Timestamp("2025-10-04T19:32:00Z"), 1).minute % 5 == 0   # rounded up


@pytest.mark.skipif(not REPLAY.exists(), reason="run scripts/forecast_replay.py first")
def test_no_quote_predates_its_forecast():
    d = pd.read_parquet(REPLAY)
    used = d[d.fc_trigger]
    assert len(used)
    assert (used.quote == "close_total").all()
    assert (used.quote_utc >= used.forecast_available_utc).all()
    for n in fr.LEADS:   # holds for every lead that triggered, not only the first
        t = used[used[f"fc{n}_wind"] >= 15]
        assert (t.quote_utc >= t[f"fc{n}_available_utc"]).all()


@pytest.mark.skipif(not REPLAY.exists(), reason="run scripts/forecast_replay.py first")
def test_record_is_graded_at_the_close_not_the_opener():
    d = pd.read_parquet(REPLAY)
    s = d[d.fc_signal]
    assert ((s.total < s.close_total) == s.under_win).all()
    assert ((s.total == s.close_total) == s.push).all()


def test_gates_match_the_board(tmp_path, monkeypatch):
    """Station-scale forecast >= 15 at lead 1-3 triggers; the frozen calibration is applied, not refit."""
    monkeypatch.setattr(fr, "CACHE", tmp_path)
    kick = pd.Timestamp("2025-10-04T19:00:00Z")
    games = pd.DataFrame(dict(game_id=[1, 2], season=2025, week=6, season_type="regular", start_utc=[kick, kick],
                              lat=[40.0, 41.0], lon=[-90.0, -91.0], wx_wind=[16.0, 5.0], open_total=[50.0, 50.0],
                              close_total=[48.0, 48.0], total=[40.0, 60.0]))
    hours = pd.date_range("2025-10-04T00:00", periods=24, freq="h").strftime("%Y-%m-%dT%H:%M").tolist()
    for lat, lon, wind in [(40.0, -90.0, 20.0), (41.0, -91.0, 14.0)]:
        js = {"hourly": {"time": hours, **{f"wind_speed_10m_previous_day{n}": [wind] * 24 for n in fr.LEADS}}}
        fr.cache_path(lat, lon, kick).write_text(json.dumps(js))
    cal = dict(wind_intercept=1.0, wind_slope=1.0)   # station = 1 + model: 21 triggers, 15 triggers
    resid = np.array([-10.0, -5.0, -1.0, 1.0])       # 75% under at the market number: positive EV at -110
    d = fr.replay(games, cal, resid).set_index("game_id")
    assert d.at[1, "fc1_wind"] == 21.0 and d.at[2, "fc1_wind"] == 15.0
    assert d.fc_signal.all() and (d.first_lead == 3).all()
    assert d.at[1, "under_win"] and not d.at[2, "under_win"]
