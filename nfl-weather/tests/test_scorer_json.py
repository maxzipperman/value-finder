"""The scorer's --json option (for the dashboard's log of signals): with it the scorer prints one JSON document and
nothing else; without it the scorer prints exactly what it printed before. Nothing about grading, decisions or
recording changes: the document's "text" is the printed report, byte for byte, every number in it equals the number
the report prints for the same thing, and a decision is recorded, or not, by the same rules."""
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
SCORER = ROOT / "scripts" / "score_forward.py"
REHEARSAL = ROOT / "output" / "tables" / "rehearsal_2025.csv"
VOID_MOVED = "the game kicked off more than 24 hours from the kickoff on its entry row"
VOID_NO_RESULT = "the schedule shows no result 30 days after that kickoff"


# ------------------------------------------------------------------ ledgers and schedules
def wk_day(year, wk):
    """The Sunday of `wk` in `year`'s season (Week 1's Sunday is Sep 13 in 2026)."""
    return (pd.Timestamp(f"{year}-09-10") + pd.Timedelta(weeks=wk - 1, days=3)).strftime("%Y-%m-%d")


def row(gid, day, time="13:00", snap=None, **kw):
    base = dict(rules_version="v3-2026-09-28", game_id=gid, gameday=day, gametime=time, away_team="AWY",
                home_team="HOM", lead_days=2, wx_src="era5", wx_wind=16, line_src="pinnacle", total_line=44.0,
                under_odds=-110, over_odds=-110, p_under=0.5, p_market=0.5, lean="", ev_under=0.08, rule_b="SIGNAL")
    base["snapshot_utc"] = snap or (pd.Timestamp(day) - pd.Timedelta(days=2)).strftime("%Y-%m-%dT15:00:00Z")
    return base | kw


def game(gid, day, time="13:00", season=None, week=None, game_type="REG", total=40, close=42, result=3):
    d = pd.Timestamp(day)
    season = season if season is not None else (d.year if d.month >= 8 else d.year - 1)
    return dict(game_id=gid, season=season, week=week, game_type=game_type, gameday=day, gametime=time,
                total=total, total_line=close, result=result)


def season(year, weeks, n, first_id=0, line=44.0, close=42, total=40):
    rows, games = [], []
    for i in range(n):
        wk = weeks[i % len(weeks)]
        gid = f"{year}_{wk:02d}_{first_id + i}"
        rows.append(row(gid, wk_day(year, wk), total_line=line))
        games.append(game(gid, wk_day(year, wk), season=year, week=wk, total=total, close=close))
    return rows, games


def filler(year):
    return [game(f"{year}_{wk:02d}_FILL", wk_day(year, wk), season=year, week=wk) for wk in range(1, 19)]


def mixed():
    """Settled bets (won, lost, pushed, one at an assumed -110), pending, void (moved; no result 30 days on), a
    signal at the backup price, leans both ways, an excluded row, and captured closes for some bets."""
    rows = [row("E1", "2026-10-04", rule_b="SIGNAL"),                                     # before Week 5: excluded
            row("W1", "2026-10-11", total_line=44.0, under_odds=-108),                    # won
            row("L1", "2026-10-11", time="16:25", total_line=41.5, under_odds=-112),      # lost
            row("P1", "2026-10-18", total_line=40.0, under_odds=-105),                    # push
            row("W2", "2026-10-25", total_line=47.0, under_odds=102),                     # won at plus money
            row("MV", "2026-10-25", time="20:20"),                                        # moved: void
            row("NR", "2026-10-18", time="16:05"),                                        # never scored: void
            row("PD", "2026-11-22"),                                                      # pending
            row("S1", "2026-11-01", line_src="nflverse", rule_b="SIGNAL_SECONDARY", under_odds=-115),
            row("S2", "2026-11-01", time="16:25", line_src="draftkings", under_odds=-110),   # a SIGNAL priced elsewhere
            row("LU", "2026-10-18", rule_b="no_trigger", lean="UNDER lean", total_line=45.5, under_odds=np.nan,
                snap="2026-10-12T15:00:00Z"),                                             # a lean with no price
            row("LO", "2026-10-25", rule_b="no_trigger", lean="OVER lean", total_line=42.0, over_odds=-104,
                snap="2026-10-19T15:00:00Z")]
    games = [game("E1", "2026-10-04", week=4), game("W1", "2026-10-11", week=6, total=38, close=43.5),
             game("L1", "2026-10-11", time="16:25", week=6, total=48, close=42.0),
             game("P1", "2026-10-18", week=7, total=40, close=39.5),
             game("W2", "2026-10-25", week=8, total=31, close=46.5),
             game("MV", "2026-10-27", time="20:15", week=8),
             game("NR", "2026-10-18", time="16:05", week=7, total=np.nan, result=np.nan),
             game("PD", "2026-11-22", week=11, total=np.nan, result=np.nan),
             game("S1", "2026-11-01", week=9, total=35, close=44.5), game("S2", "2026-11-01", time="16:25", week=9,
                                                                          total=52, close=45.0),
             game("LU", "2026-10-18", week=7, total=41, close=45.0), game("LO", "2026-10-25", week=8, total=50,
                                                                      close=43.0)]
    closes = [dict(game_id="W1", book="pinnacle", close_total=43.0), dict(game_id="L1", book="pinnacle",
                                                                           close_total=42.5),
              dict(game_id="W1", book="draftkings", close_total=43.5)]
    return rows, games + filler(2026), closes


