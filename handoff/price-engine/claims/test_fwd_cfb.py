"""My own checks of B1-B5 for the CFB forward test (Rule B and Rule HT), on made-up ledgers only. The scorer is run
as a subprocess with --ledger on a scratch copy, --schedule on a scratch file and --now (a preview; --test-record
only where a record is the point). Nothing here reads the live ledger, a 2026 price or a 2026 result.

    ./pyw.sh cfb -m pytest -q -p no:cacheprovider mine/test_fwd_cfb.py
"""
import ast
import csv
import importlib.util
import io
import math
import os
import re
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from scipy import stats

W = Path(os.environ.get("PE_WORKTREE", "/Users/maxzipperman/code/value-finder/.claude/worktrees/wf_4496c14b-845-1"))
P = W / "cfb-weather"
SCORER = P / "scripts" / "score_forward.py"
sys.path.insert(0, str(P))
from cfbweather import board, fetch  # noqa: E402

spec = importlib.util.spec_from_file_location("cfb_helpers", P / "tests" / "test_readings.py")
h = importlib.util.module_from_spec(spec)
spec.loader.exec_module(h)          # only its row(), sched() and rb_signals() builders are used
row, sched, ts = h.row, h.sched, h.ts
T = pd.Timestamp


def score(folder, rows, schedule, now, *extra, closes=None):
    folder.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(folder / "ledger.csv", index=False)
    pd.DataFrame(schedule).to_csv(folder / "sched.csv", index=False)
    if closes is not None:
        pd.DataFrame(closes).to_csv(folder / "closes.csv", index=False)
    r = subprocess.run([sys.executable, str(SCORER), "--ledger", str(folder / "ledger.csv"), "--schedule",
                        str(folder / "sched.csv"), "--now", now, *extra], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-2000:]
    return r.stdout


def rb(out):
    return out.split("RULE_B:")[1].split("RULE_HT:")[0]


def ht(out):
    return out.split("RULE_HT:")[1].split("Variants under")[0]


def extract(path, names, env):
    """The scorer's own functions, compiled from its source (the script runs its whole scoring at import)."""
    tree = ast.parse(path.read_text())
    nodes = [n for n in tree.body if (isinstance(n, ast.FunctionDef) and n.name in names)
             or (isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id in names for t in n.targets))]
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), "exec"), env)
    return env


# ================================================================ B1 entries
def test_b1_rule_b_enters_at_the_first_signal_under_a_registered_version(tmp_path):
    k = "2026-10-10T19:00Z"
    rows = [row(1, k, "2026-10-07T15:00Z", rule_b="SIGNAL", mkt_total=60.0, rules_version="cfb-v0-unregistered"),
            row(1, k, "2026-10-08T15:00Z", rule_b="SIGNAL", mkt_total=55.0),
            row(1, k, "2026-10-09T15:00Z", rule_b="SIGNAL", mkt_total=50.0),
            row(1, k, "2026-10-10T16:00Z", mkt_total=52.0)]                   # a later quote: the primary close
    out = score(tmp_path, rows, [sched(1, 20, 20, kick=k)], "2026-10-20")
    assert "excluded, unregistered rules version: 1" in out
    part = rb(out)
    assert "1 signals, 1 settled" in part and "mean CLV +3.00" in part          # entry 55, close 52
    assert "cfb-v0-unregistered" not in board.REGISTERED_VERSIONS


def test_b1_before_kickoff_is_before_the_earlier_of_row_and_schedule(tmp_path):
    # the row says 19:00, the schedule says 18:00: a signal at 18:30 is after kickoff; one at exactly 18:00 too
    rows = [row(2, "2026-10-10T19:00Z", "2026-10-10T18:30Z", rule_b="SIGNAL"),
            row(3, "2026-10-10T19:00Z", "2026-10-10T18:00Z", rule_b="SIGNAL"),
            row(4, "2026-10-10T19:00Z", "2026-10-10T17:59Z", rule_b="SIGNAL")]
    out = score(tmp_path, rows, [sched(g, 20, 20, kick="2026-10-10T18:00Z") for g in (2, 3, 4)], "2026-10-20")
    assert "excluded, logged at or after kickoff: 2" in out and "1 signals" in rb(out)


