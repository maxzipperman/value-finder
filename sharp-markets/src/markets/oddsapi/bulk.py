"""Bulk historical Odds API puller for the 5M-credit month. GET only. Config: config/odds5m.yaml.

Stages (`uv run markets odds5m <stage>`; the hub runs them on the Mac, docs/ODDS5M_DAY_ONE.md):
  probe    P0: the free key check, historical /events sweeps for every sport (1 credit each, 0 when empty) into
           exact schedules, then seven single-call billing and coverage probes
  balance  free: the key check alone, to read the credits left (after a stop, before a rerun)
  plan     free: calls and upper-bound credits per pull from those schedules, cached vs to fetch
  week     one week per sport for the chosen pulls, to check coverage before the full spend
  full     the chosen pulls in full, named or by config group (day_one, gated, march); never `all`
  check    free: what the cache holds for a pull (books, markets, snapshot lag, empty snapshots, cached 404s)
  headers  free and offline: how the balance header behaved in a pull's latest run (markets.oddsapi.headers)

A `games_from:` pull (HB1, HS1) fetches only the games in the CSV that `markets weather qualifying` writes from the
pre-registered triggers; until it exists `plan` counts the pull as 0 calls. A `require_seasons:` pull (F3) is bought
one declared slice at a time: `full` and `week` refuse it, dry run included, unless --seasons names exactly one
slice, and `full` refuses --seasons for every other pull (they are bought whole).

Safety. Nothing is fetched without --confirm, and a run starts only when the free key check returns a readable
balance at or above --floor. BulkClient's docstring has the accounting: what counts toward --max-credits, the floor,
and the one alarm. Billing headers fail closed. Every stop, Ctrl-C included, ends the run with a STOPPED line and its
summary, never a traceback, `markets` exits with status 1 (0 only when done), and the stopped client refuses every
later attempt. The key never shows in error text, headers, STOPPED lines or log lines (markets.http.scrub), and every
body has exactly the key blanked before it is kept (markets.http.blank_key). Every answer, a retried 429 or 5xx
included, gets a row in data/raw/_manifest/oddsapi_manifest.csv: requested and returned snapshot time, credits billed
(blank when unreadable: the upper bound was counted), the balance reported, the SHA-256 of the body as stored, the
cache key and the sealed flag.

Cache first: answers land in data/raw/{sport_key}/oddsapi/{hist_events,hist_odds,hist_event_odds}/ before use, so
reruns resume for free. Errors other than 404 are never cached; a 404 is cached as "nothing there at that time",
counted on each pull's summary line (not the one after Ctrl-C), and asked again with --retry-404.

The probe saves a sport's schedule only when its sweeps finished, and never an empty one when some were answered 404
or over a saved file that has games; a sport refused (HTTP 4xx) five times in a row is skipped. After a stop it says
whether to rerun or to tell the hub first (Stop.rerun): a rerun after an alarm would buy more and hide the alarm.

Sealed holdout: sealed seasons are pulled, but load_rows() leaves them out unless include_sealed=True, which only a
pre-registered test may pass. plan_calls refuses a sealed call for a `cache_as` pull (N1), whose cache `markets build`
reads directly (and `markets build` leaves sealed games out on its own as well).
"""
from __future__ import annotations

import csv
import functools
import hashlib
import json
import logging
import math
import os
import statistics
import traceback
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import requests
import yaml

from ..cache import Fetched, RawCache, body_json, cache_key, read_record, read_status
from ..http import RateLimiter, blank_key, http_get, new_session, scrub
from ..settings import CONFIG_DIR, DATA_DIR, env, parse_ts, utcnow
from .normalize import outcome_rows

log = logging.getLogger(__name__)
BASE_URL = "https://api.the-odds-api.com/v4"
CONFIG = CONFIG_DIR / "odds5m.yaml"
SRC_EVENTS, SRC_ODDS, SRC_EVENT_ODDS = "oddsapi/hist_events", "oddsapi/hist_odds", "oddsapi/hist_event_odds"
FIVE = timedelta(minutes=5)
LOOKBACK = timedelta(days=7)
DAILY_HOUR = 16          # daily_close snapshots at 16:00 UTC (strategy-research/odds_budget.py grid(at=16))
SWEEP_HOUR = 6           # /events sweeps at 06:00 UTC, before the day's first kickoff in every league
SETTLED = timedelta(hours=3)     # only games that kicked off at least this long ago are pulled
UTC = timezone.utc
MANIFEST_FIELDS = ["logged_at", "pull", "sport", "source", "path", "event_id", "requested_ts", "returned_ts",
                   "previous_ts", "next_ts", "markets", "books", "n_events", "expected_credits", "credits_last",
                   "remaining", "http_status", "sha256", "cache_key", "sealed"]
DEFAULT_MARGIN, MIN_MARGIN = 5_000, 300      # the alarm's margin: the larger of 5,000 and 10% of --max-credits


class Stop(RuntimeError):
    """The run has to stop. `rerun` says what comes next: True, run the same command again (it buys only what is
    missing, after the free key check); False, the hub looks first, because a rerun could buy more of what the stop is
    about (billing above the upper bound, unreadable or untrusted, an unreadable balance, the alarm, the floor,
    repeated errors)."""
    rerun = False

    def __init__(self, message: str = "", *, rerun: bool | None = None):
        super().__init__(message)
        if rerun is not None:
            self.rerun = rerun


class BudgetExceeded(Stop):
    pass


class CircuitBreaker(Stop):
    pass


class TooManyErrors(CircuitBreaker):
    """max_errors error answers in a row; `status` is the last one's HTTP status."""

    def __init__(self, message: str, status: int):
        super().__init__(message)
        self.status = status


# ---------------------------------------------------------------- config and time helpers
def _d(v) -> date:
    return v if isinstance(v, date) else date.fromisoformat(str(v))


def load_config(path: Path = CONFIG) -> dict:
    cfg = yaml.safe_load(Path(path).read_text())
    for sc in cfg["sports"].values():
        sc["history_from"] = _d(sc["history_from"])
        for w in sc["windows"]:
            w.update({"label": str(w["label"]), "from": _d(w["from"]), "to": _d(w["to"]),
                      "sealed": bool(w.get("sealed", False))})
    for pid, p in cfg["pulls"].items():
        p["id"] = pid
        if "from" in p:
            p["from"] = _d(p["from"])
    return cfg


def window_for(cfg: dict, sport: str, when: datetime) -> dict | None:
    d = when.astimezone(UTC).date()
    return next((w for w in cfg["sports"][sport]["windows"] if w["from"] <= d <= w["to"]), None)


def is_sealed(cfg: dict, sport: str, when: datetime) -> bool:
    w = window_for(cfg, sport, when)
    return bool(w and w["sealed"])


def iso(t: datetime) -> str:
    return t.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def floor5(t: datetime) -> datetime:
    return t.replace(second=0, microsecond=0) - timedelta(minutes=t.minute % 5)


def _ceil(t: datetime, step: timedelta) -> datetime:
    s = int(step.total_seconds())
    return datetime.fromtimestamp(math.ceil(t.timestamp() / s) * s, tz=UTC)


def close_time(kick: datetime) -> datetime:
    """The last 5-minute grid point at least 5 minutes before kickoff: no in-play prices."""
    return floor5(kick - FIVE)


def game_snapshots(kick: datetime, pull: dict) -> list[datetime]:
    """Featured-snapshot request times one game needs under the pull's schedule (always incl. its close)."""
    close, sched = close_time(kick), pull["schedule"]
    if sched == "close":
        pts = []
    elif sched == "daily_close":
        first = datetime.combine((kick - LOOKBACK).date(), time(DAILY_HOUR), tzinfo=UTC)
        pts = [t for t in (first + timedelta(days=i) for i in range(9)) if kick - LOOKBACK <= t <= close]
    elif sched in ("hourly", "5min"):
        step = timedelta(hours=1) if sched == "hourly" else FIVE
        start = kick - (LOOKBACK if sched == "hourly" else timedelta(hours=pull.get("lookback_hours", 56)))
        end = close if sched == "hourly" else floor5(kick + timedelta(minutes=pull.get("after_minutes", 0)))
        t, pts = _ceil(start, step), []
        while t <= end:
            pts.append(t)
            t += step
    else:
        raise ValueError(f"unknown schedule {sched!r}")
    return sorted(set(pts) | {close})


def event_snapshots(kick: datetime, offsets: list[int]) -> list[datetime]:
    return sorted({close_time(kick) if h == 0 else floor5(kick - timedelta(hours=h)) for h in offsets})


def regions(books: list[str]) -> int:
    return max(1, math.ceil(len(books) / 10))


# ---------------------------------------------------------------- calls
@dataclass(frozen=True)
class Call:
    pull: str
    sport: str               # Odds API sport key
    source: str
    path: str
    params: tuple            # (key, value) pairs; apiKey is added only when sending
    at: datetime             # requested snapshot time
    expected: int            # upper-bound credits (10 x markets x regions; 1 for /events)
    sealed: bool
    event_id: str = ""
    cache_sport: str = ""    # where the response is cached (the sport key unless cache_as says otherwise)
    base: str = ""           # the API's base URL when it isn't this module's BASE_URL (odds-pull's client)

    @property
    def url(self) -> str:
        return (self.base or BASE_URL) + self.path

    @property
    def key(self) -> str:
        return cache_key(self.source, self.url, dict(self.params))


def _odds_params(books: list[str], markets: str, at: datetime) -> tuple:
    # the same params as OddsApiClient.historical_odds, so a cache_as pull shares that pipeline's cache
    return tuple(sorted({"bookmakers": ",".join(books), "markets": markets, "oddsFormat": "decimal",
                         "dateFormat": "iso", "date": iso(at)}.items()))


def sweep_calls(cfg: dict, sport: str, now: datetime | None = None) -> list[Call]:
    """Historical /events every sweep_every_days inside each season window (1 credit each, 0 if empty)."""
    now, sc, out = now or utcnow(), cfg["sports"][sport], []
    for w in sc["windows"]:
        d = max(w["from"], sc["history_from"])
        while d <= w["to"]:
            t = datetime.combine(d, time(SWEEP_HOUR), tzinfo=UTC)
            if t > now:
                break
            out.append(Call("P0", sport, SRC_EVENTS, f"/historical/sports/{sport}/events",
                            (("date", iso(t)), ("dateFormat", "iso")), t, 1, w["sealed"], cache_sport=sport))
            d += timedelta(days=sc["sweep_every_days"])
    return out


