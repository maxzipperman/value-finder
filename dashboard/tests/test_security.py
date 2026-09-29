"""127.0.0.1 only; no path traversal out of the static folder; a game id or any query value with slashes, dots,
quotes or shell characters is refused or treated as plain text and never reaches a path or a command."""
from __future__ import annotations

import builtins
import http.client
import io

import pytest

from vfdash import api
from vfdash.server import HOST, make_server, static_table


@pytest.mark.parametrize("host", ["0.0.0.0", "", "localhost", "::", "::1", "192.168.1.10", "127.0.0.2"])
def test_refuses_to_bind_anywhere_else(store, host):
    with pytest.raises(ValueError):
        make_server(store, host, 0)


def test_binds_to_loopback(store):
    server = make_server(store, HOST, 0)
    try:
        assert server.server_address[0] == "127.0.0.1"
    finally:
        server.server_close()


def test_there_is_no_host_option():
    from vfdash.__main__ import main
    with pytest.raises(SystemExit):
        main(["--host", "0.0.0.0"])


def raw_get(port: int, path: str, host: str | None = None, method: str = "GET"):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    conn.putrequest(method, path, skip_host=True, skip_accept_encoding=True)
    conn.putheader("Host", host or f"127.0.0.1:{port}")
    conn.endheaders()
    r = conn.getresponse()
    body = r.read()
    conn.close()
    return r.status, body


TRAVERSALS = ["/static/../vfdash/server.py", "/static/%2e%2e/server.py", "/static/..%2fserver.py",
              "/static/..%2f..%2fpyproject.toml", "/static//etc/passwd", "//etc/passwd", "/../../etc/passwd",
              "/static/app.js/../../server.py", "/static/%2e%2e%2f%2e%2e%2fpyproject.toml", "/static/.",
              "/static/", "/static/../../../../../../etc/hosts", "/vfdash/server.py", "/pyproject.toml",
              "/static/app.js%00.html", "/STATUS.md", "/nfl-weather/.env", "/static/..\\server.py"]


@pytest.mark.parametrize("path", TRAVERSALS)
def test_no_path_traversal(served, path):
    status, body = raw_get(served.port, path)
    assert status == 404
    assert b"def " not in body and b"root:" not in body and b"[project]" not in body and b"SECRET" not in body


def test_static_table_is_only_the_static_folder():
    table = static_table()
    assert set(table) == {"/", "/static/index.html", "/static/app.css", "/static/app.js"}


def test_other_hosts_are_refused(served):
    for host in ("evil.example", "127.0.0.1.nip.io:%d" % served.port, "attacker.test:%d" % served.port):
        status, body = raw_get(served.port, "/api/summary", host=host)
        assert status == 403


@pytest.mark.parametrize("method", ["POST", "PUT", "DELETE", "PATCH", "OPTIONS"])
def test_only_get(served, method):
    status, _ = raw_get(served.port, "/api/summary", method=method)
    assert status == 405


BAD_IDS = ["../../etc/passwd", "..", ".", "a/b", "2026_05_BUF_NE/../x", "'; rm -rf / #", '"quoted"', "$(whoami)",
           "`id`", "a b", "x|y", "x;y", "x&y", "x>y", "..%2f", "%00", "nfl-weather/.env", ".env", "a" * 200,
           "\\..\\", "id=1&id=2"]


@pytest.mark.parametrize("bad", BAD_IDS)
def test_bad_game_ids_are_refused(store, runner, bad, monkeypatch):
    opened = []
    real_open = builtins.open

    def spy(file, *a, **k):
        opened.append(str(file))
        return real_open(file, *a, **k)
    monkeypatch.setattr(builtins, "open", spy)
    monkeypatch.setattr(io, "open", spy)
    before = len(runner.calls)
    status, payload = api.game(store, bad)
    assert status == 400
    assert "isn't a game id" in payload["error"]
    assert not any(bad in p for p in opened if bad not in ("", "."))
    for cmd, _cwd, _ in runner.calls[before:]:
        assert bad not in " ".join(cmd)


def test_bad_game_ids_over_http(served):
    for q in ("id=..%2F..%2Fetc%2Fpasswd", "id=%24(whoami)", "id=a%22b", "id=1&id=2", "id=",
              "x=" + "&x=".join(["1"] * 20)):
        status, body = raw_get(served.port, "/api/game?" + q)
        assert status == 400, q


def test_query_values_elsewhere_are_ignored(served):
    status, body = raw_get(served.port, "/api/board?sport=../../etc&signals=%24(rm%20-rf)")
    assert status == 200 and b'"games"' in body


def test_unknown_game_id_is_plain_text_lookup(store):
    status, payload = api.game(store, "2026_99_NOT_REAL")
    assert status == 404


def test_security_headers(served):
    status, body, headers = served.get("/")
    csp = headers["Content-Security-Policy"]
    assert "default-src 'none'" in csp and "connect-src 'self'" in csp and "script-src 'self'" in csp
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert "Access-Control-Allow-Origin" not in headers
