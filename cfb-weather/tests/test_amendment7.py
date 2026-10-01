"""Amendment 7 (draft, issue #69): a game with no kickoff time set is not eligible for Rule HT until its time is
set. cfbfastR gives such a game a placeholder of midnight Eastern on its date; before this, the board took the
placeholder as the kickoff, so Rule HT alerted on the 7:30 PM run the evening before the game and graded that
evening's quote. Tests for the board's gate, the alert and the scorer, on a game whose time is set late and on one
whose time is never set; and, for a schedule that still shows the placeholder once the game is completed, the
scorer's verified kickoff (kickoff_verifications.csv), its quarantine of a game with none, and the FINAL it withholds
meanwhile."""
import runpy
import shutil
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
    assert "the schedule marks this game's kickoff time as not set" in body and "placeholder" not in body
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
LAST_UNTIMED = "its last quote was logged with no kickoff time set, and would have signalled"


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
    source. rule_ht "SIGNAL" is how the board logged it before amendment 7; "time_tbd" is how it logs it now."""
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
    assert "excluded from Rule HT, logged with no kickoff time set (amendment 7): 3 quotes" in out
    assert "not a bet, its last quote was logged with no kickoff time set, and would have signalled: 0" in out


def test_a_game_never_logged_with_a_time_is_not_a_bet_and_is_counted(tmp_path):
    """The time was never set before the job stopped logging the game at its placeholder. The old scorer graded the
    evening-before quote (it came before the earlier kickoff); now the game is counted, listed and not graded."""
    rows = [untimed(7, "2026-10-08T14:30Z"), untimed(7, "2026-10-09T02:30Z"),
            row(8, REAL_KICK, "2026-10-10T22:30Z", mkt_total=64.5)]                  # an ordinary bet beside it
    out = score(tmp_path, rows, [sched(7, 50), sched(8, 50)], "--list-excluded")
    assert "1 signals at the last quote before kickoff, 1 settled" in ht(out)
    assert "record 1-0-0" in ht(out)
    assert "excluded from Rule HT, logged with no kickoff time set (amendment 7): 2 quotes" in ht(out)
    assert (f"not a bet, {LAST_UNTIMED}: 1 (7)"
            in ht(out))
    listed = [ln for ln in ht(out).splitlines() if "Rule HT: logged with no kickoff time set" in ln]
    assert len(listed) == 2 and all(" 7 " in ln for ln in listed)


def test_a_game_with_no_time_and_no_signal_is_counted_but_not_called_a_lost_bet(tmp_path):
    rows = [untimed(7, "2026-10-09T02:30Z", mkt_total=55.5, rule_ht="below_threshold")]
    out = ht(score(tmp_path, rows, [sched(7, 50)]))
    assert "0 signals" in out and "no kickoff time set (amendment 7): 1 quotes" in out
    assert "and would have signalled: 0" in out


def test_rows_logged_before_amendment_7_are_known_by_what_they_carry(tmp_path):
    """A row the old board logged at a dome (weather source "indoor") is known by its midnight kickoff; one whose
    schedule flag was set with a real-looking time is known by its weather source. Neither is graded. A real 11:59 PM
    Eastern kickoff (how cfbfastR lists a Hawaii night game) is graded as before."""
    late = pd.Timestamp("2026-10-11T03:59:00Z")
    rows = [row(1, PLACEHOLDER, "2026-10-09T02:30Z", wx_src="indoor"),
            row(2, REAL_KICK, "2026-10-10T14:30Z", wx_src="time_tbd", rule_b="time_tbd"),
            row(3, late, "2026-10-10T22:30Z")]
    out = ht(score(tmp_path, rows, [sched(1, 50), sched(2, 50), sched(3, 50, kick=late)]))
    assert "1 signals at the last quote before kickoff, 1 settled" in out and "record 1-0-0" in out
    assert "no kickoff time set (amendment 7): 2 quotes" in out
    assert "and would have signalled: 2 (1, 2)" in out


def test_rule_b_is_unchanged_by_amendment_7(tmp_path):
    """Rule B can't signal without a time (its status is time_tbd), and its entries and closes are read as before."""
    rows = [row(5, REAL_KICK, "2026-10-08T14:30Z", rule_b="SIGNAL", mkt_total=50.5, rule_ht="below_threshold"),
            untimed(6, "2026-10-08T14:30Z", mkt_total=50.5, rule_ht="below_threshold"),
            row(5, REAL_KICK, "2026-10-10T20:30Z", mkt_total=49.5, rule_ht="below_threshold")]
    out = score(tmp_path, rows, [sched(5, 40), sched(6, 40)])
    rb = out.split("RULE_B:")[1].split("RULE_HT:")[0]
    assert "1 signals, 1 settled" in rb and "mean CLV +1.00" in rb


# ------------------------------------------------------------------ a placeholder in the schedule the scorer reads
PH_LINE = "ledger games whose schedule kickoff is cfbfastR's placeholder (00:00 Eastern; amendment 7)"
QUARANTINED = "completed game, schedule shows the placeholder and no verified kickoff is recorded (amendment 7)"
WITHHELD = "FINAL withheld: 1 completed game awaits kickoff verification (1)"


def verified(folder, *games):
    """A kickoff_verifications.csv in `folder`, one line per (game id, kickoff), and the scorer's argument to read it.
    The source is a box score: never the ledger or the schedule."""
    folder.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([dict(game_id=g, kickoff_utc=pd.Timestamp(k).strftime("%Y-%m-%dT%H:%M:%SZ"), source="box score",
                       verified_on="2026-10-12", note="") for g, k in games],
                 columns=["game_id", "kickoff_utc", "source", "verified_on", "note"]).to_csv(folder / "v.csv",
                                                                                          index=False)
    return ["--verifications", str(folder / "v.csv")]


def rb(out):
    return out.split("RULE_B:")[1].split("RULE_HT:")[0]


def test_the_committed_verification_file_is_empty_and_read_by_default(tmp_path):
    """The committed file holds the header only: no kickoff has been verified. The scorer reads it by default."""
    assert (ROOT / "kickoff_verifications.csv").read_text() == "game_id,kickoff_utc,source,verified_on,note\n"
    rows = [row(1, REAL_KICK, "2026-10-09T14:30Z")]
    out = score(tmp_path, rows, [sched(1, 50, kick=PLACEHOLDER)])
    assert f"{PH_LINE}, completed, no verified kickoff (quarantined, not graded): 1 (1)" in out


