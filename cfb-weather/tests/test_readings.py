"""Amendment 4: the scorer readings that a review of pull request 50 found open. One test per reading,
built on the reviewers' own scenarios (their inputs are reused here). Each test fails on the scorer as
merged in pull request 50 and passes under amendment 4. Readings are numbered as amendment 4's sections."""
import fcntl
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cfbweather import board  # noqa: E402
from cfbweather.market import ev_under, p_under_at, pricing_cohort  # noqa: E402

COLUMNS = ["decision_id", "rule", "horizon", "horizon_utc", "decided_utc", "n_bets", "verdict", "numbers",
           "ledger_rows", "ledger_rows_sha256"]


def ts(x):
    t = pd.Timestamp(x)
    return t.tz_localize("UTC") if t.tzinfo is None else t.tz_convert("UTC")


def row(gid, kick, snap, **kw):
    base = dict(rules_version="cfb-v3-2026-09-28", game_id=gid, kick_et="x", away_team="A", home_team="B", venue="V",
                lead_days=2, wx_src="forecast", wx_wind=18, line_src="pinnacle", mkt_total=50.5, mkt_under=-110,
                mkt_over=-110, ev_under=0.06, ht_threshold=62.6175, rule_b="no_trigger", rule_ht="below_threshold",
                start_utc=ts(kick).strftime("%Y-%m-%dT%H:%M:%SZ"), snapshot_utc=ts(snap).strftime("%Y-%m-%dT%H:%M:%SZ"))
    return base | kw


def sched(gid, hp=20, ap=20, completed=True, kick=None):
    s = dict(game_id=gid, home_points=hp, away_points=ap, completed=completed)
    return s | ({"start_date": ts(kick).strftime("%Y-%m-%dT%H:%M:%S.000Z")} if kick else {})


def rb_signals(n, first="2026-10-03T19:00Z", every_days=1, first_id=1, entry=50.5, close=49.5, hp=20, ap=20):
    """`n` Rule B signals: an entry row 2 days out and, unless `close` is None, a later quote 3 hours out."""
    rows, s = [], []
    for i in range(n):
        k = ts(first) + pd.Timedelta(days=every_days * i)
        rows.append(row(first_id + i, k, k - pd.Timedelta(days=2), rule_b="SIGNAL", mkt_total=entry))
        if close is not None:
            rows.append(row(first_id + i, k, k - pd.Timedelta(hours=3), mkt_total=close))
        s.append(sched(first_id + i, hp, ap, kick=k))
    return rows, s


def ht_bet(gid, kick, under=-110, total=65.5, snap_h=4, **kw):
    return row(gid, kick, ts(kick) - pd.Timedelta(hours=snap_h), rule_ht="SIGNAL", mkt_total=total, mkt_under=under,
               **kw)


def score(folder, rows, schedule, now, *extra, closes=None):
    folder.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(folder / "ledger.csv", index=False)
    pd.DataFrame(schedule).to_csv(folder / "sched.csv", index=False)
    if closes is not None:
        pd.DataFrame(closes).to_csv(folder / "closes.csv", index=False)
    return subprocess.run([sys.executable, str(ROOT / "scripts" / "score_forward.py"), "--ledger",
                           str(folder / "ledger.csv"), "--schedule", str(folder / "sched.csv"), "--now", now, *extra],
                          capture_output=True, text=True, check=True).stdout


def rb(out):
    return out.split("RULE_B:")[1].split("RULE_HT:")[0]


def ht(out):
    return out.split("RULE_HT:")[1].split("Variants under")[0]


# ------------------------------------------------------------------ reading 1: void
def test_reading_1_a_postponed_or_never_scored_game_is_void(tmp_path):
    """The reviewers' postponed game: logged for Oct 10, played Oct 31 under the same id, graded 0-1."""
    rows = [row(77, "2026-10-10T19:30Z", "2026-10-08T14:30Z", rule_b="SIGNAL"),
            row(78, "2026-10-17T19:30Z", "2026-10-15T14:30Z", rule_b="SIGNAL"),
            row(79, "2026-10-24T19:30Z", "2026-10-22T14:30Z", rule_b="SIGNAL")]
    s = [sched(77, 35, 31, kick="2026-10-31T19:30Z"),                          # postponed three weeks
         sched(78, np.nan, np.nan, completed=False, kick="2026-10-17T19:30Z"),  # never scored
         sched(79, 20, 20, kick="2026-10-24T23:30Z")]                          # 4 hours late: still a bet
    out = rb(score(tmp_path, rows, s, "2026-11-20"))
    assert "3 signals, 1 settled, 0 pending, 2 void (not graded)" in out
    assert "void, the game kicked off more than 24 hours from the kickoff on its entry row: 1 (77)" in out
    assert "void, the schedule shows no result 30 days after that kickoff: 1 (78)" in out
    assert "record 1-0-0" in out


# ------------------------------------------------------------------ reading 2: pending
def test_reading_2_a_signal_still_waiting_for_its_score_holds_the_decision_open(tmp_path):
    """The reviewers' C2: a week after kickoff the old scorer treated an unscored game as never played."""
    rows, s = rb_signals(41)
    bad, sb = rb_signals(1, first="2026-12-12T19:00Z", first_id=900, close=56.5)
    waiting = [dict(x, home_points=np.nan, away_points=np.nan, completed=False) for x in sb]
    out = rb(score(tmp_path, rows + bad, s + waiting, "2026-12-21", "--test-record"))
    assert "42 signals, 41 settled, 1 pending, 0 void" in out
    assert "INTERIM read, decides nothing. Its horizon has passed: 2026-12-12" in out
    assert "The decision waits for 1 pending signal." in out
    assert "FINAL" not in out and not (tmp_path / "decisions.csv").exists()


# ------------------------------------------------------------------ reading 3: decided once, written down
def test_reading_3_the_first_final_decision_is_written_down_and_stands(tmp_path):
    """The reviewers' L1/L2: three Dec 12 signals whose scores land late turned KEEP into a drop."""
    g, sg = [], []
    for i in range(40):
        r, s1 = rb_signals(1, first=ts("2026-10-03T19:00Z") + pd.Timedelta(days=i), first_id=1 + i,
                           close=49.5 if i % 2 == 0 else 50.5)
        g, sg = g + r, sg + s1
    b, sb = rb_signals(3, first="2026-12-12T17:00Z", every_days=0, first_id=900, close=56.5)
    late = [dict(x, home_points=np.nan, away_points=np.nan, completed=False) for x in sb]
    first = rb(score(tmp_path, g + b, sg + late, "2027-01-12", "--test-record"))   # 31 days on: the three are void
    assert "43 signals, 40 settled, 0 pending, 3 void" in first
    assert "FINAL: KEEP, on the 40 signals that kicked off by 2026-12-12, the end of the regular season" in first

    rec = pd.read_csv(tmp_path / "decisions.csv", dtype=str)
    assert list(rec.columns) == COLUMNS and len(rec) == 1
    r = rec.iloc[0]
    assert (r.decision_id, r.rule, r.n_bets, r.verdict, r.decided_utc) == ("CFB_RULE_B", "Rule B", "40", "KEEP",
                                                                           "2027-01-12T00:00:00Z")
    assert r.horizon == "after 40 signals or the 2026 regular season, whichever is later"
    # the rows that entered it: each entry and each later quote used as its close (the review's minor 6)
    lines = (tmp_path / "ledger.csv").read_text().splitlines()
    entered = [lines[0]] + [ln for ln in lines[1:] if int(ln.split(",")[1]) <= 40]
    assert len(entered) == 81 and r.ledger_rows == " ".join(str(i) for i in range(1, 81))
    assert r.ledger_rows_sha256 == hashlib.sha256(("\n".join(entered) + "\n").encode()).hexdigest()

    later = rb(score(tmp_path, g + b, sg + sb, "2027-01-20", "--test-record"))   # the scores land
    assert "43 signals, 43 settled, 0 pending, 0 void" in later
    assert "FINAL: KEEP, on the 40 signals that kicked off by 2026-12-12" in later
    assert "recorded in decisions.csv on 2027-01-12T00:00:00Z" in later
    assert "a fresh computation on the same horizon now gives: NOT KEPT" in later and "n=43" in later
    assert "The recorded decision stands." in later and len(pd.read_csv(tmp_path / "decisions.csv")) == 1


def test_reading_3_fewer_than_forty_at_the_end_of_the_test_is_written_down_too(tmp_path):
    """The reviewers' D1/D2: 25 signals when the test ends."""
    rows, s = rb_signals(25, every_days=7)
    for now in ("2028-02-01", "2028-03-01"):                                 # decided, then reprinted
        out = rb(score(tmp_path, rows, s, now, "--test-record"))
        assert "decision (Rule B), FINAL: INCONCLUSIVE. The test ended with 25 settled signals, fewer than 40." in out
        assert "recorded in decisions.csv on 2028-02-01T00:00:00Z" in out and "fresh" not in out
    rec = pd.read_csv(tmp_path / "decisions.csv", dtype=str)
    assert len(rec) == 1 and (rec.rule[0], rec.n_bets[0], rec.verdict[0]) == ("Rule B", "25", "INCONCLUSIVE")