def build_schedule(cfg: dict, sport: str, bodies: list[dict]) -> list[dict]:
    """Unique games from /events sweeps. commence_time comes from the latest sighting taken before
    kickoff (kickoffs move); first_seen says how far ahead the game was listed."""
    seen: dict[str, dict] = {}
    for b in bodies:
        snap = parse_ts(b.get("timestamp"))
        for ev in b.get("data") or []:
            k = parse_ts(ev["commence_time"])
            rank = (snap is not None and snap <= k, snap or datetime.min.replace(tzinfo=UTC))
            cur = seen.get(ev["id"])
            if cur is None or rank >= cur["_rank"]:
                seen[ev["id"]] = cur = {"id": ev["id"], "sport": sport, "commence_time": k,
                                        "home_team": ev.get("home_team"), "away_team": ev.get("away_team"),
                                        "_rank": rank, "first_seen": cur["first_seen"] if cur else None}
            if snap and (cur["first_seen"] is None or snap < cur["first_seen"]):
                cur["first_seen"] = snap
    games = sorted(seen.values(), key=lambda g: (g["commence_time"], g["id"]))
    for g in games:
        del g["_rank"]
        _label(cfg, g)
    return games


def _label(cfg: dict, g: dict) -> dict:
    w = window_for(cfg, g["sport"], g["commence_time"])
    g["season"], g["sealed"] = (w["label"], w["sealed"]) if w else (None, False)
    return g


SCHEDULE_SCHEMA = pa.schema([("id", pa.string()), ("sport", pa.string()),
                             ("commence_time", pa.timestamp("us", tz="UTC")), ("home_team", pa.string()),
                             ("away_team", pa.string()), ("first_seen", pa.timestamp("us", tz="UTC"))])


def schedule_path(raw_dir: Path, sport: str) -> Path:
    return Path(raw_dir) / "_schedules" / f"{sport}.parquet"


def save_schedule(raw_dir: Path, sport: str, games: list[dict]) -> Path:
    """Written to a temporary file and then moved into place, so an interrupted write leaves the old file whole."""
    path = schedule_path(raw_dir, sport)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".parquet.tmp")
    pq.write_table(pa.Table.from_pylist([{f.name: g.get(f.name) for f in SCHEDULE_SCHEMA} for g in games],
                                        schema=SCHEDULE_SCHEMA), tmp)
    os.replace(tmp, path)
    return path


def load_schedules(cfg: dict, raw_dir: Path, sports=None) -> dict[str, list[dict]]:
    """Saved schedules, with season and sealed re-derived from the config (the config is the truth)."""
    out = {}
    for sport in sports or cfg["sports"]:
        path = schedule_path(raw_dir, sport)
        if path.exists():
            rows = pq.read_table(path).to_pylist()
            for g in rows:
                g["commence_time"] = g["commence_time"].astimezone(UTC)
            out[sport] = [_label(cfg, g) for g in rows]
    return out


def games_from_path(pull: dict) -> Path | None:
    """The CSV a `games_from:` pull reads (a relative path is under the data directory), or None."""
    if not pull.get("games_from"):
        return None
    path = Path(pull["games_from"])
    return path if path.is_absolute() else DATA_DIR / path


def waiting_for_games(pull: dict) -> Path | None:
    """The missing CSV a `games_from:` pull waits for (`markets weather qualifying` writes it), or None."""
    path = games_from_path(pull)
    return path if path is not None and not path.exists() else None


def games_from(pull: dict, sport: str) -> set[str] | None:
    """The event IDs a `games_from:` pull is limited to for one sport (None when the pull has no list).
    The CSV has `sport` and `id` columns; `markets weather qualifying` writes it. A relative path is
    under the data directory. A missing file stops the run: the trigger step has to come first."""
    path = games_from_path(pull)
    if path is None:
        return None
    if not path.exists():
        raise SystemExit(f"{pull['id']}: {path} is missing. Run `markets weather qualifying` first: it writes the "
                         "games whose day-1 forecast meets the pre-registered trigger (docs/HEAT_HYPOTHESES.md).")
    with path.open(newline="") as f:
        return {r["id"] for r in csv.DictReader(f) if r.get("sport") == sport}


def pull_games(cfg: dict, pull: dict, sport: str, games: list[dict], now: datetime, seasons=None) -> list[dict]:
    """The games a pull covers for one sport. `seasons` (the CLI's --seasons) narrows a run to those season
    labels, on top of the pull's own only_seasons/skip_seasons; it is how F3 is pulled one slice at a time."""
    lo = max(cfg["sports"][sport]["history_from"], pull.get("from", date.min))
    only = games_from(pull, sport)
    return [g for g in games
            if g["season"] is not None and g["commence_time"] <= now - SETTLED and g["commence_time"].date() >= lo
            and (not pull.get("only_seasons") or g["season"] in pull["only_seasons"])
            and g["season"] not in pull.get("skip_seasons", [])
            and (not seasons or g["season"] in seasons)
            and (only is None or g["id"] in only)]


def week_games(games: list[dict], week_of) -> list[dict]:
    """One week of games: from `week_of` (a date), or with "auto" the first week of the latest unsealed season."""
    if week_of == "auto":
        open_ = [g for g in games if not g["sealed"]]
        if not open_:
            return []
        season = max(open_, key=lambda g: g["commence_time"])["season"]
        start = min(g["commence_time"] for g in open_ if g["season"] == season)
    else:
        start = datetime.combine(_d(week_of), time(), tzinfo=UTC)
    return [g for g in games if start <= g["commence_time"] < start + timedelta(days=7)]


def plan_calls(cfg: dict, pid: str, schedules: dict[str, list[dict]], *, now: datetime | None = None,
               week_of=None, sports=None, seasons=None) -> list[Call]:
    """Every call a pull needs, from the saved schedules. Featured snapshots are unioned across games."""
    now, pull = now or utcnow(), cfg["pulls"][pid]
    books = cfg["books"][pull["books"]]
    markets = pull.get("markets", cfg["featured"])
    cost = 10 * len(markets.split(",")) * regions(books)
    cache_as = pull.get("cache_as") or {}
    calls: list[Call] = []
    for sport in pull["sports"]:
        if sports and sport not in sports:
            continue
        games = pull_games(cfg, pull, sport, schedules.get(sport, []), now, seasons)
        if week_of is not None:
            games = week_games(games, week_of)
        cache_sport = cache_as.get("sport", sport)
        start = datetime.combine(cfg["sports"][sport]["history_from"], time(), tzinfo=UTC)
        if pull["kind"] == "featured":
            sealed_at: dict[datetime, bool] = {}
            for g in games:
                for t in game_snapshots(g["commence_time"], pull):
                    if start <= t <= now:
                        sealed_at[t] = sealed_at.get(t, False) or g["sealed"]
            calls += [Call(pid, sport, cache_as.get("source", SRC_ODDS), f"/historical/sports/{sport}/odds",
                           _odds_params(books, markets, t), t, cost, s, cache_sport=cache_sport)
                      for t, s in sorted(sealed_at.items())]
        elif pull["kind"] == "event":
            calls += [Call(pid, sport, SRC_EVENT_ODDS, f"/historical/sports/{sport}/events/{g['id']}/odds",
                           _odds_params(books, markets, t), t, cost, g["sealed"], g["id"], cache_sport)
                      for g in games for t in event_snapshots(g["commence_time"], pull["offsets"])]
        else:
            raise ValueError(f"{pid}: unknown kind {pull['kind']!r}")
    sealed = [c for c in calls if c.sealed]
    if cache_as and sealed:
        raise SystemExit(
            f"{pid}: refused. It writes into another pipeline's cache ({cache_as.get('sport')}/{cache_as.get('source')}), "
            f"which `markets build` reads directly, so it must never fetch a sealed season, and {len(sealed):,} of its "
            f"planned calls are in one (the first at {iso(sealed[0].at)}). Limit the pull with only_seasons or "
            "skip_seasons in config/odds5m.yaml.")
    return calls


# ---------------------------------------------------------------- client
def _kind(call: Call) -> str:
    """"events" (historical /events), "event_odds" (one game's odds) or "featured" (a sport's odds snapshot)."""
    if call.path.endswith("/events"):
        return "events"
    return "event_odds" if "/events/" in call.path else "featured"


def markets_returned(data) -> set[str]:
    """The distinct market keys in a response's `data` (a list of events, or one event)."""
    events = [data] if isinstance(data, dict) else data if isinstance(data, list) else []
    out = set()
    for ev in events:
        for bm in (ev.get("bookmakers") or []) if isinstance(ev, dict) else []:
            for mk in (bm.get("markets") or []) if isinstance(bm, dict) else []:
                if isinstance(mk, dict) and mk.get("key"):
                    out.add(str(mk["key"]))
    return out


def documented_cost(call: Call, status: int, body: str) -> int:
    """What the API's documentation charges for one response, from the call and what came back (the v4 docs, as
    _account quotes them): /events, 1 when it lists any event; odds, 10 x the markets returned x regions (one per 10
    books in the call). Only markets asked for count (an exchange's `h2h_lay` is billed with `h2h`). The docs count a
    featured snapshot's markets asked for; counting those returned is never more, so a market nobody quoted can't make
    an honest bill look short. An empty result, a 404 or an error: 0. Never above the upper bound, `call.expected`."""
    b = _json(body) if status == 200 else None
    data = b.get("data") if isinstance(b, dict) else None
    if _kind(call) == "events":
        return 1 if data else 0
    p = dict(call.params)
    books = [x for x in p.get("bookmakers", "").split(",") if x]
    asked = {m for m in p.get("markets", "").split(",") if m}
    return 10 * len(markets_returned(data) & asked) * regions(books)


def _json(body: str):
    """A body as JSON, or None when it is empty or isn't JSON."""
    try:
        return json.loads(body) if body else None
    except ValueError:
        return None