@pytest.mark.parametrize("schedule", [dict(kick=PLACEHOLDER), dict(kick=PLACEHOLDER, start_time_tbd=True)])
def test_a_completed_placeholder_game_is_quarantined_until_its_kickoff_is_verified(tmp_path, schedule):
    """The first review's case: the schedule the scorer reads still carries the placeholder after the game was played,
    as the final schedule does for Utah State-Robert Morris (Aug 31, 2024). Read as the kickoff, the placeholder (00:00
    Eastern) is "the earlier kickoff", so the game-day row is dropped and the entry falls back to the evening before
    (68.5, a win at 67). Neither the placeholder nor the rows' own kickoff says when the game began, so with no verified
    kickoff the game is quarantined: no row of it is graded, and Rule HT's FINAL is withheld. With the real kickoff
    verified, the registered rules apply as to any game: the entry is the game-day row, 64.5 at -105, a loss."""
    rows = [untimed(1, "2026-10-08T14:30Z", mkt_total=70.5, rule_ht="time_tbd"),
            row(1, REAL_KICK, "2026-10-09T14:30Z", mkt_total=69.5),                 # time set a day ahead
            row(1, REAL_KICK, "2026-10-10T02:30Z", mkt_total=68.5),                 # the evening before
            row(1, REAL_KICK, "2026-10-10T22:30Z", mkt_total=64.5, mkt_under=-105)]  # game day, an hour before
    out = score(tmp_path, rows, [sched(1, 67, **schedule)], "--list-excluded")
    assert "ledger rows: 4; in the test: 0" in out and f"excluded, {QUARANTINED}: 4" in out
    assert f"{PH_LINE}, completed, no verified kickoff (quarantined, not graded): 1 (1)" in out
    assert f"{PH_LINE}, completed, kickoff verified: 0" in out and f"{PH_LINE}, not yet played: 0" in out
    assert "0 signals at the last quote before kickoff, 0 settled, 0 pending, 0 void" in ht(out)
    assert "  record " not in ht(out) and WITHHELD in ht(out) and "INTERIM" in ht(out)
    out = score(tmp_path / "v", rows, [sched(1, 67, **schedule)], *verified(tmp_path / "v", (1, REAL_KICK)))
    assert QUARANTINED not in out and "logged at or after kickoff" not in out
    assert "ledger rows: 4; in the test: 4" in out
    assert f"{PH_LINE}, completed, kickoff verified: 1 (1)" in out
    assert "1 signals at the last quote before kickoff, 1 settled, 0 pending, 0 void" in ht(out)
    assert "record 0-1-0" in ht(out) and "units -1.00" in ht(out) and "FINAL withheld" not in out
    assert "no kickoff time set (amendment 7): 1 quotes" in ht(out)


def test_a_placeholder_game_not_yet_played_keeps_the_placeholder_and_is_not_quarantined(tmp_path):
    """A game not yet completed is not graded anyway. Its schedule kickoff stays the placeholder, as on main: a row
    logged after it is logged at or after kickoff. It is not quarantined; while it has a signal, it holds the FINAL of
    that rule (below), and says so as a game not yet completed."""
    rows = [row(1, REAL_KICK, "2026-10-09T14:30Z", rule_b="SIGNAL", mkt_total=66.5),
            row(1, REAL_KICK, "2026-10-10T20:30Z", mkt_total=64.5)]
    out = score(tmp_path, rows, [sched(1, 50, kick=PLACEHOLDER, start_time_tbd=True, completed=False)],
                "--now", "2026-10-20")
    assert f"{PH_LINE}, not yet played: 1 (1)" in out
    assert f"{PH_LINE}, completed, no verified kickoff (quarantined, not graded): 0" in out
    assert QUARANTINED not in out and "awaits kickoff verification" not in out
    assert "excluded, logged at or after kickoff: 1" in out and OPEN_HELD in rb(out) and OPEN_HELD in ht(out)
    assert "1 signals, 0 settled, 1 pending" in rb(out) and "0 settled, 1 pending" in ht(out)


def test_with_no_completed_mark_in_the_schedule_a_final_score_makes_a_game_completed(tmp_path):
    """A schedule given with --schedule may have no "completed" column: a placeholder game with a final score is then
    completed, and quarantined; one with no score is not yet played."""
    rows = [row(1, REAL_KICK, "2026-10-09T14:30Z"), row(2, REAL_KICK, "2026-10-09T14:30Z")]
    s = [{k: v for k, v in sched(g, 50, kick=PLACEHOLDER).items() if k != "completed"} for g in (1, 2)]
    s[1] |= dict(home_points=None, away_points=None)
    out = score(tmp_path, rows, s, "--now", "2026-10-20")
    assert f"{PH_LINE}, completed, no verified kickoff (quarantined, not graded): 1 (1)" in out
    assert f"{PH_LINE}, not yet played: 1 (2)" in out and f"excluded, {QUARANTINED}: 1" in out


def test_a_flag_on_a_real_time_keeps_that_time_as_the_schedule_kickoff(tmp_path):
    """A flag left set on a real time (Oregon-UCLA, 2020) is not a placeholder: only 00:00 Eastern is. The schedule's
    real time is still the kickoff, for "before kickoff" as for the moved-game check."""
    rows = [row(1, REAL_KICK, "2026-10-10T02:30Z", mkt_total=68.5),
            row(1, REAL_KICK, "2026-10-10T22:30Z", mkt_total=64.5, mkt_under=-105),
            row(1, REAL_KICK, "2026-10-10T23:45Z", mkt_total=60.5)]                  # after kickoff: dropped
    out = score(tmp_path, rows, [sched(1, 67, start_time_tbd=True)])
    assert PH_LINE not in out and QUARANTINED not in out         # no placeholder in the schedule: the report as it was
    assert "excluded, logged at or after kickoff: 1" in out
    assert "record 0-1-0" in ht(out)


def test_a_verification_never_replaces_a_time_the_schedule_shows(tmp_path):
    """A verified kickoff is used only where the schedule shows the placeholder. Where it shows a time, that time is the
    kickoff, and the scorer names the verification it didn't use; it names one for a game not in the ledger too."""
    rows = [row(1, REAL_KICK, "2026-10-10T02:30Z", mkt_total=68.5),
            row(1, REAL_KICK, "2026-10-10T22:30Z", mkt_total=64.5, mkt_under=-105)]
    out = score(tmp_path, rows, [sched(1, 67)], *verified(tmp_path, (1, "2026-10-10T16:00:00Z"), (99, REAL_KICK)))
    assert "kickoff verifications not used, the game is not in the ledger (amendment 7): 1 (99)" in out
    assert ("kickoff verifications not used, the schedule doesn't show the placeholder for the game (amendment 7): "
            "1 (1)") in out
    assert "logged at or after kickoff" not in out and "record 0-1-0" in ht(out)


@pytest.mark.parametrize("line,why", [
    ("1,2026-10-10 16:00,box score,2026-10-12,\n", "game 1: a kickoff that is not a UTC time"),
    ("1,2026-10-10T16:00:00Z,,2026-10-12,\n", "game 1: no source"),
    ("1,2026-10-10T16:00:00Z,box score,2026-10-12,\n" * 2, "game 1 is listed more than once"),
    ("x,2026-10-10T16:00:00Z,box score,2026-10-12,\n", "a game id that is not a number"),
    ("1,2026-10-10T16:00:00Z,box score,2026-10-12,a,b\n", "line 2 has 6 fields, not 5"),
    ("1,2026-10-10T16:00:00Z,box score\n", "line 2 has 3 fields, not 5"),
    ("1,2026-10-10T16:00:00Z,box score,2026-11-21,\n", "game 1: verified_on 2026-11-21 is after this run's date "
                                                         "(2026-11-20)")])
def test_a_damaged_verification_file_verifies_nothing(tmp_path, line, why):
    """A bad line, a line with the wrong number of fields, or a verification dated after the run's clock makes the
    whole file unreadable: every completed placeholder game stays quarantined, and the scorer says why."""
    rows = [row(1, REAL_KICK, "2026-10-09T14:30Z")]
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "v.csv").write_text("game_id,kickoff_utc,source,verified_on,note\n" + line)
    out = score(tmp_path, rows, [sched(1, 50, kick=PLACEHOLDER)], "--verifications", str(tmp_path / "v.csv"))
    assert f"kickoff verifications: v.csv is unreadable (ValueError: {why}" in out
    assert f"{PH_LINE}, completed, no verified kickoff (quarantined, not graded): 1 (1)" in out
    assert f"excluded, {QUARANTINED}: 1" in out


EARLY = pd.Timestamp("2026-10-10T19:30:00Z")          # 3:30 PM Eastern: the game moved four hours earlier
MOVED_LATER = pd.Timestamp("2026-10-12T23:30:00Z")    # two days later


