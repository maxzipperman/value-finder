"""Prepare the Backtests screen's charts from tables already committed in the repo.

Run by hand from the repo root with a weather project's Python (it needs pandas for the two replay parquet files):

    nfl-weather/.venv/bin/python dashboard/tools/build_charts.py            # write dashboard/content/charts/*.json
    nfl-weather/.venv/bin/python dashboard/tools/build_charts.py --check    # compare; exit 1 on any difference

It reads only committed outputs (each source must be tracked by git and unchanged in the working tree), and it
writes one small JSON file per chart to dashboard/content/charts/ and nowhere else. Each file names its sources,
their git blob hashes and the date each last changed, so a chart can always be traced to the table it was drawn
from. The dashboard's server only reads these files (it cannot read parquet); it adds, as the page loads, whether
each result clears the project's multiple-testing bar, which it reads from STATUS.md.

The words on each chart are written here, next to the numbers they state, and must agree with the write-up the
chart illustrates (named in the file). Nothing here recomputes a result from raw data: every number is copied from
a committed table, or (the cumulative units) added up from the committed per-game replay rows, whose records the
tool checks against the committed season tables before it writes anything.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
import sys
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

sys.dont_write_bytecode = True

FORMAT = 1
OUT = Path("dashboard") / "content" / "charts"
BREAK_EVEN = 52.38                      # the under's break-even at -110: 110 / 210 = 52.38%
MINUS = "−"

# The screen's order: (group heading, [chart ids]). "evidence-vs-bar" is drawn by the server itself from
# dashboard/content/evidence.json and STATUS.md as the page loads (both change when research merges), so it has no
# file here; vfdash/backtests.py holds the same list, and a test checks the two agree.
GROUPS = [
    ("Why wind, and the wind rule replayed on forecasts",
     ["wind-and-scoring", "wind-rule-cfb-seasons", "wind-rule-nfl-seasons", "wind-rule-units",
      "wind-rule-opener-vs-close"]),
    ("How good are the forecasts", ["forecast-error-cfb", "forecast-error-nfl"]),
    ("How hard it is to prove anything", ["evidence-vs-bar", "money-gate", "keep-test"]),
    ("Other ideas tested", ["key-numbers", "line-moves"]),
]
LIVE = {"evidence-vs-bar"}

CFB_README = {"path": "cfb-weather/README.md", "section": "Forecast replay on NWS MOS, the full run: 2006–25",
              "anchor": "forecast-replay-on-nws-mos-the-full-run-200625-issue-40-sep-29"}
NFL_README = {"path": "nfl-weather/README.md", "section": "Forecast replay on NWS MOS, the full run: 2004–25",
              "anchor": "forecast-replay-on-nws-mos-the-full-run-200425-issue-40-sep-29"}
NFL_REPORT = {"path": "nfl-weather/report/nfl_weather_report.html",
              "section": "Figure 6. Wind costs points the closing total doesn't subtract", "anchor": ""}
MONEY_GATE = {"path": "strategy-research/README.md", "section": "The paper-to-money gate",
              "anchor": "the-paper-to-money-gate-added-september-29-2026-51"}
KEEP_TEST = {"path": "strategy-research/README.md",
             "section": "The keep test: plain, grouped by game day, and the wider of the two",
             "anchor": "the-keep-test-plain-grouped-by-game-day-and-the-wider-of-the-two-added-september-29-2026"}
KEY_NUMBERS = {"path": "strategy-research/README.md", "section": "Landing-mass table: key numbers",
               "anchor": "landing-mass-table-key-numbers-added-september-29-2026-52"}
TIMING = {"path": "strategy-research/README.md", "section": "Structure and timing (not bets)",
          "anchor": "structure-and-timing-not-bets"}


class Refused(Exception):
    """A source that can't be used: not tracked by git, changed since its last commit, or not as expected."""


# ---------------------------------------------------------------- git and files (read-only)

def git(*args: str) -> str:
    r = subprocess.run(["git", *args], capture_output=True, text=True)
    if r.returncode != 0:
        raise Refused(f"git {' '.join(args)} failed: {r.stderr.strip()[:200]}")
    return r.stdout.strip()


class Sources:
    """Every source a chart reads, checked once: tracked, committed, unchanged in the working tree."""

    def __init__(self):
        self.seen: dict[str, dict] = {}

    def use(self, path: str) -> Path:
        if path not in self.seen:
            p = Path(path)
            if not p.is_file():
                raise Refused(f"{path} is missing")
            try:
                committed = git("rev-parse", f"HEAD:{path}")
            except Refused:
                raise Refused(f"{path} is not committed, so no chart may be drawn from it") from None
            working = git("hash-object", "--", path)
            if working != committed:
                raise Refused(f"{path} differs from its last commit; commit it (or undo the change) first")
            commit, changed = git("log", "-1", "--format=%H %cs", "HEAD", "--", path).split()
            self.seen[path] = {"path": path, "blob": committed, "commit": commit, "changed": changed}
        return Path(path)

    def listing(self, paths: list[str]) -> list[dict]:
        return [dict(self.seen[p]) for p in paths]


def read_csv(src: Sources, path: str) -> list[dict]:
    with src.use(path).open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def one(rows: list[dict], **match) -> dict:
    hits = [r for r in rows if all(r.get(k) == v for k, v in match.items())]
    if len(hits) != 1:
        raise Refused(f"expected one row with {match}, found {len(hits)}")
    return hits[0]


# ---------------------------------------------------------------- words and numbers

def f(x) -> float:
    return float(x)


def fixed(x: float, digits: int = 1) -> str:
    """x to `digits` decimals, half away from zero on its decimal value as written (2.05 is 2.1; Python's format
    gives 2.0, from 2.05's binary value). The page rounds the number a chart file holds the same way (app.js, fixed),
    so a table and the hover read-out of the same number always agree: format the number as the file holds it."""
    return str(Decimal(repr(float(x))).quantize(Decimal(1).scaleb(-digits), rounding=ROUND_HALF_UP))


def pct(x) -> float:
    """A share (0.5035) as the percentage a chart file holds (50.35), to 4 decimals."""
    return round(f(x) * 100, 4)


def signed(x: float, digits: int = 2) -> str:
    s = fixed(abs(x), digits)
    return ("+" if x > 0 else MINUS if x < 0 else "") + s if float(s) != 0 else s


def record(s: str) -> str:
    """715-555-14 as the write-ups print it, 715–555–14 (a trailing -0 push count is dropped)."""
    parts = s.split("-")
    if len(parts) == 3 and parts[2] == "0":
        parts = parts[:2]
    return "–".join(parts)


def interval(s: str) -> tuple[float, float]:
    """'53.6-59.0' -> (53.6, 59.0)."""
    m = re.fullmatch(r"\s*(-?[\d.]+)\s*-\s*(-?[\d.]+)\s*", s)
    if not m:
        raise Refused(f"not an interval: {s!r}")
    return float(m.group(1)), float(m.group(2))


