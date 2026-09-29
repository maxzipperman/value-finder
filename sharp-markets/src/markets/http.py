"""GET-only HTTP with a token-bucket rate limit and retry/backoff.

There is deliberately no POST/PUT/DELETE helper in this project (paper-only).

Secrets never leave this module in error text or logs. `requests` puts the full URL, query string and key
included, into its exception messages, and the urllib3 error it chains carries the URL too. So a request that
still fails after the last retry is raised again as the same exception type, with every secret blanked
(`scrub`) and nothing chained.

`scrub` blanks the value of any secret query parameter (apiKey, api_key, key, token, access_token), and also
every secret value http_get has sent in this process, wherever it appears: in a URL path, an echoed error body
or a log line. Log lines are scrubbed by a filter on every urllib3 and requests logger (urllib3 prints the
URL at DEBUG for each request and at WARNING when a response has a malformed header), and the `markets` CLI
puts the same filter on its log handlers, so every logger is covered there.
"""
from __future__ import annotations

import logging
import random
import re
import time
from typing import Callable
from urllib.parse import quote, quote_plus

import requests

log = logging.getLogger(__name__)

RETRY_STATUSES = {429, 500, 502, 503, 504}
USER_AGENT = "sharp-markets-research/0.1 (paper-only)"
REDACTED = "REDACTED"
SECRET_PARAMS = frozenset({"apikey", "api_key", "key", "token", "access_token"})    # compared lower-case
_SECRET_IN_QUERY = re.compile(r"(?i)([?&;](?:apikey|api_key|key|token|access_token)=)[^&#\s'\"<>)\]]*")
_KNOWN_SECRETS: set[str] = set()       # every secret value http_get has sent in this process, in each encoding


def remember_secret(value) -> None:
    """Blank this value from now on wherever `scrub` runs. Values under 8 characters are ignored: a real key is
    far longer, and a short one would blank ordinary words."""
    if value is not None and len(str(value)) >= 8:
        v = str(value)
        _KNOWN_SECRETS.update({v, quote(v, safe=""), quote_plus(v)})


def scrub(text, params: dict | None = None) -> str:
    """`text` with secrets blanked: the value of any apiKey, api_key, key, token or access_token query parameter
    (any case), every secret value http_get has sent, and the secret values in `params`, plain or URL-encoded,
    wherever they appear."""
    text = str(text)
    extra = set()
    for k, v in (params or {}).items():
        if str(k).lower() in SECRET_PARAMS and v is not None and len(str(v)) >= 6:
            extra |= {str(v), quote(str(v), safe=""), quote_plus(str(v))}
    for form in sorted(_KNOWN_SECRETS | extra, key=len, reverse=True):
        text = text.replace(form, REDACTED)
    return _SECRET_IN_QUERY.sub(r"\1" + REDACTED, text)


class _ScrubSecrets(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
            clean = scrub(msg)
            if clean != msg:
                record.msg, record.args = clean, ()
            if record.exc_info and not record.exc_text:
                record.exc_text = logging.Formatter().formatException(record.exc_info)
            if record.exc_text:
                record.exc_text = scrub(record.exc_text)
        except Exception:                # noqa: BLE001 - a filter must never break the program's logging
            pass
        return True


_FILTER = _ScrubSecrets()
# A logger's filter only sees records logged on that logger itself, not its children's, so each is named.
# urllib3.connectionpool prints '"GET /path?apiKey=... HTTP/1.1" 200' at DEBUG; urllib3.connection prints
# 'Failed to parse headers (url=...?apiKey=...)' at WARNING.
for _name in ["urllib3", "urllib3.connection", "urllib3.connectionpool", "urllib3.poolmanager", "urllib3.response",
              "urllib3.util", "urllib3.util.retry", "requests", *(n for n in list(logging.root.manager.loggerDict)
                                                                  if n.startswith(("urllib3.", "requests.")))]:
    if _FILTER not in logging.getLogger(_name).filters:
        logging.getLogger(_name).addFilter(_FILTER)


def scrub_log_handlers(logger: logging.Logger | None = None) -> None:
    """Put the scrub filter on every handler of `logger` (the root logger by default). A handler's filter sees
    every record that reaches it, from any logger, so this covers loggers not named above."""
    for h in (logger or logging.getLogger()).handlers:
        if _FILTER not in h.filters:
            h.addFilter(_FILTER)


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
        new = type(exc)(text)
    except Exception:                    # noqa: BLE001 - an exception type with an unusual constructor
        new = requests.RequestException(text)
    new.attempts = attempts
    return new


def http_get(session: requests.Session, url: str, params: dict, limiter: RateLimiter,
             *, timeout: float = 60, max_retries: int = 6,
             before_retry: Callable[[str], None] | None = None) -> requests.Response:
    """GET with retries on 429/5xx/network errors. Honors Retry-After. Returns the final response.

    A network error or timeout that outlasts the retries, and any other `requests` error, is raised as the
    same exception type with the secrets in its text blanked (`scrub`) and no chained cause; its `attempts`
    says how many requests were sent.

    `before_retry(why)` is called before each retry, with why = the error's type name or "HTTP <status>". A
    paid caller uses it to count the attempt that got no usable answer (it may have been billed) and to check
    its budget before asking again; whatever it raises propagates, and no retry is sent."""
    for k, v in params.items():
        if str(k).lower() in SECRET_PARAMS:
            remember_secret(v)
    failure: requests.RequestException | None = None
    for attempt in range(max_retries + 1):
        limiter.wait()
        error: str | None = None
        try:
            resp = session.get(url, params=params, timeout=timeout)
        except (requests.ConnectionError, requests.Timeout) as exc:
            if attempt == max_retries:
                failure = _scrubbed(exc, params, attempt + 1)
                break
            error = exc.__class__.__name__
        except requests.RequestException as exc:     # not retried (invalid URL, too many redirects, ...)
            failure = _scrubbed(exc, params, attempt + 1)
            break
        if error is not None:
            delay, what = _backoff(attempt), f"failed ({error})"
        elif resp.status_code in RETRY_STATUSES and attempt < max_retries:
            retry_after = resp.headers.get("Retry-After")
            delay = float(retry_after) if retry_after and retry_after.replace(".", "", 1).isdigit() else _backoff(attempt)
            error = f"HTTP {resp.status_code}"
            what = f"-> {error}"
        else:
            return resp
        if before_retry is not None:
            before_retry(error)          # outside any except block, so nothing holding the URL is chained to it
        log.warning("GET %s %s; retrying in %.1fs", scrub(url, params), what, delay)
        time.sleep(delay)
    if failure is not None:
        # Raised outside the except block, so the original exception (URL and key in its text) is not even
        # attached as __context__; `from None` keeps any traceback printer from looking for a cause.
        raise failure from None
    raise RuntimeError("unreachable")


def _backoff(attempt: int) -> float:
    return min(60.0, 1.5 * 2 ** attempt) + random.uniform(0, 0.5)
