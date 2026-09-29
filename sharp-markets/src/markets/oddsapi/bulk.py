"""Bulk historical Odds API puller for the 5M-credit month. GET only. Config: config/odds5m.yaml.

Stages (`uv run markets odds5m <stage>`; the hub runs them on the Mac, docs/ODDS5M_DAY_ONE.md):
  probe  P0: verify the key (free), sweep historical /events for every sport (1 credit per call,
         0 when empty) into exact schedules, then seven single-call billing and coverage probes
  balance  free: the key check alone, to read the credits left (after a stop, before a rerun)
  plan   free: calls and upper-bound credits per pull from those schedules, cached vs to fetch
  week   one week per sport for the chosen pulls, to check coverage before the full spend
  full   the chosen pulls in full; name them, or a group from the config (day_one, gated, march)
  check  free: what the cache holds for a pull (books, markets, snapshot lag, empty snapshots)

Pulls are grouped in the config (`groups:`) by when the plan lets them run: day_one on Oct 1, gated
once a written gate has passed, march for the 2027 month. `--pull day_one` names a group; `full`
refuses `all`, so nothing runs every pull in the config by accident.

A pull with `games_from:` (the heat closes, HB1 and HS1) fetches only the games listed in that CSV,
which `markets weather qualifying` writes from the pre-registered triggers before any odds are bought.

Safety. Nothing is fetched without --confirm. Each run has a --max-credits budget, checked against
each call's upper-bound cost before the call and before every retry, and a --floor on the account's
remaining credits (the live-use reserve). What a run has cost is the largest of what the responses report,
what the documentation says they cost (worked out from what came back), and how far the balance has
fallen, so a call billed twice (a retried timeout) or reported as free still counts (BulkClient).
A run starts only when the free /sports check returns a readable balance at or above the floor. The
billing headers fail closed: a billed response whose `x-requests-last` can't be read counts its upper
bound and stops the run, one that reports less than its documented cost stops it, and an unreadable
balance stops it while a floor is set. The circuit breaker stops the run when a call bills more than its
upper bound (`x-requests-last`), when the balance falls by more than the reported cost plus the upper
bound on three calls in a row, when the key is rejected or the quota runs out, after repeated errors,
when the network fails past the retries, or when a billed response can't be kept (a body that isn't
JSON, a full disk). Every stop, Ctrl-C included, ends the run with a STOPPED line and its summary, never a
traceback, and `markets` exits with status 1 (0 only when the run is done); error text, error bodies and
log lines never hold the key (markets.http.scrub).
Every answered request is logged to data/raw/_manifest/oddsapi_manifest.csv: requested vs returned
snapshot time, credits billed (blank when unreadable: the upper bound was counted), credits remaining,
a SHA-256 of the body, the cache key, sealed flag.

Season slices: a pull with `require_seasons:` in the config (F3) is bought one declared slice at a time:
`full` and `week` refuse it, dry run included, unless --seasons names exactly one slice (blank entries, as
from a trailing comma, are dropped first), and `full` refuses --seasons for every other pull (they are
bought whole).

A probe saves a sport's schedule only when that sport's sweep finished; `plan` lists every pull, and one
that waits for its game list (HB1, HS1) counts as 0 calls until `markets weather qualifying` has run.

Cache first: responses land in data/raw/{sport_key}/oddsapi/{hist_events,hist_odds,hist_event_odds}/
before use, so reruns and interrupted runs resume for free.

Sealed holdout: seasons marked sealed in the config are pulled but load_rows() leaves them out
unless include_sealed=True, which only a pre-registered test may pass. A `cache_as` pull writes into
another pipeline's cache, which `markets build` reads directly, so plan_calls refuses to plan a sealed
call for one (and `markets build` leaves sealed games out on its own as well).
"""
from __future__ import annotations

import csv
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

from ..cache import Fetched, RawCache, body_json, cache_key, read_record
from ..http import RateLimiter, http_get, new_session, scrub
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


class Stop(RuntimeError):
    """The run has to stop: budget, floor, or circuit breaker."""


class BudgetExceeded(Stop):
    pass


