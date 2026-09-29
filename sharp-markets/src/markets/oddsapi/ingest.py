"""Plan and pull historical sharp-book snapshots for a set of games (cache-first, budgeted)."""
from __future__ import annotations

import logging
from collections import Counter

import requests

from ..context import Context
from ..games import Game
from ..http import scrub
from .client import BudgetExceeded, OddsApiClient, OddsApiError
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


def pull_snapshots(ctx: Context, plan: dict, max_credits: int, client: OddsApiClient | None = None) -> dict:
    """Fetch the plan's uncached snapshots. A budget stop, a billing that can't be read, an error status or a network
    failure ends the pull with `stopped` set (the reason, key blanked), never a traceback."""
    if plan["est_credits"] > max_credits:
        raise BudgetExceeded(f"plan needs {plan['est_credits']} credits > --max-credits {max_credits}; nothing fetched")
    client = client or OddsApiClient(ctx.sport, ctx.cache, max_credits=max_credits)
    start, stopped = client.cache.http_requests, None
    for i, t in enumerate(plan["todo"], 1):
        try:
            client.historical_odds(sport_key=ctx.cfg.odds_sport_key, at=t, bookmakers=ctx.cfg.bookmakers,
                                   markets=ctx.cfg.odds_markets)
        except (BudgetExceeded, OddsApiError, requests.RequestException) as e:
            stopped = f"{type(e).__name__}: {scrub(e)}"
            break
        if i % 50 == 0 or i == len(plan["todo"]):
            log.info("odds snapshots %d/%d, credits spent %d, remaining %s", i, len(plan["todo"]),
                     client.credits_spent, client.remaining)
    return {"fetched": client.cache.http_requests - start, "credits_spent": client.credits_spent,
            "remaining": client.remaining, "stopped": stopped}
