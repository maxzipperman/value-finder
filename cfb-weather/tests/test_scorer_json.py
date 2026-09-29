"""The scorer's --json option (for the dashboard's log of signals): with it the scorer prints one JSON document and
nothing else; without it the scorer prints exactly what it printed before. Nothing about grading, decisions or
recording changes: the document's "text" is the printed report, byte for byte, every number in it equals the number
the report prints for the same thing, and a decision is recorded, or not, by the same rules."""
import json
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
def ts(x):
    t = pd.Timestamp(x)
    return t.tz_localize("UTC") if t.tzinfo is None else t.tz_convert("UTC")


def row(gid, kick, snap, **kw):
    base = dict(rules_version="cfb-v3-2026-09-28", game_id=gid, kick_et="x", away_team="Away", home_team="Home",
                venue="V", lead_days=2, wx_src="forecast", wx_wind=18, line_src="pinnacle", mkt_total=50.5,
                mkt_under=-110, mkt_over=-110, ev_under=0.06, ht_threshold=62.6175, rule_b="no_trigger",
                rule_ht="below_threshold", start_utc=ts(kick).strftime("%Y-%m-%dT%H:%M:%SZ"),
                snapshot_utc=ts(snap).strftime("%Y-%m-%dT%H:%M:%SZ"))
    return base | kw


def sched(gid, hp=20, ap=20, completed=True, kick=None):
    s = dict(game_id=gid, home_points=hp, away_points=ap, completed=completed)
    return s | ({"start_date": ts(kick).strftime("%Y-%m-%dT%H:%M:%S.000Z")} if kick else {})


def signal(gid, kick, entry, under=-110, close=None, **kw):
    """A Rule B entry 2 days out and, when `close` is given, a later quote 3 hours out."""
    k = ts(kick)
    rows = [row(gid, k, k - pd.Timedelta(days=2), rule_b="SIGNAL", mkt_total=entry, mkt_under=under, **kw)]
    if close is not None:
        rows.append(row(gid, k, k - pd.Timedelta(hours=3), mkt_total=close))
    return rows


def ht_bet(gid, kick, total, under=-110):
    return [row(gid, kick, ts(kick) - pd.Timedelta(hours=4), rule_ht="SIGNAL", mkt_total=total, mkt_under=under)]


def mixed():
    """Rule B: won (a later quote as its close), lost (the captured close), pushed, won with no close at all, pending,
    void (moved; no result 30 days on), and a row before the test. Rule HT: won, lost, pushed, pending, void."""
    rows = ([row(100, "2026-09-26T19:00Z", "2026-09-24T14:30Z", rule_b="SIGNAL")]        # before Oct 1: excluded
            + signal(101, "2026-10-03T19:00Z", 50.5, close=49.5)
            + signal(102, "2026-10-10T19:00Z", 45.0, under=-105)
            + signal(103, "2026-10-17T19:00Z", 48.0, close=47.0)
            + signal(104, "2026-10-24T19:00Z", 52.0, under=105)
            + signal(105, "2026-11-28T19:00Z", 47.5)
            + signal(106, "2026-10-31T19:00Z", 49.0)
            + signal(107, "2026-10-24T23:00Z", 51.0)
            + ht_bet(201, "2026-10-10T23:00Z", 65.5) + ht_bet(202, "2026-10-17T23:00Z", 66.0, under=-115)
            + ht_bet(203, "2026-10-24T23:30Z", 64.0) + ht_bet(204, "2026-11-28T23:00Z", 63.5)
            + ht_bet(205, "2026-10-31T23:00Z", 70.0))
    s = [sched(100, kick="2026-09-26T19:00Z"), sched(101, 20, 20, kick="2026-10-03T19:00Z"),
         sched(102, 30, 20, kick="2026-10-10T19:00Z"), sched(103, 24, 24, kick="2026-10-17T19:00Z"),
         sched(104, 17, 13, kick="2026-10-24T19:00Z"),
         sched(105, np.nan, np.nan, completed=False, kick="2026-11-28T19:00Z"),
         sched(106, 21, 14, kick="2026-11-03T19:00Z"),                                  # moved three days
         sched(107, np.nan, np.nan, completed=False, kick="2026-10-24T23:00Z"),         # never scored
         sched(201, 30, 20, kick="2026-10-10T23:00Z"), sched(202, 40, 35, kick="2026-10-17T23:00Z"),
         sched(203, 32, 32, kick="2026-10-24T23:30Z"),
         sched(204, np.nan, np.nan, completed=False, kick="2026-11-28T23:00Z"),
         sched(205, 30, 30, kick="2026-11-02T23:00Z")]
    closes = [dict(game_id=102, close_total=45.5, line_src="pinnacle"), dict(game_id=201, close_total=64.5,
                                                                             line_src="pinnacle")]
    return rows, s, closes