def write(folder, rows, games, closes=None):
    folder.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(folder / "ledger.csv", index=False)
    pd.DataFrame(games).to_csv(folder / "games.csv", index=False)
    if closes:
        pd.DataFrame(closes).to_csv(folder / "closes.csv", index=False)
    return folder


def rehearsal(folder):
    """The committed rehearsal ledger and the schedule scripts/rehearse_2025.py scores it against."""
    folder.mkdir(parents=True, exist_ok=True)
    shutil.copy(REHEARSAL, folder / "ledger.csv")
    g = pd.read_parquet(ROOT / "data" / "processed" / "games.parquet")
    g = g[(g.season == 2025) & (g.game_type == "REG") & g.week.between(5, 18) & g.result.notna()].copy()
    g.assign(gameday=(pd.to_datetime(g.gameday) + pd.Timedelta(weeks=53)).dt.strftime("%Y-%m-%d"))[
        ["game_id", "total", "total_line", "gameday", "gametime", "result"]].to_csv(folder / "games.csv", index=False)
    return folder


def forty(folder):
    """40 Rule B signals in the 2026 regular season: a decision that is FINAL after Week 18 of 2026."""
    rows, games = season(2026, list(range(5, 18)), 40)
    for i, r in enumerate(rows):
        r["total_line"] = 43.0 if i % 2 == 0 else 42.2
    return write(folder, rows, games + filler(2026))


SCENARIOS = {"mixed": (lambda d: write(d, *mixed()), "2026-12-01"),
             "no signals": (lambda d: write(d, [row("E1", "2026-10-04")], [game("E1", "2026-10-04", week=4)]),
                            "2026-12-01"),
             "a final decision": (forty, "2027-01-20"),
             "the rehearsal": (rehearsal, "2027-03-01")}


def run(script, folder, now, *extra):
    args = [sys.executable, str(script), "--ledger", str(folder / "ledger.csv"), "--games", str(folder / "games.csv")]
    return subprocess.run(args + (["--now", now] if now else []) + list(extra), capture_output=True, text=True)


def doc_of(folder, now, *extra):
    r = run(SCORER, folder, now, "--json", *extra)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def test_json_prints_one_document_and_nothing_else(tmp_path):
    folder = write(tmp_path, *mixed())
    r = run(SCORER, folder, "2026-12-01", "--json")
    assert r.returncode == 0, r.stderr
    doc = json.loads(r.stdout)                                  # the whole of stdout is one document
    assert r.stdout.count("\n") == 1 and r.stdout.startswith("{")
    assert set(doc) >= {"generated_utc", "now", "ledger", "text", "excluded", "tests", "decision_record"}
    assert doc["now"] == "2026-12-01T00:00:00Z" and doc["ledger"] == str(folder / "ledger.csv")
    assert [t["id"] for t in doc["tests"]] == ["RULE_B", "RULE_B_SECONDARY", "MODEL_LEAN"]
    assert doc["excluded"] == {"before Week 5 (Oct 8, 2026)": 1}