# ------------------------------------------------------------------ reading 4: horizons are dates
def test_reading_4_a_game_after_the_title_game_never_counts_and_dec_12_is_named(tmp_path):
    rows, s = rb_signals(40)
    feb = row(500, "2028-02-05T19:00Z", "2028-02-03T19:00Z", rule_b="SIGNAL")   # season label 2027, after Feb 1, 2028
    out = score(tmp_path, rows + [feb], s + [sched(500)], "2026-12-20")
    assert "excluded, after the 2027 season: 1" in out
    assert "40 signals, 40 settled" in rb(out)
    assert "FINAL: KEEP, on the 40 signals that kicked off by 2026-12-12, the end of the regular season" in out


# ------------------------------------------------------------------ reading 5: a quote, and Rule HT's entry
def test_reading_5_rule_ht_enters_at_the_last_quote_with_a_price(tmp_path):
    """The reviewers' H1: a last row with a total and no under price made game 3's bet vanish."""
    k = "2026-10-10T23:00Z"
    rows = [ht_bet(1, k, total=65.5, snap_h=11.5), row(1, k, ts(k) - pd.Timedelta(hours=3.5), mkt_total=62.5),
            ht_bet(2, k, total=66.5, snap_h=11.5), ht_bet(2, k, total=64.5, snap_h=3.5),
            ht_bet(3, k, total=65.5, snap_h=11.5),
            row(3, k, ts(k) - pd.Timedelta(hours=3.5), rule_ht="no_price", mkt_total=65.5, mkt_under=np.nan,
                line_src="espn"),
            ht_bet(4, k, total=65.0)]                                          # scores 65: a push
    out = ht(score(tmp_path, rows, [sched(1), sched(2), sched(3), sched(4, 30, 35)], "2026-10-20"))
    assert "3 signals at the last quote before kickoff, 3 settled" in out
    assert "record 2-0-1" in out and "units +1.82, ROI +60.6% per bet placed" in out
    assert "pushes are left out of the exact test and count in ROI" in out


# ------------------------------------------------------------------ reading 6: Rule B's primary close
def test_reading_6_rule_b_closes_at_a_later_quote_else_the_captured_close_else_none(tmp_path):
    """The reviewers' J (Pinnacle entry, DraftKings close), plus a signal whose only quote is its own row."""
    rows = [row(1, "2026-10-10T19:30Z", "2026-10-08T14:30Z", rule_b="SIGNAL", mkt_total=50.5),
            row(1, "2026-10-10T19:30Z", "2026-10-10T18:30Z", mkt_total=48.5, line_src="draftkings"),
            row(2, "2026-10-17T19:30Z", "2026-10-15T14:30Z", rule_b="SIGNAL", mkt_total=50.5),
            row(3, "2026-10-24T19:30Z", "2026-10-22T14:30Z", rule_b="SIGNAL", mkt_total=50.5),
            row(3, "2026-10-24T19:30Z", "2026-10-24T18:30Z", mkt_total=47.5, mkt_under=-50)]  # not a price
    closes = [dict(capture_utc="2026-10-17T19:20Z", game_id=2, start_utc="2026-10-17T19:30:00Z", home_team="B",
                   away_team="A", line_src="pinnacle", close_total=49.0, close_under=-110, close_over=-110)]
    out = rb(score(tmp_path, rows, [sched(1), sched(2), sched(3)], "2026-11-01", closes=closes))
    assert "mean CLV +1.75" in out and "2 of 3 bets have a primary close" in out
    assert ("primary close: 1 from a later logged quote, 1 from the captured close, 1 with none "
            "(counted, left out of the CLV)") in out
    assert "by price source: {'pinnacle': 3}" in out
    assert "close from: {'draftkings': 1, 'captured close (pinnacle)': 1, 'none': 1}" in out


# ------------------------------------------------------------------ reading 7: not kept
def test_reading_7_not_kept_means_no_money_goes_on_the_rule(tmp_path):
    rows, s = rb_signals(40, close=51.5)                                     # every signal lost a point
    out = rb(score(tmp_path, rows, s, "2026-12-20"))
    assert ("FINAL: NOT KEPT (no money goes on the rule; it stays on paper for 2027 only by a dated amendment "
            "before 2027 Week 0)") in out


# ------------------------------------------------------------------ reading 8: Rule HT by price source
def test_reading_8_rule_ht_is_reported_by_price_source(tmp_path):
    rows = [ht_bet(1, "2026-10-10T23:00Z"), ht_bet(2, "2026-10-17T23:00Z"),
            ht_bet(3, "2026-10-24T23:00Z", line_src="draftkings", under=-105)]
    out = ht(score(tmp_path, rows, [sched(1), sched(2, 40, 40), sched(3)], "2026-11-01"))
    assert "by price source: pinnacle 2 (1-1-0, units -0.09); draftkings 1 (1-0-0, units +0.95)" in out


# ------------------------------------------------------------------ reading 9: amendment 3's numbers
def test_reading_9_amendment_4_quotes_the_models_own_numbers():
    text = (ROOT / "PREREGISTRATION.md").read_text().split("## Amendment 4 ")[1].split("\n## ")[0]
    resid = pricing_cohort(board.PRICING_COHORT_SHA256)
    for line in (42.5, 43.0):                                               # where the value at x = 0 reaches zero
        win, push = (float(np.ravel(v)[0]) for v in p_under_at(line, line, resid))
        assert round(-100 * win / (1 - win - push)) == -130
    assert "about −130" in text

    def ev(below):
        return float(np.ravel(ev_under(42.5 - below, -115, 42.5, resid))[0])
    assert ev(1.5) < 0 < ev(1.0)
    assert "from 1.5 points below the reference" in text


# ================================================================== the review of this amendment (Sep 29)
def project(tmp_path, name="proj"):
    """A copy of the scorer and its package, so a test can use a data/forward/ folder of its own and never
    touch the real one."""
    proj = tmp_path / name
    shutil.copytree(ROOT / "cfbweather", proj / "cfbweather", ignore=shutil.ignore_patterns("__pycache__"))
    (proj / "scripts").mkdir()
    shutil.copy(ROOT / "scripts" / "score_forward.py", proj / "scripts" / "score_forward.py")
    (proj / "data" / "forward").mkdir(parents=True)
    return proj


def run(script, *args):
    return subprocess.run([sys.executable, str(script), *args], capture_output=True, text=True)


def test_reading_3_a_preview_with_now_records_nothing(tmp_path):
    """The review's C5: a what-if run with --now 2027-02-01, made while the Dec 12 scores were missing,
    recorded KEEP, and the real run on Dec 15 then had to accept it."""
    a, sa = rb_signals(40)
    b, sb = rb_signals(3, first="2026-12-12T17:00Z", every_days=0, first_id=900, close=56.5)
    late = [dict(x, home_points=np.nan, away_points=np.nan, completed=False) for x in sb]
    first = rb(score(tmp_path, a + b, sa + late, "2027-02-01"))
    assert "FINAL: KEEP" in first and "not recorded: a run with --now is a preview." in first
    assert not (tmp_path / "decisions.csv").exists()
    real = score(tmp_path, a + b, sa + sb, "2026-12-15")
    assert "FINAL: NOT KEPT" in rb(real) and "recorded in decisions.csv" not in real
    assert "Decision record: none written by this run: a run with --now is a preview." in real
    refused = run(ROOT / "scripts" / "score_forward.py", "--ledger", str(tmp_path / "ledger.csv"), "--schedule",
                  str(tmp_path / "sched.csv"), "--test-record")
    assert refused.returncode != 0 and "--test-record needs --now" in refused.stderr


def test_reading_3_only_the_live_ledger_writes_the_live_record(tmp_path):
    """The review's N6, for CFB: a --ledger run on the rewrite's backup copy, which sits in data/forward/,
    wrote the live decisions.csv."""
    a, sa = rb_signals(40)
    score(tmp_path / "t", a, sa, "2026-12-20", "--test-record")                       # a KEEP, recorded in a test
    proj = project(tmp_path)
    fwd, scorer = proj / "data" / "forward", proj / "scripts" / "score_forward.py"
    shutil.copy(tmp_path / "t" / "ledger.csv", fwd / "ledger.before-cfb-v3-2026-09-28.csv")
    shutil.copy(tmp_path / "t" / "ledger.csv", fwd / "ledger.csv")
    sched = str(tmp_path / "t" / "sched.csv")

    backup = run(scorer, "--ledger", str(fwd / "ledger.before-cfb-v3-2026-09-28.csv"), "--schedule", sched,
                 "--now", "2026-12-20").stdout
    assert "FINAL: KEEP" in backup and not (fwd / "decisions.csv").exists()
    assert ("not recorded: this ledger is kept in data/forward/ but is not the live ledger, so no record is read "
            "or written.") in backup
    shutil.copy(tmp_path / "t" / "decisions.csv", fwd / "decisions.csv")               # the live record, KEEP
    backup = run(scorer, "--ledger", str(fwd / "ledger.before-cfb-v3-2026-09-28.csv"), "--schedule", sched,
                 "--now", "2026-12-21").stdout
    assert "recorded in decisions.csv" not in backup                                  # it never reads it either
    live = run(scorer, "--schedule", sched, "--now", "2026-12-21").stdout             # the live ledger reads it
    assert "recorded in decisions.csv on 2026-12-20T00:00:00Z" in live
    for ledger in ("ledger.csv", "ledger.before-cfb-v3-2026-09-28.csv"):
        refused = run(scorer, "--ledger", str(fwd / ledger), "--schedule", sched, "--now", "2026-12-22",
                      "--test-record")
        assert refused.returncode != 0 and "a test ledger outside data/forward/" in refused.stderr
    assert len(pd.read_csv(fwd / "decisions.csv")) == 1

    # a copy of the scorer in another folder (a worker's worktree) reads the live record, and never writes it
    other = run(ROOT / "scripts" / "score_forward.py", "--ledger", str(fwd / "ledger.csv"), "--schedule", sched).stdout
    assert "recorded in decisions.csv on 2026-12-20T00:00:00Z" in other
    assert ("Decision record: none written by this run: this is another folder's live ledger, and only the scorer "
            "in that folder writes its record.") in other

    # on the real clock: from the default schedule only
    out = run(scorer, "--schedule", sched).stdout
    assert ("Decision record: none written by this run: the live record is written only from the default "
            "schedule (cfbfastR).") in out
    (proj / "data" / "raw" / "cfbfastr").mkdir(parents=True, exist_ok=True)
    current = f"schedules_{board.season_of(pd.Timestamp.now(tz='UTC'))}.parquet"          # the current season's file
    pd.DataFrame(sa).assign(start_time_tbd=False).to_parquet(proj / "data" / "raw" / "cfbfastr" / current)
    out = run(scorer).stdout
    assert "Decision record: the first final decision is written to data/forward/decisions.csv (the live record)." in out


