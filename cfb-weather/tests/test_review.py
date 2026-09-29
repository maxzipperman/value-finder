"""The review of the audit fixes (pull request 50) found places where the new code still fell short of
amendment 3. One test per finding: the last-run check on the Mac's own clock, the clock change, the
decision horizons by date, games that were never played, the best line without a rule-book quote, and a
run that fails after the board."""
import runpy
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cfbweather import board, config, fetch, market, notify, runlog  # noqa: E402
from cfbweather.market import ev_under, p_under_at, pricing_cohort, valid_odds  # noqa: E402

RESID = pricing_cohort(board.PRICING_COHORT_SHA256)
PT = "America/Los_Angeles"


# ------------------------------------------------------------------ the last scheduled run
def test_last_run_check_works_on_the_macs_own_clock():
    """The alert job calls it without a zone. That path raised, so the first Rule HT signal would have
    stopped every CFB alert."""
    now = pd.Timestamp.now(tz="UTC")
    assert board.is_last_run_before(now + pd.Timedelta(minutes=5), now) is True       # no run in 5 minutes
    assert board.is_last_run_before(now + pd.Timedelta(hours=30), now) is False
    assert board.is_last_run_before(now - pd.Timedelta(minutes=5), now) is False
    assert board.local_zone() is not None


def test_run_times_are_wall_clock_times_across_the_clock_change():
    """Clocks go back on Nov 1, 2026. The next run after 7:30 PM on Oct 31 is 7:30 AM Pacific Standard."""
    nxt = board.next_scheduled_run(pd.Timestamp("2026-10-31 19:30", tz=PT))
    assert nxt == pd.Timestamp("2026-11-01 07:30", tz=PT) and nxt.tz_convert("UTC").hour == 15
    nxt = board.next_scheduled_run(pd.Timestamp("2026-11-01 08:00", tz=PT))
    assert nxt == pd.Timestamp("2026-11-01 11:30", tz=PT) and nxt.tz_convert("UTC").hour == 19
    assert board.next_scheduled_run(pd.Timestamp("2027-03-13 19:30", tz=PT)) == pd.Timestamp("2027-03-14 07:30", tz=PT)
    assert board.next_scheduled_run(pd.Timestamp("2026-10-10 12:00")) == pd.Timestamp("2026-10-10 15:30")   # naive


