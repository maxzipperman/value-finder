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


def test_lead_status_says_why_a_lead_is_missing_and_agrees_with_select_runs():
    kick = pd.Timestamp("2025-10-04T19:30:00Z")          # Saturday 3:30 PM Eastern
    runs = _runs("2025-09-29", "2025-10-04T18:00")
    sel = mos.select_runs(runs, kick)
    status = {n: mos.lead_status(runs, kick, n) for n in mos.LEADS}
    assert status == {1: "forecast", 2: "forecast", 3: "run ends before the window"}
    assert all((sel[n] is not None) == (status[n] == "forecast") for n in mos.LEADS)
    no_friday = runs[runs.runtime.dt.date != date(2025, 10, 3)]
    assert mos.lead_status(no_friday, kick, 1) == "no run that day"
    windless = runs.copy()
    windless.loc[windless.runtime.dt.date == date(2025, 10, 3), "wsp"] = np.nan
    assert mos.lead_status(windless, kick, 1) == "gap or no wind"
    assert mos.select_runs(windless, kick)[1] is None
    assert mos.lead_status(runs.iloc[0:0], kick, 1) == "no run that day"


def test_window_status_reports_every_requested_window(tmp_path):
    _cached(tmp_path, "KDMH", NO_WIND)
    _cached(tmp_path, "KIGX", NO_RUNS)
    _cached(tmp_path, "KBWI", WITH_WIND)
    w = pd.DataFrame(dict(icao=["KDMH", "KIGX", "KBWI", "KADW"], season=2024, games=[3, 2, 1, 4],
                          sts=pd.Timestamp("2024-10-01"), ets=pd.Timestamp("2024-11-01")))
    s = mos.window_status(w, cache=tmp_path)
    assert s.status.tolist() == ["no wind", "no runs", "ok", "not downloaded"]
    assert s.runs.tolist() == [1, 0, 1, 0] and s.wind_rows.tolist() == [0, 0, 2, 0]
    assert s.file.tolist()[3] == "" and s.file.tolist()[2].startswith("KBWI_GFS_")


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


# ---------------------------------------------------------------- answers with no forecast (Sep 29 full pull)
# The header IEM sent for KIGX 2023 (no runs), and a trimmed KDMH answer: Baltimore Inner Harbor has
# every MOS variable but wind, so IEM's CSV leaves the wdr and wsp columns out altogether.
NO_RUNS = "runtime,ftime,model,n_x,tmp,dpt,cld,wdr,wsp,p06,p12,station,t06,t12\n"
NO_WIND = ("runtime,ftime,model,n_x,tmp,dpt,cld,p06,p12,station,t06,t12\n"
           "2024-10-12 18:00:00,2024-10-13 00:00:00,GFS,,74,60,CL,,,KDMH,,\n"
           "2024-10-12 18:00:00,2024-10-13 03:00:00,GFS,,68,59,CL,0,,KDMH,,\n")
WITH_WIND = ("runtime,ftime,model,n_x,tmp,dpt,cld,wdr,wsp,p06,p12,station,t06,t12\n"
             "2024-10-12 18:00:00,2024-10-13 00:00:00,GFS,,74,60,CL,300,12,,,KBWI,,\n"
             "2024-10-12 18:00:00,2024-10-13 03:00:00,GFS,,68,59,CL,310,14,0,,KBWI,,\n")


def _cached(tmp_path, station, text, span=("2024-09-01", "2024-12-31T18:00")):
    f = mos.cache_file(station, *span, cache=tmp_path)
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(text)
    return f