def test_reading_3_a_stale_schedule_is_not_recorded(tmp_path):
    """The review: the daily check-in runs the scorer, and a schedule that stopped being refreshed would void
    games that were played and record a decision on the rest."""
    rows, s = rb_signals(40)
    score(tmp_path, rows, s, "2026-11-01")                                            # writes the files
    old = time.time() - 3 * 86400
    os.utime(tmp_path / "sched.csv", (old, old))
    args = ["--ledger", str(tmp_path / "ledger.csv"), "--schedule", str(tmp_path / "sched.csv"), "--now",
            "2026-12-20", "--test-record"]
    out = run(ROOT / "scripts" / "score_forward.py", *args).stdout
    assert "FINAL: KEEP" in out and "more than 2 days ago; refresh it" in out and "not recorded: the schedule" in out
    assert not (tmp_path / "decisions.csv").exists()
    os.utime(tmp_path / "sched.csv")                                                   # refreshed
    out = run(ROOT / "scripts" / "score_forward.py", *args).stdout
    assert "recorded in decisions.csv on 2026-12-20T00:00:00Z" in out and (tmp_path / "decisions.csv").exists()


def test_reading_3_a_recorded_decision_prints_when_nothing_is_settled(tmp_path):
    """The review's C6: with a schedule file that has no scores, the recorded decision wasn't printed."""
    a, sa = rb_signals(40)
    hts = [ht_bet(100 + i, ts("2026-10-10T23:00Z") + pd.Timedelta(days=7 * i)) for i in range(3)]
    sh = [sched(100 + i, kick=ts("2026-10-10T23:00Z") + pd.Timedelta(days=7 * i)) for i in range(3)]
    first = score(tmp_path, a + hts, sa + sh, "2028-02-02", "--test-record")
    assert "FINAL: KEEP" in rb(first) and "FINAL: STAY ON PAPER" in ht(first)
    blank = [dict(x, home_points=np.nan, away_points=np.nan, completed=False) for x in sa + sh]
    later = score(tmp_path, a + hts, blank, "2028-02-03", "--test-record")
    assert "40 signals, 0 settled, 0 pending, 40 void" in rb(later)
    for part, verdict in ((rb(later), "FINAL: KEEP"), (ht(later), "FINAL: STAY ON PAPER")):
        assert verdict in part and "recorded in decisions.csv on 2028-02-02T00:00:00Z" in part
        assert "a fresh computation on the same horizon now has no settled bets. The recorded decision stands." in part
    assert len(pd.read_csv(tmp_path / "decisions.csv")) == 2


def test_reading_1_a_result_that_lands_after_day_30_brings_the_bet_back(tmp_path):
    """The review: void at day 30, graded again when the score lands on day 31. Amendment 4 now says so."""
    rows = [row(9, "2026-10-10T19:30Z", "2026-10-08T14:30Z", rule_b="SIGNAL")]
    none = [sched(9, np.nan, np.nan, completed=False, kick="2026-10-10T19:30Z")]
    for now, s, expect in (("2026-11-08T19:30", none, "1 signals, 0 settled, 1 pending, 0 void"),
                           ("2026-11-09T19:30", none, "1 signals, 0 settled, 0 pending, 1 void"),
                           ("2026-11-10T19:30", [sched(9, kick="2026-10-10T19:30Z")],
                            "1 signals, 1 settled, 0 pending, 0 void")):
        assert expect in rb(score(tmp_path, rows, s, now))
    text = (ROOT / "PREREGISTRATION.md").read_text().split("## Amendment 4 ")[1].split("### 1.")[1].split("### 2.")[0]
    text = " ".join(text.split())
    assert "brings the bet back" in text and "the record stands" in text


def test_a_schedule_without_kickoff_times_says_the_moved_game_check_is_off(tmp_path):
    """The review: the reviewers' postponed game, rerun with a schedule that has no kickoff column, was
    graded as a loss without a word."""
    rows = [row(77, "2026-10-10T19:30Z", "2026-10-08T14:30Z", rule_b="SIGNAL")]
    out = score(tmp_path / "a", rows, [dict(game_id=77, home_points=35, away_points=31, completed=True)], "2026-11-02")
    assert "the schedule has no kickoff times (start_utc or start_date): the check for moved games is off" in out
    out = score(tmp_path / "b", rows, [sched(77, 35, 31, kick="2026-10-31T19:30Z")], "2026-11-02")
    assert "check for moved games is off" not in out and "1 void" in rb(out)


def test_amendment_4_says_which_earlier_text_it_replaces():
    """The review: section 6 makes the captured close primary when no later quote exists, which amendment 2
    said it could never be."""
    text = " ".join((ROOT / "PREREGISTRATION.md").read_text().split("## Amendment 4 ")[1].split("\n## ")[0].split())
    assert "Where this amendment and any earlier text differ, this one applies." in text
    assert "amendment 3 differ" not in text
    close = text.split("### 6.")[1].split("### 7.")[0]
    assert "This replaces amendment 2's \"What it can't change\" for Rule B's primary close" in close


# ================================================================== the final review of this amendment (Sep 29)
FAKE_CLOCK = """import os, runpy, sys
import pandas as pd
FAKE = pd.Timestamp(os.environ["FAKE_NOW"], tz="UTC")
pd.Timestamp.now = staticmethod(lambda tz=None: FAKE.tz_convert(tz) if tz is not None else FAKE.tz_localize(None))
script, sys.argv = sys.argv[1], sys.argv[1:]
runpy.run_path(script, run_name="__main__")
"""


def amendment4():
    return (ROOT / "PREREGISTRATION.md").read_text().split("## Amendment 4 ")[1].split("\n## ")[0]


def section(n):
    return " ".join(amendment4().split(f"### {n}.")[1].split("\n### ")[0].split())


def on_clock(tmp_path, now, script, *args):
    """Run a scorer on its real-clock path with the clock set to `now`: pd.Timestamp.now is patched, the scorer
    itself is unchanged, and no --now is passed."""
    runner = tmp_path / "fakeclock.py"
    runner.write_text(FAKE_CLOCK)
    return subprocess.run([sys.executable, str(runner), str(script), *args], capture_output=True, text=True,
                          env={**os.environ, "FAKE_NOW": now})


def touch(path, when):
    t = pd.Timestamp(when, tz="UTC").timestamp()
    os.utime(path, (t, t))


def git(repo, *args, stdin=None):
    who = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
    return subprocess.run(["git", "-C", str(repo), *args], input=stdin, capture_output=True, text=True, check=True,
                          env={**os.environ, **who}).stdout.strip()


def publish(repo, name, record):
    """A local stand-in for the nightly copy: `record` at <name>/decisions.csv on refs/remotes/origin/ledgers."""
    blob = git(repo, "hash-object", "-w", str(record))
    sub = git(repo, "mktree", stdin=f"100644 blob {blob}\tdecisions.csv\n")
    top = git(repo, "mktree", stdin=f"040000 tree {sub}\t{name}\n")
    git(repo, "update-ref", "refs/remotes/origin/ledgers", git(repo, "commit-tree", top, "-m", "Ledger snapshot"))


def season_file(proj, season, schedule, refreshed):
    path = proj / "data" / "raw" / "cfbfastr" / f"schedules_{season}.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(schedule).assign(start_time_tbd=False).to_parquet(path)
    touch(path, refreshed)
    return path


def live_project(tmp_path, name, rows, schedule, refreshed, season=2026):
    """A project laid out like the live checkout: its own ledger in data/forward, its cfbfastR schedule."""
    proj = project(tmp_path, name)
    pd.DataFrame(rows).to_csv(proj / "data" / "forward" / "ledger.csv", index=False)
    season_file(proj, season, schedule, refreshed)
    return proj