# ------------------------------------------------------------------ the printed report, byte for byte
@pytest.mark.parametrize("name", SCENARIOS)
def test_the_document_text_is_the_printed_report(tmp_path, name):
    make, now = SCENARIOS[name]
    a, b = make(tmp_path / "plain"), make(tmp_path / "json")
    plain = run(SCORER, a, now)
    assert plain.returncode == 0, plain.stderr
    assert doc_of(b, now)["text"] == plain.stdout


def scorer_before_json():
    """The scorer as it was before --json was added, from git: the parent of the commit that added it (HEAD, before
    that commit is made). None when git can't show it, or when the scorer has changed since that commit (a later
    amendment), so the comparison would no longer be like for like."""
    rel = "nfl-weather/scripts/score_forward.py"
    git = ["git", "-C", str(ROOT)]
    try:
        added = subprocess.run(git + ["log", "--format=%H", '-S"--json"', "--", "scripts/score_forward.py"],
                               capture_output=True, text=True, timeout=60)
        if added.returncode:
            return None
        commits = added.stdout.split()
        if commits:
            later = subprocess.run(git + ["log", "--format=%H", f"{commits[-1]}..HEAD", "--",
                                          "scripts/score_forward.py"], capture_output=True, text=True, timeout=60)
            if later.returncode or later.stdout.split():
                return None
            ref = f"{commits[-1]}^"
        else:
            ref = "HEAD"
        shown = subprocess.run(git + ["show", f"{ref}:{rel}"], capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None
    if shown.returncode or '"--json"' in shown.stdout:
        return None
    return shown.stdout


@pytest.mark.parametrize("name", SCENARIOS)
def test_without_json_the_report_is_what_it_was_before(tmp_path, name):
    """Byte for byte what the scorer printed before --json was added, on the same ledger at the same time."""
    before = scorer_before_json()
    if before is None:
        pytest.skip("the scorer before --json can't be read from git here, or it has changed since")
    proj = tmp_path / "proj"
    shutil.copytree(ROOT / "nflweather", proj / "nflweather", ignore=shutil.ignore_patterns("__pycache__"))
    (proj / "scripts").mkdir()
    (proj / "scripts" / "score_forward.py").write_text(before)
    make, now = SCENARIOS[name]
    a, b = make(tmp_path / "now"), make(tmp_path / "then")
    now_out, then_out = run(SCORER, a, now), run(proj / "scripts" / "score_forward.py", b, now)
    assert now_out.returncode == then_out.returncode == 0, (now_out.stderr, then_out.stderr)
    assert now_out.stdout == then_out.stdout


# ------------------------------------------------------------------ every number equals the printed one
def section(text, name):
    """One test's part of the report: from its header line to the next test's."""
    heads = ["\nMODEL_LEAN:", "\nRULE_B (wind under):", "\nRULE_B, secondary price (not part of the decision):",
             "\nWind triggers", "\nCost of waiting", "\nDecision horizons"]
    start = text.index("\n" + name)
    ends = [text.index(h, start + 1) for h in heads if h in text[start + 1:]]
    return text[start:min(ends) if ends else len(text)]


def table_rows(part):
    """The bet table under a test: {game_id: [the numbers after side and price source]}."""
    lines = part.splitlines()
    start = next((i for i, ln in enumerate(lines) if ln.split()[:2] == ["game_id", "side"]), None)
    out = {}
    for ln in lines[start + 1:] if start is not None else []:
        if ln.startswith("  ") and not ln.strip()[0].isalnum() or ln.startswith("  decision") or not ln.strip():
            break
        cells = ln.split()
        out[cells[0]] = cells[-5:]                   # total_line, close_total, total, clv_pts, profit
    return out


def close_to(printed: str, value) -> bool:
    if printed == "NaN":
        return value is None
    digits = len(printed.split(".")[1]) if "." in printed else 0
    return value is not None and abs(float(printed) - value) <= 0.5 * 10 ** -digits + 1e-12


@pytest.mark.parametrize("name", ["mixed", "the rehearsal", "a final decision"])
def test_every_number_equals_the_printed_one(tmp_path, name):
    make, now = SCENARIOS[name]
    doc = doc_of(make(tmp_path), now)
    text = doc["text"]
    m = re.match(r"ledger rows: (\d+); in the test: (\d+)", text)
    assert (int(m[1]), int(m[2])) == (doc["rows"]["ledger"], doc["rows"]["in_test"])
    assert doc["excluded"] == {k: int(v) for k, v in re.findall(r"^  excluded, (.+): (\d+)$", text, re.M)}
    for t in doc["tests"]:
        c = t["counts"]
        if t["id"] == "RULE_B_SECONDARY" and not c["signals"]:
            assert "\nRULE_B, secondary price (not part of the decision): 0 signals\n" in text
            continue
        part = section(text, t["printed_as"])
        assert part.startswith(f"\n{t['printed_as']}: {c['signals']} signals, {c['settled']} settled, "
                               f"{c['pending']} pending, {c['void']} void (not graded)")
        for reason, n in t["void_reasons"].items():
            assert f"  void, {reason}: {n} (" in part
        assert sum(b["outcome"] == "void" for b in t["bets"]) == c["void"]
        assert sum(b["outcome"] == "pending" for b in t["bets"]) == c["pending"]
        if not c["settled"]:
            assert t["record"] is None and t["units"] is None
            continue
        r = t["record"]
        assert (f"  record at entry line {r['won']}-{r['lost']}-{r['pushed']}   units {t['units']:+.2f} "
                f"(ROI {t['roi_percent']:+.1f}% per bet placed; {t['graded_at_assumed_price']} graded at an assumed "
                "-110)") in part
        iv, mean = t["interval"], t["mean_clv"]
        assert f"  mean CLV {mean:+.2f} pts; {t['n_clv']} of {c['settled']} bets have a primary close; " in part
        if iv["n"] >= 2 and iv["game_days"] >= 2:
            assert f"95% CI {iv['low']:+.2f} to {iv['high']:+.2f}; " in part
            g, p = iv["grouped_half_width"], iv["plain_half_width"]
            assert f"grouped {mean - g:+.2f} to {mean + g:+.2f}" in part and f"plain {mean - p:+.2f} to {mean + p:+.2f}" in part
            assert iv["low"] == pytest.approx(mean - max(g, p)) and iv["high"] == pytest.approx(mean + max(g, p))
        s = t["secondary_clv"]
        if s["n"]:
            assert (f"mean CLV vs captured Pinnacle close {s['mean']:+.2f} pts (95% CI " in part
                    and f"{s['without']} of {c['settled']} without a captured close" in part)
        else:
            assert f"no captured closes for these {c['settled']} bets" in part
        # each settled bet, as the report's table prints it
        printed = table_rows(part)
        settled = [b for b in t["bets"] if b["outcome"] in ("won", "lost", "push")]
        assert sorted(printed) == sorted(b["game_id"] for b in settled)
        for b in settled:
            line, close, total, clv, units = printed[b["game_id"]]
            assert close_to(line, b["entry_line"]) and close_to(close, b["close_line"])
            assert close_to(total, b["final_total"]) and close_to(clv, b["clv"]) and close_to(units, b["units"])
        assert sum(b["units"] for b in settled) == pytest.approx(t["units"])
        assert [b["outcome"] for b in settled].count("won") == r["won"]
        assert [b["outcome"] for b in settled].count("push") == r["pushed"]
        # the decision, as printed
        for d in t["decisions"]:
            assert d["text"] in text and d["text"].startswith(f"  decision ({d['name']})")
            assert ("INTERIM read" in d["text"]) == (d["status"] == "interim")


# ------------------------------------------------------------------ the cases the dashboard shows
def test_a_ledger_with_no_signals(tmp_path):
    doc = doc_of(SCENARIOS["no signals"][0](tmp_path), "2026-12-01")
    for t in doc["tests"]:
        assert t["counts"] == {"signals": 0, "settled": 0, "pending": 0, "void": 0}
        assert t["bets"] == [] and t["record"] is None and t["decisions"] == [] and t["interval"] is None
    assert doc["excluded"] == {"before Week 5 (Oct 8, 2026)": 1}


def test_pending_and_void_bets(tmp_path):
    doc = doc_of(write(tmp_path, *mixed()), "2026-12-01")
    rb, second, lean = doc["tests"]
    by = {b["game_id"]: b for b in rb["bets"]}
    assert set(by) == {"W1", "L1", "P1", "W2", "MV", "NR", "PD"}
    assert [by[g]["outcome"] for g in ("W1", "L1", "P1", "W2", "PD")] == ["won", "lost", "push", "won", "pending"]
    assert (by["MV"]["outcome"], by["MV"]["void_reason"]) == ("void", VOID_MOVED)
    assert (by["NR"]["outcome"], by["NR"]["void_reason"]) == ("void", VOID_NO_RESULT)
    for g in ("MV", "NR", "PD"):                           # not graded: no close, value, total or units
        assert by[g]["units"] is None and by[g]["clv"] is None and by[g]["final_total"] is None
    w1 = by["W1"]
    assert (w1["entry_line"], w1["entry_price"], w1["price_source"], w1["close_line"], w1["close_source"]) == (
        44.0, -108.0, "pinnacle", 43.5, "nflverse schedule")
    assert (w1["clv"], w1["final_total"], w1["units"]) == (0.5, 38.0, pytest.approx(100 / 108))
    assert (w1["captured_close"], w1["clv_captured"]) == (43.0, 1.0)            # Pinnacle's captured close
    assert (w1["away_team"], w1["home_team"], w1["side"]) == ("AWY", "HOM", "UNDER")
    assert w1["kickoff_utc"] == "2026-10-11T17:00:00Z" and w1["logged_utc"] == "2026-10-09T15:00:00Z"
    assert by["W2"]["units"] == pytest.approx(1.02)                              # +102
    assert by["P1"]["units"] == 0.0 and rb["record"] == {"won": 2, "lost": 1, "pushed": 1}
    # a SIGNAL priced anywhere but Pinnacle is a backup-price signal, as the tables print it
    assert sorted(b["game_id"] for b in second["bets"]) == ["S1", "S2"] and second["decides"] is False
    assert {b["game_id"]: b["price_source"] for b in second["bets"]} == {"S1": "nflverse", "S2": "draftkings"}
    lu, lo = sorted(lean["bets"], key=lambda b: b["game_id"])[::-1]
    assert (lu["game_id"], lu["side"], lu["price_assumed"], lu["entry_price"], lu["outcome"]) == (
        "LU", "UNDER", True, None, "won")
    assert lu["units"] == pytest.approx(100 / 110) and lean["graded_at_assumed_price"] == 1
    assert (lo["side"], lo["entry_price"], lo["outcome"], lo["clv"]) == ("OVER", -104.0, "won", 1.0)


def test_a_recorded_decision(tmp_path):
    """--json records by the same rules as the plain report: a --test-record run writes the same record either way,
    and the next run hands over the recorded decision."""
    plain, js = forty(tmp_path / "plain"), forty(tmp_path / "json")
    p = run(SCORER, plain, "2027-01-20", "--test-record")
    doc = doc_of(js, "2027-01-20", "--test-record")
    assert doc["text"] == p.stdout
    assert (plain / "decisions.csv").read_bytes() == (js / "decisions.csv").read_bytes()
    d = doc["tests"][0]["decisions"]
    assert [(x["status"], x["verdict"], x["written"]) for x in d] == [("final", "KEEP", True)]
    assert doc["decision_record"] == {"written_by_this_run": True, "why_not": None}
    later = doc_of(js, "2027-02-10")                  # a preview after the decision was made shows it as recorded
    d = later["tests"][0]["decisions"][0]
    assert (d["status"], d["verdict"], d["recorded"]["verdict"], d["recorded"]["n_bets"]) == (
        "recorded", "KEEP", "KEEP", 40)
    assert d["recorded"]["decided_utc"] == "2027-01-20T00:00:00Z" and "FINAL: KEEP" in d["text"]
    assert (js / "decisions.csv").read_bytes() == (plain / "decisions.csv").read_bytes()    # nothing more written


def test_json_with_now_never_records(tmp_path):
    folder = forty(tmp_path / "t")
    doc = doc_of(folder, "2027-01-20")                # FINAL at this date, but a preview
    d = doc["tests"][0]["decisions"][0]
    assert (d["status"], d["verdict"], d["written"]) == ("final", "KEEP", False)
    assert "not recorded: a run with --now is a preview." in d["text"]
    assert doc["decision_record"] == {"written_by_this_run": False, "why_not": "a run with --now is a preview"}
    assert not (folder / "decisions.csv").exists() and not (folder / ".decisions.lock").exists()
    # a copy of the project with its own live ledger: a --now --json run on it records nothing there either
    proj = tmp_path / "proj"
    shutil.copytree(ROOT / "nflweather", proj / "nflweather", ignore=shutil.ignore_patterns("__pycache__"))
    (proj / "scripts").mkdir()
    shutil.copy(SCORER, proj / "scripts" / "score_forward.py")
    fwd = proj / "data" / "forward"
    fwd.mkdir(parents=True)
    shutil.copy(folder / "ledger.csv", fwd / "ledger.csv")
    r = subprocess.run([sys.executable, str(proj / "scripts" / "score_forward.py"), "--ledger", str(fwd / "ledger.csv"),
                        "--games", str(folder / "games.csv"), "--now", "2027-01-20", "--json"],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout)["tests"][0]["decisions"][0]["written"] is False
    assert sorted(p.name for p in fwd.iterdir()) == ["ledger.csv"]


# ------------------------------------------------------------------ the real clock, on a live layout
FAKE_CLOCK = """import os, runpy, sys
import pandas as pd
FAKE = pd.Timestamp(os.environ["FAKE_NOW"], tz="UTC")
pd.Timestamp.now = staticmethod(lambda tz=None: FAKE.tz_convert(tz) if tz is not None else FAKE.tz_localize(None))
script, sys.argv = sys.argv[1], sys.argv[1:]
runpy.run_path(script, run_name="__main__")
"""


def live_copy(base):
    """A copy of this project laid out like the live checkout, outside any git repository (so no nightly copy): the
    scorer and its package, its own ledger in data/forward (40 Rule B signals in 2026) and its default schedule,
    data/raw/games.csv, refreshed an hour before the clock below."""
    proj = base / "nfl-weather"
    shutil.copytree(ROOT / "nflweather", proj / "nflweather", ignore=shutil.ignore_patterns("__pycache__"))
    (proj / "scripts").mkdir()
    shutil.copy(SCORER, proj / "scripts" / "score_forward.py")
    forty(proj / "data" / "forward")
    (proj / "data" / "raw").mkdir(parents=True)
    games = (proj / "data" / "forward" / "games.csv").rename(proj / "data" / "raw" / "games.csv")
    t = pd.Timestamp("2027-01-20T16:00", tz="UTC").timestamp()
    os.utime(games, (t, t))
    return proj


def on_clock(tmp_path, now, proj, *extra):
    """The scorer on its real-clock path (no --now, the default ledger and schedule), with the clock set to `now`."""
    runner = tmp_path / "fakeclock.py"
    runner.write_text(FAKE_CLOCK)
    return subprocess.run([sys.executable, str(runner), str(proj / "scripts" / "score_forward.py"), *extra],
                          capture_output=True, text=True, env={**os.environ, "FAKE_NOW": now})


def test_a_real_clock_run_records_the_same_with_or_without_json(tmp_path):
    """The live ledger on the real clock, after the horizon: the run with --json records exactly the line the run
    without it records, says so in its document, and its text is that run's report. The next real run, with --json,
    prints the recorded decision and writes nothing more."""
    plain_proj, json_proj = live_copy(tmp_path / "plain"), live_copy(tmp_path / "json")
    plain = on_clock(tmp_path, "2027-01-20T17:00:00", plain_proj)
    js = on_clock(tmp_path, "2027-01-20T17:00:00", json_proj, "--json")
    assert plain.returncode == js.returncode == 0, (plain.stderr, js.stderr)
    doc = json.loads(js.stdout)
    record = plain_proj / "data" / "forward" / "decisions.csv"
    assert doc["text"] == plain.stdout and "recorded in decisions.csv on 2027-01-20T17:00:00Z" in plain.stdout
    assert (json_proj / "data" / "forward" / "decisions.csv").read_bytes() == record.read_bytes()
    assert doc["preview"] is False and doc["decision_record"] == {"written_by_this_run": True, "why_not": None}
    assert [(d["status"], d["verdict"], d["written"]) for d in doc["tests"][0]["decisions"]] == [("final", "KEEP", True)]
    later = on_clock(tmp_path, "2027-01-21T17:00:00", json_proj, "--json")
    d = json.loads(later.stdout)
    assert [(x["status"], x["verdict"]) for x in d["tests"][0]["decisions"]] == [("recorded", "KEEP")]
    assert d["decision_record"]["written_by_this_run"] is False
    assert (json_proj / "data" / "forward" / "decisions.csv").read_bytes() == record.read_bytes()
