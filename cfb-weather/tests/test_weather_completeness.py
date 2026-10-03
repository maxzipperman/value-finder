"""Synthetic-only input completeness regressions; no caches, outcomes or calls."""
import copy
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
from cfbweather.weather import summarize, summarize_checked
import forecast_replay as fr


KICK = pd.Timestamp("2025-10-04T19:30:00Z")


def fixture(kick=KICK):
    k0 = kick.tz_convert("UTC").floor("h")
    return {"hourly": {
        "time": pd.date_range(k0, periods=5, freq="h").strftime("%Y-%m-%dT%H:%M").tolist(),
        "temperature_2m": [60, 61, 62, 63, 64],
        "wind_speed_10m": [12, 14, 16, 18, 20],
        "wind_gusts_10m": [20, 21, 22, 23, 24],
        "precipitation": [99, 0.01, 0.02, 0.03, 0.04],
        "snowfall": [99, 0, 0.1, 0.2, 0.3],
        **{f"wind_speed_10m_previous_day{n}": [n * 10 + i for i in range(5)] for n in fr.LEADS},
    }}


def test_complete_windows_keep_values_and_accumulation_alignment():
    got = summarize(fixture(), KICK)
    assert set(got) == {"om_wind", "om_temp", "om_precip", "om_snow", "om_gust"}
    assert got == pytest.approx(dict(om_wind=15, om_temp=60, om_precip=0.1, om_snow=0.6, om_gust=23))
    assert fr.summarize_prev(fixture(), KICK) == dict(fc1_raw=11.5, fc2_raw=21.5, fc3_raw=31.5)


def test_original_partial_wind_and_all_null_accumulations_fail_closed():
    js = fixture()
    js["hourly"]["wind_speed_10m"] = [15, None, None, None, 10]
    for col in ("precipitation", "snowfall"):
        js["hourly"][col] = [None] * 5
    checked = summarize_checked(js, KICK)
    assert summarize(js, KICK) is None
    assert checked["fields"]["om_wind"] == dict(required=4, present=4, finite=1, reason="nonfinite_value")
    assert checked["fields"]["om_precip"]["finite"] == 0
    assert "om_snow:nonfinite_value" in checked["missing_reason"]


@pytest.mark.parametrize("column,index", [("wind_speed_10m", 0), ("wind_speed_10m", 3),
    ("temperature_2m", 0), ("precipitation", 1), ("precipitation", 4), ("snowfall", 4)])
@pytest.mark.parametrize("bad", [None, float("inf"), float("-inf"), "bad"])
def test_nonfinite_required_values_are_not_valid_forecasts(column, index, bad):
    js = fixture()
    js["hourly"][column][index] = bad
    assert summarize(js, KICK) is None


@pytest.mark.parametrize("index", [0, 2, 4])
def test_absent_hour_is_counted_instead_of_shortening_the_window(index):
    js = fixture()
    for values in js["hourly"].values():
        values.pop(index)
    checked = summarize_checked(js, KICK)
    assert checked["values"] is None
    assert "missing_hour" in checked["missing_reason"]
    name = "om_precip" if index == 4 else "om_wind"
    assert checked["fields"][name]["required"] == 4
    assert checked["fields"][name]["present"] == 3


def test_gust_is_optional_but_never_partially_aggregated():
    js = fixture()
    js["hourly"]["wind_gusts_10m"][3] = None
    checked = summarize_checked(js, KICK)
    assert np.isnan(checked["values"]["om_gust"])
    assert checked["fields"]["om_gust"]["finite"] == 3
    assert checked["missing_reason"] == ""


def test_finite_zero_rain_and_snow_are_valid_dry_weather():
    js = fixture()
    for name in ("precipitation", "snowfall"):
        js["hourly"][name] = [0] * 5
    assert summarize(js, KICK)["om_precip"] == 0
    assert summarize(js, KICK)["om_snow"] == 0


@pytest.mark.parametrize("mutation,reason", [("no_time", "missing_time"), ("duplicate", "invalid_hourly_time"),
    ("bad_time", "malformed_hourly"), ("short_column", "malformed_hourly")])
