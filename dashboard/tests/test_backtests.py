"""The Backtests screen: every chart file's numbers recomputed here from the committed table it names (independently of
dashboard/tools/build_charts.py), the axis rules, the screen as drawn in Node, and a chart file that is missing,
empty or damaged shown as a plain sentence."""
from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
import math
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from conftest import CONTENT, STATUS_MD, copy_content, make_home, make_root, make_store

from vfdash import api, backtests

REPO = Path(__file__).resolve().parents[2]
CHARTS = CONTENT / "charts"
TOOL = REPO / "dashboard" / "tools" / "build_charts.py"
HERE = Path(__file__).resolve().parent
NODE = shutil.which("node") or ("/opt/node22/bin/node" if Path("/opt/node22/bin/node").exists() else None)
WEATHER_PY = next((p for p in (REPO / "nfl-weather" / ".venv" / "bin" / "python",
                               REPO / "cfb-weather" / ".venv" / "bin" / "python") if p.exists()), None)
BREAK_EVEN = 52.38


def tool():
    was = sys.dont_write_bytecode                         # the tool sets it for itself; keep this process as it was
    spec = importlib.util.spec_from_file_location("build_charts", TOOL)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    sys.dont_write_bytecode = was
    return mod


def chart(cid: str) -> dict:
    return json.loads((CHARTS / f"{cid}.json").read_text(encoding="utf-8"))


def rows(path: str) -> list[dict]:
    with (REPO / path).open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def pick(table: list[dict], **match) -> dict:
    hits = [r for r in table if all(r[k] == v for k, v in match.items())]
    assert len(hits) == 1, (match, len(hits))
    return hits[0]


def close(a, b, tol=1e-9) -> bool:
    return abs(float(a) - float(b)) <= tol


def series(c: dict, sid: str, panel: int = 0) -> list:
    return next(s for s in c["plot"]["panels"][panel]["series"] if s["id"] == sid)["points"]


def file_ids() -> list[str]:
    return [cid for _, ids in backtests.GROUPS for cid in ids
            if cid not in backtests.LIVE and cid not in backtests.NOT_CHARTED]


# ---------------------------------------------------------------- the files themselves

def test_the_tool_and_the_server_list_the_same_charts():
    t = tool()
    server = [(h, [i for i in ids if i not in backtests.NOT_CHARTED]) for h, ids in backtests.GROUPS]
    assert server == t.GROUPS and backtests.LIVE == t.LIVE
    assert sorted(file_ids()) == sorted(t.BUILDERS) == sorted(p.stem for p in CHARTS.glob("*.json"))
    assert set(backtests.NAMES) == set(file_ids())


@pytest.mark.parametrize("cid", file_ids())
def test_each_file_is_in_shape_and_names_its_sources_as_committed(cid):
    c = chart(cid)
    assert backtests.shape_problem(c, cid) is None
    assert c["built_by"] == "dashboard/tools/build_charts.py" and re.fullmatch(r"\d{4}-\d{2}-\d{2}", c["date"])
    for s in c["sources"]:
        data = (REPO / s["path"]).read_bytes()
        blob = hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()
        assert s["blob"] == blob, f"{s['path']} changed since {cid} was built: rerun dashboard/tools/build_charts.py"
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", s["changed"]) and s["changed"] <= c["date"]
    assert c["date"] == max(s["changed"] for s in c["sources"])
    assert isinstance(c["n"], int) and c["n"] > 0 and c["sample"]
    for w in c["writeups"]:
        assert (REPO / w["path"]).is_file()
        if w["anchor"]:                            # the section the chart illustrates is still in the write-up
            assert w["section"].split(":")[0].split(" (")[0] in (REPO / w["path"]).read_text(encoding="utf-8")


# ---------------------------------------------------------------- every number, recomputed from its source

