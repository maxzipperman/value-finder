"""GET-only HTTP with a token-bucket rate limit and retry/backoff.

There is deliberately no POST/PUT/DELETE helper in this project (paper-only).
"""
from __future__ import annotations

import logging
import random
import time

import requests

log = logging.getLogger(__name__)

RETRY_STATUSES = {429, 500, 502, 503, 504}
USER_AGENT = "sharp-markets-research/0.1 (paper-only)"


class RateLimiter:
    def __init__(self, per_sec: float):
        self.interval = 1.0 / per_sec
        self._next = 0.0

    def wait(self) -> None:
        now = time.monotonic()
        if now < self._next:
            time.sleep(self._next - now)
        self._next = max(now, self._next) + self.interval


def new_session(user_agent: str | None = USER_AGENT) -> requests.Session:
    """`user_agent=None` keeps the requests default (some CDNs, e.g. ESPN, reject custom agents)."""
    s = requests.Session()
    if user_agent:
        s.headers["User-Agent"] = user_agent
    return s


def http_get(session: requests.Session, url: str, params: dict, limiter: RateLimiter,
             *, timeout: float = 60, max_retries: int = 6) -> requests.Response:
    """GET with retries on 429/5xx/network errors. Honors Retry-After. Returns the final response."""
    for attempt in range(max_retries + 1):
        limiter.wait()
        try:
            resp = session.get(url, params=params, timeout=timeout)
        except (requests.ConnectionError, requests.Timeout) as exc:
            if attempt == max_retries:
                raise
            delay = _backoff(attempt)
            log.warning("GET %s failed (%s); retrying in %.1fs", url, exc.__class__.__name__, delay)
            time.sleep(delay)
            continue
        if resp.status_code in RETRY_STATUSES and attempt < max_retries:
            retry_after = resp.headers.get("Retry-After")
            delay = float(retry_after) if retry_after and retry_after.replace(".", "", 1).isdigit() else _backoff(attempt)
            log.warning("GET %s -> %s; retrying in %.1fs", url, resp.status_code, delay)
            time.sleep(delay)
            continue
        return resp
    raise RuntimeError("unreachable")


def _backoff(attempt: int) -> float:
    return min(60.0, 1.5 * 2 ** attempt) + random.uniform(0, 0.5)