def p_text(p: float) -> str:
    """As the dashboard writes a p-value: 3 significant figures below 0.1, else 2 decimals."""
    if p < 1e-6:
        return "below 0.000001"
    return f"{p:.3g}" if p < 0.1 else f"{p:.2f}"


def roi(x: float) -> str:
    return signed(x, 1) + "%"


def count(n: int) -> str:
    return f"{n:,}"


def table(columns, rows, num=None, note="") -> dict:
    return {"columns": columns, "num": num or [False] * len(columns), "rows": [[str(c) for c in r] for r in rows],
            "note": note}


def chart(cid: str, *, title, name, shows, not_shows, sample, n, bar, writeups, sources, src: Sources, plot, tab):
    listing = src.listing(sources)
    return {"format": FORMAT, "id": cid, "title": title, "name": name, "shows": shows, "not_shows": not_shows,
            "sample": sample, "n": n, "bar": bar, "writeups": writeups, "sources": listing,
            "date": max(s["changed"] for s in listing), "built_by": "dashboard/tools/build_charts.py",
            "plot": plot, "table": tab}


def win_axis(label="Win rate for the under, %") -> dict:
    """A win-rate axis: starts at 40% or lower, and break-even is drawn (the dashboard's honesty rule)."""
    return {"kind": "win_rate", "label": label, "unit": "%", "digits": 1, "floor_at_most": 40}


BREAK_EVEN_REF = {"value": BREAK_EVEN, "label": "Break-even at −110, 52.4%", "role": "breakeven"}


# ---------------------------------------------------------------- the charts

def wind_and_scoring(src: Sources) -> dict:
    mvr = "nfl-weather/output/tables/bet_market_vs_reality.csv"
    tbb = "nfl-weather/output/tables/bet_totals_by_bucket.csv"
    strat = "nfl-weather/output/tables/strategies.csv"
    m, t, s = read_csv(src, mvr), read_csv(src, tbb), read_csv(src, strat)
    era = "All 1999–2025"
    bands = [("wind_10_14", "10–14 mph", "Wind 10–14"), ("wind_15_19", "15–19 mph", "Wind 15–19"),
             ("wind_20p", "20+ mph", "Wind 20+")]
    pts, line, games, rows = [], [], {}, []
    for term, label, bucket in bands:
        a = one(m, outcome="total", term=term, era=era)
        c = one(m, outcome="total_line", term=term, era=era)
        games[label] = int(one(t, era="All", bucket=bucket)["games"])
        pts.append([label, f(a["coef"]), f(a["lo"]), f(a["hi"])])
        line.append([label, f(c["coef"]), f(c["lo"]), f(c["hi"])])
        rows.append([label, count(games[label]), f"{signed(f(a['coef']))} ({signed(f(a['lo']))} to {signed(f(a['hi']))})",
                     f"{signed(f(c['coef']))} ({signed(f(c['lo']))} to {signed(f(c['hi']))})"])
    n = int(one(m, outcome="total", term="wind_15_19", era=era)["n"])
    if n != int(one(m, outcome="total_line", term="wind_15_19", era=era)["n"]):
        raise Refused("the two regressions don't cover the same games")
    bet = one(s, rule="Wind 15+ mph → under", test="vs close 1999–2025")
    a15, l15 = pts[1][1], line[1][1]
    title = (f"Wind lowers NFL scoring more than the closing total allows for: at 15–19 mph, {fixed(abs(a15))} fewer "
             f"points against {fixed(abs(l15))} off the closing total")
    return chart(
        "wind-and-scoring", src=src, title=title,
        name=("Scoring against wind, NFL, 1999–2025: how much each wind band changed the points scored and the "
              "closing total"),
        shows=("Each dot is how much a wind band changed the points both teams scored, or the closing total, against "
               "a calm, mild, dry outdoor game, with its 95% interval, allowing for each team's season and the week."),
        not_shows=("It uses the wind recorded at kickoff, not the forecast a bet is placed on 1 to 3 days before, so "
                   "it shows why the wind rule exists, not a price a forecast can beat."),
        sample=(f"{count(n)} games, 1999–2025; outdoor games with 10–14 mph wind: {count(games['10–14 mph'])}, "
                f"15–19 mph: {count(games['15–19 mph'])}, 20+ mph: {count(games['20+ mph'])}"),
        n=n,
        bar={"tests": [{"label": (f"The bet built on it, the under in 15+ mph wind against the close "
                                  f"({fixed(pct(bet['win_pct']))}% of {count(int(bet['bets']))} bets, 1999–2025)"),
                        "p": f(bet["p"]), "p_words": f"one-sided p = {p_text(f(bet['p']))}"}],
             "note": "The chart itself measures scoring, not a bet."},
        writeups=[NFL_REPORT], sources=[mvr, tbb, strat],
        plot={"layout": "columns", "panels": [{
            "name": "", "x": {"kind": "category", "labels": [b[1] for b in bands], "label": "Wind at kickoff"},
            "y": {"kind": "points", "label": "Change against a calm game, points", "unit": " points", "digits": 2,
                  "zero": True},
            "series": [{"id": "scored", "name": "Points scored (both teams)", "mark": "dot", "color": "c1",
                        "points": pts},
                       {"id": "close", "name": "Closing total", "mark": "dot", "color": "c2", "points": line}],
            "refs": [{"value": 0, "label": "A calm game", "role": "zero"}],
            "tips": {b[1]: [f"{count(games[b[1]])} outdoor games"] for b in bands}}]},
        tab=table(["Wind at kickoff", "Outdoor games", "Points scored: change (95% interval)",
                   "Closing total: change (95% interval)"], rows, [False, True, False, False],
                  note="Changes are in points, against a calm, mild, dry outdoor game."))