def write(folder, rows, schedule, closes=None):
    folder.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(folder / "ledger.csv", index=False)
    pd.DataFrame(schedule).to_csv(folder / "sched.csv", index=False)
    if closes:
        pd.DataFrame(closes).to_csv(folder / "closes.csv", index=False)
    return folder


def rehearsal(folder):
    """The committed rehearsal ledger and the schedule scripts/rehearse_2025.py scores it against."""
    folder.mkdir(parents=True, exist_ok=True)
    shutil.copy(REHEARSAL, folder / "ledger.csv")
    g = pd.read_parquet(ROOT / "data" / "processed" / "games.parquet")
    g = g[(g.season == 2025) & ((g.home_division == "fbs") | (g.away_division == "fbs")) & g.close_total.notna()
          & g.home_points.notna() & ((g.week >= 5) | (g.season_type == "postseason"))].copy()
    g[["game_id", "home_points", "away_points"]].assign(
        start_utc=(g.start_utc + pd.Timedelta(weeks=53)).dt.strftime("%Y-%m-%dT%H:%M:%SZ")).to_csv(
        folder / "sched.csv", index=False)
    return folder


def forty_one(folder):
    """41 settled Rule B signals: FINAL after the 2026 regular season."""
    rows, s = [], []
    for i in range(41):
        k = ts("2026-10-03T19:00Z") + pd.Timedelta(days=i)
        rows += signal(1 + i, k, 50.5, close=49.5 if i % 3 else 50.0)
        s.append(sched(1 + i, 20, 20, kick=k))
    return write(folder, rows, s)


SCENARIOS = {"mixed": (lambda d: write(d, *mixed()), "2026-12-01"),
             "no signals": (lambda d: write(d, [row(100, "2026-09-26T19:00Z", "2026-09-24T14:30Z", rule_b="SIGNAL")],
                                            [sched(100, kick="2026-09-26T19:00Z")]), "2026-12-01"),
             "a final decision": (forty_one, "2026-12-21"),
             "the rehearsal": (rehearsal, "2028-03-01")}


def run(script, folder, now, *extra):
    args = [sys.executable, str(script), "--ledger", str(folder / "ledger.csv"), "--schedule",
            str(folder / "sched.csv")]
    return subprocess.run(args + (["--now", now] if now else []) + list(extra), capture_output=True, text=True)


