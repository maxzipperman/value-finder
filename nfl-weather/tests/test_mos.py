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


# ---------------------------------------------------------------- hand-checked real games (full run, Sep 29)
# Worked by hand from output/mos_hand_check.log (scripts/mos_hand_check.py): lead -> (run, knots at the
# kickoff instant, mph as the log prints it). The MOS rows are in tests/fixtures/.
FIX = ROOT / "tests" / "fixtures"
HAND_CHECKED = {
    "2025_01_CIN_CLE": {1: ("2025-09-06 18:00", 29 / 3, 11.12), 2: ("2025-09-05 18:00", 31 / 3, 11.89),
                        3: ("2025-09-04 18:00", 13.5, 15.54)},
    "2024_01_DAL_CLE": {1: ("2024-09-07 18:00", 205 / 18, 13.11), 2: ("2024-09-06 18:00", 367 / 36, 11.73), 3: None},
    "2023_01_DAL_NYG": {1: ("2023-09-09 18:00", 25 / 9, 3.20), 2: ("2023-09-08 18:00", 34 / 9, 4.35), 3: None},
    "2022_02_TEN_BUF": {1: ("2022-09-18 18:00", 12.25, 14.10), 2: ("2022-09-17 18:00", 12.25, 14.10), 3: None},
    "2019_06_NYG_NE": {1: ("2019-10-09 18:00", 41 / 3, 15.73), 2: ("2019-10-08 18:00", 142 / 9, 18.16), 3: None},
    "2021_16_CLE_GB": {1: ("2021-12-24 18:00", 16 / 3, 6.14), 2: ("2021-12-23 18:00", 41 / 6, 7.86), 3: None},
    "2019_09_WAS_BUF": {1: ("2019-11-02 18:00", 17.0, 19.56), 2: ("2019-11-01 18:00", 17.0, 19.56),
                        3: ("2019-10-31 18:00", 16.0, 18.41)},
    "2016_17_NE_MIA": {1: ("2016-12-31 18:00", 13.0, 14.96), 2: ("2016-12-30 18:00", 13.0, 14.96),
                       3: ("2016-12-29 18:00", 15.0, 17.26)},
    "2004_16_DEN_TEN": {1: ("2004-12-24 18:00", 1.0, 1.15), 2: ("2004-12-23 18:00", 1.5, 1.73), 3: None},
    # Andrews (KADW): College Park has no runs before 2010. Lead 3 is 13 kt = 14.96 mph, no; leads 1-2 fire.
    "2009_06_KC_WAS": {1: ("2009-10-17 18:00", 15.0, 17.26), 2: ("2009-10-16 18:00", 40 / 3, 15.34),
                       3: ("2009-10-15 18:00", 13.0, 14.96)},
    # BWI (KBWI): Baltimore Inner Harbor (KDMH) has runs but no wind forecast
    "2024_02_LV_BAL": {1: ("2024-09-14 18:00", 34 / 3, 13.04), 2: ("2024-09-13 18:00", 28 / 3, 10.74),
                       3: ("2024-09-12 18:00", 49 / 6, 9.40)},
}
STATION = {"2009_06_KC_WAS": "KADW", "2024_02_LV_BAL": "KBWI"}      # the next-nearest station each falls back to
FIRES = {"2025_01_CIN_CLE", "2019_06_NYG_NE", "2019_09_WAS_BUF", "2016_17_NE_MIA", "2009_06_KC_WAS"}


def _hand_checked():
    runs = pd.read_csv(FIX / "mos_hand_checked_runs.csv", parse_dates=["runtime", "ftime"])
    games = pd.read_csv(FIX / "mos_hand_checked_games.csv")
    games["start_utc"] = pd.to_datetime(games.start_utc, utc=True)
    return runs, games.set_index("game_id")


def _used(runs, games, gid):
    """The fixture rows of the station the replay used for this game (a nearer station's rows are kept too)."""
    return runs[(runs.game_id == gid) & (runs.station == games.station[gid])]


def test_at_least_ten_hand_checked_games_with_game_day_runs_on_hand():
    runs, games = _hand_checked()
    assert len(HAND_CHECKED) >= 10 and set(games.index) == set(HAND_CHECKED)
    on_game_day = sum(any(rt.date() == mos.kick_date(games.start_utc[g]) for rt in _used(runs, games, g).runtime)
                      for g in games.index)
    assert on_game_day >= 10          # the game day's own runs were there to be (wrongly) used, and weren't


def test_hand_checked_fallback_stations():
    _, games = _hand_checked()
    for gid, icao in STATION.items():
        assert games.station[gid] == icao


@pytest.mark.parametrize("gid", sorted(HAND_CHECKED))
def test_run_selection_matches_the_hand_check(gid):
    from datetime import timedelta
    runs, games = _hand_checked()
    kick = games.start_utc[gid]
    sel = mos.select_runs(_used(runs, games, gid), kick, how=games.how[gid])
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


