"""Break the price engine on purpose, in a scratch copy, and see which checks notice.

For each mutation: copy sharp-markets/src/markets into scratch, replace one piece of text (it must occur the stated
number of times), point PYTHONPATH at the copy, and run (a) my tests for that claim and (b) the auditor's script
that is supposed to back it. A check that still passes on broken code could not have failed.
The worktree itself is never changed. Output: mut_results.json and a printed table."""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

SC = Path(__file__).resolve().parents[1]
W = Path("/Users/maxzipperman/code/value-finder/.claude/worktrees/wf_4496c14b-845-1")
PY = W / "sharp-markets/.venv/bin/python"
PE = "markets/research/price_engine/"
MUT = SC / "tmp" / "mut"

# name: (claim, file, old, new, count, my tests (-k expression), auditor script or None)
MUTATIONS = {
    "entry_uses_latest_kickoff_only": ("A1", PE + "engine.py",
        "early = (sides.kickoff - sides.snap > CLOSE_WINDOW) & (sides.commence - sides.snap > CLOSE_WINDOW)",
        "early = (sides.kickoff - sides.snap > CLOSE_WINDOW)", 1, "a1", "audit_price.py"),
    "entry_timed_by_request": ("A1", PE + "quotes.py",
        'key = (r["sport"], r["odds_event_id"], r["snapshot_ts"], r["bookmaker"], r["market_key"])',
        'key = (r["sport"], r["odds_event_id"], r["requested_ts"], r["bookmaker"], r["market_key"])', 1, "a1",
        "audit_part_a.py"),
    "entry_at_exactly_60_minutes": ("A1", PE + "engine.py",
        "early = (sides.kickoff - sides.snap > CLOSE_WINDOW) & (sides.commence - sides.snap > CLOSE_WINDOW)",
        "early = (sides.kickoff - sides.snap >= CLOSE_WINDOW) & (sides.commence - sides.snap >= CLOSE_WINDOW)", 1,
        "a1", "audit_price.py"),
    "close_window_90_minutes": ("A2", PE + "engine.py", "last = last[last.kickoff - last.snap <= CLOSE_WINDOW]",
        "last = last[last.kickoff - last.snap <= pd.Timedelta(minutes=90)]", 1, "a2", "price_edgecases.py"),
    "close_is_first_quote": ("A2", PE + "engine.py",
        'last = q.sort_values("snap").drop_duplicates(["sport", "event_id", "book", "market"], keep="last")',
        'last = q.sort_values("snap").drop_duplicates(["sport", "event_id", "book", "market"], keep="first")', 1,
        "a2", "test_suite_a.py"),
    "sealed_rows_requested": ("A3", PE + "quotes.py", "rows = bulk.load_rows(cfg, calls[i:i + batch], cache)",
        "rows = bulk.load_rows(cfg, calls[i:i + batch], cache, include_sealed=True)", 1, "a3",
        "sealed_output_check.py"),
    "clv_points_away_sign": ("A6", PE + "engine.py", "[line - c_line, c_line - line, line - c_line, c_line - line]",
        "[line - c_line, line - c_line, line - c_line, c_line - line]", 1, "a6", "test_a6_signs.py"),
    "spread_close_side_sign": ("A6", PE + "engine.py", "sign = np.where(is_a[m][spr], 1.0, -1.0)",
        "sign = np.where(is_a[m][spr], -1.0, 1.0)", 1, "a6", "test_a6_signs.py"),
    "scores_not_reoriented": ("A6", PE + "outcomes.py",
        "hs, as_ = (r.home_score, r.away_score) if r.home_team == h else (r.away_score, r.home_score)",
        "hs, as_ = (r.home_score, r.away_score)", 2, "a6", "test_a6_signs.py"),
    "result_side_sign": ("A6", PE + "engine.py", 'signed = np.where(np.isin(side, ["home", "over"]), margin, -margin)',
        'signed = np.where(np.isin(side, ["home", "under"]), margin, -margin)', 1, "a6", "test_a6_signs.py"),
    "nfl_match_3_days": ("A7", PE + "outcomes.py", "if abs((r.day - day).days) <= 1]", "if abs((r.day - day).days) <= 3]",
        1, "a7", "audit_price.py"),
    "cfb_match_72_hours": ("A7", PE + "outcomes.py", "CFB_WINDOW = pd.Timedelta(hours=36)",
        "CFB_WINDOW = pd.Timedelta(hours=72)", 1, "a7", "audit_price.py"),
    "k1_lets_nan_through": ("A9", PE + "engine.py", 'if not row["clv_pin_cents"] > 0:', 'if row["clv_pin_cents"] <= 0:',
        1, "a9", "test_a8_a9.py"),
    "k3_lets_nan_through": ("A9", PE + "engine.py", 'if not row["clv_pin_wo_top_book"] > 0:',
        'if row["clv_pin_wo_top_book"] <= 0:', 1, "a9", "test_a8_a9.py"),
    "a1_uses_nominal_p": ("A9", PE + "engine.py", 'act = [row["clv_pin_p"] < ALPHA,',
        'act = [row["clv_pin_p"] < 0.05,', 1, "a9", "test_a8_a9.py"),
    "a3_fresh_nan_passes": ("A9", PE + "engine.py", 'row["clv_pin_fresh_pin"] > 0,',
        'not row["clv_pin_fresh_pin"] <= 0,', 1, "a9", "test_a8_a9.py"),
}