@pytest.mark.parametrize("flag", [True, False])
def test_a_flagged_real_time_moved_earlier_still_drops_the_in_play_row(tmp_path, flag):
    """The second review's case: the schedule shows the game kicked off at 3:30 PM Eastern (flag set or not), while
    the rows still carry 7:30 PM. A row logged at 5:30 PM Eastern is in play: it is not Rule HT's entry, and not Rule
    B's close, as on main."""
    rows = [row(1, REAL_KICK, "2026-10-08T14:30Z", mkt_total=66.5),
            row(1, REAL_KICK, "2026-10-10T21:30Z", mkt_total=58.5, mkt_under=-105)]  # 2 h after the real kickoff
    out = score(tmp_path, rows, [sched(1, 67, kick=EARLY, start_time_tbd=flag)])
    assert "excluded, logged at or after kickoff: 1" in out
    assert "1 signals at the last quote before kickoff, 1 settled" in ht(out) and "record 0-1-0" in ht(out)  # 66.5
    rows = [row(1, REAL_KICK, "2026-10-08T14:30Z", rule_b="SIGNAL", mkt_total=50.5, rule_ht="below_threshold"),
            row(1, REAL_KICK, "2026-10-10T21:30Z", mkt_total=44.5, rule_ht="below_threshold")]
    out = score(tmp_path / "b", rows, [sched(1, 40, kick=EARLY, start_time_tbd=flag)])
    assert "1 signals, 1 settled" in rb(out) and "0 from a later logged quote" in rb(out) and "1 with none" in rb(out)


def test_a_flagged_real_time_moved_two_days_later_is_void(tmp_path):
    rows = [row(1, REAL_KICK, "2026-10-08T14:30Z", rule_b="SIGNAL", mkt_total=50.5),
            row(1, REAL_KICK, "2026-10-10T20:30Z", mkt_total=49.5)]
    out = score(tmp_path, rows, [sched(1, 40, kick=MOVED_LATER, start_time_tbd=True)])
    assert "1 signals, 0 settled, 0 pending, 1 void" in rb(out)
    assert "kicked off more than 24 hours from the kickoff on its entry row: 1 (1)" in rb(out)
    assert "1 void" in ht(out)


def test_a_game_postponed_a_week_to_a_placeholder(tmp_path):
    """Signalled for Oct 10; the final schedule has the game on Oct 17 with no time set. Unverified, it is quarantined
    (neither rule grades it, and both FINALs are withheld). Verified at 7:30 PM Eastern Oct 17, the bet is void as a
    moved game, as on main."""
    rows = [row(1, REAL_KICK, "2026-10-08T14:30Z", rule_b="SIGNAL", mkt_total=50.5),
            row(1, REAL_KICK, "2026-10-10T20:30Z", mkt_total=49.5)]
    s = [sched(1, 40, kick="2026-10-17T04:00:00Z", start_time_tbd=True)]
    out = score(tmp_path, rows, s)
    assert f"excluded, {QUARANTINED}: 2" in out and "0 signals" in rb(out) and "0 signals" in ht(out)
    assert WITHHELD in rb(out) and WITHHELD in ht(out)
    out = score(tmp_path / "v", rows, s, *verified(tmp_path / "v", (1, "2026-10-17T23:30:00Z")))
    assert "1 signals, 0 settled, 0 pending, 1 void" in rb(out)
    assert "kicked off more than 24 hours from the kickoff on its entry row: 1 (1)" in rb(out)
    assert "1 void" in ht(out) and "0 settled" in ht(out) and "FINAL withheld" not in out


def test_a_game_moved_up_a_day_to_a_placeholder(tmp_path):
    """Signalled for Oct 10 at 7:30 PM Eastern; the final schedule has the game on Oct 9 with no time set. Verified at
    noon Eastern Oct 9, a row logged on Oct 10 is after the game: it is not Rule B's close, and the bet is void."""
    rows = [row(1, REAL_KICK, "2026-10-08T14:30Z", rule_b="SIGNAL", mkt_total=50.5, rule_ht="below_threshold"),
            row(1, REAL_KICK, "2026-10-10T21:30Z", mkt_total=44.5, rule_ht="below_threshold")]
    s = [sched(1, 40, kick="2026-10-09T04:00:00Z", start_time_tbd=True)]
    out = score(tmp_path, rows, s)
    assert f"excluded, {QUARANTINED}: 2" in out and WITHHELD in rb(out) and "FINAL withheld" not in ht(out)
    out = score(tmp_path / "v", rows, s, *verified(tmp_path / "v", (1, "2026-10-09T16:00:00Z")))
    assert "excluded, logged at or after kickoff: 1" in out
    assert f"{PH_LINE}, completed, kickoff verified: 1 (1)" in out
    assert "1 signals, 0 settled, 0 pending, 1 void" in rb(out)


def test_the_placeholder_count_splits_verified_quarantined_and_not_yet_played_games(tmp_path):
    rows = [row(g, REAL_KICK, "2026-10-09T14:30Z") for g in (1, 2, 3, 4)]
    s = [sched(1, 50, kick=PLACEHOLDER), sched(2, 50, kick=PLACEHOLDER) | dict(completed=False), sched(3, 50),
         sched(4, 50, kick=PLACEHOLDER)]
    out = score(tmp_path, rows, s, "--list-excluded", *verified(tmp_path, (4, REAL_KICK)))
    assert f"{PH_LINE}, completed, kickoff verified: 1 (4)" in out
    assert f"{PH_LINE}, completed, no verified kickoff (quarantined, not graded): 1 (1)" in out
    assert f"{PH_LINE}, not yet played: 1 (2)" in out
    listed = out.split(f"{PH_LINE}, not yet played")[1].split("ledger rows")[0]
    assert "schedule_kickoff" in listed and "verified_kickoff" in listed and "2026-10-10 04:00:00+00:00" in listed
    line4 = next(ln for ln in listed.splitlines() if ln.split()[:1] == ["4"])
    assert "2026-10-10 23:30:00+00:00" in line4                       # game 4's verified kickoff
    assert "ledger rows: 4; in the test: 3" in out and f"excluded, {QUARANTINED}: 1" in out


def test_rule_b_reads_a_verified_kickoff_like_a_time_in_the_schedule(tmp_path):
    """Rule B's close is the last quote logged after its entry and before kickoff. With the placeholder read as the
    kickoff the game-day close was dropped; unverified, the game is quarantined; verified, the close counts."""
    rows = [row(5, REAL_KICK, "2026-10-08T14:30Z", rule_b="SIGNAL", mkt_total=50.5, rule_ht="below_threshold"),
            row(5, REAL_KICK, "2026-10-10T20:30Z", mkt_total=49.5, rule_ht="below_threshold")]
    s = [sched(5, 40, kick=PLACEHOLDER, start_time_tbd=True)]
    out = score(tmp_path, rows, s)
    assert "0 signals" in rb(out) and "FINAL withheld: 1 completed game awaits kickoff verification (5)" in rb(out)
    out = score(tmp_path / "v", rows, s, *verified(tmp_path / "v", (5, REAL_KICK)))
    assert "1 signals, 1 settled" in rb(out) and "mean CLV +1.00" in rb(out)


# ------------------------------------------------------------------ the captured close (amendment 6, section 1)
REFUSED = "close captured outside the window for this listing (2 to 20 minutes before its kickoff)"
ASIDE = "capture set aside: outside the window for this listing; another capture inside it is used"


def capture(gid, captured, kick, total):
    """A row of closes.csv as scripts/capture_close.py writes it: captured at `captured` for the kickoff `kick`."""
    z = lambda x: pd.Timestamp(x).strftime("%Y-%m-%dT%H:%M:%SZ")
    return dict(capture_utc=z(captured), game_id=gid, start_utc=z(kick), home_team="B", away_team="A",
                line_src="pinnacle", close_total=total, close_under=-110, close_over=-110)