def _envelope(body: str) -> dict:
    b = _json(body)
    if not isinstance(b, dict):
        return {"n": len(b) if isinstance(b, list) else 0}
    data = b.get("data")
    return {"timestamp": b.get("timestamp") or "", "previous_timestamp": b.get("previous_timestamp") or "",
            "next_timestamp": b.get("next_timestamp") or "",
            "n": 1 if isinstance(data, dict) else len(data or [])}


def _interpret(call: Call, status: int, body: str) -> tuple[int, dict] | None:
    """An answer's documented cost and its envelope (the manifest's snapshot fields), or None for an HTTP 200 whose body
    can't be interpreted: not JSON, or JSON whose `data` (or what is inside it) isn't what the API sends, a number say.
    An error answer's documented cost is 0 whatever its body holds, and an envelope it can't give is left blank."""
    b = _json(body)
    try:
        if status == 200 and not (isinstance(b, list) or isinstance(b, dict)
                                  and isinstance(b.get("data"), (list, dict, type(None)))):
            return None
        return documented_cost(call, status, body), _envelope(body)
    except Exception:                    # noqa: BLE001 - whatever a body holds, its answer is counted
        return None if status == 200 else (0, {})


def _cost(value, up: bool = True) -> int | None:
    """A billing header as whole credits: `x-requests-last` with a fraction rounded up, `x-requests-remaining`
    (up=False) rounded down. None when it is missing, not a number, negative or not finite: "unknown", never zero."""
    try:
        x = float(value)
    except (TypeError, ValueError):
        return None
    return (math.ceil(x) if up else int(x)) if math.isfinite(x) and x >= 0 else None


def _headers(r) -> dict[str, str]:
    """A response's headers, names lower-cased, every value with the key blanked (markets.http.scrub), in case a
    server or proxy echoed the request into one."""
    return {str(k).lower(): scrub(v) for k, v in r.headers.items()}


def _n(x) -> str:
    return "unknown" if x is None else f"{x:,}"


def _credits(n: int) -> str:
    return f"{n:,} credit{'' if n == 1 else 's'}"


class _Unusable(Exception):
    """A billed HTTP 200 whose body can't be interpreted (_interpret). Raised inside the cache's fetch, so it isn't
    cached."""


DISK_HELP = "Free some space (docs/ODDS5M_DAY_ONE.md, Before buying, step 2), then rerun."


class _Sending:
    """The session as http_get sees it: it marks a request as out (BulkClient._sent) just before sending it, so a
    Ctrl-C while the next request only waits (rate limit, retry backoff) counts nothing for it (BulkClient.interrupted)."""

    def __init__(self, client: "BulkClient"):
        self.client = client

    def get(self, *a, **k):
        self.client._sent = True
        return self.client.session.get(*a, **k)


def _latched(method):
    """A client method whose first stop the client keeps, so that it refuses every later attempt with it: a Stop,
    Ctrl-C, or any other error (a full disk, a bug), which becomes the Stop its STOPPED line gives once the attempt it
    cut short is counted (BulkClient._count_out)."""
    @functools.wraps(method)
    def wrapper(self, *a, **k):
        try:
            return method(self, *a, **k)
        except (Stop, KeyboardInterrupt) as e:
            self.stopped = self.stopped or (e if isinstance(e, Stop) else Stop(f"{INTERRUPTED} (Ctrl-C)", rerun=True))
            raise
        except Exception as e:           # noqa: BLE001 - a full disk or a bug ends the run as a Stop does
            if self.stopped is None:
                self.stopped = _as_stop(e, self._count_out())
            raise self.stopped from None
    return wrapper


def _as_stop(e: Exception, note: str = "") -> Stop:
    """The Stop for an error that isn't one: a full disk, or a bug (its traceback is logged, key blanked). `note` says
    how the attempt it cut short was counted (BulkClient._count_out)."""
    if isinstance(e, OSError):
        return Stop(f"a file could not be read or written ({e.strerror or e}): is the disk full? The call that was out "
                    f"is not cached, so a rerun asks again. {DISK_HELP}{note}", rerun=True)
    log.error("the run stopped on an unexpected error:\n%s", scrub("".join(traceback.format_exception(e))))
    return Stop(f"unexpected error, probably a bug; tell the hub before rerunning ({type(e).__name__}: {scrub(e)})"
                + (f".{note}" if note else ""))