def test_wind_and_scoring_numbers():
    c = chart("wind-and-scoring")
    m = rows("nfl-weather/output/tables/bet_market_vs_reality.csv")
    t = rows("nfl-weather/output/tables/bet_totals_by_bucket.csv")
    s = pick(rows("nfl-weather/output/tables/strategies.csv"), rule="Wind 15+ mph → under", test="vs close 1999–2025")
    for term, label, bucket in (("wind_10_14", "10–14 mph", "Wind 10–14"), ("wind_15_19", "15–19 mph", "Wind 15–19"),
                                ("wind_20p", "20+ mph", "Wind 20+")):
        for sid, outcome in (("scored", "total"), ("close", "total_line")):
            r = pick(m, outcome=outcome, term=term, era="All 1999–2025")
            p = next(q for q in series(c, sid) if q[0] == label)
            assert [close(p[1], r["coef"]), close(p[2], r["lo"]), close(p[3], r["hi"])] == [True] * 3
        games = int(pick(t, era="All", bucket=bucket)["games"])
        assert c["plot"]["panels"][0]["tips"][label] == [f"{games:,} outdoor games"]
    a, l = (float(pick(m, outcome=o, term="wind_15_19", era="All 1999–2025")["coef"]) for o in ("total", "total_line"))
    assert f"{abs(a):.1f} fewer points against {abs(l):.1f} off the closing total" in c["title"]
    assert c["n"] == int(pick(m, outcome="total", term="wind_15_19", era="All 1999–2025")["n"]) == 7276
    assert c["bar"]["tests"][0]["p"] == float(s["p"]) and f"{float(s['win_pct']) * 100:.1f}%" in c["bar"]["tests"][0]["label"]


@pytest.mark.parametrize("sport, proj", [("cfb", "cfb-weather"), ("nfl", "nfl-weather")])
def test_the_season_by_season_replay_numbers(sport, proj):
    c = chart(f"wind-rule-{sport}-seasons")
    table = rows(f"{proj}/output/tables/mos_replay_seasons.csv")
    era = pick(rows(f"{proj}/output/tables/mos_replay_eras.csv"), sample="pooled")
    seasons = [r for r in table if r["sample"] != "pooled"]
    pooled = pick(table, sample="pooled")
    pts = series(c, "close")
    assert [p[0] for p in pts] == [r["sample"] for r in seasons] == c["plot"]["panels"][0]["x"]["labels"]
    for p, r in zip(pts, seasons):
        lo, hi = (float(x) for x in r["close_win_ci"].split("-"))
        assert (p[1], p[2], p[3]) == (float(r["close_win_pct"]), lo, hi)
    assert c["plot"]["panels"][0]["counts"]["points"] == [[r["sample"], int(r["close_n"])] for r in seasons]
    refs = {r["role"]: r["value"] for r in c["plot"]["panels"][0]["refs"]}
    assert refs == {"breakeven": BREAK_EVEN, "pooled": float(pooled["close_win_pct"])}
    below = sum(float(r["close_win_pct"]) < BREAK_EVEN for r in seasons)
    assert f"won {float(pooled['close_win_pct']):.1f}%" in c["title"]
    assert f"below it in {below} of {len(seasons)} seasons" in c["title"]
    assert (below, len(seasons)) == ((5, 20) if sport == "cfb" else (7, 22))         # as both write-ups say
    assert c["n"] == int(pooled["close_n"])
    test = c["bar"]["tests"][0]
    assert test["p"] == max(float(pooled["close_p_one_sided"]), float(era["grouped_p"]))
    assert c["table"]["rows"][-1][:3] == ["All", f"{int(pooled['close_n']):,}",
                                         pooled["close_record"].replace("-", "–")]
    assert f"{int(pooled['obs_also_signal']):,} of the {int(pooled['close_n']):,} signals" in c["not_shows"]


def test_the_cumulative_units_agree_with_the_season_records():
    """From the season tables alone: each season's units at -110 (a win pays 100/110) from its record, the running
    total at each season's end, and the chart's last point on each line."""
    c = chart("wind-rule-units")
    by_season = {r[0]: r for r in c["table"]["rows"]}
    for sport, proj, col in (("cfb", "cfb-weather", 1), ("nfl", "nfl-weather", 5)):
        run = 0.0
        for r in rows(f"{proj}/output/tables/mos_replay_seasons.csv"):
            if r["sample"] == "pooled":
                continue
            w, l, p = (int(x) for x in r["close_record"].split("-"))
            units = w * 100 / 110 - l
            run += units
            cells = by_season[r["sample"]][col:col + 4]
            assert cells[0] == r["close_n"] and cells[2] == ("+" if units > 0 else "−") + f"{abs(units):.1f}"
            assert cells[3] == ("+" if run > 0 else "−") + f"{abs(run):.1f}"
        pts = series(c, sport)
        assert close(pts[-1][1], round(run, 4), 1e-3)
        n = int(pick(rows(f"{proj}/output/tables/mos_replay_seasons.csv"), sample="pooled")["close_n"])
        assert len(pts) == n and f"({n:,} signals)" in next(s["name"] for s in c["plot"]["panels"][0]["series"]
                                                            if s["id"] == sport)
    assert "+95.0 units after 1,284 college football signals and +45.4 after 607 NFL signals" in c["title"]


