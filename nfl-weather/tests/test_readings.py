"""Amendment 6: the scorer readings that a review of pull request 50 found open. One test per reading,
built on the reviewers' own scenarios (their inputs are reused here). Each test fails on the scorer as
merged in pull request 50 and passes under amendment 6."""
import fcntl
import hashlib
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
