"""GET-only HTTP with a token-bucket rate limit and retry/backoff.

There is deliberately no POST/PUT/DELETE helper in this project (paper-only).

Secrets never leave this module in error text. `requests` puts the full URL, query string and key included,
into its exception messages, and the urllib3 error it chains carries the URL too. So a request that still
fails after the last retry is raised again as the same exception type, with every secret blanked (`scrub`)
and nothing chained. urllib3's own debug log line, which also prints the URL with its query, is scrubbed
by a logging filter.
"""
from __future__ import annotations

import logging
import random
import re
import time
from urllib.parse import quote, quote_plus

import requests

log = logging.getLogger(__name__)

RETRY_STATUSES = {429, 500, 502, 503, 504}
USER_AGENT = "sharp-markets-research/0.1 (paper-only)"
REDACTED = "REDACTED"
SECRET_PARAMS = frozenset({"apikey", "api_key", "key", "token", "access_token"})    # compared lower-case
_SECRET_IN_QUERY = re.compile(r"(?i)([?&;](?:apikey|api_key|key|token|access_token)=)[^&#\s'\"<>)\]]*")


def scrub(text, params: dict | None = None) -> str:
    """`text` with secrets blanked: the value of any apiKey, api_key, key or token query parameter (any case),
    and the literal values of those parameters in `params`, plain or URL-encoded, wherever they appear."""
    text = str(text)
    for k, v in (params or {}).items():
        if str(k).lower() in SECRET_PARAMS and v is not None and len(str(v)) >= 6:
            for form in {str(v), quote(str(v), safe=""), quote_plus(str(v))}:
                text = text.replace(form, REDACTED)
    return _SECRET_IN_QUERY.sub(r"\1" + REDACTED, text)


class _ScrubSecrets(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        clean = scrub(msg)
        if clean != msg:
            record.msg, record.args = clean, ()
        return True


# urllib3 logs '"GET /path?apiKey=... HTTP/1.1" 200' at DEBUG for every request it sends.
logging.getLogger("urllib3.connectionpool").addFilter(_ScrubSecrets())


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


def _scrubbed(exc: requests.RequestException, params: dict, attempts: int) -> requests.RequestException:
    """A new exception of the same type whose text has the secrets blanked. It carries no request, response
    or chained cause, so nothing that holds the URL travels with it."""
    text = f"{scrub(str(exc), params)} [GET failed after {attempts} attempt(s)]"
    try:
        return type(exc)(text)
    except Exception:                    # noqa: BLE001 - an exception type with an unusual constructor
        return requests.RequestException(text)


def http_get(session: requests.Session, url: str, params: dict, limiter: RateLimiter,
             *, timeout: float = 60, max_retries: int = 6) -> requests.Response:
    """GET with retries on 429/5xx/network errors. Honors Retry-After. Returns the final response.

    A network error or timeout that outlasts the retries, and any other `requests` error, is raised as the
    same exception type with the secrets in its text blanked (`scrub`) and no chained cause."""
    failure: requests.RequestException | None = None
    for attempt in range(max_retries + 1):
        limiter.wait()
        try:
            resp = session.get(url, params=params, timeout=timeout)
        except (requests.ConnectionError, requests.Timeout) as exc:
            if attempt == max_retries:
                failure = _scrubbed(exc, params, attempt + 1)
                break
            delay = _backoff(attempt)
            log.warning("GET %s failed (%s); retrying in %.1fs", scrub(url, params), exc.__class__.__name__, delay)
            time.sleep(delay)
            continue
        except requests.RequestException as exc:     # not retried (invalid URL, too many redirects, ...)
            failure = _scrubbed(exc, params, attempt + 1)
            break
        if resp.status_code in RETRY_STATUSES and attempt < max_retries:
            retry_after = resp.headers.get("Retry-After")
            delay = float(retry_after) if retry_after and retry_after.replace(".", "", 1).isdigit() else _backoff(attempt)
            log.warning("GET %s -> %s; retrying in %.1fs", scrub(url, params), resp.status_code, delay)
            time.sleep(delay)
            continue
        return resp
    if failure is not None:
        # Raised outside the except block, so the original exception (URL and key in its text) is not even
        # attached as __context__; `from None` keeps any traceback printer from looking for a cause.
        raise failure from None
    raise RuntimeError("unreachable")


def _backoff(attempt: int) -> float:
    return min(60.0, 1.5 * 2 ** attempt) + random.uniform(0, 0.5)
