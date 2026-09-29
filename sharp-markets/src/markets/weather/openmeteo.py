"""Open-Meteo client (GET only, free, no key; the hub runs it on the Mac, where the API is reachable).

Two sources, both cache-first under data/raw/_weather/:
  archive   ERA5 reanalysis, observed weather at the venue (archive-api.open-meteo.com). Descriptive only:
            observed weather is not known before kickoff, so it never drives a pre-game decision.
  prev      what the forecast said one day earlier (previous-runs-api.open-meteo.com, `*_previous_day1`),
            available from 2024. This is the exposure the heat hypotheses bet on (docs/HEAT_HYPOTHESES.md).

One request per venue per calendar month with games (the whole month, so cache keys are stable), so a
season costs roughly venues x months. Open-Meteo's free tier allows 600 calls a minute and 10,000 a
day; `fetch` defaults to 5 a second and stops at --max-calls.
"""
from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from ..cache import Fetched, RawCache, body_json, cache_key
from ..http import RateLimiter, http_get, new_session

ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
PREV_URL = "https://previous-runs-api.open-meteo.com/v1/forecast"
ARCHIVE_VARS = ("temperature_2m", "relative_humidity_2m", "dew_point_2m", "wind_speed_10m", "wind_direction_10m",
                "precipitation")
PREV_VARS = tuple(f"{v}_previous_day1" for v in ("temperature_2m", "relative_humidity_2m", "wind_speed_10m",
                                                 "wind_direction_10m", "precipitation"))
PREV_FROM = date(2024, 1, 1)
SPORT = "_weather"
SOURCES = {"archive": "openmeteo_archive", "prev": "openmeteo_prev"}


@dataclass(frozen=True)
class Request:
    kind: str                 # archive | prev
    venue_id: str
    lat: float
    lon: float
    start: date
    end: date

    @property
    def url(self) -> str:
        return ARCHIVE_URL if self.kind == "archive" else PREV_URL

    @property
    def params(self) -> dict:
        return {"latitude": f"{self.lat:.4f}", "longitude": f"{self.lon:.4f}", "start_date": self.start.isoformat(),
                "end_date": self.end.isoformat(), "timezone": "UTC", "temperature_unit": "fahrenheit",
                "wind_speed_unit": "mph", "precipitation_unit": "inch",
                "hourly": ",".join(ARCHIVE_VARS if self.kind == "archive" else PREV_VARS)}

    @property
    def key(self) -> str:
        return cache_key(SOURCES[self.kind], self.url, self.params)


def plan_requests(venue_days: set[tuple[str, date]], venues: dict, today: date | None = None) -> list[Request]:
    """Archive and previous-run requests for (venue_id, UTC day) pairs, one per venue per month.
    The archive lags about five days, so days within five days of today are left for a later run."""
    today = today or datetime.now(timezone.utc).date()
    months: dict[tuple[str, int, int], list[date]] = defaultdict(list)
    for vid, day in venue_days:
        if day <= today - timedelta(days=5):
            months[(vid, day.year, day.month)].append(day)
    out = []
    for (vid, y, m) in sorted(months):
        out += month_requests(vid, venues[vid], y, m, today)
    return out


def month_requests(vid: str, v, year: int, month: int, today: date | None = None) -> list[Request]:
    """Whole calendar months (clipped to five days ago), so cache keys don't move as games are added."""
    today = today or datetime.now(timezone.utc).date()
    lo = date(year, month, 1)
    hi = min((lo.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1), today - timedelta(days=5))
    out = [Request("archive", vid, v.lat, v.lon, lo, hi)]
    if hi >= PREV_FROM:
        out.append(Request("prev", vid, v.lat, v.lon, max(lo, PREV_FROM), hi))
    return out


class OpenMeteo:
    def __init__(self, cache: RawCache, *, rate_per_sec: float = 5, session=None):
        self.cache = cache
        self.session = session or new_session()
        self.limiter = RateLimiter(rate_per_sec)

    def is_cached(self, req: Request) -> bool:
        return self.cache.lookup(SPORT, SOURCES[req.kind], req.key) is not None

    def body(self, req: Request) -> dict | None:
        """The cached response, or None (never fetches)."""
        p = self.cache.lookup(SPORT, SOURCES[req.kind], req.key)
        if p is None:
            return None
        from ..cache import read_record
        rec = read_record(p)
        return body_json(rec) if rec["http_status"] == 200 else None

    def fetch(self, req: Request) -> dict:
        def fetch() -> Fetched:
            r = http_get(self.session, req.url, req.params, self.limiter, max_retries=4)
            return Fetched(r.status_code, dict(r.headers), r.text)
        return self.cache.get_or_fetch(sport=SPORT, source=SOURCES[req.kind], data_date=req.start.isoformat(),
                                       url=req.url, params=req.params, fetch=fetch, cache_statuses=(200,))

    def run(self, reqs: list[Request], *, max_calls: int) -> dict:
        todo = [r for r in reqs if not self.is_cached(r)]
        done = errors = 0
        for r in todo[:max_calls]:
            rec = self.fetch(r)
            done += 1
            if rec["http_status"] != 200:
                errors += 1
                print(f"  {r.kind} {r.venue_id} {r.start}..{r.end}: HTTP {rec['http_status']} {(rec['body'] or '')[:160]}")
                if errors >= 5:
                    print("  stopping: 5 errors")
                    break
            if done % 250 == 0:
                print(f"  {done}/{len(todo)}", flush=True)
        return {"requests": len(reqs), "todo": len(todo), "fetched": done, "errors": errors,
                "left": max(0, len(todo) - done)}


def at_hour(body: dict | None, when: datetime) -> dict:
    """The hourly values at the hour `when` (UTC), with the `_previous_day1` suffix dropped."""
    if not body or "hourly" not in body:
        return {}
    h = body["hourly"]
    target = when.strftime("%Y-%m-%dT%H:00")          # callers pass the hour (join.kick_hour)
    try:
        i = h["time"].index(target)
    except ValueError:
        return {}
    return {k.replace("_previous_day1", ""): v[i] for k, v in h.items() if k != "time"}


def dumps(req: Request) -> str:
    return json.dumps({"kind": req.kind, "venue": req.venue_id, "start": str(req.start), "end": str(req.end)})