# ------------------------------------------------------------------ the scorer's decisions
def signals(n, first="2026-10-03", every_days=2, first_id=1, rule="rule_b", total=50.5, close=None, under=-110):
    rows, sched = [], []
    for i in range(n):
        kick = pd.Timestamp(first, tz="UTC") + pd.Timedelta(days=every_days * i, hours=19)
        base = dict(rules_version="cfb-v3-2026-09-28", game_id=first_id + i, kick_et="x", away_team="A",
                    home_team="B", venue="V", lead_days=2, wx_src="forecast", wx_wind=18, line_src="pinnacle",
                    mkt_total=total, mkt_under=under, mkt_over=-110, ev_under=0.06, ht_threshold=62.6175,
                    rule_b="SIGNAL" if rule == "rule_b" else "no_trigger",
                    rule_ht="SIGNAL" if rule == "rule_ht" else "below_threshold",
                    start_utc=kick.strftime("%Y-%m-%dT%H:%M:%SZ"))
        rows.append(dict(base, snapshot_utc=(kick - pd.Timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%SZ")))
        if close is not None:       # a later quote before kickoff: the primary close
            rows.append(dict(base, mkt_total=close, rule_b="no_trigger", rule_ht=base["rule_ht"],
                             snapshot_utc=(kick - pd.Timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M:%SZ")))
        sched.append(dict(game_id=first_id + i, home_points=20, away_points=20, completed=True))
    return rows, sched


def score(tmp_path, rows, sched, now, *extra):
    pd.DataFrame(rows).to_csv(tmp_path / "ledger.csv", index=False)
    pd.DataFrame(sched).to_csv(tmp_path / "sched.csv", index=False)
    return subprocess.run([sys.executable, str(ROOT / "scripts" / "score_forward.py"), "--ledger",
                           str(tmp_path / "ledger.csv"), "--schedule", str(tmp_path / "sched.csv"), "--now", now,
                           *extra], capture_output=True, text=True, check=True).stdout


def rule_b(out):
    return out.split("RULE_B:")[1].split("RULE_HT:")[0]


def test_rule_b_is_final_after_forty_signals_and_the_regular_season(tmp_path):
    rows, sched = signals(40, every_days=1, close=49.5)                  # the 40th kicks off Nov 11, 2026
    out = rule_b(score(tmp_path, rows, sched, "2026-11-20"))
    assert "INTERIM read, decides nothing" in out and "FINAL" not in out  # the regular season isn't over
    out = rule_b(score(tmp_path, rows, sched, "2026-12-20"))
    assert "FINAL: KEEP, on the 40 signals that kicked off by 2026-12-12" in out and "n=40" in out


def test_a_cancelled_game_cannot_hold_the_decision_open(tmp_path):
    """The real schedules hold unscored rows years later (App State v Liberty, 2024). The old test for
    "season complete" asked for every row to have a score, so no decision could ever be final."""
    rows, sched = signals(41, every_days=1, close=49.5)
    sched[5].update(home_points=np.nan, away_points=np.nan, completed=False)     # never played
    out = rule_b(score(tmp_path, rows, sched, "2026-12-20"))
    assert "41 signals, 40 settled" in out and "FINAL: KEEP, on the 40 signals" in out


def test_a_final_rule_b_decision_does_not_move_when_later_signals_arrive(tmp_path):
    rows, sched = signals(40, every_days=1, close=49.5)
    first = rule_b(score(tmp_path, rows, sched, "2026-12-20"))
    more, more_sched = signals(5, first="2027-09-04", first_id=100, close=55.5)  # five bad ones the next season
    later = rule_b(score(tmp_path, rows + more, sched + more_sched, "2027-10-01"))
    pick = lambda out: next(ln for ln in out.splitlines() if "decision (" in ln)  # noqa: E731
    assert "FINAL: KEEP" in first and pick(first) == pick(later)


def test_the_fortieth_signal_sets_the_horizon_when_it_comes_late(tmp_path):
    rows, sched = signals(40, every_days=9, close=49.5)                  # the 40th kicks off in Sep 2027
    out = rule_b(score(tmp_path, rows, sched, "2027-06-01"))
    assert "INTERIM read, decides nothing" in out
    out = rule_b(score(tmp_path, rows, sched, "2027-10-01"))
    assert "FINAL: KEEP, on the 40 signals that kicked off by 2027-09-19" in out


def test_a_score_on_a_game_that_was_not_completed_is_not_graded(tmp_path):
    rows, sched = signals(2, first="2026-10-10", rule="rule_ht", total=65.5)
    sched[1].update(home_points=0, away_points=0, completed=False)       # the feed's 0-0 for a game never played
    out = score(tmp_path, rows, sched, "2026-11-01")
    assert "not marked completed (not graded): 1" in out
    assert "RULE_HT: 2 signals at the last quote before kickoff, 1 settled" in out


def test_rule_ht_is_final_only_after_the_title_game_and_drops_on_roi(tmp_path):
    wins, sw = signals(10, first="2026-10-10", rule="rule_ht", total=65.5, under=105)
    losses, sl = signals(10, first="2027-10-09", first_id=100, rule="rule_ht", total=65.5, under=-115)
    for g in sl:
        g.update(home_points=40, away_points=40)
    out = score(tmp_path, wins + losses, sw + sl, "2027-12-20").split("RULE_HT:")[1]
    assert "record 10-10-0" in out and "ROI +2.5% per bet placed" in out
    assert "INTERIM read, decides nothing" in out and "FINAL" not in out
    assert not any(w in out.split("decision (")[1].splitlines()[0] for w in ("PROMOTE", "DROP", "STAY ON PAPER"))
    out = score(tmp_path, wins + losses, sw + sl, "2028-02-02").split("RULE_HT:")[1]
    assert "FINAL: STAY ON PAPER" in out                                 # it made money: not a drop
    for g in sw[:2]:
        g.update(home_points=40, away_points=40)                         # 8-12 now: it lost money
    out = score(tmp_path, wins + losses, sw + sl, "2028-02-02").split("RULE_HT:")[1]
    assert "record 8-12-0" in out and "FINAL: DROP" in out


def test_a_row_with_no_kickoff_time_is_excluded_under_its_own_reason(tmp_path):
    rows, sched = signals(2)
    rows[1]["start_utc"] = ""
    out = score(tmp_path, rows, sched, "2026-11-01", "--list-excluded")
    assert "excluded, no kickoff time in the row: 1" in out and "in the test: 1" in out


# ------------------------------------------------------------------ the odds feed
NAMES = {"Troy Trojans": "Troy", "Southern Miss Golden Eagles": "Southern Miss"}


def book(key, point, under):
    outs = [dict(name="Over", price=-110, point=point), dict(name="Under", price=under, point=point)]
    return dict(key=key, markets=[dict(key="totals", last_update="u", outcomes=outs)])


def event(books):
    return dict(id="e1", home_team="Troy Trojans", away_team="Southern Miss Golden Eagles",
                commence_time="2026-10-07T00:00:00Z", bookmakers=books)


def test_best_line_is_logged_when_no_rule_book_quotes():
    r = fetch.parse_odds_api([event([book("fanduel", 56.5, -108), book("betmgm", 57.0, -112)])], NAMES, "s").iloc[0]
    assert pd.isna(r.mkt_total) and pd.isna(r.mkt_under) and r.line_src == ""
    assert (r.best_line, r.best_line_under, r.best_line_book) == (57.0, -112, "betmgm")
    up = board.price(pd.DataFrame([r]), RESID)
    assert up.ev_under.isna().all() and up.ev_best_line.isna().all()      # no reference, so nothing is priced
    status = board.rule_b_status(SimpleNamespace(wx_src="forecast", wx_wind=18.0, lead_days=2, mkt_total=r.mkt_total,
                                                 mkt_under=r.mkt_under, ev_under=np.nan))
    assert status == "no_price"


def test_a_number_that_is_not_a_price_is_not_a_quote():
    r = fetch.parse_odds_api([event([book("pinnacle", 55.5, 0), book("draftkings", 56.0, -112)])], NAMES, "s").iloc[0]
    assert (r.line_src, r.mkt_total, r.mkt_under) == ("draftkings", 56.0, -112)
    for odds in (0, -50, 99, None):
        assert not valid_odds(odds) and np.isnan(ev_under(55.5, odds, 55.5, RESID)).all()
        game = SimpleNamespace(mkt_total=65.5, mkt_under=odds, ht_threshold=62.6)
        assert board.rule_ht_status(game) == "no_price"


def test_a_higher_line_is_never_worth_less_on_the_quarter_point_grid():
    for ref in (45.5, 52.0, 61.5, 70.0):
        lines = np.arange(ref - 20, ref + 20.01, 0.25)
        win, push = p_under_at(lines, np.full(len(lines), ref), RESID)
        assert (np.diff(win) >= -1e-12).all() and (np.diff(1 - win - push) <= 1e-12).all()


def test_the_live_path_refuses_a_cohort_that_was_not_registered(tmp_path, monkeypatch):
    import json
    js = json.loads((config.PROC / "pricing_cohort.json").read_text())
    js["residuals"] = js["residuals"][:-1]
    (tmp_path / "pricing_cohort.json").write_text(json.dumps(js))
    monkeypatch.setattr(market, "PROC", tmp_path)
    with pytest.raises(ValueError, match="not the registered cohort"):
        pricing_cohort(board.PRICING_COHORT_SHA256)


# ------------------------------------------------------------------ records
def test_widening_the_ledger_leaves_old_rows_exactly_as_written(tmp_path):
    path = tmp_path / "ledger.csv"
    old = ("snapshot_utc,game_id,wx_precip,legacy\n2026-09-28T17:44:00Z,401,0.08700000000000002,x\n"
           "2026-09-28T21:30:00Z,402,,\n")
    path.write_text(old)
    snap = pd.DataFrame(dict(snapshot_utc=["2026-09-29T14:30:00Z"], rules_version=["cfb-v3-2026-09-28"],
                             game_id=[403], wx_precip=[0.1], best_line=[np.nan]))
    board.widen_ledger(path, snap)
    new = pd.read_csv(path, dtype=str, keep_default_na=False)
    assert list(new.columns) == ["snapshot_utc", "rules_version", "game_id", "wx_precip", "best_line", "legacy"]
    assert new.wx_precip.tolist() == ["0.08700000000000002", "", "0.1"] and new.game_id.tolist() == ["401", "402", "403"]
    assert (tmp_path / "ledger.before-cfb-v3-2026-09-28.csv").read_text() == old
    assert pd.read_csv(path).game_id.dtype == "int64"                    # the scorer still reads ids as numbers


# ------------------------------------------------------------------ the alert run, end to end and offline
def board_row(**kw):
    kick = pd.Timestamp.now(tz="UTC") + pd.Timedelta(minutes=30)          # no scheduled run comes before it
    base = dict(game_id=401, away_team="Southern Miss", home_team="Troy", kick_et="Tue 10-06 20:00", lead_days=2,
                start_utc=kick, wx_wind=18.0, wx_temp=55.0, line_src="pinnacle", mkt_total=63.5, mkt_under=-110.0,
                ev_under=0.08, rule_b="SIGNAL", rule_ht="SIGNAL", ht_threshold=62.6175, best_under=np.nan,
                best_under_book="", best_line=64.5, best_line_under=-110.0, best_line_book="fanduel",
                ev_best_line=0.11)
    return base | kw


def run_alerts(tmp_path, monkeypatch, up, save=None):
    sent = []
    monkeypatch.setattr(config, "ROOT", tmp_path)
    monkeypatch.setattr(board, "compute", up if callable(up) else (lambda **k: up))
    monkeypatch.setattr(board, "save", save or (lambda up: None))
    monkeypatch.setattr(notify, "send", lambda title, body: sent.append((title, body)) or True)
    monkeypatch.setattr(sys, "argv", ["alerts.py"])
    error = None
    try:
        runpy.run_path(str(ROOT / "scripts" / "alerts.py"), run_name="__main__")
    except BaseException as e:
        error = e
    runs = pd.read_csv(tmp_path / "data" / "forward" / "runs.csv", keep_default_na=False)
    return sent, runs, error


def test_a_rule_ht_signal_alerts_on_the_live_path(tmp_path, monkeypatch):
    """The blocker: with a Rule HT signal on the board the run crashed before any alert went out."""
    sent, runs, error = run_alerts(tmp_path, monkeypatch, pd.DataFrame([board_row()]))
    assert error is None and runs.status.tolist() == ["ok"] and runs.signals.tolist() == [2]
    assert [t.split(":")[0] for t, _ in sent] == ["CFB HIGH TOTAL UNDER 63.5 at -110 (paper)",
                                                   "CFB RULE B WIND UNDER 63.5 at -110"]
    assert "Best number: under 64.5 at -110 (fanduel)" in sent[1][1]
    sent, runs, _ = run_alerts(tmp_path, monkeypatch, pd.DataFrame([board_row()]))
    assert sent == [] and runs.status.tolist() == ["ok", "ok"]            # each alert goes out once


def failed(error):
    """A failed run exits with status 1 after printing the error with any key blanked (it no longer
    re-raises the original exception, whose text could hold a key)."""
    return isinstance(error, SystemExit) and error.code == 1


def test_one_games_alert_cannot_cost_the_others_theirs(tmp_path, monkeypatch):
    def broken(kick, now):
        raise TypeError("tz_convert() takes exactly 2 positional arguments (1 given)")
    monkeypatch.setattr(board, "is_last_run_before", broken)
    rows = [board_row(), board_row(game_id=402, home_team="Army", away_team="Navy", rule_ht="below_threshold")]
    sent, runs, error = run_alerts(tmp_path, monkeypatch, pd.DataFrame(rows))
    assert sent[0][0].startswith("CFB RULE B WIND UNDER 63.5 at -110: Navy @ Army")
    assert failed(error) and runs.status.tolist() == ["failed"] and runs.games.tolist() == [2]
    assert runs.error[0].startswith("while building the alerts: RuntimeError: 1 game(s) raised: Southern Miss @ Troy")
    assert sent[-1][0] == "CFB weather alerts: run failed"


def test_a_run_that_fails_while_saving_is_recorded_and_notified(tmp_path, monkeypatch):
    def full(up):
        raise OSError(28, "No space left on device")
    sent, runs, error = run_alerts(tmp_path, monkeypatch, pd.DataFrame([board_row()]), save=full)
    assert failed(error) and runs.status.tolist() == ["failed"]
    assert runs.error[0].startswith("while saving the ledger: OSError")
    assert [t for t, _ in sent] == ["CFB weather alerts: run failed"]


def test_a_failed_download_is_recorded_without_the_key(tmp_path, monkeypatch):
    def down(**k):
        raise ConnectionError("GET https://api.the-odds-api.com/v4/odds?apiKey=SECRETKEY123 failed")
    sent, runs, error = run_alerts(tmp_path, monkeypatch, down)
    assert failed(error) and runs.error[0].startswith("while building the board")
    assert "SECRETKEY123" not in runs.error[0] and "SECRETKEY123" not in sent[0][1]
    assert "SECRETKEY123" not in runlog.scrub("x?api_key=SECRETKEY123&y=1 token=SECRETKEY123")
