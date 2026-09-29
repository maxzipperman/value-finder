"""Plan and pull historical sharp-book snapshots for a set of games (cache-first, budgeted)."""
from __future__ import annotations

import logging
from collections import Counter

from ..context import Context
from ..games import Game
from ..http import scrub
from .bulk import DISK_HELP, Stop, run_calls
from .client import OddsApiClient
from .schedule import credits_per_snapshot, describe, plan_snapshots, tier_label

log = logging.getLogger(__name__)


def snapshot_plan(ctx: Context, games: list[Game], schedule: str) -> dict:
    times = plan_snapshots([(g.kalshi_est_tip, g.open_time) for g in games], schedule)
    client = OddsApiClient(ctx.sport, ctx.cache, max_credits=0)
    books = ctx.cfg.bookmakers
    cached = {t for t in times if client.is_cached_historical(sport_key=ctx.cfg.odds_sport_key, at=t, bookmakers=books)}
    per = credits_per_snapshot(len(ctx.cfg.odds_markets.split(",")), len(books))
    # tier mix: label each snapshot by the densest tier it serves for any game
    order = {"5m": 0, "15m": 1, "30m": 2, "60m": 3, "outside": 9}
    tiers = Counter()
    for t in times:
        labels = [tier_label(t, g.kalshi_est_tip, schedule) for g in games]
        tiers[min(labels, key=lambda x: order.get(x, 9))] += 1
    return {"times": times, "todo": [t for t in times if t not in cached], "cached": len(cached),
            "credits_per_snapshot": per, "est_credits": per * (len(times) - len(cached)),
            "tiers": dict(tiers), "summary": describe(times), "bookmakers": books}


def _refused(why: str) -> dict:
    why = scrub(why)                     # the reason can quote a header the key check got back
    print(f"STOPPED before the first paid call, nothing spent: {why}", flush=True)
    return {"fetched": 0, "credits_spent": 0, "remaining": None, "stopped": why}


def pull_snapshots(ctx: Context, plan: dict, max_credits: int, client: OddsApiClient | None = None, *,
                   floor: int = 0) -> dict:
    """Fetch the plan's uncached snapshots through the bulk puller's client and run loop (bulk.run_calls), so it
    has the same protections as `markets odds5m`: the free key check first, the run budget and the floor before
    every call and retry, fail-closed billing, a STOPPED line and a summary on every stop (Ctrl-C included), never
    a traceback, and a manifest row per paid request (pull N0). `stopped` is the reason, key blanked, or None."""
    if plan["est_credits"] > max_credits:
        return _refused(f"the plan needs {plan['est_credits']:,} credits, more than --max-credits {max_credits:,}")
    client = client or OddsApiClient(ctx.sport, ctx.cache, max_credits=max_credits, floor=floor)
    calls = [client.call_for(sport_key=ctx.cfg.odds_sport_key, at=t, bookmakers=ctx.cfg.bookmakers,
                             markets=ctx.cfg.odds_markets) for t in plan["todo"]]
    if any(not client.is_cached(c) for c in calls):
        try:
            info = client.account()
        except Stop as e:
            return _refused(str(e))
        except OSError as e:
            return _refused(f"a file could not be read or written ({e.strerror or e}): is the disk full? {DISK_HELP}")
        print(f"key ok: HTTP {info['status']}, {info['remaining']:,} credits remaining, {info['used']} used; "
              f"floor {client.floor:,}", flush=True)
    res = run_calls(client, calls, f"{client.sport} odds-pull (N0)")
    return {"fetched": res["fetched"], "credits_spent": res["spent"], "remaining": res["remaining"],
            "stopped": res["stopped"]}
