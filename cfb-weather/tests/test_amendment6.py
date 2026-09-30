"""Amendment 6 (draft, issue #69): a game with no kickoff time set is not eligible for Rule HT until its time is
set. cfbfastR gives such a game a placeholder of midnight Eastern on its date; before this, the board took the
placeholder as the kickoff, so Rule HT alerted on the 7:30 PM run the evening before the game and graded that
evening's quote. Tests for the board's gate, the alert and the scorer, on a game whose time is set late and on one
whose time is never set."""
import runpy
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cfbweather import board, config, fetch, notify  # noqa: E402

PLACEHOLDER = pd.Timestamp("2026-10-10T04:00:00Z")    # Sat Oct 10, 00:00 Eastern (EDT): cfbfastR's "no time yet"
REAL_KICK = pd.Timestamp("2026-10-10T23:30:00Z")      # the time set later: 7:30 PM Eastern the same day


def set_clock(monkeypatch, at):
    """pd.Timestamp.now returns `at`, for the test, the board and the alert run alike."""
    at = pd.Timestamp(at).tz_convert("UTC")
    monkeypatch.setattr(pd.Timestamp, "now", staticmethod(lambda tz=None: at.tz_convert(tz) if tz is not None
                                                          else at.tz_convert(board.local_zone()).tz_localize(None)))
    return at


def last_run_before(kick):
    """The alert job's last scheduled run before `kick`, on the Mac's own clock (a minute after it starts)."""
    run = board.next_scheduled_run((pd.Timestamp(kick) - pd.Timedelta(days=1)).tz_convert(board.local_zone()))
    while (nxt := board.next_scheduled_run(run)) < kick:
        run = nxt
    return run.tz_convert("UTC") + pd.Timedelta(minutes=1)


# ------------------------------------------------------------------ what "no kickoff time" is
@pytest.mark.parametrize("kick,flag,expected", [
    ("2026-10-10T04:00:00Z", False, True),     # midnight Eastern (EDT): the placeholder, even without the flag
    ("2026-11-14T05:00:00Z", False, True),     # midnight Eastern (EST), after the clock change
    ("2026-10-10T23:30:00Z", True, True),      # the schedule's flag, whatever the time
    ("2026-10-10T23:30:00Z", False, False),    # a set time
    ("2026-10-11T03:59:00Z", False, False),    # 11:59 PM Eastern: how cfbfastR lists a real midnight (Hawaii) kickoff
    ("2026-10-10T05:00:00Z", False, False),    # midnight Central is 1:00 AM Eastern: a real time
])
def test_no_kickoff_time_is_the_flag_or_midnight_eastern(kick, flag, expected):
    got = board.no_kickoff_time(pd.Series([flag]), pd.Series([pd.Timestamp(kick)]))
    assert got.tolist() == [expected]


def test_a_missing_kickoff_is_not_read_as_midnight():
    got = board.no_kickoff_time(False, pd.Series(pd.to_datetime([None, "2026-10-10T04:00:00Z"], utc=True)))
    assert got.tolist() == [False, True]


# ------------------------------------------------------------------ the board
def board_now(monkeypatch, now, games):
    """board.compute, offline: the schedule, venues and ESPN prices are `games`; no forecast, no Odds API."""
    set_clock(monkeypatch, now)
    s = pd.DataFrame([dict(game_id=g["game_id"], season=2026, start_utc=pd.Timestamp(g["kick"]), tbd=g["tbd"],
                           home_division="fbs", away_division="fbs", venue_id=g.get("venue_id", 1),
                           home_team=f"H{g['game_id']}", away_team=f"A{g['game_id']}") for g in games])
    v = pd.DataFrame([dict(venue_id=1, venue_name="Open", city="c", state="s", lat=40.0, lon=-80.0, elevation=0,
                           grass=True, dome=False, timezone="America/New_York"),
                      dict(venue_id=2, venue_name="Dome", city="c", state="s", lat=40.0, lon=-80.0, elevation=0,
                           grass=False, dome=True, timezone="America/New_York")])
    odds = pd.DataFrame([dict(game_id=g["game_id"], mkt_total=g["total"], mkt_under=-110.0, mkt_over=-110.0,
                              line_src="espn", quote_utc="") for g in games])
    monkeypatch.setattr(board, "schedules", lambda: s)
    monkeypatch.setattr(board, "venues", lambda: v)
    monkeypatch.setattr(board, "odds_team_names", lambda: {})
    monkeypatch.setattr(fetch, "espn_week_odds", lambda days: odds)
    return board.compute(refresh=False, prices=False).set_index("game_id")


