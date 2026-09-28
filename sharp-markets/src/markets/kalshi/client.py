"""Kalshi public market-data client. GET ONLY — this project never places, amends, or cancels orders.

Routing: markets settled before the historical cutoff live under /historical/*; newer ones under the
live endpoints. The caller passes `historical=` per market (from where the market was listed).
"""
from __future__ import annotations

from ..cache import Fetched, RawCache, body_json
from ..http import RateLimiter, http_get, new_session
from ..settings import utcnow

BASE_URL = "https://api.elections.kalshi.com/trade-api/v2"
MAX_CANDLES_PER_REQUEST = 5000


class KalshiHTTPError(RuntimeError):
    def __init__(self, status: int, path: str, body: str):
        super().__init__(f"Kalshi GET {path} -> {status}: {body[:300]}")
        self.status = status


class KalshiClient:
    def __init__(self, sport: str, cache: RawCache, rate_per_sec: float = 10):
        self.sport = sport
        self.cache = cache
        self.session = new_session()
        self.limiter = RateLimiter(rate_per_sec)

    # -- plumbing ---------------------------------------------------------------------------------
    def _get(self, path: str, params: dict, *, source: str, data_date: str, key_extra: dict | None = None) -> dict:
        url = BASE_URL + path

        def fetch() -> Fetched:
            r = http_get(self.session, url, params, self.limiter)
            return Fetched(r.status_code, dict(r.headers), r.text)

        rec = self.cache.get_or_fetch(sport=self.sport, source=source, data_date=data_date, url=url,
                                      params=params, fetch=fetch, key_extra=key_extra)
        if rec["http_status"] != 200:
            raise KalshiHTTPError(rec["http_status"], path, rec["body"] or "")
        return body_json(rec)

    def _paginate(self, path: str, list_key: str, params: dict, *, source: str, data_date: str,
                  key_extra: dict | None = None, max_pages: int = 10_000) -> list[dict]:
        out: list[dict] = []
        cursor = None
        for _ in range(max_pages):
            p = {**params, **({"cursor": cursor} if cursor else {})}
            page = self._get(path, p, source=source, data_date=data_date, key_extra=key_extra)
            items = page.get(list_key) or []
            out.extend(items)
            cursor = page.get("cursor")
            if not cursor or not items:
                return out
        raise RuntimeError(f"pagination of {path} did not terminate")

    @staticmethod
    def _today() -> str:
        return utcnow().date().isoformat()

    # -- metadata ---------------------------------------------------------------------------------
    def historical_cutoff(self, as_of: str) -> dict:
        return self._get("/historical/cutoff", {}, source="kalshi_meta", data_date=self._today(),
                         key_extra={"as_of": as_of})

    def series(self, series_ticker: str, as_of: str) -> dict:
        return self._get(f"/series/{series_ticker}", {}, source="kalshi_meta", data_date=self._today(),
                         key_extra={"as_of": as_of})["series"]

    def series_fee_changes(self, series_ticker: str, as_of: str) -> list[dict]:
        d = self._get("/series/fee_changes", {"series_ticker": series_ticker, "show_historical": "true"},
                      source="kalshi_meta", data_date=self._today(), key_extra={"as_of": as_of})
        return d.get("series_fee_change_arr") or []

    def event_fee_changes(self, event_ticker: str, data_date: str, as_of: str) -> list[dict]:
        return self._paginate("/events/fee_changes", "event_fee_changes", {"event_ticker": event_ticker},
                              source="kalshi_event_fees", data_date=data_date, key_extra={"as_of": as_of})

    # -- listings ---------------------------------------------------------------------------------
    def events(self, series_ticker: str, as_of: str) -> list[dict]:
        return self._paginate("/events", "events", {"series_ticker": series_ticker, "limit": 200},
                              source="kalshi_events", data_date=self._today(), key_extra={"as_of": as_of})

    def markets(self, series_ticker: str, *, historical: bool, as_of: str) -> list[dict]:
        path = "/historical/markets" if historical else "/markets"
        return self._paginate(path, "markets", {"series_ticker": series_ticker, "limit": 1000},
                              source="kalshi_markets_hist" if historical else "kalshi_markets_live",
                              data_date=self._today(), key_extra={"as_of": as_of})

    # -- time series ------------------------------------------------------------------------------
    def candles(self, *, market_ticker: str, series_ticker: str, start_ts: int, end_ts: int,
                period_min: int, historical: bool, data_date: str) -> list[dict]:
        if (end_ts - start_ts) // (60 * period_min) >= MAX_CANDLES_PER_REQUEST:
            raise ValueError("candle window exceeds the 5,000-candle cap; chunk it first")
        path = (f"/historical/markets/{market_ticker}/candlesticks" if historical
                else f"/series/{series_ticker}/markets/{market_ticker}/candlesticks")
        d = self._get(path, {"start_ts": start_ts, "end_ts": end_ts, "period_interval": period_min},
                      source="kalshi_candles", data_date=data_date,
                      key_extra={"market_ticker": market_ticker, "endpoint": "historical" if historical else "live"})
        return d.get("candlesticks") or []

    def trades(self, *, market_ticker: str, min_ts: int, max_ts: int, historical: bool, data_date: str) -> list[dict]:
        path = "/historical/trades" if historical else "/markets/trades"
        return self._paginate(path, "trades",
                              {"ticker": market_ticker, "min_ts": min_ts, "max_ts": max_ts, "limit": 1000},
                              source="kalshi_trades", data_date=data_date,
                              key_extra={"endpoint": "historical" if historical else "live"})
