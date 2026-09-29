"""Bulk historical Odds API puller for the 5M-credit month. GET only. Config: config/odds5m.yaml.

Stages (`uv run markets odds5m <stage>`; the hub runs them on the Mac, docs/ODDS5M_DAY_ONE.md):
  probe  P0: verify the key (free), sweep historical /events for every sport (1 credit per call,
         0 when empty) into exact schedules, then four single-call billing probes
  plan   free: calls and upper-bound credits per pull from those schedules, cached vs to fetch
  week   one week per sport for the chosen pulls, to check coverage before the full spend
  full   the chosen pulls in full, in the plan's value order
  check  free: what the cache holds for a pull (books, markets, snapshot lag, empty snapshots)

Safety. Nothing is fetched without --confirm. Each run has a --max-credits budget, checked against
each call's upper-bound cost before the call, and a --floor on the account's remaining credits
(the live-use reserve). The circuit breaker stops the run when a call bills more than its upper
bound (`x-requests-last`), when the key is rejected or the quota runs out, or after repeated errors.
Every real request is logged to data/raw/_manifest/oddsapi_manifest.csv: requested vs returned
snapshot time, credits billed, credits remaining, a SHA-256 of the body, the cache key, sealed flag.

Cache first: responses land in data/raw/{sport_key}/oddsapi/{hist_events,hist_odds,hist_event_odds}/
before use, so reruns and interrupted runs resume for free.

Sealed holdout: seasons marked sealed in the config are pulled but load_rows() leaves them out
unless include_sealed=True, which only a pre-registered test may pass.
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
import yaml

from ..cache import Fetched, RawCache, body_json, cache_key, read_record
from ..http import RateLimiter, http_get, new_session
from ..settings import CONFIG_DIR, env, parse_ts, utcnow
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
    if sched == "daily_close":
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


def pull_games(cfg: dict, pull: dict, sport: str, games: list[dict], now: datetime) -> list[dict]:
    lo = max(cfg["sports"][sport]["history_from"], pull.get("from", date.min))
    return [g for g in games
            if g["season"] is not None and g["commence_time"] <= now - SETTLED and g["commence_time"].date() >= lo
            and (not pull.get("only_seasons") or g["season"] in pull["only_seasons"])
            and g["season"] not in pull.get("skip_seasons", [])]


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
               week_of=None, sports=None) -> list[Call]:
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
        games = pull_games(cfg, pull, sport, schedules.get(sport, []), now)
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
        return http_get(self.session, url, {**params, "apiKey": self.api_key or env("ODDS_API_KEY")},
                        self.limiter, max_retries=self.max_retries)

    def account(self) -> dict:
        """GET /v4/sports: free. Checks the key and reads the credits remaining. Never cached."""
        r = self._get(BASE_URL + "/sports", {})
        h = {k.lower(): v for k, v in r.headers.items()}
        if h.get("x-requests-remaining") is not None:
            self.remaining = int(float(h["x-requests-remaining"]))
        self._log({"pull": "account", "path": "/sports", "http_status": r.status_code,
                   "credits_last": h.get("x-requests-last", ""), "remaining": self.remaining,
                   "sha256": hashlib.sha256(r.text.encode()).hexdigest()})
        if r.status_code == 401:
            raise CircuitBreaker("the Odds API rejected the key (401): check ODDS_API_KEY in sharp-markets/.env")
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
            if self.remaining is not None and self.remaining - call.expected < self.floor:
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
        h = json.loads(rec["headers_json"] or "{}")
        last = int(float(h.get("x-requests-last") or 0))
        self.spent += last
        self.fetched += 1
        if h.get("x-requests-remaining") is not None:
            self.remaining = int(float(h["x-requests-remaining"]))
        body, status = rec["body"] or "", rec["http_status"]
        env_, p = _envelope(body), dict(call.params)
        self._log({"pull": call.pull, "sport": call.sport, "source": call.source, "path": call.path,
                   "event_id": call.event_id, "requested_ts": iso(call.at), "returned_ts": env_.get("timestamp", ""),
                   "previous_ts": env_.get("previous_timestamp", ""), "next_ts": env_.get("next_timestamp", ""),
                   "markets": p.get("markets", ""), "books": p.get("bookmakers", ""), "n_events": env_["n"],
                   "expected_credits": call.expected, "credits_last": last, "remaining": self.remaining,
                   "http_status": status, "sha256": hashlib.sha256(body.encode()).hexdigest(),
                   "cache_key": rec["cache_key"], "sealed": call.sealed})
        if status == 401:
            raise CircuitBreaker("the Odds API rejected the key (401)")
        if status == 429:
            raise CircuitBreaker(f"HTTP 429 after retries (quota used up or rate limited): {body[:200]}")
        if last > call.expected:
            raise CircuitBreaker(f"{call.path} at {iso(call.at)} billed {last} credits; it should cost at most "
                                 f"{call.expected}. Stopped: check the billing before going on.")
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
    ids = list(cfg["pulls"]) if arg in (None, "", "all") else [p.strip() for p in arg.split(",")]
    bad = [p for p in ids if p not in cfg["pulls"]]
    if bad:
        raise SystemExit(f"unknown pull(s) {bad}; the config has {list(cfg['pulls'])}")
    return ids


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
        calls = plan_calls(cfg, pid, schedules, now=now, sports=args.sports)
        todo = sum(c.expected for c in calls if cache.lookup(c.cache_sport, c.source, c.key) is None)
        total += todo
        rows = summarize(cfg, calls, cache)
        out += rows
        print(f"{pid:3} {len(calls):>9,} calls  at most {todo:>11,} credits to fetch  cumulative {total:>11,}  "
              f"sealed calls {sum(c.sealed for c in calls):,}")
    return out


def _client(cache, args, session=None) -> BulkClient:
    if not args.confirm:
        raise SystemExit("dry run: add --confirm (and --max-credits) to call the Odds API")
    if args.max_credits <= 0:
        raise SystemExit("--max-credits is required with --confirm")
    c = BulkClient(cache, max_credits=args.max_credits, floor=args.floor, rate_per_sec=args.rate, session=session)
    info = c.account()
    print(f"key ok: HTTP {info['status']}, {info['remaining']} credits remaining, {info['used']} used")
    return c


def stage_probe(cfg, cache, args, now=None, session=None) -> dict:
    now = now or utcnow()
    sports = [s for s in cfg["sports"] if not args.sports or s in args.sports]
    sweeps = {s: sweep_calls(cfg, s, now) for s in sports}
    n = sum(len(v) for v in sweeps.values())
    print(f"P0 /events sweeps: {n:,} calls across {len(sports)} sports (1 credit each, 0 when empty); "
          f"billing probes: at most 180 more")
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
    return {**res, "games": counts, "probes": probes}


def _probe_row(name: str, client: BulkClient, call: Call, want: str) -> dict:
    try:
        rec = client.fetch(call)
    except Stop as e:
        return {"probe": name, "result": f"stopped: {e}"}
    h = json.loads(rec["headers_json"] or "{}")
    body = body_json(rec) if rec["http_status"] == 200 else {}
    rows = outcome_rows(body or {}, iso(call.at))
    mk = sorted({r["market_key"] for r in rows})
    return {"probe": name, "http_status": rec["http_status"], "expected_max": call.expected,
            "billed": h.get("x-requests-last"), "markets_returned": mk, "books_returned": sorted({r["bookmaker"] for r in rows}),
            "events": len({r["odds_event_id"] for r in rows}), "check": want,
            **({"billing_rule": f"10 x {len(mk)} markets returned = {10 * len(mk)}"} if call.source == SRC_EVENT_ODDS else {})}


def billing_probes(cfg: dict, client: BulkClient, schedules: dict, now: datetime) -> list[dict]:
    """Four single calls that test the cost model and coverage before the big spend (~180 credits at most)."""
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
    fe = lambda books, g: Call("P0", "americanfootball_nfl", SRC_ODDS,  # noqa: E731
                               "/historical/sports/americanfootball_nfl/odds",
                               _odds_params(books, featured, close_time(g["commence_time"])),
                               close_time(g["commence_time"]), 30 * regions(books), g["sealed"],
                               cache_sport="americanfootball_nfl")
    at = close_time(g24["commence_time"])
    rows = [_probe_row("featured NFL, 10 books, 3 markets", client, fe(us10, g24), "billed 30 (one region)"),
            _probe_row("event odds NFL props, 10 books", client, ev(us10, g24, at),
                       "billed = 10 x markets returned, at most 60"),
            _probe_row("event odds NFL props, Pinnacle only", client, ev(["pinnacle"], g24, at),
                       "which props Pinnacle quotes")]
    if g20:
        rows.append(_probe_row("featured NFL 2020, sharp books", client, fe(cfg["books"]["sharp3"], g20),
                               "is LowVig in the 2020 data?"))
    for r in rows:
        print("  " + json.dumps(r, default=str))
    return rows


def stage_pull(cfg, cache, args, *, week: bool, now=None, session=None) -> list[dict]:
    schedules = load_schedules(cfg, cache.raw_dir)
    if not schedules:
        raise SystemExit("no schedules: run `markets odds5m probe --confirm --max-credits N` first")
    ids = _pulls(cfg, args.pull)
    plans = {pid: plan_calls(cfg, pid, schedules, now=now, week_of=args.week_of if week else None,
                             sports=args.sports) for pid in ids}
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
        cov = coverage(cfg, plan_calls(cfg, pid, schedules, now=now, sports=args.sports), cache)
        print(f"{pid}: {json.dumps(cov, default=str)}")
        out.append({"pull": pid, **cov})
    return out


def main(args) -> None:
    cfg, cache = load_config(), RawCache()
    args.sports = [s.strip() for s in args.sports.split(",")] if args.sports else None
    if args.stage == "probe":
        stage_probe(cfg, cache, args)
    elif args.stage == "plan":
        stage_plan(cfg, cache, args)
    elif args.stage in ("week", "full"):
        stage_pull(cfg, cache, args, week=args.stage == "week")
    else:
        stage_check(cfg, cache, args)
