"""Odds API free-tier guard. Copied to cfb-weather (cfbweather/quota.py); keep the two in sync.

Both weather projects share one key and one monthly quota (500 credits on the
free plan, reset on the 1st). The last quota the API reported is kept in one
file outside the repo, ~/.cache/value-finder/odds_quota.json, so each project
sees what the other spent.

* Scheduled alert runs (launchd sets XPC_SERVICE_NAME to the job label) call the
  API until the quota is gone; an exhausted quota just means no price that run.
* Manual runs skip the API when fewer than MANUAL_FLOOR credits remain, so the
  alerts keep their budget for the rest of the month.
* Background loggers (the trigger poller, the props log and the other live uses; their
  launchd jobs set ODDS_QUOTA_KIND=background) run only on a paid plan, and stop when
  fewer than background_floor() credits remain, so the alerts and close capture always
  have credits left. On the free plan they never call the API.

Paid-tier setting: the plan size is read from the last response (used + remaining), so a
paid key switches the tier by itself. ODDS_API_TIER=free|paid overrides that, and
ODDS_BACKGROUND_FLOOR overrides the background floor. Alert, close-capture and manual
runs behave exactly as before on every plan.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pandas as pd

STATE = Path(os.environ.get("ODDS_QUOTA_FILE", Path.home() / ".cache" / "value-finder" / "odds_quota.json"))
MANUAL_FLOOR = 60
FREE_PLAN = 500
BACKGROUND_MIN_FLOOR = 2_000      # background loggers leave at least this many credits,
BACKGROUND_SHARE = 0.02           # or 2% of the plan if that is more (100K on the 5M plan)


def scheduled() -> bool:
    return os.environ.get("XPC_SERVICE_NAME", "").endswith(".alerts")


def read() -> dict | None:
    """The last reported quota, or None when unknown or from an earlier month (it has reset since)."""
    try:
        s = json.loads(STATE.read_text())
    except (OSError, ValueError):
        return None
    now = pd.Timestamp.now(tz="UTC")
    seen = pd.Timestamp(s.get("utc", "1970-01-01"), tz="UTC") if "utc" in s else None
    if seen is None or (seen.year, seen.month) != (now.year, now.month):
        return None
    return s


def background() -> bool:
    return os.environ.get("ODDS_QUOTA_KIND", "").strip().lower() == "background"


def plan_size(s: dict | None = None) -> int | None:
    """Credits in the current plan (used + remaining, from the last response), or None when unknown."""
    s = read() if s is None else s
    if not s or s.get("remaining") is None or s.get("used") is None:
        return None
    return s["remaining"] + s["used"]


def tier(s: dict | None = None) -> str:
    """"paid" or "free". ODDS_API_TIER wins; otherwise a plan bigger than the free 500 credits is paid."""
    forced = os.environ.get("ODDS_API_TIER", "").strip().lower()
    if forced in ("free", "paid"):
        return forced
    size = plan_size(s)
    return "paid" if size is not None and size > FREE_PLAN else "free"


def background_floor(s: dict | None = None) -> int:
    forced = os.environ.get("ODDS_BACKGROUND_FLOOR", "").strip()
    if forced.isdigit():
        return int(forced)
    return max(BACKGROUND_MIN_FLOOR, int(BACKGROUND_SHARE * (plan_size(s) or 0)))


def check() -> str | None:
    """Why this run must not call the API, or None when it may."""
    s = read()
    if background():
        if tier(s) != "paid":
            return "background Odds API loggers run only on a paid plan (ODDS_API_TIER=paid overrides)"
        floor = background_floor(s)
        if s and s.get("remaining") is not None and s["remaining"] < floor:
            return f"Odds API quota low: {s['remaining']} credits left this month, below the background floor {floor}"
        return None
    if not s or s.get("remaining") is None:
        return None
    floor = 1 if scheduled() else MANUAL_FLOOR
    if s["remaining"] < floor:
        who = "scheduled run" if scheduled() else f"manual run (floor {MANUAL_FLOOR})"
        return f"Odds API quota low: {s['remaining']} credits left this month, skipping for this {who}"
    return None


def record(response, project: str) -> dict:
    """Store the quota headers from any Odds API response and return them."""
    h = response.headers

    def num(name):
        v = h.get(name)
        try:
            return int(float(v)) if v is not None else None
        except ValueError:
            return None

    s = dict(utc=pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%dT%H:%M:%SZ"), project=project,
             status=response.status_code, last=num("x-requests-last"), used=num("x-requests-used"),
             remaining=num("x-requests-remaining"))
    if s["remaining"] is None and s["used"] is None:
        return s                    # no quota headers (a network-level error page): keep the last known quota
    try:
        STATE.parent.mkdir(parents=True, exist_ok=True)
        STATE.write_text(json.dumps(s))
    except OSError:
        pass
    return s
