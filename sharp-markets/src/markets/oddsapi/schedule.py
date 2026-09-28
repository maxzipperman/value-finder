"""Historical snapshot scheduling. One snapshot covers every game of the sport, so windows are unioned.

Schedule tiers are (step_min, lo, hi): snapshots every `step_min` on the wall-clock grid inside
[tip - hi, tip - lo] minutes, where hi=None means "from market open" (capped at FAR_CAP_MIN).
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

GRID_SEC = 300                 # The Odds API historical snapshots are 5 minutes apart (since Sep 2022)
FAR_CAP_MIN = 96 * 60          # never schedule earlier than 96h before tip

SCHEDULES: dict[str, list[tuple[int, int, int | None]]] = {
    # A (approved for the sample week): dense in the final 2h, medium 2-6h, hourly before that.
    "A": [(5, -15, 120), (15, 120, 360), (60, 360, None)],
    "B": [(5, -15, 120), (60, 120, None)],
    "C": [(5, -15, 360), (30, 360, None)],
    "D": [(5, -15, None)],
}


def plan_snapshots(games: list[tuple[datetime, datetime]], schedule: str = "A") -> list[datetime]:
    """games: (est_tip, market_open) pairs. Returns sorted unique UTC request times on the 5-min grid."""
    tiers = SCHEDULES[schedule]
    out: set[int] = set()
    for tip, opened in games:
        tip_s = int(tip.timestamp())
        open_s = max(int(opened.timestamp()), tip_s - FAR_CAP_MIN * 60)
        for step_min, lo, hi in tiers:
            start = open_s if hi is None else max(open_s, tip_s - hi * 60)
            end = tip_s - lo * 60
            step = step_min * 60
            t = -(-start // step) * step            # first wall-clock multiple of step >= start
            while t <= end:
                out.add(t // GRID_SEC * GRID_SEC)
                t += step
    return [datetime.fromtimestamp(t, tz=timezone.utc) for t in sorted(out)]


def credits_per_snapshot(n_markets: int, n_bookmakers: int) -> int:
    """Historical odds cost 10 x markets x regions; every 10 bookmakers count as one region."""
    return 10 * n_markets * max(1, math.ceil(n_bookmakers / 10))


def describe(times: list[datetime]) -> str:
    if not times:
        return "no snapshots"
    days = {t.date() for t in times}
    return f"{len(times)} snapshots across {len(days)} UTC days, {times[0]:%Y-%m-%d %H:%M} -> {times[-1]:%Y-%m-%d %H:%M} UTC"


def tier_label(ts: datetime, tip: datetime, schedule: str = "A") -> str:
    mins = (tip - ts) / timedelta(minutes=1)
    for step_min, lo, hi in SCHEDULES[schedule]:
        if lo <= mins <= (hi if hi is not None else math.inf):
            return f"{step_min}m"
    return "outside"
