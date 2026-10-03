"""Forward collector (docs/PLAN.md section 7): Kalshi top of book and sharp-book moneylines, live.
Paper-only and GET-only: it reads public Kalshi market data and Odds API prices, nothing else.

launchd runs one tick a minute (com.valuefinder.nbacollector, ops/install_live_uses.sh). A tick:
  1. takes a lockfile, so ticks never overlap;
  2. does nothing before `collector.start` in the sport config (2026-10-20 for the NBA opener);
  3. reads the schedule from the Odds API's free /events endpoint, refreshed hourly;
  4. acts every `every_min` minutes (every `final_every_min` inside the final `final_minutes` before a
     tip, when that is set) while any game is inside [tip - window_before_tip_hours, tip + window_after_tip_min]:
     - Kalshi: GET /events?series_ticker=...&status=open&with_nested_markets=true (public, free);
     - Odds API: live h2h at the sport's bookmakers (1 credit per call for up to 10 books);
  5. writes a heartbeat row to data/collector/{sport}/runs.csv on every acting or idle tick, with the
     gap since the last one, so sleep gaps are measured and logged, never hidden.

`markets collect --now T` (testing) is a dry run in a scratch directory: it never writes the live
state, heartbeat or cache, never spends an Odds API credit and never writes the shared quota file.
A last_tick in the future (a clock change, or state from an old --now run) counts as due.

Every response is stored before use, one parquet per source per tick (RawCache: temp file, then rename):
data/raw/{sport}/collector_kalshi/{date}/ and data/raw/{sport}/collector_oddsapi/{date}/. Each tick's
requests are keyed to its own time, so the cache looks only in that date's directory, never the whole
season's history.

Credits: a background logger under the weather projects' shared quota file
(~/.cache/value-finder/odds_quota.json). As in nfl-weather/nflweather/quota.py's background kind, it
runs only on a paid plan (plan size = used + remaining > 500, or ODDS_API_TIER=paid) and stops at the
background floor (max(2,000, 2% of the plan), or ODDS_BACKGROUND_FLOOR). It records every response's
quota headers to the same file, so the alerts see what it spent. Each record carries the key's
fingerprint (sha256, first 12 hex digits), and a record made with a different key is ignored, as in
quota.py, so the weather projects never read this key's plan as theirs (or the reverse).
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
import time
import sys
import fcntl
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import yaml

from .cache import Fetched, RawCache, body_json
from .http import RateLimiter, http_get, new_session, scrub
from .kalshi.client import KalshiClient, KalshiHTTPError
from .settings import CONFIG_DIR, DATA_DIR, env, parse_ts, utcnow

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from ops.collector_guard import paid_get, slot

ODDS_BASE = "https://api.the-odds-api.com/v4"
QUOTA_FILE = Path(os.environ.get("ODDS_QUOTA_FILE", Path.home() / ".cache" / "value-finder" / "odds_quota.json"))
FREE_PLAN, BACKGROUND_MIN_FLOOR, BACKGROUND_SHARE = 500, 2_000, 0.02
LOCK_STALE = timedelta(minutes=10)
SCHEDULE_TTL = timedelta(hours=1)
COLLECTOR_SOURCES = ("collector_kalshi", "collector_oddsapi")   # tick-keyed: looked up in the tick's date dir only
HEARTBEAT_FIELDS = ["tick_utc", "action", "games_in_window", "final_window", "kalshi_status", "kalshi_events",
                    "kalshi_markets", "odds_status", "odds_events", "credits_last", "remaining", "gap_min", "note"]


def load_collector_config(sport: str) -> dict:
    cfg = yaml.safe_load((CONFIG_DIR / "sports" / f"{sport}.yaml").read_text())
    c = dict(cfg.get("collector") or {})
    if not c:
        raise SystemExit(f"config/sports/{sport}.yaml has no collector: section")
    c["start"] = date.fromisoformat(str(c["start"]))
    c.update(sport=sport, series_ticker=cfg["kalshi"]["series_ticker"], sport_key=cfg["odds_api"]["sport_key"],
             bookmakers=list(cfg["odds_api"]["bookmakers"]), markets=cfg["odds_api"].get("markets", "h2h"))
    return c


# ---------------------------------------------------------------- the shared quota file
def fingerprint(key: str | None) -> str | None:
    """A key's identity in the shared file (as quota.fingerprint in the weather projects)."""
    return hashlib.sha256(key.encode()).hexdigest()[:12] if key else None


def quota_state(now: datetime, key: str | None = None) -> dict | None:
    """The last recorded quota this month, or None (unknown, an earlier month, or another key's record)."""
    try:
        s = json.loads(QUOTA_FILE.read_text())
    except (OSError, ValueError):
        return None
    mine = fingerprint(key)
    if s.get("key") and mine and s["key"] != mine:
        return None
    seen = parse_ts(s.get("utc"))
    return s if seen and (seen.year, seen.month) == (now.year, now.month) else None