def test_the_board_holds_rule_ht_until_the_kickoff_time_is_set(monkeypatch):
    games = [dict(game_id=1, kick=PLACEHOLDER, tbd=True, total=66.5),                 # flagged, at the placeholder
             dict(game_id=2, kick=REAL_KICK, tbd=False, total=66.5),                  # timed: signals as before
             dict(game_id=3, kick=PLACEHOLDER, tbd=True, total=55.5),                 # no time, below the threshold
             dict(game_id=4, kick=PLACEHOLDER, tbd=False, total=66.5, venue_id=2),    # midnight, no flag, a dome
             dict(game_id=5, kick="2026-10-11T03:59:00Z", tbd=False, total=66.5)]     # a real 11:59 PM kickoff
    up = board_now(monkeypatch, "2026-10-08T14:31:00Z", games)
    assert up.rule_ht.to_dict() == {1: "time_tbd", 2: "SIGNAL", 3: "below_threshold", 4: "time_tbd", 5: "SIGNAL"}
    assert up.wx_src[1] == "time_tbd" and up.rule_b[1] == "time_tbd"                  # Rule B as before
    assert up.wx_src[4] == "indoor"


def test_a_game_whose_time_is_set_late_is_eligible_from_the_next_run(monkeypatch):
    before = board_now(monkeypatch, "2026-10-09T02:31:00Z", [dict(game_id=1, kick=PLACEHOLDER, tbd=True, total=66.5)])
    after = board_now(monkeypatch, "2026-10-10T18:31:00Z", [dict(game_id=1, kick=REAL_KICK, tbd=False, total=66.5)])
    assert before.rule_ht[1] == "time_tbd" and after.rule_ht[1] == "SIGNAL"


def test_a_game_still_without_a_time_leaves_the_board_at_its_placeholder(monkeypatch):
    """The board shows games that kick off after now, so once the placeholder has passed, a game with no time set is
    no longer logged (and so never alerts) until its time is set."""
    up = board_now(monkeypatch, "2026-10-10T04:01:00Z", [dict(game_id=1, kick=PLACEHOLDER, tbd=True, total=66.5),
                                                         dict(game_id=2, kick=REAL_KICK, tbd=False, total=66.5)])
    assert up.index.tolist() == [2]


# ------------------------------------------------------------------ the alert
def board_row(**kw):
    base = dict(game_id=401, away_team="Southern Miss", home_team="Troy", kick_et="Sat 10-10 00:00", lead_days=1,
                start_utc=PLACEHOLDER, wx_wind=np.nan, wx_temp=np.nan, line_src="pinnacle", mkt_total=66.5,
                mkt_under=-110.0, ev_under=np.nan, rule_b="time_tbd", rule_ht="time_tbd", ht_threshold=62.6175,
                best_under=np.nan, best_under_book="", best_line=np.nan, best_line_under=np.nan, best_line_book="",
                ev_best_line=np.nan)
    return base | kw


def run_alerts(tmp_path, monkeypatch, rows):
    sent = []
    monkeypatch.setattr(config, "ROOT", tmp_path)
    monkeypatch.setattr(board, "compute", lambda **k: pd.DataFrame(rows))
    monkeypatch.setattr(board, "save", lambda up: None)
    monkeypatch.setattr(notify, "send", lambda title, body: sent.append((title, body)) or True)
    monkeypatch.setattr(sys, "argv", ["alerts.py"])
    runpy.run_path(str(ROOT / "scripts" / "alerts.py"), run_name="__main__")
    runs = pd.read_csv(tmp_path / "data" / "forward" / "runs.csv", keep_default_na=False)
    return sent, runs