class CircuitBreaker(Stop):
    pass


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
    """What the API's documentation says one response costs, worked out from the call and what came back, never
    from a constant (the v4 docs, as _account quotes them). Historical /events: 1 when it lists any event.
    Historical event odds: 10 x the distinct markets in the body x regions. Featured historical odds: 10 x markets
    x regions, where the docs count the markets asked for; this counts the markets that came back, which is never
    more, so a snapshot in which some market isn't quoted can't make an honest bill look short. Only markets the
    call asked for count: an exchange's lay prices come back as their own key (`h2h_lay`), billed with `h2h`.
    Regions are one per 10 books in the call. An empty result, a 404 or an error status: 0, as the API documents.
    `call.expected` stays the upper bound; this is the floor under what a response with data is counted at, and
    it is never above the upper bound."""
    if status != 200:
        return 0
    try:
        b = json.loads(body) if body else None
    except ValueError:
        return 0
    data = b.get("data") if isinstance(b, dict) else None
    if _kind(call) == "events":
        return 1 if data else 0
    p = dict(call.params)
    books = [x for x in p.get("bookmakers", "").split(",") if x]
    asked = {m for m in p.get("markets", "").split(",") if m}
    return 10 * len(markets_returned(data) & asked) * regions(books)


def _envelope(body: str) -> dict:
    try:
        b = json.loads(body) if body else None
    except ValueError:
        b = None
    if not isinstance(b, dict):
        return {"n": len(b) if isinstance(b, list) else 0}
    data = b.get("data")
    return {"timestamp": b.get("timestamp") or "", "previous_timestamp": b.get("previous_timestamp") or "",
            "next_timestamp": b.get("next_timestamp") or "",
            "n": 1 if isinstance(data, dict) else len(data or [])}


def _cost(value) -> int | None:
    """`x-requests-last` as whole credits, a fraction rounded up; None when it is missing, not a number,
    negative or not finite. None means "unknown", never zero."""
    try:
        x = float(value)
    except (TypeError, ValueError):
        return None
    return math.ceil(x) if math.isfinite(x) and x >= 0 else None


def _balance(value) -> int | None:
    """`x-requests-remaining` as whole credits, a fraction rounded down; None when it is missing, not a number,
    negative or not finite."""
    try:
        x = float(value)
    except (TypeError, ValueError):
        return None
    return int(x) if math.isfinite(x) and x >= 0 else None


def _is_json(body: str) -> bool:
    try:
        return isinstance(json.loads(body), (dict, list))
    except ValueError:
        return False


def _n(x) -> str:
    return "unknown" if x is None else f"{x:,}"


def _credits(n: int) -> str:
    return f"{n:,} credit{'' if n == 1 else 's'}"


class _Unusable(Exception):
    """A billed HTTP 200 whose body can't be used (not JSON). Raised inside the cache's fetch, so it isn't cached."""


OVERBILLED_IN_A_ROW = 3         # calls in a row whose balance fall exceeds the reported cost by more than the upper bound
DISK_HELP = "Free some space (docs/ODDS5M_DAY_ONE.md, Before buying, step 2), then rerun."


