"""The MOS replay (issue #40) must not look ahead, must convert knots correctly, and must read
the cache instead of re-fetching. cfbweather/mos.py and nflweather/mos.py must stay identical."""
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from cfbweather import mos  # noqa: E402


# ---------------------------------------------------------------- units
def test_knots_to_mph():
    assert mos.KT_TO_MPH == pytest.approx(1.150779, abs=1e-6)
    assert mos.kt_to_mph(13) == pytest.approx(14.96, abs=0.01)     # 13 kt is just under the 15 mph trigger
    assert mos.kt_to_mph(14) == pytest.approx(16.11, abs=0.01)
    assert 15 / mos.KT_TO_MPH == pytest.approx(13.03, abs=0.01)
    assert list(mos.kt_to_mph(pd.Series([0.0, 10.0]))) == pytest.approx([0.0, 11.50779], abs=1e-5)


def test_replay_threshold_is_the_boards():
    from cfbweather.board import RULE_B_LEAD, RULE_B_WIND
    import mos_replay
    assert mos_replay.WIND == RULE_B_WIND == 15
    assert tuple(range(RULE_B_LEAD[0], RULE_B_LEAD[1] + 1)) == mos.LEADS


# ---------------------------------------------------------------- timing
@pytest.mark.parametrize("day", ["2025-09-06", "2025-11-29", "2025-12-20"])     # summer and winter time
@pytest.mark.parametrize("cycle", [0, 6, 12, 18])
def test_a_run_counts_on_its_utc_date(day, cycle):
    """Published at cycle + 5 h, every run is usable at a scheduled Pacific alert run on its UTC date."""
    rt = pd.Timestamp(day) + pd.Timedelta(hours=cycle)
    d = mos.mac_date(rt)
    assert d == rt.date()
    assert rt.tz_localize("UTC") + pd.Timedelta(hours=mos.PUBLISH_H) <= mos.mac_slot_utc(d)


def test_kickoff_date_is_eastern():
    # 10:30 PM Eastern on Saturday Oct 4 is 02:30 UTC Sunday
    assert mos.kick_date(pd.Timestamp("2025-10-05T02:30:00Z")) == date(2025, 10, 4)
    assert mos.kick_date(pd.Timestamp("2025-12-07T01:00:00Z")) == date(2025, 12, 6)   # EST


def _runs(first_day, last_day, wind=10.0, horizon=(6, 72)):
    """Synthetic MAV runs: every 00/06/12/18Z cycle, steps 3-hourly to +60 h then +66 h and +72 h."""
    taus = list(range(6, 61, 3)) + [66, 72]
    rows = []
    for rt in pd.date_range(first_day, last_day, freq="6h"):
        for tau in taus:
            if horizon[0] <= tau <= horizon[1]:
                rows.append(dict(runtime=rt, ftime=rt + pd.Timedelta(hours=tau), wsp=wind))
    return pd.DataFrame(rows)


def test_run_selection_uses_only_runs_from_before_the_bet():
    kick = pd.Timestamp("2025-10-04T19:30:00Z")          # Saturday 3:30 PM Eastern
    runs = _runs("2025-09-29", "2025-10-04T18:00")        # includes runs on game day, which must never count
    sel = mos.select_runs(runs, kick)
    assert sel[1]["runtime"] == pd.Timestamp("2025-10-03T18:00")   # last run of Friday
    assert sel[2]["runtime"] == pd.Timestamp("2025-10-02T18:00")   # last run of Thursday
    assert sel[3] is None       # Wednesday 18Z + 72 h = Saturday 18Z, short of the 19Z-22Z window
    for v in sel.values():
        if v is not None:
            assert v["runtime"].date() < date(2025, 10, 4)
            assert v["published_utc"] <= v["bet_by_utc"] < kick


def test_lead_three_is_used_when_the_run_reaches_the_window():
    kick = pd.Timestamp("2025-10-04T16:00:00Z")          # noon Eastern: window 16Z-19Z
    runs = _runs("2025-09-30", "2025-10-03T18:00")
    sel = mos.select_runs(runs, kick)
    assert sel[3] is None                                 # 72 h from Wed 18Z ends at Sat 18Z
    kick = pd.Timestamp("2025-10-04T14:00:00Z")          # 10 AM Eastern: window 14Z-17Z
    sel = mos.select_runs(runs, kick)
    assert sel[3]["runtime"] == pd.Timestamp("2025-10-01T18:00")   # +66 h and +72 h bracket it