def replay_seasons(src: Sources, sport: str) -> dict:
    proj = "cfb-weather" if sport == "cfb" else "nfl-weather"
    seasons_path = f"{proj}/output/tables/mos_replay_seasons.csv"
    eras_path = f"{proj}/output/tables/mos_replay_eras.csv"
    rows, eras = read_csv(src, seasons_path), read_csv(src, eras_path)
    pooled = one(rows, sample="pooled")
    pooled_era = one(eras, sample="pooled")
    seasons = [r for r in rows if r["sample"] != "pooled"]
    pts, counts, tab_rows, tips = [], [], [], {}
    for r in seasons:
        lo, hi = interval(r["close_win_ci"])
        pts.append([r["sample"], f(r["close_win_pct"]), lo, hi])
        counts.append([r["sample"], int(r["close_n"])])
        tips[r["sample"]] = [f"{record(r['close_record'])}, {int(r['close_n'])} signals",
                             f"Return at −110 {roi(f(r['close_roi_pct']))}"]
        tab_rows.append([r["sample"], count(int(r["close_n"])), record(r["close_record"]),
                         f"{fixed(r['close_win_pct'])}%", f"{fixed(lo)}–{fixed(hi)}%", roi(f(r["close_roi_pct"])),
                         p_text(f(r["close_p_one_sided"]))])
    plo, phi = interval(pooled["close_win_ci"])
    tab_rows.append(["All", count(int(pooled["close_n"])), record(pooled["close_record"]),
                     f"{fixed(pooled['close_win_pct'])}%", f"{fixed(plo)}–{fixed(phi)}%",
                     roi(f(pooled["close_roi_pct"])),
                     p_text(f(pooled["close_p_one_sided"]))])
    first, last = seasons[0]["sample"], seasons[-1]["sample"]
    span = f"{first}–{last[2:]}"
    below = sum(f(r["close_win_pct"]) < BREAK_EVEN for r in seasons)
    rate = f(pooled["close_win_pct"])
    p, pg = f(pooled["close_p_one_sided"]), f(pooled_era["grouped_p"])
    n = int(pooled["close_n"])
    also = int(pooled["obs_also_signal"])
    who = "College football's wind rule" if sport == "cfb" else "The NFL wind rule"
    how = ("above break-even by ordinary standards" if max(p, pg) < 0.01 else
           "only weakly distinguishable from break-even" if max(p, pg) < 0.05 else
           "not distinguishable from break-even")
    title = (f"{who} won {fixed(rate)}% on forecasts as issued, {span}: {how}, and below it in {below} of "
             f"{len(seasons)} seasons")
    sport_words = "college football" if sport == "cfb" else "NFL"
    return chart(
        f"wind-rule-{sport}-seasons", src=src, title=title,
        name=f"The wind rule on NWS MOS forecasts as issued, {sport_words}, season by season",
        shows=("Each dot is one season's win rate for the under at the consensus closing total, at an assumed −110, "
               "with its 95% interval; the bars below count that season's signals."),
        not_shows=(f"It is not the forecast or the price the live board uses, and not an independent test: {also:,} of "
                   f"the {n:,} signals are games the observed-wind evidence already counts."),
        sample=(f"{count(n)} signals from {count(int(pooled['with_mos']))} games with a forecast "
                f"({record(pooled['close_record'])}; pushes are left out of the win rate)"),
        n=n,
        bar={"tests": [{"label": f"All {len(seasons)} seasons against break-even", "p": max(p, pg),
                        "p_words": f"one-sided p = {p_text(p)} ({p_text(pg)} grouped by game day)"}], "note": ""},
        writeups=[CFB_README if sport == "cfb" else NFL_README], sources=[seasons_path, eras_path],
        plot={"layout": "columns", "panels": [{
            "name": "", "x": {"kind": "category", "labels": [r["sample"] for r in seasons], "label": "Season"},
            "y": win_axis(),
            "series": [{"id": "close", "name": "Win rate at the close, with its 95% interval", "mark": "dot",
                        "color": "c1", "points": pts}],
            "counts": {"name": "Signals", "points": counts},
            "refs": [BREAK_EVEN_REF, {"value": rate, "label": f"All seasons, {fixed(rate)}%", "role": "pooled"}],
            "tips": tips}]},
        tab=table(["Season", "Signals", "Record", "Win rate", "95% interval", "Return at −110", "One-sided p"],
                  tab_rows, [False, True, False, True, False, True, True],
                  note=f"Grouped by game day, the pooled one-sided p is {p_text(pg)}."))


def replay_units(src: Sources) -> dict:
    import pandas as pd

    out, tests, lines, per_season = {}, [], [], {}
    for sport, proj in (("cfb", "cfb-weather"), ("nfl", "nfl-weather")):
        path = f"{proj}/data/processed/mos_replay.parquet"
        d = pd.read_parquet(src.use(path))
        s = d[d["mos_signal"] == True].sort_values(["start_utc", "game_id"], kind="mergesort")  # noqa: E712
        won = s["under_win"].astype(bool) & ~s["push"].astype(bool)
        pushed = s["push"].astype(bool)
        units = [0.0 if p else (100 / 110 if w else -1.0) for w, p in zip(won, pushed)]
        seasons = read_csv(src, f"{proj}/output/tables/mos_replay_seasons.csv")
        eras = read_csv(src, f"{proj}/output/tables/mos_replay_eras.csv")
        pooled = one(seasons, sample="pooled")
        rec = f"{int(won.sum())}-{int((~won & ~pushed).sum())}-{int(pushed.sum())}"
        if rec != pooled["close_record"]:
            raise Refused(f"{path}: the signals' record {rec} is not the season table's {pooled['close_record']}")
        cum, pts, peak, worst = 0.0, [], 0.0, 0.0
        et = s["start_utc"].dt.tz_convert("America/New_York").dt.strftime("%Y-%m-%d")
        for u, day, away, home, w, p in zip(units, et, s["away_team"], s["home_team"], won, pushed):
            cum += u
            peak = max(peak, cum)
            worst = min(worst, cum - peak)
            pts.append([day, round(cum, 4), f"{away} at {home}, {'push' if p else 'won' if w else 'lost'}"])
        for season, g in s.assign(u=units).groupby("season"):
            r = one(seasons, sample=str(season))
            gw = g["under_win"].astype(bool) & ~g["push"].astype(bool)
            grec = f"{int(gw.sum())}-{int((~gw & ~g['push'].astype(bool)).sum())}-{int(g['push'].astype(bool).sum())}"
            if grec != r["close_record"]:
                raise Refused(f"{path}: season {season} is {grec} in the rows, {r['close_record']} in the table")
            per_season.setdefault(int(season), {})[sport] = (len(g), record(grec), float(g["u"].sum()))
        out[sport] = {"n": len(s), "total": cum, "worst": worst, "path": path}
        p, pg = f(pooled["close_p_one_sided"]), f(one(eras, sample="pooled")["grouped_p"])
        tests.append({"label": "College football, all signals" if sport == "cfb" else "NFL, all signals",
                      "p": max(p, pg), "p_words": f"one-sided p = {p_text(p)} ({p_text(pg)} grouped by game day)"})
        lines.append({"id": sport, "name": f"{'College football' if sport == 'cfb' else 'NFL'} ({len(s):,} signals)",
                      "mark": "line", "color": "c1" if sport == "cfb" else "c2", "points": pts})
    c, nf = out["cfb"], out["nfl"]
    title = (f"At an assumed −110 both replays end ahead: {signed(c['total'], 1)} units after {c['n']:,} college "
             f"football signals and {signed(nf['total'], 1)} after {nf['n']:,} NFL signals, with losing stretches of "
             f"up to {fixed(abs(c['worst']))} and {fixed(abs(nf['worst']))} units")
    rows, run = [], {"cfb": 0.0, "nfl": 0.0}
    for season in sorted(per_season):
        row = [str(season)]
        for sport in ("cfb", "nfl"):
            v = per_season[season].get(sport)
            if v is None:
                row += ["", "", "", ""]
                continue
            run[sport] += v[2]
            row += [str(v[0]), v[1], signed(v[2], 1), signed(run[sport], 1)]
        rows.append(row)
    sources = [c["path"], "cfb-weather/output/tables/mos_replay_seasons.csv", "cfb-weather/output/tables/mos_replay_eras.csv",
               nf["path"], "nfl-weather/output/tables/mos_replay_seasons.csv", "nfl-weather/output/tables/mos_replay_eras.csv"]
    return chart(
        "wind-rule-units", src=src, title=title,
        name="Units won at an assumed −110, signal by signal, in each sport's forecast replay",
        shows=("Each line adds the units won or lost, one unit a bet, as each signal's game is played, in kickoff order; "
               "a push adds nothing."),
        not_shows=("These are not units anyone could have won: every bet is at the consensus close at an assumed −110, "
                   "while the live rule bets 1 to 3 days early at one book's price, under a −115 cap."),
        sample=f"{c['n']:,} college football signals (2006–25) and {nf['n']:,} NFL signals (2004–25)",
        n=c["n"] + nf["n"], bar={"tests": tests, "note": ""}, writeups=[CFB_README, NFL_README], sources=sources,
        plot={"layout": "columns", "panels": [{
            "name": "", "x": {"kind": "time", "label": "Kickoff date"},
            "y": {"kind": "units", "label": "Units won, cumulative", "unit": " units", "digits": 1, "zero": True},
            "series": lines, "refs": [{"value": 0, "label": "Even", "role": "zero"}]}]},
        tab=table(["Season", "College football signals", "Record", "Units", "Running total", "NFL signals", "Record",
                   "Units", "Running total"], rows, [False, True, False, True, True, True, False, True, True],
                  note="By season; the chart plots every signal. One unit a bet at −110: a win pays 0.909 units."))