def doc_of(folder, now, *extra):
    r = run(SCORER, folder, now, "--json", *extra)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def test_json_prints_one_document_and_nothing_else(tmp_path):
    folder = write(tmp_path, *mixed())
    r = run(SCORER, folder, "2026-12-01", "--json")
    assert r.returncode == 0, r.stderr
    doc = json.loads(r.stdout)
    assert r.stdout.count("\n") == 1 and r.stdout.startswith("{")
    assert set(doc) >= {"generated_utc", "now", "ledger", "text", "excluded", "tests", "decision_record"}
    assert doc["now"] == "2026-12-01T00:00:00Z" and doc["ledger"] == str(folder / "ledger.csv")
    assert [t["id"] for t in doc["tests"]] == ["RULE_B", "RULE_HT"]
    assert doc["excluded"] == {"before Oct 1, 2026": 1}


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
    rel = "cfb-weather/scripts/score_forward.py"
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
    shutil.copytree(ROOT / "cfbweather", proj / "cfbweather", ignore=shutil.ignore_patterns("__pycache__"))
    (proj / "scripts").mkdir()
    (proj / "scripts" / "score_forward.py").write_text(before)
    make, now = SCENARIOS[name]
    a, b = make(tmp_path / "now"), make(tmp_path / "then")
    now_out, then_out = run(SCORER, a, now), run(proj / "scripts" / "score_forward.py", b, now)
    assert now_out.returncode == then_out.returncode == 0, (now_out.stderr, then_out.stderr)
    assert now_out.stdout == then_out.stdout


# ------------------------------------------------------------------ every number equals the printed one
def section(text, tid):
    if tid == "RULE_B":
        return "\nRULE_B:" + text.split("\nRULE_B:", 1)[1].split("\nRULE_HT:", 1)[0]
    rest = "\nRULE_HT:" + text.split("\nRULE_HT:", 1)[1]
    return re.split(r"\n\nCost of waiting|\n\nDecision record:", rest)[0]


def table_rows(part, first="game_id", keep=4):
    """The bet table: {game_id: its last `keep` cells} (the middle cells can hold spaces: team names, sources)."""
    lines = part.splitlines()
    start = next((i for i, ln in enumerate(lines) if ln.split()[:1] == [first]), None)
    out = {}
    for ln in lines[start + 1:] if start is not None else []:
        if ln.startswith("  by price source") or not ln.strip() or ln.startswith("  decision"):
            break
        cells = ln.split()
        out[cells[0]] = cells[-keep:]
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
    m = re.search(r"ledger rows: (\d+); in the test: (\d+)", text)
    assert (int(m[1]), int(m[2])) == (doc["rows"]["ledger"], doc["rows"]["in_test"])
    assert doc["excluded"] == {k: int(v) for k, v in re.findall(r"^  excluded, (.+): (\d+)$", text, re.M)}
    for t in doc["tests"]:
        c, part = t["counts"], section(text, t["id"])
        head = ("\nRULE_B: " if t["id"] == "RULE_B" else "\nRULE_HT: ") + f"{c['signals']} signals" + (
            " at the last quote before kickoff" if t["id"] == "RULE_HT" else "")
        assert part.startswith(f"{head}, {c['settled']} settled, {c['pending']} pending, {c['void']} void (not graded)")
        for reason, n in t["void_reasons"].items():
            assert f"  void, {reason}: {n} (" in part
        assert sum(b["outcome"] == "void" for b in t["bets"]) == c["void"]
        assert sum(b["outcome"] == "pending" for b in t["bets"]) == c["pending"]
        if not c["settled"]:
            assert t["record"] is None and t["units"] is None
            continue
        r = t["record"]
        settled = [b for b in t["bets"] if b["outcome"] in ("won", "lost", "push")]
        s = t["secondary_clv"]
        if s["n"]:
            assert (f"mean CLV vs the captured close {s['mean']:+.2f} (95% CI " in part
                    and f"{s['without']} of {c['settled']} bets without a captured close" in part)
        else:
            assert f"no captured closes for these {c['settled']} bets" in part
        if t["id"] == "RULE_B":
            iv, mean = t["interval"], t["mean_clv"]
            assert (f"  record {r['won']}-{r['lost']}-{r['pushed']}, units {t['units']:+.2f} (ROI "
                    f"{t['roi_percent']:+.1f}% per bet placed); mean CLV {mean:+.2f}; {t['n_clv']} of {c['settled']} "
                    "bets have a primary close; ") in part
            if iv["n"] >= 2 and iv["game_days"] >= 2:
                assert f"95% CI {iv['low']:+.2f} to {iv['high']:+.2f}; " in part
                g, p = iv["grouped_half_width"], iv["plain_half_width"]
                assert f"grouped {mean - g:+.2f} to {mean + g:+.2f}" in part
                assert f"plain {mean - p:+.2f} to {mean + p:+.2f}" in part
            printed = table_rows(part)
            assert sorted(printed) == sorted(b["game_id"] for b in settled)
            for b in settled:
                close, total, clv, units = printed[b["game_id"]]
                assert close_to(close, b["close_line"]) and close_to(total, b["final_total"])
                assert close_to(clv, b["clv"]) and close_to(units, b["units"])
            assert [b["clv"] for b in settled if b["clv"] is not None] and mean == pytest.approx(
                np.mean([b["clv"] for b in settled if b["clv"] is not None]))
        else:
            decided = r["won"] + r["lost"]
            assert (f"  record {r['won']}-{r['lost']}-{r['pushed']} ({t['win_rate_percent']:.1f}%), units "
                    f"{t['units']:+.2f}, ROI {t['roi_percent']:+.1f}% per bet placed; average break-even "
                    f"{100 * t['avg_break_even']:.1f}%, one-sided p {t['p_one_sided']:.3f}") in part
            assert t["win_rate_percent"] == pytest.approx(100 * r["won"] / max(decided, 1))
            assert t["mean_clv"] is None and t["interval"] is None               # graded on results, not CLV
            printed = table_rows(part, keep=2)
            assert sorted(printed) == sorted(b["game_id"] for b in settled)
            for b in settled:
                total, units = printed[b["game_id"]]
                assert close_to(total, b["final_total"]) and close_to(units, b["units"])
        assert sum(b["units"] for b in settled) == pytest.approx(t["units"])
        assert [b["outcome"] for b in settled].count("won") == r["won"]
        assert [b["outcome"] for b in settled].count("push") == r["pushed"]
        for d in t["decisions"]:
            assert d["text"] in text and "decision (" in d["text"].splitlines()[0]
            assert ("INTERIM read" in d["text"]) == (d["status"] == "interim")


