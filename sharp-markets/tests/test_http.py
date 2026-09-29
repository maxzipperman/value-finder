"""markets.http: no secret ever leaves a failed request in error text or logs. The only network use is an
unresolvable .invalid host, which fails at name resolution; nothing reaches the Odds API."""
import logging
import traceback

import pytest
import requests

from markets import http

KEY, KEY2, KEY3 = "FAKESECRETKEY999", "FAKEAPIKEY2SECRET", "FAKETOKEN3SECRET"


def _everywhere(exc, caplog, capsys) -> dict:
    out = capsys.readouterr()
    return {"str": str(exc), "repr": repr(exc), "traceback": "".join(traceback.format_exception(exc)),
            "log": caplog.text, "stdout": out.out, "stderr": out.err}


def test_a_failed_request_never_shows_the_key(monkeypatch, caplog, capsys):
    """Audit 2 finding 1: requests puts the URL, key included, in its error text, and chains a urllib3 error
    that carries it too. After the last retry, the error has every secret blanked and no chained cause."""
    monkeypatch.setattr(http.time, "sleep", lambda s: None)
    caplog.set_level(logging.DEBUG)                                   # urllib3's debug lines included
    params = {"date": "2024-09-08T16:55:00Z", "apiKey": KEY, "api_key": KEY2, "token": KEY3}
    with pytest.raises(requests.ConnectionError) as ei:               # same exception type as before
        http.http_get(requests.Session(), "https://unresolvable.invalid/v4/historical/sports/x/odds", params,
                      http.RateLimiter(1e6), timeout=5, max_retries=1)
    exc = ei.value
    for where, text in _everywhere(exc, caplog, capsys).items():
        for secret in (KEY, KEY2, KEY3):
            assert secret not in text, f"{secret} in {where}"
    assert "unresolvable.invalid" in str(exc) and "apiKey=REDACTED" in str(exc)      # still says what failed
    assert "after 2 attempt(s)" in str(exc)
    assert exc.__cause__ is None and exc.__context__ is None and exc.__suppress_context__
    assert "retrying" in caplog.text                                  # the retry was logged, without the key


def test_errors_that_are_not_retried_are_scrubbed_too(caplog, capsys):
    class Broken:
        def get(self, url, params=None, timeout=None):
            raise requests.exceptions.InvalidURL(f"bad {url}?apiKey={params['apiKey']}&x=1 ({params})")

    with pytest.raises(requests.exceptions.InvalidURL) as ei:
        http.http_get(Broken(), "https://host.invalid/v4/sports", {"apiKey": KEY}, http.RateLimiter(1e6), max_retries=3)
    for where, text in _everywhere(ei.value, caplog, capsys).items():
        assert KEY not in text, where


def test_scrub_blanks_secret_parameters_and_their_values():
    assert http.scrub("GET /v4/x?date=1&apiKey=abc123XYZ&b=2") == "GET /v4/x?date=1&apiKey=REDACTED&b=2"
    for name in ("api_key", "key", "token", "APIKEY", "access_token"):
        assert http.scrub(f"https://h/p?{name}=s3cr3tv4lue&z=1") == f"https://h/p?{name}=REDACTED&z=1"
    assert http.scrub("date=2024&monkey=1&keys=2") == "date=2024&monkey=1&keys=2"    # other names untouched
    # the literal value anywhere, plain or URL-encoded, when the caller's params are known
    params = {"apiKey": "FAKE/SECRET KEY999"}
    text = "boom {'apiKey': 'FAKE/SECRET KEY999'} FAKE%2FSECRET%20KEY999 FAKE%2FSECRET+KEY999"
    assert "SECRET" not in http.scrub(text, params)


def test_urllib3_debug_lines_are_scrubbed(caplog):
    """urllib3 logs each request line, query string and key included, at DEBUG."""
    caplog.set_level(logging.DEBUG, logger="urllib3.connectionpool")
    logging.getLogger("urllib3.connectionpool").debug('%s://%s:%s "%s %s %s" %s %s', "https", "host.invalid", 443,
                                                      "GET", f"/v4/sports?apiKey={KEY}", "HTTP/1.1", 200, 10)
    assert KEY not in caplog.text and "apiKey=REDACTED" in caplog.text