def test_reading_3_a_lost_record_is_restored_from_the_ledgers_branch_never_decided_again(tmp_path):
    """The final review's M1 (its 1e): a recorded KEEP was lost, and the next real run recorded NOT KEPT."""
    a, sa = rb_signals(40)
    repo = tmp_path / "repo"
    proj = live_project(repo, "cfb-weather", a, sa, "2026-12-20T16:00")
    git(repo, "init", "-q")
    fwd, scorer = proj / "data" / "forward", proj / "scripts" / "score_forward.py"
    first = on_clock(tmp_path, "2026-12-20T17:00", scorer).stdout
    assert "FINAL: KEEP" in first and "recorded in decisions.csv on 2026-12-20T17:00:00Z" in first
    publish(repo, "cfb-weather", fwd / "decisions.csv")                        # the nightly copy
    (fwd / "decisions.csv").unlink()                                           # the record is lost ...
    b, sb = rb_signals(3, first="2026-12-12T17:00Z", every_days=0, first_id=900, close=56.5)   # ... late Dec 12 rows
    pd.DataFrame(a + b).to_csv(fwd / "ledger.csv", index=False)
    season_file(proj, 2026, sa + sb, "2026-12-21T16:00")
    later = on_clock(tmp_path, "2026-12-21T17:00", scorer).stdout
    assert "restored 1 recorded decision from its copy on the ledgers branch" in later
    assert "FINAL: KEEP" in rb(later) and "recorded in decisions.csv on 2026-12-20T17:00:00Z" in rb(later)
    assert "a fresh computation on the same horizon now gives: NOT KEPT" in rb(later)
    assert len(pd.read_csv(fwd / "decisions.csv")) == 1
    (fwd / "decisions.csv").unlink()                                           # neither the file nor the copy
    git(repo, "update-ref", "-d", "refs/remotes/origin/ledgers")
    anew = on_clock(tmp_path, "2026-12-21T18:00", scorer).stdout
    assert "FINAL: NOT KEPT" in rb(anew) and "recorded in decisions.csv on 2026-12-21T18:00:00Z" in rb(anew)
    assert ("The record is copied to the ledgers branch every night. A lost record is restored from that copy; it is "
            "never decided again.") in section(3)


def test_reading_11_before_kickoff_is_before_the_earlier_of_the_rows_kickoff_and_the_schedules(tmp_path):
    """The final review's M2: a game moved 7.5 hours earlier, before cfbfastR showed it; rows logged 2.5 hours
    after the real kickoff were graded (Rule B's close, Rule HT's entry)."""
    k_row, k_sched = "2026-10-10T23:30Z", "2026-10-10T16:00Z"
    rows = [row(5, k_row, "2026-10-08T23:30Z", rule_b="SIGNAL", mkt_total=50.5),
            row(5, k_row, "2026-10-10T18:30Z", mkt_total=44.5),                   # in play
            ht_bet(6, k_row, total=65.5, snap_h=11.5),                           # 12:00Z, before the real kickoff
            ht_bet(6, k_row, total=58.5, snap_h=5)]                              # 18:30Z, in play
    out = score(tmp_path, rows, [sched(5, kick=k_sched), sched(6, 31, 31, kick=k_sched)], "2026-10-20")
    assert "excluded, logged at or after kickoff: 2" in out
    assert "0 of 1 bets have a primary close" in rb(out)
    assert "record 1-0-0" in ht(out)                                              # under 65.5, not under 58.5
    assert "before the earlier of the kickoff on the row" in section(11)


def test_reading_3_a_scorer_whose_data_forward_is_a_link_is_not_live(tmp_path):
    """The final review's m1, for CFB: a copy whose data/forward was a link to the live folder wrote its record."""
    a, sa = rb_signals(40)
    live = project(tmp_path, "live")
    pd.DataFrame(a).to_csv(live / "data" / "forward" / "ledger.csv", index=False)
    worker = live_project(tmp_path, "worker", a, sa, "2026-12-20T16:00")
    shutil.rmtree(worker / "data" / "forward")
    (worker / "data" / "forward").symlink_to(live / "data" / "forward")
    out = on_clock(tmp_path, "2026-12-20T17:00", worker / "scripts" / "score_forward.py").stdout
    assert "FINAL: KEEP" in out and not (live / "data" / "forward" / "decisions.csv").exists()
    assert "not recorded: this scorer's data/forward folder is a link to a folder outside its own project" in out
    assert "with links resolved, is inside its own project folder" in section(3)


def test_reading_3_two_runs_at_once_write_one_record(tmp_path):
    """The final review's m2: run B holds the record while run A reaches it; A must read it again and add nothing."""
    a_rows, sa = rb_signals(40)
    score(tmp_path / "b", a_rows, sa, "2026-12-20", "--test-record")                    # run B's record
    a = tmp_path / "a"
    a.mkdir()
    pd.DataFrame(a_rows).to_csv(a / "ledger.csv", index=False)
    pd.DataFrame(sa).to_csv(a / "sched.csv", index=False)
    b_lines = (tmp_path / "b" / "decisions.csv").read_text().splitlines()
    with open(a / ".decisions.lock", "a") as held:
        fcntl.flock(held, fcntl.LOCK_EX)
        run_a = subprocess.Popen([sys.executable, str(ROOT / "scripts" / "score_forward.py"), "--ledger",
                                  str(a / "ledger.csv"), "--schedule", str(a / "sched.csv"), "--now", "2026-12-21",
                                  "--test-record"], stdout=subprocess.PIPE, text=True)
        seen = ""
        for line in run_a.stdout:
            seen += line
            if "waiting for another run" in line:
                break
        if (a / "decisions.csv").exists():
            with open(a / "decisions.csv", "a") as fh:
                fh.write(b_lines[1] + "\n")
        else:
            (a / "decisions.csv").write_text("\n".join(b_lines) + "\n")
        fcntl.flock(held, fcntl.LOCK_UN)
    seen += run_a.stdout.read()
    run_a.wait()
    assert "waiting for another run to finish with the decision record" in seen
    assert "not recorded: this decision was already recorded on 2026-12-20T00:00:00Z (KEEP)" in seen
    assert len(pd.read_csv(a / "decisions.csv")) == 1


def test_reading_3_a_damaged_record_stops_recording_not_the_scores(tmp_path):
    """The final review's m3: a damaged decisions.csv crashed the whole scorer."""
    a_rows, sa = rb_signals(40)
    score(tmp_path / "ok", a_rows, sa, "2026-12-20", "--test-record")
    head, first = (tmp_path / "ok" / "decisions.csv").read_text().splitlines()[:2]
    damaged = {"half": f'{head}\n{first[:40]}"unclosed\n', "short": head + "\n" + ",".join(first.split(",")[:5]) + "\n",
               "noheader": first + "\n", "empty": ""}
    for name, content in damaged.items():
        d = tmp_path / name
        d.mkdir()
        pd.DataFrame(a_rows).to_csv(d / "ledger.csv", index=False)
        pd.DataFrame(sa).to_csv(d / "sched.csv", index=False)
        (d / "decisions.csv").write_text(content)
        r = run(ROOT / "scripts" / "score_forward.py", "--ledger", str(d / "ledger.csv"), "--schedule",
                str(d / "sched.csv"), "--now", "2026-12-21", "--test-record")
        assert r.returncode == 0, (name, r.stderr[-400:])
        assert "Decision record: decisions.csv is unreadable" in r.stdout, name
        assert "Nothing will be recorded until it is repaired or restored from the ledgers branch" in r.stdout
        assert "40 signals, 40 settled" in r.stdout and "FINAL: KEEP" in r.stdout
        if name == "noheader":      # amendment 5, reading 3: a record that can still be read is printed as recorded
            assert "recorded in decisions.csv on 2026-12-20T00:00:00Z" in r.stdout
            assert "the file is damaged, and this record can still be read" in r.stdout
        else:
            assert "not recorded: the decision record is unreadable" in r.stdout
        assert (d / "decisions.csv").read_text() == content


def test_amendment_4_says_test_record_is_for_tests_only():
    """The final review's m4: section 3 said a run with --now records nothing, but --now --test-record records
    beside a test ledger."""
    text = section(3)
    assert "`--test-record` exists for tests only" in text
    assert "beside a test ledger" in text and "refused on a live ledger" in text


def test_reading_3_a_preview_shows_only_decisions_made_by_its_date(tmp_path):
    """The final review's m5: a preview dated before a recorded decision printed it as FINAL."""
    a, sa = rb_signals(40)
    score(tmp_path, a, sa, "2027-01-10", "--test-record")                               # recorded on Jan 10, 2027
    early = rb(score(tmp_path, a, sa, "2026-11-20"))
    assert "INTERIM read, decides nothing" in early and "recorded in decisions.csv" not in early
    late = rb(score(tmp_path, a, sa, "2027-02-01"))
    assert "FINAL: KEEP" in late and "recorded in decisions.csv on 2027-01-10T00:00:00Z" in late
    assert "only if it was decided at or before the preview's date" in section(3)


def test_reading_3_the_fingerprint_is_rechecked_and_its_recipe_is_stated(tmp_path):
    """The final review's m6 (its 1d): an entered row was edited, no number changed, and nothing was said."""
    a, sa = rb_signals(40)
    score(tmp_path, a, sa, "2026-12-20", "--test-record")
    again = rb(score(tmp_path, a, sa, "2026-12-21", "--test-record"))
    assert "FINAL: KEEP" in again and "warning" not in again
    edited = [dict(r, venue="Other") if i == 1 else r for i, r in enumerate(a)]         # a later quote used as a close
    later = rb(score(tmp_path, edited, sa, "2026-12-22", "--test-record"))
    assert ("warning: the ledger's header or the rows behind this recorded decision have changed since it was "
            "recorded") in later and "The recorded decision still stands." in later
    assert len(pd.read_csv(tmp_path / "decisions.csv")) == 1
    text = section(3)
    for words in ("sha256 of the ledger's header line", "exactly as written", "in the order of the ledger",
                  "newline", "UTF-8", "recomputes", "later quotes used as closes"):
        assert words in text, words