def test_b1_rule_ht_enters_at_the_last_quote_before_kickoff(tmp_path):
    k = "2026-10-10T19:00Z"
    rows = [  # game 5: an early HT signal, then a later quote that is not one: no HT bet
            row(5, k, "2026-10-10T12:00Z", rule_ht="SIGNAL", mkt_total=66.0),
            row(5, k, "2026-10-10T18:00Z", mkt_total=60.0),
            # game 6: the last quote is a signal at -105: the bet is there, at that price
            row(6, k, "2026-10-10T12:00Z", mkt_total=60.0),
            row(6, k, "2026-10-10T18:00Z", rule_ht="SIGNAL", mkt_total=66.0, mkt_under=-105),
            # game 7: a later row whose under price is not a price is not a quote: the signal before it stands
            row(7, k, "2026-10-10T12:00Z", rule_ht="SIGNAL", mkt_total=66.0),
            row(7, k, "2026-10-10T18:00Z", mkt_total=60.0, mkt_under=-50),
            # game 8: a signal after kickoff never counts
            row(8, k, "2026-10-10T12:00Z", mkt_total=60.0),
            row(8, k, "2026-10-10T19:05Z", rule_ht="SIGNAL", mkt_total=66.0)]
    out = score(tmp_path, rows, [sched(g, 20, 20, kick=k) for g in (5, 6, 7, 8)], "2026-10-20")
    part = ht(out)
    assert "2 signals at the last quote before kickoff, 2 settled" in part
    ids = [int(ln.split()[0]) for ln in part.splitlines() if re.match(r"\s+\d+\s+x\s", ln)]
    assert sorted(ids) == [6, 7]
    assert re.search(r"\n\s+6 .* -105 ", part)


# ================================================================ B3 void and pending
def test_b3_void_and_pending_boundaries(tmp_path):
    k = "2026-10-10T19:00Z"
    rows = [row(g, k, "2026-10-08T15:00Z", rule_b="SIGNAL") for g in range(11, 17)]
    s = [sched(11, 20, 20, kick="2026-10-11T19:00Z"),                          # exactly 24 hours later: a bet
         sched(12, 20, 20, kick="2026-10-11T19:01Z"),                          # 24 hours 1 minute: void
         sched(13, np.nan, np.nan, completed=False, kick=k),                   # no score, 29 days on: pending
         sched(14, 20, 20, completed=False, kick=k),                           # a score, not completed: pending
         sched(15, 20, 20, kick=k), sched(16, 20, 20, kick=k)]
    out = rb(score(tmp_path, rows, s, "2026-11-08T18:00Z"))
    assert "6 signals, 3 settled, 2 pending, 1 void" in out
    assert "void, the game kicked off more than 24 hours from the kickoff on its entry row: 1 (12)" in out
    out = rb(score(tmp_path / "later", rows, s, "2026-11-09T19:00Z"))          # 30 days after kickoff: void
    assert "void, the schedule shows no result 30 days after that kickoff: 2 (13, 14)" in out


def test_b3_two_listings_one_graded(tmp_path):
    rows = [row(21, "2026-10-10T19:00Z", "2026-10-08T15:00Z", rule_b="SIGNAL"),
            row(21, "2026-10-31T19:00Z", "2026-10-29T15:00Z", rule_b="SIGNAL", mkt_total=60.0)]
    out = rb(score(tmp_path, rows, [sched(21, 20, 20, kick="2026-10-31T19:00Z")], "2026-11-05"))
    assert "2 signals, 1 settled, 0 pending, 1 void" in out and "another listing" not in out   # moved: void first
    # two listings 25 hours apart, both within 24 hours of the actual kickoff: the nearer is graded
    rows = [row(22, "2026-10-10T00:00Z", "2026-10-08T15:00Z", rule_b="SIGNAL"),
            row(22, "2026-10-11T01:00Z", "2026-10-08T16:00Z", rule_b="SIGNAL", mkt_total=60.0)]
    out = rb(score(tmp_path / "b", rows, [sched(22, 20, 20, kick="2026-10-10T06:00Z")], "2026-11-05"))
    assert "2 signals, 1 settled, 0 pending, 1 void" in out
    assert "void, another listing of this game is the one graded: 1 (22)" in out and "50.5" in out


