"""Amendment 6: the scorer readings that a review of pull request 50 found open. One test per reading,
built on the reviewers' own scenarios (their inputs are reused here). Each test fails on the scorer as
merged in pull request 50 and passes under amendment 6."""
import csv
import fcntl
import hashlib
import io
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
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from nflweather import board  # noqa: E402
from nflweather.market import ev_under, p_under_at, pricing_cohort  # noqa: E402

RB = ("RULE_B (wind under)", "RULE_B, secondary")
LEAN = ("MODEL_LEAN", "RULE_B (wind under)")
COLUMNS = ["decision_id", "rule", "horizon", "horizon_utc", "decided_utc", "n_bets", "verdict", "numbers",
           "ledger_rows", "ledger_rows_sha256"]


def wk_day(year, wk):
    """The Sunday of `wk` in `year`'s season (Week 1's Sunday is Sep 13 in 2026)."""
    return (pd.Timestamp(f"{year}-09-10") + pd.Timedelta(weeks=wk - 1, days=3)).strftime("%Y-%m-%d")


def row(gid, day, time="13:00", snap=None, **kw):
    base = dict(rules_version="v3-2026-09-28", game_id=gid, gameday=day, gametime=time, away_team="A",
                home_team="B", lead_days=2, wx_src="era5", wx_wind=16, line_src="pinnacle", total_line=44.0,
                under_odds=-110, over_odds=-110, p_under=0.5, p_market=0.5, lean="", ev_under=0.08, rule_b="SIGNAL")
    base["snapshot_utc"] = snap or (pd.Timestamp(day) - pd.Timedelta(days=2)).strftime("%Y-%m-%dT15:00:00Z")
    return base | kw


def game(gid, day, time="13:00", season=None, week=None, game_type="REG", total=40, close=42, result=3):
    d = pd.Timestamp(day)
    season = season if season is not None else (d.year if d.month >= 8 else d.year - 1)
    return dict(game_id=gid, season=season, week=week, game_type=game_type, gameday=day, gametime=time,
                total=total, total_line=close, result=result)


def season(year, weeks, n, first_id=0, line=44.0, close=42, total=40, lean=""):
    """`n` Rule B signals (or leans) spread over `weeks`: ledger rows and schedule rows."""
    rows, games = [], []
    for i in range(n):
        wk = weeks[i % len(weeks)]
        gid = f"{year}_{wk:02d}_{first_id + i}"
        r = row(gid, wk_day(year, wk), total_line=line, lean=lean, rule_b="" if lean else "SIGNAL")
        if lean:                                                   # a lean is logged 6 days out
            r["snapshot_utc"] = (pd.Timestamp(wk_day(year, wk)) - pd.Timedelta(days=6)).strftime("%Y-%m-%dT15:00:00Z")
        rows.append(r)
        games.append(game(gid, wk_day(year, wk), season=year, week=wk, total=total, close=close))
    return rows, games


def filler(year, played=True):
    """One game a week with no bet on it, so the season's regular season is in the schedule."""
    return [game(f"{year}_{wk:02d}_FILL", wk_day(year, wk), season=year, week=wk,
                 total=40 if played else np.nan, result=3 if played else np.nan) for wk in range(1, 19)]


def score(folder, rows, games, now, *extra):
    folder.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(folder / "ledger.csv", index=False)
    pd.DataFrame(games).to_csv(folder / "games.csv", index=False)
    return subprocess.run([sys.executable, str(ROOT / "scripts" / "score_forward.py"), "--ledger",
                           str(folder / "ledger.csv"), "--games", str(folder / "games.csv"), "--now", now, *extra],
                          capture_output=True, text=True, check=True).stdout


def part(out, start, end):
    return out.split(start, 1)[1].split(end, 1)[0] if start in out else ""


def entry_fingerprint(ledger, game_ids):
    """The sha256 of the ledger's header and the entry rows of `game_ids`, exactly as written."""
    lines = ledger.read_text().splitlines()
    col = lines[0].split(",").index("game_id")
    keep = [ln for ln in lines[1:] if ln.split(",")[col] in set(game_ids)]
    return hashlib.sha256(("\n".join([lines[0]] + keep) + "\n").encode()).hexdigest()


# ------------------------------------------------------------------ reading 1: void
def test_reading_1_a_game_moved_more_than_a_day_or_never_scored_is_void(tmp_path):
    rows = [row("MOVED", "2026-10-11"), row("NORESULT", "2026-10-18"), row("PLAYED", "2026-10-25"),
            row("LATER", "2026-11-01")]
    games = [game("MOVED", "2026-10-13", time="20:15", week=6),                 # postponed two days
             game("NORESULT", "2026-10-18", week=7, total=np.nan, result=np.nan),
             game("PLAYED", "2026-10-25", week=8),
             game("LATER", "2026-11-01", time="16:25", week=9)]                 # 3 hours late: still a bet
    out = part(score(tmp_path, rows, games, "2026-11-20"), *RB)                 # NORESULT kicked off 33 days ago
    assert "4 signals, 2 settled, 0 pending, 2 void (not graded)" in out
    assert "void, the game kicked off more than 24 hours from the kickoff on its entry row: 1 (MOVED)" in out
    assert "void, the schedule shows no result 30 days after that kickoff: 1 (NORESULT)" in out
    assert "record at entry line 2-0-0" in out and "units +1.82" in out          # MOVED went under, and isn't graded


# ------------------------------------------------------------------ reading 2: pending
def test_reading_2_a_bet_still_waiting_for_its_result_holds_the_decision_open(tmp_path):
    """The reviewers' D1: the 7-day rule made this FINAL: KEEP on 40, and the late results then turned it."""
    good, g_good = season(2026, list(range(5, 18)), 40)
    for i, r in enumerate(good):
        r["total_line"] = 43.0 if i % 2 == 0 else 42.2
    late, g_late = season(2026, [18], 6, first_id=300, line=38.0)
    waiting = [dict(g, total=np.nan, result=np.nan) for g in g_late]
    out = part(score(tmp_path, good + late, g_good + waiting + filler(2026), "2027-01-25", "--test-record"), *RB)
    assert "46 signals, 40 settled, 6 pending, 0 void" in out
    assert "INTERIM read, decides nothing. Week 18 of 2026 is over; the decision waits for 6 pending signals" in out
    assert "FINAL" not in out and not (tmp_path / "decisions.csv").exists()


# ------------------------------------------------------------------ reading 3: decided once, written down
def test_reading_3_the_first_final_decision_is_written_down_and_stands(tmp_path):
    good, g_good = season(2026, list(range(5, 18)), 40)
    for i, r in enumerate(good):
        r["total_line"] = 43.0 if i % 2 == 0 else 42.2
    late, g_late = season(2026, [18], 1, first_id=300, line=30.0)             # CLV -12, if it ever counts
    unscored = [dict(g, total=np.nan, result=np.nan) for g in g_late]
    first = part(score(tmp_path, good + late, g_good + unscored + filler(2026), "2027-02-10", "--test-record"), *RB)
    assert "41 signals, 40 settled, 0 pending, 1 void" in first and "FINAL: KEEP" in first

    rec = pd.read_csv(tmp_path / "decisions.csv", dtype=str)                 # beside the test ledger
    assert list(rec.columns) == COLUMNS and len(rec) == 1
    r = rec.iloc[0]
    assert (r.decision_id, r.rule, r.horizon, r.n_bets, r.verdict) == ("RULE_B:2026", "Rule B", "after Week 18 of 2026",
                                                                       "40", "KEEP")
    assert r.decided_utc == "2027-02-10T00:00:00Z" and r.horizon_utc == "2027-01-10T18:00:00Z"
    assert '"mean_clv": 0.6' in r.numbers and '"vs_close_no_tie": 40' in r.numbers
    assert r.ledger_rows == " ".join(str(i) for i in range(1, 41))          # the 40 entry rows, by position
    assert r.ledger_rows_sha256 == entry_fingerprint(tmp_path / "ledger.csv", [x["game_id"] for x in good])

    # the missing score lands after the decision: a fresh computation now has 41 bets; the record stands
    later = part(score(tmp_path, good + late, g_good + g_late + filler(2026), "2027-02-20", "--test-record"), *RB)
    assert "41 signals, 41 settled, 0 pending, 0 void" in later
    assert "decision (Rule B: 40 signals in 2026, decided after Week 18 of 2026), FINAL: KEEP" in later
    assert "recorded in decisions.csv on 2027-02-10T00:00:00Z" in later
    assert "a fresh computation on the same horizon now gives" in later and "n=41" in later
    assert "The recorded decision stands." in later
    assert len(pd.read_csv(tmp_path / "decisions.csv")) == 1


# ------------------------------------------------------------------ reading 4: horizons are dates
def test_reading_4_week_18_ends_at_the_last_regular_season_kickoff(tmp_path):
    """No bet on the last game: the decision is final once it has kicked off, not a week after."""
    rows, games = season(2026, list(range(5, 18)), 40)
    last = game("2026_18_LAST", wk_day(2026, 18), time="20:20", week=18, total=np.nan, result=np.nan)
    before = part(score(tmp_path / "a", rows, games + [last], "2027-01-11T01:00"), *RB)
    assert ("INTERIM read, decides nothing. The decision comes after Week 18 of 2026 (the last regular-season "
            "kickoff, 2027-01-11 01:20 UTC)") in before
    after = part(score(tmp_path / "b", rows, games + [last], "2027-01-11T02:00"), *RB)
    assert "decided after Week 18 of 2026), FINAL: KEEP" in after


# ------------------------------------------------------------------ reading 5: the model lean's entry
def test_reading_5_the_lean_enters_at_its_first_snapshot_with_a_posted_total(tmp_path):
    """The reviewers' F: the earliest lean 24 hours out had no total, and was graded as a loss."""
    rows = [row("2026_06_X", "2026-10-18", snap="2026-10-11T15:00:00Z", rule_b="no_trigger", lean="UNDER lean",
                total_line=np.nan, under_odds=np.nan, over_odds=np.nan, line_src="nflverse"),
            row("2026_06_X", "2026-10-18", snap="2026-10-16T15:00:00Z", rule_b="no_trigger", lean="UNDER lean",
                total_line=44.5),
            row("2026_06_Y", "2026-10-18", snap="2026-10-18T02:30:00Z", lead_days=1)]   # Rule B, 14.5 hours out
    games = [game("2026_06_X", "2026-10-18", week=6, total=38, close=44), game("2026_06_Y", "2026-10-18", week=6)]
    out = score(tmp_path, rows, games + filler(2026, played=False), "2026-10-25")
    lean = part(out, *LEAN)
    assert "MODEL_LEAN: 1 signals, 1 settled" in out and "record at entry line 1-0-0" in lean
    assert "mean CLV +0.50 pts" in lean and "1 of 1 bets have a primary close" in lean
    assert "RULE_B (wind under): 1 signals, 1 settled" in out          # the 24-hour rule is the lean's only


# ------------------------------------------------------------------ reading 6: after the 2026 decision
def test_reading_6_an_inconclusive_2026_result_is_decided_once_more_after_2027(tmp_path):
    a, ga = season(2026, range(5, 19), 40)
    for i, r in enumerate(a):
        r["total_line"] = 43.5 if i % 2 == 0 else 41.0                 # mean CLV +0.25, interval across zero
    b, gb = season(2027, range(1, 18), 30, first_id=100)                # CLV +2 each
    out = part(score(tmp_path / "rb", a + b, ga + gb + filler(2026) + filler(2027), "2028-01-20"), *RB)
    assert "decided after Week 18 of 2026), FINAL: INCONCLUSIVE (carried into 2027 unchanged)" in out
    assert ("inconclusive in 2026, decided once more after the 2027 regular season, both seasons pooled), "
            "FINAL: KEEP") in out and "n=70" in out
    assert "mean CLV positive in both seasons (met)" in out

    leans = [dict(r, lean="UNDER lean", rule_b="") for r in a]
    for r in leans:
        r["snapshot_utc"] = (pd.Timestamp(r["gameday"]) - pd.Timedelta(days=6)).strftime("%Y-%m-%dT15:00:00Z")
    more, gm = season(2027, range(1, 18), 30, first_id=100, lean="UNDER lean")
    out = part(score(tmp_path / "lean", leans + more, ga + gm + filler(2026) + filler(2027), "2028-01-20"), *LEAN)
    assert "FINAL: INCONCLUSIVE (carried into 2027 unchanged)" in out
    assert "model lean: inconclusive in 2026, decided once more after the 2027 regular season" in out

    good, gg = season(2026, range(5, 19), 40)                           # a keep in 2026 is the decision
    bad, gbad = season(2027, range(1, 18), 30, first_id=100, line=30.0)
    out = part(score(tmp_path / "keep", good + bad, gg + gbad + filler(2026) + filler(2027), "2028-01-20"), *RB)
    assert "FINAL: KEEP" in out and out.count("FINAL") == 1
    assert "Later signals are logged and reported, and decide nothing" in out