def score_with_closes(folder, rows, schedule, closes, *extra):
    folder.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(closes).to_csv(folder / "closes.csv", index=False)
    return score(folder, rows, schedule, *extra)


def rb_signal(gid, kick=REAL_KICK, entry=50.5):
    """A Rule B signal logged two days out, with no later quote: its primary close can only be the captured close."""
    return row(gid, kick, pd.Timestamp(kick) - pd.Timedelta(days=2), rule_b="SIGNAL", mkt_total=entry,
               rule_ht="below_threshold")


MIN = pd.Timedelta(minutes=1)
EVENING_BEFORE = PLACEHOLDER - 10 * MIN     # 11:50 PM Eastern, Oct 9: 10 minutes before the placeholder


@pytest.mark.parametrize("flag", [True, False])
def test_a_verified_placeholder_game_is_graded_on_its_game_day_captured_close(tmp_path, flag):
    """Amendment 6 measures the capture window from the listing's kickoff, the bound "before kickoff" gives. With the
    placeholder in the schedule that bound is the verified kickoff (amendment 7), so the genuine close, captured 10
    minutes before it, is Rule B's primary close. Read against the placeholder, the window would be 11:40-11:58 PM
    Eastern the evening before, and this close would be refused."""
    out = score_with_closes(tmp_path, [rb_signal(1)], [sched(1, 40, kick=PLACEHOLDER, start_time_tbd=flag)],
                            [capture(1, REAL_KICK - 10 * MIN, REAL_KICK, 48.5)], *verified(tmp_path, (1, REAL_KICK)))
    r = rb(out)
    assert "1 signals, 1 settled, 0 pending, 0 void" in r and "mean CLV +2.00" in r
    assert "primary close: 0 from a later logged quote, 1 from the captured close, 0 with none" in r
    assert "refused" not in r and "set aside" not in r


def test_a_verified_placeholder_game_refuses_a_capture_from_the_evening_before(tmp_path):
    """A capture 10 minutes before the placeholder (11:50 PM Eastern the evening before) is not the game's close: the
    listing's kickoff is the verified one. It is refused, counted as missing and listed; with the genuine close also
    in the file, that one is used and the evening-before capture is set aside, wherever it sits."""
    s, v = [sched(1, 40, kick=PLACEHOLDER, start_time_tbd=True)], verified(tmp_path, (1, REAL_KICK))
    out = score_with_closes(tmp_path, [rb_signal(1)], s, [capture(1, EVENING_BEFORE, PLACEHOLDER, 44.5)],
                            "--list-excluded", *v)
    r = rb(out)
    assert "1 signals, 1 settled" in r and "0 of 1 bets have a primary close" in r
    assert f"captured close refused for 1 of these 1 bets: {REFUSED}; counted as missing (1)" in r
    line = next(ln for ln in r.splitlines() if REFUSED in ln and "2026-10-10T03:50:00Z" in ln)
    assert "2026-10-10 23:30:00+00:00" in line                       # the listing's kickoff: the verified one
    closes = [capture(1, REAL_KICK - 10 * MIN, REAL_KICK, 48.5), capture(1, EVENING_BEFORE, PLACEHOLDER, 44.5)]
    r = rb(score_with_closes(tmp_path / "both", [rb_signal(1)], s, closes, *v))
    assert "mean CLV +2.00" in r and "1 from the captured close" in r
    assert "captures set aside for 1 of these 1 bets: 1 outside the window for the listing" in r


@pytest.mark.parametrize("at", [REAL_KICK - MIN, REAL_KICK, REAL_KICK + 5 * MIN, REAL_KICK - 21 * MIN])
def test_a_verified_placeholder_game_refuses_an_in_play_or_late_capture(tmp_path, at):
    """Measured from the verified kickoff, the window is 2 to 20 minutes before it: a capture in the last 2 minutes, at
    kickoff or after it (in play), or 21 minutes before is refused."""
    out = score_with_closes(tmp_path, [rb_signal(1)], [sched(1, 40, kick=PLACEHOLDER, start_time_tbd=True)],
                            [capture(1, at, REAL_KICK, 48.5)], *verified(tmp_path, (1, REAL_KICK)))
    assert "0 of 1 bets have a primary close" in rb(out) and "captured close refused for 1 of these 1 bets" in rb(out)


def test_a_verified_placeholder_game_never_takes_another_listings_capture(tmp_path):
    """Signalled for Oct 10 (7:30 PM Eastern), postponed to Oct 17; the schedule shows the Oct 17 placeholder, verified
    at 7:30 PM Eastern Oct 17. The Oct 10 listing is void (moved more than 24 hours). The Oct 17 listing never takes
    the close captured for Oct 10; it takes its own, and sets the Oct 10 one aside."""
    ph17, kick17 = pd.Timestamp("2026-10-17T04:00:00Z"), pd.Timestamp("2026-10-17T23:30:00Z")
    rows = [rb_signal(1), rb_signal(1, kick=kick17, entry=52.5)]
    s, v = [sched(1, 40, kick=ph17, start_time_tbd=True)], verified(tmp_path, (1, kick17))
    old = capture(1, REAL_KICK - 10 * MIN, REAL_KICK, 40.0)
    r = rb(score_with_closes(tmp_path, rows, s, [old], *v))
    assert "2 signals, 1 settled, 0 pending, 1 void" in r and "0 of 1 bets have a primary close" in r
    assert "captured close refused for 1 of these 1 bets" in r and "+12.50" not in r
    r = rb(score_with_closes(tmp_path / "own", rows, s, [capture(1, kick17 - 10 * MIN, kick17, 50.5), old], *v))
    assert "mean CLV +2.00" in r and "captures set aside for 1 of these 1 bets: 1 outside" in r


def test_a_verified_kickoff_bounds_the_rows_and_the_window_not_a_later_kickoff_a_row_carries(tmp_path):
    """The entry row carries 8:00 PM Eastern on the game's date, the verified kickoff; the last row, logged at 5:00 AM
    Eastern the next day, carries 4:00 PM that day (the row is wrong). That row is after the verified kickoff, so it
    doesn't count, and a capture before the 4:00 PM kickoff it carries is refused; the one before 8:00 PM is used."""
    entry_kick, late_kick = PLACEHOLDER + pd.Timedelta(hours=20), PLACEHOLDER + pd.Timedelta(hours=40)
    rows = [rb_signal(1, kick=entry_kick),
            row(1, late_kick, PLACEHOLDER + pd.Timedelta(hours=29), mkt_total=50.5, rule_ht="below_threshold")]
    s, v = [sched(1, 40, kick=PLACEHOLDER, start_time_tbd=True)], verified(tmp_path, (1, entry_kick))
    closes = [capture(1, entry_kick - 10 * MIN, entry_kick, 49.0), capture(1, late_kick - 10 * MIN, late_kick, 44.5)]
    out = score_with_closes(tmp_path, rows, s, closes, "--list-excluded", *v)
    assert "excluded, logged at or after kickoff: 1" in out
    r = rb(out)
    assert "1 signals, 1 settled, 0 pending, 0 void" in r and "mean CLV +1.50" in r and "1 from the captured close" in r
    line = next(ln for ln in r.splitlines() if ASIDE in ln and "2026-10-11T19:50:00Z" in ln)
    assert "2026-10-11 00:00:00+00:00" in line                                         # the verified kickoff