def test_malformed_hourly_payload_is_explicit(mutation, reason):
    js = fixture()
    if mutation == "no_time":
        del js["hourly"]["time"]
    elif mutation == "duplicate":
        js["hourly"]["time"][2] = js["hourly"]["time"][1]
    elif mutation == "bad_time":
        js["hourly"]["time"][2] = "invalid"
    else:
        js["hourly"]["snowfall"].pop()
    assert summarize_checked(js, KICK)["missing_reason"] == reason
    assert all(np.isnan(v) for v in fr.summarize_prev(js, KICK).values())


def test_missing_field_has_distinct_reason():
    js = fixture()
    del js["hourly"]["precipitation"]
    checked = summarize_checked(js, KICK)
    assert checked["fields"]["om_precip"] == dict(required=4, present=4, finite=0, reason="missing_field")


def test_midnight_window_and_timezone_conversion_use_exact_utc_hours():
    kick = pd.Timestamp("2025-10-04T23:30:00Z")
    js = fixture(kick)
    assert summarize(js, kick) == summarize(js, kick.tz_convert("America/New_York"))
    offset = copy.deepcopy(js)
    offset["hourly"]["time"] = [pd.Timestamp(t, tz="UTC").tz_convert("America/New_York").isoformat()
                                 for t in js["hourly"]["time"]]
    assert summarize(offset, kick) == summarize(js, kick)
    for values in js["hourly"].values():
        del values[1:]
    assert summarize(js, kick) is None
    assert np.isnan(fr.summarize_prev(js, kick)["fc1_raw"])


def test_unknown_kickoff_is_not_assumed_utc():
    assert summarize_checked(fixture(), KICK.tz_localize(None))["missing_reason"] == "invalid_kickoff"


@pytest.mark.parametrize("index", [0, 1, 3])
def test_replay_invalid_lead_does_not_poison_complete_leads(index):
    js = fixture()
    js["hourly"]["wind_speed_10m_previous_day1"][index] = None
    checked = fr.summarize_prev_checked(js, KICK)
    assert np.isnan(checked["values"]["fc1_raw"])
    assert checked["fields"]["fc1_raw"]["finite"] == 3
    assert checked["values"]["fc2_raw"] == 21.5
    assert checked["values"]["fc3_raw"] == 31.5


def test_board_retains_missingness_and_weather_independent_ht(tmp_path, monkeypatch):
    from cfbweather import board as b
    kick = (pd.Timestamp.now(tz="UTC") + pd.Timedelta(days=2)).floor("h")
    js = fixture(kick)
    js["hourly"]["precipitation"] = [None] * 5
    (tmp_path / "calibration.json").write_text('{"wind_intercept":0,"wind_slope":1,"temp_intercept":0,"temp_slope":1}')
    monkeypatch.setattr(b, "PROC", tmp_path)
    schedule = pd.DataFrame([dict(game_id=1, season=2025, start_utc=kick, tbd=False, venue_id=1,
                                  home_division="fbs", away_division="fbs", home_team="Home", away_team="Away")])
    monkeypatch.setattr(b, "schedules", lambda: schedule)
    monkeypatch.setattr(b, "venues", lambda: pd.DataFrame([dict(venue_id=1, venue="Synthetic", dome=False, lat=1., lon=2.)]))
    monkeypatch.setattr(b.fetch, "fetch_cfbfastr", lambda *_: None)
    monkeypatch.setattr(b.fetch, "om_forecast", lambda *_: js)
    monkeypatch.setattr(b, "odds_team_names", lambda: {})
    monkeypatch.setattr(b.fetch, "espn_week_odds", lambda *_: pd.DataFrame([dict(game_id=1, mkt_total=70., mkt_under=-110, mkt_over=-110)]))
    monkeypatch.setattr(b, "pricing_cohort", lambda *_: np.array([0.]))
    monkeypatch.setattr(b, "price", lambda d, *_: d.assign(ev_under=0.1))
    monkeypatch.setattr(b, "ht_threshold", lambda *_: 60.)
    monkeypatch.setattr(b, "HT_FIRST_KICK", kick - pd.Timedelta(days=1))
    monkeypatch.setattr(b, "keep_forecast", lambda *_: pytest.fail("Incomplete weather must not claim used provenance"))
    row = b.compute(refresh=True, prices=False).iloc[0]
    assert row.wx_src == "no_forecast" and row.rule_b == "no_forecast"
    assert row.wx_missing_reason == "om_precip:nonfinite_value"
    assert pd.isna(row.wx_precip) and pd.isna(row.wx_snow)
    assert row.rule_ht == "SIGNAL"