# ------------------------------------------------------------------ reading 7: ties with the close
def test_reading_7_ties_with_the_close_are_left_out_of_the_win_rate(tmp_path):
    """The reviewers' E: 20 beat the close, 2 tie it, 18 lose to it. The win rate's count names itself, so it can't
    be read as a second count of bets "with a close" (the final review's m9)."""
    rows, games = season(2026, range(5, 19), 40, line=43.0, close=42)
    for i, g in enumerate(games):
        g["total"] = 40 if i < 20 else (42 if i < 22 else 45)
    out = part(score(tmp_path, rows, games, "2027-01-20"), *RB)
    assert ("win rate vs the close 52.6% (20 of the 38 bets that have a primary close and didn't tie it; 2 ties left "
            "out)") in out
    assert "with a close" not in out
    assert "40 of 40 bets have a primary close" in out and "FINAL: KEEP" in out


# ------------------------------------------------------------------ reading 8: amendment 5's numbers
def amendment(n):
    return (ROOT / "PREREGISTRATION.md").read_text().split(f"## Amendment {n} ")[1].split("\n## ")[0]


def test_reading_8_amendment_6_quotes_the_models_own_numbers():
    text, resid = amendment(6), pricing_cohort(board.PRICING_COHORT_SHA256)
    for line, quoted in ((42.5, -135), (43.0, -136)):                  # where the value at x = 0 reaches zero
        win, push = (float(np.ravel(v)[0]) for v in p_under_at(line, line, resid))
        assert round(-100 * win / (1 - win - push)) == quoted
    assert "about −135" in text and "−136 on a whole number" in text

    def ev(below):
        return float(np.ravel(ev_under(42.5 - below, -115, 42.5, resid))[0])
    assert ev(1.5) < 0 < ev(1.0)
    assert "from 1.5 points below the reference" in text


# ------------------------------------------------------------------ labels (the review's S14)
def test_labels_say_what_they_mean(tmp_path):
    rows, games = season(2026, range(5, 19), 40)
    out = score(tmp_path / "halves", rows, games, "2027-01-20")
    assert "mean CLV positive in both halves" in out and "halfs" not in out

    r = [row("OK", "2026-10-11"), row("NOTIME", "2026-10-11"), row("NOSCHED", "2026-10-11")]
    g = [game("OK", "2026-10-11", week=5), dict(game("NOTIME", "2026-10-11", week=5), gametime=np.nan)]
    out = score(tmp_path / "time", r, g, "2026-10-20")
    assert "excluded, no kickoff time in the schedule: 1" in out and "excluded, game not in the schedule: 1" in out

    a, ga = season(2026, range(5, 15), 10, lean="UNDER lean")          # 20 leans by the end of 2027
    b, gb = season(2027, range(1, 11), 10, first_id=100, lean="UNDER lean")
    out = part(score(tmp_path / "few", a + b, ga + gb + filler(2026) + filler(2027), "2028-01-20"), *LEAN)
    assert "FINAL: INCONCLUSIVE (fewer than 40 leans by the end of the 2027 regular season)" in out
    assert "end of the test" not in out

    a, ga = season(2026, range(5, 15), 10)                              # after Week 18 of 2026, 10 signals
    out = part(score(tmp_path / "ahead", a, ga + filler(2026) + filler(2027, played=False), "2027-02-01"), *RB)
    line = next(ln for ln in out.splitlines() if "decision (" in ln)
    assert "The decision comes after Week 18 of 2027" in line and "2026" not in line.split("INTERIM")[1]


# ================================================================== the review of this amendment (Sep 29)
def project(tmp_path, name="proj"):
    """A copy of the scorer and its package, so a test can use a data/forward/ folder of its own and never
    touch the real one."""
    proj = tmp_path / name
    shutil.copytree(ROOT / "nflweather", proj / "nflweather", ignore=shutil.ignore_patterns("__pycache__"))
    (proj / "scripts").mkdir()
    shutil.copy(ROOT / "scripts" / "score_forward.py", proj / "scripts" / "score_forward.py")
    (proj / "data" / "forward").mkdir(parents=True)
    return proj


def run(script, *args):
    return subprocess.run([sys.executable, str(script), *args], capture_output=True, text=True)


def test_reading_3_a_preview_with_now_records_nothing(tmp_path):
    """The review's N5: a what-if run with --now after Week 18 recorded KEEP while six Week 18 results were
    still missing, and the real run then had to accept it."""
    good, gg = season(2026, list(range(5, 18)), 40, line=43.0)
    bad, gbad = season(2026, [18], 6, first_id=300, line=38.0)
    waiting = [dict(g, total=np.nan, result=np.nan) for g in gbad]
    first = part(score(tmp_path, good + bad, gg + waiting + filler(2026), "2027-03-01"), *RB)
    assert "FINAL: KEEP" in first and "not recorded: a run with --now is a preview." in first
    assert not (tmp_path / "decisions.csv").exists()
    real = score(tmp_path, good + bad, gg + gbad + filler(2026), "2027-01-13")
    assert "FINAL: INCONCLUSIVE (carried into 2027 unchanged)" in real and "recorded in decisions.csv" not in real
    assert "Decision record: none written by this run: a run with --now is a preview." in real
    refused = run(ROOT / "scripts" / "score_forward.py", "--ledger", str(tmp_path / "ledger.csv"), "--games",
                  str(tmp_path / "games.csv"), "--test-record")
    assert refused.returncode != 0 and "--test-record needs --now" in refused.stderr


def test_reading_3_only_the_live_ledger_writes_the_live_record(tmp_path):
    """The review's N6: a --ledger run on the rewrite's backup copy, which sits in data/forward/, wrote the
    live decisions.csv, and the live ledger's own run then printed that record."""
    good, gg = season(2026, list(range(5, 19)), 40, line=43.0)
    score(tmp_path / "t", good, gg + filler(2026), "2027-01-20", "--test-record")     # a KEEP, recorded in a test
    proj = project(tmp_path)
    fwd, scorer = proj / "data" / "forward", proj / "scripts" / "score_forward.py"
    shutil.copy(tmp_path / "t" / "ledger.csv", fwd / "ledger.before-v3-2026-09-28.csv")
    bad, gbad = season(2026, list(range(5, 19)), 14, first_id=500, line=36.0)
    pd.DataFrame(good + bad).to_csv(fwd / "ledger.csv", index=False)
    games = tmp_path / "t" / "games.csv"
    pd.DataFrame(gg + gbad + filler(2026)).to_csv(games, index=False)

    backup = run(scorer, "--ledger", str(fwd / "ledger.before-v3-2026-09-28.csv"), "--games", str(games),
                 "--now", "2027-01-20").stdout
    assert "FINAL: KEEP" in backup and not (fwd / "decisions.csv").exists()
    assert ("not recorded: this ledger is kept in data/forward/ but is not the live ledger, so no record is read "
            "or written.") in backup
    shutil.copy(tmp_path / "t" / "decisions.csv", fwd / "decisions.csv")               # the live record, KEEP
    backup = run(scorer, "--ledger", str(fwd / "ledger.before-v3-2026-09-28.csv"), "--games", str(games),
                 "--now", "2027-01-21").stdout
    assert "recorded in decisions.csv" not in backup                                  # it never reads it either
    live = run(scorer, "--games", str(games), "--now", "2027-01-21").stdout           # the live ledger reads it
    assert "54 signals, 54 settled" in live and "recorded in decisions.csv on 2027-01-20T00:00:00Z" in live
    assert "The recorded decision stands." in live
    for ledger in ("ledger.csv", "ledger.before-v3-2026-09-28.csv"):
        refused = run(scorer, "--ledger", str(fwd / ledger), "--games", str(games), "--now", "2027-01-22",
                      "--test-record")
        assert refused.returncode != 0 and "a test ledger outside data/forward/" in refused.stderr
    assert len(pd.read_csv(fwd / "decisions.csv")) == 1

    # a copy of the scorer in another folder (a worker's worktree) reads the live record, and never writes it
    other = run(ROOT / "scripts" / "score_forward.py", "--ledger", str(fwd / "ledger.csv"), "--games", str(games)).stdout
    assert "recorded in decisions.csv on 2027-01-20T00:00:00Z" in other
    assert ("Decision record: none written by this run: this is another folder's live ledger, and only the scorer "
            "in that folder writes its record.") in other

    # on the real clock: from the default schedule only
    out = run(scorer, "--games", str(games)).stdout
    assert ("Decision record: none written by this run: the live record is written only from the default "
            "schedule, data/raw/games.csv.") in out
    shutil.copy(games, proj / "data" / "raw" / "games.csv")
    out = run(scorer).stdout
    assert "Decision record: the first final decision is written to data/forward/decisions.csv (the live record)." in out


def test_reading_3_a_stale_schedule_is_not_recorded(tmp_path):
    """The review: the daily check-in runs the scorer, and a schedule that stopped being refreshed would void
    games that were played and record a decision on the rest."""
    rows, games = season(2026, list(range(5, 19)), 40)
    score(tmp_path, rows, games + filler(2026), "2027-01-01")                         # writes the files
    old = time.time() - 3 * 86400
    os.utime(tmp_path / "games.csv", (old, old))
    args = ["--ledger", str(tmp_path / "ledger.csv"), "--games", str(tmp_path / "games.csv"), "--now", "2027-01-20",
            "--test-record"]
    out = run(ROOT / "scripts" / "score_forward.py", *args).stdout
    assert "FINAL: KEEP" in out and "more than 2 days ago; refresh it" in out and "not recorded: the schedule" in out
    assert not (tmp_path / "decisions.csv").exists()
    os.utime(tmp_path / "games.csv")                                                   # refreshed
    out = run(ROOT / "scripts" / "score_forward.py", *args).stdout
    assert "recorded in decisions.csv on 2027-01-20T00:00:00Z" in out and (tmp_path / "decisions.csv").exists()


def test_reading_6_a_pooled_decision_is_never_followed_by_a_2026_one(tmp_path):
    """The review's N4: a 2026 result missing past 30 days left 2026 at 39, so the pooled decision was
    recorded after 2027; when the result landed, a second FINAL (after Week 18 of 2026) was written."""
    a, ga = season(2026, list(range(5, 19)), 40, line=45.0)                  # CLV +3 each: a 2026 keep
    b, gb = season(2027, list(range(1, 18)), 40, first_id=100, line=38.0)    # CLV -4 each
    missing = [dict(g, total=np.nan, result=np.nan) if i == 0 else g for i, g in enumerate(ga)]
    sched = filler(2026) + filler(2027)
    first = part(score(tmp_path, a + b, missing + gb + sched, "2028-01-20", "--test-record"), *RB)
    assert "79 settled, 0 pending, 1 void" in first
    assert "once, after the 2027 regular season, both seasons pooled), FINAL: DROP" in first
    later = part(score(tmp_path, a + b, ga + gb + sched, "2028-01-21", "--test-record"), *RB)
    assert "80 settled, 0 pending, 0 void" in later
    assert "once, after the 2027 regular season, both seasons pooled), FINAL: DROP" in later
    assert "recorded in decisions.csv on 2028-01-20T00:00:00Z" in later and "The recorded decision stands." in later
    assert "decided after Week 18 of 2026" not in later
    rec = pd.read_csv(tmp_path / "decisions.csv")
    assert len(rec) == 1 and rec.horizon[0] == "after the 2027 regular season"


def test_reading_1_a_result_that_lands_after_day_30_brings_the_bet_back(tmp_path):
    """The review: void at day 30, graded again when the result lands on day 31. Amendment 6 now says so."""
    rows = [row("D", "2026-10-18")]
    unscored = [game("D", "2026-10-18", week=6, total=np.nan, result=np.nan)] + filler(2026, played=False)
    scored = [game("D", "2026-10-18", week=6)] + filler(2026, played=False)
    for now, g, expect in (("2026-11-16T17:00", unscored, "1 signals, 0 settled, 1 pending, 0 void"),
                           ("2026-11-17T17:00", unscored, "1 signals, 0 settled, 0 pending, 1 void"),
                           ("2026-11-18T17:00", scored, "1 signals, 1 settled, 0 pending, 0 void")):
        assert expect in part(score(tmp_path, rows, g, now), *RB)
    text = " ".join(amendment(6).split("### 1.")[1].split("### 2.")[0].split())
    assert "brings the bet back" in text and "the record stands" in text