def opener_vs_close(src: Sources) -> dict:
    rows_out, opener, close, tab_rows, notes = [], [], [], [], {}
    diffs = {}
    for sport, proj, label in (("cfb", "cfb-weather", "College football"), ("nfl", "nfl-weather", "NFL")):
        eras = read_csv(src, f"{proj}/output/tables/mos_replay_eras.csv")
        by_season = read_csv(src, f"{proj}/output/tables/mos_replay_seasons.csv")
        for r in eras:
            first, last = (int(x) for x in r["seasons"].split("-"))
            with_opener = [int(x["sample"]) for x in by_season if x["sample"] != "pooled"
                           and first <= int(x["sample"]) <= last and int(x["open_n"]) > 0]
            n = int(r["open_n"])
            if sum(int(x["open_n"]) for x in by_season if x["sample"] != "pooled"
                   and first <= int(x["sample"]) <= last) != n:
                raise Refused(f"{proj}: the seasons' openers don't add up to the {r['sample']} era's")
            what = "all seasons" if r["sample"] == "pooled" else f"{first}–{str(last)[2:]}"
            span = (f"{min(with_opener)}–{str(max(with_opener))[2:]}" if min(with_opener) != max(with_opener)
                    else str(min(with_opener)))
            row = f"{label}, {what} ({n:,} games with an opener, {span})"
            if n != int(r["closeop_n"]):
                raise Refused(f"{proj}: the opener and the close cover different games in {r['sample']}")
            olo, ohi = interval(r["open_win_ci"])
            clo, chi = interval(r["closeop_win_ci"])
            rows_out.append(row)
            opener.append([row, f(r["open_win_pct"]), olo, ohi])
            close.append([row, f(r["closeop_win_pct"]), clo, chi])
            notes[row] = f"{record(r['open_record'])} at the opener, {record(r['closeop_record'])} at the close"
            tab_rows.append([row, record(r["open_record"]),
                             f"{fixed(r['open_win_pct'])}% ({fixed(olo)}–{fixed(ohi)}%)",
                             record(r["closeop_record"]),
                             f"{fixed(r['closeop_win_pct'])}% ({fixed(clo)}–{fixed(chi)}%)"])
            if r["sample"] == "pooled":
                diffs[sport] = (f(r["open_win_pct"]), f(r["closeop_win_pct"]), n, span)
    c, nf = diffs["cfb"], diffs["nfl"]
    title = (f"On the same games the wind rule won {fixed(c[0] - c[1])} percentage points more often at the opener "
             f"than at the close in college football and {fixed(nf[0] - nf[1])} in the NFL, but the opener is posted "
             "before the forecast that fires")
    return chart(
        "wind-rule-opener-vs-close", src=src, title=title,
        name="The forecast replays graded at the opener and at the close, on the same games",
        shows=("Each row pairs the under's win rate at the opening total and at the closing total on the same games, "
               "with 95% intervals, for all seasons and for the eras declared before the replays ran."),
        not_shows=("It does not show a price the rule could get: the opener is usually posted before the forecast "
                   "that fires, so it flatters the rule, and the live entry, 1 to 3 days early, sits between the two."),
        sample=(f"{c[2]:,} college football signals with an opener ({c[3]}) and {nf[2]:,} NFL signals with an SBR "
                f"opener ({nf[3]})"),
        n=c[2] + nf[2],
        bar={"tests": [], "none": ("A comparison of two prices for the same bets, not a separate test: it adds no "
                                   "variant, and the opener's record is not held against the bar because the opener "
                                   "is posted before the forecast that fires.")},
        writeups=[CFB_README, NFL_README],
        sources=["cfb-weather/output/tables/mos_replay_eras.csv", "nfl-weather/output/tables/mos_replay_eras.csv"],
        plot={"layout": "rows", "panels": [{
            "name": "", "rows": rows_out, "x": win_axis(),
            "series": [{"id": "open", "name": "At the opener", "mark": "dot", "color": "c2", "points": opener},
                       {"id": "close", "name": "At the close, same games", "mark": "dot", "color": "c1",
                        "points": close}],
            "refs": [BREAK_EVEN_REF], "tips": {k: [v] for k, v in notes.items()}}]},
        tab=table(["Games", "At the opener", "Win rate (95% interval)", "At the close", "Win rate (95% interval)"],
                  tab_rows, note=("Pushes are left out of the win rates. The NFL's openers are SBR's, 2007–21; college "
                                  "football's are cfbfastR's consensus opener, else the median CFBD opener.")))


