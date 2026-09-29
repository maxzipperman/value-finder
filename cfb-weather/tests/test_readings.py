"""Amendment 4: the scorer readings that a review of pull request 50 found open. One test per reading,
built on the reviewers' own scenarios (their inputs are reused here). Each test fails on the scorer as
merged in pull request 50 and passes under amendment 4."""
import hashlib
import os
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

COLUMNS = ["rule", "horizon", "horizon_utc", "decided_utc", "n_bets", "verdict", "numbers", "ledger_rows_sha256"]


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
    assert (r.rule, r.n_bets, r.verdict, r.decided_utc) == ("Rule B", "40", "KEEP", "2027-01-12T00:00:00Z")
    assert r.horizon == "after 40 signals or the 2026 regular season, whichever is later"
    # the rows that entered it: each entry and each later quote used as its close (the review's minor 6)
    lines = (tmp_path / "ledger.csv").read_text().splitlines()
    entered = [lines[0]] + [ln for ln in lines[1:] if int(ln.split(",")[1]) <= 40]
    assert len(entered) == 81
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


# ------------------------------------------------------------------ reading 9: a quote, and Rule HT's entry
def test_reading_9_rule_ht_enters_at_the_last_quote_with_a_price(tmp_path):
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


# ------------------------------------------------------------------ reading 10: Rule B's primary close
def test_reading_10_rule_b_closes_at_a_later_quote_else_the_captured_close_else_none(tmp_path):
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


# ------------------------------------------------------------------ reading 11: not kept
def test_reading_11_not_kept_means_no_money_goes_on_the_rule(tmp_path):
    rows, s = rb_signals(40, close=51.5)                                     # every signal lost a point
    out = rb(score(tmp_path, rows, s, "2026-12-20"))
    assert ("FINAL: NOT KEPT (no money goes on the rule; it stays on paper for 2027 only by a dated amendment "
            "before 2027 Week 0)") in out


# ------------------------------------------------------------------ reading 12: Rule HT by price source
def test_reading_12_rule_ht_is_reported_by_price_source(tmp_path):
    rows = [ht_bet(1, "2026-10-10T23:00Z"), ht_bet(2, "2026-10-17T23:00Z"),
            ht_bet(3, "2026-10-24T23:00Z", line_src="draftkings", under=-105)]
    out = ht(score(tmp_path, rows, [sched(1), sched(2, 40, 40), sched(3)], "2026-11-01"))
    assert "by price source: pinnacle 2 (1-1-0, units -0.09); draftkings 1 (1-0-0, units +0.95)" in out


# ------------------------------------------------------------------ reading 13: amendment 3's numbers
def test_reading_13_amendment_4_quotes_the_models_own_numbers():
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
def project(tmp_path):
    """A copy of the scorer and its package, so a test can use a data/forward/ folder of its own and never
    touch the real one."""
    proj = tmp_path / "proj"
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
    pd.DataFrame(sa).assign(start_time_tbd=False).to_parquet(proj / "data" / "raw" / "cfbfastr" / "schedules_2026.parquet")
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