def test_the_interim_read_names_week_18_of_2026_while_the_40th_signal_waits(tmp_path):
    """The review's N3b: 39 settled and the 40th still waiting after Week 18 read as a 2027 decision."""
    a, ga = season(2026, list(range(5, 19)), 40)
    last = max(range(40), key=lambda i: ga[i]["gameday"])
    ga[last] = dict(ga[last], total=np.nan, result=np.nan)
    out = part(score(tmp_path, a, ga + filler(2026), "2027-01-15"), *RB)
    assert "40 signals, 39 settled, 1 pending" in out
    assert ("decided after Week 18 of 2026): INTERIM read, decides nothing. Week 18 of 2026 is over; the decision "
            "waits for 1 pending signal.") in out
    assert "after Week 18 of 2027" not in out


def test_amendment_6_says_which_earlier_text_it_replaces():
    """The review: section 5 changes the original "What counts" entry, but the amendment named only
    amendment 5."""
    text = " ".join(amendment(6).split())                             # the text as read, line breaks aside
    assert "Where this amendment and any earlier text differ, this one applies." in text
    assert "amendment 5 differ" not in text
    lean = text.split("### 5.")[1].split("### 6.")[0]
    assert 'replaces the original "What counts"' in lean


# ================================================================== the final review of this amendment (Sep 29)
FAKE_CLOCK = """import os, runpy, sys
import pandas as pd
FAKE = pd.Timestamp(os.environ["FAKE_NOW"], tz="UTC")
pd.Timestamp.now = staticmethod(lambda tz=None: FAKE.tz_convert(tz) if tz is not None else FAKE.tz_localize(None))
script, sys.argv = sys.argv[1], sys.argv[1:]
runpy.run_path(script, run_name="__main__")
"""


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


def live_project(tmp_path, name, rows, games, refreshed):
    """A project laid out like the live checkout: its own ledger in data/forward, its default schedule."""
    proj = project(tmp_path, name)
    pd.DataFrame(rows).to_csv(proj / "data" / "forward" / "ledger.csv", index=False)
    (proj / "data" / "raw").mkdir(parents=True, exist_ok=True)
    pd.DataFrame(games).to_csv(proj / "data" / "raw" / "games.csv", index=False)
    touch(proj / "data" / "raw" / "games.csv", refreshed)
    return proj


def section(n, amend=6):
    return " ".join(amendment(amend).split(f"### {n}.")[1].split("\n### ")[0].split())


def test_reading_3_a_lost_record_is_restored_from_the_ledgers_branch_never_decided_again(tmp_path):
    """The final review's M1: the recorded KEEP was moved away and the closes corrected; the next real run
    decided again, and recorded DROP."""
    good, gg = season(2026, list(range(5, 19)), 40, line=43.0)                # CLV +1 each: a keep
    repo = tmp_path / "repo"
    proj = live_project(repo, "nfl-weather", good, gg + filler(2026), "2027-01-20T16:00")
    git(repo, "init", "-q")
    fwd, scorer = proj / "data" / "forward", proj / "scripts" / "score_forward.py"
    games = proj / "data" / "raw" / "games.csv"
    first = on_clock(tmp_path, "2027-01-20T17:00", scorer).stdout
    assert "FINAL: KEEP" in first and "recorded in decisions.csv on 2027-01-20T17:00:00Z" in first
    publish(repo, "nfl-weather", fwd / "decisions.csv")                       # the nightly copy
    (fwd / "decisions.csv").unlink()                                          # the record is lost ...
    pd.DataFrame([dict(x, total_line=46) for x in gg] + filler(2026)).to_csv(games, index=False)   # ... closes corrected
    touch(games, "2027-01-22T16:00")
    later = on_clock(tmp_path, "2027-01-22T17:00", scorer).stdout
    assert "restored 1 recorded decision from its copy on the ledgers branch" in later
    rb = part(later, *RB)
    assert "FINAL: KEEP" in rb and "recorded in decisions.csv on 2027-01-20T17:00:00Z" in rb
    assert "a fresh computation on the same horizon now gives: DROP" in rb and "The recorded decision stands." in rb
    rec = pd.read_csv(fwd / "decisions.csv")
    assert len(rec) == 1 and rec.verdict[0] == "KEEP"
    # only when neither the file nor the copy holds it is a decision recorded anew
    (fwd / "decisions.csv").unlink()
    git(repo, "update-ref", "-d", "refs/remotes/origin/ledgers")
    anew = on_clock(tmp_path, "2027-01-22T18:00", scorer).stdout
    assert "FINAL: DROP" in anew and "recorded in decisions.csv on 2027-01-22T18:00:00Z" in anew
    assert ("The record is copied to the ledgers branch every night. A lost record is restored from that copy; it is "
            "never decided again.") in section(3)


def test_reading_10_before_kickoff_is_before_the_earlier_of_the_rows_kickoff_and_the_schedules(tmp_path):
    """The final review's M2: "before kickoff" was the schedule's kickoff only."""
    rows = [row("LATE", "2026-10-11", snap="2026-10-11T18:00:00Z"),                  # after the row's 1:00 PM
            row("EARLY", "2026-10-18", time="16:25", snap="2026-10-18T18:00:00Z"),   # after the schedule's 1:00 PM
            row("LEAN", "2026-10-25", snap="2026-10-25T00:00:00Z", rule_b="no_trigger", lean="UNDER lean")]
    games = [game("LATE", "2026-10-11", time="16:25", week=5),        # moved 3 hours later
             game("EARLY", "2026-10-18", week=6),                      # moved 3 hours earlier
             game("LEAN", "2026-10-26", time="12:00", week=7)]         # moved 23 hours later: 17 hours out on the row
    out = score(tmp_path, rows, games + filler(2026, played=False), "2026-11-20")
    assert "excluded, logged at or after kickoff: 2" in out
    assert "RULE_B (wind under): 0 signals" in out and "MODEL_LEAN: 0 signals" in out
    assert "before the earlier of the kickoff on the row" in section(10)


def test_reading_3_a_scorer_whose_data_forward_is_a_link_is_not_live(tmp_path):
    """The final review's m1: a project copy whose data/forward was a link to the live folder, run with default
    arguments, wrote the live record from its own schedule."""
    good, gg = season(2026, list(range(5, 19)), 40, line=43.0)
    live = project(tmp_path, "live")
    pd.DataFrame(good).to_csv(live / "data" / "forward" / "ledger.csv", index=False)
    worker = live_project(tmp_path, "worker", good, gg + filler(2026), "2027-01-20T16:00")
    shutil.rmtree(worker / "data" / "forward")
    (worker / "data" / "forward").symlink_to(live / "data" / "forward")
    out = on_clock(tmp_path, "2027-01-20T17:00", worker / "scripts" / "score_forward.py").stdout
    assert "FINAL: KEEP" in out and not (live / "data" / "forward" / "decisions.csv").exists()
    assert "not recorded: this scorer's data/forward folder is a link to a folder outside its own project" in out
    assert "with links resolved, is inside its own project folder" in section(3)


def test_reading_3_two_runs_at_once_write_one_record(tmp_path):
    """The final review's m2: four real runs at once wrote the same decision twice in one trial of six. Here run B
    holds the record while run A reaches it; A must read it again and add nothing."""
    good, gg = season(2026, list(range(5, 19)), 40, line=43.0)
    score(tmp_path / "b", good, gg + filler(2026), "2027-01-20", "--test-record")           # run B's record
    a = tmp_path / "a"
    a.mkdir()
    pd.DataFrame(good).to_csv(a / "ledger.csv", index=False)
    pd.DataFrame(gg + filler(2026)).to_csv(a / "games.csv", index=False)
    b_lines = (tmp_path / "b" / "decisions.csv").read_text().splitlines()
    with open(a / ".decisions.lock", "a") as held:
        fcntl.flock(held, fcntl.LOCK_EX)
        run_a = subprocess.Popen([sys.executable, str(ROOT / "scripts" / "score_forward.py"), "--ledger",
                                  str(a / "ledger.csv"), "--games", str(a / "games.csv"), "--now", "2027-01-21",
                                  "--test-record"], stdout=subprocess.PIPE, text=True)
        seen = ""
        for line in run_a.stdout:
            seen += line
            if "waiting for another run" in line:
                break
        if (a / "decisions.csv").exists():                                    # B writes its row
            with open(a / "decisions.csv", "a") as fh:
                fh.write(b_lines[1] + "\n")
        else:
            (a / "decisions.csv").write_text("\n".join(b_lines) + "\n")
        fcntl.flock(held, fcntl.LOCK_UN)
    seen += run_a.stdout.read()
    run_a.wait()
    assert "waiting for another run to finish with the decision record" in seen
    assert "not recorded: this decision was already recorded on 2027-01-20T00:00:00Z (KEEP)" in seen
    assert len(pd.read_csv(a / "decisions.csv")) == 1


def test_reading_3_a_damaged_record_stops_recording_not_the_scores(tmp_path):
    """The final review's m3: a half-written line, a record cut short, a missing header or an empty file crashed
    the whole scorer, so the daily report was lost."""
    good, gg = season(2026, list(range(5, 19)), 40, line=43.0)
    score(tmp_path / "ok", good, gg + filler(2026), "2027-01-20", "--test-record")
    head, first = (tmp_path / "ok" / "decisions.csv").read_text().splitlines()[:2]
    damaged = {"half": f'{head}\n{first[:40]}"unclosed\n', "short": head + "\n" + ",".join(first.split(",")[:5]) + "\n",
               "noheader": first + "\n", "empty": ""}
    for name, content in damaged.items():
        d = tmp_path / name
        d.mkdir()
        pd.DataFrame(good).to_csv(d / "ledger.csv", index=False)
        pd.DataFrame(gg + filler(2026)).to_csv(d / "games.csv", index=False)
        (d / "decisions.csv").write_text(content)
        r = run(ROOT / "scripts" / "score_forward.py", "--ledger", str(d / "ledger.csv"), "--games", str(d / "games.csv"),
                "--now", "2027-01-21", "--test-record")
        assert r.returncode == 0, (name, r.stderr[-400:])
        assert "Decision record: decisions.csv is unreadable" in r.stdout, name
        assert "Nothing will be recorded until it is repaired or restored from the ledgers branch" in r.stdout
        assert "40 signals, 40 settled" in r.stdout and "FINAL: KEEP" in r.stdout
        if name == "noheader":      # amendment 7, reading 3: a record that can still be read is printed as recorded
            assert "recorded in decisions.csv on 2027-01-20T00:00:00Z" in r.stdout
            assert "the file is damaged, and this record can still be read" in r.stdout
        else:
            assert "not recorded: the decision record is unreadable" in r.stdout
        assert (d / "decisions.csv").read_text() == content


def test_amendment_6_says_test_record_is_for_tests_only():
    """The final review's m4: section 3 said a run with --now records nothing, but --now --test-record records
    beside a test ledger."""
    text = section(3)
    assert "`--test-record` exists for tests only" in text
    assert "beside a test ledger" in text and "refused on a live ledger" in text


def test_reading_3_a_preview_shows_only_decisions_made_by_its_date(tmp_path):
    """The final review's m5: a preview dated before a recorded decision printed it as FINAL."""
    good, gg = season(2026, list(range(5, 19)), 40, line=43.0)
    score(tmp_path, good, gg + filler(2026), "2027-02-10", "--test-record")              # recorded on Feb 10, 2027
    early = part(score(tmp_path, good, gg + filler(2026), "2026-12-01"), *RB)
    assert "INTERIM read, decides nothing" in early and "recorded in decisions.csv" not in early
    late = part(score(tmp_path, good, gg + filler(2026), "2027-03-01"), *RB)
    assert "FINAL: KEEP" in late and "recorded in decisions.csv on 2027-02-10T00:00:00Z" in late
    assert "only if it was decided at or before the preview's date" in section(3)


