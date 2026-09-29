"""The NBA pipeline's Odds API client (`markets odds-pull`): historical featured snapshots for one sport. GET only.

It is the bulk puller's client (bulk.BulkClient) with this pipeline's cache layout, so it counts, checks and stops
the way `markets odds5m` does, from the same code: the free key check before the first paid call (it refuses to
start on an unreadable balance or one below the floor); the run budget and the floor checked before every call and
every retry; billing headers that fail closed; the cost counted as the largest of what the response reports, what
the documentation charges for what came back, and how far the balance fell; attempts with no answer counted until
a balance reading explains them; the key blanked everywhere; a STOPPED line and a summary on every stop; no 200 that
isn't JSON ever cached; and a row per paid request in data/raw/_manifest/oddsapi_manifest.csv, with pull id N0.

What it asks for and where it caches are its own and unchanged: data/raw/{sport}/oddsapi_hist/, keyed on the same
URL and parameters as before (N1's cache_as calls and the sample week's cached Kalshi data rely on them). Unlike the
bulk puller it caches only HTTP 200 and stops at the first error status.

Cost model (docs): historical odds = 10 x markets x regions; `bookmakers=` counts one region per 10 books.
"""
from __future__ import annotations

import logging
from datetime import datetime

from ..cache import RawCache, body_json
from ..http import scrub
from .bulk import BudgetExceeded, BulkClient, Call, CircuitBreaker, Stop, is_sealed, iso, load_config
from .schedule import credits_per_snapshot

__all__ = ["BASE_URL", "BudgetExceeded", "OddsApiClient", "OddsApiError", "PULL_ID", "SOURCE", "Stop"]

log = logging.getLogger(__name__)
BASE_URL = "https://api.the-odds-api.com/v4"
SOURCE = "oddsapi_hist"
PULL_ID = "N0"               # the NBA sample week's pull ID in the manifest (N1 is the full season)


class OddsApiError(CircuitBreaker):
    """An error status from the API: odds-pull stops at the first one."""


class OddsApiClient(BulkClient):
    cache_statuses = (200,)

    def __init__(self, sport: str, cache: RawCache, *, max_credits: int, rate_per_sec: float = 2, floor: int = 0,
                 session=None, api_key: str | None = None, max_retries: int = 6):
        super().__init__(cache, max_credits=max_credits, floor=floor, rate_per_sec=rate_per_sec, session=session,
                         api_key=api_key, max_retries=max_retries)
        self.sport = sport
        self._odds5m: dict | None = None

    def _base(self) -> str:
        return BASE_URL

    @property
    def credits_spent(self) -> int:
        return self.counted

    def _sealed(self, sport_key: str, at: datetime) -> bool:
        """The manifest's sealed flag: whether the snapshot falls in a sealed season of config/odds5m.yaml."""
        if self._odds5m is None:
            self._odds5m = load_config()
        return sport_key in self._odds5m["sports"] and is_sealed(self._odds5m, sport_key, at)

    def call_for(self, *, sport_key: str, at: datetime, bookmakers: tuple[str, ...], markets: str = "h2h") -> Call:
        """One featured historical snapshot. The URL and parameters are exactly the ones odds-pull has always sent, so
        the cache key and folder are unchanged."""
        params = {"bookmakers": ",".join(bookmakers), "markets": markets, "oddsFormat": "decimal",
                  "dateFormat": "iso", "date": at.strftime("%Y-%m-%dT%H:%M:%SZ")}
        return Call(PULL_ID, sport_key, SOURCE, f"/historical/sports/{sport_key}/odds", tuple(sorted(params.items())),
                    at, credits_per_snapshot(len(markets.split(",")), len(bookmakers)), self._sealed(sport_key, at),
                    cache_sport=self.sport, base=BASE_URL)

    def fetch(self, call: Call) -> dict:
        rec = super().fetch(call)
        if rec["http_status"] != 200:
            # the body is printed only with any key blanked, in case a server or proxy echoes the request
            raise OddsApiError(f"Odds API {call.path} at {iso(call.at)} -> HTTP {rec['http_status']}: "
                               f"{scrub(rec['body'] or '')[:300]}. Nothing was cached for it.")
        return rec

    def historical_odds(self, *, sport_key: str, at: datetime, bookmakers: tuple[str, ...], markets: str = "h2h") -> dict:
        return body_json(self.fetch(self.call_for(sport_key=sport_key, at=at, bookmakers=bookmakers, markets=markets)))

    def is_cached_historical(self, *, sport_key: str, at: datetime, bookmakers: tuple[str, ...], markets: str = "h2h") -> bool:
        return self.is_cached(self.call_for(sport_key=sport_key, at=at, bookmakers=bookmakers, markets=markets))