class BulkClient:
    """The one client that spends Odds API credits (the bulk puller, and odds-pull through OddsApiClient). How it
    counts what a run has cost (`counted`), so that the run budget and the floor hold even when a header is wrong or
    a call is billed more than once:

    - each answered call counts the larger of its `x-requests-last` (rounded up) and its documented cost worked out
      from what came back (documented_cost), or its upper bound when `x-requests-last` can't be read. A response
      with data that reports less than its documented cost stops the run: the billing can't be trusted;
    - the balance (`x-requests-remaining`) is tracked as the lower of what the API reports and the previous
      balance less what was counted, so a balance that rises or makes no sense is never believed;
    - the run's cost is the larger of the sum of those counts and how far the balance has fallen since the key
      check. A call that is billed twice (a retried timeout or error) or reports 0 while the balance drops is
      caught this way. Other uses of the key during the run (the alerts, the collectors) count too, which errs
      toward stopping early;
    - an attempt that got no usable answer (a timeout, a network error, a retried error status, Ctrl-C while a call
      was out) may have been billed, so its upper bound is counted on top. That count is cleared only by as much
      as the balance has fallen beyond what the responses were counted at. An attempt the balance never shows
      stays counted until the run ends: no balance reading can prove it is current (one that arrives two answers
      late, or never moves, looks like a live one), so a bill that hasn't shown yet can't be told from no bill.
      That errs toward stopping early; the next run's key check reads the true balance. A retry is checked against
      the budget and the floor like a new call;
    - when, on three calls in a row, the balance falls by more than the call's reported cost plus its upper bound,
      the run stops: the account is being charged more than the API reports.
    """
    cache_statuses: tuple[int, ...] = (200, 404)     # a 404 (event not found) is cached like an empty response

    def __init__(self, cache: RawCache, *, max_credits: int, floor: int = 0, rate_per_sec: float = 8.0,
                 session=None, api_key: str | None = None, max_retries: int = 6, max_errors: int = 5):
        self.cache, self.max_credits, self.floor = cache, max_credits, floor
        self.session = session or new_session()
        self.limiter = RateLimiter(rate_per_sec)
        self.api_key, self.max_retries, self.max_errors = api_key, max_retries, max_errors
        self.spent = self.fetched = self.errors_in_row = 0
        self._pending: list[int] = []          # upper bound of each attempt with no answer, less what the balance showed
        self._fresh = 0                        # upper bounds of such attempts since the last balance reading
        self.explained = 0                     # the most the balance has fallen beyond what responses were counted at
        self.balance_drop = 0                  # the most the balance has fallen below the start of the run
        self.overbilled_in_row = 0
        self.start_remaining: int | None = None
        self.remaining: int | None = None
        self.last_reading: int | None = None   # the last readable x-requests-remaining, as reported
        self.not_saved: dict[str, int] = {}    # cache key -> HTTP status of a call whose last answer was an error
        self.manifest = Path(cache.raw_dir) / "_manifest" / "oddsapi_manifest.csv"

    def _base(self) -> str:
        return BASE_URL

    @property
    def unanswered(self) -> int:
        """Upper bounds of attempts that got no usable answer and that no balance reading has explained yet."""
        return sum(self._pending)

    @property
    def counted(self) -> int:
        """What this run has cost, as far as it can tell (see the class docstring). Never goes down."""
        return max(self.spent, self.balance_drop) + self.unanswered

    def _no_answer(self, call: Call) -> None:
        """An attempt at `call` got no usable answer; it may have been billed."""
        self._pending.append(call.expected)
        self._fresh += call.expected

    def in_flight(self, call: Call) -> None:
        """The run was interrupted (Ctrl-C) while `call` may have been out: count it like an attempt with no answer."""
        if not self.is_cached(call):
            self._no_answer(call)

    def _see_balance(self, left: int, counted: int, reported: int, call: Call) -> bool:
        """A readable `x-requests-remaining` after a call that counted `counted` (and reported `reported`). Returns
        True when the run must stop because the account is being charged more than the API reports."""
        if self.start_remaining is None:             # no key check ran (library use): start from the first reading
            self.start_remaining = left + counted
        prev = self.remaining
        if prev is None:
            self.remaining = left
        else:
            if left > prev:
                log.warning("the reported balance rose from %s to %s during the run; keeping the lower figure",
                            prev, left)
            self.remaining = min(left, prev - counted)
            if prev - self.remaining > counted:
                log.warning("the balance fell by %s, more than the %s this call was counted at: an attempt that got no "
                            "answer was billed too, or another use of the key spent in the meantime. The run counts "
                            "the larger figure.", prev - self.remaining, counted)
        self.balance_drop = max(self.balance_drop, self.start_remaining - self.remaining)
        # attempts with no answer: cleared only by as much as the balance has fallen beyond the counted costs. One the
        # balance never shows stays counted for the rest of the run: no reading can prove that it is current (a
        # balance two answers late, or one that never moves, looks like a live one), so an attempt that was never
        # billed can't be told from one whose bill hasn't shown yet. The next run's key check reads the true balance.
        beyond = (self.start_remaining - left) - self.spent
        if beyond > self.explained:
            clear, self.explained = beyond - self.explained, beyond
            for i, amount in enumerate(self._pending):
                take = min(amount, clear)
                self._pending[i], clear = amount - take, clear - take
            self._pending = [a for a in self._pending if a > 0]
        # overbilling that shows only in the balance
        over = False
        if self.last_reading is not None:
            excess = (self.last_reading - left) - reported - self._fresh
            self.overbilled_in_row = self.overbilled_in_row + 1 if excess > call.expected else 0
            over = self.overbilled_in_row >= OVERBILLED_IN_A_ROW
        self.last_reading, self._fresh = left, 0
        return over

    def _precheck(self, call: Call, what: str = "the next call") -> None:
        """Budget and floor, before a call or a retry. Raises BudgetExceeded."""
        maybe = (f" ({self.unanswered:,} of it for attempts that got no answer and may have been billed)"
                 if self.unanswered else "")
        if self.counted + call.expected > self.max_credits:
            raise BudgetExceeded(f"{what} could cost {call.expected}; {self.counted:,} of the {self.max_credits:,}-credit "
                                 f"run budget is counted{maybe}")
        if self.remaining is None:
            if self.floor > 0:
                raise BudgetExceeded(f"the account balance is unknown, so the floor of {self.floor:,} can't be "
                                     "checked. Nothing more was fetched; a new run reads the balance before it starts")
        elif self.remaining - self.unanswered - call.expected < self.floor:
            raise BudgetExceeded(f"{self.remaining - self.unanswered:,} credits remain at most{maybe}; {what} could "
                                 f"cost {call.expected}, and the floor is {self.floor:,}")

    def _retrying(self, call: Call, why: str) -> None:
        """http_get is about to retry `call` after `why`. The attempt may have been billed: count its upper bound,
        and check the budget and floor before asking again."""
        self._no_answer(call)
        self._precheck(call, f"retrying {call.path} at {iso(call.at)} after {why} (the attempt may have been billed)")

    def _get(self, url: str, params: dict, call: Call | None = None):
        """One GET with the key added. For a paid `call`, each retry is budget-checked first (`_retrying`), and a
        network failure that outlasts the retries counts the last attempt's upper bound and stops the run. Error
        text never holds the key (markets.http.scrub)."""
        try:
            return http_get(self.session, url, {**params, "apiKey": self.api_key or env("ODDS_API_KEY")},
                            self.limiter, max_retries=self.max_retries,
                            before_retry=None if call is None else (lambda why: self._retrying(call, why)))
        except requests.RequestException as e:
            maybe = ""
            if call is not None:
                self._no_answer(call)
                maybe = (f" It may still have been billed, so the run counts {self.unanswered:,} credits for the "
                         "attempts that got no answer until a balance reading shows what they cost; the rerun's key "
                         "check reads the true balance.")
            raise CircuitBreaker(
                f"no answer from the Odds API after the retries ({type(e).__name__}: {scrub(e)}). Nothing was cached "
                f"for this call, so a rerun asks again.{maybe}") from None

    def account(self) -> dict:
        """GET /v4/sports: free. Checks the key and reads the credits remaining. Never cached.

        Refuses to start the run (raises Stop, before any paid call) when the key is rejected, the check
        doesn't return HTTP 200, the balance (`x-requests-remaining`) is missing or unreadable, the balance
        is already below the floor, or its manifest row can't be written (a full disk)."""
        r = self._get(self._base() + "/sports", {})
        h = {k.lower(): v for k, v in r.headers.items()}
        self.remaining = self.start_remaining = self.last_reading = _balance(h.get("x-requests-remaining"))
        try:
            self._log({"pull": "account", "path": "/sports", "http_status": r.status_code,
                       "credits_last": h.get("x-requests-last", ""), "remaining": self.remaining,
                       "sha256": hashlib.sha256(r.text.encode()).hexdigest()})
        except OSError as e:
            raise CircuitBreaker(f"the key check's manifest row could not be written ({e.strerror or e}): is the disk "
                                 f"full? The key check is free, so nothing was spent. {DISK_HELP}") from None
        if r.status_code == 401:
            raise CircuitBreaker("the Odds API rejected the key (401): check ODDS_API_KEY in sharp-markets/.env")
        if r.status_code != 200:
            raise CircuitBreaker(f"the free key check (/v4/sports) returned HTTP {r.status_code}: "
                                 f"{scrub(r.text)[:200]}. Try again in a few minutes.")
        if self.remaining is None:
            raise CircuitBreaker(f"the free key check did not return a readable balance (x-requests-remaining is "
                                 f"{h.get('x-requests-remaining')!r}), so the floor and the budget can't be checked")
        if self.remaining < self.floor:
            raise BudgetExceeded(f"the account has {self.remaining:,} credits left, already below the floor of "
                                 f"{self.floor:,}")
        return {"status": r.status_code, "remaining": self.remaining, "used": h.get("x-requests-used")}

    def is_cached(self, call: Call) -> bool:
        return self.cache.lookup(call.cache_sport, call.source, call.key) is not None

    def cached_record(self, call: Call) -> dict | None:
        p = self.cache.lookup(call.cache_sport, call.source, call.key)
        return read_record(p) if p is not None else None

    def fetch(self, call: Call) -> dict:
        """The stored record for this call (cache first). Raises Stop before or after a call that must end the run.

        A billed response that can't be kept stops the run after it is counted and logged: a 200 whose body isn't
        JSON (not cached, so a rerun asks again) and a response the disk can't store (a full disk)."""
        if not self.is_cached(call):
            self._precheck(call)
        sent: list[Fetched] = []

        def fetch() -> Fetched:
            r = self._get(call.url, dict(call.params), call)
            # an error body is kept only with the key blanked, in case a server or proxy echoes the request
            f = Fetched(r.status_code, {k.lower(): v for k, v in r.headers.items()},
                        r.text if r.status_code == 200 else scrub(r.text))
            sent.append(f)
            if f.status == 200 and not _is_json(f.body):
                raise _Unusable
            return f

        try:
            rec = self.cache.get_or_fetch(sport=call.cache_sport, source=call.source,
                                          data_date=call.at.date().isoformat(), url=call.url, params=dict(call.params),
                                          fetch=fetch, cache_statuses=self.cache_statuses)
        except _Unusable:
            self._account(call, self._record(call, sent[-1]),
                          problem=f"the API answered HTTP 200 with a body that is not JSON "
                                  f"({scrub(sent[-1].body)[:120]!r}). It was not cached, so a rerun asks again.")
            raise                        # not reached: _account raises CircuitBreaker when given a problem
        except OSError as e:
            if not sent:
                raise CircuitBreaker(f"the cache could not be read ({e.strerror or e}). Nothing was fetched.") from None
            self._account(call, self._record(call, sent[-1]),
                          problem=f"the response could not be saved ({e.strerror or e}): is the disk full? It was "
                                  f"billed and is counted, but not cached, so a rerun buys it again. {DISK_HELP}")
            raise
        if sent:
            if rec["http_status"] in self.cache_statuses:
                self.not_saved.pop(call.key, None)
            else:                        # an error answer: not cached, so a rerun asks again
                self.not_saved[call.key] = rec["http_status"]
            self._account(call, rec)
        return rec

    @staticmethod
    def _record(call: Call, f: Fetched) -> dict:
        """The fields _account reads, for a response the cache didn't store."""
        return {"headers_json": json.dumps({k: v for k, v in f.headers.items() if k.startswith("x-requests-")}),
                "body": f.body, "http_status": f.status, "cache_key": call.key}

    def _account(self, call: Call, rec: dict, problem: str | None = None) -> None:
        """Count what one real request cost, log it, and stop the run when it must end. `problem` (a response
        that couldn't be kept) stops the run once the call is counted and logged.

        What the API bills (its v4 docs, read Sep 29, 2026): a call is billed by the data it returns. Historical
        odds cost 10 x markets x regions, historical /events 1 (nothing when no events are found), event odds
        10 x markets returned x regions, and "responses with empty data do not count". The docs name no charge
        for an error status, and don't say whether error responses carry the usage headers. So:

        - HTTP 200 is billed. It counts the larger of `x-requests-last` and the documented cost of what came back
          (documented_cost). When `x-requests-last` is below that documented cost, the documented cost is counted
          and the run stops: the billing can't be trusted. When `x-requests-last` is missing or not a number,
          the call's upper bound (call.expected) is counted as spent and the run stops: the billing could not be
          read. The response is already cached, so nothing is lost. When `x-requests-remaining` is missing or not
          a number, the balance becomes unknown, and the run stops if a floor is set.
        - HTTP 404 (the event is not found; cached like an empty response) and error statuses return no data,
          so by the docs they cost nothing. Their headers are still used when readable, and the overbilling
          checks apply to them. When `x-requests-last` is unreadable, the upper bound is counted anyway, so
          the run budget errs toward stopping early, but the run goes on: stopping at every 404 would stall F2
          and F3 over responses the docs call free. Errors still stop the run after max_errors in a row, and
          401 and 429 stop it at once. When `x-requests-remaining` is unreadable, the known balance is lowered
          by what was counted, so the floor keeps being checked.
        - Whatever a call reports, the run also counts how far the balance fell (class docstring), so a retried
          call billed twice, or a 0 reported while the balance drops, still counts toward the budget, and three
          calls in a row whose balance fall exceeds the reported cost by more than the upper bound stop the run.
        """
        h = json.loads(rec["headers_json"] or "{}")
        body, status = rec["body"] or "", rec["http_status"]
        raw_last, raw_left = h.get("x-requests-last"), h.get("x-requests-remaining")
        last, left = _cost(raw_last), _balance(raw_left)
        documented = documented_cost(call, status, body)
        counted = call.expected if last is None else max(last, documented)
        self.spent += counted
        self.fetched += 1
        overbilled = False
        if left is not None:
            overbilled = self._see_balance(left, counted, counted if last is None else last, call)
        elif status == 200:
            self.remaining = None
        elif self.remaining is not None:
            self.remaining -= counted
            if self.start_remaining is not None:
                self.balance_drop = max(self.balance_drop, self.start_remaining - self.remaining)
        env_, p = _envelope(body), dict(call.params)
        where = f"{call.path} at {iso(call.at)}"
        try:
            self._log({"pull": call.pull, "sport": call.sport, "source": call.source, "path": call.path,
                       "event_id": call.event_id, "requested_ts": iso(call.at),
                       "returned_ts": env_.get("timestamp", ""), "previous_ts": env_.get("previous_timestamp", ""),
                       "next_ts": env_.get("next_timestamp", ""), "markets": p.get("markets", ""),
                       "books": p.get("bookmakers", ""), "n_events": env_["n"], "expected_credits": call.expected,
                       "credits_last": last, "remaining": self.remaining, "http_status": status,
                       "sha256": hashlib.sha256(body.encode()).hexdigest(), "cache_key": rec["cache_key"],
                       "sealed": call.sealed})
        except OSError as e:
            problem = (f"{problem} The manifest row could not be written either." if problem else
                       f"the response is cached, but its manifest row could not be written ({e.strerror or e}): is "
                       f"the disk full? {DISK_HELP}")
        if problem:
            billed = _credits(counted) if last is not None else f"its upper bound, {_credits(call.expected)}"
            raise CircuitBreaker(f"{where}: {problem} It counted {billed} (x-requests-last {raw_last!r})"
                                 + (f", more than its upper bound of {call.expected}" if last and last > call.expected
                                    else "") + ".")
        err = scrub(body)[:200]          # error bodies are printed and logged only with any key blanked
        if status == 401:
            raise CircuitBreaker("the Odds API rejected the key (401)")
        if status == 429:
            raise CircuitBreaker(f"HTTP 429 after retries (quota used up or rate limited): {err}")
        if last is not None and last > call.expected:
            raise CircuitBreaker(f"{where} billed {last} credits; it should cost at most "
                                 f"{call.expected}. Stopped: check the billing before going on.")
        if status == 200 and last is None:
            raise CircuitBreaker(f"the billing could not be read: {where} came back with x-requests-last "
                                 f"{raw_last!r}, so its upper bound, {call.expected}, was counted as spent. The "
                                 "response is cached. Check the billing before going on.")
        if last is not None and last < documented:
            raise CircuitBreaker(f"the billing cannot be trusted: {where} reported {last} credits (x-requests-last "
                                 f"{raw_last!r}), less than the {documented} the API's documentation charges for what "
                                 f"came back, so {documented} was counted. The response is cached. Check the billing "
                                 "before going on.")
        if overbilled:
            raise CircuitBreaker(f"the account is being charged more than the API reports: on {self.overbilled_in_row} "
                                 "calls in a row the balance fell by more than the call's reported cost plus its upper "
                                 f"bound (the last: {where}, reported {last}, upper bound {call.expected}). The run "
                                 "counts what the balance shows. Check the billing before going on.")
        if status == 200 and left is None and self.floor > 0:
            raise CircuitBreaker(f"the balance could not be read: {where} came back with x-requests-remaining "
                                 f"{raw_left!r}, so the floor of {self.floor:,} can't be checked. The response is "
                                 "cached; a new run reads the balance before it starts.")
        if last is None:
            log.warning("%s -> HTTP %s without a readable x-requests-last (%r); counted its upper bound %s",
                        where, status, raw_last, call.expected)
        if status in (200, 404):
            self.errors_in_row = 0
            return
        self.errors_in_row += 1
        log.warning("%s at %s -> HTTP %s: %s", call.path, iso(call.at), status, err)
        if self.errors_in_row >= self.max_errors:
            raise CircuitBreaker(f"{self.errors_in_row} errors in a row; the last was HTTP {status}: {err}")

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
                 errors: int = 0) -> str:
    """The line every run ends with: this pull's calls fetched and credits, the run's credits, and the balance, and
    how many calls got an error answer (not saved, so a rerun asks for them again)."""
    fetched = client.fetched if fetched is None else fetched
    credits = client.counted if credits is None else credits
    errs = f" ({errors:,} answered with an error and not saved; a rerun asks again)" if errors else ""
    return (f"  {'stopped' if stopped else 'done'}: {fetched:,} fetched{errs}, credits {credits:,} "
            f"(this run {client.counted:,}), remaining {_n(client.remaining)}")