def test_reading_3_the_fingerprint_is_rechecked_and_its_recipe_is_stated(tmp_path):
    """The final review's m6: an entered row edited without changing a number went unnoticed, and the text did
    not give the recipe."""
    good, gg = season(2026, list(range(5, 19)), 40, line=43.0)
    score(tmp_path, good, gg + filler(2026), "2027-01-20", "--test-record")
    again = part(score(tmp_path, good, gg + filler(2026), "2027-01-21", "--test-record"), *RB)
    assert "FINAL: KEEP" in again and "warning" not in again
    edited = [dict(r, wx_src="gamebook") if i == 7 else r for i, r in enumerate(good)]
    later = part(score(tmp_path, edited, gg + filler(2026), "2027-01-22", "--test-record"), *RB)
    assert ("warning: the ledger's header or the rows behind this recorded decision have changed since it was "
            "recorded") in later and "The recorded decision still stands." in later
    assert "FINAL: KEEP" in later and len(pd.read_csv(tmp_path / "decisions.csv")) == 1
    text = section(3)
    for words in ("sha256 of the ledger's header line", "exactly as written", "in the order of the ledger",
                  "newline", "UTF-8", "recomputes"):
        assert words in text, words


def test_reading_3_the_record_is_looked_up_by_its_decision_id(tmp_path):
    """The final review's m10: the lookup keyed on the label text, so a reworded label orphaned the record and the
    next real run decided again."""
    good, gg = season(2026, list(range(5, 19)), 40, line=43.0)
    score(tmp_path, good, gg + filler(2026), "2027-01-20", "--test-record")
    d = pd.read_csv(tmp_path / "decisions.csv", dtype=str, keep_default_na=False)
    assert list(d.decision_id) == ["RULE_B:2026"]
    d["horizon"] = "after the last regular-season kickoff of 2026"                     # a later rewording
    d.to_csv(tmp_path / "decisions.csv", index=False)
    out = part(score(tmp_path, good, gg + filler(2026), "2027-01-21", "--test-record"), *RB)
    assert "recorded in decisions.csv on 2027-01-20T00:00:00Z" in out
    assert len(pd.read_csv(tmp_path / "decisions.csv")) == 1
    assert "`RULE_B:2026`" in section(3) and "never by the wording of its label" in section(3)


def test_reading_9_a_postponed_game_that_signals_again_is_two_listings(tmp_path):
    """The final review's m11: a game postponed two days and signalled again on its new date was never a bet (the
    first signal was void and the second was dropped as a repeat)."""
    rows = [row("P", "2026-10-11", snap="2026-10-09T15:00:00Z"),                          # for Sunday ...
            row("P", "2026-10-13", time="20:15", snap="2026-10-12T15:00:00Z", total_line=41.0)]   # ... then Tuesday
    out = part(score(tmp_path / "p", rows, [game("P", "2026-10-13", time="20:15", week=5)], "2026-10-20"), *RB)
    assert "2 signals, 1 settled, 0 pending, 1 void (not graded)" in out
    assert "void, the game kicked off more than 24 hours from the kickoff on its entry row: 1 (P)" in out
    assert "record at entry line 1-0-0" in out and " 41.0 " in out
    # two listings both within 24 hours of the actual kickoff: the nearer one is graded
    rows = [row("Q", "2026-10-18", snap="2026-10-16T15:00:00Z", total_line=44.0),                # Sunday 1:00 PM
            row("Q", "2026-10-19", time="16:00", snap="2026-10-17T15:00:00Z", total_line=45.0)]  # 27 hours later
    out = part(score(tmp_path / "q", rows, [game("Q", "2026-10-19", time="02:00", week=6)], "2026-10-25"), *RB)
    assert "2 signals, 1 settled, 0 pending, 1 void (not graded)" in out
    assert "void, another listing of this game is nearer its actual kickoff: 1 (Q)" in out and " 44.0 " in out
    assert "is two listings" in section(9)


def test_reading_11_fewer_than_20_closes_make_a_decision_inconclusive(tmp_path):
    rows, games = season(2026, list(range(5, 19)), 40)
    for i, r in enumerate(rows):
        r["total_line"] = 43.0 if i % 2 == 0 else 42.5
    for g_ in games[:25]:
        g_["total_line"] = np.nan                                                        # no primary close
    out = part(score(tmp_path, rows, games + filler(2026), "2027-01-20"), *RB)
    assert ("FINAL: INCONCLUSIVE (only 15 of the 40 bets have a primary close, fewer than 20; carried into 2027 "
            "unchanged)") in out
    assert "25 of the 40 bets have no primary close" in out
    assert "fewer than 20 of the bets in a decision have a primary close" in section(11)


def norm(text):
    return " ".join(text.replace("**", "").replace("`", "").split())


def test_amendment_6_names_every_earlier_sentence_it_replaces():
    """The final review's m12: section 6 changed amendment 5's "decided once" without naming it, and four more
    pairs elsewhere. Every sentence quoted as replaced must be quoted exactly."""
    whole = (ROOT / "PREREGISTRATION.md").read_text()
    earlier = norm(whole.split("## Amendment 6 ")[0])
    replaces = amendment(6).split("### What this amendment replaces")[1]
    quotes = re.findall(r'"([^"]+)"', replaces)
    assert len(quotes) >= 8
    for q in quotes:
        assert norm(q) in earlier, q
    six = section(6)
    assert "second look at overlapping data" in six and 'amendment 5, section 4\'s "The decision is made once."' in six


def test_amendment_6_tests_nothing_and_leaves_the_count_unchanged():
    """The final review's M3: the new text said the count stays 200 (bar p < 0.00025); it was 271 at merge."""
    text = norm(amendment(6))
    assert "stays 200" not in text and "0.00025" not in text
    assert "test nothing and leave the running variant count unchanged" in text
    assert "271" in text and "p < 0.000185" in text
    assert "now 200 variants" not in (ROOT / "STRATEGY.md").read_text()


def test_the_readme_keeps_its_original_sentence_and_adds_a_dated_note():
    """The final review: a sentence inside the README's historical section was reworded instead of superseded."""
    readme = (ROOT / "README.md").read_text()
    assert ("A decision uses only the bets that kicked off by its horizon, so it can't change later. Before the horizon "
            "the scorer prints the numbers and no verdict.") in readme
    assert "*Note, Sep 29 (amendment 6):*" in readme


# ================================================================== the second review of this amendment (Sep 29)
def test_reading_3_a_record_cut_inside_its_last_field_is_damaged_and_never_added_to(tmp_path):
    """The second review's major finding: a record cut inside its fingerprint (and its line break) read as whole;
    the lean's decision was then glued onto it, and later runs recorded decisions a second time."""
    rb_rows, g1 = season(2026, list(range(5, 19)), 40, line=43.0)
    leans, g2 = season(2026, list(range(5, 19)), 40, first_id=200, line=43.0, lean="UNDER lean")
    games = g1 + g2 + filler(2026)
    score(tmp_path / "ok", rb_rows, games, "2027-01-20", "--test-record")
    whole = (tmp_path / "ok" / "decisions.csv").read_text()
    head, line = whole.splitlines()
    cut = {"cut": whole[:-20],                                                  # no line break, fingerprint cut
           "short": f"{head}\n{line[:-20]}\n",                                  # a line break, fingerprint cut
           "nine": f"{head}\n{line.rsplit(',', 1)[0]}\n"}                       # the last field gone
    for name, content in cut.items():
        d = tmp_path / name
        d.mkdir()
        (d / "decisions.csv").write_text(content)
        out = score(d, rb_rows + leans, games, "2027-01-22", "--test-record")
        assert "Decision record: decisions.csv is unreadable" in out, name
        assert "model lean: 40 leans in 2026, decided after Week 18 of 2026), FINAL: KEEP" in out, name
        assert out.count("not recorded: the decision record is unreadable") == 2, name
        assert "recorded in decisions.csv on" not in out, name
        assert (d / "decisions.csv").read_text() == content, name
    assert "a line without exactly its 10 fields" in section(3) and "It never adds a line" in section(3)


