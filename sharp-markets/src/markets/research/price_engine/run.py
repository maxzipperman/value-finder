"""`uv run markets price-engine`: the price-engine backtest on F1 (issues #8 and #53), in one command.

Today, before F1 exists, it prints that there is nothing to backtest and stops. `--fixture` runs the whole
pipeline on a small synthetic fixture instead (nothing in it is data). Once F1 is pulled
(docs/ODDS5M_DAY_ONE.md), the same command reads F1 from the cache, sealed seasons left out, and writes:

  reports/price_engine/results.csv   one row per variant (the variant count printed is its row count)
  reports/price_engine/report.md     the write-up: results, decisions under the registered rule, books, lag, calibration
  reports/price_engine/bets.parquet  every bet with its grading (gitignored)
  reports/price_engine/dropped.csv   what was left out, by reason

`--handoff <bundle> --handoff-root <sha256>` reads F1 as pulled by the football archive bundle instead of planning
the legacy F1 call set (issue #101; amendment 2, a DRAFT until the hub registers it). See handoff.py: the bundle's
code runs, so the folder is verified against its FREEZE.json and the pinned root before anything in it is imported.
Everything after loading is the same `run(cfg, calls, cache)`.
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

DAILY_NOTE = ("F1 sees each game at 16:00 UTC on each of the 7 days before kickoff and, on busy days, also at every "
              "other game's close (each snapshot lists every game). A price gap shows up only if it is open at one "
              "of those moments, so gaps that last minutes, the kind Kaunitz et al. found with minute data and "
              "issue #53 describes, are mostly missed, and nothing here says how long any gap lasted.")
PREREG = "sharp-markets/docs/PRICE_ENGINE_PREREGISTRATION.md"


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
    out["home_away_changed"] = home_away_changed(q)
    unmatched: Counter = Counter()
    detail: dict = {}
    if scores is None:
        scores, unmatched = outcomes.match(events, cfb_raw=cfb_raw, detail=detail)
    out.update(names=detail.get("names"), cfb_team_files=detail.get("cfb_team_files"),
               coverage=score_coverage(q, scores))
    graded = {}
    for v in engine.VARIANTS:
        graded[v.id] = engine.grade(engine.entries(sides, v), cl, scores).assign(variant=v.id)
    out.update(fair=fair, comparable=engine.comparable(q, fair), closes=cl, scores=scores, unmatched=unmatched,
               graded=graded, results=engine.results_table(graded), books=engine.by_book(graded),
               lag=engine.lag_frequency(q), calibration=engine.calibration(q, cl, scores))
    return out


def home_away_changed(q: pd.DataFrame) -> int:
    """Descriptive, nothing is excluded for it (amendment 1, known limit): how many games are listed with more than
    one (home, away) pair across their quotes. Nothing guards against the feed swapping home and away between
    snapshots: a bet's CLV would be graded against the other side's close, and the final score goes on the first
    listing, so a swap before the entry would flip the result. Whether to exclude such games is the hub's decision."""
    listing = q[["sport", "event_id", "home", "away"]].drop_duplicates()
    return int((listing.groupby(["sport", "event_id"]).size() > 1).sum())


MIN_SCORE_SHARE = 0.95      # amendment 1, item 8: below this share of a season's games scored, the first page says so


def score_coverage(q: pd.DataFrame, scores: pd.DataFrame) -> pd.DataFrame:
    """Per sport and season: the games loaded, how many were matched to a final score, and the share."""
    ev = q[["sport", "season", "event_id"]].drop_duplicates(["sport", "event_id"])
    got = set(zip(scores.sport, scores.event_id)) if len(scores) else set()
    ev = ev.assign(matched=[(s, e) in got for s, e in zip(ev.sport, ev.event_id)])
    cov = ev.groupby(["sport", "season"]).agg(games=("event_id", "size"), matched=("matched", "sum")).reset_index()
    cov["matched"] = cov.matched.astype(int)
    cov["share"] = cov.matched / cov.games
    cov["sport"] = cov.sport.map(LABEL)
    return cov