class BulkClient:
    """The one client that spends Odds API credits (the bulk puller, and odds-pull through OddsApiClient).

    `counted`, checked against --max-credits before every attempt (first try or retry) and never lowered, counts every
    answer, a 429 or 5xx about to be retried included, at the larger of what it reports (x-requests-last, rounded up)
    and its documented_cost (its upper bound for a 200 whose body can't be interpreted), or at its upper bound when a
    billed answer's cost can't be read; and every attempt with no answer (a timeout, a dropped connection, any other
    error from the session, Ctrl-C with a request out) at its upper bound. The run stops on a 200 whose cost or body
    can't be read, an answer with data that reports less than its documented cost, any answer that reports more than
    its upper bound (not retried), and an answer that takes the count past --max-credits.

    The balance (x-requests-remaining) never adds to the count. The key check's is the start; `lowest` is the lowest
    since. A reading above the one before it by more than `margin` is credits added or the month renewed (a warning,
    and the run starts again from it: start = it + count, lowest = it); by the margin or less, it is out of date
    (ignored, tallied in `stale`). No attempt starts that could take `remaining`, min(lowest, start - count), below
    --floor. The one alarm: `unexplained`, (start - lowest) - count, above `margin` (the larger of 5,000 and 10% of
    --max-credits, or --alarm-margin). After any stop the client refuses every later attempt with that stop (`stopped`).
    """
    cache_statuses: tuple[int, ...] = (200, 404)     # a 404 is "nothing there at that time"; other errors never cached

    def __init__(self, cache: RawCache, *, max_credits: int, floor: int = 0, rate_per_sec: float = 8.0,
                 session=None, api_key: str | None = None, max_retries: int = 6, max_errors: int = 5,
                 alarm_margin: int | None = None):
        self.cache, self.max_credits, self.floor, self.alarm_margin = cache, max_credits, floor, alarm_margin
        self.session = session or new_session()
        self.limiter = RateLimiter(rate_per_sec)
        self.api_key, self.max_retries, self.max_errors = api_key, max_retries, max_errors
        self.counted = self.unanswered = self.fetched = self.errors_in_row = self.stale = 0
        self.start: int | None = None          # the balance the count is measured from (the key check's)
        self.lowest: int | None = None         # the lowest balance reported since the start
        self.last_seen: int | None = None      # the last readable balance, as reported
        self.stopped: Stop | None = None       # the first stop: every later attempt is refused with it
        self.not_saved: dict[str, int] = {}    # cache key -> HTTP status of a call whose last answer was an error
        self._out: Call | None = None          # the call being fetched, and an answer to it not counted yet (Ctrl-C)
        self._answer: tuple[Call, Fetched, bool] | None = None   # (call, answer, about to be retried)
        self._unlogged: tuple | None = None    # (call, row, cost, manifest size) of an answer counted, row not written
        self._sent = False                     # a request for `_out` is out, its answer not yet counted or held
        self.manifest = Path(cache.raw_dir) / "_manifest" / "oddsapi_manifest.csv"

    def _base(self) -> str:
        return BASE_URL

    def _key(self) -> str | None:
        return self.api_key or env("ODDS_API_KEY")

    @property
    def margin(self) -> int:
        return self.alarm_margin if self.alarm_margin is not None else max(DEFAULT_MARGIN, self.max_credits // 10)

    @property
    def remaining(self) -> int | None:
        """The run's estimate of the balance: the lower of the lowest reported and the start less the count."""
        return None if self.start is None else min(self.lowest, self.start - self.counted)

    @property
    def unexplained(self) -> int | None:
        """How much further the account has fallen than this run counted."""
        return None if self.start is None else (self.start - self.lowest) - self.counted

    def _no_answer(self, call: Call) -> None:
        """An attempt at `call` got no answer. It may have been billed: its upper bound counts, to the end of the run."""
        self.counted += call.expected
        self.unanswered += call.expected
        self._sent = False

    def _count_out(self) -> str:
        """An error other than a Stop cut an attempt short (_latched); what follows says how it was counted, for the
        STOPPED line. An answer already counted keeps its count, and its manifest row is written now (if it can't be,
        the line says what the row would have held); an answer not yet counted counts the larger of what it reported
        and its upper bound, with no row; a request still out, its upper bound."""
        if (logged := self._write_unlogged()) is not None:
            _, cost, note = logged
            return note and f" The answer that had come back was counted at what it cost, {_credits(cost)}.{note}"
        if self._answer is not None:
            (call, f, retrying), self._answer = self._answer, None
            last = _cost(f.headers.get("x-requests-last"))
            cost = max(last or 0, call.expected)
            self.counted += cost
            self.fetched += not retrying
            return (f" The answer that had come back was counted at {_credits(cost)}, the larger of what it reported "
                    f"and its upper bound, and has no manifest row (it would have held HTTP {f.status}, credits_last "
                    f"{last}, cache key {call.key}).")
        if self._sent and self._out is not None:
            self._no_answer(self._out)
            return f" The call that was out is counted at its upper bound, {_credits(self._out.expected)}."
        return ""

    def _write_unlogged(self) -> tuple[Call, int, str] | None:
        """An answer counted whose manifest row isn't written yet (a Ctrl-C or an error came between the two): the row is
        written now, unless it already was. Returns (call, cost, note), the note saying what the row would have held
        when it can't be written; None when there is no such answer."""
        if self._unlogged is None:
            return None
        (call, row, cost, size), self._unlogged = self._unlogged, None
        try:
            if self._manifest_size() == size:
                self._log(row)
            return call, cost, ""
        except Exception as e:           # noqa: BLE001 - a full disk, or a row the file can't hold
            return call, cost, (f" Its manifest row could not be written ({getattr(e, 'strerror', None) or e}); it "
                                f"would have held HTTP {row['http_status']}, credits_last {row['credits_last']}, cache "
                                f"key {row['cache_key']}.")

    def _saw_balance(self, left: int) -> None:
        if self.start is None or left - self.last_seen > self.margin:   # library use with no key check, or credits added
            if self.start is not None:
                log.warning("the reported balance rose from %s to %s during the run, more than the margin of %s: credits "
                            "were added or the month renewed; the run starts again from there",
                            f"{self.last_seen:,}", f"{left:,}", f"{self.margin:,}")
            self.start, self.lowest = left + self.counted, left
        elif left > self.last_seen:        # out of date: ignored, and logged as a count when the pull ends
            self.stale += 1
        self.lowest, self.last_seen = min(self.lowest, left), left

    def _precheck(self, call: Call, what: str = "the next call") -> None:
        """Before every attempt, first try or retry: the first stop again, if there was one; the budget; the floor."""
        if self.stopped is not None:
            raise self.stopped
        if self.counted + call.expected > self.max_credits:
            maybe = (f" ({self.unanswered:,} of it for attempts that got no answer and may have been billed)"
                     if self.unanswered else "")
            raise BudgetExceeded(f"{what} could cost {call.expected}; {self.counted:,} of the {self.max_credits:,}-credit "
                                 f"run budget is counted{maybe}", rerun=True)
        left = self.remaining
        if left is None:
            if self.floor > 0:
                raise BudgetExceeded(f"the account balance is unknown, so the floor of {self.floor:,} can't be "
                                     "checked. Nothing more was fetched; a new run reads the balance before it starts",
                                     rerun=True)
        elif left - call.expected < self.floor:
            raise BudgetExceeded(f"{left:,} credits remain at most; {what} could cost {call.expected}, and the floor is "
                                 f"{self.floor:,}")

    def _retrying(self, call: Call, why: str, resp) -> None:
        """http_get is about to retry `call` after `why`. The attempt is counted first: an answer (a 429 or 5xx) like
        any other, and one with no answer at its upper bound. Then the budget and floor are checked as for a new call."""
        if resp is None:
            self._no_answer(call)
        else:
            f = self._fetched(resp)
            self._answer, self._sent = (call, f, True), False
            self._account(call, self._record(call, f), retrying=True)
        self._precheck(call, f"retrying {call.path} at {iso(call.at)} after {why}")

    def _get(self, url: str, params: dict, call: Call | None = None):
        """One GET with the key added; for a paid `call`, each retry goes through `_retrying`, and a network failure
        that outlasts the retries, or any other error the session raises with the request out, counts its upper bound
        and stops the run. Error text never holds the key."""
        try:
            return http_get(_Sending(self), url, {**params, "apiKey": self._key()}, self.limiter,
                            max_retries=self.max_retries,
                            before_retry=None if call is None else (lambda why, r: self._retrying(call, why, r)))
        except requests.RequestException as e:
            why, rerun = (f"no answer from the Odds API after the retries ({type(e).__name__}: {scrub(e)}). Nothing was "
                          "cached for this call, so a rerun asks again."), True
        except Exception as e:
            if isinstance(e, Stop) or not self._sent:
                raise                    # not the session's: a Stop from _retrying, the cache, or a bug of ours
            if isinstance(e, OSError):   # a socket error `requests` didn't wrap (a raw TimeoutError): no answer
                why, rerun = (f"no answer from the Odds API ({type(e).__name__}: {scrub(e)}; not retried). Nothing was "
                              "cached for this call, so a rerun asks again."), True
            else:
                log.error("the request raised an unexpected error:\n%s", scrub("".join(traceback.format_exception(e))))
                why, rerun = (f"unexpected error, probably a bug; tell the hub before rerunning ({type(e).__name__}: "
                              f"{scrub(e)}). It came from sending the request, which got no answer."), False
        self._sent = False
        if call is not None:
            self._no_answer(call)
            why += (f" It may still have been billed, so its upper bound, {_credits(call.expected)}, is counted to the "
                    "end of the run; the rerun's key check reads the true balance.")
        raise CircuitBreaker(why, rerun=rerun)

    def _fetched(self, r) -> Fetched:
        """A response as it is kept: header values scrubbed, and the body with the key itself blanked and nothing else
        changed, so a body that doesn't hold the key is stored exactly as the server sent it."""
        body = blank_key(r.text, self._key())
        if r.status_code == 200 and body != r.text:
            log.warning("the API echoed the key in an answer with data; it was blanked before the answer was kept")
        return Fetched(r.status_code, _headers(r), body)

    @_latched
    def account(self) -> dict:
        """GET /v4/sports, free and never cached: checks the key and reads the balance the run starts from. Raises Stop,
        before any paid call, on a rejected key, an answer other than 200, a balance that is unreadable or below the
        floor, or a manifest row that can't be written (a full disk). A client that stopped refuses it with that stop,
        so its start and lowest balance still describe the run that stopped."""
        if self.stopped is not None:
            raise self.stopped
        r = self._get(self._base() + "/sports", {})
        h = _headers(r)                  # every value with the key blanked, in case a header echoes the request
        self.start = self.lowest = self.last_seen = _cost(h.get("x-requests-remaining"), up=False)
        try:
            self._log({"pull": "account", "path": "/sports", "http_status": r.status_code,
                       "credits_last": _cost(h.get("x-requests-last")), "remaining": self.start,
                       "sha256": hashlib.sha256(r.text.encode()).hexdigest()})
        except OSError as e:
            raise CircuitBreaker(f"the key check's manifest row could not be written ({e.strerror or e}): is the disk "
                                 f"full? The key check is free, so nothing was spent. {DISK_HELP}", rerun=True) from None
        if r.status_code == 401:
            raise CircuitBreaker("the Odds API rejected the key (401): check ODDS_API_KEY in sharp-markets/.env")
        if r.status_code != 200:
            raise CircuitBreaker(f"the free key check (/v4/sports) returned HTTP {r.status_code}: "
                                 f"{scrub(r.text)[:200]}. Try again in a few minutes.")
        if self.start is None:
            raise CircuitBreaker(f"the free key check did not return a readable balance (x-requests-remaining is "
                                 f"{h.get('x-requests-remaining')!r}), so the floor and the budget can't be checked")
        if self.start < self.floor:
            raise BudgetExceeded(f"the account has {self.start:,} credits left, already below the floor of "
                                 f"{self.floor:,}")
        return {"status": r.status_code, "remaining": self.start, "used": h.get("x-requests-used")}

    def is_cached(self, call: Call) -> bool:
        return self.cache.lookup(call.cache_sport, call.source, call.key) is not None

    def cached_record(self, call: Call) -> dict | None:
        p = self.cache.lookup(call.cache_sport, call.source, call.key)
        return read_record(p) if p is not None else None

    def cached_status(self, call: Call) -> int | None:
        """The HTTP status of the cached answer to `call` (200, or 404: nothing there at that time), or None."""
        p = self.cache.lookup(call.cache_sport, call.source, call.key)
        return None if p is None else read_status(p)

    @_latched
    def fetch(self, call: Call, refetch: bool = False) -> dict:
        """The stored record for this call (cache first; `refetch`, --retry-404, asks a cached call again and keeps the
        answer only if it is a 200). Raises Stop before or after a call that must end the run. A billed response that
        can't be kept (a 200 it can't interpret, a full disk) is counted, logged, not cached, and stops the run."""
        if refetch or not self.is_cached(call):
            self._precheck(call)
        sent: list[Fetched] = []

        def fetch() -> Fetched:
            f = self._fetched(self._get(call.url, dict(call.params), call))
            self._answer, self._sent = (call, f, False), False
            sent.append(f)
            if f.status == 200 and _interpret(call, f.status, f.body) is None:
                raise _Unusable
            return f

        self._out, self._sent = call, False
        try:
            rec = self.cache.get_or_fetch(sport=call.cache_sport, source=call.source,
                                          data_date=call.at.date().isoformat(), url=call.url, params=dict(call.params),
                                          fetch=fetch, cache_statuses=(200,) if refetch else self.cache_statuses,
                                          refresh=refetch)
        except _Unusable:
            self._account(call, self._record(call, sent[-1]))
            raise                        # not reached: _account stops the run on a 200 it can't interpret
        except OSError as e:
            if not sent:
                raise CircuitBreaker(f"the cache could not be read ({e.strerror or e}). Nothing was fetched.",
                                     rerun=True) from None
            self._account(call, self._record(call, sent[-1]),
                          problem=f"the response could not be saved ({e.strerror or e}): is the disk full? It was "
                                  f"billed and is counted, but not cached, so a rerun buys it again. {DISK_HELP}")
            raise
        self._out = None
        if sent:
            if rec["http_status"] in self.cache_statuses:      # saved (a 404 asked again keeps the saved 404)
                self.not_saved.pop(call.key, None)
            else:                        # an error answer: not cached, so a rerun asks again
                self.not_saved[call.key] = rec["http_status"]
            self._account(call, rec)
        return rec

    def interrupted(self) -> str:
        """Ctrl-C: counts the call that was out and says how, for the STOPPED line; the client then refuses every later
        attempt. An answer that had come back counts what it cost, with one manifest row (written here if the Ctrl-C came
        between its count and its row); a request with no answer yet, its upper bound; a request not yet sent, nothing."""
        out, self._out = self._out, None
        self.stopped = self.stopped or Stop(f"{INTERRUPTED} (Ctrl-C)", rerun=True)
        note = ""
        if (logged := self._write_unlogged()) is not None:  # counted: its row is written now, unless it already was
            call, cost, note = logged
        elif self._answer is not None:                     # came back, not counted yet: counted and logged now
            (call, answer, retrying), before = self._answer, self.counted
            try:
                self._account(call, self._record(call, answer), retrying=retrying)
            except Stop as e:
                note = f" That answer also stops the run: {e}"
            cost = self.counted - before
        elif out is None or not self._sent:
            return ("No call was out." if out is None else "No request was out (the next one was waiting for the rate "
                    "limit or for a retry), so nothing more is counted for it.")
        else:
            self._no_answer(out)
            return (f"The call that was out may have been billed, so it is counted at its upper bound, "
                    f"{_credits(out.expected)}, and a rerun may buy it again.")
        saved = self.is_cached(call)
        return (f"The answer to the call that was out had come back{' and was saved' if saved else ''}, so it is "
                f"counted at what it cost, {_credits(cost)}" + ("." if saved else ", and a rerun buys it again.") + note)

    @staticmethod
    def _record(call: Call, f: Fetched) -> dict:
        """The fields _account reads, for a response the cache didn't store."""
        return {"headers_json": json.dumps({k: v for k, v in f.headers.items() if k.startswith("x-requests-")}),
                "body": f.body, "http_status": f.status, "cache_key": call.key}

    def _account(self, call: Call, rec: dict, problem: str | None = None, retrying: bool = False) -> None:
        """Count one answer, log it, and stop the run when it must end (the class docstring has the rule). `problem`
        (a response that couldn't be kept) stops the run once the answer is counted and logged; `retrying`, a 429 or
        5xx that http_get is about to retry. The v4 docs (read Sep 29, 2026) bill by the data returned and name no charge
        for an error, so an error answer counts what it reports and the run goes on (stopping at every 404 would stall
        F2 and F3), until max_errors in a row; 401 and 429 stop it at once."""
        h = json.loads(rec["headers_json"] or "{}")
        body, status = rec["body"] or "", rec["http_status"]
        # the raw values go into STOPPED lines and log lines, so the key is blanked in them
        raw_last, raw_left = (None if v is None else scrub(v) for v in (h.get("x-requests-last"),
                                                                         h.get("x-requests-remaining")))
        last, left = _cost(raw_last), _cost(raw_left, up=False)
        read = _interpret(call, status, body)      # None: a 200 whose documented cost can't be worked out
        documented, env_ = read or (call.expected, {})
        cost = call.expected if last is None else max(last, documented)
        p = dict(call.params)
        row = {"pull": call.pull, "sport": call.sport, "source": call.source, "path": call.path,
               "event_id": call.event_id, "requested_ts": iso(call.at), "returned_ts": env_.get("timestamp", ""),
               "previous_ts": env_.get("previous_timestamp", ""), "next_ts": env_.get("next_timestamp", ""),
               "markets": p.get("markets", ""), "books": p.get("bookmakers", ""), "n_events": env_.get("n"),
               "expected_credits": call.expected, "credits_last": last, "remaining": left, "http_status": status,
               "sha256": hashlib.sha256(body.encode()).hexdigest(), "cache_key": rec["cache_key"], "sealed": call.sealed}
        # One statement, so a Ctrl-C comes before it (interrupted() counts the answer) or after it (the answer is
        # counted, and interrupted() writes its manifest row if the row isn't written yet): never both, never neither.
        self.counted, self.fetched, self._answer, self._sent, self._unlogged = (
            self.counted + cost, self.fetched + (not retrying), None, False, (call, row, cost, self._manifest_size()))
        if left is not None:
            self._saw_balance(left)
        where = f"{call.path} at {iso(call.at)}" + (f" (HTTP {status}, not retried)" if retrying else "")
        try:
            self._log(row)
        except OSError as e:
            saved = not retrying and self.is_cached(call)
            problem = (f"{problem} The manifest row could not be written either." if problem else
                       ("the response is cached, but its manifest row" if saved else
                        "the answer was not saved (a rerun asks for it again), and its manifest row")
                       + f" could not be written ({e.strerror or e}): is the disk full? {DISK_HELP}")
        self._unlogged = None
        above = last is not None and last > call.expected
        if read is None:                 # a 200 it can't interpret: fetch raised _Unusable, so the cache didn't keep it
            kind = "a body that is not JSON" if _json(body) is None else "JSON it cannot read"
            problem = (f"the API answered HTTP 200 with {kind} ({scrub(body)[:120]!r}). It was not cached, so a rerun "
                       "asks again." + (f" {problem}" if problem else ""))
        if problem:
            billed = f"its upper bound, {_credits(call.expected)}" if last is None else _credits(cost)
            if read is None and last is not None:
                billed += ", the larger of what it reported and its upper bound"
            raise CircuitBreaker(f"{where}: {problem} It counted {billed} (x-requests-last {raw_last!r})"
                                 + (f", more than its upper bound of {call.expected}" if above else "") + ".",
                                 rerun=not above)
        if above:
            raise CircuitBreaker(f"{where} billed {last} credits; it should cost at most {call.expected}. Stopped: "
                                 "check the billing before going on.")
        if (fall := self.unexplained) is not None and fall > self.margin:
            raise CircuitBreaker(f"the account has fallen by {fall:,} credits more than this run counted (the margin "
                                 f"is {self.margin:,}; the last answer: {where}). The cause is one of three: something "
                                 "else is spending on this key, the balance header runs behind the charges, or the "
                                 "API is charging more than it reports. Run `uv run markets odds5m headers --pull "
                                 f"{call.pull}` and tell the hub before rerunning.")
        if last is None:
            log.warning("%s -> HTTP %s without a readable x-requests-last (%r); counted its upper bound %s",
                        where, status, raw_last, call.expected)
        if retrying:
            return
        err = scrub(body)[:200]          # error bodies are printed and logged only with any key blanked
        # A rejected key or a rate limit: a rerun starts with the free key check and buys nothing before the API
        # takes requests again, so rerunning is the next step (after the checks in the runbook's table).
        if status == 401:
            raise CircuitBreaker("the Odds API rejected the key (401)", rerun=True)
        if status == 429:
            raise CircuitBreaker(f"HTTP 429 after retries (quota used up or rate limited): {err}", rerun=True)
        if status == 200 and last is None:
            raise CircuitBreaker(f"the billing could not be read: {where} came back with x-requests-last "
                                 f"{raw_last!r}, so its upper bound, {call.expected}, was counted as spent. The "
                                 "response is cached. Check the billing before going on.")
        if last is not None and last < documented:
            raise CircuitBreaker(f"the billing cannot be trusted: {where} reported {last} credits (x-requests-last "
                                 f"{raw_last!r}), less than the {documented} the API's documentation charges for what "
                                 f"came back, so {documented} was counted. The response is cached. Check the billing "
                                 "before going on.")
        if status == 200 and left is None and self.floor > 0:
            raise CircuitBreaker(f"the balance could not be read: {where} came back with x-requests-remaining "
                                 f"{raw_left!r}, so the floor of {self.floor:,} can't be checked. The response is "
                                 "cached; a new run reads the balance before it starts.")
        if self.counted > self.max_credits:
            raise BudgetExceeded(f"{where} took the count to {self.counted:,}, past the {self.max_credits:,}-credit run "
                                 "budget. Check the billing before going on.")
        if status in (200, 404):
            self.errors_in_row = 0
            return
        self.errors_in_row += 1
        log.warning("%s at %s -> HTTP %s: %s", call.path, iso(call.at), status, err)
        if self.errors_in_row >= self.max_errors:
            raise TooManyErrors(f"{self.errors_in_row} errors in a row; the last was HTTP {status}: {err}", status)

    def _manifest_size(self) -> int:
        try:
            return self.manifest.stat().st_size
        except OSError:
            return -1

    def _log(self, row: dict) -> None:
        self.manifest.parent.mkdir(parents=True, exist_ok=True)
        new = not self.manifest.exists()
        with self.manifest.open("a", newline="") as f:
            w = csv.DictWriter(f, MANIFEST_FIELDS)
            if new:
                w.writeheader()
            w.writerow({"logged_at": iso(utcnow()), **{k: ("" if v is None else v) for k, v in row.items()}})


INTERRUPTED = "interrupted"


def summary_line(client: BulkClient, stopped, fetched: int | None = None, credits: int | None = None,
                 errors: int = 0, cached_404: int | None = None) -> str:
    """The line every run ends with: this pull's calls fetched and credits, the run's credits, the balance, how many
    calls got an error answer (not saved, so a rerun asks for them again), and how many are cached 404s."""
    fetched = client.fetched if fetched is None else fetched
    credits = client.counted if credits is None else credits
    errs = f" ({errors:,} answered with an error and not saved; a rerun asks again)" if errors else ""
    n404 = "" if cached_404 is None else f", cached 404s {cached_404:,}"
    return (f"  {'stopped' if stopped else 'done'}: {fetched:,} fetched{errs}, credits {credits:,} "
            f"(this run {client.counted:,}), remaining {_n(client.remaining)}{n404}")


def _todo(client: BulkClient, calls: list[Call], retry_404: bool = False) -> list[Call]:
    """The calls a run asks: the ones not cached, and with retry_404 the cached 404s as well."""
    return [c for c in calls if not client.is_cached(c) or (retry_404 and client.cached_status(c) == 404)]


def _stopped_by(client: BulkClient, e: BaseException) -> tuple[str, bool]:
    """What follows `STOPPED:` (key blanked) for anything a fetch raised, and whether a rerun is next (Stop.rerun)."""
    if isinstance(e, KeyboardInterrupt):
        return f"{INTERRUPTED} (Ctrl-C). {client.interrupted()} A rerun resumes from the cache.", True
    stop = e if isinstance(e, Stop) else _as_stop(e)
    return scrub(stop), stop.rerun


def _log_stale(client: BulkClient, stale0: int, label: str) -> None:
    """Once, when a pull ends: how many readings of the balance were out of date (ignored; BulkClient._saw_balance)."""
    if n := client.stale - stale0:
        log.info("%s: %s reading%s of the balance came back higher than the one before, by no more than the margin of "
                 "%s: out of date, so ignored", label or "the pull", f"{n:,}", "" if n == 1 else "s",
                 f"{client.margin:,}")


def run_calls(client: BulkClient, calls: list[Call], label: str = "", *, skip_sport_on_errors: bool = False,
              retry_404: bool = False) -> dict:
    """Fetch the calls not yet cached, in order (with retry_404, the cached 404s too, each kept only if it comes back a
    200). Every way a run can end, a bug included, ends here with a STOPPED line when it stopped (key blanked), then one
    summary line with this pull's own counts. skip_sport_on_errors (the probe's sweeps): max_errors refusals in a row
    (HTTP 4xx) in one sport skip the rest of its calls ("skipped": sport -> calls not asked); 5xx still stop the run."""
    todo = _todo(client, calls, retry_404)
    again = sum(client.is_cached(c) for c in todo)
    print(f"{label}: {len(calls):,} calls, {len(calls) - len(todo):,} cached, {len(todo):,} to fetch"
          + (f" ({again:,} of them cached 404s asked again)" if again else "")
          + f", at most {sum(c.expected for c in todo):,} credits", flush=True)
    fetched0, counted0, stale0 = client.fetched, client.counted, client.stale
    stopped, interrupted, rerun = None, False, False
    skipped: dict[str, int] = {}
    sport = None
    for i, c in enumerate(todo, 1):
        if skip_sport_on_errors:
            if c.sport in skipped:
                skipped[c.sport] += 1
                continue
            if c.sport != sport:
                sport, client.errors_in_row = c.sport, 0
        try:
            client.fetch(c, refetch=retry_404 and client.is_cached(c))
        except (Exception, KeyboardInterrupt) as e:     # noqa: BLE001 - a bug too ends the run with its summary
            if skip_sport_on_errors and isinstance(e, TooManyErrors) and 400 <= e.status < 500:
                skipped[c.sport] = 0
                client.errors_in_row, client.stopped = 0, None      # skipping one sport is not a stop of the run
                print(f"  {c.sport}: {scrub(e)}. The rest of its calls are skipped; going on with the next sport.",
                      flush=True)
            else:
                (stopped, rerun), interrupted = _stopped_by(client, e), isinstance(e, KeyboardInterrupt)
        if stopped:
            print(f"  STOPPED: {stopped}", flush=True)
            break
        if i % 500 == 0:
            print(f"  {i:,}/{len(todo):,}  credits this run {client.counted:,}  remaining {_n(client.remaining)}",
                  flush=True)
    fetched, spent = client.fetched - fetched0, client.counted - counted0
    _log_stale(client, stale0, label)
    errors = sum(c.key in client.not_saved for c in todo)
    n404 = None if interrupted else sum(client.cached_status(c) == 404 for c in calls)
    print(summary_line(client, stopped, fetched, spent, errors, n404), flush=True)
    return {"calls": len(calls), "todo": len(todo), "fetched": fetched, "spent": spent,
            "run_fetched": client.fetched, "run_spent": client.counted, "remaining": client.remaining,
            "stopped": stopped, "interrupted": interrupted, "rerun": rerun, "errors": errors, "skipped": skipped,
            "cached_404": n404}


# ---------------------------------------------------------------- reading the cache
def cached_bodies(client: BulkClient, calls: list[Call], statuses: Counter | None = None):
    """(call, record, body) for each cached 200; `statuses`, when given, counts every cached record by HTTP status."""
    for c in calls:
        rec = client.cached_record(c)
        if rec is not None and statuses is not None:
            statuses[rec["http_status"]] += 1
        if rec is not None and rec["http_status"] == 200:
            yield c, rec, body_json(rec)


def game_time(value) -> datetime | None:
    """An odds row's commence_time, or None when it is missing or can't be read (never an error)."""
    try:
        return parse_ts(value) if isinstance(value, str) else None
    except ValueError:
        return None


def load_rows(cfg: dict, calls: list[Call], cache: RawCache, *, include_sealed: bool = False,
              left_out: Counter | None = None) -> list[dict]:
    """Normalized rows for the cached calls. Rows for games in a sealed season are left out unless
    include_sealed=True (only a pre-registered test of that season may pass it). A row whose game time can't be
    read, or whose game falls in no season window of the config (NHL 2026-27's first games, Sep 29-30, before its
    window starts), is judged by its call instead: left out when the plan marked the call sealed. `left_out`, when
    given, counts the rows left out by reason."""
    client = BulkClient(cache, max_credits=0)
    rows, out = [], Counter()
    for c, _, body in cached_bodies(client, calls):
        for r in outcome_rows(body, iso(c.at)):
            k = game_time(r["commence_time"])
            w = None if k is None else window_for(cfg, c.sport, k)
            sealed = w["sealed"] if w else c.sealed
            if include_sealed or not sealed:
                rows.append({**r, "sport": c.sport, "pull": c.pull})
            else:
                out["sealed season" if w else "no game time, sealed call" if k is None
                    else "in no season window, sealed call"] += 1
    if left_out is not None:
        left_out.update(out)
    return rows


def coverage(cfg: dict, calls: list[Call], cache: RawCache) -> dict:
    """What the cache holds for these calls: rows by book and market, empty snapshots, snapshot lag, and how many
    are cached 404s (the API had nothing there at that time; `--retry-404` asks them again)."""
    client = BulkClient(cache, max_credits=0)
    books, markets, lags, games, statuses = Counter(), Counter(), [], set(), Counter()
    n = empty = 0
    for c, _, body in cached_bodies(client, calls, statuses):
        n += 1
        rows = outcome_rows(body, iso(c.at))
        if not rows:
            empty += 1
        ts = parse_ts(body.get("timestamp"))
        if ts:
            lags.append((c.at - ts).total_seconds() / 60)
        books.update(r["bookmaker"] for r in rows)
        markets.update(r["market_key"] for r in rows)
        games.update(r["odds_event_id"] for r in rows)
    want = set()
    for pid in {c.pull for c in calls}:
        want |= set(cfg["books"][cfg["pulls"][pid]["books"]])
    return {"calls": len(calls), "cached_ok": n, "cached_404": statuses[404], "empty": empty, "games": len(games),
            "books": dict(books.most_common()),
            "missing_books": sorted(want - set(books)), "markets": dict(markets.most_common()),
            "lag_min_median": statistics.median(lags) if lags else None, "lag_min_max": max(lags) if lags else None}


# ---------------------------------------------------------------- stages
def _pulls(cfg: dict, arg: str) -> list[str]:
    """Pull IDs from a comma-separated argument; a group name (config `groups:`) expands to its pulls."""
    groups = cfg.get("groups", {})
    if arg in (None, "", "all"):
        return list(cfg["pulls"])
    ids = []
    for p in (x.strip() for x in arg.split(",")):
        ids += groups[p] if p in groups else [p]
    bad = [p for p in ids if p not in cfg["pulls"]]
    if bad:
        raise SystemExit(f"unknown pull(s) {bad}; the config has {list(cfg['pulls'])} and groups {list(groups)}")
    return list(dict.fromkeys(ids))


def group_of(cfg: dict, pid: str) -> str:
    return next((g for g, ids in cfg.get("groups", {}).items() if pid in ids), "-")


def summarize(cfg: dict, calls: list[Call], cache: RawCache) -> list[dict]:
    by = defaultdict(lambda: {"calls": 0, "cached": 0, "credits_todo": 0, "sealed_calls": 0})
    for c in calls:
        w = window_for(cfg, c.sport, c.at)
        row = by[(c.pull, c.sport, w["label"] if w else "-")]
        row["calls"] += 1
        row["sealed_calls"] += c.sealed
        if cache.lookup(c.cache_sport, c.source, c.key) is not None:
            row["cached"] += 1
        else:
            row["credits_todo"] += c.expected
    return [{"pull": p, "sport": s, "season": se, **v} for (p, s, se), v in by.items()]


def stage_plan(cfg, cache, args, now=None) -> list[dict]:
    """Every pull asked for (all of them by default), in the config's group order. A pull that waits for its game
    list (HB1 and HS1 before `markets weather qualifying`) gets one line saying so and counts as 0 calls for now."""
    schedules = load_schedules(cfg, cache.raw_dir)
    missing = [s for s in cfg["sports"] if s not in schedules]
    if missing:
        print(f"no schedule yet for {missing}: run `markets odds5m probe --confirm` first")
    total, out = 0, []
    for pid in _pulls(cfg, args.pull):
        if (waits := waiting_for_games(cfg["pulls"][pid])) is not None:
            print(f"{pid:3} {group_of(cfg, pid):8} {0:>9,} calls  waits for `markets weather qualifying` ({waits} is "
                  f"not written yet); counted as 0 for now")
            continue
        calls = plan_calls(cfg, pid, schedules, now=now, sports=args.sports, seasons=args.seasons)
        todo = sum(c.expected for c in calls if cache.lookup(c.cache_sport, c.source, c.key) is None)
        total += todo
        rows = summarize(cfg, calls, cache)
        out += rows
        by_slice = cfg["pulls"][pid].get("require_seasons") and not args.seasons
        named = ", ".join(f"--seasons {','.join(sorted(s))} ({n})" for n, s in _slices(cfg["pulls"][pid]).items())
        slices = f"  (all seasons; `full` needs one slice: {named or '--seasons'})" if by_slice else ""
        print(f"{pid:3} {group_of(cfg, pid):8} {len(calls):>9,} calls  at most {todo:>11,} credits to fetch  "
              f"cumulative {total:>11,}  sealed calls {sum(c.sealed for c in calls):,}{slices}")
    return out


def _client(cache, args, session=None) -> BulkClient:
    if not args.confirm:
        raise SystemExit("dry run: add --confirm (and --max-credits) to call the Odds API")
    if args.max_credits <= 0:
        raise SystemExit("--max-credits is required with --confirm")
    global _ACTIVE
    c = _ACTIVE = BulkClient(cache, max_credits=args.max_credits, floor=args.floor, rate_per_sec=args.rate,
                             session=session, alarm_margin=getattr(args, "alarm_margin", None))
    try:
        info = c.account()
    except Stop as e:
        raise SystemExit(f"STOPPED before the first paid call, nothing spent: {scrub(e)}") from None
    started(c, info)
    return c


def started(c: BulkClient, info: dict) -> None:
    """A paid run's first two lines: the key check, then the alarm's margin in force (odds5m and odds-pull)."""
    print(f"key ok: HTTP {info['status']}, {info['remaining']:,} credits remaining, "
          f"{_n(_cost(info['used'], up=False))} used; floor {c.floor:,}", flush=True)
    how = ("set by --alarm-margin" if c.alarm_margin is not None else
           f"the default: the larger of {DEFAULT_MARGIN:,} and 10% of --max-credits")
    print(f"alarm margin: {c.margin:,} credits ({how})", flush=True)


_ACTIVE: BulkClient | None = None       # the client of the current `odds5m` run, for the summary after a Ctrl-C


def stage_balance(cfg, cache, args, session=None) -> dict:
    """The free key check alone (/v4/sports costs nothing): prints the balance and the floor, and spends nothing.
    For reading the balance after a stop, before deciding whether to rerun."""
    if not args.confirm:
        raise SystemExit("dry run: add --confirm to read the balance (the key check is free, and nothing else is called)")
    c = BulkClient(cache, max_credits=0, floor=args.floor, rate_per_sec=args.rate, session=session)
    try:
        info = c.account()
    except Stop as e:
        raise SystemExit(f"STOPPED: {scrub(e)}") from None
    print(f"key ok: HTTP {info['status']}, {info['remaining']:,} credits remaining, "
          f"{_n(_cost(info['used'], up=False))} used; floor {c.floor:,}. Nothing was spent.")
    return info


def stage_probe(cfg, cache, args, now=None, session=None) -> dict:
    now = now or utcnow()
    sports = [s for s in cfg["sports"] if not args.sports or s in args.sports]
    sweeps = {s: sweep_calls(cfg, s, now) for s in sports}
    n = sum(len(v) for v in sweeps.values())
    print(f"P0 /events sweeps: {n:,} calls across {len(sports)} sports (1 credit each, 0 when empty); "
          f"billing and coverage probes: at most 270 more")
    if not args.confirm:
        for s, v in sweeps.items():
            print(f"  {s:36} {len(v):6,}")
        print("dry run: add --confirm --max-credits N to run it")
        return {"sweep_calls": n}
    client = _client(cache, args, session)
    res = run_calls(client, [c for v in sweeps.values() for c in v], "P0 sweeps", skip_sport_on_errors=True)
    # A sport's schedule is saved only when all of its /events calls are cached; otherwise the earlier file is kept
    # and the sport is incomplete. So is one whose sweeps found no games while some were answered 404 (cached, so a
    # rerun wouldn't ask them again), or while the saved file has games.
    counts, incomplete, refused, empty = {}, {}, {}, {}
    for s, calls in sweeps.items():
        missing = [c for c in calls if not client.is_cached(c)]
        if res["interrupted"] or missing:
            incomplete[s] = missing
            refused[s] = [(c, client.not_saved[c.key]) for c in missing if c.key in client.not_saved]
            continue
        games = build_schedule(cfg, s, [b for _, _, b in cached_bodies(client, calls)])
        if not games:
            path, n404 = schedule_path(cache.raw_dir, s), sum(client.cached_status(c) == 404 for c in calls)
            kept = pq.read_metadata(path).num_rows if path.exists() else 0
            if n404 or kept:
                incomplete[s], refused[s], empty[s] = [], [], (
                    f"all {len(calls):,} sweeps came back but listed no games, and {n404:,} of them were HTTP 404 "
                    "(saved, so a rerun won't ask them again)" if n404 else
                    f"the sweeps listed no games, so the saved schedule of {kept:,} game(s) was kept")
                continue
        save_schedule(cache.raw_dir, s, games)
        counts[s] = Counter(g["season"] or "outside windows" for g in games)
        print(f"  {s:36} {len(games):6,} games  " + "  ".join(f"{k}: {v}" for k, v in sorted(counts[s].items())))
    if incomplete:
        print(f"  incomplete, schedule not saved (any earlier schedule file is kept): {', '.join(incomplete)}")
    # The billing probes need only the sweeps that finished, so they run unless the sweeps themselves stopped. A sport
    # whose sweeps got error answers doesn't hold them up, unless it is the NFL: the probes start from its games.
    stopped, rerun = res["stopped"], res["rerun"]
    probes = [] if stopped else billing_probes(cfg, client, load_schedules(cfg, cache.raw_dir), now)
    if not stopped and (hit := next((p for p in probes if p.get("stopped")), None)):
        stopped, rerun = hit["result"], hit["rerun"]
    errors = False                       # the sweeps ran to the end, but some got an error answer
    if incomplete and not stopped:
        errors, rerun = any(refused.values()), not empty     # a rerun can't change a sport left empty by 404s
        what = "; ".join(f"{s} ({empty.get(s) or _unfinished(incomplete[s], refused[s], s in res['skipped'])})"
                         for s in incomplete)
        stopped = (f"the sweeps did not finish for {len(incomplete)} sport(s), so their schedules were not saved: "
                   f"{what}")
        print(f"  STOPPED: {stopped}", flush=True)
    print(f"P0 {'stopped' if stopped else 'done'}: credits this run {client.counted:,}, remaining "
          f"{_n(client.remaining)}", flush=True)
    if stopped:
        print("  " + _probe_next_step(rerun, errors), flush=True)
    return {**res, "stopped": stopped, "rerun": rerun, "spent": client.counted, "remaining": client.remaining,
            "games": counts, "incomplete": list(incomplete), "probes": probes}


def _probe_next_step(rerun: bool, errors: bool) -> str:
    """What the probe tells the operator after a stop: rerun only after a stop a rerun can't make worse (Stop.rerun);
    otherwise tell the hub first, since a rerun would buy more and could end `P0 done` with the alarm gone."""
    if not rerun:
        return ("Tell the hub before rerunning: a rerun could buy more of what this STOPPED line is about, and it "
                "would not stop again on an answer that is already saved (docs/ODDS5M_DAY_ONE.md, If a run stops, "
                "says what the line means).")
    return ("Rerun the same command until it prints `P0 done` before going on: the sweeps already fetched are cached, "
            "so a rerun buys only what is missing. "
            + ("If a rerun stops again on the same sweeps with an error answer, don't keep rerunning: tell the hub (the "
               "other sports' schedules are saved)." if errors else "If it stops the same way twice, tell the hub."))


def _unfinished(missing: list[Call], refused: list[tuple[Call, int]], skipped: bool = False,
                max_errors: int = 5) -> str:
    """Which of a sport's sweeps are missing: the ones answered with an error (date and HTTP status, the first
    three), and how many were skipped (after max_errors error answers in a row) or never reached."""
    parts = []
    if refused:
        shown = ", ".join(f"{iso(c.at)[:10]} HTTP {status}" for c, status in refused[:3])
        more = f" and {len(refused) - 3} more" if len(refused) > 3 else ""
        parts.append(f"{len(refused)} sweep{'s' if len(refused) != 1 else ''} answered with an error: {shown}{more}")
    if len(missing) > len(refused):
        n = len(missing) - len(refused)
        parts.append(f"{n} sweep{'s' if n != 1 else ''} "
                     + (f"skipped after {max_errors} errors in a row" if skipped else "not reached"))
    return "; ".join(parts)


def _probe_row(name: str, client: BulkClient, call: Call, want: str) -> dict:
    """One probe call through client.fetch, so it has the same budget, floor, billing and circuit-breaker
    checks as any pull. A stop (or an unexpected error) is printed like run_calls prints it, key blanked, and marked
    `stopped`, with `rerun` as Stop.rerun gives it."""
    try:
        rec = client.fetch(call)
    except (Exception, KeyboardInterrupt) as e:   # noqa: BLE001 - Stop, Ctrl-C or a bug: the probes end with their summary
        why, rerun = _stopped_by(client, e)
        print(f"  STOPPED: {why}", flush=True)
        return {"probe": name, "result": f"stopped: {why}", "stopped": True, "rerun": rerun}
    h = json.loads(rec["headers_json"] or "{}")
    billed = h.get("x-requests-last")
    body = body_json(rec) if rec["http_status"] == 200 else {}
    rows = outcome_rows(body or {}, iso(call.at))
    mk = sorted({r["market_key"] for r in rows})
    return {"probe": name, "http_status": rec["http_status"], "expected_max": call.expected,
            "billed": None if billed is None else scrub(billed), "markets_returned": mk,
            "books_returned": sorted({r["bookmaker"] for r in rows}),
            "events": len({r["odds_event_id"] for r in rows}), "check": want,
            **({"billing_rule": f"10 x {len(mk)} markets returned = {10 * len(mk)}"} if call.source == SRC_EVENT_ODDS else {})}


# The three coverage probes the plan review asked for (strategy-research/plan-review-2026-09-28.md, section 1):
# (sport key, season label, book group, what the answer decides). One featured close each, 30 credits at most.
EXTRA_PROBES = (
    ("americanfootball_ncaaf", "2020", "us10", "does Pinnacle price NCAAF in the 2020 history? (F1's CFB sharp close)"),
    ("baseball_mlb", "2024", "us10", "MLB featured history: are totals and Pinnacle there? (HB1)"),
    ("soccer_usa_mls", "2024", "soccer10", "MLS featured history: are totals and Pinnacle there? (HS1)"),
)


def billing_probes(cfg: dict, client: BulkClient, schedules: dict, now: datetime) -> list[dict]:
    """Seven single calls that test the cost model and coverage before the big spend (~270 credits at most):
    four on NFL billing, then EXTRA_PROBES, one featured close each, skipped when the schedule has no such game.
    They follow the pulls' rules: the first stop (budget, floor, overbilling, unreadable billing, network)
    ends the probes, and the ones after it are listed as not run."""
    nfl = [g for g in schedules.get("americanfootball_nfl", []) if g["commence_time"] <= now - SETTLED]
    g24 = next((g for g in nfl if g["season"] == "2024"), None)
    g20 = next((g for g in nfl if g["season"] == "2020"), None)
    if not g24:
        print("  billing probes skipped: no NFL 2024 game in the schedule")
        return []
    props = cfg["pulls"]["F3"]["markets"]
    us10, featured = cfg["books"]["us10"], cfg["featured"]
    ev = lambda books, g, at: Call("P0", "americanfootball_nfl", SRC_EVENT_ODDS,  # noqa: E731
                                   f"/historical/sports/americanfootball_nfl/events/{g['id']}/odds",
                                   _odds_params(books, props, at), at, 10 * len(props.split(",")) * regions(books),
                                   g["sealed"], g["id"], "americanfootball_nfl")
    fe = lambda books, g, sport="americanfootball_nfl": Call(  # noqa: E731
        "P0", sport, SRC_ODDS, f"/historical/sports/{sport}/odds",
        _odds_params(books, featured, close_time(g["commence_time"])), close_time(g["commence_time"]),
        30 * regions(books), g["sealed"], cache_sport=sport)
    at = close_time(g24["commence_time"])
    # (name, call or None when skipped, what it checks or why it is skipped), in the order they run
    specs = [("featured NFL, 10 books, 3 markets", fe(us10, g24), "billed 30 (one region)"),
             ("event odds NFL props, 10 books", ev(us10, g24, at), "billed = 10 x markets returned, at most 60"),
             ("event odds NFL props, Pinnacle only", ev(["pinnacle"], g24, at), "which props Pinnacle quotes")]
    if g20:
        specs.append(("featured NFL 2020, sharp books", fe(cfg["books"]["sharp3"], g20), "is LowVig in the 2020 data?"))
    for sport, season, books, want in EXTRA_PROBES:
        g = next((g for g in schedules.get(sport, []) if g["season"] == season and g["commence_time"] <= now - SETTLED),
                 None)
        name = f"featured {sport} {season}, {books}"
        if g is None or books not in cfg["books"]:
            specs.append((name, None, f"skipped: no {sport} {season} game in the schedule"))
        else:
            specs.append((name, fe(cfg["books"][books], g, sport), want))
    rows, stopped_at, stale0 = [], None, client.stale
    for name, call, want in specs:
        if call is None:
            rows.append({"probe": name, "result": want})
        elif stopped_at:
            rows.append({"probe": name, "result": f"not run: the probes stopped at {stopped_at!r}"})
        else:
            rows.append(_probe_row(name, client, call, want))
            if rows[-1].get("stopped"):
                stopped_at = name
    _log_stale(client, stale0, "the billing probes")
    for r in rows:
        print("  " + json.dumps(r, default=str))
    return rows


def _slices(pull: dict) -> dict[str, frozenset[str]]:
    """A `require_seasons` pull's named slices (slice name -> season labels); empty when it is just `true`."""
    need = pull.get("require_seasons")
    return ({name: frozenset(s.strip() for s in str(seasons).split(",")) for name, seasons in need.items()}
            if isinstance(need, dict) else {})


def _slice_commands(pid: str, pull: dict, stage: str = "full") -> list[str]:
    lines = [f"  {name}: uv run markets odds5m {stage} --pull {pid} --seasons {','.join(sorted(s))} --confirm "
             "--max-credits N" for name, s in _slices(pull).items()]
    return (lines or ["  add --seasons with the slice's season labels, e.g. --seasons 2025"]) + [
        "Buy only a slice the plan allows now: the day-one steps and the gated table in docs/ODDS5M_DAY_ONE.md say "
        "which. Run it first without --confirm to see its cost, and set N a little above it."]


def _slice_refusal(cfg: dict, cache: RawCache, pid: str, schedules: dict, now, args, others=(),
                   stage: str = "full") -> str:
    """Why `full` or `week` refuses a `require_seasons` pull without --seasons, with the command for each named
    slice. `require_seasons` is true, or a mapping of slice name to season labels (F3: F3a 2025, F3b the rest)."""
    week_of = args.week_of if stage == "week" else None
    todo = [c for c in plan_calls(cfg, pid, schedules, now=now, sports=args.sports, week_of=week_of)
            if cache.lookup(c.cache_sport, c.source, c.key) is None]
    what = "every season at once" if stage == "full" else "a week from any of its seasons"
    lines = [f"{pid}: refused. `{stage} --pull {pid}` needs --seasons. This pull is bought one season slice at a time "
             f"(require_seasons in config/odds5m.yaml); without --seasons this run would fetch {what}: "
             f"{len(todo):,} calls, at most {sum(c.expected for c in todo):,} credits. Nothing was fetched."]
    if others:
        lines.append(f"Run the other pulls by name, without --seasons ({', '.join(others)}), and {pid} on its own, "
                     "one slice at a time:")
    return "\n".join(lines + _slice_commands(pid, cfg["pulls"][pid], stage))


def _check_seasons(cfg: dict, cache: RawCache, ids: list[str], schedules: dict, now, args, stage: str = "full") -> None:
    """A `require_seasons` pull (F3) is bought one declared slice at a time, by `full` and by `week` alike, so a week
    run can't reach a gated slice either. `full` also buys every other pull whole, so it refuses --seasons for them;
    `week` lets --seasons pick which season's week the other pulls sample. Raises SystemExit, before anything is
    fetched and in the dry run too, when the run could buy anything else."""
    sliced = [pid for pid in ids if cfg["pulls"][pid].get("require_seasons")]
    whole = [pid for pid in ids if pid not in sliced]
    if not args.seasons:
        if sliced:
            raise SystemExit(_slice_refusal(cfg, cache, sliced[0], schedules, now, args, others=whole, stage=stage))
        return
    if whole and stage == "full":
        raise SystemExit(f"refused: --seasons would also narrow {', '.join(whole)}, which the plan buys whole, not by "
                         "season. Nothing was fetched. Run "
                         + (f"them without --seasons, and {', '.join(sliced)} on its own." if sliced else
                            "them without --seasons."))
    want = frozenset(args.seasons)
    for pid in sliced:
        slices = _slices(cfg["pulls"][pid])
        if slices and want not in slices.values():
            raise SystemExit("\n".join([
                f"{pid}: refused. --seasons {','.join(sorted(want))} is not one of its slices, so it could buy more "
                f"or other than the plan says. Nothing was fetched. Its slices:"]
                + _slice_commands(pid, cfg["pulls"][pid], stage)))


def stage_pull(cfg, cache, args, *, week: bool, now=None, session=None) -> list[dict]:
    schedules = load_schedules(cfg, cache.raw_dir)
    if not schedules:
        raise SystemExit("no schedules: run `markets odds5m probe --confirm --max-credits N` first")
    if not week and args.pull in (None, "", "all"):
        raise SystemExit("full: name the pulls (--pull F1,F2) or a group from config/odds5m.yaml "
                         f"({', '.join(cfg.get('groups', {}))}); `all` would run every pull in the config")
    ids = _pulls(cfg, args.pull)
    _check_seasons(cfg, cache, ids, schedules, now, args, stage="week" if week else "full")
    for pid in ids if args.seasons else ():
        labels = {g["season"] for s in cfg["pulls"][pid]["sports"] for g in schedules.get(s, [])}
        if missing := sorted(set(args.seasons) - labels):
            print(f"warning: {pid}: no game in the saved schedules is in season {', '.join(missing)} (--seasons takes "
                  "the season labels in config/odds5m.yaml)")
    plans = {pid: plan_calls(cfg, pid, schedules, now=now, week_of=args.week_of if week else None,
                             sports=args.sports, seasons=args.seasons) for pid in ids}
    retry_404 = getattr(args, "retry_404", False)
    if not args.confirm:
        reader = BulkClient(cache, max_credits=0)
        for pid, calls in plans.items():
            todo = _todo(reader, calls, retry_404)
            again = f" ({sum(reader.is_cached(c) for c in todo):,} of them cached 404s asked again)" if retry_404 else ""
            print(f"{pid:3} {len(calls):,} calls, {len(todo):,} to fetch{again}, at most "
                  f"{sum(c.expected for c in todo):,} credits")
        print("dry run: add --confirm --max-credits N to run it")
        return []
    client = _client(cache, args, session)
    out = []
    for pid, calls in plans.items():
        res = run_calls(client, calls, f"{pid}{' (one week per sport)' if week else ''}", retry_404=retry_404)
        if res["interrupted"]:                  # Ctrl-C: stop now, without reading the cache for the coverage line
            out.append({"pull": pid, **res})
            break
        cov = coverage(cfg, calls, cache)
        print(f"  coverage: {json.dumps(cov, default=str)}")
        out.append({"pull": pid, **res, "coverage": cov})
        if res["stopped"]:
            break
    return out


def stage_check(cfg, cache, args, now=None) -> list[dict]:
    schedules = load_schedules(cfg, cache.raw_dir)
    out = []
    for pid in _pulls(cfg, args.pull):
        cov = coverage(cfg, plan_calls(cfg, pid, schedules, now=now, sports=args.sports, seasons=args.seasons), cache)
        print(f"{pid}: {json.dumps(cov, default=str)}")
        out.append({"pull": pid, **cov})
    return out


def _list_arg(value) -> list[str] | None:
    """A comma-separated argument as a list; blank entries (a trailing comma, ",,") are dropped. None when empty."""
    items = [s for s in (x.strip() for x in str(value).split(",")) if s] if value else []
    return items or None


def main(args) -> int:
    """Runs one stage; returns the exit status: 0 when it finished (a dry run included), 1 when it stopped. Every
    stop, a Ctrl-C or a full disk included, ends with a STOPPED line, never a traceback. A refusal before anything
    is spent raises SystemExit with its message, which also exits with status 1."""
    global _ACTIVE
    _ACTIVE = None
    cfg, cache = load_config(), RawCache()
    args.sports = _list_arg(args.sports)
    args.seasons = _list_arg(getattr(args, "seasons", None))
    if getattr(args, "retry_404", False) and args.stage not in ("week", "full"):
        raise SystemExit(f"--retry-404 works with week and full, not {args.stage}")
    if getattr(args, "alarm_margin", None) is not None and args.stage not in ("probe", "week", "full"):
        raise SystemExit(f"--alarm-margin works with probe, week and full, not {args.stage}")
    if args.stage == "headers":
        from .headers import stage_headers
        return stage_headers(cache.raw_dir / "_manifest" / "oddsapi_manifest.csv", args.pull, getattr(args, "per_call", 30))
    try:
        if args.stage == "probe":
            return 1 if stage_probe(cfg, cache, args).get("stopped") else 0
        if args.stage == "balance":
            stage_balance(cfg, cache, args)
        elif args.stage == "plan":
            stage_plan(cfg, cache, args)
        elif args.stage in ("week", "full"):
            return 1 if any(r["stopped"] for r in stage_pull(cfg, cache, args, week=args.stage == "week")) else 0
        else:
            stage_check(cfg, cache, args)
        return 0
    except KeyboardInterrupt:
        print(f"  STOPPED: {INTERRUPTED} (Ctrl-C). A rerun resumes from the cache.", flush=True)
    except OSError as e:
        print(f"  STOPPED: a file could not be read or written ({e.strerror or e}): is the disk full? {DISK_HELP}",
              flush=True)
    except Stop as e:
        print(f"  STOPPED: {scrub(e)}", flush=True)
    if _ACTIVE is not None:
        print(summary_line(_ACTIVE, True), flush=True)
    return 1