@pytest.mark.parametrize("text,status,rows", [
    (WITH_WIND, "ok", 2),
    (NO_RUNS, "no runs", 0),
    (NO_WIND, "no wind", 2),
    ("", "unreadable", 0),                                            # a zero-byte file
    ("<html><body>Service unavailable</body></html>\n", "unreadable", 0),
    ("runtime,ftime,wsp\n2024-10-12 18:00:00,2024-10-13 00:00:00,M\n", "no wind", 1),   # a missing value
])
def test_every_kind_of_answer_reads_without_crashing(tmp_path, text, status, rows):
    f = _cached(tmp_path, "KXYZ", text)
    d = mos.read_file(f)                  # the Sep 29 pull crashed here: no 'wsp' attribute
    assert set(mos.COLUMNS) <= set(d.columns) and len(d) == rows
    assert mos.file_status(f) == status
    assert (d.wsp.notna().any()) == (status == "ok")


def test_a_station_with_no_wind_is_a_missing_forecast(tmp_path):
    """A run with no wind value is no forecast: every lead is missing, nothing is guessed."""
    _cached(tmp_path, "KDMH", NO_WIND)
    runs = mos.load_station("KDMH", cache=tmp_path)
    assert len(runs) == 2 and runs.wsp.isna().all()
    sel = mos.select_runs(runs, pd.Timestamp("2024-10-13T17:00:00Z"), how="kickoff")
    assert all(v is None for v in sel.values())
    empty = mos.load_station("KIGX", cache=tmp_path)           # no folder at all
    assert empty.empty and set(mos.COLUMNS) <= set(empty.columns)


def test_no_wind_files_mixed_with_good_ones_keep_the_good_rows(tmp_path):
    _cached(tmp_path, "KXYZ", NO_WIND.replace("2024-10-12 18", "2023-10-12 18"), span=("2023-09-01", "2023-12-31T18:00"))
    _cached(tmp_path, "KXYZ", WITH_WIND)
    runs = mos.load_station("KXYZ", cache=tmp_path)
    assert runs.wsp.notna().sum() == 2 and runs.wsp.isna().sum() == 2          # different runs: all kept
    _cached(tmp_path, "KXYZ", NO_WIND, span=("2024-08-01", "2024-12-31T18:00"))  # sorts before WITH_WIND's file
    runs = mos.load_station("KXYZ", cache=tmp_path)
    same = runs[runs.runtime == pd.Timestamp("2024-10-12 18:00")]
    assert len(same) == 2 and same.wsp.tolist() == [12, 14]                    # the same run twice: wind wins


def test_the_fetchers_treat_a_windless_answer_as_empty(tmp_path, monkeypatch):
    """So the next-nearest station is tried, as PR 61 specified for a station with no forecast."""
    import mos_fetch
    _cached(tmp_path, "KDMH", NO_WIND)
    _cached(tmp_path, "KIGX", NO_RUNS)
    _cached(tmp_path, "KBWI", WITH_WIND)
    monkeypatch.setattr(mos, "CACHE", tmp_path)
    monkeypatch.setattr(mos, "fetch_runs", lambda *a, **k: pytest.fail("fetched a cached window"))
    w = pd.DataFrame(dict(icao=["KDMH", "KIGX", "KBWI"], season=2024, games=1,
                          sts=pd.Timestamp("2024-10-01"), ets=pd.Timestamp("2024-11-01")))
    res = mos_fetch.run_windows(w, log=lambda m: None)
    assert [(icao, n) for icao, _, n, _ in res] == [("KDMH", 0), ("KIGX", 0), ("KBWI", 2)]


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


