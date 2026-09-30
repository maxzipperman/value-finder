"""My own checks of B1, B2, B3 and B5 for the NFL forward test (Rule B), on made-up ledgers only. The scorer runs as
a subprocess with --ledger and --games on scratch copies and --now. Nothing here reads the live ledger or a 2026
price or result.

    ./pyw.sh nfl -m pytest -q -p no:cacheprovider mine/test_fwd_nfl.py
"""
import ast
import importlib.util
import math
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from scipy import stats

W = Path(os.environ.get("PE_WORKTREE", "/Users/maxzipperman/code/value-finder/.claude/worktrees/wf_4496c14b-845-1"))
P = W / "nfl-weather"
SCORER = P / "scripts" / "score_forward.py"
sys.path.insert(0, str(P))
from nflweather import board, oddsapi  # noqa: E402
from nflweather.market import valid_odds  # noqa: E402

spec = importlib.util.spec_from_file_location("nfl_helpers", P / "tests" / "test_readings.py")
h = importlib.util.module_from_spec(spec)
spec.loader.exec_module(h)          # only its row(), game() and filler() builders are used
row, game = h.row, h.game
T = pd.Timestamp
RB = ("RULE_B (wind under)", "RULE_B, secondary")


def score(folder, rows, games, now, *extra):
    folder.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(folder / "ledger.csv", index=False)
    pd.DataFrame(games).to_csv(folder / "games.csv", index=False)
    r = subprocess.run([sys.executable, str(SCORER), "--ledger", str(folder / "ledger.csv"), "--games",
                        str(folder / "games.csv"), "--now", now, *extra], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-2000:]
    return r.stdout


def part(out):
    return out.split(RB[0], 1)[1].split(RB[1], 1)[0]


def extract(path, names, env):
    tree = ast.parse(path.read_text())
    nodes = [n for n in tree.body if (isinstance(n, ast.FunctionDef) and n.name in names)
             or (isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id in names for t in n.targets))]
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), "exec"), env)
    return env


# ================================================================ B1
def test_b1_rule_b_first_registered_pinnacle_signal(tmp_path):
    d = "2026-10-11"          # a Sunday, 13:00 Eastern = 17:00 UTC
    rows = [row("G1", d, snap="2026-10-08T15:00:00Z", total_line=50.0, rules_version="v0-unregistered"),
            row("G1", d, snap="2026-10-09T15:00:00Z", total_line=46.0, line_src="draftkings"),
            row("G1", d, snap="2026-10-10T15:00:00Z", total_line=45.0),
            row("G1", d, snap="2026-10-11T15:00:00Z", total_line=44.0)]
    out = score(tmp_path, rows, [game("G1", d, week=6, close=43.0, total=40)] + h.filler(2026), "2026-10-20")
    assert "excluded, unregistered rules version: 1" in out
    p = part(out)
    assert "1 signals, 1 settled" in p and "mean CLV +2.00" in p          # entry 45 (first Pinnacle signal), close 43
    assert "v0-unregistered" not in board.REGISTERED_VERSIONS


def test_b1_before_kickoff_is_before_the_earlier_of_row_and_schedule(tmp_path):
    # the row says 16:25 Eastern (20:25 UTC); the schedule says 13:00 Eastern (17:00 UTC)
    rows = [row("G2", "2026-10-11", time="16:25", snap="2026-10-11T18:00:00Z"),
            row("G3", "2026-10-11", time="16:25", snap="2026-10-11T17:00:00Z"),
            row("G4", "2026-10-11", time="16:25", snap="2026-10-11T16:59:00Z")]
    games = [game(g, "2026-10-11", week=6) for g in ("G2", "G3", "G4")] + h.filler(2026)
    out = score(tmp_path, rows, games, "2026-10-20")
    assert "excluded, logged at or after kickoff: 2" in out and "1 signals" in part(out)