def test_the_alert_says_a_game_with_no_time_is_not_eligible_then_alerts_once_its_time_is_set(tmp_path, monkeypatch):
    # The evening before: the last scheduled run before the placeholder. The old code alerted "take the latest
    # number" here, and this row became the entry.
    set_clock(monkeypatch, last_run_before(PLACEHOLDER))
    sent, runs = run_alerts(tmp_path, monkeypatch, [board_row()])
    assert len(sent) == 1 and runs.signals.tolist() == [0]
    title, body = sent[0]
    assert title == "CFB HIGH TOTAL 66.5, NOT ELIGIBLE (no kickoff time set): Southern Miss @ Troy Sat 10-10 ET"
    assert "not take a game until its kickoff time is set" in body.replace("doesn't", "does not")
    assert "No bet." in body and "UNDER" not in title
    assert "the schedule has no kickoff time set for this game" in body and "placeholder" not in body
    # Game day: the time is set, and the last scheduled run before the real kickoff alerts as Rule HT always has
    set_clock(monkeypatch, last_run_before(REAL_KICK))
    timed = board_row(start_utc=REAL_KICK, kick_et="Sat 10-10 19:30", rule_ht="SIGNAL", lead_days=0)
    sent, runs = run_alerts(tmp_path, monkeypatch, [timed])
    assert [t for t, _ in sent] == ["CFB HIGH TOTAL UNDER 66.5 at -110 (paper): Southern Miss @ Troy Sat 10-10 19:30 ET"]
    assert runs.signals.tolist() == [0, 1]


def test_no_notice_before_the_last_run_and_none_twice(tmp_path, monkeypatch):
    set_clock(monkeypatch, last_run_before(PLACEHOLDER) - pd.Timedelta(hours=4))     # an earlier run
    sent, _ = run_alerts(tmp_path, monkeypatch, [board_row()])
    assert sent == []
    set_clock(monkeypatch, last_run_before(PLACEHOLDER))
    assert len(run_alerts(tmp_path, monkeypatch, [board_row()])[0]) == 1
    assert run_alerts(tmp_path, monkeypatch, [board_row()])[0] == []                  # sent once


def test_a_game_with_no_time_below_the_threshold_gets_no_notice(tmp_path, monkeypatch):
    set_clock(monkeypatch, last_run_before(PLACEHOLDER))
    sent, _ = run_alerts(tmp_path, monkeypatch, [board_row(rule_ht="below_threshold", mkt_total=55.5)])
    assert sent == []


# ------------------------------------------------------------------ the scorer
def row(gid, kick, snap, **kw):
    kick = pd.Timestamp(kick)
    base = dict(rules_version="cfb-v3-2026-09-28", game_id=gid,
                kick_et=kick.tz_convert("America/New_York").strftime("%a %m-%d %H:%M"), away_team="A", home_team="B",
                venue="V", lead_days=1, wx_src="forecast", wx_wind=5, line_src="pinnacle", mkt_total=66.5,
                mkt_under=-110, mkt_over=-110, ev_under=0.06, ht_threshold=62.6175, rule_b="no_trigger",
                rule_ht="SIGNAL", start_utc=kick.strftime("%Y-%m-%dT%H:%M:%SZ"),
                snapshot_utc=pd.Timestamp(snap).strftime("%Y-%m-%dT%H:%M:%SZ"))
    return base | kw


def untimed(gid, snap, **kw):
    """A row logged while the game had no kickoff time: the placeholder kickoff, and the flag's "time_tbd" weather
    source. rule_ht "SIGNAL" is how the board logged it before amendment 6; "time_tbd" is how it logs it now."""
    return row(gid, PLACEHOLDER, snap, wx_src="time_tbd", rule_b="time_tbd", **kw)


def score(folder, rows, schedule, *extra):
    folder.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(folder / "ledger.csv", index=False)
    pd.DataFrame(schedule).to_csv(folder / "sched.csv", index=False)
    return subprocess.run([sys.executable, str(ROOT / "scripts" / "score_forward.py"), "--ledger",
                           str(folder / "ledger.csv"), "--schedule", str(folder / "sched.csv"), "--now", "2026-11-20",
                           *extra], capture_output=True, text=True, check=True).stdout


def ht(out):
    return out.split("RULE_HT:")[1].split("Variants under")[0]