def _names_line(res: dict) -> str:
    """Whether the college team files were found, and how many names needed the prefix rule or did not resolve."""
    names = res.get("names")
    if names is None:
        return ("Team names: not resolved in this run (the scores were supplied with the input, as the fixture "
                "does).")
    files = res.get("cfb_team_files")
    if files is None:
        where = "no college game was loaded, so the college team files were not needed"
    elif files:
        where = f"the college team files (cfbfastR team_info) were found ({files} files)"
    else:
        where = ("the college team files (cfbfastR team_info) were NOT found: college names were resolved by the "
                 "alias table, exact school names and the prefix rule only")
    weak = names[names.how.isin([outcomes.PREFIX, outcomes.UNRESOLVED])]
    return (f"Team names: {where}. {len(weak):,} distinct names resolved only by the prefix rule or not at all "
            "(listed below the table of games with no final score).")


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


RESULT_COLS = ["variant", "bets", "clv_pin_n", "graded", "pushes", "games", "ev_entry_pct", "clv_pin_expected",
               "clv_pin_cents", "clv_pin_se", "clv_pin_p", "clv_pin_pts", "clv_own_cents", "clv_own_pts",
               "seasons_positive", "seasons_counted", "seasons_20_closes", "top_book", "win_rate", "roi", "roi_lo",
               "roi_hi", "decision"]
MOVED_COLS = ["variant", "bets", "clv_pin_n", "clv_pin_same_n", "clv_pin_cents_same", "clv_pin_moved_n",
              "clv_pin_cents_moved", "clv_pin_cents", "clv_pin_pts"]