# ================================================================ B4 the decision record
RECORD_COLS = ["decision_id", "rule", "horizon", "horizon_utc", "decided_utc", "n_bets", "verdict", "numbers",
               "ledger_rows", "ledger_rows_sha256"]


def _final(tmp_path):
    rows, s = h.rb_signals(41)
    out = score(tmp_path, rows, s, "2026-12-21", "--test-record")
    return rows, s, out


def test_b4_first_final_is_written_once_with_ten_columns(tmp_path):
    rows, s, out = _final(tmp_path)
    rec = tmp_path / "decisions.csv"
    assert "FINAL" in rb(out) and "recorded in decisions.csv" in out
    lines = list(csv.reader(io.StringIO(rec.read_text())))
    assert lines[0] == RECORD_COLS and len(lines) == 2 and len(lines[1]) == 10
    before = rec.read_bytes()
    changed = [dict(r, mkt_total=40.0) if r["rule_b"] == "SIGNAL" else r for r in rows]
    out2 = score(tmp_path, changed, s, "2026-12-22", "--test-record")
    assert rec.read_bytes() == before                                        # never rewritten
    assert "have changed since it was recorded" in out2 and "recorded decision still stands" in out2
    # a preview (no --test-record) records nothing
    rec.unlink()
    out3 = score(tmp_path, rows, s, "2026-12-21")
    assert not rec.exists() and "a run with --now is a preview" in out3


@pytest.mark.parametrize("damage", ["cut", "nine_fields", "no_header"])
def test_b4_a_damaged_record_stops_recording_not_scoring(tmp_path, damage):
    rows, s, _ = _final(tmp_path)
    rec = tmp_path / "decisions.csv"
    good = rec.read_bytes()
    header, first = good.decode().splitlines()[:2]
    nine = io.StringIO()
    csv.writer(nine, lineterminator="\n").writerow(next(csv.reader([first]))[:9])
    bad = {"cut": good[:-2], "nine_fields": (header + "\n" + nine.getvalue()).encode(),
           "no_header": (first + "\n").encode()}[damage]
    rec.write_bytes(bad)
    out = score(tmp_path, rows, s, "2026-12-22", "--test-record")
    assert rec.read_bytes() == bad                                            # untouched
    assert "unreadable" in out and "RULE_HT:" in out and "RULE_B:" in out    # scores still printed


def test_b4_the_append_is_under_a_file_lock():
    src = SCORER.read_text()
    fn = src.split("def write_down", 1)[1].split("\ndef ", 1)[0]
    assert "with record_lock():" in fn and "parse_record(DECISIONS.read_bytes())" in fn
    lock = src.split("def record_lock", 1)[1].split("\n\n\n", 1)[0]
    assert "fcntl.flock(fh, fcntl.LOCK_EX" in lock


# ================================================================ B5 the keep test's interval
def _indep(clv, day):
    """Written from amendment 5's words, not from the scorer."""
    clv, day = np.asarray(clv, float), np.asarray(day)
    n = len(clv)
    m = sum(clv) / n
    s = math.sqrt(sum((x - m) ** 2 for x in clv) / (n - 1))
    plain = stats.t.ppf(0.975, n - 1) * s / math.sqrt(n)
    days = sorted(set(day))
    G = len(days)
    sums = [sum(c - m for c, d in zip(clv, day) if d == g) for g in days]
    grouped = stats.t.ppf(0.975, G - 1) * math.sqrt(G / (G - 1) * sum(x * x for x in sums) / n ** 2)
    half = max(plain, grouped)
    return m, plain, grouped, m - half, m + half, G