def build(name, rel, old, new, count):
    root = MUT / name
    if root.exists():
        shutil.rmtree(root)
    (root / "sharp-markets/src").mkdir(parents=True)
    shutil.copytree(W / "sharp-markets/src/markets", root / "sharp-markets/src/markets",
                    ignore=shutil.ignore_patterns("__pycache__"))
    for folder in ("nfl-weather", "cfb-weather"):        # model.REPO = the copy's root: the imports must resolve
        (root / folder).symlink_to(W / folder)
    f = root / "sharp-markets/src" / rel
    text = f.read_text()
    assert text.count(old) == count, (name, text.count(old))
    f.write_text(text.replace(old, new))
    return root


def run(root, args, cwd):
    env = dict(os.environ, PYTHONPATH=str(root / "sharp-markets/src"), PYTHONDONTWRITEBYTECODE="1",
               TMPDIR=str(SC / "tmp"))
    return subprocess.run([str(PY), *args], cwd=cwd, env=env, capture_output=True, text=True, timeout=900)


out = {}
only = sys.argv[1:]
for name, (claim, rel, old, new, count, k, script) in MUTATIONS.items():
    if only and name not in only:
        continue
    root = build(name, rel, old, new, count)
    probe = run(root, ["-c", "import markets.research.price_engine.engine as e; print(e.__file__)"], SC)
    assert str(root) in probe.stdout, probe.stdout + probe.stderr
    mine = run(root, ["-m", "pytest", "-q", "-p", "no:cacheprovider", "-k", k, "test_pe_mine.py"], SC / "mine")
    tail = [ln for ln in mine.stdout.splitlines() if " passed" in ln or " failed" in ln]
    aud = run(root, [script], SC / "run") if script else None
    ref = (SC / "run/logs" / f"{script}.out").read_text() if script else ""
    aud_changed = aud is not None and aud.stdout + aud.stderr != ref
    out[name] = dict(claim=claim, mine=tail[-1] if tail else mine.stdout[-300:], auditor_script=script,
                     auditor_exit=None if aud is None else aud.returncode,
                     auditor_output_changed=aud_changed)
    print(f"{name:32} {claim}  mine: {out[name]['mine']:<30} auditor {script}: exit {out[name]['auditor_exit']}, "
          f"output changed: {aud_changed}", flush=True)
    shutil.rmtree(root)
(SC / "mine/mut_results.json").write_text(json.dumps(out, indent=1))