def report(res: dict, results: pd.DataFrame, *, fixture: bool) -> str:
    n = len(results)
    head = ["# Price-engine backtest (F1)" + (" — SYNTHETIC FIXTURE, NOT DATA" if fixture else ""), "",
            f"Run {utcnow():%Y-%m-%d %H:%M} UTC from commit {_commit()}. Rules: `{PREREG}` "
            "(registered September 29, 2026; amendment 1, September 30, 2026). Sealed 2026 seasons left out.", "",
            f"**{DAILY_NOTE}**", ""]
    if res.get("handoff"):
        h = res["handoff"]
        head += [f"F1 as pulled: the football archive bundle's priority-1 manifest, read through `--handoff` "
                 f"(amendment 2, a DRAFT until the hub registers it). Bundle root `{h['bundle_root_sha256']}`, request "
                 f"set `{h['request_set_sha256']}`, coverage report `{h['coverage_report_sha256']}`; "
                 f"{h['calls']:,} calls, {h['reused']:,} of them reused from the bundle's `reuse/`.", ""]
    cov = res.get("coverage")
    if cov is not None and len(cov) and (cov.share < MIN_SCORE_SHARE).any():
        low = cov[cov.share < MIN_SCORE_SHARE]
        head += [f"**Final scores: fewer than {MIN_SCORE_SHARE:.0%} of games were matched to a final score in "
                 + ", ".join(f"{r.sport} {r.season} ({r.share:.1%}, {r.matched:,} of {r.games:,})"
                             for r in low.itertuples(index=False))
                 + ". Unmatched games are left out of the realized result (the ROI, K2 and the count of results "
                 "that item 4 needs) and of the calibration table; see \"Final scores matched\" below "
                 "(amendment 1, item 8).**", ""]
    head += [_names_line(res), "",
            f"Variants tested: **{n}**. Running count with them: {engine.PRIOR_COUNT} before + {n} = "
            f"{engine.RUNNING_COUNT}; the bar is p < 0.05 / {engine.RUNNING_COUNT} = {engine.ALPHA:.6f} (one-sided, "
            "on CLV against Pinnacle's close).", "",
            "Reading the table: `clv_pin_cents` is the average of (Pinnacle's no-vig closing probability of the bet's "
            "side at the bet's line) minus (the break-even probability of the price taken), in cents; above zero means "
            "the price beat Pinnacle's close. `clv_pin_n` is how many bets had a Pinnacle close to grade against. "
            "`clv_pin_expected` is what an efficient Pinnacle implies (EV / price, about 1 cent for a 2% flag): a "
            "cell near it means the flags held their value to the close; well below it, Pinnacle moved toward the "
            "retail price. `clv_own_*` is the same against the entry book's own close. Points (`*_pts`) are for "
            "spreads and totals only, and need no conversion between numbers. ROI is flat one-unit bets at the price "
            "taken, pushes left out; its interval is 95%. Standard errors are clustered by game. `graded` is how "
            "many bets have a final score that won or lost, and `pushes` how many have a final score that pushed: "
            "a primary cell with fewer than 100 `graded` cannot act (amendment 1, item 4; pushes do not count "
            "toward the 100). A2's seasons (amendment 1, item 1): `seasons_counted` have 20 or more bets, "
            "`seasons_20_closes` have 20 or more bets with a Pinnacle close, and `seasons_positive` are counted "
            "seasons with 20 or more closes and mean CLV above zero. `top_book` lists every book tied for the most "
            "bets (amendment 1, item 3).", ""]
    moved = results[results.market.isin(["spreads", "totals"]) & results.primary]
    body = ["## Results, one row per variant", "", table(results, RESULT_COLS),
            "## Closes at another number (primary spread and total cells)", "",
            "When Pinnacle closed at a number other than the bet's, its close was converted to the bet's number "
            "(totals: the registered model; spreads: the declared margin table, `model.cover_at`). `same` is the "
            "bets whose Pinnacle close stayed on the bet's number, `moved` the converted ones. If `moved` is well "
            "below `same`, Pinnacle's later moves went against the flags (the stale-Pinnacle failure), and the "
            "points column says the same without any conversion.", "",
            table(moved, MOVED_COLS)]
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
                 "Games listed with more than one (home, away) pair across their quotes (the teams swapped, or a "
                 f"name spelled two ways): {res.get('home_away_changed', 0):,}. Descriptive; nothing is excluded "
                 "for it. Nothing guards against a swap: CLV would be graded against the other side's close, and "
                 "the final score goes on the first listing (amendment 1, known limit; excluding such games is the "
                 "hub's decision).", "",
                 "Quotes left out, by reason (a quote is one book's two-sided market at one snapshot; nothing is "
                 "dropped silently):", "",
                 table(pd.DataFrame(sorted(res["drops"].items()), columns=["reason", "quotes"]), ["reason", "quotes"]),
                 "## Final scores matched, per sport and season (amendment 1, item 8)", "",
                 table(res["coverage"], ["sport", "season", "games", "matched", "share"], 3)
                 if res.get("coverage") is not None else "_(none)_\n",
                 "Games with no final score (kept for CLV, left out of the realized result). "
                 "`cfb_prefix_name_no_game`: no game found; a name was resolved by the prefix rule (the name may "
                 "be wrong, or the game missing from the score table); "
                 "`*_team_name_unknown`: a name did not resolve at all:", "",
                 table(pd.DataFrame(sorted(res.get("unmatched", {}).items()), columns=["reason", "games"]),
                       ["reason", "games"]),
                 _names_line(res), "",
                 table(res["names"][res["names"].how.isin([outcomes.PREFIX, outcomes.UNRESOLVED])]
                       if res.get("names") is not None else pd.DataFrame(),
                       ["sport", "name", "resolves_to", "how", "games"]),
                 "## Primary cells by book (issue #53: which books lag)", "",
                 table(res["books"], ["variant", "book", "bets", "clv_pin_cents", "clv_own_cents", "clv_pin_pts",
                                      "clv_own_pts", "roi"]),
                 "## How often a retail total sits a point or more off Pinnacle's (descriptive)", "",
                 "`still_off_next_snapshot`: of those gaps, the share still open at that book's next snapshot of the "
                 "same game. That is a day later early in the week, but on game days often another game's close, "
                 "minutes to a few hours later, so it is not a measure of how long gaps last.", "",
                 table(res["lag"], ["sport", "book", "quotes", "share_1pt_off", "still_off_next_snapshot"], 3),
                 "## Is Pinnacle's no-vig close a fair probability? (descriptive, no decision)", "",
                 "Side a is home (moneyline, spread) or over (total). `excess` = actual minus predicted.", "",
                 table(res["calibration"], ["sport", "market", "games", "predicted_side_a", "actual_side_a", "excess",
                                            "excess_se"], 3)]
    body += ["## What this cannot show", "",
             "- Most short-lived gaps (see above), and how long any gap lasted.",
             "- Exact CLV for a close at another number. Totals go through the registered windy cohort (656 NFL and "
             "855 CFB games through 2023, 92 and 236 of them from 2020-23, inside the backtest); spreads through a "
             "margin table from the seasons before 2020. The points columns need neither.",
             "- Whether a posted price was fillable, or for how much: the Odds API shows quotes, not limits.",
             "- Voids and account limits: books void obvious errors and limit accounts that take stale numbers. "
             "`bets_ev_10plus` in results.csv counts the flags most likely to be voided.",
             "- Retail spreads at a number other than Pinnacle's: never flagged (only their closes are converted).",
             ""]
    return "\n".join(head + body)


