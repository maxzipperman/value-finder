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


def _local_server(response: bytes):
    """A tiny HTTP server on 127.0.0.1 that answers every request with `response` (no other network is used)."""
    import socket
    import threading
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    sock.listen(4)

    def serve():
        while True:
            try:
                conn, _ = sock.accept()
            except OSError:
                return
            with conn:
                data = b""
                while b"\r\n\r\n" not in data:
                    chunk = conn.recv(65536)
                    if not chunk:
                        break
                    data += chunk
                conn.sendall(response)

    threading.Thread(target=serve, daemon=True).start()
    return sock


def test_a_malformed_header_warning_never_shows_the_key(monkeypatch, caplog, capsys):
    """Audit 2 review, blocker: urllib3.connection logs 'Failed to parse headers (url=...)' at WARNING, which the
    CLI shows, with the full URL and key. The filter used to sit only on urllib3.connectionpool."""
    body = b'{"timestamp": "2024-09-08T16:55:00Z", "data": []}'
    sock = _local_server(b"HTTP/1.1 200 OK\r\nx-requests-last: 30\r\nBrokenHeaderWithoutAColon\r\n"
                         b"Content-Type: application/json\r\nContent-Length: %d\r\nConnection: close\r\n\r\n" % len(body)
                         + body)
    caplog.set_level(logging.WARNING)
    try:
        r = http.http_get(requests.Session(), f"http://127.0.0.1:{sock.getsockname()[1]}/v4/historical/x/odds",
                          {"date": "2024-09-08T16:55:00Z", "apiKey": KEY}, http.RateLimiter(1e6), timeout=5,
                          max_retries=0)
    finally:
        sock.close()
    assert r.status_code == 200
    assert "Failed to parse headers" in caplog.text and "apiKey=REDACTED" in caplog.text
    assert KEY not in caplog.text and KEY not in capsys.readouterr().err


def test_the_cli_scrubs_every_logger_and_known_keys_anywhere(caplog):
    """Audit 2 review: the markets CLI puts the filter on its log handlers, so any logger is covered, and a key
    http_get has sent is blanked wherever it shows up, even without a parameter name (a URL path, an echoed body,
    a traceback)."""
    import io

    from markets import cli
    with pytest.raises(SystemExit):
        cli.main([])                                                 # sets up logging, then argparse exits
    root = logging.getLogger()
    assert root.handlers and all(http._FILTER in h.filters for h in root.handlers)
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    root.addHandler(handler)
    http.scrub_log_handlers()
    try:
        http.remember_secret("LITERALSECRET9")
        other = logging.getLogger("some.library")
        other.warning("GET https://h/p?token=%s&x=1", "SOMETOKEN123")
        other.warning("redirected to /moved/LITERALSECRET9 and %s", "LITERALSECRET9")
        try:
            raise ValueError("boom /v4/sports?apiKey=ABCDEFG12345 LITERALSECRET9")
        except ValueError:
            other.exception("it failed")
    finally:
        root.removeHandler(handler)
    text = stream.getvalue()
    for secret in ("SOMETOKEN123", "LITERALSECRET9", "ABCDEFG12345"):
        assert secret not in text, secret
    assert text.count("REDACTED") >= 5 and "Traceback" in text
    assert http.scrub("GET /moved/LITERALSECRET9 HTTP/1.1") == "GET /moved/REDACTED HTTP/1.1"


def test_before_retry_can_stop_a_retry_and_nothing_holding_the_key_is_chained(monkeypatch):
    """The bulk puller's retry check: whatever before_retry raises propagates, no further request is sent, and
    the raised error carries no chained exception holding the URL."""
    monkeypatch.setattr(http.time, "sleep", lambda s: None)
    sent, whys = [], []

    class Flaky:
        def get(self, url, params=None, timeout=None):
            sent.append(url)
            raise requests.ReadTimeout(f"read timed out: {url}?apiKey={params['apiKey']}")

    class Refused(RuntimeError):
        pass

    def check(why, resp):
        whys.append((why, resp))
        raise Refused("no budget for a retry")

    with pytest.raises(Refused) as ei:
        http.http_get(Flaky(), "https://h.invalid/v4/x", {"apiKey": KEY}, http.RateLimiter(1e6), max_retries=6,
                      before_retry=check)
    assert len(sent) == 1 and whys == [("ReadTimeout", None)]         # no answer: no response to count
    assert ei.value.__context__ is None and KEY not in "".join(traceback.format_exception(ei.value))


def test_urllib3_debug_lines_are_scrubbed(caplog):
    """urllib3 logs each request line, query string and key included, at DEBUG."""
    caplog.set_level(logging.DEBUG, logger="urllib3.connectionpool")
    logging.getLogger("urllib3.connectionpool").debug('%s://%s:%s "%s %s %s" %s %s', "https", "host.invalid", 443,
                                                      "GET", f"/v4/sports?apiKey={KEY}", "HTTP/1.1", 200, 10)
    assert KEY not in caplog.text and "apiKey=REDACTED" in caplog.text
