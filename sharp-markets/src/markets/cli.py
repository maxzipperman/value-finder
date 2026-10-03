"""Command-line entry point: `uv run markets <command> ...`."""
from __future__ import annotations

import argparse
import collections
import logging
import sys
from datetime import date
from pathlib import Path

from .context import Context
from .games import select_games


def _margin(value: str) -> int:
    """--alarm-margin: whole credits, at least 300; "23,940", as `markets odds5m headers` prints it, is read as 23940."""
    n = int(value.replace(",", ""))
    if n < 300:
        raise argparse.ArgumentTypeError(f"{n} is below 300; the alarm's margin is at least 300 credits")
    return n


def _dates(args) -> tuple[date, date]:
    return date.fromisoformat(args.start), date.fromisoformat(args.end)


def cmd_discover(args) -> None:
    ctx = Context(args.sport, args.as_of)
    d = ctx.discovery
    games = ctx.games
    print(f"cutoff: {d.cutoff}")
    print(f"series {d.series['ticker']}: fee_type={d.series.get('fee_type')} "
          f"fee_multiplier={d.series.get('fee_multiplier')} fee_changes={d.series_fee_changes}")
    print(f"events={len(d.events)} markets={len(d.markets)} "
          f"(historical={sum(m['_endpoint'] == 'historical' for m in d.markets)}, "
          f"live={sum(m['_endpoint'] == 'live' for m in d.markets)}) games={len(games)}")
    by = collections.Counter((g.season, g.phase) for g in games)
    for (season, phase), n in sorted(by.items(), key=lambda kv: (str(kv[0][0]), kv[0][1])):
        print(f"  {season or '-':8} {phase:18} {n:5}")
    reasons = collections.Counter(r for g in games for r, _, _ in g.exclusions)
    print("exclusion reasons:", dict(reasons))
    print(f"http requests this run: {ctx.cache.http_requests}")


def cmd_kalshi(args) -> None:
    from .kalshi.ingest import fetch_candles, fetch_event_fees, fetch_trades
    ctx = Context(args.sport, args.as_of)
    start, end = _dates(args)
    games = select_games(ctx.games, start, end)
    skipped = select_games(ctx.games, start, end, include_excluded=True)
    print(f"{len(games)} in-scope games ({len(skipped) - len(games)} excluded games in range are skipped)")
    n_c = fetch_candles(ctx.kalshi, ctx.cfg, games)
    n_t = fetch_trades(ctx.kalshi, ctx.cfg, games, ctx.discovery.cutoff)
    n_f = fetch_event_fees(ctx.kalshi, games, args.as_of)
    print(f"candles={n_c} trades={n_t} event_fee_changes={n_f} http requests={ctx.cache.http_requests}")


def cmd_cup_calendar(args) -> None:
    from .espn import pull_cup_calendar
    ctx = Context(args.sport, args.as_of)
    path, rows, problems = pull_cup_calendar(ctx, args.season)
    print(f"wrote {len(rows)} NBA Cup games to {path} (review_status=unreviewed — please review)")
    print("by round:", dict(collections.Counter(r["cup_round"] for r in rows)))
    kalshi = {(str(g.game_date_et), frozenset((g.away_code, g.home_code))) for g in ctx.games}
    missing = [r for r in rows if (r["game_date_et"], frozenset((r["away_code"], r["home_code"]))) not in kalshi]
    print(f"cup games without a matching Kalshi game: {len(missing)}", [(r['game_date_et'], r['away_code'], r['home_code']) for r in missing][:10])
    for p in problems:
        print("PROBLEM:", p)


ALARM_HELP = ("the alarm's margin in credits (at least 300): the run stops when the account has fallen by more than "
              "this beyond what it counted; default the larger of 5,000 and 10%% of --max-credits")


def cmd_odds_plan(args, *, pull: bool = False) -> int:
    """odds-plan, and odds-pull (exit status 1 when the pull stopped, 0 when it is done or a dry run)."""
    from .oddsapi.ingest import pull_snapshots, snapshot_plan
    ctx = Context(args.sport, args.as_of)
    start, end = _dates(args)
    games = select_games(ctx.games, start, end)
    plan = snapshot_plan(ctx, games, args.schedule)
    print(f"schedule {args.schedule} for {len(games)} games {start}..{end}: {plan['summary']}")
    print(f"  tiers: {plan['tiers']}  bookmakers={','.join(plan['bookmakers'])}  "
          f"credits/snapshot={plan['credits_per_snapshot']}")
    print(f"  cached={plan['cached']}  to fetch={len(plan['todo'])}  estimated credits={plan['est_credits']:,}")
    if not pull:
        return 0
    if not args.confirm:
        print("dry run: add --confirm to spend credits")
        return 0
    res = pull_snapshots(ctx, plan, args.max_credits, floor=args.floor, alarm_margin=args.alarm_margin)
    return 1 if res["stopped"] else 0


