"""Health, as the menu-bar light reads it (GET /api/summary).

fail: the latest run of either alert job is recorded failed; or the last exit status of any of the four
      scheduled jobs is not 0; or an alert job has not recorded a run for more than 5 hours, counting only
      the hours between 7:30 AM and 11:30 PM local (so a quiet night is not an outage).
warn: otherwise, a ledger's newest row is more than 5 such hours old; or the credit balance is below 50
      on the free plan (a balance under 1,000 is taken to be the free plan); or a file the dashboard
      expects can't be read.
ok:   none of that.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, tzinfo

from . import words

STALE_HOURS = 5.0
FREE_PLAN_BELOW = 1_000
LOW_CREDITS = 50
ALERT_JOBS = {"nfl-weather": ("com.nflweather.alerts", "NFL alerts"),
              "cfb-weather": ("com.cfbweather.alerts", "college football alerts")}
JOB_NAMES = {"com.nflweather.alerts": "NFL alerts", "com.cfbweather.alerts": "college football alerts",
             "com.valuefinder.closecapture": "close capture", "com.valuefinder.ledgersync": "nightly ledger copy"}


@dataclass
class Health:
    level: str = "ok"
    problems: list[str] = field(default_factory=list)        # plain sentences, worst first
    fails: list[str] = field(default_factory=list)
    warns: list[str] = field(default_factory=list)

    def fail(self, s: str):
        if s not in self.fails:
            self.fails.append(s)

    def warn(self, s: str):
        if s not in self.warns:
            self.warns.append(s)

    def done(self) -> "Health":
        self.problems = self.fails + self.warns
        self.level = "fail" if self.fails else "warn" if self.warns else "ok"
        return self


def last_run(runs_rows: list[dict]) -> tuple[datetime | None, dict | None]:
    """The newest run in runs.csv, by its time."""
    best, best_t = None, None
    for r in runs_rows or []:
        t = words.parse_utc(r.get("run_utc", ""))
        if t is not None and (best_t is None or t >= best_t):
            best, best_t = r, t
    return best_t, best


def step_of(error: str) -> str:
    """The step a failed run names, e.g. "while building the board"."""
    e = words.scrub(error or "").strip()
    if not e:
        return "no reason was recorded"
    head = e.split(":", 1)[0].strip()
    return head if head.startswith("while ") and len(head) < 60 else (e[:120] + ("…" if len(e) > 120 else ""))


def assess(snap, now: datetime, tz: tzinfo) -> Health:
    """`snap` is a data.Snap. Pure: reads nothing, starts nothing."""
    h = Health()
    stale_run = set()
    # --- the alert jobs' run records
    for project, (_label, name) in ALERT_JOBS.items():
        runs = snap.runs.get(project)
        rows = runs.data[1] if runs is not None and runs.data else []
        t, row = last_run(rows)
        if t is None:
            continue                                   # an unreadable runs.csv is a warning, below
        if (row.get("status") or "").strip().lower() == "failed":
            h.fail(f"The last {name} run, at {words.when(t, tz, now)}, failed ({step_of(row.get('error', ''))}).")
        hours = words.working_hours_between(t, now, tz)
        if hours > STALE_HOURS:
            stale_run.add(project)
            h.fail(f"The {name} have not recorded a run since {words.when(t, tz, now)}: more than 5 hours of the "
                   "7:30 AM to 11:30 PM day.")
    # --- launchd's last exit status for the four jobs
    lc = snap.launchctl
    if lc.listed is not None:
        for label, name in JOB_NAMES.items():
            entry = lc.listed.get(label)
            if entry is None:
                h.warn(f"The {name} job is not loaded in launchd, so it will not run until it is installed again.")
                continue
            status = entry.get("status")
            if isinstance(status, int) and status != 0:
                h.fail(f"The {name} job last ended with an error (exit status {status}).")
    # --- ledgers going stale
    for ledger in snap.ledgers.values():
        project = ledger.path.parent.parent.parent.name
        if not ledger.readable or project in stale_run:
            continue
        t = words.parse_utc(ledger.latest_snapshot)
        if t is not None and words.working_hours_between(t, now, tz) > STALE_HOURS:
            h.warn(f"The newest row in the {ledger.name} ledger is from {words.when(t, tz, now)}: more than 5 hours "
                   "of the 7:30 AM to 11:30 PM day ago.")
    # --- credits
    q = snap.quota
    remaining = q.get("remaining") if isinstance(q, dict) else None
    if isinstance(remaining, int) and remaining < FREE_PLAN_BELOW and remaining < LOW_CREDITS:
        seen = words.parse_utc(q.get("utc", ""))
        if seen is None or (seen.year, seen.month) == (now.year, now.month):
            h.warn(f"Only {remaining} Odds API credits are left this month (free plan).")
    # --- files the dashboard expects
    for sentence in snap.unreadable:
        h.warn(sentence)
    return h.done()