def forecast_error(src: Sources, sport: str) -> dict:
    proj = "cfb-weather" if sport == "cfb" else "nfl-weather"
    path = f"{proj}/output/tables/mos_bias_by_season.csv"
    rows = read_csv(src, path)
    seasons = sorted({r["season"] for r in rows if r["season"] != "all"})
    leads = sorted({r["lead"] for r in rows})
    colors = {"1": "o3", "2": "o2", "3": "o1"}
    bias, mae, tab_rows, tips = [], [], [], {}
    for lead in leads:
        pts_b = [[r["season"], f(r["mean_error"])] for r in rows if r["lead"] == lead and r["season"] != "all"]
        pts_m = [[r["season"], f(r["mae"])] for r in rows if r["lead"] == lead and r["season"] != "all"]
        name = f"{lead} day{'s' if lead != '1' else ''} before"
        bias.append({"id": f"lead{lead}", "name": name, "mark": "line", "color": colors[lead], "points": pts_b})
        mae.append({"id": f"lead{lead}", "name": name, "mark": "line", "color": colors[lead], "points": pts_m})
    for r in rows:
        tab_rows.append([r["season"] if r["season"] != "all" else "All", r["lead"], count(int(r["n"])),
                         signed(f(r["mean_error"])), fixed(r["mae"], 2), fixed(r["corr"], 2),
                         f"{fixed(r['mos_ge15_pct'])}%", f"{fixed(r['obs_ge15_pct'])}%"])
    for s in seasons:
        tips[s] = [f"{count(int(r['n']))} games at lead {r['lead']}" for r in rows if r["season"] == s]
    a1 = one(rows, season="all", lead="1")
    l1 = [r for r in rows if r["lead"] == "1" and r["season"] != "all"]
    obs = "the airport later recorded" if sport == "cfb" else "the game book's wind"
    if all(f(r["mean_error"]) > 0 for r in rows if r["season"] != "all"):
        head = (f"NWS MOS forecasts ran windier than {obs} in every season, by {fixed(a1['mean_error'], 2)} mph on "
                f"average a day out")
    else:
        head = f"NWS MOS forecasts ran {fixed(a1['mean_error'], 2)} mph above {obs} on average a day out"
    last2 = l1[-2:]
    grown = all(f(r["mean_error"]) >= max(f(x["mean_error"]) for x in l1[:-2]) for r in last2)
    if grown:
        head += (f", and the gap has grown lately ({signed(f(last2[0]['mean_error']))} and "
                 f"{signed(f(last2[1]['mean_error']))} mph in {last2[0]['season']} and {last2[1]['season']})")
    title = head + f"; the typical miss was {fixed(a1['mae'], 2)} mph"
    n = int(a1["n"])
    by_lead = {r["lead"]: int(r["n"]) for r in rows if r["season"] == "all"}
    same = [k for k, v in by_lead.items() if v == by_lead["1"]]
    sample = f"{count(by_lead['1'])} games with a forecast and an observed wind at " + (
        f"leads {' and '.join(same)}" if len(same) > 1 else "lead 1") + "".join(
        f", {count(v)} at lead {k}" for k, v in by_lead.items() if k not in same)
    sport_words = "College football" if sport == "cfb" else "NFL"
    return chart(
        f"forecast-error-{sport}", src=src, title=title,
        name=f"{sport_words}: NWS MOS forecast wind against the observed wind, by season and by days before kickoff",
        shows=("Each line is one lead, in days before kickoff: the top panel is the average of the forecast minus the "
               "wind observed at kickoff, the lower one the typical size of the miss (mean absolute error)."),
        not_shows=(("It measures the airport's wind, not the stadium's, and MOS is not the forecast the live board "
                    "reads (Open-Meteo).") if sport == "cfb" else
                   ("MOS forecasts the airport while the game book records the stadium, so part of the gap is where the "
                    "wind is measured, and MOS is not the forecast the live board reads (Open-Meteo).")),
        sample=f"{sample}, {seasons[0]}–{seasons[-1][2:]}", n=n,
        bar={"tests": [], "none": ("A measure of forecast accuracy, not a betting test: it adds no variant and has no "
                                   "p-value to hold against the bar.")},
        writeups=[CFB_README if sport == "cfb" else NFL_README], sources=[path],
        plot={"layout": "columns", "panels": [
            {"name": "Forecast minus observed wind, average (mph)",
             "x": {"kind": "category", "labels": seasons, "label": "Season"},
             "y": {"kind": "mph", "label": "mph", "unit": " mph", "digits": 2, "zero": True},
             "series": bias, "refs": [{"value": 0, "label": "No bias", "role": "zero"}], "tips": tips},
            {"name": "Typical miss, mean absolute error (mph)",
             "x": {"kind": "category", "labels": seasons, "label": "Season"},
             "y": {"kind": "mph", "label": "mph", "unit": " mph", "digits": 2, "zero": True},
             "series": mae, "refs": [], "tips": tips}]},
        tab=table(["Season", "Days before", "Games", "Forecast minus observed (mph)", "Typical miss (mph)",
                   "Correlation", "Forecast reaches 15 mph", "Observed reaches 15 mph"], tab_rows,
                  [False, True, True, True, True, True, True, True]))


GATE_WORDS = {
    ("mean CLV > 0 (today's gate)", "20"): "Today's gate: average closing-line value above 0 at signal 20",
    ("t > 1.65", "20"): "t above 1.65 at signal 20",
    ("t > 1.65", "40"): "t above 1.65 at signal 40",
    ("bootstrap 90% lower bound > 0", "20"): "Bootstrap 90% lower bound above 0 at signal 20",
    ("bootstrap 95% lower bound > 0", "20"): "Bootstrap 95% lower bound above 0 at signal 20",
    ("bootstrap 95% lower bound > 0", "40"): "Bootstrap 95% lower bound above 0 at signal 40",
    ("t > calibrated 5%", "20"): "t above a calibrated {t} at signal 20",
    ("t > calibrated 5%", "40"): "t above a calibrated {t} at signal 40",
    ("sequential constant 5%", "10-40"): "Sequential, constant bar {t} (5%), signals 10 to 40",
    ("sequential OBF, fixed bar 2.75 CFB / 2.14 NFL", "10-40"):
        "Sequential, O'Brien–Fleming bar {t} (5%), signals 10 to 40: the recommended gate",
    ("sequential OBF 5%, realistic bar", "10-40"): "Sequential, O'Brien–Fleming bar {t} (5%, realistic case), signals "
                                                   "10 to 40",
    ("sequential constant 10%", "10-40"): "Sequential, constant bar {t} (10%), signals 10 to 40",
    ("sequential OBF 10%", "10-40"): "Sequential, O'Brien–Fleming bar {t} (10%), signals 10 to 40",
    # the CSV's reference row is the keep test as scored before the Sep 29 amendments (nfl-weather 7, cfb-weather 5):
    # the plain interval, not the wider of two that both sports register now (the keep-test chart)
    ("registered keep test (reference)", "40"): ("For reference: the keep test as scored before the Sep 29 "
                                                 "amendments (plain interval), at signal 40"),
}