def run_calls(client: BulkClient, calls: list[Call], label: str = "") -> dict:
    """Fetch the calls not yet cached, in order. Every way a run can end (done, budget, floor, circuit breaker,
    unreadable billing, network, a full disk, Ctrl-C, even a bug) ends here with a STOPPED line when it stopped,
    then one summary line with this pull's own counts. "credits" is what BulkClient.counted rose by."""
    todo = [c for c in calls if not client.is_cached(c)]
    print(f"{label}: {len(calls):,} calls, {len(calls) - len(todo):,} cached, {len(todo):,} to fetch, "
          f"at most {sum(c.expected for c in todo):,} credits", flush=True)
    fetched0, counted0 = client.fetched, client.counted
    stopped, interrupted = None, False
    for i, c in enumerate(todo, 1):
        try:
            client.fetch(c)
        except Stop as e:
            stopped = str(e)
        except KeyboardInterrupt:
            client.in_flight(c)
            stopped, interrupted = (f"{INTERRUPTED} (Ctrl-C). The call that was out may have been billed, so it is "
                                    f"counted at its upper bound, {_credits(c.expected)}. A rerun resumes from the "
                                    "cache and may buy that one call again."), True
        except OSError as e:
            stopped = (f"a file could not be read or written ({e.strerror or e}): is the disk full? The call that was "
                       f"out is not cached, so a rerun asks again. {DISK_HELP}")
        except Exception as e:          # noqa: BLE001 - a bug still ends the run with its summary, key blanked
            stopped = f"unexpected error, probably a bug; tell the hub before rerunning ({type(e).__name__}: {scrub(e)})"
            log.error("the run stopped on an unexpected error:\n%s", scrub("".join(traceback.format_exception(e))))
        if stopped:
            print(f"  STOPPED: {stopped}", flush=True)
            break
        if i % 500 == 0:
            print(f"  {i:,}/{len(todo):,}  credits this run {client.counted:,}  remaining {_n(client.remaining)}",
                  flush=True)
    fetched, spent = client.fetched - fetched0, client.counted - counted0
    errors = sum(c.key in client.not_saved for c in todo)
    print(summary_line(client, stopped, fetched, spent, errors), flush=True)
    return {"calls": len(calls), "todo": len(todo), "fetched": fetched, "spent": spent,
            "run_fetched": client.fetched, "run_spent": client.counted, "remaining": client.remaining,
            "stopped": stopped, "interrupted": interrupted, "errors": errors}