def test_rule_ht_on_a_verified_placeholder_game_takes_its_game_day_capture_as_the_secondary_close(tmp_path):
    """Rule HT's secondary measure (amendment 2) reads the same window: the capture 10 minutes before the verified
    kickoff is used beside the bet; one from the evening before is set aside."""
    rows = [untimed(1, "2026-10-08T14:30Z", mkt_total=70.5, rule_ht="time_tbd"),
            row(1, REAL_KICK, "2026-10-10T22:30Z", mkt_total=64.5, mkt_under=-105)]
    closes = [capture(1, REAL_KICK - 10 * MIN, REAL_KICK, 63.5), capture(1, EVENING_BEFORE, PLACEHOLDER, 70.0)]
    out = ht(score_with_closes(tmp_path, rows, [sched(1, 67, kick=PLACEHOLDER, start_time_tbd=True)], closes,
                               *verified(tmp_path, (1, REAL_KICK))))
    assert "1 signals at the last quote before kickoff, 1 settled" in out
    assert "mean CLV vs the captured close +1.00" in out
    assert "captures set aside for 1 of these 1 bets: 1 outside the window" in out


def test_the_json_document_carries_the_amendment_7_counts_as_printed(tmp_path):
    """--json: Rule HT's quotes logged with no kickoff time set, the listings that are not a bet, and the ledger games
    whose schedule kickoff is the placeholder, each as the report prints them; untimed listings are not among the
    bets."""
    import json
    rows = [untimed(7, "2026-10-08T14:30Z"), untimed(7, "2026-10-09T02:30Z"),
            row(8, REAL_KICK, "2026-10-10T22:30Z", mkt_total=64.5)]
    s, v = [sched(7, 50, kick=PLACEHOLDER, start_time_tbd=True), sched(8, 50)], verified(tmp_path, (7, REAL_KICK))
    doc = json.loads(score(tmp_path, rows, s, "--json", *v))
    text = doc["text"]
    assert text == score(tmp_path, rows, s, *v)
    assert f"{PH_LINE}, completed, kickoff verified: 1 (7)" in text
    assert doc["placeholder_games"] == {"completed_verified": ["7"], "quarantined": [], "not_yet_played": []}
    assert doc["quarantine"]["games"] == [] and doc["quarantine"]["rows"] == 0
    t = next(t for t in doc["tests"] if t["id"] == "RULE_HT")
    assert "no kickoff time set (amendment 7): 2 quotes" in ht(text) and f"{LAST_UNTIMED}: 1 (7)" in ht(text)
    assert t["no_kickoff_time"] == {"quotes": 2, "not_a_bet": ["7"]} and t["final_withheld"] == []
    assert [b["game_id"] for b in t["bets"]] == ["8"] and t["counts"]["signals"] == 1
    assert "no_kickoff_time" not in next(t for t in doc["tests"] if t["id"] == "RULE_B")


def test_the_json_document_carries_the_quarantine_as_printed(tmp_path):
    """--json: the quarantined games, their rows, the reason (counted among the excluded rows) and the FINALs withheld,
    for each rule and on each interim decision, as the report prints them."""
    import json
    rows = [row(1, REAL_KICK, "2026-10-09T14:30Z", rule_b="SIGNAL", mkt_total=50.5, rule_ht="below_threshold"),
            row(1, REAL_KICK, "2026-10-10T19:00Z", mkt_total=48.5, rule_ht="below_threshold"),
            row(2, REAL_KICK, "2026-10-10T22:30Z", mkt_total=64.5)]
    s = [sched(1, 40, kick=PLACEHOLDER, start_time_tbd=True), sched(2, 50)]
    doc = json.loads(score(tmp_path, rows, s, "--json"))
    assert doc["text"] == score(tmp_path, rows, s)
    assert doc["quarantine"] == {"reason": QUARANTINED, "games": ["1"], "rows": 2,
                                 "final_withheld": {"Rule B": ["1"], "Rule HT": []},
                                 "not_yet_completed": {"Rule B": [], "Rule HT": []}}
    assert doc["excluded"][QUARANTINED] == 2
    assert doc["placeholder_games"] == {"completed_verified": [], "quarantined": ["1"], "not_yet_played": []}
    b, h = (next(t for t in doc["tests"] if t["id"] == i) for i in ("RULE_B", "RULE_HT"))
    assert b["final_withheld"] == ["1"] and h["final_withheld"] == []
    assert b["counts"]["signals"] == 0 and h["counts"]["signals"] == 1
    assert [d["status"] for d in b["decisions"]] == ["interim"] and b["decisions"][0]["final_withheld"] == ["1"]
    assert WITHHELD in b["decisions"][0]["text"] and "final_withheld" not in h["decisions"][0]


@pytest.mark.parametrize("schedule_kick", ["2026-11-14T05:00:00Z", "2026-11-14T20:00:00Z"])
def test_an_eastern_standard_time_placeholder(tmp_path, schedule_kick):
    """After the clock change the placeholder is 05:00 UTC (00:00 EST). Rows logged at it are not Rule HT quotes,
    whether the schedule the scorer reads shows the placeholder (verified at the real time) or the real time (3:00 PM
    Eastern)."""
    est, real = pd.Timestamp("2026-11-14T05:00:00Z"), pd.Timestamp("2026-11-14T20:00:00Z")
    rows = [row(3, est, "2026-11-12T15:30Z", wx_src="time_tbd", rule_b="time_tbd", mkt_total=70.5),
            row(3, est, "2026-11-14T03:30Z", wx_src="time_tbd", rule_b="time_tbd", mkt_total=70.5),  # evening before
            row(3, real, "2026-11-14T15:30Z", mkt_total=64.5)]                                       # game day, timed
    out = score(tmp_path, rows, [sched(3, 67, kick=schedule_kick)], *verified(tmp_path, (3, real)))
    assert "logged at or after kickoff" not in out and QUARANTINED not in out
    assert "1 signals at the last quote before kickoff, 1 settled, 0 pending, 0 void" in ht(out)
    assert "record 0-1-0" in ht(out)
    assert "no kickoff time set (amendment 7): 2 quotes" in ht(out)
    assert "and would have signalled: 0" in ht(out)


def test_a_real_kickoff_more_than_24_hours_after_the_placeholder(tmp_path):
    """A known limit (section 3). Hawai'i-New Mexico, Oct 17, 2026, has no time set; its placeholder is 04:00 UTC Oct
    17. Set at 7:00 PM Hawaii time, the kickoff is 05:00 UTC Oct 18, 25 hours later, so the rows logged with the time
    are a second listing (amendment 4, section 10). That listing is graded as usual; the listing logged before the
    time was set is counted as a listing whose last quote was logged with no time set, although the game was
    logged with one: the count is spurious here."""
    ph, hi = pd.Timestamp("2026-10-17T04:00:00Z"), pd.Timestamp("2026-10-18T05:00:00Z")
    rows = [row(9, ph, "2026-10-15T14:30Z", wx_src="time_tbd", rule_b="time_tbd", rule_ht="time_tbd"),
            row(9, ph, "2026-10-16T02:30Z", wx_src="time_tbd", rule_b="time_tbd", rule_ht="time_tbd"),
            row(9, hi, "2026-10-17T14:30Z", mkt_total=67.5),
            row(9, hi, "2026-10-18T02:30Z", mkt_total=66.5)]             # 7:30 PM Pacific, the last run before
    out = ht(score(tmp_path, rows, [sched(9, 60, kick=hi)]))
    assert "1 signals at the last quote before kickoff, 1 settled, 0 pending, 0 void" in out
    assert "record 1-0-0" in out
    assert "no kickoff time set (amendment 7): 2 quotes" in out
    assert "and would have signalled: 1 (9)" in out                  # the spurious count
    # Set at 00:00 Eastern instead, the real kickoff reads as the placeholder: never eligible, and counted. The
    # schedule's 00:00 Eastern is a placeholder to the scorer, so the game is graded only once the hub verifies it.
    rows = [row(9, ph, "2026-10-15T14:30Z", wx_src="time_tbd", rule_b="time_tbd", rule_ht="time_tbd"),
            row(9, ph, "2026-10-16T02:30Z", mkt_total=66.5, rule_ht="time_tbd")]
    out = ht(score(tmp_path / "midnight", rows, [sched(9, 60, kick=ph)], *verified(tmp_path / "midnight", (9, ph))))
    assert "0 signals" in out and "and would have signalled: 1 (9)" in out