def money_gate(src: Sources) -> dict:
    path = "strategy-research/output/money_gate.csv"
    rows = read_csv(src, path)
    case = [r for r in rows if r["section"] == "gates" and r["sport"] == "CFB Rule B"
            and r["dependence"] == "realistic dependence" and r["volume"] == "40" and r["zero_share"] == "0"
            and r["floor"] == "0"]
    scen = [("no edge", "none", "o1", "No edge"), ("half the move", "half", "o2", "Half the historical line move"),
            ("full move", "full", "o3", "The full historical line move")]
    labels, series, tab_rows, got = [], {k: [] for _, k, _, _ in scen}, [], {}
    for (gate, signals), words in GATE_WORDS.items():
        vals = {}
        for sc, key, _, _ in scen:
            r = one(case, gate=gate, signals=signals, scenario=sc)
            vals[key] = pct(r["p_pass"])
            thr = r["threshold"]
        label = words.format(t=thr)
        labels.append(label)
        for key in vals:
            series[key].append([label, round(vals[key], 4)])
        got[(gate, signals)] = vals
        tab_rows.append([label, f"{fixed(vals['none'])}%", f"{fixed(vals['half'])}%", f"{fixed(vals['full'])}%"])
    today = got[("mean CLV > 0 (today's gate)", "20")]
    rec = got[("sequential OBF, fixed bar 2.75 CFB / 2.14 NFL", "10-40")]
    dates = [r for r in rows if r["section"] == "dates" and r["sport"] == "CFB Rule B"
             and r["dependence"] == "realistic dependence" and r["volume"] == "40" and r["floor"] == "0"
             and r["zero_share"] == "0" and r["gate"] == "sequential OBF, fixed bar 2.75 CFB / 2.14 NFL"]
    money = {sc: pct(one(dates, scenario=sc)["p_money_this_season"]) for sc in ("half the move", "full move")}
    title = (f"Today's gate passes a rule with no edge {fixed(today['none'], 0)}% of the time; the recommended "
             f"sequential gate passes one {fixed(rec['none'])}% of the time, and a real edge {fixed(rec['half'], 0)}% "
             f"(half the historical move) to {fixed(rec['full'], 0)}% (all of it)")
    return chart(
        "money-gate", src=src, title=title,
        name="The paper-to-money gate: how often each candidate gate passes, college football's wind rule",
        shows=("For each candidate gate, the chance it passes by the 40th signal: with no edge (a false pass), with "
               "half the historical line move and with all of it (college football, 40 signals a season, same-day "
               "correlation 0.11, the write-up's realistic case)."),
        not_shows=("It is no evidence that the wind rule has an edge, and it is not the chance of real money this "
                   f"season, which is lower: {fixed(money['half the move'], 0)}% and {fixed(money['full move'], 0)}% "
                   "for the "
                   "recommended gate, since a signal already logged when a gate passes stays on paper."),
        sample="40,000 simulated runs of 40 signals for each gate and each case", n=40000,
        bar={"tests": [], "none": "A simulation of a staking rule, not a betting test: it adds no variants."},
        writeups=[MONEY_GATE], sources=[path],
        plot={"layout": "rows", "panels": [{
            "name": "", "rows": labels,
            "x": {"kind": "chance", "label": "Chance the gate passes, %", "unit": "%", "digits": 1, "min": 0,
                  "max": 100},
            "series": [{"id": key, "name": name, "mark": "bar", "color": color, "points": series[key]}
                       for _, key, color, name in scen],
            "refs": [{"value": 5, "label": "5%", "role": "line"}]}]},
        tab=table(["Gate", "No edge", "Half the move", "The full move"], tab_rows, [False, True, True, True],
                  note=("The t in a gate's name is the average closing-line value divided by its standard error. "
                        "The CSV's calibrated 2.72 row is left out, as in the write-up's table; it is within a point "
                        "of the 2.75 row everywhere. The last row is the keep test as it was scored before the Sep 29 "
                        "amendments, on the plain interval; both sports now register the wider of two intervals, "
                        "which keeps a rule with no edge less often (the keep-test chart).")))


def keep_test(src: Sources) -> dict:
    path = "strategy-research/output/keep_test_check.csv"
    rows = read_csv(src, path)
    base = [r for r in rows if r["section"] == "keep test at 40 bets" and r["scenario"] == "no edge"]
    cases = [("independent", "bets independent"), ("realistic dependence", "realistic correlation"),
             ("stress dependence", "stress correlation")]
    order = [("CFB Rule B", "College football", ["25", "40", "55"]), ("NFL Rule B", "NFL", ["17", "25"])]
    labels, plain, grouped, wider, tab_rows = [], [], [], [], []
    realistic = {"CFB Rule B": [], "NFL Rule B": []}
    for sport, words, vols in order:
        for case, cwords in cases:
            for v in vols:
                r = one(base, sport=sport, case=case, volume=v)
                label = f"{words}, {v} signals a season, {cwords}"
                labels.append(label)
                vals = [pct(r["plain"]), pct(r["grouped"]), pct(r["wider"])]
                plain.append([label, vals[0]])
                grouped.append([label, vals[1]])
                wider.append([label, vals[2]])
                tab_rows.append([label] + [f"{fixed(x)}%" for x in vals])
                if case == "realistic dependence":
                    realistic[sport].append(vals[2])
    c, nf = realistic["CFB Rule B"], realistic["NFL Rule B"]
    title = (f"With no edge, the registered interval keeps a rule {fixed(min(c))} to {fixed(max(c))}% of the time in "
             f"college football and {fixed(min(nf))} to {fixed(max(nf))}% in the NFL in the realistic case, against an "
             "intended 2.5%")
    return chart(
        "keep-test", src=src, title=title,
        name="The keep test: how often a wind rule with no edge would be kept",
        shows=("For each sport, season volume and assumed correlation between bets, the chance the keep test keeps a "
               "wind rule that has no edge, under the plain interval, the one grouped by game day, and the wider of the "
               "two, which both sports registered on Sep 29."),
        not_shows=("It does not measure any real bet: the closing-line values are simulated from past line moves, and "
                   "the win rate against the close is not simulated."),
        sample="40,000 simulated runs of 40 bets for each case", n=40000,
        bar={"tests": [], "none": "A check of how a test is graded, not a betting test: it adds no variants."},
        writeups=[KEEP_TEST], sources=[path],
        plot={"layout": "rows", "panels": [{
            "name": "", "rows": labels,
            "x": {"kind": "chance", "label": "Chance a no-edge rule is kept, %", "unit": "%", "digits": 1, "min": 0},
            "series": [{"id": "plain", "name": "Plain interval", "mark": "bar", "color": "c2", "points": plain},
                       {"id": "grouped", "name": "Grouped by game day", "mark": "bar", "color": "ink",
                        "points": grouped},
                       {"id": "wider", "name": "The wider of the two (registered)", "mark": "bar", "color": "c1",
                        "points": wider}],
            "refs": [{"value": 2.5, "label": "Intended, 2.5%", "role": "line"}]}]},
        tab=table(["Case", "Plain", "Grouped by game day", "Wider of the two (registered)"], tab_rows,
                  [False, True, True, True]))