def test_reading_3_freshness_is_the_current_seasons_schedule_file(tmp_path):
    """The final review's m7 (its 1g): the current season's file was 2 days and 1 minute old, an older season's
    file was fresh, and the run recorded."""
    a, sa = rb_signals(40)
    proj = live_project(tmp_path, "live", a, sa, "2026-12-18T16:59")
    season_file(proj, 2025, [sched(999999, kick="2025-10-04T19:00Z")], "2026-12-20T16:00")
    scorer = proj / "scripts" / "score_forward.py"
    out = on_clock(tmp_path, "2026-12-20T17:00", scorer).stdout
    assert "FINAL: KEEP" in out and not (proj / "data" / "forward" / "decisions.csv").exists()
    assert ("not recorded: the current season's schedule, schedules_2026.parquet, was last refreshed 2026-12-18 16:59 "
            "UTC, more than 2 days ago") in out
    touch(proj / "data" / "raw" / "cfbfastr" / "schedules_2026.parquet", "2026-12-18T17:01")
    out = on_clock(tmp_path, "2026-12-20T17:00", scorer).stdout
    assert "recorded in decisions.csv on 2026-12-20T17:00:00Z" in out
    assert "current season's schedule file" in section(3)


def test_reading_3_a_record_made_at_the_end_of_the_test_reprints_without_contradiction(tmp_path):
    """The final review's m8: after two late scores the reprint said "The test ended with 40 settled signals,
    fewer than 40.\""""
    rows, s = rb_signals(40, every_days=7)
    unscored = [dict(x, home_points=np.nan, away_points=np.nan, completed=False) if i < 2 else x for i, x in enumerate(s)]
    first = rb(score(tmp_path, rows, unscored, "2028-02-05", "--test-record"))
    assert "FINAL: INCONCLUSIVE. The test ended with 38 settled signals, fewer than 40." in first
    later = rb(score(tmp_path, rows, s, "2028-02-06", "--test-record"))
    assert "40 settled, 0 pending, 0 void" in later
    assert "The test ended with 38 settled signals, fewer than 40." in later
    assert "The test ended with 40 settled signals" not in later
    assert "a fresh count on the same horizon now finds 40 settled signals, not 38. The recorded decision stands." in later


def test_reading_3_the_record_is_looked_up_by_its_decision_id(tmp_path):
    """The final review's m10: the record is found by its fixed id, whatever its label says."""
    a, sa = rb_signals(40)
    score(tmp_path, a, sa, "2026-12-20", "--test-record")
    d = pd.read_csv(tmp_path / "decisions.csv", dtype=str, keep_default_na=False)
    assert list(d.decision_id) == ["CFB_RULE_B"]
    d["rule"], d["horizon"] = "Rule B (wind)", "after 40 signals or Army-Navy"             # a later rewording
    d.to_csv(tmp_path / "decisions.csv", index=False)
    out = rb(score(tmp_path, a, sa, "2026-12-21", "--test-record"))
    assert "recorded in decisions.csv on 2026-12-20T00:00:00Z" in out
    assert len(pd.read_csv(tmp_path / "decisions.csv")) == 1
    assert "`CFB_RULE_B`" in section(3) and "never by the wording of its label" in section(3)


def test_reading_10_a_postponed_game_that_signals_again_is_two_listings(tmp_path):
    """The final review's m11 (its misc.py): the postponed game signalled again on its new date was never a bet."""
    rows = [row(77, "2026-10-10T19:30Z", "2026-10-08T14:30Z", rule_b="SIGNAL", mkt_total=50.5),
            row(77, "2026-10-31T19:30Z", "2026-10-29T14:30Z", rule_b="SIGNAL", mkt_total=48.5),
            row(77, "2026-10-31T19:30Z", "2026-10-31T16:30Z", mkt_total=47.5)]          # the new listing's later quote
    out = rb(score(tmp_path, rows, [sched(77, 20, 20, kick="2026-10-31T19:30Z")], "2026-11-10"))
    assert "2 signals, 1 settled, 0 pending, 1 void (not graded)" in out
    assert "void, the game kicked off more than 24 hours from the kickoff on its entry row: 1 (77)" in out
    assert "record 1-0-0" in out and "mean CLV +1.00" in out
    assert "is two listings" in section(10)


def test_reading_12_fewer_than_20_closes_make_rule_b_inconclusive(tmp_path):
    a, sa = rb_signals(15)                                                               # each with a later quote
    b, sb = rb_signals(25, first="2026-10-18T19:00Z", first_id=100, close=None)          # no close at all
    out = rb(score(tmp_path, a + b, sa + sb, "2026-12-20"))
    assert "FINAL: INCONCLUSIVE (only 15 of the 40 signals have a primary close, fewer than 20)" in out
    assert "25 of the 40 signals have no primary close" in out
    assert "fewer than 20 of the bets in a decision have a primary close" in section(12)
    assert "does not apply to Rule HT" in section(12)


def norm(text):
    return " ".join(text.replace("**", "").replace("`", "").split())


def test_amendment_4_names_every_earlier_sentence_it_replaces():
    """The final review's m12 and its list of pairs: every sentence quoted as replaced is quoted exactly."""
    whole = (ROOT / "PREREGISTRATION.md").read_text()
    earlier = norm(whole.split("## Amendment 4 ")[0])
    replaces = amendment4().split("### What this amendment replaces")[1]
    quotes = re.findall(r'"([^"]+)"', replaces)
    assert len(quotes) >= 8
    for q in quotes:
        assert norm(q) in earlier, q
    for pair in ("The primary CLV compares the entry with the last alert quote before kickoff.",
                 "Later signals never enter it, so a later run of the scorer prints the same result.",
                 "40th signal's kickoff"):
        assert pair in norm(replaces), pair


def test_amendment_4_tests_nothing_and_leaves_the_count_unchanged():
    """The final review's M3: the new text said the count stays 200 (bar p < 0.00025); it was 271 at merge."""
    text = norm(amendment4())
    assert "stays 200" not in text and "0.00025" not in text
    assert "test nothing and leave the running variant count unchanged" in text
    assert "271" in text and "p < 0.000185" in text
    assert "now 200 variants" not in (ROOT / "STRATEGY.md").read_text()


def test_the_readme_keeps_its_original_sentence_and_adds_a_dated_note():
    """The final review: a sentence inside the README's historical section was reworded instead of superseded."""
    readme = (ROOT / "README.md").read_text()
    assert ("- **Decisions are made on dates, once.** Rule B: after 40 signals or Army–Navy (Dec 12, 2026), whichever "
            "is later, on the signals that kicked off by then. Rule HT: after the 2027 season's title game. A cancelled "
            "game can't hold a decision open, and a game is graded only once the schedule marks it completed. Before "
            "the horizon the scorer prints the numbers and no verdict.") in readme
    assert "*Note, Sep 29 (amendment 4):*" in readme


# ================================================================== the second review of this amendment (Sep 29)
def rb_and_ht():
    """40 Rule B signals that keep, and 12 Rule HT bets that promote, with their schedule."""
    rows, s = rb_signals(40)
    for i in range(12):
        k = ts("2026-10-10T23:00Z") + pd.Timedelta(days=7 * i)
        rows.append(ht_bet(500 + i, k))
        s.append(sched(500 + i, kick=k))
    return rows, s


def test_reading_3_a_record_cut_inside_its_last_field_is_damaged_and_never_added_to(tmp_path):
    """The second review's major finding (its probe_c5): Rule B's record was cut inside its fingerprint; Rule HT's
    decision was glued onto it, and the next run recorded Rule B a second time, 14 months late."""
    rows, s = rb_and_ht()
    score(tmp_path / "ok", rows, s, "2026-12-20", "--test-record")
    whole = (tmp_path / "ok" / "decisions.csv").read_text()
    head, line = whole.splitlines()
    cut = {"cut": whole[:-20],                                                  # no line break, fingerprint cut
           "short": f"{head}\n{line[:-20]}\n",                                  # a line break, fingerprint cut
           "nine": f"{head}\n{line.rsplit(',', 1)[0]}\n"}                       # the last field gone
    for name, content in cut.items():
        d = tmp_path / name
        d.mkdir()
        (d / "decisions.csv").write_text(content)
        out = score(d, rows, s, "2028-02-02", "--test-record")
        assert "Decision record: decisions.csv is unreadable" in out, name
        assert "decision (Rule HT: once, after the 2027 season), FINAL: PROMOTE" in out, name
        assert out.count("not recorded: the decision record is unreadable") == 2, name
        assert "recorded in decisions.csv on" not in out, name
        assert (d / "decisions.csv").read_text() == content, name
    assert "a line without exactly its 10 fields" in section(3) and "It never adds a line" in section(3)