def sched(gid, total, kick=REAL_KICK, **kw):
    return dict(game_id=gid, home_points=total - 30, away_points=30, completed=True,
                start_date=pd.Timestamp(kick).strftime("%Y-%m-%dT%H:%M:%S.000Z")) | kw


def test_a_game_whose_time_is_set_late_enters_at_its_last_quote_with_a_time(tmp_path):
    """Logged three times with no time (70.5, the kind of number the old code would have graded from the evening
    before), then twice on game day with the time set; the entry is the last of those, 64.5 at -105. The game lands
    on 67: under 70.5 would have won, under 64.5 loses."""
    rows = [untimed(1, "2026-10-08T14:30Z", mkt_total=70.5),
            untimed(1, "2026-10-09T02:30Z", mkt_total=70.5),                          # the evening before, 7:30 PM PT
            untimed(1, "2026-10-09T14:30Z", mkt_total=70.5, rule_ht="time_tbd"),      # as the board logs it now
            row(1, REAL_KICK, "2026-10-10T14:30Z", mkt_total=65.5),
            row(1, REAL_KICK, "2026-10-10T22:30Z", mkt_total=64.5, mkt_under=-105)]
    out = ht(score(tmp_path, rows, [sched(1, 67)]))
    assert "1 signals at the last quote before kickoff, 1 settled, 0 pending, 0 void" in out
    assert "record 0-1-0" in out and "units -1.00" in out
    assert "excluded from Rule HT, logged with no kickoff time set (amendment 6): 3 quotes" in out
    assert "not a bet, never logged with a kickoff time set before kickoff; its last quote would have signalled: 0" in out


def test_a_game_never_logged_with_a_time_is_not_a_bet_and_is_counted(tmp_path):
    """The time was never set before the job stopped logging the game at its placeholder. The old scorer graded the
    evening-before quote (it came before the earlier kickoff); now the game is counted, listed and not graded."""
    rows = [untimed(7, "2026-10-08T14:30Z"), untimed(7, "2026-10-09T02:30Z"),
            row(8, REAL_KICK, "2026-10-10T22:30Z", mkt_total=64.5)]                  # an ordinary bet beside it
    out = score(tmp_path, rows, [sched(7, 50), sched(8, 50)], "--list-excluded")
    assert "1 signals at the last quote before kickoff, 1 settled" in ht(out)
    assert "record 1-0-0" in ht(out)
    assert "excluded from Rule HT, logged with no kickoff time set (amendment 6): 2 quotes" in ht(out)
    assert ("not a bet, never logged with a kickoff time set before kickoff; its last quote would have signalled: 1 (7)"
            in ht(out))
    listed = [ln for ln in ht(out).splitlines() if "Rule HT: logged with no kickoff time set" in ln]
    assert len(listed) == 2 and all(" 7 " in ln for ln in listed)


def test_a_game_with_no_time_and_no_signal_is_counted_but_not_called_a_lost_bet(tmp_path):
    rows = [untimed(7, "2026-10-09T02:30Z", mkt_total=55.5, rule_ht="below_threshold")]
    out = ht(score(tmp_path, rows, [sched(7, 50)]))
    assert "0 signals" in out and "no kickoff time set (amendment 6): 1 quotes" in out
    assert "its last quote would have signalled: 0" in out


def test_rows_logged_before_amendment_6_are_known_by_what_they_carry(tmp_path):
    """A row the old board logged at a dome (weather source "indoor") is known by its midnight kickoff; one whose
    schedule flag was set with a real-looking time is known by its weather source. Neither is graded. A real 11:59 PM
    Eastern kickoff (how cfbfastR lists a Hawaii night game) is graded as before."""
    late = pd.Timestamp("2026-10-11T03:59:00Z")
    rows = [row(1, PLACEHOLDER, "2026-10-09T02:30Z", wx_src="indoor"),
            row(2, REAL_KICK, "2026-10-10T14:30Z", wx_src="time_tbd", rule_b="time_tbd"),
            row(3, late, "2026-10-10T22:30Z")]
    out = ht(score(tmp_path, rows, [sched(1, 50), sched(2, 50), sched(3, 50, kick=late)]))
    assert "1 signals at the last quote before kickoff, 1 settled" in out and "record 1-0-0" in out
    assert "no kickoff time set (amendment 6): 2 quotes" in out
    assert "its last quote would have signalled: 2 (1, 2)" in out