def test_b5_the_real_interval_matches_the_registered_formula():
    fn = extract(SCORER, {"interval", "game_day"}, dict(np=np, pd=pd, stats=stats))
    rng = np.random.default_rng(5)
    for n, G in ((40, 5), (41, 13), (25, 2), (60, 20)):
        clv = rng.normal(0.4, 2.5, n) + np.repeat(rng.normal(0, 1.5, G), -(-n // G))[:n]   # day effects
        day = np.repeat(np.arange(G), -(-n // G))[:n]
        got = fn["interval"](clv, day)
        m, plain, grouped, lo, hi, g = _indep(clv, day)
        assert got["G"] == g and got["n"] == n
        for k, v in (("m", m), ("plain", plain), ("grouped", grouped), ("lo", lo), ("hi", hi)):
            assert got[k] == pytest.approx(v, rel=1e-12, abs=1e-12), (n, G, k)
    one = fn["interval"]([1.0, 2.0, 3.0], [0, 0, 0])
    assert math.isnan(one["lo"]) and one["G"] == 1
    assert math.isnan(fn["interval"]([1.0], [0])["lo"])
    # a missing CLV is left out of n and of the days
    got = fn["interval"]([1.0, np.nan, 3.0, 2.0], [0, 1, 1, 2])
    assert got["n"] == 3 and got["G"] == 3


def test_b5_game_day_is_the_eastern_date_of_the_actual_kickoff():
    fn = extract(SCORER, {"game_day"}, dict(np=np, pd=pd))
    k = pd.to_datetime(["2026-11-08T05:30Z", "2026-11-01T06:30Z", "2027-01-01T04:30Z"], utc=True)  # 9:30 PM PST Sat
    bets = pd.DataFrame(dict(sched_kick=[k[0], pd.NaT, k[2]], start_utc=[T("2026-11-07T20:00Z"), k[1], k[2]]))
    assert list(fn["game_day"](bets)) == ["2026-11-08", "2026-11-01", "2026-12-31"]


def test_b5_end_to_end_the_printed_interval_is_the_registered_one(tmp_path):
    rows, s, clv, days = [], [], [], []
    rng = np.random.default_rng(11)
    for i in range(41):
        k = T("2026-10-03T19:00Z") + pd.Timedelta(days=7 * (i % 10)) + pd.Timedelta(hours=i % 3)
        c = float(np.round(rng.normal(0.5, 2.0), 1))
        rows += [row(100 + i, k, k - pd.Timedelta(days=2), rule_b="SIGNAL", mkt_total=50.0 + c),
                 row(100 + i, k, k - pd.Timedelta(hours=3), mkt_total=50.0)]
        s.append(sched(100 + i, 20, 20, kick=k))
        clv.append(c)
        days.append(k.tz_convert("America/New_York").strftime("%Y-%m-%d"))
    out = rb(score(tmp_path, rows, s, "2026-12-21"))
    m, plain, grouped, lo, hi, G = _indep(clv, days)
    want = f"95% CI {lo:+.2f} to {hi:+.2f}"
    assert want in out, (want, out[:600])
    assert f"over {G} game days" in out


# ================================================================ B2 which feed event gives the captured close
def _one_event():
    env = dict(pd=pd, fetch=fetch)
    return extract(P / "scripts" / "capture_close.py", {"one_event", "NEAR", "BOOK_NAME"}, env)["one_event"]


def _feed(event, commence, src="pinnacle", total=50.0, under=-110, over=-110, home="H", away="A"):
    return dict(event=event, home_team=home, away_team=away, commence_utc=commence, line_src=src, mkt_total=total,
                mkt_under=under, mkt_over=over)


def test_b2_capture_event_choice():
    one = _one_event()
    due = pd.DataFrame([dict(game_id=1, start_utc=T("2026-10-10T19:00Z"), home_team="H", away_team="A")])
    pick = lambda feed: one(due, pd.DataFrame(feed))[0].event.tolist()          # noqa: E731
    assert pick([_feed(0, "2026-10-11T01:01Z")]) == []                            # 6 h 1 min: not the game
    assert pick([_feed(0, "2026-10-11T00:59Z")]) == [0]
    assert pick([_feed(0, "2026-10-10T19:00Z", src="draftkings"), _feed(1, "2026-10-10T22:00Z")]) == [1]
    assert pick([_feed(0, "2026-10-10T19:00Z", src=""), _feed(1, "2026-10-10T21:00Z", src="draftkings")]) == [1]
    assert pick([_feed(0, "2026-10-17T19:00Z"), _feed(1, "2026-10-10T19:30Z")]) == [1]            # a rematch
    assert pick([_feed(3, "2026-10-10T19:00Z"), _feed(2, "2026-10-10T19:00Z")]) == [2]            # same quote
    assert pick([_feed(0, "2026-10-10T19:00Z"), _feed(1, "2026-10-10T19:00Z", total=51.0)]) == []  # differ
    assert pick([_feed(0, None)]) == []
    assert fetch.RULE_BOOKS == ("pinnacle", "draftkings")
