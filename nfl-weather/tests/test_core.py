"""Pins the facts the analysis depends on. Run: .venv/bin/python -m pytest -q"""
import ast
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from nflweather import boxscore, market, weather  # noqa: E402


def test_wind_chill_matches_nws():
    # NWS chart: 0F with 15 mph wind -> -19F; formula only applies at <=50F and >3 mph
    assert round(float(weather.wind_chill(0, 15)), 0) == -19
    assert float(weather.wind_chill(72, 0)) == 72
    assert float(weather.wind_chill(60, 20)) == 60


def test_passer_rating_bounds():
    assert round(float(boxscore.passer_rating(20, 20, 400, 5, 0)), 1) == 158.3
    assert round(float(boxscore.passer_rating(0, 20, 0, 0, 5)), 1) == 0.0


@pytest.mark.skipif(not (ROOT / "data/raw/pbp/play_by_play_2012.parquet").exists(), reason="pbp not downloaded")
def test_boxscore_reproduces_official_stats():
    # Houston vs Jacksonville, 2012-11-18: Schaub 43/55, 527 yds, 5 TD, 2 INT
    p = boxscore.load_pbp(2012)
    s = boxscore.team_game_stats(p[p.game_id == "2012_11_JAX_HOU"])
    hou = s[s.team == "HOU"].iloc[0]
    assert (hou.cmp, hou.pass_att, hou.pass_yds, hou.pass_td, hou.ints) == (43, 55, 527, 5, 2)


def test_devig_methods():
    assert market.market_p_under([-110], [-110], "shin")[0] == pytest.approx(0.5)
    assert market.market_p_under([-110], [-110], "prop")[0] == pytest.approx(0.5)
    p_shin = market.market_p_under([-150], [130], "shin")[0]
    p_prop = market.market_p_under([-150], [130], "prop")[0]
    assert 0.55 < p_shin < 0.6 and 0.55 < p_prop < 0.6


def test_record_roi_at_minus_110():
    r = market.record(np.array([True] * 11 + [False] * 10), np.array([False] * 11 + [True] * 10))
    assert r["bets"] == 21 and r["roi_110"] == pytest.approx((11 * 100 / 110 - 10) / 21)


def test_gamebook_text_ignores_forecast_phrasing():
    f = weather.parse_gamebook_weather(pd.Series(["20% chance of rain Temp: 50° F, Wind: SW 8 mph",
                                                  "Light Rain Temp: 45° F, Humidity: 90%, Wind: NW 13 mph"]))
    assert list(f.gb_rain) == [False, True]
    assert list(f.gb_text_wind) == [8, 13]


def test_odds_client_is_get_only():
    """Like sharp-markets: nothing in the odds client may post, put or delete."""
    src = (ROOT / "nflweather" / "oddsapi.py").read_text()
    calls = {n.func.attr for n in ast.walk(ast.parse(src)) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
    assert not calls & {"post", "put", "delete", "patch"}