def quota_block(now: datetime, key: str | None = None) -> str | None:
    """Why this background logger must not spend credits now, or None."""
    s = quota_state(now, key)
    size = s["remaining"] + s["used"] if s and s.get("remaining") is not None and s.get("used") is not None else None
    forced = os.environ.get("ODDS_API_TIER", "").strip().lower()
    paid = forced == "paid" or (forced != "free" and size is not None and size > FREE_PLAN)
    if not paid:
        return "background Odds API loggers run only on a paid plan (ODDS_API_TIER=paid overrides)"
    f = os.environ.get("ODDS_BACKGROUND_FLOOR", "").strip()
    floor = int(f) if f.isdigit() else max(BACKGROUND_MIN_FLOOR, int(BACKGROUND_SHARE * (size or 0)))
    if s and s.get("remaining") is not None and s["remaining"] < floor:
        return f"Odds API quota low: {s['remaining']} credits left, below the background floor {floor}"
    return None


def quota_record(status: int, headers: dict, now: datetime, key: str | None = None) -> None:
    def num(name):
        try:
            return int(float(headers[name])) if headers.get(name) is not None else None
        except ValueError:
            return None
    s = dict(utc=now.strftime("%Y-%m-%dT%H:%M:%SZ"), project="sharp-markets", status=status,
             last=num("x-requests-last"), used=num("x-requests-used"), remaining=num("x-requests-remaining"),
             key=fingerprint(key))
    if s["remaining"] is None and s["used"] is None:
        return                      # no quota headers: keep the last known quota
    try:
        QUOTA_FILE.parent.mkdir(parents=True, exist_ok=True)
        QUOTA_FILE.write_text(json.dumps(s))
    except OSError:
        pass