def test_baltimore_inner_harbor_runs_are_there_but_windless_so_bwi_is_used():
    runs, _ = _hand_checked()
    b = runs[(runs.game_id == "2024_02_LV_BAL") & (runs.station == "KDMH")]
    assert len(b) > 50 and b.wsp.isna().all()
    kick = pd.Timestamp("2024-09-15T17:00:00Z")
    assert [mos.lead_status(b, kick, n, how="kickoff") for n in mos.LEADS] == ["gap or no wind"] * 3
    assert all(v is None for v in mos.select_runs(b, kick, how="kickoff").values())    # so the replay moves on
    bwi = runs[(runs.game_id == "2024_02_LV_BAL") & (runs.station == "KBWI")]
    assert all(v is not None for v in mos.select_runs(bwi, kick, how="kickoff").values())


@pytest.mark.skipif(not (ROOT / "data" / "processed" / "mos_replay.parquet").exists(), reason="run scripts/mos_replay.py")
def test_the_replay_rows_match_the_hand_check():
    d = pd.read_parquet(ROOT / "data" / "processed" / "mos_replay.parquet").set_index("game_id")
    for gid, leads in HAND_CHECKED.items():
        for n, want in leads.items():
            v = d.loc[gid, f"mos{n}_mph"]
            assert (np.isnan(v) if want is None else v == pytest.approx(want[1] * mos.KT_TO_MPH, abs=1e-9)), (gid, n)
        assert bool(d.loc[gid, "mos_signal"]) == (gid in FIRES)


@pytest.mark.skipif(not (ROOT / "data" / "processed" / "mos_replay.parquet").exists(), reason="run scripts/mos_replay.py")
def test_every_forecast_used_was_public_before_the_bet():
    from datetime import timedelta
    d = pd.read_parquet(ROOT / "data" / "processed" / "mos_replay.parquet")
    for n in mos.LEADS:
        u = d[d[f"mos{n}_runtime"].notna()]
        kd = [mos.kick_date(k) for k in u.start_utc]
        rt = pd.to_datetime(u[f"mos{n}_runtime"])
        assert all(r.date() == k - timedelta(days=n) for r, k in zip(rt, kd))
        pub = rt.dt.tz_localize("UTC") + pd.Timedelta(hours=mos.PUBLISH_H)
        bet_by = pd.Series([mos.mac_slot_utc(k - timedelta(days=n)) for k in kd], index=u.index)
        assert (pub <= bet_by).all() and (bet_by < u.start_utc).all()
    fired = pd.concat([d[f"mos{n}_mph"] >= 15 for n in mos.LEADS], axis=1).any(axis=1)
    assert (fired == d.mos_signal).all()


def test_the_fetch_treats_a_windless_answer_as_empty(tmp_path, monkeypatch):
    """The Sep 29 pull crashed here: KDMH's answers have no wsp column. Now they are empty answers,
    so the next-nearest station is fetched, as PR 61 specified."""
    import mos_fetch
    no_wind = ("runtime,ftime,model,n_x,tmp,dpt,cld,p06,p12,station,t06,t12\n"
               "2024-10-12 18:00:00,2024-10-13 00:00:00,GFS,,74,60,CL,,,KDMH,,\n")
    with_wind = ("runtime,ftime,model,n_x,tmp,dpt,cld,wdr,wsp,p06,p12,station,t06,t12\n"
                 "2024-10-12 18:00:00,2024-10-13 00:00:00,GFS,,74,60,CL,300,12,,,KBWI,,\n")
    for station, text in (("KDMH", no_wind), ("KBWI", with_wind), ("KCGS", "runtime,ftime,wsp\n")):
        f = mos.cache_file(station, "2024-09-01", "2024-12-31T18:00", cache=tmp_path)
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(text)
    monkeypatch.setattr(mos, "CACHE", tmp_path)
    w = pd.DataFrame(dict(icao=["KDMH", "KBWI", "KCGS"], season=2024,
                          sts=pd.Timestamp("2024-10-01"), ets=pd.Timestamp("2024-11-01")))
    assert mos_fetch.empty_windows(w) == [("KDMH", 2024), ("KCGS", 2024)]


def test_replay_threshold_is_the_boards():
    from nflweather.board import RULE_B_LEAD, RULE_B_WIND
    from nflweather.market import MIN_UNDER_ODDS
    import mos_replay
    assert mos_replay.WIND == RULE_B_WIND == 15 and mos_replay.MIN_UNDER_ODDS == MIN_UNDER_ODDS
    assert tuple(range(RULE_B_LEAD[0], RULE_B_LEAD[1] + 1)) == mos.LEADS
