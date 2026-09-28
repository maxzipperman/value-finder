"""The Odds API client (historical + live odds) with a hard credit budget. GET only.

Cost model (docs): historical odds = 10 x markets x regions; live odds = markets x regions;
`bookmakers=` counts one region per 10 books. Actual cost is read from `x-requests-last`.
"""
from __future__ import annotations

import logging
from datetime import datetime

from ..cache import Fetched, RawCache, body_json, cache_key
from ..http import RateLimiter, http_get, new_session
from ..settings import env
from .schedule import credits_per_snapshot

log = logging.getLogger(__name__)
BASE_URL = "https://api.the-odds-api.com/v4"


class BudgetExceeded(RuntimeError):
    pass


class OddsApiError(RuntimeError):
    pass


class OddsApiClient:
    def __init__(self, sport: str, cache: RawCache, *, max_credits: int, rate_per_sec: float = 2):
        self.sport = sport
        self.cache = cache
        self.max_credits = max_credits
        self.credits_spent = 0
        self.remaining: int | None = None
        self.session = new_session()
        self.limiter = RateLimiter(rate_per_sec)

    def _request(self, path: str, params: dict, *, source: str, data_date: str, expected_cost: int) -> dict:
        url = BASE_URL + path
        key = cache_key(source, url, params)
        if self.cache.lookup(self.sport, source, key) is None and not self.cache.offline:
            if self.credits_spent + expected_cost > self.max_credits:
                raise BudgetExceeded(f"next call would spend {expected_cost} credits; "
                                     f"{self.credits_spent}/{self.max_credits} already spent this run")
        def fetch() -> Fetched:   # the key is only needed on a cache miss
            r = http_get(self.session, url, {**params, "apiKey": env("ODDS_API_KEY")}, self.limiter)
            return Fetched(r.status_code, dict(r.headers), r.text)

        rec = self.cache.get_or_fetch(sport=self.sport, source=source, data_date=data_date, url=url,
                                      params=params, fetch=fetch, cache_statuses=(200,))
        headers = body_json({"body": rec["headers_json"]}) or {}
        if rec["http_status"] != 200:
            raise OddsApiError(f"Odds API {path} -> HTTP {rec['http_status']}: {(rec['body'] or '')[:300]}")
        return {"record": rec, "headers": headers, "body": body_json(rec)}

    def _account(self, before_http: int, headers: dict, source: str) -> None:
        if self.cache.stats.get(f"http:{source}", 0) > before_http:     # a real request happened
            last = headers.get("x-requests-last")
            self.credits_spent += int(float(last)) if last is not None else 0
            if headers.get("x-requests-remaining") is not None:
                self.remaining = int(float(headers["x-requests-remaining"]))

    def historical_odds(self, *, sport_key: str, at: datetime, bookmakers: tuple[str, ...], markets: str = "h2h") -> dict:
        params = {"bookmakers": ",".join(bookmakers), "markets": markets, "oddsFormat": "decimal",
                  "dateFormat": "iso", "date": at.strftime("%Y-%m-%dT%H:%M:%SZ")}
        source = "oddsapi_hist"
        before = self.cache.stats.get(f"http:{source}", 0)
        res = self._request(f"/historical/sports/{sport_key}/odds", params, source=source,
                            data_date=at.date().isoformat(),
                            expected_cost=credits_per_snapshot(len(markets.split(",")), len(bookmakers)))
        self._account(before, res["headers"], source)
        return res["body"]

    def is_cached_historical(self, *, sport_key: str, at: datetime, bookmakers: tuple[str, ...], markets: str = "h2h") -> bool:
        params = {"bookmakers": ",".join(bookmakers), "markets": markets, "oddsFormat": "decimal",
                  "dateFormat": "iso", "date": at.strftime("%Y-%m-%dT%H:%M:%SZ")}
        url = f"{BASE_URL}/historical/sports/{sport_key}/odds"
        return self.cache.lookup(self.sport, "oddsapi_hist", cache_key("oddsapi_hist", url, params)) is not None