def test_late_kickoff_counts_from_its_eastern_date():
    kick = pd.Timestamp("2025-10-05T02:30:00Z")          # Saturday 10:30 PM Eastern
    runs = _runs("2025-09-29", "2025-10-04T18:00")
    sel = mos.select_runs(runs, kick)
    assert sel[1]["runtime"] == pd.Timestamp("2025-10-03T18:00")   # Friday, not Saturday's runs
    assert sel[2]["runtime"] == pd.Timestamp("2025-10-02T18:00")


def test_falls_back_to_an_earlier_run_of_the_same_day_never_a_later_day():
    kick = pd.Timestamp("2025-10-04T19:30:00Z")
    runs = _runs("2025-09-29", "2025-10-04T18:00")
    runs.loc[runs.runtime == pd.Timestamp("2025-10-03T18:00"), "wsp"] = np.nan   # Friday 18Z unusable
    sel = mos.select_runs(runs, kick)
    assert sel[1]["runtime"] == pd.Timestamp("2025-10-03T12:00")
    runs = runs[runs.runtime.dt.date != date(2025, 10, 3)]          # no Friday run at all
    sel = mos.select_runs(runs, kick)
    assert sel[1] is None and sel[2]["runtime"] == pd.Timestamp("2025-10-02T18:00")


# ---------------------------------------------------------------- the window
def test_window_interpolates_between_three_hourly_steps():
    steps = pd.DataFrame(dict(ftime=pd.to_datetime(["2025-10-04T15:00", "2025-10-04T18:00", "2025-10-04T21:00"]),
                              wsp=[10.0, 16.0, 4.0]))
    # kickoff 16:30Z -> hours 16, 17, 18, 19 -> 12, 14, 16, 12 kt
    assert mos.window_wind_kt(steps, pd.Timestamp("2025-10-04T16:30:00Z")) == pytest.approx(13.5)
    # kickoff 18:00Z -> hours 18, 19, 20, 21 -> 16, 12, 8, 4 kt
    assert mos.window_wind_kt(steps, pd.Timestamp("2025-10-04T18:00:00Z")) == pytest.approx(10.0)


def test_window_not_covered_is_missing():
    steps = pd.DataFrame(dict(ftime=pd.to_datetime(["2025-10-04T12:00", "2025-10-04T18:00"]), wsp=[10.0, 10.0]))
    assert np.isnan(mos.window_wind_kt(steps, pd.Timestamp("2025-10-04T16:00:00Z")))   # 19Z beyond the last step
    wide = pd.DataFrame(dict(ftime=pd.to_datetime(["2025-10-04T06:00", "2025-10-05T00:00"]), wsp=[10.0, 10.0]))
    assert np.isnan(mos.window_wind_kt(wide, pd.Timestamp("2025-10-04T16:00:00Z")))    # 18 h gap
    gap = pd.DataFrame(dict(ftime=pd.to_datetime(["2025-10-04T15:00", "2025-10-04T18:00", "2025-10-04T21:00"]),
                            wsp=[10.0, np.nan, 10.0]))
    assert np.isnan(mos.window_wind_kt(gap, pd.Timestamp("2025-10-04T16:00:00Z")))


def test_season_window_spans_the_runs_the_replay_can_use():
    g = pd.DataFrame(dict(icao="KAMW", season=2025,
                          start_utc=pd.to_datetime(["2025-09-06T16:00:00Z", "2025-11-30T02:00:00Z"])))
    w = mos.season_windows(g).iloc[0]
    assert w.sts == pd.Timestamp("2025-09-03T00:00") and w.ets == pd.Timestamp("2025-11-28T18:00")   # Nov 29 ET


# ---------------------------------------------------------------- cache and politeness
class _Resp:
    def __init__(self, status, text):
        self.status_code, self.text = status, text