@pytest.mark.skipif(WEATHER_PY is None, reason="no weather project's Python to read the replay's parquet files")
def test_the_cumulative_units_signal_by_signal_from_the_parquet_files():
    script = """
import json, sys, pandas as pd
out = {}
for sport, proj in (("cfb", "cfb-weather"), ("nfl", "nfl-weather")):
    d = pd.read_parquet(f"{proj}/data/processed/mos_replay.parquet")
    s = d[d.mos_signal == True].sort_values(["start_utc", "game_id"], kind="mergesort")
    cum, pts = 0.0, []
    for w, p, t in zip(s.under_win, s.push, s.start_utc.dt.tz_convert("America/New_York")):
        cum += 0.0 if p else (100 / 110 if w else -1.0)
        pts.append([t.strftime("%Y-%m-%d"), round(cum, 4)])
    out[sport] = pts
print(json.dumps(out))
"""
    got = json.loads(subprocess.run([str(WEATHER_PY), "-c", script], cwd=REPO, capture_output=True, text=True,
                                    check=True, timeout=120).stdout)
    c = chart("wind-rule-units")
    for sport in ("cfb", "nfl"):
        assert [p[:2] for p in series(c, sport)] == got[sport]


def test_the_opener_against_the_close_numbers():
    c = chart("wind-rule-opener-vs-close")
    labels = c["plot"]["panels"][0]["rows"]
    got_open, got_close = series(c, "open"), series(c, "close")
    i = 0
    for proj, sport in (("cfb-weather", "College football"), ("nfl-weather", "NFL")):
        for r in rows(f"{proj}/output/tables/mos_replay_eras.csv"):
            assert labels[i].startswith(sport + ", ") and f"({int(r['open_n']):,} games with an opener" in labels[i]
            for got, key in ((got_open, "open"), (got_close, "closeop")):
                lo, hi = (float(x) for x in r[f"{key}_win_ci"].split("-"))
                assert got[i] == [labels[i], float(r[f"{key}_win_pct"]), lo, hi]
            i += 1
    assert i == len(labels) == 8
    cfb = pick(rows("cfb-weather/output/tables/mos_replay_eras.csv"), sample="pooled")
    nfl = pick(rows("nfl-weather/output/tables/mos_replay_eras.csv"), sample="pooled")
    d1 = float(cfb["open_win_pct"]) - float(cfb["closeop_win_pct"])
    d2 = float(nfl["open_win_pct"]) - float(nfl["closeop_win_pct"])
    assert f"won {d1:.1f} points more often at the opener" in c["title"] and f"and {d2:.1f} in the NFL" in c["title"]
    assert c["bar"]["tests"] == [] and c["bar"]["none"]


@pytest.mark.parametrize("sport, proj", [("cfb", "cfb-weather"), ("nfl", "nfl-weather")])
def test_the_forecast_error_numbers(sport, proj):
    c = chart(f"forecast-error-{sport}")
    table = rows(f"{proj}/output/tables/mos_bias_by_season.csv")
    for panel, col in ((0, "mean_error"), (1, "mae")):
        for s in c["plot"]["panels"][panel]["series"]:
            lead = s["id"].removeprefix("lead")
            want = [[r["season"], float(r[col])] for r in table if r["lead"] == lead and r["season"] != "all"]
            assert s["points"] == want
    a1 = pick(table, season="all", lead="1")
    assert f"{float(a1['mae']):.2f} mph" in c["title"] and f"{float(a1['mean_error']):.2f} mph" in c["title"]
    assert c["n"] == int(a1["n"]) and len(c["table"]["rows"]) == len(table)
    if sport == "nfl":                                      # "the gap has grown lately" (nfl-weather/README.md)
        assert "+1.82 and +2.03 mph in 2024 and 2025" in c["title"]
    else:
        assert "in every season" in c["title"] and all(float(r["mean_error"]) > 0 for r in table)