def main(args) -> int:
    bundle = getattr(args, "handoff", None)
    if bundle and args.fixture:
        raise SystemExit("price-engine: --handoff and --fixture are alternatives; give one")
    if not bundle and (getattr(args, "handoff_root", None) or getattr(args, "handoff_runtime", None)):
        raise SystemExit("price-engine: --handoff-root and --handoff-runtime need --handoff")
    if args.fixture:
        tmp = Path(tempfile.mkdtemp(prefix="price-engine-fixture-"))
        from .fixture import build
        cfg, calls, cache, scores = build(tmp)
        print(f"SYNTHETIC FIXTURE (not data), in {tmp}")
        res = run(cfg, calls, cache, scores=scores)
        out_dir = Path(args.out) if args.out else tmp / "report"
    elif bundle:
        from . import handoff
        cfg = bulk.load_config()
        try:
            calls, cache, info = handoff.load(bundle, getattr(args, "handoff_root", None), cfg,
                                              getattr(args, "handoff_runtime", None))
        except handoff.HandoffRefused as exc:
            raise SystemExit(f"price-engine --handoff refused (no price read, nothing written): {exc}") from None
        print(f"F1 as pulled (football archive bundle {info['bundle_root_sha256']}): {info['calls']:,} calls, "
              f"{info['reused']:,} of them reused from the bundle's reuse/, every response hash-checked "
              "(amendment 2, DRAFT until the hub registers it)")
        res = run(cfg, calls, cache)
        res["handoff"] = info
        out_dir = Path(args.out) if args.out else REPORTS_DIR / "price_engine"
    else:
        cfg, cache = bulk.load_config(), RawCache()
        calls = f1_calls(cfg, cache)
        cached = sum(1 for c in calls if cache.lookup(c.cache_sport, c.source, c.key) is not None)
        if not calls or not cached:
            print("No F1 data yet: " + ("no NFL or CFB schedule has been saved (`markets odds5m probe` runs first)"
                                        if not calls else f"0 of F1's {len(calls):,} planned snapshots are cached")
                  + ". Nothing to backtest.")
            print(f"The {len(engine.VARIANTS)} variants and every threshold are fixed in code and in {PREREG}.")
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
        print(results[["variant", "bets", "clv_pin_n", "clv_pin_expected", "clv_pin_cents", "clv_pin_p", "clv_pin_pts",
                       "clv_own_cents", "roi", "decision"]].to_string(index=False))
    print(DAILY_NOTE)
    print(f"variants tested: {len(results)} (rows in results.csv); running count {engine.RUNNING_COUNT}, "
          f"bar p < {engine.ALPHA:.6f}")
    print(f"wrote {out_dir}/report.md and results.csv")
    return 0
