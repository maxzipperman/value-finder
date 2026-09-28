"""Odds API free-tier guard. Copied from nfl-weather (nflweather/quota.py); keep the two in sync.

Both weather projects share one key and one monthly quota (500 credits on the
free plan, reset on the 1st). The last quota the API reported is kept in one
file outside the repo, ~/.cache/value-finder/odds_quota.json, so each project
sees what the other spent.

* Scheduled alert runs (launchd sets XPC_SERVICE_NAME to the job label) call the
  API until the quota is gone; an exhausted quota just means no price that run.
* Manual runs skip the API when fewer than MANUAL_FLOOR credits remain, so the
  alerts keep their budget for the rest of the month.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pandas as pd

STATE = Path(os.environ.get("ODDS_QUOTA_FILE", Path.home() / ".cache" / "value-finder" / "odds_quota.json"))
MANUAL_FLOOR = 60


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


def check() -> str | None:
    """Why this run must not call the API, or None when it may."""
    s = read()
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
    try:
        STATE.parent.mkdir(parents=True, exist_ok=True)
        STATE.write_text(json.dumps(s))
    except OSError:
        pass
    return s