def test_cached_window_is_not_fetched_again(tmp_path, monkeypatch):
    f = mos.cache_file("KAMW", "2025-09-01", "2025-11-30T18:00", cache=tmp_path)
    f.parent.mkdir(parents=True)
    f.write_text("runtime,ftime,model,wsp,station\n2025-09-02 00:00:00,2025-09-02 06:00:00,GFS,7,KAMW\n")
    monkeypatch.setattr(mos._session, "get", lambda *a, **k: pytest.fail("fetched a cached window"))
    assert mos.fetch_runs("KAMW", "2025-09-10", "2025-09-20", cache=tmp_path) == f
    assert mos.load_station("KAMW", cache=tmp_path).wsp.tolist() == [7]


def test_rate_limit_is_retried_and_never_cached(tmp_path, monkeypatch):
    replies = [_Resp(429, "Too many requests from your IP address, slow down."),
               _Resp(200, "runtime,ftime,model,wsp,station\n")]
    monkeypatch.setattr(mos._session, "get", lambda *a, **k: replies.pop(0))
    monkeypatch.setattr(mos, "BACKOFF_S", (0, 0))
    monkeypatch.setattr(mos, "_interval", [0.0])
    monkeypatch.setattr(mos.time, "sleep", lambda s: None)
    p = mos.fetch_runs("KXYZ", "2025-09-01", "2025-09-02", cache=tmp_path, log=lambda m: None)
    assert p.read_text().startswith("runtime,") and not replies
    assert [x.name for x in p.parent.iterdir()] == [p.name]       # no .part, nothing from the 429
    assert mos.load_station("KXYZ", cache=tmp_path).empty


def test_user_agent_is_the_projects():
    from cfbweather.config import USER_AGENT
    assert mos._session.headers["User-Agent"] == USER_AGENT
    assert "@" not in USER_AGENT


def test_the_nfl_copy_is_identical():
    nfl = ROOT.parent / "nfl-weather" / "nflweather" / "mos.py"
    assert nfl.exists(), "nflweather/mos.py is a copy of cfbweather/mos.py"
    assert nfl.read_text() == (ROOT / "cfbweather" / "mos.py").read_text()


# ---------------------------------------------------------------- the replay's own output
REPLAYS = sorted((ROOT / "data" / "processed").glob("mos_replay*.parquet"))


@pytest.mark.skipif(not REPLAYS, reason="run scripts/mos_replay.py first")
@pytest.mark.parametrize("path", REPLAYS, ids=lambda p: p.name)
def test_every_forecast_used_was_public_before_the_bet(path):
    from datetime import timedelta
    d = pd.read_parquet(path)
    assert len(d)
    for n in mos.LEADS:
        u = d[d[f"mos{n}_runtime"].notna()]
        kd = [mos.kick_date(k) for k in u.start_utc]
        rt = pd.to_datetime(u[f"mos{n}_runtime"])
        assert all(r.date() == k - timedelta(days=n) for r, k in zip(rt, kd))
        pub = rt.dt.tz_localize("UTC") + pd.Timedelta(hours=mos.PUBLISH_H)
        bet_by = pd.Series([mos.mac_slot_utc(k - timedelta(days=n)) for k in kd], index=u.index)
        assert (pub <= bet_by).all() and (bet_by < u.start_utc).all()


@pytest.mark.skipif(not REPLAYS, reason="run scripts/mos_replay.py first")
@pytest.mark.parametrize("path", REPLAYS, ids=lambda p: p.name)
def test_replay_signals_and_grades(path):
    d = pd.read_parquet(path)
    fired = pd.concat([d[f"mos{n}_mph"] >= 15 for n in mos.LEADS], axis=1).any(axis=1)
    assert (fired == d.mos_signal).all()
    s = d[d.mos_signal]
    assert ((s.total < s.close_total) == s.under_win).all() and ((s.total == s.close_total) == s.push).all()


# ---------------------------------------------------------------- station map
def test_station_map_keeps_only_stations_within_40_km():
    m = pd.read_csv(ROOT / "data" / "processed" / "mos_station_map.csv")
    assert (m.km <= 40).all() and m.icao.str.len().eq(4).all()
    assert m.groupby("venue_id")["rank"].apply(lambda r: list(r) == list(range(len(r)))).all()
    assert m.groupby("venue_id").km.apply(lambda k: k.is_monotonic_increasing).all()
