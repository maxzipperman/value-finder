"""`uv run markets price-engine`: the price-engine backtest on F1 (issues #8 and #53), in one command.

Today, before F1 exists, it prints that there is nothing to backtest and stops. `--fixture` runs the whole
pipeline on a small synthetic fixture instead (nothing in it is data). Once F1 is pulled
(docs/ODDS5M_DAY_ONE.md), the same command reads F1 from the cache, sealed seasons left out, and writes:

  reports/price_engine/results.csv   one row per variant (the variant count printed is its row count)
  reports/price_engine/report.md     the write-up: results, decisions under the draft rule, books, lag, calibration
  reports/price_engine/bets.parquet  every bet with its grading (gitignored)
  reports/price_engine/dropped.csv   what was left out, by reason
"""
from __future__ import annotations

import math
import subprocess
import tempfile
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

from ...cache import RawCache
from ...oddsapi import bulk
from ...settings import REPORTS_DIR, utcnow
from . import engine, outcomes
from .model import LABEL
from .quotes import f1_calls, load_quotes

DAILY_NOTE = ("F1 has one snapshot a day (16:00 UTC, up to 7 days out) plus the close, so this backtest only finds "
              "price gaps that last for hours. Gaps that open and close within minutes, the kind Kaunitz et al. "
              "found with minute data and issue #53 describes, are invisible to it.")
DRAFT = "strategy-research/price-engine-preregistration-draft.md"


def run(cfg: dict, calls: list, cache: RawCache, *, scores: pd.DataFrame | None = None,
        cfb_raw: Path | None = None) -> dict:
    """The whole backtest. `scores` overrides the outcome join (the fixture passes its own)."""
    q, drops = load_quotes(cfg, calls, cache)
    out = {"quotes": q, "drops": drops, "calls": len(calls), "sealed_calls": sum(bool(c.sealed) for c in calls)}
    if q.empty:
        return out
    fair = engine.fair_table(q)
    sides = engine.side_rows(q, fair)
    cl = engine.closes(q)
    events = q[["sport", "event_id", "kickoff", "home", "away"]].drop_duplicates(["sport", "event_id"])
    unmatched: Counter = Counter()
    if scores is None:
        scores, unmatched = outcomes.match(events, cfb_raw=cfb_raw)
    graded = {}
    for v in engine.VARIANTS:
        graded[v.id] = engine.grade(engine.entries(sides, v), cl, scores).assign(variant=v.id)
    out.update(fair=fair, comparable=engine.comparable(q, fair), closes=cl, scores=scores, unmatched=unmatched,
               graded=graded, results=engine.results_table(graded), books=engine.by_book(graded),
               lag=engine.lag_frequency(q), calibration=engine.calibration(q, cl, scores))
    return out


def _fmt(x, nd=2) -> str:
    if isinstance(x, str):
        return x
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "–"
    if isinstance(x, (bool, np.bool_)):
        return "yes" if x else ""
    if isinstance(x, (int, np.integer)):
        return f"{int(x):,}"
    return f"{x:,.{nd}f}"


def table(df: pd.DataFrame, cols: list[str], nd: int = 2) -> str:
    if df.empty:
        return "_(none)_\n"
    lines = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for r in df[cols].itertuples(index=False):
        lines.append("| " + " | ".join(_fmt(v, nd) for v in r) + " |")
    return "\n".join(lines) + "\n"


def _commit() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True,
                              cwd=Path(__file__).parent, timeout=10).stdout.strip() or "unknown"
    except Exception:       # no git here: the report still writes
        return "unknown"


RESULT_COLS = ["variant", "bets", "games", "ev_entry_pct", "clv_pin_cents", "clv_pin_se", "clv_pin_p", "clv_own_cents",
               "clv_pin_pts", "clv_own_pts", "seasons_positive", "seasons_counted", "top_book", "win_rate", "roi",
               "roi_lo", "roi_hi", "decision"]