def test_rule_b_is_unchanged_by_amendment_6(tmp_path):
    """Rule B can't signal without a time (its status is time_tbd), and its entries and closes are read as before."""
    rows = [row(5, REAL_KICK, "2026-10-08T14:30Z", rule_b="SIGNAL", mkt_total=50.5, rule_ht="below_threshold"),
            untimed(6, "2026-10-08T14:30Z", mkt_total=50.5, rule_ht="below_threshold"),
            row(5, REAL_KICK, "2026-10-10T20:30Z", mkt_total=49.5, rule_ht="below_threshold")]
    out = score(tmp_path, rows, [sched(5, 40), sched(6, 40)])
    rb = out.split("RULE_B:")[1].split("RULE_HT:")[0]
    assert "1 signals, 1 settled" in rb and "mean CLV +1.00" in rb


# ------------------------------------------------------------------ a placeholder in the schedule the scorer reads
@pytest.mark.parametrize("schedule", [
    dict(kick=PLACEHOLDER),                                 # 00:00 Eastern, no flag column
    dict(kick=PLACEHOLDER, start_time_tbd=True),            # 00:00 Eastern and the flag, as cfbfastR writes it
    dict(kick=REAL_KICK, start_time_tbd=True),              # a flag left set on a real time (Oregon-UCLA, 2020)
])
def test_a_placeholder_in_the_schedule_is_no_kickoff(tmp_path, schedule):
    """The review's case: the schedule the scorer reads still carries the placeholder after the game was played, as
    the final schedule does for Utah State-Robert Morris (Aug 31, 2024). Read as a kickoff, the placeholder (00:00
    Eastern) was "the earlier kickoff", so the game-day row with the time set was dropped as logged at or after
    kickoff and the entry fell back to the evening before (68.5, a win at 67). A placeholder is no schedule kickoff:
    the entry is the game-day row, 64.5 at -105, a loss."""
    rows = [untimed(1, "2026-10-08T14:30Z", mkt_total=70.5, rule_ht="time_tbd"),
            row(1, REAL_KICK, "2026-10-09T14:30Z", mkt_total=69.5),                 # time set a day ahead
            row(1, REAL_KICK, "2026-10-10T02:30Z", mkt_total=68.5),                 # the evening before
            row(1, REAL_KICK, "2026-10-10T22:30Z", mkt_total=64.5, mkt_under=-105)]  # game day, an hour before
    out = score(tmp_path, rows, [sched(1, 67, **schedule)], "--list-excluded")
    assert "logged at or after kickoff" not in out and "ledger rows: 4; in the test: 4" in out
    assert "ledger games whose schedule kickoff is cfbfastR's placeholder, read as no schedule kickoff" in out
    assert "1 signals at the last quote before kickoff, 1 settled, 0 pending, 0 void" in ht(out)
    assert "record 0-1-0" in ht(out) and "units -1.00" in ht(out)
    assert "no kickoff time set (amendment 6): 1 quotes" in ht(out)


def test_a_schedule_with_a_time_is_read_as_before(tmp_path):
    """The same rows against a schedule that shows the real time: nothing is read as a placeholder."""
    rows = [row(1, REAL_KICK, "2026-10-10T02:30Z", mkt_total=68.5),
            row(1, REAL_KICK, "2026-10-10T22:30Z", mkt_total=64.5, mkt_under=-105),
            row(1, REAL_KICK, "2026-10-10T23:45Z", mkt_total=60.5)]                  # after kickoff: dropped
    out = score(tmp_path, rows, [sched(1, 67, start_time_tbd=False)])
    assert "cfbfastR's placeholder" not in out.split("RULE_B:")[0]
    assert "excluded, logged at or after kickoff: 1" in out
    assert "record 0-1-0" in ht(out)


