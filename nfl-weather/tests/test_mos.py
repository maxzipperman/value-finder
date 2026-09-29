"""NFL side of the MOS replay (issue #40): the wind is read at the kickoff instant, lead time is
counted from the kickoff's Eastern date, and knots become mph. The module itself is tested in
cfb-weather/tests/test_mos.py; nflweather/mos.py must stay identical to cfbweather/mos.py."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from nflweather import mos  # noqa: E402


def _runs(first_day, last_day, wind=10.0):
    taus = list(range(6, 61, 3)) + [66, 72]
    return pd.DataFrame([dict(runtime=rt, ftime=rt + pd.Timedelta(hours=t), wsp=wind)
                         for rt in pd.date_range(first_day, last_day, freq="6h") for t in taus])


def test_same_module_as_cfb():
    cfb = ROOT.parent / "cfb-weather" / "cfbweather" / "mos.py"
    assert (ROOT / "nflweather" / "mos.py").read_text() == cfb.read_text()


def test_knots_to_mph():
    assert mos.kt_to_mph(13) == pytest.approx(14.96, abs=0.01)
    assert mos.kt_to_mph(14) == pytest.approx(16.11, abs=0.01)


def test_kickoff_instant_is_interpolated():
    steps = pd.DataFrame(dict(ftime=pd.to_datetime(["2025-10-05T15:00", "2025-10-05T18:00"]), wsp=[10.0, 16.0]))
    assert mos.window_wind_kt(steps, pd.Timestamp("2025-10-05T17:00:00Z"), how="kickoff") == pytest.approx(14.0)
    assert np.isnan(mos.window_wind_kt(steps, pd.Timestamp("2025-10-05T19:00:00Z"), how="kickoff"))


def test_sunday_one_pm_gets_all_three_leads_from_earlier_days_only():
    kick = pd.Timestamp("2025-10-05T17:00:00Z")          # Sunday 1:00 PM Eastern
    sel = mos.select_runs(_runs("2025-09-30", "2025-10-05T18:00"), kick, how="kickoff")
    assert sel[1]["runtime"] == pd.Timestamp("2025-10-04T18:00")
    assert sel[2]["runtime"] == pd.Timestamp("2025-10-03T18:00")
    assert sel[3]["runtime"] == pd.Timestamp("2025-10-02T18:00")   # +66 h and +72 h bracket 17Z Sunday
    assert all(v["published_utc"] <= v["bet_by_utc"] < kick for v in sel.values())


def test_monday_night_counts_from_monday():
    kick = pd.Timestamp("2025-10-07T00:15:00Z")          # Monday 8:15 PM Eastern
    sel = mos.select_runs(_runs("2025-10-01", "2025-10-06T18:00"), kick, how="kickoff")
    assert sel[1]["runtime"] == pd.Timestamp("2025-10-05T18:00")   # Sunday, not Monday's own runs
    assert sel[3] is None                                           # Friday 18Z + 72 h ends Monday 18Z


def test_replay_threshold_is_the_boards():
    from nflweather.board import RULE_B_LEAD, RULE_B_WIND
    from nflweather.market import MIN_UNDER_ODDS
    import mos_replay
    assert mos_replay.WIND == RULE_B_WIND == 15 and mos_replay.MIN_UNDER_ODDS == MIN_UNDER_ODDS
    assert tuple(range(RULE_B_LEAD[0], RULE_B_LEAD[1] + 1)) == mos.LEADS