# ------------------------------------------------------------------ the last quote is taken over every quote
@pytest.mark.parametrize("case,rows,schedule", [
    # A: a timed signal, then the time is unset again (the placeholder, the flag's weather source), below the line
    ("A", [row(1, REAL_KICK, "2026-10-08T14:30Z", mkt_total=66.5),
           row(1, PLACEHOLDER, "2026-10-09T14:30Z", mkt_total=60.5, rule_ht="below_threshold", wx_src="time_tbd")],
     sched(1, 67)),
    # A2: the same, with the placeholder in the schedule the scorer reads (verified at the real kickoff)
    ("A2", [row(1, REAL_KICK, "2026-10-08T14:30Z", mkt_total=66.5),
            row(1, PLACEHOLDER, "2026-10-09T14:30Z", mkt_total=60.5, rule_ht="below_threshold", wx_src="time_tbd")],
     sched(1, 67, kick=PLACEHOLDER, start_time_tbd=True)),
    # B: the flag turns on at a real time (Oregon-UCLA style), and the flagged row is below the line
    ("B", [row(1, REAL_KICK, "2026-10-08T14:30Z", mkt_total=66.5),
           row(1, REAL_KICK, "2026-10-10T20:30Z", mkt_total=61.5, rule_ht="below_threshold", wx_src="time_tbd")],
     sched(1, 60, start_time_tbd=True)),
    # C: the flag turns on at a real time, and the flagged row would still signal, at a lower total
    ("C", [row(1, REAL_KICK, "2026-10-08T14:30Z", mkt_total=68.5),
           row(1, REAL_KICK, "2026-10-10T20:30Z", mkt_total=64.5, rule_ht="time_tbd", wx_src="time_tbd")],
     sched(1, 66, start_time_tbd=True)),
])
def test_a_timed_signal_followed_by_an_untimed_quote_is_not_a_bet(tmp_path, case, rows, schedule):
    """The third review's cases. The listing's last quote was logged with no kickoff time set, so it is not a bet; main
    gives no bet on these rows either. Before this fix the untimed quote was skipped and the earlier timed signal
    became the entry: a bet no alert was sent for, graded at a stale, higher total. The eligibility reading can cost a
    bet, never add one."""
    extra = verified(tmp_path, (1, REAL_KICK)) if case == "A2" else []
    out = ht(score(tmp_path, rows, [schedule], "--list-excluded", *extra))
    assert "0 signals at the last quote before kickoff" in out
    assert "no kickoff time set (amendment 7): 1 quotes" in out
    assert f"not a bet, {LAST_UNTIMED}: {1 if case == 'C' else 0}" in out
    if case == "C":
        assert f"Rule HT, not a bet: {LAST_UNTIMED}" in out


def test_the_reviews_gap_an_unverified_placeholder_game_is_never_graded_at_an_in_play_price(tmp_path):
    """The review's P1 (first case). The rows say 7:30 PM Eastern; the game really kicked off at noon Eastern; the
    completed schedule shows only the placeholder. A row logged at 3:00 PM Eastern is in play. The rows' own kickoff
    is not evidence of when the game began, so the game is quarantined: the 58.5 is never Rule HT's entry, nothing of
    the game is graded for either rule, and both FINALs are withheld. Once the hub records the real kickoff (noon
    Eastern) from the box score, the registered rules apply: the in-play row is logged after kickoff and refused, and
    the entry is the genuine pre-kickoff quote, 66.5."""
    rows = [row(1, REAL_KICK, "2026-10-09T14:30Z", mkt_total=66.5, rule_b="SIGNAL"),
            row(1, REAL_KICK, "2026-10-10T19:00Z", mkt_total=58.5, mkt_under=-105)]
    s = [sched(1, 60, kick=PLACEHOLDER, start_time_tbd=True)]
    out = score(tmp_path, rows, s, "--list-excluded")
    assert f"excluded, {QUARANTINED}: 2" in out and "ledger rows: 2; in the test: 0" in out
    assert "0 signals at the last quote before kickoff, 0 settled" in ht(out) and "  record " not in ht(out)
    assert "0 signals, 0 settled" in rb(out)
    assert WITHHELD in rb(out) and WITHHELD in ht(out) and "FINAL:" not in out
    listed = out.split(f"  {QUARANTINED}: the rows, for the hub to verify each game's kickoff")[1]
    assert "row_kickoff" in listed and "2026-10-10 19:00:00+00:00" in listed and "58.5" not in listed  # no price
    out = score(tmp_path / "v", rows, s, *verified(tmp_path / "v", (1, "2026-10-10T16:00:00Z")))
    assert "excluded, logged at or after kickoff: 1" in out and QUARANTINED not in out
    assert "1 signals at the last quote before kickoff, 1 settled" in ht(out) and "record 1-0-0" in ht(out)  # 66.5
    assert "1 signals, 1 settled" in rb(out) and "1 with none" in rb(out)        # the in-play quote is no close


def test_a_nearer_untimed_listing_still_voids_a_farther_timed_one(tmp_path):
    """The review's case D. Listing X was logged with a time (Thu 7:00 PM Eastern) and signalled; listing Y, 29 hours
    later, was logged at the placeholder (a row from before amendment 7, as SIGNAL) and would have signalled. The game
    was played Fri at noon Eastern: 17 hours from X, 12 from Y. Main grades Y and voids X as another listing. Y is not
    a bet under amendment 7, but it is still the listing nearest the actual kickoff, so X stays void: amendment 7 never
    turns a void listing into a bet."""
    x, y = pd.Timestamp("2026-10-08T23:00:00Z"), pd.Timestamp("2026-10-10T04:00:00Z")
    rows = [row(1, x, "2026-10-07T14:30Z", mkt_total=68.5),
            row(1, y, "2026-10-09T02:00Z", mkt_total=66.5, wx_src="time_tbd")]
    out = ht(score(tmp_path, rows, [sched(1, 60, kick="2026-10-09T16:00:00Z")]))
    assert "1 signals at the last quote before kickoff, 0 settled, 0 pending, 1 void" in out
    assert "void, another listing of this game is the one graded: 1 (1)" in out
    assert f"not a bet, {LAST_UNTIMED}: 1 (1)" in out


def test_a_listing_logged_after_the_placeholder_counts_once_the_kickoff_is_verified(tmp_path):
    """The review's case listing_shift. The schedule shows only the placeholder. Listing X kicks off 14 hours before it
    (Fri 10:00 AM Eastern), its Rule B signal logged the day before; listing Y kicks off 11 hours after it (Sat 11:00
    AM Eastern), its only row logged after the placeholder. Main reads the placeholder as the kickoff: it drops Y's row
    as logged after kickoff and grades X (CLV +1.00). Unverified, the game is quarantined: neither is graded. With the
    real kickoff verified (Sat 11:00 AM), the registered rules grade Y (CLV +2.00) and void X, which kicked off more
    than 24 hours from the game: one graded bet per game, on the listing that matches the kickoff."""
    x, y = PLACEHOLDER - pd.Timedelta(hours=14), PLACEHOLDER + pd.Timedelta(hours=11)
    rows = [row(1, x, "2026-10-08T12:00Z", rule_b="SIGNAL", mkt_total=50.5, rule_ht="below_threshold"),
            row(1, y, "2026-10-10T06:00Z", rule_b="SIGNAL", mkt_total=47.5, rule_ht="below_threshold")]
    closes = [capture(1, x - 10 * MIN, x, 49.5), capture(1, y - 10 * MIN, y, 45.5)]
    s = [sched(1, 40, kick=PLACEHOLDER, start_time_tbd=True)]
    out = score_with_closes(tmp_path, rows, s, closes)
    assert f"excluded, {QUARANTINED}: 2" in out and "0 signals" in rb(out) and WITHHELD in rb(out)
    out = score_with_closes(tmp_path / "v", rows, s, closes, *verified(tmp_path / "v", (1, y)))
    assert "logged at or after kickoff" not in out and "ledger rows: 2; in the test: 2" in out
    r = rb(out)
    assert "2 signals, 1 settled, 0 pending, 1 void" in r
    assert "void, the game kicked off more than 24 hours from the kickoff on its entry row: 1 (1)" in r
    assert "record 1-0-0" in r and "mean CLV +2.00" in r and "Sat 10-10 11:00" in r and "Fri 10-09 10:00" not in r