# ---------------------------------------------------------------- reading the cache
def cached_bodies(client: BulkClient, calls: list[Call]):
    for c in calls:
        rec = client.cached_record(c)
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
    """What the cache holds for these calls: rows by book and market, empty snapshots, snapshot lag."""
    client = BulkClient(cache, max_credits=0)
    books, markets, lags, games = Counter(), Counter(), [], set()
    n = empty = 0
    for c, _, body in cached_bodies(client, calls):
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
    return {"calls": len(calls), "cached_ok": n, "empty": empty, "games": len(games), "books": dict(books.most_common()),
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
                             session=session)
    try:
        info = c.account()
    except Stop as e:
        raise SystemExit(f"STOPPED before the first paid call, nothing spent: {e}") from None
    print(f"key ok: HTTP {info['status']}, {info['remaining']:,} credits remaining, {info['used']} used; "
          f"floor {c.floor:,}")
    return c


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
        raise SystemExit(f"STOPPED: {e}") from None
    print(f"key ok: HTTP {info['status']}, {info['remaining']:,} credits remaining, {info['used']} used; "
          f"floor {c.floor:,}. Nothing was spent.")
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
    res = run_calls(client, [c for v in sweeps.values() for c in v], "P0 sweeps")
    # A sport's schedule is saved only when its sweep finished: every one of its /events calls is cached. A
    # stopped or partial sweep leaves the earlier schedule file as it was, and the sport is listed as incomplete.
    counts, incomplete, refused = {}, {}, {}
    for s, calls in sweeps.items():
        missing = [c for c in calls if not client.is_cached(c)]
        if res["interrupted"] or missing:
            incomplete[s] = missing
            refused[s] = [(c, client.not_saved[c.key]) for c in missing if c.key in client.not_saved]
            continue
        games = build_schedule(cfg, s, [b for _, _, b in cached_bodies(client, calls)])
        save_schedule(cache.raw_dir, s, games)
        counts[s] = Counter(g["season"] or "outside windows" for g in games)
        print(f"  {s:36} {len(games):6,} games  " + "  ".join(f"{k}: {v}" for k, v in sorted(counts[s].items())))
    if incomplete:
        print(f"  incomplete, schedule not saved (any earlier schedule file is kept): {', '.join(incomplete)}")
    # The billing probes need only the sweeps that finished, so they run unless the sweeps themselves stopped (a
    # sport whose sweep got an error answer doesn't hold them up).
    stopped = res["stopped"]
    probes = [] if stopped else billing_probes(cfg, client, load_schedules(cfg, cache.raw_dir), now)
    stopped = stopped or next((p["result"] for p in probes if p.get("stopped")), None)
    errors = False                       # the sweeps ran to the end, but some got an error answer
    if incomplete and not stopped:
        errors = any(refused.values())
        what = "; ".join(f"{s} ({_unfinished(incomplete[s], refused[s])})" for s in incomplete)
        stopped = (f"the sweeps did not finish for {len(incomplete)} sport(s), so their schedules were not saved: "
                   f"{what}")
        print(f"  STOPPED: {stopped}", flush=True)
    print(f"P0 {'stopped' if stopped else 'done'}: credits this run {client.counted:,}, remaining "
          f"{_n(client.remaining)}", flush=True)
    if stopped:
        print("  Rerun the same command until it prints `P0 done` before going on: the sweeps already fetched are "
              "cached, so a rerun buys only what is missing."
              + (" If a rerun stops again on the same sweeps with an error answer, don't keep rerunning: tell the "
                 "hub (the other sports' schedules are saved)." if errors else ""), flush=True)
    return {**res, "stopped": stopped, "spent": client.counted, "remaining": client.remaining, "games": counts,
            "incomplete": list(incomplete), "probes": probes}