# ------------------------------------------------------------------ the cases the dashboard shows
def test_a_ledger_with_no_signals(tmp_path):
    doc = doc_of(SCENARIOS["no signals"][0](tmp_path), "2026-12-01")
    for t in doc["tests"]:
        assert t["counts"] == {"signals": 0, "settled": 0, "pending": 0, "void": 0}
        assert t["bets"] == [] and t["record"] is None and t["decisions"] == []
    assert doc["excluded"] == {"before Oct 1, 2026": 1}


def test_pending_and_void_bets(tmp_path):
    doc = doc_of(write(tmp_path, *mixed()), "2026-12-01")
    rb, ht = doc["tests"]
    by = {b["game_id"]: b for b in rb["bets"]}
    assert set(by) == {"101", "102", "103", "104", "105", "106", "107"}
    assert [by[g]["outcome"] for g in ("101", "102", "103", "104", "105")] == ["won", "lost", "push", "won", "pending"]
    assert (by["106"]["outcome"], by["106"]["void_reason"]) == ("void", VOID_MOVED)
    assert (by["107"]["outcome"], by["107"]["void_reason"]) == ("void", VOID_NO_RESULT)
    for g in ("105", "106", "107"):
        assert by[g]["units"] is None and by[g]["clv"] is None and by[g]["final_total"] is None
    assert (by["101"]["close_line"], by["101"]["close_from"], by["101"]["close_source"], by["101"]["clv"]) == (
        49.5, "later quote", "pinnacle", 1.0)
    assert (by["102"]["close_line"], by["102"]["close_from"], by["102"]["clv"], by["102"]["units"]) == (
        45.5, "captured close", -0.5, -1.0)
    assert by["102"]["close_source"] == "captured close (pinnacle)" and by["102"]["entry_price"] == -105.0
    assert (by["104"]["close_line"], by["104"]["close_from"], by["104"]["clv"]) == (None, "none", None)
    assert by["104"]["units"] == pytest.approx(1.05) and by["103"]["units"] == 0.0
    assert by["101"]["kickoff_utc"] == "2026-10-03T19:00:00Z" and by["101"]["logged_utc"] == "2026-10-01T19:00:00Z"
    assert rb["record"] == {"won": 2, "lost": 1, "pushed": 1} and rb["n_clv"] == 3
    hb = {b["game_id"]: b for b in ht["bets"]}
    assert [hb[g]["outcome"] for g in ("201", "202", "203", "204", "205")] == ["won", "lost", "push", "pending", "void"]
    assert hb["201"]["clv"] is None and hb["201"]["captured_close"] == 64.5 and hb["201"]["clv_captured"] == 1.0
    assert hb["202"]["entry_price"] == -115.0 and hb["202"]["units"] == -1.0
    assert ht["record"] == {"won": 1, "lost": 1, "pushed": 1} and ht["p_one_sided"] is not None