def test_the_reviews_gap_never_takes_an_in_play_capture(tmp_path):
    """The review's P1 (second case, gap_close_inplay). The rows say 7:30 PM Eastern; the game really kicked off at noon
    Eastern; the schedule shows only the placeholder. A capture 10 minutes before the rows' kickoff was taken in play
    (41.5). Unverified, the game is quarantined: no capture is used, and --list-excluded prints when each capture was
    taken and for which kickoff, with no price, for the hub to check. Verified at noon, the true close (48.5, captured
    for noon) is the primary close, and the in-play capture is set aside."""
    true_kick = pd.Timestamp("2026-10-10T16:00:00Z")
    closes = [capture(1, true_kick - 10 * MIN, true_kick, 48.5), capture(1, REAL_KICK - 10 * MIN, REAL_KICK, 41.5)]
    s = [sched(1, 40, kick=PLACEHOLDER, start_time_tbd=True)]
    out = score_with_closes(tmp_path, [rb_signal(1)], s, closes, "--list-excluded")
    assert f"{PH_LINE}, completed, no verified kickoff (quarantined, not graded): 1 (1)" in out
    assert "0 signals" in rb(out) and "+9.00" not in out and "41.5" not in out and WITHHELD in rb(out)
    caps = out.split(f"  {QUARANTINED}: the captured closes of these games, 2:")[1].split("RULE_B:")[0]
    assert "captured_for" in caps and "2026-10-10T23:20:00Z" in caps and "2026-10-10T15:50:00Z" in caps
    out = score_with_closes(tmp_path / "v", [rb_signal(1)], s, closes, "--list-excluded",
                            *verified(tmp_path / "v", (1, true_kick)))
    r = rb(out)
    assert "1 from the captured close" in r and "mean CLV +2.00" in r and "+9.00" not in r      # 50.5 against 48.5
    assert "captures set aside for 1 of these 1 bets: 1 outside the window for the listing" in r
    line = next(ln for ln in r.splitlines() if ASIDE in ln)
    assert "2026-10-10T23:20:00Z" in line and "2026-10-10 16:00:00+00:00" in line          # in play, vs the listing's


# ------------------------------------------------------------------ the FINAL gate
def test_no_final_decision_is_recorded_while_a_game_is_quarantined(tmp_path):
    """After the test's end, with every bet settled: Rule B's only signal is on a quarantined game, so its FINAL is
    withheld and nothing is written to the record, while Rule HT, which the quarantined game has no signal for, is
    decided and recorded as usual. Once the hub records the game's kickoff, Rule B is decided and recorded."""
    rows = [row(1, REAL_KICK, "2026-10-09T14:30Z", rule_b="SIGNAL", mkt_total=50.5, rule_ht="below_threshold"),
            row(2, REAL_KICK, "2026-10-10T22:30Z", mkt_total=64.5),
            row(3, REAL_KICK, "2026-10-09T14:30Z", rule_b="SIGNAL", mkt_total=50.5, rule_ht="below_threshold")]
    s = [sched(1, 40, kick=PLACEHOLDER, start_time_tbd=True), sched(2, 50), sched(3, 40)]
    folder = tmp_path / "t"
    out = score(folder, rows, s, "--now", "2028-03-01", "--test-record")
    assert "decision (Rule B): INTERIM read, decides nothing. The test has ended. The decision waits for kickoff " \
           "verification." in rb(out)
    assert WITHHELD in rb(out) and "FINAL" not in rb(out).replace("FINAL withheld", "")
    assert "decision (Rule HT: once, after the 2027 season), FINAL: " in ht(out) and "FINAL withheld" not in ht(out)
    rec = pd.read_csv(folder / "decisions.csv")
    assert rec.decision_id.tolist() == ["CFB_RULE_HT"]
    out = score(folder, rows, s, "--now", "2028-03-01", "--test-record", *verified(folder, (1, REAL_KICK)))
    assert "FINAL withheld" not in out and "decision (Rule B), FINAL: INCONCLUSIVE" in rb(out)
    assert pd.read_csv(folder / "decisions.csv").decision_id.tolist() == ["CFB_RULE_HT", "CFB_RULE_B"]


def test_a_quarantine_holds_only_the_rules_it_has_a_signal_for(tmp_path):
    """A quarantined game with a Rule HT signal and no Rule B signal holds Rule HT's FINAL only. Rule B's interim read,
    and the other games' grades, are as they would be without it."""
    rows = [row(1, REAL_KICK, "2026-10-09T14:30Z", mkt_total=66.5),
            row(2, REAL_KICK, "2026-10-09T14:30Z", rule_b="SIGNAL", mkt_total=50.5, rule_ht="below_threshold"),
            row(2, REAL_KICK, "2026-10-10T20:30Z", mkt_total=49.5, rule_ht="below_threshold"),
            row(3, REAL_KICK, "2026-10-10T22:30Z", mkt_total=64.5)]
    s = [sched(1, 60, kick=PLACEHOLDER), sched(2, 40), sched(3, 50)]
    out = score(tmp_path, rows, s)
    base = score(tmp_path / "base", rows[1:], s[1:])
    assert rb(out) == rb(base) and "FINAL withheld" not in rb(out)
    assert "1 signals at the last quote before kickoff, 1 settled" in ht(out) and "record 1-0-0" in ht(out)
    line = (f"    {WITHHELD}: the schedule shows the placeholder and no verified kickoff is recorded in "
            "kickoff_verifications.csv (amendment 7)\n")
    assert line in ht(out) and ht(out).replace(line, "") == ht(base)