# ---------------------------------------------------------------- tick
class Collector:
    def __init__(self, sport: str = "nba", *, cfg: dict | None = None, data_dir: Path = DATA_DIR,
                 odds_session=None, kalshi_session=None, api_key: str | None = None, dry_run: bool = False):
        self.c = cfg or load_collector_config(sport)
        self.sport = self.c["sport"]
        self.dir = Path(data_dir) / "collector" / self.sport
        self.cache = RawCache(Path(data_dir) / "raw", dated_sources=frozenset(COLLECTOR_SOURCES))
        self.odds = odds_session or new_session()
        self.limiter = RateLimiter(5)
        self.kalshi = KalshiClient(self.sport, self.cache)
        if kalshi_session is not None:
            self.kalshi.session = kalshi_session
        self.api_key = api_key
        self.dry_run = dry_run              # no paid Odds API call and no shared-quota write (--now)

    # -- odds api
    @property
    def key(self) -> str:
        return self.api_key or env("ODDS_API_KEY")

    def _odds_get(self, path: str, params: dict, *, request_slot=None):
        keyed = {**params, "apiKey": self.key}
        if path.endswith("/odds"):
            r = paid_get(self.odds, ODDS_BASE + path, keyed, label="nba", request_slot=request_slot)
        else:
            r = http_get(self.odds, ODDS_BASE + path, keyed, self.limiter, max_retries=0, allow_redirects=False)
        return r.status_code, {k.lower(): v for k, v in r.headers.items()}, r.text

    def schedule(self, now: datetime) -> list[dict]:
        """Upcoming games from the free /events endpoint, cached for SCHEDULE_TTL."""
        path = self.dir / "schedule.json"
        if path.exists():
            s = json.loads(path.read_text())
            if now - parse_ts(s["fetched_utc"]) < SCHEDULE_TTL:
                return s["events"]
        status, headers, text = self._odds_get(f"/sports/{self.c['sport_key']}/events", {"dateFormat": "iso"})
        if status != 200:
            raise RuntimeError(f"Odds API /events -> HTTP {status}: {scrub(text)[:200]}")   # the body may echo the key
        if not self.dry_run:
            quota_record(status, headers, now, self.key)
        events = json.loads(text)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"fetched_utc": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "events": events}))
        return events

    def windows(self, events: list[dict], now: datetime) -> tuple[int, bool]:
        before = timedelta(hours=self.c["window_before_tip_hours"])
        after = timedelta(minutes=self.c["window_after_tip_min"])
        final = timedelta(minutes=self.c.get("final_minutes", 120))
        tips = [parse_ts(e["commence_time"]) for e in events]
        inside = [t for t in tips if t - before <= now <= t + after]
        return len(inside), any(t - final <= now <= t + after for t in inside)

    def fetch_odds(self, tick: str, now: datetime, *, step=None) -> dict:
        if self.dry_run:
            return {"odds_status": "skipped", "note": "dry run (--now): no Odds API call"}
        if (why := quota_block(now, self.key)):
            return {"odds_status": "skipped", "note": why}
        params = {"bookmakers": ",".join(self.c["bookmakers"]), "markets": self.c["markets"],
                  "oddsFormat": "decimal", "dateFormat": "iso"}
        sent = {}

        def fetch() -> Fetched:
            status, headers, text = self._odds_get(f"/sports/{self.c['sport_key']}/odds", params,
                                                   request_slot=slot(now, 60 * (step or self.c["every_min"])))
            sent.update(status=status, headers=headers)
            return Fetched(status, headers, text)

        rec = self.cache.get_or_fetch(sport=self.sport, source="collector_oddsapi", data_date=tick[:10],
                                      url=f"{ODDS_BASE}/sports/{self.c['sport_key']}/odds", params=params,
                                      fetch=fetch, key_extra={"tick": tick}, cache_statuses=(200,))
        if sent:
            quota_record(sent["status"], sent["headers"], now, self.key)
        h = json.loads(rec["headers_json"] or "{}")
        body = body_json(rec) if rec["http_status"] == 200 else None
        return {"odds_status": rec["http_status"], "odds_events": len(body or []),
                "credits_last": h.get("x-requests-last"), "remaining": h.get("x-requests-remaining")}

    def fetch_kalshi(self, tick: str) -> dict:
        try:
            events = self.kalshi._paginate("/events", "events", {"series_ticker": self.c["series_ticker"],
                                                                 "status": "open", "with_nested_markets": "true",
                                                                 "limit": 200},
                                           source="collector_kalshi", data_date=tick[:10], key_extra={"tick": tick})
        except KalshiHTTPError as e:
            return {"kalshi_status": e.status}
        return {"kalshi_status": 200, "kalshi_events": len(events),
                "kalshi_markets": sum(len(e.get("markets") or []) for e in events)}

    # -- state, lock, heartbeat
    def _state(self) -> dict:
        p = self.dir / "state.json"
        return json.loads(p.read_text()) if p.exists() else {}

    def _heartbeat(self, row: dict, state: dict, now: datetime) -> dict:
        last = parse_ts(state.get("last_tick"))
        row = {"tick_utc": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
               "gap_min": round((now - last).total_seconds() / 60, 1) if last else "", **row}
        p = self.dir / "runs.csv"
        new = not p.exists()
        with p.open("a", newline="") as f:
            w = csv.DictWriter(f, HEARTBEAT_FIELDS)
            if new:
                w.writeheader()
            w.writerow({k: row.get(k, "") for k in HEARTBEAT_FIELDS})
        (self.dir / "state.json").write_text(json.dumps({**state, "last_tick": row["tick_utc"]}))
        return row

    def tick(self, now: datetime | None = None) -> dict | None:
        """One launchd run. Returns the heartbeat row, or None when it did nothing (not due, locked, too early)."""
        now = (now or utcnow()).astimezone(timezone.utc).replace(microsecond=0)
        if now.date() < self.c["start"]:
            return None
        self.dir.mkdir(parents=True, exist_ok=True)
        lock = self.dir / "tick.lock"
        lock_handle = lock.open("a+")
        try:
            fcntl.flock(lock_handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            lock_handle.close()
            return None
        try:
            state = self._state()
            try:
                n, final = self.windows(self.schedule(now), now)
            except Exception as e:          # noqa: BLE001 - a failed schedule read is logged, never fatal
                return self._heartbeat({"action": "error", "note": scrub(f"schedule: {e}")[:300]}, state, now)
            step = self.c.get("final_every_min") if (final and self.c.get("final_every_min")) else self.c["every_min"]
            last = parse_ts(state.get("last_tick"))
            if last and last <= now and now - last < timedelta(minutes=step) - timedelta(seconds=30):
                return None                 # not due; a last_tick in the future counts as due
            if n == 0:
                return self._heartbeat({"action": "idle", "games_in_window": 0}, state, now)
            tick = now.strftime("%Y-%m-%dT%H:%M:%SZ")
            row = {"action": "collected", "games_in_window": n, "final_window": final}
            for name, part in (("kalshi", lambda: self.fetch_kalshi(tick)), ("odds", lambda: self.fetch_odds(tick, now, step=step))):
                try:
                    row.update(part())
                except Exception as e:      # noqa: BLE001 - one source failing must not lose the other
                    row.update({f"{name}_status": "error", "note": scrub(f"{name}: {type(e).__name__}: {e}")[:300]})
            return self._heartbeat(row, state, now)
        finally:
            lock_handle.close()  # Keep inode: unlinking a held lock permits overlapping owners.