# ---------------------------------------------------------------- hand-checked real games (full run, Sep 29)
# Worked by hand from output/mos_hand_check.log (scripts/mos_hand_check.py): lead -> (run, mean knots
# over the four window hours, mph as the log prints it). The MOS rows are in tests/fixtures/.
FIX = ROOT / "tests" / "fixtures"
HAND_CHECKED = {
    401752822: {1: ("2025-09-05 18:00", 125 / 12, 11.99), 2: ("2025-09-04 18:00", 133 / 12, 12.75), 3: None},
    401643858: {1: ("2024-08-23 18:00", 17.0, 19.56), 2: ("2024-08-22 18:00", 17.5, 20.14), 3: None},
    401525461: {1: ("2023-08-30 18:00", 41 / 12, 3.93), 2: ("2023-08-29 18:00", 4.25, 4.89), 3: None},
    272510276: {1: ("2007-09-07 18:00", 4.0, 4.60), 2: ("2007-09-06 18:00", 3.5, 4.03),
                3: ("2007-09-05 18:00", 4.25, 4.89)},
    282570248: {1: ("2008-09-12 18:00", 17.0, 19.56), 2: ("2008-09-11 18:00", 15.5, 17.84),
                3: ("2008-09-10 18:00", 17.0, 19.56)},
    272932711: {1: ("2007-10-19 18:00", 13.0, 14.96), 2: ("2007-10-18 18:00", 14.0, 16.11), 3: None},
    273140265: {1: ("2007-11-09 18:00", 157 / 12, 15.06), 2: ("2007-11-08 18:00", 107 / 12, 10.26), 3: None},
    263010120: {1: ("2006-10-27 18:00", 205 / 12, 19.66), 2: ("2006-10-26 18:00", 178 / 12, 17.07), 3: None},
    401635615: {1: ("2024-11-22 18:00", 2.5, 2.88), 2: ("2024-11-21 18:00", 41 / 12, 3.93), 3: None},
    401247332: {1: ("2020-11-26 12:00", 10.5, 12.08), 2: ("2020-11-25 18:00", 10.5, 12.08), 3: None},
    401769076: {1: ("2026-01-18 18:00", 8.5, 9.78), 2: ("2026-01-17 18:00", 6.5, 7.48), 3: None},
    401760405: {1: ("2025-10-31 18:00", 16 / 3, 6.14), 2: ("2025-10-30 18:00", 65 / 12, 6.23), 3: None},
}
FIRES = {401643858, 282570248, 272932711, 273140265, 263010120}


def _hand_checked():
    runs = pd.read_csv(FIX / "mos_hand_checked_runs.csv", parse_dates=["runtime", "ftime"])
    games = pd.read_csv(FIX / "mos_hand_checked_games.csv")
    games["start_utc"] = pd.to_datetime(games.start_utc, utc=True)
    return runs, games.set_index("game_id")


def test_at_least_ten_hand_checked_games_with_game_day_runs_on_hand():
    runs, games = _hand_checked()
    assert len(HAND_CHECKED) >= 10 and set(games.index) == set(HAND_CHECKED)
    on_game_day = sum(any(rt.date() == mos.kick_date(games.start_utc[g]) for rt in runs[runs.game_id == g].runtime)
                      for g in games.index)
    assert on_game_day >= 10          # the game day's own runs were there to be (wrongly) used, and weren't


@pytest.mark.parametrize("gid", sorted(HAND_CHECKED))
def test_run_selection_matches_the_hand_check(gid):
    from datetime import timedelta
    runs, games = _hand_checked()
    kick = games.start_utc[gid]
    sel = mos.select_runs(runs[runs.game_id == gid], kick, how=games.how[gid])
    for n, want in HAND_CHECKED[gid].items():
        if want is None:
            assert sel[n] is None
            continue
        rt, kt, mph = want
        got = sel[n]
        assert got["runtime"] == pd.Timestamp(rt)
        assert got["runtime"].date() == mos.kick_date(kick) - timedelta(days=n)       # no lookahead
        assert got["published_utc"] <= got["bet_by_utc"] < kick
        assert got["wind_kt"] == pytest.approx(kt, abs=1e-9)
        assert got["wind_mph"] == pytest.approx(kt * 1.150779, abs=1e-5) and round(got["wind_mph"], 2) == mph
    fired = any(v is not None and v["wind_mph"] >= 15 for v in sel.values())
    assert fired == (gid in FIRES)