# ================================================================ B3
def test_b3_void_and_pending(tmp_path):
    rows = [row(f"V{i}", "2026-10-11", snap="2026-10-09T15:00:00Z") for i in range(4)]
    games = [game("V0", "2026-10-12", week=6),                                   # 24 hours later: a bet
             game("V1", "2026-10-12", time="13:01", week=6),                     # 24 hours 1 minute: void
             game("V2", "2026-10-11", week=6, total=np.nan, result=np.nan),      # no result yet
             game("V3", "2026-10-11", week=6)] + h.filler(2026)
    p = part(score(tmp_path, rows, games, "2026-11-09T18:00:00Z"))
    assert "4 signals, 2 settled, 1 pending, 1 void" in p
    assert "void, the game kicked off more than 24 hours from the kickoff on its entry row: 1 (V1)" in p
    p = part(score(tmp_path / "later", rows, games, "2026-11-10T17:00:00Z"))
    assert "void, the schedule shows no result 30 days after that kickoff: 1 (V2)" in p


# ================================================================ B5
def _indep(clv, day):
    clv, day = np.asarray(clv, float), np.asarray(day)
    n = len(clv)
    m = sum(clv) / n
    s = math.sqrt(sum((x - m) ** 2 for x in clv) / (n - 1))
    plain = stats.t.ppf(0.975, n - 1) * s / math.sqrt(n)
    days = sorted(set(day))
    G = len(days)
    sums = [sum(c - m for c, d in zip(clv, day) if d == g) for g in days]
    grouped = stats.t.ppf(0.975, G - 1) * math.sqrt(G / (G - 1) * sum(x * x for x in sums) / n ** 2)
    return m, plain, grouped, m - max(plain, grouped), m + max(plain, grouped), G


def test_b5_real_interval_and_game_day():
    fn = extract(SCORER, {"interval", "game_day"}, dict(np=np, pd=pd, stats=stats))
    rng = np.random.default_rng(3)
    for n, G in ((40, 14), (41, 4), (60, 18)):
        clv = rng.normal(0.3, 2.0, n) + np.repeat(rng.normal(0, 1.0, G), -(-n // G))[:n]
        day = np.repeat(np.arange(G), -(-n // G))[:n]
        got = fn["interval"](clv, day)
        want = _indep(clv, day)
        for k, v in zip(("m", "plain", "grouped", "lo", "hi"), want[:5]):
            assert got[k] == pytest.approx(v, rel=1e-12, abs=1e-12), (n, G, k)
    k = pd.to_datetime(["2026-11-02T01:20Z", "2026-11-08T05:30Z"], utc=True)          # SNF 8:20 PM ET; 12:30 AM ET
    assert list(fn["game_day"](pd.DataFrame(dict(kick_utc=k, row_kick=k)))) == ["2026-11-01", "2026-11-08"]


# ================================================================ B2
def test_b2_capture_event_choice():
    env = dict(pd=pd, oddsapi=oddsapi, valid_odds=valid_odds)
    one = extract(P / "scripts" / "capture_close.py", {"one_event", "NEAR"}, env)["one_event"]
    due = pd.DataFrame([dict(game_id="G", kick_utc=T("2026-10-11T17:00Z"), home_team="H", away_team="A")])

    def f(eid, start, book="pinnacle", total=44.0, under=-110, over=-110):
        return dict(event_id=eid, home_team="H", away_team="A", commence_utc=start, book=book, close_total=total,
                    close_under=under, close_over=over)
    pick = lambda feed: one(due, pd.DataFrame(feed))[0].event_id.tolist()      # noqa: E731
    assert pick([f("a", "2026-10-11T23:01Z")]) == []                            # 6 h 1 min
    assert pick([f("a", "2026-10-11T22:59Z")]) == ["a"]
    assert pick([f("a", "2026-10-11T17:00Z", book="draftkings"), f("b", "2026-10-11T20:00Z")]) == ["b"]
    assert pick([f("a", "2026-10-11T17:00Z", under=-50), f("b", "2026-10-11T19:00Z")]) == ["b"]   # a is no quote
    assert pick([f("b", "2026-10-11T17:00Z"), f("a", "2026-10-11T17:00Z")]) == ["b"]              # same quote: first
    assert pick([f("a", "2026-10-11T17:00Z"), f("b", "2026-10-11T17:00Z", total=45.0)]) == []    # differ: none
    assert oddsapi.RULE_BOOK == "pinnacle"