def key_numbers(src: Sources) -> dict:
    prices = "strategy-research/output/landing_mass_prices.csv"
    loso = "strategy-research/output/landing_mass_loso.csv"
    rows, tests = read_csv(src, prices), read_csv(src, loso)
    declared = [r for r in tests if r["variant"] == "primary" and r["market"] == "total" and r["metric"] in ("under", "push")]
    if len(declared) != 8:
        raise Refused(f"expected the 8 declared comparisons in {loso}, found {len(declared)}")
    same = sum(r["verdict"] == "no difference shown" for r in declared)
    # the lead the write-up and STATUS.md quote, p = 0.0006: where college football games land next to a half-point
    # line, by a t-test on the seasons. The smallest p-value in the study is a variant of the same comparison.
    lead = one(tests, sport="CFB", market="total", cohort="all", variant="primary", metric="neighbour")
    lead_p = f(lead["p_t"])
    smallest, low = min(((f(r[k]), r) for r in tests for k in ("p_t", "p_signflip") if r[k] != ""),
                        key=lambda x: x[0])
    h = re.fullmatch(r"h = (\d+)", low["variant"])
    if low is lead:
        variant = ""
    elif h and all(low[k] == lead[k] for k in ("sport", "market", "cohort", "metric")):
        variant = (f" (the smallest p-value in the study, {p_text(smallest)}, is the same comparison with the curve "
                   f"smoothed by {h.group(1)} point{'s' if h.group(1) != '1' else ''})")
    else:
        raise Refused(f"the smallest p-value in {loso} is not a smoothing variant of the lead: say which it is")
    panels, tab_rows, sums = [], [], {}
    for sport, words, span in (("NFL", "NFL: how often a game finished exactly on each total, closes 2015–25",
                                "2015–25"),
                               ("CFB", "College football: the same, closes 2006–25", "2006–25")):
        mine = [r for r in rows if r["sport"] == sport and r["market"] == "total" and r["cohort"] == "all"]
        keys = sorted({int(f(r["key"])) for r in mine})
        on, half, tab_, reg = [], [], [], []
        total_on = 0
        for k in keys:
            ks = str(k)
            o = one(mine, key=ks, model="raw, market on K")
            hf = one(mine, key=ks, model="raw, market a half-point from K")
            t = one(mine, key=ks, model="table", line=f"{k}.0")
            g = one(mine, key=ks, model="residual", line=f"{k}.0")
            on_n, on_l = int(f(o["raw_games"])), int(f(o["raw_landed"]))
            hf_n, hf_l = int(f(hf["raw_games"])), int(f(hf["raw_landed"]))
            total_on += on_n
            lo_k, hi_k = keys[0], keys[-1]
            # how often a game landed on K, from the row's own counts (its p_push is the same share, rounded to 4
            # decimals, and rounding that again would misstate it: 13 of 788 is 1.6497%, not 1.65%)
            on_s = round(on_l / on_n * 100, 4) if on_n else None
            hf_s = round(hf_l / hf_n * 100, 4) if hf_n else None
            for share, row_ in ((on_s, o), (hf_s, hf)):
                if share is not None and abs(share - f(row_["p_push"]) * 100) > 0.00501:
                    raise Refused(f"{prices}: K = {ks}, {row_['model']}: p_push is not landed / games")
            if on_n:
                on.append([k, on_s, on_n, on_l])
            if hf_n:
                half.append([k, hf_s, hf_n, hf_l])
            tab_.append([k, pct(t["p_push"])])
            reg.append([k, pct(g["p_push"])])
            tab_rows.append(["NFL" if sport == "NFL" else "College football", ks,
                             f"{on_l} of {on_n}" + (f" ({fixed(on_s)}%)" if on_n else ""),
                             f"{hf_l} of {hf_n}" + (f" ({fixed(hf_s)}%)" if hf_n else ""),
                             f"{fixed(pct(t['p_push']))}%", f"{fixed(pct(g['p_push']))}%"])
        sums[sport] = (total_on, lo_k, hi_k)
        panels.append({
            "name": words, "x": {"kind": "number", "label": "Total", "step": 5},
            "y": {"kind": "share", "label": "Share of games that finished exactly on K, %", "unit": "%", "digits": 1,
                  "zero": True},
            "series": [{"id": "on", "name": "Closed on K", "mark": "dot", "color": "c1", "sized": True, "points": on},
                       {"id": "half", "name": "Closed a half-point from K", "mark": "dot", "color": "c2",
                        "sized": True, "points": half},
                       {"id": "table", "name": "The key-number table", "mark": "line", "color": "ink",
                        "points": tab_},
                       {"id": "registered", "name": "The registered method", "mark": "line", "color": "ink2",
                        "points": reg}],
            "refs": []})
    title = ("Some final totals come up more often than others, but the key-number table did not beat the registered "
             f"pricing model on any of the {len(declared)} comparisons declared before the run")
    if same != len(declared):
        title = (f"The key-number table beat the registered pricing model on {len(declared) - same} of the "
                 f"{len(declared)} comparisons declared before the run")
    return chart(
        "key-numbers", src=src, title=title,
        name="Key numbers: how often a game finishes exactly on a total, NFL and college football",
        shows=("Each dot is how often a game finished exactly on a total K, when the closing total was K and when it "
               "was a half-point away; bigger dots stand on more games, and the two lines are the chances the "
               "key-number table and the registered method give."),
        not_shows=("It prices no bet: no alternate line, teaser or juice price was tested, and totals with few games "
                   "swing widely."),
        sample=(f"{sums['NFL'][0]:,} NFL closes on a whole number from {sums['NFL'][1]} to {sums['NFL'][2]} "
                f"(2015–25) and {sums['CFB'][0]:,} in college football from {sums['CFB'][1]} to {sums['CFB'][2]} "
                "(2006–25), with the half-point closes beside them"),
        n=sums["NFL"][0] + sums["CFB"][0],
        bar={"tests": [{"label": ("Where college football games land next to a half-point line (a lead found after "
                                  "the first run)"),
                        "p": lead_p, "p_words": (f"p = {fixed(lead_p, 4)} by a t-test on the {int(lead['seasons'])} "
                                                 f"seasons{variant}")}],
             "note": (f"The {len(declared)} comparisons declared before the run found no difference."
                      if same == len(declared) else "")},
        writeups=[KEY_NUMBERS], sources=[prices, loso],
        plot={"layout": "columns", "panels": panels},
        tab=table(["Sport", "K", "Closed on K: landed on K", "Closed a half-point away: landed on K",
                   "The table's chance", "The registered method's chance"], tab_rows,
                  [False, True, True, True, True, True]))