def test_reading_3_a_damaged_copy_on_the_ledgers_branch_stops_recording(tmp_path):
    """The second review: the local record was damaged, the nightly copy took the damage, the damaged file was
    removed, and the next real run decided again (DROP after the recorded KEEP)."""
    good, gg = season(2026, list(range(5, 19)), 40, line=43.0)
    repo = tmp_path / "repo"
    proj = live_project(repo, "nfl-weather", good, gg + filler(2026), "2027-01-20T16:00")
    git(repo, "init", "-q")
    fwd, scorer = proj / "data" / "forward", proj / "scripts" / "score_forward.py"
    games = proj / "data" / "raw" / "games.csv"
    assert "FINAL: KEEP" in on_clock(tmp_path, "2027-01-20T17:00", scorer).stdout
    data = (fwd / "decisions.csv").read_bytes()
    pd.DataFrame([dict(x, total_line=46) for x in gg] + filler(2026)).to_csv(games, index=False)   # closes corrected
    for name, damaged in (("cut", data[: len(data) // 2 + 60]), ("empty", b"")):
        (tmp_path / name).write_bytes(damaged)
        publish(repo, "nfl-weather", tmp_path / name)                        # the nightly copy took the damage
        if (fwd / "decisions.csv").exists():
            (fwd / "decisions.csv").unlink()                                  # the damaged file is removed
        touch(games, "2027-01-22T16:00")
        out = on_clock(tmp_path, "2027-01-22T17:00", scorer).stdout
        assert "its copy on the ledgers branch (origin/ledgers:nfl-weather/decisions.csv) is unreadable" in out, name
        assert "git log origin/ledgers -- nfl-weather/decisions.csv" in out, name
        rb = part(out, *RB)
        assert "FINAL: DROP" in rb and "not recorded: the decision record is missing and its copy" in rb, name
        assert not (fwd / "decisions.csv").exists(), name
    assert "A copy that is there but can't be read" in section(3) and "counts as no copy" not in section(3)


def test_reading_3_while_the_record_is_missing_every_run_on_the_live_ledger_prints_its_copy(tmp_path):
    """The second review: with the record lost and the schedule 3 days old, the daily run printed a fresh FINAL:
    DROP against the recorded KEEP and never mentioned the copy; so did a worker's scorer on the live ledger."""
    good, gg = season(2026, list(range(5, 19)), 40, line=43.0)
    repo = tmp_path / "repo"
    proj = live_project(repo, "nfl-weather", good, gg + filler(2026), "2027-01-20T16:00")
    git(repo, "init", "-q")
    fwd, scorer = proj / "data" / "forward", proj / "scripts" / "score_forward.py"
    games = proj / "data" / "raw" / "games.csv"
    assert "FINAL: KEEP" in on_clock(tmp_path, "2027-01-20T17:00", scorer).stdout
    publish(repo, "nfl-weather", fwd / "decisions.csv")
    (fwd / "decisions.csv").unlink()
    pd.DataFrame([dict(x, total_line=46) for x in gg] + filler(2026)).to_csv(games, index=False)
    touch(games, "2027-01-19T16:00")                                          # 3 days old at the next run
    worker = project(repo / "worker", "nfl-weather")                          # a worker's copy of the scorer
    for script, args in ((scorer, ()), (worker / "scripts" / "score_forward.py",
                                        ("--ledger", str(fwd / "ledger.csv"), "--games", str(games)))):
        out = on_clock(tmp_path, "2027-01-22T17:00", script, *args).stdout
        assert "its copy on the ledgers branch (origin/ledgers:nfl-weather/decisions.csv) holds 1 recorded decision" in out
        rb = part(out, *RB)
        assert "FINAL: KEEP" in rb and "recorded in decisions.csv on 2027-01-20T17:00:00Z" in rb
        assert "read from its copy on the ledgers branch (the file is missing)" in rb
        assert "a fresh computation on the same horizon now gives: DROP" in rb and "FINAL: DROP" not in rb
        assert not (fwd / "decisions.csv").exists()                           # only a real run restores it
    touch(games, "2027-01-22T16:00")
    out = on_clock(tmp_path, "2027-01-22T18:00", scorer).stdout
    assert "restored 1 recorded decision from its copy on the ledgers branch" in out
    assert len(pd.read_csv(fwd / "decisions.csv")) == 1
    assert "prints its decisions as recorded, and leaves the file alone" in section(3)


def test_reading_3_a_record_whose_numbers_a_later_run_cant_print_is_damaged(tmp_path):
    """The second review: a record whose numbers were valid JSON without a key the scorer prints crashed the
    whole run (KeyError), so the day's report was lost. An id the scorer doesn't know is damage too: a hand edit
    left a space after RULE_B:2026, and the next run decided again."""
    good, gg = season(2026, list(range(5, 19)), 40, line=43.0)
    score(tmp_path / "ok", good, gg + filler(2026), "2027-01-20", "--test-record")
    rec = pd.read_csv(tmp_path / "ok" / "decisions.csv", dtype=str, keep_default_na=False)
    nums = json.loads(rec.numbers[0])
    nums["with_close"] = nums.pop("vs_close_no_tie")                          # an older name for the key
    for name, edited, why in (("key", rec.assign(numbers=json.dumps(nums)), "numbers have no vs_close_no_tie"),
                              ("id", rec.assign(decision_id="RULE_B:2026 "), "an unknown decision id")):
        d = tmp_path / name
        d.mkdir()
        edited.to_csv(d / "decisions.csv", index=False)
        pd.DataFrame(good).to_csv(d / "ledger.csv", index=False)
        pd.DataFrame(gg + filler(2026)).to_csv(d / "games.csv", index=False)
        r = run(ROOT / "scripts" / "score_forward.py", "--ledger", str(d / "ledger.csv"), "--games", str(d / "games.csv"),
                "--now", "2027-01-21", "--test-record")
        assert r.returncode == 0, (name, r.stderr[-400:])
        assert "Decision record: decisions.csv is unreadable" in r.stdout and why in r.stdout, name
        assert "RULE_B, secondary price" in r.stdout and "Variants under forward test" in r.stdout, name
        assert len(pd.read_csv(d / "decisions.csv")) == 1, name


def test_amendment_6_names_the_amendment_5_sentences_sections_1_and_6_change():
    """The second review: section 6 changes amendment 5's "If 40 Rule B signals settle ..." (and the lean's
    sentence), and section 1 its "It uses the bets that kicked off by its horizon.", and neither was named."""
    replaces = norm(amendment(6).split("### What this amendment replaces")[1])
    for quote in ("If 40 Rule B signals settle in the 2026 regular season, the decision is made after Week 18 of 2026 "
                  "on those bets.",
                  "with 40 leans in the 2026 regular season it is decided after Week 18 of 2026 on those leans, by half",
                  "It uses the bets that kicked off by its horizon.", "Keep using it only if all of these hold:"):
        assert f'"{quote}"' in replaces, quote


def test_the_summaries_say_a_record_lost_before_its_copy_can_be_decided_again():
    """The second review: STATUS, STRATEGY and the README promised "never decided again" without the amendment's
    limit (a record lost before its first nightly copy)."""
    caveat = "never decided again unless it is lost before that night's copy is made"
    for f in (ROOT / "STRATEGY.md", ROOT / "README.md"):
        assert caveat in f.read_text(), f.name
    assert "never decided again, unless it is lost before that night's copy is made" in (
        ROOT.parent / "STATUS.md").read_text()
    assert ("if it is lost before then, neither the file nor a copy holds it, and the next real run decides it "
            "again") in section(3)


# ================================================================== amendment 7 (Sep 29): the keep test and the record
def amendment7_section(n):
    return " ".join(amendment(7).split(f"### {n}.")[1].split("\n### ")[0].split())


REGISTERED_BY_HUB = ("Registered by the hub on the owner's standing instruction of September 29, 2026 (the hub decides "
                     "questions of how the tests are graded and reports them; money, and any rule's trigger, gate or "
                     "price cap, stay the owner's). The registering commit is the merge of pull request 64. The owner "
                     "can change any reading here by a dated amendment made before the first outcome it would affect.")


def replaced_sources(whole, strategy, amend):
    """Each bullet of an amendment's "What this amendment replaces": (its source's text, the sentences it quotes).
    A bullet names its source before the first quoted sentence: STRATEGY.md, the original file, or an amendment
    and, when given, its section."""
    out = []
    for bullet in amend.split("### What this amendment replaces")[1].split("\n* ")[1:]:
        label, rest = bullet.split(': "', 1)
        quotes = re.findall(r'"([^"]+)"', '"' + rest)
        if label.startswith("`STRATEGY.md`"):
            src = strategy
        elif label.startswith("The original file"):
            src = whole.split("## Amendment 1 ")[0]
        else:
            m = re.match(r"Amendment (\d+)(?:, section (\d+))?", label)
            src = whole.split(f"## Amendment {m[1]} ")[1].split("\n## ")[0]
            if m[2]:
                src = src.split(f"### {m[2]}.")[1].split("\n### ")[0]
        out.append((label, norm(src), quotes))
    return out


def test_amendment_7_is_registered_as_the_hub_was_told_and_names_what_it_replaces():
    text = norm(amendment(7))
    assert REGISTERED_BY_HUB in text
    assert "No trigger, gate, price cap or stake changes." in text and "The rules version stays v3-2026-09-28" in text
    assert "on the day of registration it is 273, so the multiple-testing bar is p < 0.000183" in text
    whole = (ROOT / "PREREGISTRATION.md").read_text()
    earlier = whole.split("## Amendment 7 ")[0]
    sources = replaced_sources(earlier, (ROOT / "STRATEGY.md").read_text(), amendment(7))
    assert len(sources) >= 8
    for label, src, quotes in sources:
        assert quotes, label
        for q in quotes:
            assert norm(q) in src, (label, q)
    one = amendment7_section(1)
    for words in ("5.8% of the time at 17 signals a season and 7.4% at 25 (plain 8.0% and 10.3%; grouped 6.4% and "
                  "8.1%)", "40,000 simulated paths per case", "6.5% of the time at 17 signals a season and 8.4% at 25",
                  "1.4% and 1.4% (plain 2.1% and 2.1%; grouped 2.0% and 2.0%)", "the owner has not chosen a gate",
                  "one or two seasons can't measure a season-wide swing", "0 variants",
                  "Until now the scorer computed the plain interval as m plus or minus 1.96 x s / sqrt(n)"):
        assert words in one, words
    two = amendment7_section(2)
    assert "the first in the feed is taken" in two and "none is taken" in two and "within 6 hours" in two
    assert "the run ends cleanly" in two and "byte-identical" in two
    # "listing" is amendment 6's word for a group of ledger rows; a thing in the odds feed is a feed event
    assert "A **feed event** is one event in the odds feed" in amendment(7) and two.count("listing") == 1
    assert "It is not a listing in the sense of amendment 6, section 9" in two
    assert '("returned no events", or "returned k events, none priced by any logged book")' in two
    hub = (ROOT.parent / ".claude" / "commands" / "hub.md").read_text()
    assert "run `git fetch` in `~/code/value-finder` first" in hub


def test_the_summaries_name_amendment_7():
    strategy = (ROOT / "STRATEGY.md").read_text()
    assert ("*Amendment 7 (Sep 29):* the 95% interval is the wider of the plain interval and one grouped by game day"
            in strategy)
    # amendment 6's dated note is left as written, and a new dated note after it says the copy never loses a line
    old = "never decided again unless it is lost before that night's copy is made (3)"
    new = ("never decided again unless it is lost before any nightly copy has published it. Normally that means "
           "recorded and lost on the same day; while the nightly copy holds the record back because a published "
           "line in it has changed, it means any decision recorded until the hub puts that line back (section 3)")
    assert old in strategy and new in strategy and strategy.index(old) < strategy.index(new)
    status = (ROOT.parent / "STATUS.md").read_text()
    assert "nfl-weather amendment 7 and cfb-weather amendment 5" in status
    assert status.count("the college football one until Thu Oct 1, 5:00 PM Pacific; the NFL one until Thu Oct 8") == 2
    assert "the NFL 5.8 to 7.4% (8.0 to 10.3% and 6.4 to 8.1%), and 6.5 to 8.4% for its two looks together" in status
    assert "**The published copy never loses a line:**" in status and "as long as the copy still holds it" not in status
    readme = (ROOT.parent / "strategy-research" / "README.md").read_text()
    assert "### The keep test: plain, grouped by game day, and the wider of the two (added September 29, 2026)" in (
        readme)
    assert ("| NFL, 17 / 25 | realistic (same day 0.07, same season 0.06) | 8.0 / 10.3% | 6.4 / 8.1% | 5.8 / 7.4% |"
            in readme)
    assert "the running count stays at 200." in readme                     # the study's text is left as written
    assert "*Note, Sep 29, 2026:* when this study merged, the running count was **271**" in readme
    for f in (ROOT / "README.md", ROOT.parent / "STATUS.md"):
        text = f.read_text()
        assert "feed listing" not in text and "One listing per game" not in text, f.name
        assert "one feed event" in text and "the copy protects a lost line only until" not in text.lower(), f.name
    log = (ROOT.parent / "strategy-research" / "output" / "keep_test_check.log").read_text()
    assert "NFL Rule B, realistic dependence: wider 5.8 to 7.4% (plain 8.0 to 10.3%, grouped 6.4 to 8.1%)" in log
    assert "NFL two looks, 17 signals a season, realistic dependence: wider 6.5%" in log


def by_hand(clv, days):
    """The registered interval computed here from its definition (amendment 7, reading 1), not with the scorer's
    code: the plain mean m of the n CLVs; the plain half-width t(0.975, n - 1) x sd / sqrt(n); G game days, s_g the
    sum of (CLV - m) over day g, the grouped half-width t(0.975, G - 1) x sqrt((G / (G - 1)) x sum(s_g^2) / n^2);
    the interval m plus or minus the larger half-width, none with fewer than 2 game days."""
    from scipy import stats
    x, d = np.asarray(clv, float), np.asarray(days, object)
    x, d = x[~np.isnan(x)], d[~np.isnan(x)]
    n, m = len(x), x.mean()
    labels = sorted(set(d))
    G = len(labels)
    s = np.array([(x[d == g] - m).sum() for g in labels])
    plain = stats.t.ppf(0.975, n - 1) * x.std(ddof=1) / np.sqrt(n)
    grouped = stats.t.ppf(0.975, G - 1) * np.sqrt(G / (G - 1) * (s ** 2).sum() / n ** 2) if G > 1 else np.nan
    half = max(plain, grouped) if G > 1 else np.nan
    return dict(mean_clv=m, ci_low=m - half, ci_high=m + half, n_clv=n, game_days=G, plain_half_width=plain,
                grouped_half_width=grouped)


def printed(want):
    """The line the scorer prints for an interval: the registered one, which of the two it is, and both."""
    m, g, p, G = want["mean_clv"], want["grouped_half_width"], want["plain_half_width"], want["game_days"]
    both_g, both_p = f"grouped {m - g:+.2f} to {m + g:+.2f}", f"plain {m - p:+.2f} to {m + p:+.2f}"
    which = (f"the two are equally wide, over {G} game days ({both_g}; {both_p})" if np.isclose(g, p, rtol=1e-9) else
             f"the wider is the grouped one, over {G} game days ({both_g}; {both_p})" if g > p else
             f"the wider is the plain one ({both_p}; {both_g}, over {G} game days)")
    return f"95% CI {want['ci_low']:+.2f} to {want['ci_high']:+.2f}; {which}"


def keep_case(bets):
    """40 Rule B bets from (game id, Eastern date, Eastern time, week, entry line, close or nan, final total): the
    ledger rows, the schedule (with the 2026 regular season around them), and each bet's CLV."""
    rows = [row(gid, day, time, total_line=line) for gid, day, time, wk, line, close, total in bets]
    games = [game(gid, day, time, week=wk, total=total, close=close) for gid, day, time, wk, line, close, total in bets]
    clv = [line - close for gid, day, time, wk, line, close, total in bets]
    return rows, games + filler(2026), clv


def lines_for(k):
    """Entry lines that give varied CLVs against a close of 42, some of them equal."""
    return [42 + ((7 * i) % 11 - 3) * 0.5 for i in range(k)]


def eastern_utc(day, time):
    return pd.Timestamp(f"{day} {time}").tz_localize("America/New_York").tz_convert("UTC")


def test_amendment_7_reading_1_the_keep_interval_is_the_wider_of_two(tmp_path):
    """Recomputed here from the registered definition on 1, 2, 5, 20 and 40 game days, with ties with the close, bets
    with no close, and a late Saturday game (8:15 PM Eastern, 01:15 UTC Sunday) that groups with Saturday. The
    grouped half-width is the wider in some cases and the plain one in others; with one bet per game day they are
    equally wide."""
    line = lines_for(40)
    late = ([("2026-12-19", "16:30")] * 6 + [("2026-12-19", "20:15")] * 4 + [("2026-12-20", "13:00")] * 12
            + [("2026-12-21", "20:15")] * 6 + [("2026-12-24", "20:15")] * 4 + [("2026-12-27", "13:00")] * 8)
    cases = {
        "one day": [(f"A{i}", "2026-10-11", "13:00", 5, line[i], 42, 40) for i in range(40)],
        "two days": [(f"B{i}", "2026-10-11" if i < 20 else "2026-10-18", "13:00", 5 if i < 20 else 6, line[i],
                      np.nan if i in (3, 17, 30) else 42, 42 if i in (5, 25) else 40) for i in range(40)],
        "five days, late Saturday": [(f"C{i}", day, time, 15 if day < "2026-12-21" else 16, line[i],
                                      np.nan if i in (0, 9) else 42, 42 if i == 4 else 40)
                                     for i, (day, time) in enumerate(late)],
        "twenty days": [(f"D{i}", wk_day(2026, 5 + i // 4) if i % 4 < 2 else
                         (pd.Timestamp(wk_day(2026, 5 + i // 4)) + pd.Timedelta(days=1)).strftime("%Y-%m-%d"),
                         "13:00" if i % 4 < 2 else "20:15", 5 + i // 4, line[i], np.nan if i == 11 else 42, 40)
                        for i in range(40)],
        "forty days, one bet each": [(f"E{i}", (pd.Timestamp("2026-10-11") + pd.Timedelta(days=2 * i)).strftime(
            "%Y-%m-%d"), "13:00", 5 + (2 * i) // 7, line[i], 42, 40) for i in range(40)],
    }
    wider = {}
    for name, bets in cases.items():
        rows, games, clv = keep_case(bets)
        d = tmp_path / name.replace(" ", "_").replace(",", "")
        out = part(score(d, rows, games, "2027-01-20", "--test-record"), *RB)
        nums = json.loads(pd.read_csv(d / "decisions.csv", dtype=str).numbers[0])
        want = by_hand(clv, [b[1] for b in bets])                     # the Eastern date of each game's kickoff
        assert (nums["game_days"], nums["n_clv"]) == (want["game_days"], want["n_clv"]), name
        for k in ("mean_clv", "plain_half_width"):
            assert np.isclose(nums[k], want[k], rtol=1e-12, atol=1e-12), (name, k)
        if want["game_days"] < 2:
            assert nums["ci_low"] is None and nums["ci_high"] is None and nums["grouped_half_width"] is None, name
            assert ("FINAL: INCONCLUSIVE (the 40 bets that have a primary close kicked off on 1 game day, so there is "
                    "no interval; carried into 2027 unchanged)") in out, name
            assert "no interval: the bets with a primary close kicked off on 1 game day" in out, name
            continue
        for k in ("ci_low", "ci_high", "grouped_half_width"):
            assert np.isclose(nums[k], want[k], rtol=1e-12, atol=1e-12), (name, k)
        assert np.isclose(nums["ci_high"] - nums["mean_clv"], max(nums["plain_half_width"],
                                                                  nums["grouped_half_width"]), rtol=1e-12), name
        assert printed(want) in out, (name, printed(want))
        wider[name] = ("equal" if np.isclose(want["grouped_half_width"], want["plain_half_width"], rtol=1e-9) else
                       "grouped" if want["grouped_half_width"] > want["plain_half_width"] else "plain")
    assert wider == {"two days": "grouped", "five days, late Saturday": "plain", "twenty days": "plain",
                     "forty days, one bet each": "equal"}
    # the late Saturday game is Sunday in UTC, where it would join Sunday's games and change the interval
    bets = cases["five days, late Saturday"]
    clv, utc = keep_case(bets)[2], [eastern_utc(b[1], b[2]).strftime("%Y-%m-%d") for b in bets]
    assert [utc[i] for i in (6, 10)] == ["2026-12-20", "2026-12-20"] and bets[6][1] == "2026-12-19"
    eastern_days = [b[1] for b in bets]
    assert not np.isclose(by_hand(clv, utc)["grouped_half_width"], by_hand(clv, eastern_days)["grouped_half_width"])
    text = amendment7_section(1)
    for words in ("THE REGISTERED INTERVAL IS", "the larger of the two half-widths", "(G / (G - 1))",
                  "Student's t with n - 1 degrees of freedom", "Student's t with G - 1 degrees of freedom",
                  "fewer than 2 game days, or fewer than 2 bets", "the wider is the grouped one, over G game days"):
        assert words.lower() in text.lower(), words


def test_amendment_7_reading_1_the_lean_and_the_interim_read_use_the_wider_interval_too(tmp_path):
    """Every CLV decision goes through the same test: the model lean's pooled decision is checked here, and the
    interim read shows the registered interval."""
    a, ga = season(2026, list(range(5, 19)), 25, lean="UNDER lean")
    b, gb = season(2027, list(range(1, 11)), 15, first_id=100, lean="UNDER lean")
    for i, r in enumerate(a + b):
        r["total_line"] = lines_for(40)[i]
    out = score(tmp_path / "lean", a + b, ga + gb + filler(2026) + filler(2027), "2028-01-20", "--test-record")
    nums = json.loads(pd.read_csv(tmp_path / "lean" / "decisions.csv", dtype=str).numbers[0])
    want = by_hand([r["total_line"] - 42 for r in a + b], [r["gameday"] for r in a + b])
    assert nums["game_days"] == want["game_days"] == 24
    assert np.isclose(nums["ci_low"], want["ci_low"], rtol=1e-12) and printed(want) in out
    early = part(score(tmp_path / "interim", a, ga + filler(2026, played=False), "2026-12-01"), *LEAN)
    assert "INTERIM read" in early and "95% CI" in early and "the wider is the" in early


def test_amendment_7_reading_3_a_time_with_no_time_zone_is_damage_not_a_crash(tmp_path):
    """The second review of amendment 6 (its r2naive): a recorded time re-saved without its 'Z' passed the checks
    and crashed the whole run with TypeError, so the day's report was lost."""
    good, gg = season(2026, list(range(5, 19)), 40, line=43.0)
    score(tmp_path, good, gg + filler(2026), "2027-01-20", "--test-record")
    rec = pd.read_csv(tmp_path / "decisions.csv", dtype=str, keep_default_na=False)
    for col, naive in (("horizon_utc", "2027-01-10T18:00:00"), ("decided_utc", "2027-01-20 00:00:00")):
        rec.assign(**{col: naive}).to_csv(tmp_path / "decisions.csv", index=False)
        before = (tmp_path / "decisions.csv").read_text()
        r = run(ROOT / "scripts" / "score_forward.py", "--ledger", str(tmp_path / "ledger.csv"), "--games",
                str(tmp_path / "games.csv"), "--now", "2027-01-21", "--test-record")
        assert r.returncode == 0, (col, r.stderr[-400:])
        assert "Decision record: decisions.csv is unreadable (ValueError: a time with no time zone" in r.stdout, col
        assert "RULE_B, secondary price" in r.stdout and "Variants under forward test" in r.stdout, col
        assert (tmp_path / "decisions.csv").read_text() == before, col
    assert "a record whose time cannot be read as a UTC time is a damaged record" in amendment7_section(3)


def test_amendment_7_reading_3_a_damaged_record_still_prints_the_decisions_it_can(tmp_path):
    """The second review of amendment 6 (its r2probe T2): a second record line was cut mid-write and the closes
    were corrected; the next run printed a fresh FINAL: DROP and never showed the recorded KEEP."""
    good, gg = season(2026, list(range(5, 19)), 40, line=43.0)                # CLV +1 each: KEEP
    score(tmp_path, good, gg + filler(2026), "2027-01-20", "--test-record")
    whole = (tmp_path / "decisions.csv").read_text()
    (tmp_path / "decisions.csv").write_text(whole + "MODEL_LEAN:2026,model lean,after Week 18 of 2026,2027-01-1")
    before = (tmp_path / "decisions.csv").read_text()
    corrected = [dict(g_, total_line=46) for g_ in gg] + filler(2026)          # a fresh computation: DROP
    out = score(tmp_path, good, corrected, "2027-01-22", "--test-record")
    assert "Decision record: decisions.csv is unreadable" in out
    assert "1 recorded decision in it can still be read (RULE_B:2026) and is printed below as recorded." in out
    rb = part(out, *RB)
    assert "decided after Week 18 of 2026), FINAL: KEEP" in rb
    assert "recorded in decisions.csv on 2027-01-20T00:00:00Z" in rb
    assert "the file is damaged, and this record can still be read" in rb
    assert "a fresh computation on the same horizon now gives: DROP" in rb and "FINAL: DROP" not in rb
    assert "The recorded decision stands." in rb
    assert (tmp_path / "decisions.csv").read_text() == before                  # nothing is added to a damaged file
    assert "any decision in it that can still be read is still printed as recorded" in amendment7_section(3)


def test_amendment_7_reading_3_a_decision_missing_from_the_file_is_restored_from_the_copy(tmp_path):
    """The second review of amendment 6 (its r2probe T3): the record was cut back to its header while the file
    stayed, the closes were corrected, and the next real run decided DROP although the copy held KEEP."""
    good, gg = season(2026, list(range(5, 19)), 40, line=43.0)
    repo = tmp_path / "repo"
    proj = live_project(repo, "nfl-weather", good, gg + filler(2026), "2027-01-20T16:00")
    git(repo, "init", "-q")
    fwd, scorer = proj / "data" / "forward", proj / "scripts" / "score_forward.py"
    games = proj / "data" / "raw" / "games.csv"
    assert "FINAL: KEEP" in on_clock(tmp_path, "2027-01-20T17:00", scorer).stdout
    publish(repo, "nfl-weather", fwd / "decisions.csv")                       # the nightly copy holds KEEP
    whole = (fwd / "decisions.csv").read_text()
    head = whole.splitlines()[0] + "\n"
    (fwd / "decisions.csv").write_text(head)                                  # the file stays; its record is gone
    pd.DataFrame([dict(x, total_line=46) for x in gg] + filler(2026)).to_csv(games, index=False)   # closes corrected
    touch(games, "2027-01-19T16:00")                                          # stale: this run may not record
    out = on_clock(tmp_path, "2027-01-22T17:00", scorer).stdout
    assert ("data/forward/decisions.csv doesn't hold 1 recorded decision that its copy on the ledgers branch "
            "(origin/ledgers:nfl-weather/decisions.csv) holds (RULE_B:2026), printed below as recorded") in out
    rb = part(out, *RB)
    assert "FINAL: KEEP" in rb and "read from its copy on the ledgers branch (the file is missing it)" in rb
    assert "FINAL: DROP" not in rb and (fwd / "decisions.csv").read_text() == head
    touch(games, "2027-01-22T16:00")                                          # a real run restores it
    out = on_clock(tmp_path, "2027-01-22T18:00", scorer).stdout
    assert ("data/forward/decisions.csv was missing 1 recorded decision that its copy on the ledgers branch "
            "(origin/ledgers:nfl-weather/decisions.csv) holds (RULE_B:2026); restored from the copy") in out
    rb = part(out, *RB)
    assert "FINAL: KEEP" in rb and "recorded in decisions.csv on 2027-01-20T17:00:00Z" in rb
    assert "restored from the ledgers branch" in rb and "a fresh computation on the same horizon now gives: DROP" in rb
    assert (fwd / "decisions.csv").read_text() == whole                        # the copy's line, as it was written
    # a damaged file whose record can't be read, while the copy holds it: printed from the copy, the file left alone
    cut = head + whole.splitlines()[1][:60] + "\n"
    (fwd / "decisions.csv").write_text(cut)
    out = on_clock(tmp_path, "2027-01-22T19:00", scorer).stdout
    assert "No recorded decision in it can still be read." in out
    rb = part(out, *RB)
    assert "FINAL: KEEP" in rb and "read from its copy on the ledgers branch (the file is damaged)" in rb
    assert "FINAL: DROP" not in rb and (fwd / "decisions.csv").read_text() == cut
    assert "is restored from the copy, never decided again" in amendment7_section(3)


# ================================================================== the review of pull request 64 (Sep 29)
# The fourth review: the nightly copy keeps a damaged published copy, so the scorer no longer says that the nightly
# copy repairs it; it says this, as section 3, hub.md and ops/RUN_RECORDS.md do
HUB_REPLACES = ("the hub replaces a damaged published copy by hand with a commit to the ledgers branch, and recording "
                "resumes once the copy can be read")


def test_amendment_7_reading_3_a_damaged_copy_stops_recording_and_shows_what_it_can(tmp_path):
    """The review of pull request 64 (its rec_probe c3 and c4): the copy's first record line could be read and the
    line after it was cut. With the file present but missing that decision, the next real run decided it again
    (DROP after the recorded KEEP) and said nothing about the copy; with the file missing, it printed a fresh DROP.
    A damaged copy stops recording (amendment 6, section 3) whether or not the file is there."""
    good, gg = season(2026, list(range(5, 19)), 40, line=43.0)                # CLV +1 each: KEEP
    repo = tmp_path / "repo"
    proj = live_project(repo, "nfl-weather", good, gg + filler(2026), "2027-01-20T16:00")
    git(repo, "init", "-q")
    fwd, scorer = proj / "data" / "forward", proj / "scripts" / "score_forward.py"
    games = proj / "data" / "raw" / "games.csv"
    assert "FINAL: KEEP" in on_clock(tmp_path, "2027-01-20T17:00", scorer).stdout
    whole = (fwd / "decisions.csv").read_text()
    head, line = whole.splitlines()
    (tmp_path / "damaged.csv").write_text(f"{head}\n{line}\n{line[:40]}")    # the copy's last line was cut
    publish(repo, "nfl-weather", tmp_path / "damaged.csv")
    pd.DataFrame([dict(x, total_line=46) for x in gg] + filler(2026)).to_csv(games, index=False)   # closes corrected
    touch(games, "2027-01-22T16:00")
    unreadable = "its copy on the ledgers branch (origin/ledgers:nfl-weather/decisions.csv) is unreadable"
    for name, content, why in (
            ("the file lost it", head + "\n",
             "the file is missing it; the copy is damaged, and this line of it can still be read"),
            ("the file is missing", None,
             "the file is missing, and the copy is damaged; this line of it can still be read")):
        if content is None:
            (fwd / "decisions.csv").unlink()
        else:
            (fwd / "decisions.csv").write_text(content)
        out = on_clock(tmp_path, "2027-01-22T17:00", scorer).stdout
        assert unreadable in out and "1 recorded decision in the copy can still be read (RULE_B:2026)." in out, name
        assert HUB_REPLACES in out and "does that" not in out and "before the nightly copy" not in out, name
        if content is not None:
            assert "before the hub replaces the damaged copy by hand, after which the copy no longer holds it" in out
        rb = part(out, *RB)
        assert "FINAL: KEEP" in rb and "recorded in decisions.csv on 2027-01-20T17:00:00Z" in rb, name
        assert f"read from its copy on the ledgers branch ({why})" in rb, name
        assert "a fresh computation on the same horizon now gives: DROP" in rb and "FINAL: DROP" not in rb, name
        if content is None:
            assert not (fwd / "decisions.csv").exists(), name               # nothing restored from a damaged copy
        else:
            assert (fwd / "decisions.csv").read_text() == content, name
    # the file is whole again, the copy still damaged, and the model lean's decision is final: it is not recorded
    leans, gl = season(2026, list(range(5, 19)), 40, first_id=200, line=43.0, lean="UNDER lean")
    pd.DataFrame(good + leans).to_csv(fwd / "ledger.csv", index=False)
    pd.DataFrame([dict(x, total_line=46) for x in gg] + gl + filler(2026)).to_csv(games, index=False)
    touch(games, "2027-01-22T16:00")
    (fwd / "decisions.csv").write_text(whole)
    out = on_clock(tmp_path, "2027-01-22T18:00", scorer).stdout
    assert unreadable in out and "Nothing will be recorded until the copy can be read again" in out
    lean = part(out, *LEAN)
    assert "FINAL: KEEP" in lean and "not recorded: its copy on the ledgers branch is unreadable" in lean
    assert f"not recorded: its copy on the ledgers branch is unreadable; {HUB_REPLACES}." in lean
    assert (fwd / "decisions.csv").read_text() == whole
    publish(repo, "nfl-weather", fwd / "decisions.csv")                       # the nightly copy of the whole file
    out = on_clock(tmp_path, "2027-01-22T19:00", scorer).stdout
    assert unreadable not in out and "recorded in decisions.csv on 2027-01-22T19:00:00Z" in part(out, *LEAN)
    text = amendment7_section(3)
    assert "amendment 6's rule for a damaged copy applies whether or not the file is there" in text
    assert "it is not restored from a damaged copy" in text


def nightly(tmp_path, repo):
    """The real nightly copy: ops/sync_ledgers.sh run for `repo`, whose origin is a local bare repository, with HOME
    (and so the script's own clone) inside tmp_path; then `git fetch`, as the hub's check-in runs before the
    scorers. Returns the script's printout."""
    remote = tmp_path / "remote.git"
    env = dict(os.environ, HOME=str(tmp_path / "home"), GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull,
               GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")
    if not remote.exists():
        subprocess.run(["git", "init", "-q", "--bare", str(remote)], check=True, env=env)
        subprocess.run(["git", "-C", str(repo), "remote", "add", "origin", str(remote)], check=True, env=env)
        (repo / "ops").mkdir(exist_ok=True)
        shutil.copy(ROOT.parent / "ops" / "sync_ledgers.sh", repo / "ops")
        for p in ("nfl-weather", "cfb-weather"):                     # the script copies both projects' ledgers
            ledger = repo / p / "data" / "forward" / "ledger.csv"
            if not ledger.exists():
                ledger.parent.mkdir(parents=True)
                ledger.write_text("snapshot_utc\n")
    r = subprocess.run(["bash", str(repo / "ops" / "sync_ledgers.sh")], capture_output=True, text=True, env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    subprocess.run(["git", "-C", str(repo), "fetch", "-q", "origin"], check=True, env=env)
    return r.stdout


def test_amendment_7_reading_3_a_line_lost_after_the_check_in_survives_the_nightly_copy(tmp_path):
    """The reviews of pull request 64 (their rec_probe2): a line lost after the morning check-in was published with
    the shortened file that night, the copy no longer held it, and the next real run decided it again (DROP after
    the recorded KEEP). The nightly copy now never publishes a file that has lost a published line, so the next real
    run restores it from the copy; once the file holds every published line again, the nightly copy publishes it."""
    good, gg = season(2026, list(range(5, 19)), 40, line=43.0)                # CLV +1 each: KEEP
    repo = tmp_path / "repo"
    proj = live_project(repo, "nfl-weather", good, gg + filler(2026), "2027-01-20T16:00")
    git(repo, "init", "-q")
    fwd, scorer = proj / "data" / "forward", proj / "scripts" / "score_forward.py"
    games = proj / "data" / "raw" / "games.csv"
    assert "FINAL: KEEP" in on_clock(tmp_path, "2027-01-20T17:00", scorer).stdout      # day 1: the check-in records
    whole = (fwd / "decisions.csv").read_text()
    assert "not published" not in nightly(tmp_path, repo)                     # day 1, 11:45 PM: the copy holds it
    (fwd / "decisions.csv").write_text(whole.splitlines()[0] + "\n")          # day 2, after the check-in: lost
    out = nightly(tmp_path, repo)                                             # day 2, 11:45 PM
    assert ("nfl-weather: decisions.csv not published (it has lost or changed a line that the published copy "
            "holds); the published copy is kept as it is") in out
    assert git(repo, "show", "origin/ledgers:nfl-weather/decisions.csv") + "\n" == whole
    pd.DataFrame([dict(x, total_line=46) for x in gg] + filler(2026)).to_csv(games, index=False)   # closes corrected
    touch(games, "2027-01-22T16:00")
    out = on_clock(tmp_path, "2027-01-22T17:00", scorer).stdout               # day 3: the check-in
    assert "restored from the copy. A lost record is never decided again." in out
    rb = part(out, *RB)
    assert "FINAL: KEEP" in rb and "recorded in decisions.csv on 2027-01-20T17:00:00Z" in rb and "FINAL: DROP" not in rb
    assert (fwd / "decisions.csv").read_text() == whole
    assert "not published" not in nightly(tmp_path, repo)                     # day 3, 11:45 PM: published again
    text = amendment7_section(3)
    assert "the published copy never loses a line" in text.lower()
    assert "a decision that was ever published is never decided again" in text
    assert ("The one case left is a decision recorded since the last nightly copy that published the file and "
            "lost before the next one") in text


def test_amendment_7_reading_3_a_restore_appends_the_copy_s_own_line(tmp_path):
    """A restored line is the copy's line byte for byte, so the file again holds every published line and the next
    nightly copy publishes it. Before, the scorer wrote the decision out again, and a copy line written another way
    (every field quoted, say, by a hand repair) came back different: the nightly copy would then never publish."""
    good, gg = season(2026, list(range(5, 19)), 40, line=43.0)
    repo = tmp_path / "repo"
    proj = live_project(repo, "nfl-weather", good, gg + filler(2026), "2027-01-20T16:00")
    git(repo, "init", "-q")
    fwd, scorer = proj / "data" / "forward", proj / "scripts" / "score_forward.py"
    games = proj / "data" / "raw" / "games.csv"
    assert "FINAL: KEEP" in on_clock(tmp_path, "2027-01-20T17:00", scorer).stdout
    head, line = (fwd / "decisions.csv").read_text().splitlines()
    quoted = io.StringIO()
    csv.writer(quoted, quoting=csv.QUOTE_ALL, lineterminator="\n").writerow(next(csv.reader([line])))
    (tmp_path / "copy.csv").write_text(f"{head}\n{quoted.getvalue()}")
    assert quoted.getvalue() != line + "\n"
    publish(repo, "nfl-weather", tmp_path / "copy.csv")
    (fwd / "decisions.csv").write_text(head + "\n")                           # the file lost it
    touch(games, "2027-01-22T16:00")
    out = on_clock(tmp_path, "2027-01-22T17:00", scorer).stdout
    assert "restored from the copy" in out and "FINAL: KEEP" in part(out, *RB)
    assert (fwd / "decisions.csv").read_text() == (tmp_path / "copy.csv").read_text()
    assert "appends the copy's own line for it to the file, byte for byte" in amendment7_section(3)


def test_amendment_7_states_the_review_s_smaller_points(tmp_path):
    """The review of pull request 64, minor points, and the hub's answer to the first: day totals that balance give
    the grouped interval zero width. The draft kept that rule (+0.30 to +0.30); the registered test takes the wider
    interval, here the plain one, which includes zero, so the result is inconclusive. Also: amendment 5, section 4's
    sentence about the whole interval is named; STATUS counts paths, not seasons; and the replay counts are labelled
    as a replay made with scratch scripts."""
    bets = [(f"Z{d}{j}", d, "13:00", wk, 42 + (5.5 if j < 2 else -1.0), 42, 40)
            for d, wk in (("2026-10-11", 5), ("2026-10-25", 7), ("2026-11-29", 12), ("2026-12-20", 15))
            for j in range(10)]
    rows, games, clv = keep_case(bets)
    out = part(score(tmp_path, rows, games, "2027-01-20", "--test-record"), *RB)
    rec = pd.read_csv(tmp_path / "decisions.csv", dtype=str)
    nums = json.loads(rec.numbers[0])
    assert rec.verdict[0] == "INCONCLUSIVE (carried into 2027 unchanged)"
    assert np.isclose(nums["grouped_half_width"], 0, atol=1e-12) and np.isclose(nums["mean_clv"], 0.3, atol=1e-12)
    assert nums["ci_low"] < 0 < nums["ci_high"] and np.isclose(nums["ci_high"] - 0.3, nums["plain_half_width"])
    assert ("95% CI -0.54 to +1.14; the wider is the plain one (plain -0.54 to +1.14; grouped +0.30 to +0.30, over 4 "
            "game days)") in out
    one = amendment7_section(1)
    assert "even of zero width" not in one.split("Known limit")[-1]                    # the draft's limit is gone
    assert "-0.54 to +1.14" in one and "inconclusive" in one
    assert ('Amendment 5, section 4: "If the keep test and the drop test are both met, the result is drop. That can '
            'only happen when the whole 95% interval sits between 0 and +0.25 points') in norm(amendment(7))
    status = (ROOT.parent / "STATUS.md").read_text()
    assert "40,000 simulated paths of 40 bets per case" in status and "simulated seasons per case" not in status
    assert "scratch scripts, not kept in the repository" in amendment7_section(2)


# ================================================================== the third review of pull request 64 (Sep 29)
def test_amendment_7_reading_3_a_decision_recorded_while_the_copy_is_held_back_is_on_the_mac_only(tmp_path):
    """The third review (its e2e_window). Day 1 records Rule B's KEEP and that night's copy publishes it. Day 2 the
    file is re-saved with other line endings, which the scorer still reads, and the model lean's KEEP is recorded
    into it; that night the copy holds the whole file back, because every published line changed. Day 3 the file is
    lost and the closes are corrected: the next real run restores Rule B from the copy but decides the lean again,
    DROP. Section 3 said the one case left was a decision recorded and lost on the same day; it now states this
    one, and the replaced sentence of amendment 6 is named."""
    good, gg = season(2026, list(range(5, 19)), 40, line=43.0)                # CLV +1 each: KEEP
    leans, gl = season(2026, list(range(5, 19)), 40, first_id=200, line=43.0, lean="UNDER lean")
    repo = tmp_path / "repo"
    proj = live_project(repo, "nfl-weather", good, gg + filler(2026), "2027-01-20T16:00")
    git(repo, "init", "-q")
    fwd, scorer = proj / "data" / "forward", proj / "scripts" / "score_forward.py"
    games = proj / "data" / "raw" / "games.csv"
    out = on_clock(tmp_path, "2027-01-20T17:00", scorer).stdout                # day 1
    assert "FINAL: KEEP" in part(out, *RB) and "recorded in decisions.csv" not in part(out, *LEAN)
    assert "not published" not in nightly(tmp_path, repo)                     # night 1: published
    day1 = (fwd / "decisions.csv").read_bytes()
    (fwd / "decisions.csv").write_bytes(day1.replace(b"\n", b"\r\n"))          # day 2: re-saved
    pd.DataFrame(good + leans).to_csv(fwd / "ledger.csv", index=False)         # the lean's decision is now final
    pd.DataFrame(gg + gl + filler(2026)).to_csv(games, index=False)
    touch(games, "2027-01-21T16:00")
    lean = part(on_clock(tmp_path, "2027-01-21T17:00", scorer).stdout, *LEAN)
    assert "FINAL: KEEP" in lean and "recorded in decisions.csv on 2027-01-21T17:00:00Z" in lean
    out = nightly(tmp_path, repo)                                             # night 2: held back
    assert ("nfl-weather: decisions.csv not published (it has lost or changed a line that the published copy holds); "
            "the published copy is kept as it is") in out
    assert git(repo, "show", "origin/ledgers:nfl-weather/decisions.csv") + "\n" == day1.decode()
    (fwd / "decisions.csv").unlink()                                          # day 3: lost; closes corrected
    pd.DataFrame([dict(x, total_line=46) for x in gg + gl] + filler(2026)).to_csv(games, index=False)
    touch(games, "2027-01-22T16:00")
    out = on_clock(tmp_path, "2027-01-22T17:00", scorer).stdout
    assert "restored 1 recorded decision from its copy on the ledgers branch" in out
    rb = part(out, *RB)
    assert "FINAL: KEEP" in rb and "recorded in decisions.csv on 2027-01-20T17:00:00Z" in rb   # restored, as stated
    lean = part(out, *LEAN)
    assert "FINAL: DROP" in lean and "recorded in decisions.csv on 2027-01-22T17:00:00Z" in lean  # decided again
    # what section 3 and its list of replaced sentences now say
    three = amendment7_section(3)
    assert ("while the nightly copy holds the file back because a published line in it has changed (a hand edit, "
            "say, or a spreadsheet re-saving the file with other line endings, which the scorer still reads), the "
            "scorer goes on recording and nothing new is published, so every decision recorded until the hub puts that "
            "line back exists only on the Mac") in three
    assert "recorded and lost on the same day, before that night's copy" not in norm(amendment(7))
    replaces = norm(amendment(7).split("### What this amendment replaces")[1])
    assert ('Amendment 6, section 3: "A record made since the last nightly copy exists only on the Mac until that '
            'night: if it is lost before then, neither the file nor a copy holds it, and the next real run decides it '
            'again."') in replaces
    cfb = ROOT.parent / "cfb-weather"
    for f in (ROOT / "STRATEGY.md", ROOT / "README.md", ROOT.parent / "STATUS.md", ROOT / "scripts" / "score_forward.py",
              cfb / "STRATEGY.md", cfb / "README.md", cfb / "scripts" / "score_forward.py"):
        text = " ".join(f.read_text().split())
        assert "recorded and lost on the same day, before that night's copy" not in text, f
        assert "since the last nightly copy that published" in text or "before any nightly copy has published it" in (
            text), f


def test_amendment_7_says_why_the_two_looks_are_measured_not_certain():
    """The third review: section 1 said of every case, the two looks included, that the registered test keeps a
    no-edge rule no more often than the others "as it must: a path it keeps, both of the others keep". Over the two
    looks keep and drop both met is a drop, so a wider interval can turn a drop into a keep: there it is measured
    (keep_test_check.py counts such paths: none), not certain. Also: the check's run time is stated the same way in
    the script and in strategy-research/README.md."""
    one = amendment7_section(1)
    assert "as it must" not in one
    assert ("For the keep test on its own this must be so: a path it keeps, both of the others keep. Over the two "
            "looks it need not be, because keep and drop both met is a drop, and a wider interval can turn a drop into "
            "a keep; there it is measured instead: every simulated path the registered test keeps, both of the others "
            "keep too.") in one
    log = (ROOT.parent / "strategy-research" / "output" / "keep_test_check.log").read_text()
    assert "In (3), paths kept by the wider test and not the grouped one: 0; not the plain one: 0" in log
    script = (ROOT.parent / "strategy-research" / "keep_test_check.py").read_text()
    readme = (ROOT.parent / "strategy-research" / "README.md").read_text()
    assert "It takes about a minute." in script and "the run takes about a minute" in readme


# ================================================================== the fourth review of pull request 64 (Sep 29)
BLANKS = "\n   \n"                                                   # a blank line, and a line of only spaces


def with_blanks(text, where):
    """`text` with a blank line and a line of only spaces at its start, before its last line, or at its end."""
    lines = text.splitlines(keepends=True)
    at = {"start": 0, "middle": len(lines) - 1, "end": len(lines)}[where]
    return "".join(lines[:at]) + BLANKS + "".join(lines[at:])


def shown(repo, name):
    """The published copy exactly as `git show` gives it (git() strips the ends, where a blank line may be)."""
    return subprocess.run(["git", "-C", str(repo), "show", f"origin/ledgers:{name}"], capture_output=True, text=True,
                          check=True).stdout


def commit_by_hand(tmp_path, repo, name, text):
    """The hub's hand commit to the ledgers branch, made in the nightly copy's own clone (HOME is inside tmp_path) and
    pushed to the local bare remote; then `git fetch`, as the check-in runs before the scorers."""
    env = dict(os.environ, HOME=str(tmp_path / "home"), GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull,
               GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")
    clone = tmp_path / "home" / "code" / ".value-finder-ledgers"
    (clone / name).write_bytes(text.encode())
    for args in (["add", name], ["commit", "-q", "-m", "by hand"], ["push", "-q", "origin", "ledgers"]):
        subprocess.run(["git", "-C", str(clone), *args], check=True, capture_output=True, env=env)
    subprocess.run(["git", "-C", str(repo), "fetch", "-q", "origin"], check=True, env=env)
    assert shown(repo, name) == text


@pytest.mark.parametrize("where", ["start", "middle", "end"])
@pytest.mark.parametrize("side", ["file", "copy", "both"])
def test_amendment_7_reading_3_a_blank_line_is_skipped_never_damage_never_copied(tmp_path, side, where):
    """The fourth review of pull request 64 (its e2e_record blank and blank_mid): a hand edit left a blank line in
    decisions.csv, the nightly copy published it, the file then lost a decision, and the next real run stopped with
    IndexError while restoring it, so the decision was not restored and the day's report was lost. Now a blank line,
    or a line of only spaces, anywhere in the file or its published copy is not a record and is not damage: the
    scorer skips it when it reads, never counts it and never copies it when it restores, and the nightly copy
    ignores it on both sides and publishes the file without it. Here the blank lines are at `where` in the file, in
    the copy (put there by a hand commit, as the nightly copy no longer publishes them), or in both; the real nightly
    copy runs on a throwaway repository whose origin is a local bare repository."""
    good, gg = season(2026, list(range(5, 19)), 40, line=43.0)                # Rule B, CLV +1 each: KEEP
    leans, gl = season(2026, list(range(5, 19)), 40, first_id=200, line=43.0, lean="UNDER lean")
    repo = tmp_path / "repo"
    proj = live_project(repo, "nfl-weather", good + leans, gg + gl + filler(2026), "2027-01-20T16:00")
    git(repo, "init", "-q")
    fwd, scorer = proj / "data" / "forward", proj / "scripts" / "score_forward.py"
    rec, name = fwd / "decisions.csv", "nfl-weather/decisions.csv"
    day1 = "recorded in decisions.csv on 2027-01-20T17:00:00Z"
    assert on_clock(tmp_path, "2027-01-20T17:00", scorer).stdout.count(day1) == 2         # day 1: both recorded
    whole = rec.read_text()
    head, first, second = whole.splitlines(keepends=True)
    assert "not published" not in nightly(tmp_path, repo) and shown(repo, name) == whole   # night 1
    copy = whole if side == "file" else with_blanks(whole, where)
    if side != "file":
        commit_by_hand(tmp_path, repo, name, copy)                           # a hand repair left blank lines
    kept = head + second if side == "copy" else with_blanks(head + second, where)
    rec.write_text(kept)                                                      # day 2: the file loses a decision
    out = nightly(tmp_path, repo)                                             # night 2: held back, blank lines aside
    assert ("nfl-weather: decisions.csv not published (it has lost or changed a line that the published copy holds); "
            "the published copy is kept as it is") in out and shown(repo, name) == copy
    touch(proj / "data" / "raw" / "games.csv", "2027-01-22T16:00")
    r = on_clock(tmp_path, "2027-01-22T17:00", scorer)                        # day 3: the check-in
    assert r.returncode == 0, r.stderr
    lost = first.split(",")[0]
    assert (f"data/forward/decisions.csv was missing 1 recorded decision that its copy on the ledgers branch "
            f"(origin/ledgers:{name}) holds ({lost}); restored from the copy") in r.stdout
    assert "unreadable" not in r.stdout and r.stdout.count(day1) == 2 and "on 2027-01-22T17:00:00Z" not in r.stdout
    assert rec.read_text() == kept + first                                    # the copy's line only, no blank line
    if side != "file":                                                        # the whole file lost: no blank lines
        rec.unlink()
        r = on_clock(tmp_path, "2027-01-22T18:00", scorer)
        assert r.returncode == 0, r.stderr
        assert "restored 2 recorded decisions from its copy on the ledgers branch" in r.stdout
        assert r.stdout.count(day1) == 2 and rec.read_text() == whole
    out = nightly(tmp_path, repo)                                             # night 3: published, no blank lines
    assert "not published" not in out
    assert shown(repo, name) == (head + second + first if side == "file" else whole)
    assert ("A blank line, or a line of only spaces, anywhere in `decisions.csv` or in its published copy is not a "
            "record and is not damage") in amendment7_section(3)


def test_amendment_7_reading_3_a_record_of_only_blank_lines_is_unreadable(tmp_path):
    """Blank lines are skipped, so a file of only blank lines holds no header: it can't be read, as an empty file
    can't, and nothing is added to it."""
    rows, games = season(2026, list(range(5, 19)), 40, line=43.0)
    (tmp_path / "decisions.csv").write_text(BLANKS)
    out = score(tmp_path, rows, games + filler(2026), "2027-01-20", "--test-record")
    assert "Decision record: decisions.csv is unreadable (ValueError: the file holds only blank lines)" in out
    assert "FINAL: KEEP" in part(out, *RB) and (tmp_path / "decisions.csv").read_text() == BLANKS


def test_amendment_7_section_3_hub_md_and_run_records_say_who_replaces_a_damaged_copy():
    """The fourth review's minor finding: while the published copy can't be read, the scorer said that the nightly
    copy of a readable file would repair it, but the nightly copy keeps a damaged published copy (section 3), so
    recording stayed stopped until the hub worked that out. The scorer's lines (checked in
    test_amendment_7_reading_3_a_damaged_copy_stops_recording_and_shows_what_it_can), section 3, hub.md and
    ops/RUN_RECORDS.md now say the same."""
    assert HUB_REPLACES in amendment7_section(3)
    assert "Recording resumes once the copy can be read again." not in amendment7_section(3)
    for doc in (ROOT.parent / ".claude" / "commands" / "hub.md", ROOT.parent / "ops" / "RUN_RECORDS.md"):
        assert HUB_REPLACES in " ".join(doc.read_text().replace("`", "").split()), doc
