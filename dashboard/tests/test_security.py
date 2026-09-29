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


def test_a_link_in_the_static_folder_is_never_followed(tmp_path, monkeypatch):
    """A link planted in the static folder (to a .env file, to STATUS.md, even to a file beside it) is not served
    and not opened."""
    import os
    import shutil

    from vfdash import server
    folder = tmp_path / "static"
    shutil.copytree(server.STATIC_DIR, folder)
    env = tmp_path / "nfl-weather" / ".env"
    env.parent.mkdir()
    env.write_text("ODDS_API_KEY=FAKEKEY-SECRET\n")
    (tmp_path / "STATUS.md").write_text("# Value Finder: status\n")
    os.symlink(env, folder / "leak.css")
    os.symlink(tmp_path / "STATUS.md", folder / "status.html")
    os.symlink(folder / "app.js", folder / "again.js")
    monkeypatch.setattr(server, "STATIC_DIR", folder)
    opened = []
    real_os_open, real_open = os.open, builtins.open

    def spy_os_open(path, *a, **k):
        opened.append(os.path.realpath(path))
        return real_os_open(path, *a, **k)

    def spy_open(file, *a, **k):
        if isinstance(file, (str, os.PathLike)):
            opened.append(os.path.realpath(file))
        return real_open(file, *a, **k)
    monkeypatch.setattr(os, "open", spy_os_open)
    monkeypatch.setattr(builtins, "open", spy_open)
    monkeypatch.setattr(io, "open", spy_open)
    table = server.static_table()
    assert set(table) == {"/", "/static/index.html", "/static/app.css", "/static/app.js"}
    assert not any(b"FAKEKEY" in body or b"Value Finder: status" in body for body, _ in table.values())
    assert str(env.resolve()) not in opened and str((tmp_path / "STATUS.md").resolve()) not in opened


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
    store.snapshot()                                  # the files as read in the last 30 seconds
    monkeypatch.setattr(builtins, "open", spy)
    monkeypatch.setattr(io, "open", spy)
    before = len(runner.calls)
    status, payload = api.game(store, bad)
    assert status == 400
    assert "isn't a game id" in payload["error"]
    assert payload["header"]["last_written"].startswith("Last run")      # the page's stamp is this screen's
    assert opened == []                               # a refused id opens nothing
    assert runner.calls[before:] == []                # and starts nothing


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


def test_a_burst_of_requests_waits_in_line():
    from vfdash.server import LocalServer
    assert LocalServer.request_queue_size >= 64


def closed_by_server(sock, wait: float) -> bool:
    sock.settimeout(wait)
    try:
        return sock.recv(1024) == b""                 # closed, with no answer
    except ConnectionResetError:
        return True
    except TimeoutError:
        return False


def test_a_request_that_is_never_finished_is_dropped(store, monkeypatch, capsys):
    """A connection that sends part of a request and waits, or drips it a byte at a time, is closed once the time
    for a request is up, so a pile of them can't use up the server; it answers everyone else meanwhile."""
    import socket
    import threading
    import time

    from conftest import Running
    from vfdash import server
    monkeypatch.setattr(server, "REQUEST_SECONDS", 1.0, raising=False)
    s = Running(store)
    stop = threading.Event()
    try:
        idle = socket.create_connection(("127.0.0.1", s.port))
        idle.sendall(b"GET /api/summary HTTP/1.1\r\nHost: 127.0.0.1\r\n")        # never the blank line
        half = socket.create_connection(("127.0.0.1", s.port))
        half.sendall(b"GET /api/summ")                                          # not even the first line
        drip = socket.create_connection(("127.0.0.1", s.port))
        drip.sendall(b"GET /api/summary HTTP/1.1\r\n")

        def dripping():
            while not stop.is_set():
                try:
                    drip.sendall(b"X")
                except OSError:
                    return
                time.sleep(0.2)
        threading.Thread(target=dripping, daemon=True).start()
        assert s.get("/api/summary")[0] == 200
        t0 = time.monotonic()
        assert closed_by_server(idle, 6) and closed_by_server(drip, 6) and closed_by_server(half, 6)
        assert time.monotonic() - t0 < 5
        # a request sent in full is answered as before
        assert s.get("/api/summary")[0] == 200
    finally:
        stop.set()
        s.close()
    assert "Exception occurred" not in capsys.readouterr().err       # dropped quietly, not with a traceback


def test_the_open_file_limit_is_raised_at_start(monkeypatch):
    """launchd starts its jobs with a soft limit of 256 open files; each connection holds one."""
    import errno
    import resource

    from vfdash import server
    inf = resource.RLIM_INFINITY
    for soft, hard, want in ((256, inf, (4096, inf)), (256, 1024, (1024, 1024)), (8192, inf, None), (inf, inf, None)):
        calls = []
        server.raise_open_file_limit(get=lambda _, s=soft, h=hard: (s, h), set_=lambda _, v, c=calls: c.append(v))
        assert calls == ([want] if want else []), (soft, hard)
    order = []
    monkeypatch.setattr(server, "raise_open_file_limit", lambda: order.append("limit"))

    def busy(*a, **k):
        order.append("bind")
        raise OSError(errno.EADDRINUSE, "in use")
    monkeypatch.setattr(server, "make_server", busy)
    with pytest.raises(server.PortInUse):
        server.serve(store=None, port=8787)
    assert order == ["limit", "bind"]


def test_security_headers(served):
    status, body, headers = served.get("/")
    csp = headers["Content-Security-Policy"]
    assert "default-src 'none'" in csp and "connect-src 'self'" in csp and "script-src 'self'" in csp
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert "Access-Control-Allow-Origin" not in headers