def line_moves(src: Sources) -> dict:
    lm = "strategy-research/output/line_moves.csv"
    oc = "nfl-weather/output/tables/bet_open_vs_close.csv"
    cfb = "strategy-research/output/cfb_open_vs_close.csv"
    moves, buckets, tiers = read_csv(src, lm), read_csv(src, oc), read_csv(src, cfb)
    tot = one(moves, market="total")
    all_move = f(tot["mean_move"])
    bands = [("Wind 0–4", "0–4 mph"), ("Wind 5–9", "5–9 mph"), ("Wind 10–14", "10–14 mph"), ("Wind 15–19", "15–19 mph"),
             ("Wind 20+", "20+ mph")]
    pts, tips, tab_rows, outdoor = [], {}, [], 0
    for b, label in bands:
        r = one(buckets, bucket=b)
        m, se, n = f(r["mean_move"]), f(r["move_se"]), int(r["games"])
        outdoor += n
        m4, lo4, hi4 = round(m, 4), round(m - 1.96 * se, 4), round(m + 1.96 * se, 4)
        pts.append([label, m4, lo4, hi4])
        tips[label] = [f"{n:,} games", f"Moved down in {fixed(pct(r['share_moved_down']))}%"]
        tab_rows.append(["NFL, " + label, f"{n:,}", signed(m4), f"{signed(lo4)} to {signed(hi4)}",
                         f"{fixed(pct(r['share_moved_down']))}%", "", ""])
    tab_rows.append(["NFL, all games", f"{int(tot['games']):,}", signed(round(all_move, 4)), "",
                     f"{fixed(pct(tot['share_down']))}%", "", ""])
    names = {"any Group of 5 / other": "Group of 5 and other games", "both Power 5": "Both teams Power 5"}
    bars, ctips, sizes, cfb_n = [], {}, [], 0
    for r in tiers:
        label = names.get(r["tier"], r["tier"])
        size, n = round(f(r["mean_abs_move"]), 4), int(r["games"])
        cfb_n += n
        sizes.append(size)
        bars.append([label, size])
        ctips[label] = [f"{n:,} games", f"Moved 3 or more points in {fixed(pct(r['share_move_3plus']))}%",
                        f"Typical miss: opener {fixed(r['mae_open'])}, close {fixed(r['mae_close'])} points"]
        tab_rows.append(["College football, " + label, f"{n:,}", "", "", "", fixed(size, 2),
                         f"{fixed(pct(r['share_move_3plus']))}%"])
    b20 = pts[-1][1]
    title = (f"NFL totals fell {fixed(abs(all_move), 2)} points on average from the opener to the close, and further "
             f"in wind ({signed(b20, 1)} at 20+ mph); college football totals moved {fixed(min(sizes))} to "
             f"{fixed(max(sizes))} points on average")
    return chart(
        "line-moves", src=src, title=title, name="How totals move from the opener to the close",
        shows=("The top panel is the NFL's average change in the total, opener to close, by wind at kickoff, with 95% "
               "intervals; the lower one is the average size of a college football move, up or down."),
        not_shows=(f"A move is not a bet: moves did not predict the result beyond the close (slope "
                   f"{signed(f(tot['slope_resid_on_move']))} ± {fixed(tot['slope_se'], 2)} for NFL totals), so timing "
                   "gets a better number, not a signal."),
        sample=(f"{int(tot['games']):,} NFL games, 2007–21 ({outdoor:,} outdoor games with an opener by wind band), "
                f"and {cfb_n:,} college football games"),
        n=int(tot["games"]) + cfb_n,
        bar={"tests": [], "none": "A description of how lines move, not a betting test: it adds no variant."},
        writeups=[TIMING], sources=[lm, oc, cfb],
        plot={"layout": "columns", "panels": [
            {"name": "NFL, 2007–21: change in the total from the opener to the close, by wind (points)",
             "x": {"kind": "category", "labels": [b[1] for b in bands], "label": "Wind at kickoff"},
             "y": {"kind": "points", "label": "points", "unit": " points", "digits": 2, "zero": True},
             "series": [{"id": "move", "name": "Average change, with its 95% interval", "mark": "dot", "color": "c1",
                         "points": pts}],
             "refs": [{"value": 0, "label": "No change", "role": "zero"},
                      {"value": round(all_move, 4), "label": f"All games, {signed(round(all_move, 4))}",
                       "role": "pooled"}],
             "tips": tips},
            {"name": "College football: average size of the move, up or down (points)",
             "x": {"kind": "category", "labels": [b[0] for b in bars], "label": "Games"},
             "y": {"kind": "points", "label": "points", "unit": " points", "digits": 2, "zero": True},
             "series": [{"id": "size", "name": "Average size of the move", "mark": "bar", "color": "c1",
                         "points": bars}],
             "refs": [], "tips": ctips}]},
        tab=table(["Games", "Count", "Average change (points)", "95% interval", "Moved down",
                   "Average size of the move (points)", "Moved 3 or more points"], tab_rows,
                  [False, True, True, False, True, True, True]))


BUILDERS = {
    "wind-and-scoring": wind_and_scoring,
    "wind-rule-cfb-seasons": lambda s: replay_seasons(s, "cfb"),
    "wind-rule-nfl-seasons": lambda s: replay_seasons(s, "nfl"),
    "wind-rule-units": replay_units,
    "wind-rule-opener-vs-close": opener_vs_close,
    "forecast-error-cfb": lambda s: forecast_error(s, "cfb"),
    "forecast-error-nfl": lambda s: forecast_error(s, "nfl"),
    "money-gate": money_gate,
    "keep-test": keep_test,
    "key-numbers": key_numbers,
    "line-moves": line_moves,
}


def render(c: dict) -> str:
    return json.dumps(c, ensure_ascii=False, indent=1) + "\n"


def build_all() -> dict[str, str]:
    ids = [i for _, group in GROUPS for i in group if i not in LIVE]
    if sorted(ids) != sorted(BUILDERS):
        raise Refused("the screen's list of charts and the builders differ")
    src = Sources()
    return {f"{cid}.json": render(BUILDERS[cid](src)) for cid in ids}


def committed(name: str) -> str | None:
    try:
        return subprocess.run(["git", "show", f"HEAD:{(OUT / name).as_posix()}"], capture_output=True, check=True,
                              text=True).stdout
    except subprocess.CalledProcessError:
        return None


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Prepare the Backtests screen's charts from committed tables.")
    ap.add_argument("--check", action="store_true",
                    help="compare what would be written with the committed files and exit 1 on any difference")
    args = ap.parse_args(argv)
    if not (Path("dashboard") / "content").is_dir() or Path(git("rev-parse", "--show-toplevel")).resolve() != Path.cwd().resolve():
        print("Run this from the repo root: nfl-weather/.venv/bin/python dashboard/tools/build_charts.py", file=sys.stderr)
        return 2
    try:
        import pandas  # noqa: F401  (the two forecast replays' parquet files need it)
    except ImportError:
        print("No chart was written or checked: this tool needs pandas, to read the two forecast replays' parquet "
              "files, and this Python doesn't have it. Run it with a weather project's Python: "
              "nfl-weather/.venv/bin/python dashboard/tools/build_charts.py", file=sys.stderr)
        return 1
    try:
        files = build_all()
    except Refused as e:
        print(f"No chart was written: {e}.", file=sys.stderr)
        return 2
    on_disk = {p.name for p in OUT.glob("*.json")} if OUT.is_dir() else set()
    if args.check:
        bad = []
        for name, text in files.items():
            head = committed(name)
            disk = (OUT / name).read_text(encoding="utf-8") if (OUT / name).is_file() else None
            if head is None:
                bad.append(f"{name}: not committed")
            elif head != text:
                bad.append(f"{name}: the committed file differs from what the tables give now")
            if disk is None:
                bad.append(f"{name}: missing from {OUT}")
            elif disk != text:
                bad.append(f"{name}: the file on disk differs from what the tables give now")
        for name in sorted(on_disk - set(files)):
            bad.append(f"{name}: in {OUT} but not made by this tool")
        if bad:
            print("The charts are not up to date:\n  " + "\n  ".join(bad), file=sys.stderr)
            return 1
        print(f"All {len(files)} chart files match the committed tables.")
        return 0
    OUT.mkdir(parents=True, exist_ok=True)
    changed = 0
    for name, text in files.items():
        p = OUT / name
        if not p.is_file() or p.read_text(encoding="utf-8") != text:
            p.write_text(text, encoding="utf-8")
            changed += 1
    extra = sorted(on_disk - set(files))
    print(f"Wrote {changed} of {len(files)} chart files to {OUT}." + (
        f" Not made by this tool, left alone: {', '.join(extra)}." if extra else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
