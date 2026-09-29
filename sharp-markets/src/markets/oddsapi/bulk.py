"""Bulk historical Odds API puller for the 5M-credit month. GET only. Config: config/odds5m.yaml.

Stages (`uv run markets odds5m <stage>`; the hub runs them on the Mac, docs/ODDS5M_DAY_ONE.md):
  probe  P0: verify the key (free), sweep historical /events for every sport (1 credit per call,
         0 when empty) into exact schedules, then seven single-call billing and coverage probes
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
each call's upper-bound cost before the call, and a --floor on the account's remaining credits
(the live-use reserve). A run starts only when the free /sports check returns a readable balance at or
above the floor. The billing headers fail closed: a billed response whose `x-requests-last` can't be read
counts its upper bound and stops the run, and an unreadable balance stops it while a floor is set. The
circuit breaker stops the run when a call bills more than its upper bound (`x-requests-last`), when the key
is rejected or the quota runs out, after repeated errors, or when the network fails past the retries.
Every stop ends the run with a STOPPED line and its summary, never a traceback; error text never holds
the key (markets.http.scrub).
Every real request is logged to data/raw/_manifest/oddsapi_manifest.csv: requested vs returned
snapshot time, credits billed, credits remaining, a SHA-256 of the body, the cache key, sealed flag.

Season slices: a pull with `require_seasons:` in the config (F3) is bought one season slice at a time,
so `full` refuses it without --seasons, dry run included.

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
import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import requests
import yaml

from ..cache import Fetched, RawCache, body_json, cache_key, read_record
from ..http import RateLimiter, http_get, new_session
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

    @property
    def url(self) -> str:
        return BASE_URL + self.path

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
    path = schedule_path(raw_dir, sport)
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pylist([{f.name: g.get(f.name) for f in SCHEDULE_SCHEMA} for g in games],
                                        schema=SCHEDULE_SCHEMA), path)
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


def games_from(pull: dict, sport: str) -> set[str] | None:
    """The event IDs a `games_from:` pull is limited to for one sport (None when the pull has no list).
    The CSV has `sport` and `id` columns; `markets weather qualifying` writes it. A relative path is
    under the data directory. A missing file stops the run: the trigger step has to come first."""
    if not pull.get("games_from"):
        return None
    path = Path(pull["games_from"])
    if not path.is_absolute():
        path = DATA_DIR / path
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


def _credits(value) -> int | None:
    """A billing header (`x-requests-last`, `x-requests-remaining`) as whole credits; None when it is
    missing, not a number, negative or not finite. None means "unknown", never zero."""
    try:
        x = float(value)
    except (TypeError, ValueError):
        return None
    return int(x) if math.isfinite(x) and x >= 0 else None


class BulkClient:
    def __init__(self, cache: RawCache, *, max_credits: int, floor: int = 0, rate_per_sec: float = 8.0,
                 session=None, api_key: str | None = None, max_retries: int = 6, max_errors: int = 5):
        self.cache, self.max_credits, self.floor = cache, max_credits, floor
        self.session = session or new_session()
        self.limiter = RateLimiter(rate_per_sec)
        self.api_key, self.max_retries, self.max_errors = api_key, max_retries, max_errors
        self.spent = self.fetched = self.errors_in_row = 0
        self.remaining: int | None = None
        self.manifest = Path(cache.raw_dir) / "_manifest" / "oddsapi_manifest.csv"

    def _get(self, url: str, params: dict):
        """One GET with the key added. A network failure that outlasts http_get's retries stops the run; its
        text has the key blanked (markets.http.scrub)."""
        try:
            return http_get(self.session, url, {**params, "apiKey": self.api_key or env("ODDS_API_KEY")},
                            self.limiter, max_retries=self.max_retries)
        except requests.RequestException as e:
            raise CircuitBreaker(
                f"no answer from the Odds API after the retries ({type(e).__name__}: {e}). Nothing was cached for "
                "this call, so a rerun asks again. A call that timed out may still have been billed: the rerun "
                "reads the balance before its first call.") from None

    def account(self) -> dict:
        """GET /v4/sports: free. Checks the key and reads the credits remaining. Never cached.

        Refuses to start the run (raises Stop, before any paid call) when the key is rejected, the check
        doesn't return HTTP 200, the balance (`x-requests-remaining`) is missing or unreadable, or the
        balance is already below the floor."""
        r = self._get(BASE_URL + "/sports", {})
        h = {k.lower(): v for k, v in r.headers.items()}
        self.remaining = _credits(h.get("x-requests-remaining"))
        self._log({"pull": "account", "path": "/sports", "http_status": r.status_code,
                   "credits_last": h.get("x-requests-last", ""), "remaining": self.remaining,
                   "sha256": hashlib.sha256(r.text.encode()).hexdigest()})
        if r.status_code == 401:
            raise CircuitBreaker("the Odds API rejected the key (401): check ODDS_API_KEY in sharp-markets/.env")
        if r.status_code != 200:
            raise CircuitBreaker(f"the free key check (/v4/sports) returned HTTP {r.status_code}: {r.text[:200]}. "
                                 "Try again in a few minutes.")
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
        """The stored record for this call (cache first). Raises Stop before or after a call that must end the run."""
        if not self.is_cached(call):
            if self.spent + call.expected > self.max_credits:
                raise BudgetExceeded(f"the next call could cost {call.expected}; {self.spent:,} of the "
                                     f"{self.max_credits:,}-credit run budget is spent")
            if self.remaining is None:
                if self.floor > 0:
                    raise BudgetExceeded(f"the account balance is unknown, so the floor of {self.floor:,} can't be "
                                         "checked. Nothing was fetched; a new run reads the balance before it starts")
            elif self.remaining - call.expected < self.floor:
                raise BudgetExceeded(f"{self.remaining:,} credits remain; the floor is {self.floor:,}")
        sent = []

        def fetch() -> Fetched:
            r = self._get(call.url, dict(call.params))
            sent.append(r.status_code)
            return Fetched(r.status_code, {k.lower(): v for k, v in r.headers.items()}, r.text)

        rec = self.cache.get_or_fetch(sport=call.cache_sport, source=call.source, data_date=call.at.date().isoformat(),
                                      url=call.url, params=dict(call.params), fetch=fetch, cache_statuses=(200, 404))
        if sent:
            self._account(call, rec)
        return rec

    def _account(self, call: Call, rec: dict) -> None:
        """Count what one real request cost, log it, and stop the run when it must end.

        What the API bills (its v4 docs, read Sep 29, 2026): a call is billed by the data it returns. Historical
        odds cost 10 x markets x regions, historical /events 1 (nothing when no events are found), event odds
        10 x markets returned x regions, and "responses with empty data do not count". The docs name no charge
        for an error status, and don't say whether error responses carry the usage headers. So:

        - HTTP 200 is billed. When `x-requests-last` is missing or not a number, the call's upper bound
          (call.expected) is counted as spent and the run stops: the billing could not be read. The response is
          already cached, so nothing is lost. When `x-requests-remaining` is missing or not a number, the
          balance becomes unknown, and the run stops if a floor is set.
        - HTTP 404 (the event is not found; cached like an empty response) and error statuses return no data,
          so by the docs they cost nothing. Their headers are still used when readable, and the overbilling
          check applies to them. When `x-requests-last` is unreadable, the upper bound is counted anyway, so
          the run budget errs toward stopping early, but the run goes on: stopping at every 404 would stall F2
          and F3 over responses the docs call free. Errors still stop the run after max_errors in a row, and
          401 and 429 stop it at once. When `x-requests-remaining` is unreadable, the known balance is lowered
          by what was counted, so the floor keeps being checked.
        """
        h = json.loads(rec["headers_json"] or "{}")
        body, status = rec["body"] or "", rec["http_status"]
        raw_last, raw_left = h.get("x-requests-last"), h.get("x-requests-remaining")
        last, left = _credits(raw_last), _credits(raw_left)
        counted = call.expected if last is None else last
        self.spent += counted
        self.fetched += 1
        if left is not None:
            self.remaining = left
        elif status == 200:
            self.remaining = None
        elif self.remaining is not None:
            self.remaining -= counted
        env_, p = _envelope(body), dict(call.params)
        self._log({"pull": call.pull, "sport": call.sport, "source": call.source, "path": call.path,
                   "event_id": call.event_id, "requested_ts": iso(call.at), "returned_ts": env_.get("timestamp", ""),
                   "previous_ts": env_.get("previous_timestamp", ""), "next_ts": env_.get("next_timestamp", ""),
                   "markets": p.get("markets", ""), "books": p.get("bookmakers", ""), "n_events": env_["n"],
                   "expected_credits": call.expected, "credits_last": last, "remaining": self.remaining,
                   "http_status": status, "sha256": hashlib.sha256(body.encode()).hexdigest(),
                   "cache_key": rec["cache_key"], "sealed": call.sealed})
        where = f"{call.path} at {iso(call.at)}"
        if status == 401:
            raise CircuitBreaker("the Odds API rejected the key (401)")
        if status == 429:
            raise CircuitBreaker(f"HTTP 429 after retries (quota used up or rate limited): {body[:200]}")
        if last is not None and last > call.expected:
            raise CircuitBreaker(f"{where} billed {last} credits; it should cost at most "
                                 f"{call.expected}. Stopped: check the billing before going on.")
        if status == 200 and last is None:
            raise CircuitBreaker(f"the billing could not be read: {where} came back with x-requests-last "
                                 f"{raw_last!r}, so its upper bound, {call.expected}, was counted as spent. The "
                                 "response is cached. Check the billing before going on.")
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
        log.warning("%s at %s -> HTTP %s: %s", call.path, iso(call.at), status, body[:200])
        if self.errors_in_row >= self.max_errors:
            raise CircuitBreaker(f"{self.errors_in_row} errors in a row; the last was HTTP {status}: {body[:200]}")

    def _log(self, row: dict) -> None:
        self.manifest.parent.mkdir(parents=True, exist_ok=True)
        new = not self.manifest.exists()
        with self.manifest.open("a", newline="") as f:
            w = csv.DictWriter(f, MANIFEST_FIELDS)
            if new:
                w.writeheader()
            w.writerow({"logged_at": iso(utcnow()), **{k: ("" if v is None else v) for k, v in row.items()}})


def run_calls(client: BulkClient, calls: list[Call], label: str = "") -> dict:
    """Fetch the calls not yet cached, in order. Every way a run can end (done, budget, floor, circuit breaker,
    unreadable billing, network) ends here with a STOPPED line when it stopped, then one summary line."""
    todo = [c for c in calls if not client.is_cached(c)]
    print(f"{label}: {len(calls):,} calls, {len(calls) - len(todo):,} cached, {len(todo):,} to fetch, "
          f"at most {sum(c.expected for c in todo):,} credits", flush=True)
    stopped = None
    for i, c in enumerate(todo, 1):
        try:
            client.fetch(c)
        except Stop as e:
            stopped = str(e)
            print(f"  STOPPED: {stopped}", flush=True)
            break
        if i % 500 == 0:
            print(f"  {i:,}/{len(todo):,}  credits this run {client.spent:,}  remaining {client.remaining}", flush=True)
    print(f"  {'stopped' if stopped else 'done'}: {client.fetched:,} fetched, credits this run {client.spent:,}, "
          f"remaining {client.remaining}", flush=True)
    return {"calls": len(calls), "todo": len(todo), "fetched": client.fetched, "spent": client.spent,
            "remaining": client.remaining, "stopped": stopped}


# ---------------------------------------------------------------- reading the cache
def cached_bodies(client: BulkClient, calls: list[Call]):
    for c in calls:
        rec = client.cached_record(c)
        if rec is not None and rec["http_status"] == 200:
            yield c, rec, body_json(rec)


def load_rows(cfg: dict, calls: list[Call], cache: RawCache, *, include_sealed: bool = False) -> list[dict]:
    """Normalized rows for the cached calls. Rows for games in a sealed season are left out unless
    include_sealed=True (only a pre-registered test of that season may pass it)."""
    client = BulkClient(cache, max_credits=0)
    rows = []
    for c, _, body in cached_bodies(client, calls):
        for r in outcome_rows(body, iso(c.at)):
            k = parse_ts(r["commence_time"])
            if include_sealed or k is None or not is_sealed(cfg, c.sport, k):
                rows.append({**r, "sport": c.sport, "pull": c.pull})
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
    schedules = load_schedules(cfg, cache.raw_dir)
    missing = [s for s in cfg["sports"] if s not in schedules]
    if missing:
        print(f"no schedule yet for {missing}: run `markets odds5m probe --confirm` first")
    total, out = 0, []
    for pid in _pulls(cfg, args.pull):
        calls = plan_calls(cfg, pid, schedules, now=now, sports=args.sports, seasons=args.seasons)
        todo = sum(c.expected for c in calls if cache.lookup(c.cache_sport, c.source, c.key) is None)
        total += todo
        rows = summarize(cfg, calls, cache)
        out += rows
        by_slice = cfg["pulls"][pid].get("require_seasons") and not args.seasons
        slices = "  (all seasons; `full` needs --seasons)" if by_slice else ""
        print(f"{pid:3} {group_of(cfg, pid):8} {len(calls):>9,} calls  at most {todo:>11,} credits to fetch  "
              f"cumulative {total:>11,}  sealed calls {sum(c.sealed for c in calls):,}{slices}")
    return out


def _client(cache, args, session=None) -> BulkClient:
    if not args.confirm:
        raise SystemExit("dry run: add --confirm (and --max-credits) to call the Odds API")
    if args.max_credits <= 0:
        raise SystemExit("--max-credits is required with --confirm")
    c = BulkClient(cache, max_credits=args.max_credits, floor=args.floor, rate_per_sec=args.rate, session=session)
    try:
        info = c.account()
    except Stop as e:
        raise SystemExit(f"STOPPED before the first paid call, nothing spent: {e}") from None
    print(f"key ok: HTTP {info['status']}, {info['remaining']:,} credits remaining, {info['used']} used; "
          f"floor {c.floor:,}")
    return c


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
    counts = {}
    for s, calls in sweeps.items():
        games = build_schedule(cfg, s, [b for _, _, b in cached_bodies(client, calls)])
        save_schedule(cache.raw_dir, s, games)
        counts[s] = Counter(g["season"] or "outside windows" for g in games)
        print(f"  {s:36} {len(games):6,} games  " + "  ".join(f"{k}: {v}" for k, v in sorted(counts[s].items())))
    probes = [] if res["stopped"] else billing_probes(cfg, client, load_schedules(cfg, cache.raw_dir), now)
    stopped = res["stopped"] or next((p["result"] for p in probes if p.get("stopped")), None)
    print(f"P0 {'stopped' if stopped else 'done'}: credits this run {client.spent:,}, remaining {client.remaining}",
          flush=True)
    return {**res, "stopped": stopped, "spent": client.spent, "remaining": client.remaining, "games": counts,
            "probes": probes}


def _probe_row(name: str, client: BulkClient, call: Call, want: str) -> dict:
    """One probe call through client.fetch, so it has the same budget, floor, billing and circuit-breaker
    checks as any pull. A stop is printed like run_calls prints it and marked `stopped`."""
    try:
        rec = client.fetch(call)
    except Stop as e:
        print(f"  STOPPED: {e}", flush=True)
        return {"probe": name, "result": f"stopped: {e}", "stopped": True}
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


def _slice_refusal(cfg: dict, cache: RawCache, pid: str, schedules: dict, now, args) -> str:
    """Why `full` refuses a `require_seasons` pull without --seasons, with the command for each named slice.
    `require_seasons` is true, or a mapping of slice name to season labels (F3: day_one 2025, gated the rest)."""
    need = cfg["pulls"][pid]["require_seasons"]
    todo = [c for c in plan_calls(cfg, pid, schedules, now=now, sports=args.sports)
            if cache.lookup(c.cache_sport, c.source, c.key) is None]
    lines = [f"{pid}: refused. `full --pull {pid}` needs --seasons. This pull is bought one season slice at a time "
             f"(require_seasons in config/odds5m.yaml); without --seasons this run would fetch every season at once: "
             f"{len(todo):,} calls, at most {sum(c.expected for c in todo):,} credits. Nothing was fetched."]
    if isinstance(need, dict):
        for name, seasons in need.items():
            lines.append(f"  {name}: uv run markets odds5m full --pull {pid} --seasons {seasons} --confirm --max-credits N"
                         + ("" if name == "day_one" else "   (only once its gate has passed)"))
    else:
        lines.append("  add --seasons with the slice's season labels, e.g. --seasons 2025")
    lines.append("Run it first without --confirm to see the slice's cost, and set N a little above it "
                 "(docs/ODDS5M_DAY_ONE.md, step 5).")
    return "\n".join(lines)


def stage_pull(cfg, cache, args, *, week: bool, now=None, session=None) -> list[dict]:
    schedules = load_schedules(cfg, cache.raw_dir)
    if not schedules:
        raise SystemExit("no schedules: run `markets odds5m probe --confirm --max-credits N` first")
    if not week and args.pull in (None, "", "all"):
        raise SystemExit("full: name the pulls (--pull F1,F2) or a group from config/odds5m.yaml "
                         f"({', '.join(cfg.get('groups', {}))}); `all` would run every pull in the config")
    ids = _pulls(cfg, args.pull)
    if not week and not args.seasons:
        for pid in ids:
            if cfg["pulls"][pid].get("require_seasons"):
                raise SystemExit(_slice_refusal(cfg, cache, pid, schedules, now, args))
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


def main(args) -> None:
    cfg, cache = load_config(), RawCache()
    args.sports = [s.strip() for s in args.sports.split(",")] if args.sports else None
    args.seasons = [s.strip() for s in args.seasons.split(",")] if getattr(args, "seasons", None) else None
    if args.stage == "probe":
        stage_probe(cfg, cache, args)
    elif args.stage == "plan":
        stage_plan(cfg, cache, args)
    elif args.stage in ("week", "full"):
        stage_pull(cfg, cache, args, week=args.stage == "week")
    else:
        stage_check(cfg, cache, args)