def lost_record_project(tmp_path):
    """A live project whose Rule B KEEP was recorded on Dec 20 and copied to the ledgers branch; three late Dec 12
    signals then turn a fresh computation to NOT KEPT."""
    a, sa = rb_signals(40)
    repo = tmp_path / "repo"
    proj = live_project(repo, "cfb-weather", a, sa, "2026-12-20T16:00")
    git(repo, "init", "-q")
    fwd, scorer = proj / "data" / "forward", proj / "scripts" / "score_forward.py"
    assert "FINAL: KEEP" in on_clock(tmp_path, "2026-12-20T17:00", scorer).stdout
    b, sb = rb_signals(3, first="2026-12-12T17:00Z", every_days=0, first_id=900, close=56.5)
    pd.DataFrame(a + b).to_csv(fwd / "ledger.csv", index=False)
    return repo, proj, fwd, scorer, sa + sb


def test_reading_3_a_damaged_copy_on_the_ledgers_branch_stops_recording(tmp_path):
    """The second review: the local record was damaged, the nightly copy took the damage, the damaged file was
    removed, and the next real run decided again."""
    repo, proj, fwd, scorer, s = lost_record_project(tmp_path)
    data = (fwd / "decisions.csv").read_bytes()
    for name, damaged in (("cut", data[: len(data) // 2 + 60]), ("empty", b"")):
        (tmp_path / name).write_bytes(damaged)
        publish(repo, "cfb-weather", tmp_path / name)                        # the nightly copy took the damage
        if (fwd / "decisions.csv").exists():
            (fwd / "decisions.csv").unlink()                                  # the damaged file is removed
        season_file(proj, 2026, s, "2026-12-21T16:00")
        out = on_clock(tmp_path, "2026-12-21T17:00", scorer).stdout
        assert "its copy on the ledgers branch (origin/ledgers:cfb-weather/decisions.csv) is unreadable" in out, name
        assert "git log origin/ledgers -- cfb-weather/decisions.csv" in out, name
        assert "FINAL: NOT KEPT" in rb(out) and "not recorded: the decision record is missing and its copy" in rb(out)
        assert not (fwd / "decisions.csv").exists(), name
    assert "A copy that is there but can't be read" in section(3) and "counts as no copy" not in section(3)


def test_reading_3_while_the_record_is_missing_every_run_on_the_live_ledger_prints_its_copy(tmp_path):
    """The second review: with the record lost and the schedule 3 days old, the daily run printed a fresh FINAL
    against the recorded one and never mentioned the copy; so did a worker's scorer on the live ledger."""
    repo, proj, fwd, scorer, s = lost_record_project(tmp_path)
    publish(repo, "cfb-weather", fwd / "decisions.csv")
    (fwd / "decisions.csv").unlink()
    season_file(proj, 2026, s, "2026-12-18T16:00")                            # 3 days old at the next run
    pd.DataFrame(s).to_csv(tmp_path / "sched.csv", index=False)
    worker = project(repo / "worker", "cfb-weather")                          # a worker's copy of the scorer
    for script, args in ((scorer, ()), (worker / "scripts" / "score_forward.py",
                                        ("--ledger", str(fwd / "ledger.csv"), "--schedule", str(tmp_path / "sched.csv")))):
        out = on_clock(tmp_path, "2026-12-21T17:00", script, *args).stdout
        assert "its copy on the ledgers branch (origin/ledgers:cfb-weather/decisions.csv) holds 1 recorded decision" in out
        assert "FINAL: KEEP" in rb(out) and "recorded in decisions.csv on 2026-12-20T17:00:00Z" in rb(out)
        assert "read from its copy on the ledgers branch (the file is missing)" in rb(out)
        assert "a fresh computation on the same horizon now gives: NOT KEPT" in rb(out)
        assert "FINAL: NOT KEPT" not in rb(out)
        assert not (fwd / "decisions.csv").exists()                           # only a real run restores it
    season_file(proj, 2026, s, "2026-12-21T16:00")
    out = on_clock(tmp_path, "2026-12-21T18:00", scorer).stdout
    assert "restored 1 recorded decision from its copy on the ledgers branch" in out
    assert len(pd.read_csv(fwd / "decisions.csv")) == 1
    assert "prints its decisions as recorded, and leaves the file alone" in section(3)


def test_reading_3_a_record_whose_numbers_a_later_run_cant_print_is_damaged(tmp_path):
    """The second review: a record whose numbers were valid JSON without a key the scorer prints crashed the
    whole run, so the day's report was lost. An id the scorer doesn't know is damage too."""
    a, sa = rb_signals(40)
    score(tmp_path / "ok", a, sa, "2026-12-20", "--test-record")
    rec = pd.read_csv(tmp_path / "ok" / "decisions.csv", dtype=str, keep_default_na=False)
    nums = json.loads(rec.numbers[0])
    nums["n_close"] = nums.pop("n_clv")                                       # another name for the key
    for name, edited, why in (("key", rec.assign(numbers=json.dumps(nums)), "numbers have no n_clv"),
                              ("id", rec.assign(decision_id="CFB_RULE_B "), "an unknown decision id")):
        d = tmp_path / name
        d.mkdir()
        edited.to_csv(d / "decisions.csv", index=False)
        pd.DataFrame(a).to_csv(d / "ledger.csv", index=False)
        pd.DataFrame(sa).to_csv(d / "sched.csv", index=False)
        r = run(ROOT / "scripts" / "score_forward.py", "--ledger", str(d / "ledger.csv"), "--schedule",
                str(d / "sched.csv"), "--now", "2026-12-21", "--test-record")
        assert r.returncode == 0, (name, r.stderr[-400:])
        assert "Decision record: decisions.csv is unreadable" in r.stdout and why in r.stdout, name
        assert "RULE_HT:" in r.stdout and "Variants under forward test" in r.stdout, name
        assert len(pd.read_csv(d / "decisions.csv")) == 1, name


def test_amendment_4_names_the_amendment_3_sentence_section_1_changes():
    """The second review found amendment 6's list left out amendment 5's "It uses the bets that kicked off by its
    horizon."; amendment 3 has the same sentence for Rule B, which section 1 changes (void signals are left out)."""
    replaces = norm(amendment4().split("### What this amendment replaces")[1])
    assert '"The decision uses the signals that kicked off by that horizon"' in replaces


def test_the_summaries_say_a_record_lost_before_its_copy_can_be_decided_again():
    """The second review: STATUS, both STRATEGY rows and the README promised "never decided again" without the
    amendment's limit; and the strategy-research rehearsal row lost its old "3 to 5 a week"."""
    caveat = "never decided again unless it is lost before that night's copy is made"
    assert (ROOT / "STRATEGY.md").read_text().count(caveat) == 2
    assert caveat in (ROOT / "README.md").read_text()
    assert "never decided again, unless it is lost before that night's copy is made" in (
        ROOT.parent / "STATUS.md").read_text()
    assert ("if it is lost before then, neither the file nor a copy holds it, and the next real run decides it "
            "again") in section(3)
    assert "about 3 to 6 a week (rerun Sep 29; was 34, about 3 to 5 a week)" in (
        ROOT.parent / "strategy-research" / "README.md").read_text()


# ================================================================== amendment 5 (Sep 29): the keep test and the record
def amendment5():
    return (ROOT / "PREREGISTRATION.md").read_text().split("## Amendment 5 ")[1].split("\n## ")[0]


def amendment5_section(n):
    return " ".join(amendment5().split(f"### {n}.")[1].split("\n### ")[0].split())


REGISTERED_BY_HUB = ("Registered by the hub on the owner's standing instruction of September 29, 2026 (the hub decides "
                     "questions of how the tests are graded and reports them; money, and any rule's trigger, gate or "
                     "price cap, stay the owner's). The registering commit is the merge of pull request 64. The owner "
                     "can change any reading here by a dated amendment made before the first outcome it would affect.")


def test_amendment_5_is_registered_as_the_hub_was_told_and_names_what_it_replaces():
    text = norm(amendment5())
    assert REGISTERED_BY_HUB in text
    assert "No trigger, gate, price cap or stake changes." in text and "The rules version stays cfb-v3-2026-09-28" in text
    assert "on the day of registration it is 271, so the multiple-testing bar is p < 0.000185" in text
    whole = (ROOT / "PREREGISTRATION.md").read_text().split("## Amendment 5 ")[0]
    strategy = (ROOT / "STRATEGY.md").read_text()
    bullets = amendment5().split("### What this amendment replaces")[1].split("\n* ")[1:]
    assert len(bullets) >= 7
    for bullet in bullets:
        label, rest = bullet.split(': "', 1)
        if label.startswith("`STRATEGY.md`"):
            src = strategy
        else:
            m = re.match(r"Amendment (\d+)(?:, section (\d+))?", label)
            src = whole.split(f"## Amendment {m[1]} ")[1].split("\n## ")[0]
            src = src.split(f"### {m[2]}.")[1].split("\n### ")[0] if m[2] else src
        quotes = re.findall(r'"([^"]+)"', '"' + rest)
        assert quotes, label
        for q in quotes:
            assert norm(q) in norm(src), (label, q)
    one = amendment5_section(1)
    for words in ("5.2%, 5.8% and 6.3% of the time; the grouped interval 3.6%, 3.7% and 4.0%",
                  "40,000 simulated paths per case", "the owner has not chosen a gate", "Rule HT is graded on results",
                  "It does not fix the NFL", "0 variants"):
        assert words in one, words
    two = amendment5_section(2)
    assert "the first listed in the feed is taken" in two and "none is taken" in two and "within 6 hours" in two
    assert "Pinnacle comes first, then one priced at DraftKings" in two and "byte-identical" in two


def test_the_summaries_name_amendment_5():
    strategy = (ROOT / "STRATEGY.md").read_text()
    assert "*Amendment 5 (Sep 29):* the 95% interval is grouped by game day" in strategy
    status = (ROOT.parent / "STATUS.md").read_text()
    assert "the college football one until Thu Oct 1, 5:00 PM Pacific" in status
    assert "The registered primary CLV and the decision rules are unchanged" not in status
    assert "the captured close enters Rule B's primary CLV when no later quote was logged" in status
    assert "college football goes from 5.2 to 6.3% to 3.6 to 4.0%" in status


def by_hand(clv, days):
    """The registered interval computed here from its definition (amendment 5, reading 1), not with the scorer's
    code: the plain mean m of the n CLVs; G game days; s_g the sum of (CLV - m) over day g; the variance of the mean
    (G / (G - 1)) x sum(s_g^2) / n^2; m +/- t(0.975, G - 1) x its square root. Also the plain interval."""
    from scipy import stats
    x, d = np.asarray(clv, float), np.asarray(days, object)
    x, d = x[~np.isnan(x)], d[~np.isnan(x)]
    n, m = len(x), x.mean()
    labels = sorted(set(d))
    s = np.array([(x[d == g] - m).sum() for g in labels])
    se = np.sqrt(len(labels) / (len(labels) - 1) * (s ** 2).sum() / n ** 2) if len(labels) > 1 else np.nan
    half = stats.t.ppf(0.975, len(labels) - 1) * se if len(labels) > 1 else np.nan
    plain = 1.96 * x.std(ddof=1) / np.sqrt(n)
    return dict(mean_clv=m, ci_low=m - half, ci_high=m + half, n_clv=n, game_days=len(labels),
                plain_ci_low=m - plain, plain_ci_high=m + plain)


def keep_case(kicks, no_close=()):
    """One Rule B signal per kickoff (UTC), entry 50.5, and a later quote 3 hours out that gives a varied CLV
    (none for the signals in `no_close`): ledger rows, schedule, each signal's CLV and its Eastern game day."""
    rows, s, clv = [], [], []
    for i, k in enumerate(kicks):
        c = ((7 * i) % 11 - 3) * 0.5                                             # CLVs from -1.5 to +3.5, repeated
        rows.append(row(1 + i, k, ts(k) - pd.Timedelta(days=2), rule_b="SIGNAL", mkt_total=50.5))
        if i not in no_close:
            rows.append(row(1 + i, k, ts(k) - pd.Timedelta(hours=3), mkt_total=50.5 - c))
        s.append(sched(1 + i, kick=k))
        clv.append(np.nan if i in no_close else c)
    days = [ts(k).tz_convert("America/New_York").strftime("%Y-%m-%d") for k in kicks]
    return rows, s, clv, days


def test_amendment_5_reading_1_the_keep_interval_is_grouped_by_game_day(tmp_path):
    """Recomputed here from the registered definition on 1, 2, 5 and 20 game days, with equal CLVs, signals with no
    close, and a late Saturday game (10:30 PM Eastern, 02:30 UTC Sunday) that groups with Saturday."""
    late = (["2026-10-17T16:00Z"] * 8 + ["2026-10-18T02:30Z"] * 5 + ["2026-10-22T23:30Z"] * 6
            + ["2026-10-24T00:00Z"] * 6 + ["2026-10-24T19:30Z"] * 8 + ["2026-10-31T19:30Z"] * 7)
    cases = {
        "one day": (["2026-10-10T19:00Z"] * 40, ()),
        "two days": (["2026-10-10T19:00Z"] * 20 + ["2026-10-17T19:00Z"] * 20, (3, 17, 30)),
        "five days, late Saturday": (late, (0, 9)),
        "twenty days": ([ts("2026-10-03T19:30Z") + pd.Timedelta(days=3 * (i // 2)) for i in range(40)], (11,)),
    }
    for name, (kicks, none) in cases.items():
        rows, s, clv, days = keep_case(kicks, none)
        d = tmp_path / name.replace(" ", "_").replace(",", "")
        out = rb(score(d, rows, s, "2026-12-20", "--test-record"))
        nums = json.loads(pd.read_csv(d / "decisions.csv", dtype=str).numbers[0])
        want = by_hand(clv, days)
        assert (nums["game_days"], nums["n_clv"]) == (want["game_days"], want["n_clv"]), name
        for k in ("mean_clv", "plain_ci_low", "plain_ci_high"):
            assert np.isclose(nums[k], want[k], rtol=1e-12, atol=1e-12), (name, k)
        if want["game_days"] < 2:
            assert nums["ci_low"] is None and nums["ci_high"] is None, name
            assert ("FINAL: INCONCLUSIVE (the 40 signals that have a primary close kicked off on 1 game day, so there "
                    "is no interval)") in out, name
            assert "no interval: the signals with a primary close kicked off on 1 game day; plain, for reference" in out
            continue
        for k in ("ci_low", "ci_high"):
            assert np.isclose(nums[k], want[k], rtol=1e-12, atol=1e-12), (name, k)
        assert (f"95% CI {want['ci_low']:+.2f} to {want['ci_high']:+.2f}, grouped by game day over "
                f"{want['game_days']} days; plain, for reference: {want['plain_ci_low']:+.2f} to "
                f"{want['plain_ci_high']:+.2f}") in out, name
    # the late Saturday game is Sunday in UTC, where it would be a day of its own and change the interval
    rows, s, clv, days = keep_case(late, (0, 9))
    utc = [ts(k).strftime("%Y-%m-%d") for k in late]
    assert days[8] == "2026-10-17" and utc[8] == "2026-10-18" and len(set(days)) == 5
    assert not np.isclose(by_hand(clv, utc)["ci_low"], by_hand(clv, days)["ci_low"])
    text = amendment5_section(1)
    for words in ("grouped by the calendar date of the game's actual kickoff in Eastern time", "(G / (G - 1))",
                  "97.5th percentile of Student's t with G - 1 degrees of freedom", "fewer than 2 game days",
                  "plain, for reference"):
        assert words in text, words


def test_amendment_5_reading_1_the_interim_read_uses_the_grouped_interval(tmp_path):
    rows, s, clv, days = keep_case([ts("2026-10-03T19:30Z") + pd.Timedelta(days=7 * (i // 3)) for i in range(12)])
    out = rb(score(tmp_path, rows, s, "2026-11-01"))
    assert "INTERIM read" in out and f"grouped by game day over {len(set(days))} days" in out


def test_amendment_5_reading_3_a_time_with_no_time_zone_is_damage_not_a_crash(tmp_path):
    """The second review of amendment 4 (its r2naive): a recorded time re-saved without its 'Z' passed the checks
    and crashed the whole run with TypeError, so the day's report was lost."""
    a, sa = rb_signals(40)
    score(tmp_path, a, sa, "2026-12-20", "--test-record")
    rec = pd.read_csv(tmp_path / "decisions.csv", dtype=str, keep_default_na=False)
    for col, naive in (("horizon_utc", "2026-12-13 08:00:00"), ("decided_utc", "2026-12-20T00:00:00")):
        rec.assign(**{col: naive}).to_csv(tmp_path / "decisions.csv", index=False)
        before = (tmp_path / "decisions.csv").read_text()
        r = run(ROOT / "scripts" / "score_forward.py", "--ledger", str(tmp_path / "ledger.csv"), "--schedule",
                str(tmp_path / "sched.csv"), "--now", "2026-12-21", "--test-record")
        assert r.returncode == 0, (col, r.stderr[-400:])
        assert "Decision record: decisions.csv is unreadable (ValueError: a time with no time zone" in r.stdout, col
        assert "RULE_HT:" in r.stdout and "Variants under forward test" in r.stdout, col
        assert (tmp_path / "decisions.csv").read_text() == before, col
    assert "a record whose time cannot be read as a UTC time is a damaged record" in amendment5_section(3)


def test_amendment_5_reading_3_a_damaged_record_still_prints_the_decisions_it_can(tmp_path):
    """The second review of amendment 4 (its r2probe T2): a second record line was cut mid-write; the next run
    printed a fresh FINAL that contradicted the recorded KEEP and never showed it."""
    a, sa = rb_signals(40)
    score(tmp_path, a, sa, "2026-12-20", "--test-record")
    whole = (tmp_path / "decisions.csv").read_text()
    (tmp_path / "decisions.csv").write_text(whole + "CFB_RULE_HT,Rule HT,once, after the 2027")
    before = (tmp_path / "decisions.csv").read_text()
    worse = [dict(r, mkt_total=56.5) if r["rule_b"] != "SIGNAL" else r for r in a]    # a fresh computation: NOT KEPT
    out = score(tmp_path, worse, sa, "2026-12-22", "--test-record")
    assert "Decision record: decisions.csv is unreadable" in out
    assert "1 recorded decision in it can still be read (CFB_RULE_B) and is printed below as recorded." in out
    assert "FINAL: KEEP, on the 40 signals" in rb(out) and "recorded in decisions.csv on 2026-12-20T00:00:00Z" in rb(out)
    assert "the file is damaged, and this record can still be read" in rb(out)
    assert "a fresh computation on the same horizon now gives: NOT KEPT" in rb(out)
    assert "FINAL: NOT KEPT" not in rb(out) and "The recorded decision stands." in rb(out)
    assert (tmp_path / "decisions.csv").read_text() == before                  # nothing is added to a damaged file
    assert "any decision in it that can still be read is still printed as recorded" in amendment5_section(3)


def test_amendment_5_reading_3_a_decision_missing_from_the_file_is_restored_from_the_copy(tmp_path):
    """The second review of amendment 4 (its r2probe T3): the record was cut back to its header while the file
    stayed, and the next real run decided NOT KEPT although the copy held KEEP."""
    repo, proj, fwd, scorer, s = lost_record_project(tmp_path)
    publish(repo, "cfb-weather", fwd / "decisions.csv")                       # the nightly copy holds KEEP
    whole = (fwd / "decisions.csv").read_text()
    head = whole.splitlines()[0] + "\n"
    (fwd / "decisions.csv").write_text(head)                                  # the file stays; its record is gone
    season_file(proj, 2026, s, "2026-12-18T16:00")                            # stale: this run may not record
    out = on_clock(tmp_path, "2026-12-21T17:00", scorer).stdout
    assert ("data/forward/decisions.csv doesn't hold 1 recorded decision that its copy on the ledgers branch "
            "(origin/ledgers:cfb-weather/decisions.csv) holds (CFB_RULE_B), printed below as recorded") in out
    assert "FINAL: KEEP" in rb(out) and "read from its copy on the ledgers branch (the file is missing it)" in rb(out)
    assert "FINAL: NOT KEPT" not in rb(out) and (fwd / "decisions.csv").read_text() == head
    season_file(proj, 2026, s, "2026-12-21T16:00")                            # a real run restores it
    out = on_clock(tmp_path, "2026-12-21T18:00", scorer).stdout
    assert ("data/forward/decisions.csv was missing 1 recorded decision that its copy on the ledgers branch "
            "(origin/ledgers:cfb-weather/decisions.csv) holds (CFB_RULE_B); restored from the copy") in out
    assert "FINAL: KEEP" in rb(out) and "recorded in decisions.csv on 2026-12-20T17:00:00Z" in rb(out)
    assert "restored from the ledgers branch" in rb(out)
    assert "a fresh computation on the same horizon now gives: NOT KEPT" in rb(out)
    assert (fwd / "decisions.csv").read_text() == whole                        # the copy's line, as it was written
    cut = head + whole.splitlines()[1][:60] + "\n"                            # damaged, and the copy holds it
    (fwd / "decisions.csv").write_text(cut)
    out = on_clock(tmp_path, "2026-12-21T19:00", scorer).stdout
    assert "No recorded decision in it can still be read." in out
    assert "FINAL: KEEP" in rb(out) and "read from its copy on the ledgers branch (the file is damaged)" in rb(out)
    assert "FINAL: NOT KEPT" not in rb(out) and (fwd / "decisions.csv").read_text() == cut
    assert "is restored from the copy, never decided again" in amendment5_section(3)


# ================================================================== the review of pull request 64 (Sep 29)
def test_amendment_5_reading_3_a_damaged_copy_stops_recording_and_shows_what_it_can(tmp_path):
    """The review of pull request 64 (its rec_probe c3 and c4, on the NFL scorer; the record code is the same
    here): the copy's first record line could be read and the line after it was cut. With the file present but
    missing that decision, the next real run decided it again and said nothing about the copy; with the file
    missing, it printed a fresh FINAL. A damaged copy stops recording (amendment 4, section 3) whether or not the
    file is there."""
    repo, proj, fwd, scorer, s = lost_record_project(tmp_path)
    whole = (fwd / "decisions.csv").read_text()
    head, line = whole.splitlines()
    (tmp_path / "damaged.csv").write_text(f"{head}\n{line}\n{line[:40]}")    # the copy's last line was cut
    publish(repo, "cfb-weather", tmp_path / "damaged.csv")
    season_file(proj, 2026, s, "2026-12-21T16:00")
    unreadable = "its copy on the ledgers branch (origin/ledgers:cfb-weather/decisions.csv) is unreadable"
    for name, content, why in (
            ("the file lost it", head + "\n",
             "the file is missing it; the copy is damaged, and this line of it can still be read"),
            ("the file is missing", None,
             "the file is missing, and the copy is damaged; this line of it can still be read")):
        if content is None:
            (fwd / "decisions.csv").unlink()
        else:
            (fwd / "decisions.csv").write_text(content)
        out = on_clock(tmp_path, "2026-12-21T17:00", scorer).stdout
        assert unreadable in out and "1 recorded decision in the copy can still be read (CFB_RULE_B)." in out, name
        assert "FINAL: KEEP" in rb(out) and "recorded in decisions.csv on 2026-12-20T17:00:00Z" in rb(out), name
        assert f"read from its copy on the ledgers branch ({why})" in rb(out), name
        assert "a fresh computation on the same horizon now gives: NOT KEPT" in rb(out), name
        assert "FINAL: NOT KEPT" not in rb(out), name
        if content is None:
            assert not (fwd / "decisions.csv").exists(), name               # nothing restored from a damaged copy
        else:
            assert (fwd / "decisions.csv").read_text() == content, name
    # the file is there and holds nothing, and the copy can't be read at all: a final decision is not recorded
    (fwd / "decisions.csv").write_text(head + "\n")
    (tmp_path / "empty.csv").write_bytes(b"")
    publish(repo, "cfb-weather", tmp_path / "empty.csv")
    out = on_clock(tmp_path, "2026-12-21T18:00", scorer).stdout
    assert unreadable in out and "No recorded decision in the copy can still be read." in out
    assert "FINAL: NOT KEPT" in rb(out) and "not recorded: its copy on the ledgers branch is unreadable" in rb(out)
    assert (fwd / "decisions.csv").read_text() == head + "\n"
    publish(repo, "cfb-weather", fwd / "decisions.csv")                       # the nightly copy of the file
    out = on_clock(tmp_path, "2026-12-21T19:00", scorer).stdout
    assert unreadable not in out and "recorded in decisions.csv on 2026-12-21T19:00:00Z" in rb(out)
    text = amendment5_section(3)
    assert "amendment 4's rule for a damaged copy applies whether or not the file is there" in text
    assert "it is not restored from a damaged copy" in text


def test_amendment_5_reading_3_the_copy_protects_a_lost_line_only_until_the_nightly_copy(tmp_path):
    """The review of pull request 64 (its rec_probe2): a line lost after the morning check-in was gone from the copy
    once that night's copy published the shortened file (ops/sync_ledgers.sh copies the file as it is), and the next
    real run decided it again. The scorer doesn't read the branch's earlier copies: this is a stated limit."""
    repo, proj, fwd, scorer, s = lost_record_project(tmp_path)
    publish(repo, "cfb-weather", fwd / "decisions.csv")                       # Dec 20, 11:45 PM: the copy holds it
    (fwd / "decisions.csv").write_text((fwd / "decisions.csv").read_text().splitlines()[0] + "\n")   # lost
    publish(repo, "cfb-weather", fwd / "decisions.csv")                       # that night: copied as it is
    season_file(proj, 2026, s, "2026-12-21T16:00")
    out = rb(on_clock(tmp_path, "2026-12-21T17:00", scorer).stdout)
    assert "FINAL: NOT KEPT" in out and "recorded in decisions.csv on 2026-12-21T17:00:00Z" in out
    text = amendment5_section(3)
    assert "the copy protects a lost line only until the next nightly copy" in text.lower()
    assert "a line lost during the day, after the check-in, is gone from the copy by the next morning" in text
    for f in (ROOT.parent / "STATUS.md", ROOT / "README.md"):
        assert "as long as the copy still holds it" in f.read_text(), f.name
    replaces = norm(amendment5().split("### What this amendment replaces")[1])
    assert '"A lost record is restored from that copy; it is never decided again." Only while the copy holds it' in (
        replaces)


def test_amendment_5_states_the_review_s_smaller_points(tmp_path):
    """The review of pull request 64, minor points: day totals that balance give the grouped interval zero width,
    now a stated limit; and the replay counts are labelled as a replay made with scratch scripts."""
    rows, s = [], []
    kicks = [ts(d) for d in ("2026-10-03T19:00Z", "2026-10-10T19:00Z", "2026-10-17T19:00Z", "2026-10-24T19:00Z")
             for _ in range(10)]
    for i, k in enumerate(kicks):
        c = 5.5 if i % 10 < 2 else -1.0                                     # each day: sum +3.0, mean +0.3
        rows.append(row(1 + i, k, k - pd.Timedelta(days=2), rule_b="SIGNAL", mkt_total=50.5))
        rows.append(row(1 + i, k, k - pd.Timedelta(hours=3), mkt_total=50.5 - c))
        s.append(sched(1 + i, kick=k))
    out = rb(score(tmp_path, rows, s, "2026-12-20", "--test-record"))
    nums = json.loads(pd.read_csv(tmp_path / "decisions.csv", dtype=str).numbers[0])
    assert nums["game_days"] == 4 and np.allclose([nums["ci_low"], nums["ci_high"], nums["mean_clv"]], 0.3,
                                                  rtol=0, atol=1e-12)
    assert nums["plain_ci_low"] < 0 < nums["plain_ci_high"]
    assert "95% CI +0.30 to +0.30, grouped by game day over 4 days; plain, for reference: -0.52 to +1.12" in out
    one = amendment5_section(1)
    assert "the grouped interval can be narrower than the plain one" in one and "even of zero width" in one
    assert "scratch scripts, not kept in the repository" in amendment5_section(2)
