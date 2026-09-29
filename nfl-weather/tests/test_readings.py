"""Amendment 6: the scorer readings that a review of pull request 50 found open. One test per reading,
built on the reviewers' own scenarios (their inputs are reused here). Each test fails on the scorer as
merged in pull request 50 and passes under amendment 6."""
import hashlib
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from nflweather import board  # noqa: E402
from nflweather.market import ev_under, p_under_at, pricing_cohort  # noqa: E402

RB = ("RULE_B (wind under)", "RULE_B, secondary")
LEAN = ("MODEL_LEAN", "RULE_B (wind under)")
COLUMNS = ["rule", "horizon", "horizon_utc", "decided_utc", "n_bets", "verdict", "numbers", "ledger_rows_sha256"]


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
    out = part(score(tmp_path, good + late, g_good + waiting + filler(2026), "2027-01-25"), *RB)
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
    first = part(score(tmp_path, good + late, g_good + unscored + filler(2026), "2027-02-10"), *RB)
    assert "41 signals, 40 settled, 0 pending, 1 void" in first and "FINAL: KEEP" in first

    rec = pd.read_csv(tmp_path / "decisions.csv", dtype=str)                 # beside the test ledger
    assert list(rec.columns) == COLUMNS and len(rec) == 1
    r = rec.iloc[0]
    assert (r.rule, r.horizon, r.n_bets, r.verdict) == ("Rule B", "after Week 18 of 2026", "40", "KEEP")
    assert r.decided_utc == "2027-02-10T00:00:00Z" and r.horizon_utc == "2027-01-10T18:00:00Z"
    assert '"mean_clv": 0.6' in r.numbers and '"with_close": 40' in r.numbers
    assert r.ledger_rows_sha256 == entry_fingerprint(tmp_path / "ledger.csv", [x["game_id"] for x in good])

    # the missing score lands after the decision: a fresh computation now has 41 bets; the record stands
    later = part(score(tmp_path, good + late, g_good + g_late + filler(2026), "2027-02-20"), *RB)
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
    """The reviewers' E: 20 beat the close, 2 tie it, 18 lose to it."""
    rows, games = season(2026, range(5, 19), 40, line=43.0, close=42)
    for i, g in enumerate(games):
        g["total"] = 40 if i < 20 else (42 if i < 22 else 45)
    out = part(score(tmp_path, rows, games, "2027-01-20"), *RB)
    assert "win rate vs the close 52.6% (20 of 38 with a close, 2 ties), ties left out" in out
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