def test_the_money_gate_numbers():
    c = chart("money-gate")
    t = tool()
    case = [r for r in rows("strategy-research/output/money_gate.csv") if r["section"] == "gates"
            and r["sport"] == "CFB Rule B" and r["dependence"] == "realistic dependence" and r["volume"] == "40"
            and r["zero_share"] == "0" and r["floor"] == "0"]
    labels = c["plot"]["panels"][0]["rows"]
    assert len(labels) == len(t.GATE_WORDS) == 14
    for label, (gate, signals) in zip(labels, t.GATE_WORDS):
        for sid, scen in (("none", "no edge"), ("half", "half the move"), ("full", "full move")):
            r = pick(case, gate=gate, signals=signals, scenario=scen)
            assert close(dict((p[0], p[1]) for p in series(c, sid))[label], float(r["p_pass"]) * 100, 1e-6)
    # the write-up's table: today's gate 50% / 86% / 98%; the recommended gate 2.6% / 28% / 80%
    assert "no edge 50% of the time" in c["title"] and "one 2.6% of the time" in c["title"]
    assert "28% (half the historical move) to 80% (all of it)" in c["title"]
    dates = [r for r in rows("strategy-research/output/money_gate.csv") if r["section"] == "dates"
             and r["sport"] == "CFB Rule B" and r["dependence"] == "realistic dependence" and r["volume"] == "40"
             and r["gate"] == "sequential OBF, fixed bar 2.75 CFB / 2.14 NFL"]
    half, full = (float(pick(dates, scenario=s_)["p_money_this_season"]) * 100 for s_ in ("half the move", "full move"))
    assert f"lower: {half:.0f}% and {full:.0f}% for the recommended gate" in c["not_shows"]
    assert (round(half), round(full)) == (21, 65)                # as the write-up says


def test_the_keep_test_numbers():
    c = chart("keep-test")
    base = [r for r in rows("strategy-research/output/keep_test_check.csv") if r["section"] == "keep test at 40 bets"
            and r["scenario"] == "no edge"]
    labels = c["plot"]["panels"][0]["rows"]
    words = {"independent": "bets independent", "realistic dependence": "realistic correlation",
             "stress dependence": "stress correlation"}
    seen = 0
    for r in base:
        if r["case"] not in words:
            continue
        sport = "College football" if r["sport"] == "CFB Rule B" else "NFL"
        label = f"{sport}, {r['volume']} signals a season, {words[r['case']]}"
        assert label in labels
        for sid in ("plain", "grouped", "wider"):
            assert close(dict((p[0], p[1]) for p in series(c, sid))[label], float(r[sid]) * 100, 1e-6)
        seen += 1
    assert seen == len(labels) == 15
    # the write-up: 2.8 to 3.0% in college football, 5.8 to 7.4% in the NFL (realistic case), against 2.5%
    assert "2.8 to 3.0% of the time in college football and 5.8 to 7.4% in the NFL" in c["title"]
    assert c["plot"]["panels"][0]["refs"][0]["value"] == 2.5


def test_the_key_number_numbers():
    c = chart("key-numbers")
    prices = [r for r in rows("strategy-research/output/landing_mass_prices.csv") if r["market"] == "total"
              and r["cohort"] == "all"]
    loso = rows("strategy-research/output/landing_mass_loso.csv")
    for panel, sport in ((0, "NFL"), (1, "CFB")):
        mine = [r for r in prices if r["sport"] == sport]
        for sid, model in (("on", "raw, market on K"), ("half", "raw, market a half-point from K")):
            want = [[int(float(r["key"])), round(float(r["p_push"]) * 100, 4), int(float(r["raw_games"])),
                     int(float(r["raw_landed"]))] for r in mine if r["model"] == model and float(r["raw_games"]) > 0]
            assert series(c, sid, panel) == want
            for p in want:                                   # the share is the count over the games
                assert close(p[1], round(p[3] / p[2] * 100, 2), 0.01)
        for sid, model in (("table", "table"), ("registered", "residual")):
            want = [[int(float(r["key"])), round(float(r["p_push"]) * 100, 4)] for r in mine
                    if r["model"] == model and float(r["line"]) == float(r["key"])]
            assert series(c, sid, panel) == want
    declared = [r for r in loso if r["variant"] == "primary" and r["market"] == "total" and r["metric"] in ("under", "push")]
    assert len(declared) == 8 and all(r["verdict"] == "no difference shown" for r in declared)
    assert "did not beat the registered pricing model on any of the 8 comparisons declared before the run" in c["title"]
    smallest = min(float(r[k]) for r in loso for k in ("p_t", "p_signflip") if r[k])
    assert c["bar"]["tests"][0]["p"] == smallest and c["bar"]["tests"][0]["p_words"] == "p = 0.00055"