def test_a_recorded_decision(tmp_path):
    """--json records by the same rules as the plain report: a --test-record run writes the same record either way,
    and the next run hands over the recorded decision."""
    plain, js = forty_one(tmp_path / "plain"), forty_one(tmp_path / "json")
    p = run(SCORER, plain, "2026-12-21", "--test-record")
    doc = doc_of(js, "2026-12-21", "--test-record")
    assert doc["text"] == p.stdout
    assert (plain / "decisions.csv").read_bytes() == (js / "decisions.csv").read_bytes()
    d = doc["tests"][0]["decisions"]
    assert [(x["status"], x["written"]) for x in d] == [("final", True)] and d[0]["verdict"] == "KEEP"
    assert doc["decision_record"] == {"written_by_this_run": True, "why_not": None}
    later = doc_of(js, "2027-01-10")
    d = later["tests"][0]["decisions"][0]
    assert (d["status"], d["verdict"], d["recorded"]["verdict"], d["recorded"]["n_bets"]) == (
        "recorded", "KEEP", "KEEP", 41)
    assert d["recorded"]["decided_utc"] == "2026-12-21T00:00:00Z"
    assert (js / "decisions.csv").read_bytes() == (plain / "decisions.csv").read_bytes()


def test_json_with_now_never_records(tmp_path):
    folder = forty_one(tmp_path / "t")
    doc = doc_of(folder, "2026-12-21")
    d = doc["tests"][0]["decisions"][0]
    assert (d["status"], d["verdict"], d["written"]) == ("final", "KEEP", False)
    assert "not recorded: a run with --now is a preview." in d["text"]
    assert doc["decision_record"] == {"written_by_this_run": False, "why_not": "a run with --now is a preview"}
    assert not (folder / "decisions.csv").exists() and not (folder / ".decisions.lock").exists()
    proj = tmp_path / "proj"
    shutil.copytree(ROOT / "cfbweather", proj / "cfbweather", ignore=shutil.ignore_patterns("__pycache__"))
    (proj / "scripts").mkdir()
    shutil.copy(SCORER, proj / "scripts" / "score_forward.py")
    fwd = proj / "data" / "forward"
    fwd.mkdir(parents=True)
    shutil.copy(folder / "ledger.csv", fwd / "ledger.csv")
    r = subprocess.run([sys.executable, str(proj / "scripts" / "score_forward.py"), "--ledger", str(fwd / "ledger.csv"),
                        "--schedule", str(folder / "sched.csv"), "--now", "2026-12-21", "--json"],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout)["tests"][0]["decisions"][0]["written"] is False
    assert sorted(p.name for p in fwd.iterdir()) == ["ledger.csv"]