def test_rule_b_reads_a_placeholder_in_the_schedule_as_no_kickoff_too(tmp_path):
    """Rule B's close is the last quote logged after its entry and before kickoff; with the placeholder read as the
    schedule's kickoff, the game-day close was dropped and the bet had no primary close."""
    rows = [row(5, REAL_KICK, "2026-10-08T14:30Z", rule_b="SIGNAL", mkt_total=50.5, rule_ht="below_threshold"),
            row(5, REAL_KICK, "2026-10-10T20:30Z", mkt_total=49.5, rule_ht="below_threshold")]
    rb = score(tmp_path, rows, [sched(5, 40, kick=PLACEHOLDER, start_time_tbd=True)]).split("RULE_B:")[1]
    assert "1 signals, 1 settled" in rb and "mean CLV +1.00" in rb


@pytest.mark.parametrize("schedule_kick", ["2026-11-14T05:00:00Z", "2026-11-14T20:00:00Z"])
def test_an_eastern_standard_time_placeholder(tmp_path, schedule_kick):
    """After the clock change the placeholder is 05:00 UTC (00:00 EST). Rows logged at it are not Rule HT quotes,
    whether the schedule the scorer reads still shows the placeholder or the real time (3:00 PM Eastern)."""
    est, real = pd.Timestamp("2026-11-14T05:00:00Z"), pd.Timestamp("2026-11-14T20:00:00Z")
    rows = [row(3, est, "2026-11-12T15:30Z", wx_src="time_tbd", rule_b="time_tbd", mkt_total=70.5),
            row(3, est, "2026-11-14T03:30Z", wx_src="time_tbd", rule_b="time_tbd", mkt_total=70.5),  # evening before
            row(3, real, "2026-11-14T15:30Z", mkt_total=64.5)]                                       # game day, timed
    out = score(tmp_path, rows, [sched(3, 67, kick=schedule_kick)])
    assert "logged at or after kickoff" not in out
    assert "1 signals at the last quote before kickoff, 1 settled, 0 pending, 0 void" in ht(out)
    assert "record 0-1-0" in ht(out)
    assert "no kickoff time set (amendment 6): 2 quotes" in ht(out)
    assert "its last quote would have signalled: 0" in ht(out)


def test_a_real_kickoff_more_than_24_hours_after_the_placeholder(tmp_path):
    """A known limit (section 3). Hawai'i-New Mexico, Oct 17, 2026, has no time set; its placeholder is 04:00 UTC Oct
    17. Set at 7:00 PM Hawaii time, the kickoff is 05:00 UTC Oct 18, 25 hours later, so the rows logged with the time
    are a second listing (amendment 4, section 10). That listing is graded as usual; the listing logged before the
    time was set is counted as never logged with a kickoff time, although the game was: the count is spurious here."""
    ph, hi = pd.Timestamp("2026-10-17T04:00:00Z"), pd.Timestamp("2026-10-18T05:00:00Z")
    rows = [row(9, ph, "2026-10-15T14:30Z", wx_src="time_tbd", rule_b="time_tbd", rule_ht="time_tbd"),
            row(9, ph, "2026-10-16T02:30Z", wx_src="time_tbd", rule_b="time_tbd", rule_ht="time_tbd"),
            row(9, hi, "2026-10-17T14:30Z", mkt_total=67.5),
            row(9, hi, "2026-10-18T02:30Z", mkt_total=66.5)]             # 7:30 PM Pacific, the last run before
    out = ht(score(tmp_path, rows, [sched(9, 60, kick=hi)]))
    assert "1 signals at the last quote before kickoff, 1 settled, 0 pending, 0 void" in out
    assert "record 1-0-0" in out
    assert "no kickoff time set (amendment 6): 2 quotes" in out
    assert "its last quote would have signalled: 1 (9)" in out                  # the spurious count
    # Set at 00:00 Eastern instead, the real kickoff reads as the placeholder: never eligible, and counted
    rows = [row(9, ph, "2026-10-15T14:30Z", wx_src="time_tbd", rule_b="time_tbd", rule_ht="time_tbd"),
            row(9, ph, "2026-10-16T02:30Z", mkt_total=66.5, rule_ht="time_tbd")]
    out = ht(score(tmp_path / "midnight", rows, [sched(9, 60, kick=ph)]))
    assert "0 signals" in out and "its last quote would have signalled: 1 (9)" in out