def _unfinished(missing: list[Call], refused: list[tuple[Call, int]]) -> str:
    """Which of a sport's sweeps are missing: the ones answered with an error (date and HTTP status, the first
    three), and how many were never reached."""
    parts = []
    if refused:
        shown = ", ".join(f"{iso(c.at)[:10]} HTTP {status}" for c, status in refused[:3])
        more = f" and {len(refused) - 3} more" if len(refused) > 3 else ""
        parts.append(f"{len(refused)} sweep{'s' if len(refused) != 1 else ''} answered with an error: {shown}{more}")
    if len(missing) > len(refused):
        n = len(missing) - len(refused)
        parts.append(f"{n} sweep{'s' if n != 1 else ''} not reached")
    return "; ".join(parts)


def _probe_row(name: str, client: BulkClient, call: Call, want: str) -> dict:
    """One probe call through client.fetch, so it has the same budget, floor, billing and circuit-breaker
    checks as any pull. A stop (or an unexpected error) is printed like run_calls prints it and marked `stopped`."""
    try:
        rec = client.fetch(call)
    except (Exception, KeyboardInterrupt) as e:   # noqa: BLE001 - Stop, Ctrl-C or a bug: the probes end with their summary
        if isinstance(e, KeyboardInterrupt):
            client.in_flight(call)
            why = (f"{INTERRUPTED} (Ctrl-C). The probe that was out may have been billed, so it is counted at its "
                   f"upper bound, {_credits(call.expected)}. A rerun resumes from the cache and may buy that one "
                   "probe again.")
        elif isinstance(e, OSError):
            why = f"a file could not be read or written ({e.strerror or e}): is the disk full? {DISK_HELP}"
        elif isinstance(e, Stop):
            why = str(e)
        else:
            why = f"unexpected error, probably a bug; tell the hub before rerunning ({type(e).__name__}: {scrub(e)})"
            log.error("the probes stopped on an unexpected error:\n%s",
                      scrub("".join(traceback.format_exception(e))))
        print(f"  STOPPED: {why}", flush=True)
        return {"probe": name, "result": f"stopped: {why}", "stopped": True}
    h = json.loads(rec["headers_json"] or "{}")
    body = body_json(rec) if rec["http_status"] == 200 else {}
    rows = outcome_rows(body or {}, iso(call.at))
    mk = sorted({r["market_key"] for r in rows})
    return {"probe": name, "http_status": rec["http_status"], "expected_max": call.expected,
            "billed": h.get("x-requests-last"), "markets_returned": mk, "books_returned": sorted({r["bookmaker"] for r in rows}),
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
    rows, stopped_at = [], None
    for name, call, want in specs:
        if call is None:
            rows.append({"probe": name, "result": want})
        elif stopped_at:
            rows.append({"probe": name, "result": f"not run: the probes stopped at {stopped_at!r}"})
        else:
            rows.append(_probe_row(name, client, call, want))
            if rows[-1].get("stopped"):
                stopped_at = name
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
    if not args.confirm:
        for pid, calls in plans.items():
            todo = [c for c in calls if cache.lookup(c.cache_sport, c.source, c.key) is None]
            print(f"{pid:3} {len(calls):,} calls, {len(todo):,} to fetch, at most {sum(c.expected for c in todo):,} credits")
        print("dry run: add --confirm --max-credits N to run it")
        return []
    client = _client(cache, args, session)
    out = []
    for pid, calls in plans.items():
        res = run_calls(client, calls, f"{pid}{' (one week per sport)' if week else ''}")
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
        print(f"  STOPPED: {e}", flush=True)
    if _ACTIVE is not None:
        print(summary_line(_ACTIVE, True), flush=True)
    return 1