def test_the_line_move_numbers():
    c = chart("line-moves")
    tot = pick(rows("strategy-research/output/line_moves.csv"), market="total")
    oc = rows("nfl-weather/output/tables/bet_open_vs_close.csv")
    for p, b in zip(series(c, "move", 0), ("Wind 0–4", "Wind 5–9", "Wind 10–14", "Wind 15–19", "Wind 20+")):
        r = pick(oc, bucket=b)
        m, se = float(r["mean_move"]), float(r["move_se"])
        assert close(p[1], round(m, 4)) and close(p[2], round(m - 1.96 * se, 4)) and close(p[3], round(m + 1.96 * se, 4))
    assert close(c["plot"]["panels"][0]["refs"][1]["value"], round(float(tot["mean_move"]), 4))
    tiers = rows("strategy-research/output/cfb_open_vs_close.csv")
    assert [p[1] for p in series(c, "size", 1)] == [round(float(r["mean_abs_move"]), 4) for r in tiers]
    assert f"fell {abs(float(tot['mean_move'])):.2f} points" in c["title"]
    assert c["n"] == int(tot["games"]) + sum(int(r["games"]) for r in tiers)


@pytest.mark.skipif(WEATHER_PY is None, reason="no weather project's Python (the tool needs pandas)")
def test_the_build_tools_check_passes_and_writes_nothing():
    before = {p.name: p.stat().st_mtime_ns for p in CHARTS.glob("*.json")}
    r = subprocess.run([str(WEATHER_PY), str(TOOL), "--check"], cwd=REPO, capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, r.stderr
    assert {p.name: p.stat().st_mtime_ns for p in CHARTS.glob("*.json")} == before


def test_the_build_tool_writes_only_its_chart_files():
    """What it can write, read from its code: one write_text, to OUT / name, and nothing that removes or moves."""
    src = TOOL.read_text()
    assert src.count(".write_text(") == 1 and "p = OUT / name" in src and 'OUT = Path("dashboard") / "content" / "charts"' in src
    for banned in ("write_bytes", "to_csv", "to_parquet", "unlink", "rmtree", "os.remove", "rename(", "replace(p",
                   "open(", "import nflweather", "import cfbweather"):
        assert banned not in src.replace("with src.use(path).open(newline", ""), banned


# ---------------------------------------------------------------- the axis rules

def test_axis_rules_in_every_file():
    for cid in file_ids():
        c = chart(cid)
        for pn in c["plot"]["panels"]:
            ax = pn["x"] if c["plot"]["layout"] == "rows" else pn["y"]
            refs = {r.get("role"): r["value"] for r in pn.get("refs", [])}
            if ax.get("kind") == "win_rate" or ax.get("unit") == "%" and "win" in ax.get("label", "").lower():
                assert ax["kind"] == "win_rate" and ax["floor_at_most"] <= 40, cid
                assert 52.38 <= refs.get("breakeven", 0) <= 52.4, cid
            elif ax.get("min") is None and not ax.get("log"):
                assert ax.get("zero") is True, (cid, "a value axis that isn't a win rate starts at zero")
            elif ax.get("min") is not None:
                assert ax["min"] == 0, cid


# ---------------------------------------------------------------- the screen

def test_the_screen_answer(store):
    d = api.backtests(store)
    assert "error" not in d and not [n for n in d["notes"] if "chart" in n.lower()]
    assert d["header"]["last_written"].startswith("Charts from tables dated up to ")
    first, second, third = d["intro"]
    assert "drawn from tables committed in the repo" in first
    assert "not a forward result" in second
    assert third == ("None of the 17 results in the evidence list has cleared the project's multiple-testing bar "
                     "(p < 0.000185, 0.05 / 271 variants).")
    ids = [c["id"] for g in d["groups"] for c in g["charts"]]
    assert ids == [i for _, group in backtests.GROUPS for i in group]
    by = {c["id"]: c for g in d["groups"] for c in g["charts"]}
    for cid in file_ids():
        c = by[cid]
        assert c["missing"] == "" and c["title"] and c["sample"] and c["bar_lines"] and c["sources"]
        assert all(s["url"].startswith("https://github.com/maxzipperman/value-finder/blob/main/") for s in c["sources"])
    seasons = by["wind-rule-cfb-seasons"]["bar_lines"][0]
    assert seasons == ("All 20 seasons against break-even: one-sided p = 0.0028 (0.0039 grouped by game day). Does not "
                       "clear the multiple-testing bar, p < 0.000185 (0.05 / 271 variants).")
    assert by["money-gate"]["bar_lines"] == ["A simulation of a staking rule, not a betting test: it adds no variants."]
    assert "not charted: no table committed in the repo holds its record by season" in by["high-total-seasons"]["not_charted"]


def test_the_bar_is_read_from_status_md(root, home):
    """With the fixture's 288 variants the bar is 0.05 / 288; a result below it would clear (none does)."""
    status = root / "STATUS.md"
    status.write_text(STATUS_MD.replace("Then **271**, so new analyses use p < 0.000185 (0.05 / 271).",
                                        "Then **271**. Then **288**, so p < 0.000174."))
    d = api.backtests(make_store(root, home))
    assert d["variants"] == 288 and d["bar"] == "0.000174"
    by = {c["id"]: c for g in d["groups"] for c in g["charts"]}
    assert by["evidence-vs-bar"]["title"] == ("None of the 8 results with a p-value clears the project's bar of "
                                              "p < 0.000174; the closest is p = 0.0006")
    refs = {r["role"]: r["value"] for r in by["evidence-vs-bar"]["plot"]["panels"][0]["refs"]}
    assert refs == {"line": 0.05, "bar": 0.05 / 288}
    status.write_text("# Status\n\nNo variants bullet here.\n")
    d = api.backtests(make_store(root, home))
    by = {c["id"]: c for g in d["groups"] for c in g["charts"]}
    assert "could not be read from STATUS.md" in by["wind-rule-cfb-seasons"]["bar_lines"][0]
    assert by["evidence-vs-bar"]["clears"] is None
    assert "The running count of variants could not be read from STATUS.md's “Variants” bullet." in d["notes"]


def test_the_evidence_chart_places_each_result_at_its_p_value(store):
    d = api.backtests(store)
    c = next(c for g in d["groups"] for c in g["charts"] if c["id"] == "evidence-vs-bar")
    ev = json.loads((CONTENT / "evidence.json").read_text())
    want = [(e["title"], backtests.p_of(e["p_value"])) for e in ev if backtests.p_of(e.get("p_value")) is not None]
    assert [tuple(p) for p in c["plot"]["panels"][0]["series"][0]["points"]] == want and len(want) == 8
    notes = c["plot"]["panels"][0]["notes"]
    assert all(notes[t] == f"n = {e['n']:,}" for t, e in ((e["title"], e) for e in ev) if t in notes)
    assert backtests.p_of("0.028 (one-sided; 0.021 grouped by game day)") == 0.028
    assert backtests.p_of("≈ 0.007") == 0.007 and backtests.p_of("0.0006 (t-test on the 20 seasons)") == 0.0006
    assert backtests.p_of(0.0035) == 0.0035 and backtests.p_of(None) is None and backtests.p_of("n/a") is None
    assert backtests.p_of(True) is None and backtests.p_of("2.5") is None


def test_a_result_that_clears_is_named_in_the_opening_sentences(root, home, tmp_path):
    content = copy_content(tmp_path / "content")
    ev = json.loads((content / "evidence.json").read_text())
    ev[0]["clears_bar"] = True
    (content / "evidence.json").write_text(json.dumps(ev))
    d = api.backtests(make_store(root, home, content=content))
    assert d["intro"][2] == (f"Of the 17 results in the evidence list, only this one has cleared the project's "
                             f"multiple-testing bar (p < 0.000185, 0.05 / 271 variants): {ev[0]['title']}.")


@pytest.mark.parametrize("damage", ["missing", "empty", "cut", "not a chart", "wrong id", "bad points", "huge", "deep"])
def test_a_damaged_chart_file_is_one_plain_sentence(root, home, tmp_path, damage):
    content = copy_content(tmp_path / "content")
    f = content / "charts" / "money-gate.json"
    if damage == "missing":
        f.unlink()
    elif damage == "empty":
        f.write_text("")
    elif damage == "cut":
        f.write_text(f.read_text()[:500])
    elif damage == "not a chart":
        f.write_text("[1, 2, 3]")
    elif damage == "wrong id":
        f.write_text(f.read_text().replace('"id": "money-gate"', '"id": "keep-test"'))
    elif damage == "bad points":
        c = json.loads(f.read_text())
        c["plot"]["panels"][0]["series"][0]["points"][0][1] = "fifty"
        f.write_text(json.dumps(c))
    elif damage == "huge":
        f.write_text(" " * (backtests.MAX_BYTES + 1))
    else:
        f.write_text("[" * 100_000 + "]" * 100_000)
    store = make_store(root, home, content=content)
    d = api.backtests(store)
    assert "error" not in d
    by = {c["id"]: c for g in d["groups"] for c in g["charts"]}
    why = by["money-gate"]["missing"]
    assert why.startswith("The chart “The paper-to-money gate” is not shown: ") and why.endswith(".")
    assert "dashboard/content/charts/money-gate.json" in why and "Traceback" not in why
    assert by["keep-test"]["missing"] == "" and by["keep-test"]["title"]         # the rest is drawn
    if NODE:
        page = draw(tmp_path, d)
        sec = section(page, "money-gate")
        assert text(sec) == "The paper-to-money gate" + why and not list(find(sec, "svg"))


def test_the_screen_with_no_chart_folder_at_all(root, home, tmp_path):
    content = copy_content(tmp_path / "content")
    shutil.rmtree(content / "charts")
    d = api.backtests(make_store(root, home, content=content))
    missing = [c for g in d["groups"] for c in g["charts"] if c.get("missing")]
    assert len(missing) == len(file_ids()) and d["header"]["last_written"] == "No chart file could be read"


# ---------------------------------------------------------------- the screen as drawn (Node)

def draw(tmp_path, answer: dict, hover: bool = False) -> dict:
    f = tmp_path / "backtests.json"
    f.write_text(json.dumps(answer, ensure_ascii=False))
    out = subprocess.run([NODE, str(HERE / "render_page.mjs"), str(HERE.parent / "vfdash" / "static" / "app.js"),
                          "#backtests", str(f)] + (["hover"] if hover else []), capture_output=True, text=True,
                         timeout=60, check=True)
    return json.loads(out.stdout)


def text(n) -> str:
    return n["text"] if "text" in n else "".join(text(k) for k in n["kids"])


def find(n, tag, cls=None):
    if "tag" in n:
        if n["tag"] == tag and (cls is None or cls in (n["attrs"].get("class") or n.get("cls") or "").split()):
            yield n
        for k in n["kids"]:
            yield from find(k, tag, cls)


def section(page, cid):
    return next(s for s in find(page, "section") if s["attrs"].get("data-chart") == cid)


@pytest.mark.skipif(NODE is None, reason="Node is not installed")
def test_the_screen_as_drawn_has_every_chart(store, tmp_path):
    d = api.backtests(store)
    page = draw(tmp_path, d)
    drawn = text(page)
    assert drawn.startswith("Backtests" + "".join(d["intro"]))
    assert "!" not in drawn and "could not be drawn" not in drawn and "Part of this screen" not in drawn
    for g in d["groups"]:
        assert g["heading"] in drawn
        for c in g["charts"]:
            sec = section(page, c["id"])
            if c.get("not_charted"):
                assert text(sec) == c["not_charted"]
                continue
            svgs = list(find(sec, "svg"))
            assert len(svgs) == len(c["plot"]["panels"]), c["id"]
            words = text(sec)
            for part in (c["title"], c["name"], c["shows"], c["not_shows"], c["sample"], *c["bar_lines"]):
                assert part in words, (c["id"], part)
            for s in c["sources"]:
                links = [a for a in find(sec, "a") if text(a) == s["path"]]
                assert links and links[0]["attrs"]["href"] == s["url"] and links[0]["attrs"]["rel"] == "noreferrer noopener"
            tables = list(find(sec, "table"))
            assert len(tables) == 1 and len(list(find(next(find(tables[0], "tbody")), "tr"))) == len(c["table"]["rows"])
            assert "Show the numbers" in words
            for svg in svgs:                             # every mark's value is inside its axis: nothing is cropped
                lo, hi = float(svg["attrs"]["data-axis-min"]), float(svg["attrs"]["data-axis-max"])
                for m in find(svg, "circle"):
                    if "data-value" in m["attrs"]:
                        assert lo - 1e-9 <= float(m["attrs"]["data-value"]) <= hi + 1e-9, c["id"]


@pytest.mark.skipif(NODE is None, reason="Node is not installed")
def test_win_rate_axes_as_drawn_start_at_40_or_lower_and_show_break_even(store, tmp_path):
    page = draw(tmp_path, api.backtests(store))
    win = [s for s in find(page, "svg") if s["attrs"].get("data-axis-kind") == "win_rate"]
    assert len(win) == 3                                 # both season charts and the opener against the close
    for svg in win:
        assert float(svg["attrs"]["data-axis-min"]) <= 40 and float(svg["attrs"]["data-axis-max"]) >= 52.4
        be = [ln for ln in find(svg, "line", "breakeven")]
        assert len(be) == 1 and 52.38 <= float(be[0]["attrs"]["data-value"]) <= 52.4
    for svg in find(page, "svg"):                        # every value axis that isn't a win rate or a p-value has 0
        kind = svg["attrs"].get("data-axis-kind")
        if kind not in ("win_rate", "p"):
            assert float(svg["attrs"]["data-axis-min"]) <= 0 <= float(svg["attrs"]["data-axis-max"]), kind
    p_axis = [s for s in find(page, "svg") if s["attrs"].get("data-axis-kind") == "p"]
    assert len(p_axis) == 1
    bar = [ln for ln in find(p_axis[0], "line", "bar")]
    assert len(bar) == 1 and math.isclose(float(bar[0]["attrs"]["data-value"]), 0.05 / 271)


@pytest.mark.skipif(NODE is None, reason="Node is not installed")
def test_hovering_reads_out_the_exact_numbers(store, tmp_path):
    d = api.backtests(store)
    hovers = draw(tmp_path, d, hover=True)["hovers"]
    charts = [c for g in d["groups"] for c in g["charts"] if c.get("plot")]
    panels = sum(len(c["plot"]["panels"]) for c in charts)
    assert len(hovers) == 3 * panels                     # three points on every panel, each with a read-out
    assert not [x for x in hovers if "undefined" in x or "NaN" in x or "null" in x]
    joined = "\n".join(hovers)
    for want in ("Win rate at the close, with its 95% interval: ", "Signals: ", "units", "p-value: ", "No edge: ",
                 "Closed on K: ", " of ", "Plain interval: ", "At the opener: ", "Points scored (both teams): "):
        assert want in joined, want
    cfb2006 = next(x for x in hovers if x.startswith("2006Win rate at the close"))
    assert cfb2006.startswith("2006Win rate at the close, with its 95% interval: 62.5% (45.3% to 77.1%)")
    assert "15–19 mphPoints scored (both teams): −4.18 points (−5.63 to −2.73)" in joined
    assert "Total 44Closed on K: 2.8% (4 of 145)Closed a half-point from K: 5.1% (16 of 311)" in joined


@pytest.mark.skipif(NODE is None, reason="Node is not installed")
def test_the_navigation_has_backtests_after_signals():
    html = (HERE.parent / "vfdash" / "static" / "index.html").read_text()
    order = re.findall(r'data-screen="([a-z]+)"', html)
    assert order[:3] == ["home", "signals", "backtests"]


def test_the_screens_words_are_plain(store):
    from test_wording import strings
    d = api.backtests(store)
    said = [s for s in strings(d, skip=("id", "kind", "mark", "color", "role", "layout", "url", "path", "blob",
                                        "health", "last_written_utc", "generated_utc", "sport")) if s]
    assert not [s for s in said if "!" in s]
    assert not [s for s in said if re.search(r"\bCFB\b|\bRULE_B\b|\bRULE_HT\b", s)]
    sentences = [s for s in said if " " in s and s.endswith(".")]
    assert sentences and all(s[:1].isupper() or s[:1] in "+−0123456789" for s in sentences), [
        s for s in sentences if not (s[:1].isupper() or s[:1] in "+−0123456789")]


def test_the_backtests_endpoint_over_http_changes_nothing(tmp_path):
    from test_readonly import state
    root, home = make_root(tmp_path / "f"), make_home(tmp_path / "f")
    content = copy_content(tmp_path / "content")
    before = state(root, home, content)
    from conftest import Running
    served = Running(make_store(root, home, content=content))
    try:
        for _ in range(3):
            status, body, headers = served.get("/api/backtests")
            assert status == 200 and headers["Content-Type"].startswith("application/json")
            assert "error" not in json.loads(body)
    finally:
        served.close()
    assert state(root, home, content) == before
    assert sys.modules.get("pandas") is None              # the server never needs pandas