def test_the_live_record_waits_for_the_committed_verification(tmp_path):
    """On the live ledger, on the real clock (the project in a git repository, as the live checkout is): a Rule B
    decision whose horizon has passed, with one of its 41 signals on a game the schedule still shows at the placeholder.
    Nothing is recorded while the game is quarantined; a run that reads another verification file records nothing
    either; nor does a run while the project's kickoff_verifications.csv holds the kickoff as an edit not yet
    committed (the game is graded, but the record waits). Once that edit is committed, the decision is recorded."""
    import test_readings as R
    rows, s = R.rb_signals(41)
    s[0] = s[0] | {"start_date": "2026-10-03T04:00:00.000Z"}                  # game 1, Oct 3: the placeholder
    proj = R.live_project(tmp_path, "cfb-weather", rows, s, "2026-12-20T16:00")
    fwd, scorer = proj / "data" / "forward", proj / "scripts" / "score_forward.py"
    out = R.on_clock(tmp_path, "2026-12-20T17:00", scorer).stdout
    assert f"{PH_LINE}, completed, no verified kickoff (quarantined, not graded): 1 (1)" in out
    assert "INTERIM read" in rb(out) and WITHHELD in rb(out) and "FINAL:" not in out
    assert not (fwd / "decisions.csv").exists()
    other = verified(tmp_path / "elsewhere", (1, "2026-10-03T19:00:00Z"))
    out = R.on_clock(tmp_path, "2026-12-20T17:05", scorer, *other).stdout
    assert "FINAL: KEEP" in rb(out) and not (fwd / "decisions.csv").exists()
    assert ("not recorded: the live record is written only from the committed kickoff_verifications.csv.") in rb(out)
    shutil.copy(tmp_path / "elsewhere" / "v.csv", proj / "kickoff_verifications.csv")       # edited, not committed
    out = R.on_clock(tmp_path, "2026-12-20T17:08", scorer).stdout
    assert f"{PH_LINE}, completed, kickoff verified: 1 (1)" in out and "FINAL: KEEP" in rb(out)
    assert ("not recorded: kickoff_verifications.csv differs from its committed version (git show "
            "HEAD:./kickoff_verifications.csv), and the live record is written only from the committed file: commit "
            "the change, or restore the file, and run the scorer again.") in rb(out)
    assert not (fwd / "decisions.csv").exists()
    R.commit_verifications(proj, (tmp_path / "elsewhere" / "v.csv").read_bytes())
    out = R.on_clock(tmp_path, "2026-12-20T17:10", scorer).stdout
    assert f"{PH_LINE}, completed, kickoff verified: 1 (1)" in out
    assert "FINAL: KEEP" in rb(out) and "recorded in decisions.csv on 2026-12-20T17:10:00Z" in rb(out)
    assert pd.read_csv(fwd / "decisions.csv").decision_id.tolist() == ["CFB_RULE_B"]


# ------------------------------------------------------------------ a game not yet completed holds the FINAL too
OPEN_HELD = ("FINAL withheld: 1 game not yet completed, with the placeholder in the schedule and a signal, awaits its "
             "result (1) (amendment 7)")


def test_a_game_not_yet_completed_holds_rule_hts_final(tmp_path):
    """The second review's case (h1). After the title game, Rule HT's other bets are settled; game 1's schedule still
    shows the placeholder and the game isn't marked completed, and its only rows, logged on game day with the real time,
    are logged after the placeholder. They don't count yet, so nothing is pending, but once the game is completed and
    verified they do: the FINAL waits, and nothing is recorded. When the game is completed and verified, the FINAL is
    recorded on both bets. With no score 30 days after its kickoff (void under amendment 4), it no longer holds."""
    ph, rk = pd.Timestamp("2028-01-10T05:00:00Z"), pd.Timestamp("2028-01-11T01:00:00Z")   # 00:00 EST; 8:00 PM EST
    rows = [row(2, REAL_KICK, "2026-10-10T22:30Z", mkt_total=64.5),
            row(1, rk, "2028-01-10T18:00Z", mkt_total=70.5), row(1, rk, "2028-01-10T23:00Z", mkt_total=70.5)]
    waiting = [sched(2, 50), sched(1, 60, kick=ph) | dict(home_points=None, away_points=None, completed=False)]
    f = tmp_path / "t"
    out = score(f, rows, waiting, "--now", "2028-02-02", "--test-record")
    assert f"{PH_LINE}, not yet played: 1 (1)" in out and "excluded, logged at or after kickoff: 2" in out
    assert "1 signals at the last quote before kickoff, 1 settled, 0 pending" in ht(out)
    assert ("The title game has passed; the decision waits for the games named below (amendment 7)." in ht(out)
            and OPEN_HELD in ht(out) and "FINAL:" not in ht(out))
    assert not (f / "decisions.csv").exists()
    out = score(f, rows, [sched(2, 50), sched(1, 60, kick=ph)], "--now", "2028-02-03", "--test-record",
                *verified(f, (1, rk)))
    assert "FINAL: STAY ON PAPER" in ht(out) and "on 2 bets: record 2-0-0" in ht(out)
    assert pd.read_csv(f / "decisions.csv").decision_id.tolist() == ["CFB_RULE_HT"]
    out = score(tmp_path / "late", rows, waiting, "--now", "2028-02-11", "--test-record")       # 31 days on
    assert "FINAL withheld" not in out and "FINAL: STAY ON PAPER" in ht(out) and "on 1 bets" in ht(out)


def test_a_game_not_yet_completed_holds_rule_bs_final_only_if_it_could_enter_it(tmp_path):
    """The second review's case (h1b): 41 settled Rule B signals and the regular season over; game 99, on the last
    Saturday, still shows the placeholder, isn't marked completed, and its signal and later quote were logged on game
    day, after the placeholder. The FINAL waits; once the game is completed and verified, both rows count and the
    decision is made on 42 signals. A game whose placeholder and rows are after the horizon doesn't hold it."""
    import test_readings as R
    rows, s = R.rb_signals(41)
    ph, rk = pd.Timestamp("2026-12-12T05:00:00Z"), pd.Timestamp("2026-12-12T20:00:00Z")
    extra = [R.row(99, rk, "2026-12-12T14:00Z", rule_b="SIGNAL", mkt_total=50.5),
             R.row(99, rk, "2026-12-12T18:00Z", mkt_total=44.5)]
    waiting = s + [R.sched(99, 20, 20, kick=ph) | dict(completed=False, home_points=None, away_points=None)]
    f = tmp_path / "t"
    out = score(f, rows + extra, waiting, "--now", "2026-12-13T12:00", "--test-record")
    assert "41 signals, 41 settled, 0 pending" in rb(out) and "FINAL:" not in rb(out)
    assert OPEN_HELD.replace("(1)", "(99)") in rb(out) and not (f / "decisions.csv").exists()
    out = score(f, rows + extra, s + [R.sched(99, 20, 20, kick=ph)], "--now", "2026-12-14T12:00", "--test-record",
                *verified(f, (99, rk)))
    assert "FINAL: KEEP, on the 42 signals" in rb(out)
    assert pd.read_csv(f / "decisions.csv").decision_id.tolist() == ["CFB_RULE_B"]
    after = [R.row(99, rk + pd.Timedelta(days=7), "2026-12-19T14:00Z", rule_b="SIGNAL", mkt_total=50.5),
             R.row(99, rk + pd.Timedelta(days=7), "2026-12-19T18:00Z", mkt_total=44.5)]
    waiting = s + [R.sched(99, 20, 20, kick=ph + pd.Timedelta(days=7)) | dict(completed=False, home_points=None,
                                                                              away_points=None)]
    out = score(tmp_path / "after", rows + after, waiting, "--now", "2026-12-20T12:00", "--test-record")
    assert "FINAL withheld" not in rb(out) and "FINAL: KEEP, on the 41 signals" in rb(out)


def test_the_json_document_carries_the_games_not_yet_completed_that_hold_a_final(tmp_path):
    import json
    ph, rk = pd.Timestamp("2028-01-10T05:00:00Z"), pd.Timestamp("2028-01-11T01:00:00Z")
    rows = [row(2, REAL_KICK, "2026-10-10T22:30Z", mkt_total=64.5), row(1, rk, "2028-01-10T18:00Z", mkt_total=70.5)]
    waiting = [sched(2, 50), sched(1, 60, kick=ph) | dict(home_points=None, away_points=None, completed=False)]
    doc = json.loads(score(tmp_path, rows, waiting, "--now", "2028-02-02", "--json"))
    assert doc["quarantine"]["games"] == [] and doc["quarantine"]["not_yet_completed"] == {"Rule B": [],
                                                                                           "Rule HT": ["1"]}
    assert doc["quarantine"]["final_withheld"] == {"Rule B": [], "Rule HT": ["1"]}
    h = next(t for t in doc["tests"] if t["id"] == "RULE_HT")
    assert h["final_withheld"] == ["1"] and h["decisions"][0]["final_withheld"] == ["1"]
    assert OPEN_HELD in h["decisions"][0]["text"]