@pytest.mark.skipif(not (ROOT / "data" / "processed" / "mos_replay.parquet").exists(), reason="run scripts/mos_replay.py")
def test_the_replay_rows_match_the_hand_check():
    d = pd.read_parquet(ROOT / "data" / "processed" / "mos_replay.parquet").set_index("game_id")
    for gid, leads in HAND_CHECKED.items():
        for n, want in leads.items():
            v = d.loc[gid, f"mos{n}_mph"]
            assert (np.isnan(v) if want is None else v == pytest.approx(want[1] * mos.KT_TO_MPH, abs=1e-9)), (gid, n)
        assert bool(d.loc[gid, "mos_signal"]) == (gid in FIRES)


# ---------------------------------------------------------------- the descriptive checks (review, Sep 29)
@pytest.mark.skipif(not REPLAYS, reason="run scripts/mos_replay.py first")
@pytest.mark.parametrize("path", REPLAYS, ids=lambda p: p.name)
def test_checks_split_every_signal_once(path):
    import mos_replay_checks as ch
    d = pd.read_parquet(path)
    m = d[d.has_mos]
    sp = ch.split(m)
    assert len(sp["both"]) + len(sp["mos_only"]) == int(m.mos_signal.sum())
    assert sp["both"].obs_signal.all() and not sp["mos_only"].obs_signal.any()
    assert 0 < sp["fisher_p"] <= 1
    assert any("Fisher exact" in line for line in ch.checks(d))


def test_matched_threshold_fires_as_often_as_mos_at_15():
    import mos_replay_checks as ch
    obs = pd.Series(np.random.default_rng(0).gamma(4, 2, 5000))
    mos_ = obs + 1.0                              # a forecast that runs exactly 1 mph high
    t = ch.matched_threshold(mos_, obs)
    assert t == pytest.approx(14.0, abs=0.05)
    assert (obs >= t).mean() == pytest.approx((mos_ >= 15).mean(), abs=0.002)


# ---------------------------------------------------------------- the pull script
@pytest.mark.skipif(not Path("/usr/bin/caffeinate").exists(), reason="macOS only (caffeinate)")
@pytest.mark.parametrize("with_nfl", [True, False])
def test_pull_runs_every_leg_and_stops_if_a_folder_is_gone(tmp_path, with_nfl):
    import shutil
    import subprocess
    scripts = tmp_path / "cfb-weather" / "scripts"
    scripts.mkdir(parents=True)
    shutil.copy(ROOT / "scripts" / "mos_pull_all.sh", scripts)
    if with_nfl:
        (tmp_path / "nfl-weather").mkdir()
    env = dict(PATH="/usr/bin:/bin", HOME=str(tmp_path), PAUSE_S="0", PY_CFB="/bin/echo", PY_NFL="/bin/echo")
    r = subprocess.run(["/bin/sh", str(scripts / "mos_pull_all.sh")], env=env, capture_output=True, text=True)
    legs = [line for line in r.stdout.splitlines() if line.startswith("scripts/mos_fetch.py")]
    if with_nfl:
        assert r.returncode == 0 and "mos_pull_all: finished" in r.stdout
        assert legs == ["scripts/mos_fetch.py --seasons 2023-2025", "scripts/mos_fetch.py", "scripts/mos_fetch.py"]
    else:
        assert r.returncode == 1 and "is gone; stopping" in r.stdout and "finished" not in r.stdout
        assert len(legs) == 2


# ---------------------------------------------------------------- station map
def test_station_map_keeps_only_stations_within_40_km():
    m = pd.read_csv(ROOT / "data" / "processed" / "mos_station_map.csv")
    assert (m.km <= 40).all() and m.icao.str.len().eq(4).all()
    assert m.groupby("venue_id")["rank"].apply(lambda r: list(r) == list(range(len(r)))).all()
    assert m.groupby("venue_id").km.apply(lambda k: k.is_monotonic_increasing).all()