def cmd_build(args) -> None:
    from .build.run import build
    ctx = Context(args.sport, args.as_of)
    s = build(ctx)
    print("tables:", s["tables"])
    print("games by match_status:", s["match_status"])
    print("exclusions by reason:", s["exclusions"])
    print("anomalies by kind:", s["anomalies"])
    sealed = s["sealed_odds_rows_left_out"]
    print(f"odds rows left out for games in sealed seasons (config/odds5m.yaml): {sum(sealed.values()):,}",
          sealed or "")
    if s["odds_rows_without_commence_time"]:
        print(f"odds rows left out with no readable game time: {s['odds_rows_without_commence_time']:,}")
    if s["odds_bodies_unreadable"]:
        print(f"cached odds responses that could not be read, skipped: {s['odds_bodies_unreadable']:,} (recorded as "
              "an odds_body_unreadable anomaly; tell the hub)")
    print(f"http requests this run: {ctx.cache.http_requests}")


def cmd_backtest(args) -> None:
    from .analysis.run import run_backtest
    ctx = Context(args.sport, args.as_of)
    start, end = _dates(args)
    res = run_backtest(ctx, start, end)
    print(f"n_variants_tested={res['n_variants']}; report: {res['report']}")


def cmd_h3(args) -> None:
    from .research.kaggle_h3 import run
    top, own = getattr(args, "sport", "nba"), getattr(args, "h3_sport", None)
    if own and top not in ("nba", own):
        raise SystemExit(f"h3-kaggle: two different sports given (--sport {top} and --sport {own}).")
    sport = own or top
    if sport not in ("nba", "nfl"):
        raise SystemExit(f"h3-kaggle: no registered test for the sport {sport!r} (only nba and nfl).")
    if sport == "nba":
        if args.check_only or args.nfl_dir:
            raise SystemExit("--check-only and --nfl-dir are for --sport nfl only.")
        res = run("nba")
        print(f"rows={res['n_rows']} games={res['n_games']} unknown teams={res['unknown_teams']} "
              f"kalshi-joined={res['kalshi_joined_games']} n_variants_tested={res['n_variants']}")
        print(f"report: {res['report']}")
        return
    res = run(sport, nfl_dir=args.nfl_dir, check_only=args.check_only)
    if args.check_only:
        print("check only: no result computed and no report written. No score is read. Won flags are touched only by "
              "the exact-duplicate check, which compares every column as text, and no flag's value is read. Prices, "
              "shares and lines are read only for the format counts below.")
        for line in res["check"]:
            print(f"  {line}")
        return
    print(f"rows={res['n_rows']} joined={res['n_joined']} with scores={res['n_games']} "
          f"unknown teams={res['unknown_teams']} n_variants_tested={res['n_variants']}")
    print(f"report: {res['report']}")


def cmd_h4a(args) -> None:
    from pathlib import Path

    from .research.nfl_weather import run_h4a
    res = run_h4a(Path(args.nfl_dir), season=args.season, as_of=args.as_of)
    print(f"ladders matched={len(res['rows'])} valid T-5m={len(res['valid'])} unmatched={len(res['unmatched'])} "
          f"n_variants_tested={res['n_variants']}")
    print(f"report: {res['report']}")


def cmd_collect(args) -> None:
    import json

    from .collector import Collector
    from .settings import parse_ts
    if not args.now:
        row = Collector(args.sport).tick()
    else:                                   # a pretend time never touches the live state, cache or credits
        import tempfile
        from pathlib import Path
        scratch = Path(tempfile.mkdtemp(prefix="collector-now-"))
        print(f"--now: dry run in {scratch} (no Odds API credits; live state untouched)")
        row = Collector(args.sport, data_dir=scratch, dry_run=True).tick(parse_ts(args.now))
    if row:
        print(json.dumps(row, default=str))


def cmd_weather(args) -> None:
    from .weather import join
    join.main(args)


def cmd_odds5m(args) -> int:
    from .oddsapi import bulk
    return bulk.main(args)


def cmd_price_engine(args) -> None:
    from .research.price_engine import run
    run.main(args)


def cmd_props_grade(args) -> int:
    from .research.props_grade import run
    return run.main(args)