def report(res: dict, results: pd.DataFrame, *, fixture: bool) -> str:
    n = len(results)
    head = ["# Price-engine backtest (F1)" + (" — SYNTHETIC FIXTURE, NOT DATA" if fixture else ""), "",
            f"Run {utcnow():%Y-%m-%d %H:%M} UTC from commit {_commit()}. Rules: `{DRAFT}` "
            "(a draft until the hub registers it). Sealed 2026 seasons left out.", "",
            f"**{DAILY_NOTE}**", "",
            f"Variants tested: **{n}**. Running count with them: {engine.RUNNING_COUNT}; the bar is "
            f"p < 0.05 / {engine.RUNNING_COUNT} = {engine.ALPHA:.5f} (one-sided, on CLV against Pinnacle's close).", "",
            "Reading the table: `clv_pin_cents` is the average of (Pinnacle's no-vig closing probability of the bet's "
            "side at the bet's line) minus (the break-even probability of the price taken), in cents; above zero means "
            "the price beat Pinnacle's close. `clv_own_*` is the same against the entry book's own close. Points are "
            "for spreads and totals only. ROI is flat one-unit bets at the price taken, pushes left out; its "
            "interval is 95%. Standard errors are clustered by game.", ""]
    body = ["## Results, one row per variant", "", table(results, RESULT_COLS)]
    if "quotes" in res and not res["quotes"].empty:
        q = res["quotes"]
        cov = q.groupby(["sport", "season"]).agg(games=("event_id", "nunique"), snapshots=("snap", "nunique"),
                                                 quotes=("book", "size")).reset_index()
        cov["sport"] = cov.sport.map(LABEL)
        comp = pd.DataFrame(list(res["comparable"].items()), columns=["retail quotes", "quotes"])
        body += ["## What was loaded", "", table(cov, ["sport", "season", "games", "snapshots", "quotes"]),
                 f"F1 snapshots flagged sealed: {res['sealed_calls']:,} of {res['calls']:,}; their 2026 games are "
                 "left out by `bulk.load_rows` before anything here sees them.", "",
                 table(comp, ["retail quotes", "quotes"]),
                 "Quotes left out, by reason (a quote is one book's two-sided market at one snapshot; nothing is "
                 "dropped silently):", "",
                 table(pd.DataFrame(sorted(res["drops"].items()), columns=["reason", "quotes"]), ["reason", "quotes"]),
                 "Games with no final score (kept for CLV, left out of the realized result):", "",
                 table(pd.DataFrame(sorted(res.get("unmatched", {}).items()), columns=["reason", "games"]),
                       ["reason", "games"]),
                 "## Primary cells by book (issue #53: which books lag)", "",
                 table(res["books"], ["variant", "book", "bets", "clv_pin_cents", "clv_own_cents", "clv_pin_pts",
                                      "clv_own_pts", "roi"]),
                 "## How often a retail total sits a point or more off Pinnacle's (descriptive)", "",
                 "`still_off_next_snapshot`: of those gaps, the share still open at that book's next snapshot of the "
                 "same game, usually a day later. Daily data can't say how long a gap lasts within the day.", "",
                 table(res["lag"], ["sport", "book", "quotes", "share_1pt_off", "still_off_next_snapshot"], 3),
                 "## Is Pinnacle's no-vig close a fair probability? (descriptive, no decision)", "",
                 "Side a is home (moneyline, spread) or over (total). `excess` = actual minus predicted.", "",
                 table(res["calibration"], ["sport", "market", "games", "predicted_side_a", "actual_side_a", "excess",
                                            "excess_se"], 3)]
    body += ["## What this cannot show", "",
             "- Gaps shorter than a few hours (see above), and how long any gap lasted within a day.",
             "- Whether a posted price was fillable, or for how much: the Odds API shows quotes, not limits.",
             "- Voids and account limits: books void obvious errors and limit accounts that take stale numbers. "
             "`bets_ev_10plus` in results.csv counts the flags most likely to be voided.",
             "- Spreads and moneylines at a line other than Pinnacle's (left out of the primary analysis).", ""]
    return "\n".join(head + body)


def main(args) -> int:
    if args.fixture:
        tmp = Path(tempfile.mkdtemp(prefix="price-engine-fixture-"))
        from .fixture import build
        cfg, calls, cache, scores = build(tmp)
        print(f"SYNTHETIC FIXTURE (not data), in {tmp}")
        res = run(cfg, calls, cache, scores=scores)
        out_dir = Path(args.out) if args.out else tmp / "report"
    else:
        cfg, cache = bulk.load_config(), RawCache()
        calls = f1_calls(cfg, cache)
        cached = sum(1 for c in calls if cache.lookup(c.cache_sport, c.source, c.key) is not None)
        if not calls or not cached:
            print("No F1 data yet: " + ("no NFL or CFB schedule has been saved (`markets odds5m probe` runs first)"
                                        if not calls else f"0 of F1's {len(calls):,} planned snapshots are cached")
                  + ". Nothing to backtest.")
            print(f"The {len(engine.VARIANTS)} variants and every threshold are fixed in code and in {DRAFT}.")
            print("On data day: `uv run markets odds5m full --pull F1 ...`, then `uv run markets price-engine`.")
            print(DAILY_NOTE)
            return 0
        print(f"F1: {cached:,} of {len(calls):,} planned snapshots cached"
              + ("" if cached == len(calls) else " (a partial pull: the results cover only what is cached)"))
        res = run(cfg, calls, cache)
        out_dir = Path(args.out) if args.out else REPORTS_DIR / "price_engine"
    if res["quotes"].empty:
        print("F1 is cached but no quote survived loading (dropped: "
              + ", ".join(f"{k} {v:,}" for k, v in res["drops"].most_common()) + "). Nothing to backtest.")
        return 0
    results = res["results"]
    out_dir.mkdir(parents=True, exist_ok=True)
    results.to_csv(out_dir / "results.csv", index=False)
    pd.DataFrame(sorted(res["drops"].items()), columns=["reason", "quotes"]).to_csv(out_dir / "dropped.csv",
                                                                                    index=False)
    bets = pd.concat([g for g in res["graded"].values() if len(g)], ignore_index=True) if any(
        len(g) for g in res["graded"].values()) else pd.DataFrame()
    if len(bets):
        bets.to_parquet(out_dir / "bets.parquet", index=False)
    (out_dir / "report.md").write_text(report(res, results, fixture=bool(args.fixture)))
    with pd.option_context("display.width", 200, "display.max_columns", 20, "display.max_rows", 100):
        print(results[["variant", "bets", "clv_pin_cents", "clv_pin_p", "clv_own_cents", "roi", "decision"]]
              .to_string(index=False))
    print(DAILY_NOTE)
    print(f"variants tested: {len(results)} (rows in results.csv); running count {engine.RUNNING_COUNT}, "
          f"bar p < {engine.ALPHA:.5f}")
    print(f"wrote {out_dir}/report.md and results.csv")
    return 0