def main(argv: list[str] | None = None) -> None:
    from .http import scrub_log_handlers
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    scrub_log_handlers()        # every log line, from any logger, with keys blanked (markets.http.scrub)
    p = argparse.ArgumentParser(prog="markets", description="Paper-only Kalshi vs sharp-book research pipeline")
    p.add_argument("--sport", default="nba")
    p.add_argument("--as-of", default="v1", help="cache label for listing endpoints; change to refresh")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("discover", help="list events/markets, cutoff, fees (cache-first)").set_defaults(fn=cmd_discover)

    c = sub.add_parser("cup-calendar", help="one-time ESPN NBA Cup pull -> CSV for review")
    c.add_argument("--season", required=True)
    c.set_defaults(fn=cmd_cup_calendar)

    k = sub.add_parser("kalshi", help="fetch candles + trades + event fee overrides for a date range")
    k.add_argument("--start", required=True)
    k.add_argument("--end", required=True)
    k.set_defaults(fn=cmd_kalshi)

    for name, pull in (("odds-plan", False), ("odds-pull", True)):
        o = sub.add_parser(name, help="historical sharp-odds snapshot plan" + (" + budgeted pull" if pull else " (free)"))
        o.add_argument("--start", required=True)
        o.add_argument("--end", required=True)
        o.add_argument("--schedule", default="A", choices=["A", "B", "C", "D"])
        if pull:
            o.add_argument("--confirm", action="store_true", help="actually spend credits")
            o.add_argument("--max-credits", type=int, required=True)
            o.add_argument("--floor", type=int, default=531_630,
                           help="stop when the account would drop below this (the same reserve as odds5m)")
            o.add_argument("--alarm-margin", type=_margin, default=None, help=ALARM_HELP)
        o.set_defaults(fn=lambda a, _pull=pull: cmd_odds_plan(a, pull=_pull))

    sub.add_parser("build", help="rebuild DuckDB tables from the raw cache").set_defaults(fn=cmd_build)

    b = sub.add_parser("backtest", help="H1 + H2 + lead-lag for a date range -> reports/")
    b.add_argument("--start", required=True)
    b.add_argument("--end", required=True)
    b.set_defaults(fn=cmd_backtest)

    h3 = sub.add_parser("h3-kaggle", help="H3, the registered test on the Kaggle MGM closing splits: NBA "
                                          "(docs/H3_KAGGLE_PREREGISTRATION.md) or NFL "
                                          "(docs/H3_KAGGLE_NFL_PREREGISTRATION.md); needs a Kaggle token in "
                                          "KAGGLE_API_TOKEN or ~/.kaggle/access_token, or KAGGLE_USERNAME and "
                                          "KAGGLE_KEY in .env, unless the file is already in the cache")
    h3.add_argument("--sport", dest="h3_sport", choices=["nba", "nfl"], default=None,
                    help="nba (the default) or nfl; the same as markets --sport before the command")
    h3.add_argument("--nfl-dir", help="NFL: the nfl-weather project, read-only (its games.parquet scores and the "
                                      "Rule B replay table); default ../nfl-weather")
    h3.add_argument("--check-only", action="store_true",
                    help="NFL: check the file's columns, team names, join to the schedule and the format of its "
                         "lines, shares and prices (counts only); read no score or won flag; compute no result")
    h3.set_defaults(fn=cmd_h3)

    h = sub.add_parser("h4a-nfl-weather", help="H4a: Kalshi NFL totals vs wind (zero Odds API credits)")
    h.add_argument("--nfl-dir", required=True, help="path to the nfl-weather study project (read-only)")
    h.add_argument("--season", type=int, default=2025)
    h.set_defaults(fn=cmd_h4a, sport="nfl")

    col = sub.add_parser("collect", help="one forward-collector tick (PLAN.md section 7; launchd runs it every minute)")
    col.add_argument("--now", help="pretend it's this UTC time (testing: a dry run in a scratch dir, no credits)")
    col.set_defaults(fn=cmd_collect)

    w = sub.add_parser("weather", help="venue and weather joins for MLB and soccer (docs/HEAT_HYPOTHESES.md)")
    w.add_argument("stage", choices=["check", "venues", "plan", "fetch", "join", "qualifying"])
    w.add_argument("--sports", default=None, help="only these Odds API sport keys, comma-separated")
    w.add_argument("--confirm", action="store_true", help="venues/fetch: actually call the free APIs")
    w.add_argument("--max-calls", type=int, default=9000,
                   help="fetch: weighted Open-Meteo calls this run, as Open-Meteo counts them (a 31-day request is 3; "
                        "free tier: 10,000 a day)")
    w.add_argument("--leagues-too", action="store_true", help="venues: ESPN match venues for the leagues too")
    w.set_defaults(fn=cmd_weather)

    f = sub.add_parser("odds5m", help="5M-credit month: bulk historical Odds API pulls (docs/ODDS5M_DAY_ONE.md)")
    f.add_argument("stage", choices=["probe", "balance", "plan", "week", "full", "check", "headers"],
                   help="balance: the free key check alone (with --confirm), to read the credits left after a stop; "
                   "headers: free and offline, how the balance header behaved in a pull's latest run (--pull, default "
                   "P0) and the --alarm-margin it advises")
    f.add_argument("--pull", default="all", help="pull IDs or groups (day_one, gated, march) from config/odds5m.yaml, "
                   "comma-separated; `all` works for plan, week and check but not for full")
    f.add_argument("--sports", default=None, help="only these Odds API sport keys, comma-separated")
    f.add_argument("--seasons", default=None, help="only these season labels from config/odds5m.yaml, comma-separated "
                   "(e.g. 2025 for the first F3 slice); `full` needs exactly one slice of a pull with require_seasons "
                   "(F3) and refuses --seasons for any other pull")
    f.add_argument("--week-of", default="auto", help="week stage: YYYY-MM-DD, or auto (first week of the latest unsealed season)")
    f.add_argument("--confirm", action="store_true", help="actually spend credits")
    f.add_argument("--max-credits", type=int, default=0, help="credit budget for this run")
    f.add_argument("--floor", type=int, default=531_630,
                   help="stop when the account would drop below this (the reserve: 300K + X3's 231,630)")
    f.add_argument("--rate", type=float, default=8.0, help="requests per second (the API allows 30)")
    f.add_argument("--retry-404", action="store_true", help="week and full: ask the pull's cached 404s (nothing there "
                   "at that time) again, under the same budget and floor; a 404 is replaced only by a 200")
    f.add_argument("--alarm-margin", type=_margin, default=None, help="probe, week and full: " + ALARM_HELP)
    f.add_argument("--per-call", type=int, default=30, help="headers: the most a call of the next pull costs, for the "
                   "margin it advises (30 for F1, 60 for F3)")
    f.set_defaults(fn=cmd_odds5m)

    pe = sub.add_parser("price-engine", help="price-engine backtest on F1, issues #8 and #53 "
                        "(docs/PRICE_ENGINE_PREREGISTRATION.md); no API calls")
    pe.add_argument("--fixture", action="store_true", help="run on a synthetic fixture instead (nothing in it is data)")
    pe.add_argument("--out", default=None, help="output folder (default reports/price_engine; a scratch folder with "
                    "--fixture)")
    pe.add_argument("--handoff", metavar="BUNDLE", default=None,
                    help="read F1 as pulled by the football archive bundle (its frozen folder, e.g. strategy-research/"
                    "football_archive/acquisition/football-archive-v4) instead of planning legacy F1; issue #101, "
                    "amendment 2 (DRAFT). Reading it runs the folder's code, so every file is first checked against "
                    "its FREEZE.json and --handoff-root, and any difference refuses the run")
    pe.add_argument("--handoff-root", metavar="SHA256", default=None,
                    help="with --handoff (required): the bundle's frozen root, as the hub approved it")
    pe.add_argument("--handoff-runtime", metavar="DIR", default=None,
                    help="with --handoff: the bundle executor's runtime folder (its spending ledger, receipts, "
                    "coverage report and data/raw); default the executor's fixed runtime, ~/Library/Application "
                    "Support/ValueFinder/football-acquisition-state/<--handoff-root>")
    pe.set_defaults(fn=cmd_price_engine)

    pg = sub.add_parser("props-grade", help="the registered props test on F3, issue #10 "
                        "(nfl-weather/PREREGISTRATION_PROPS.md); no API calls. Without --book-recorded it stops "
                        "after the book's coverage, before any outcome is read")
    pg.add_argument("--book-recorded", choices=["pinnacle", "draftkings"], default=None,
                    help="the book recorded in the registration's section 8 note; must be the one the rule picks")
    pg.add_argument("--list-excluded", action="store_true", help="also list every excluded line, with its reason")
    pg.add_argument("--fixture", action="store_true", help="run on a synthetic fixture instead (nothing in it is data)")
    pg.add_argument("--out", default=None, help="output folder (default reports/props_grade; a scratch folder with "
                    "--fixture)")
    pg.add_argument("--archive-runtime", type=Path, default=None,
                    help="receipt-bound F3a 2025 coverage only; grading blocked pending timing amendment")
    pg.set_defaults(fn=cmd_props_grade)

    args = p.parse_args(argv)
    try:
        return args.fn(args) or 0       # the exit status: 1 when a paid run stopped (odds5m, odds-pull)
    except KeyboardInterrupt:           # Ctrl-C outside a paid run's own handler: a plain line, never a traceback
        print("STOPPED: interrupted (Ctrl-C)", flush=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
