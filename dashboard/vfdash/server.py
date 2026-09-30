"""The HTTP server: 127.0.0.1 only, GET only, a fixed set of routes.

* Static files are looked up by name in a table built at start-up from the static folder; no part of a
  URL ever becomes a file path, so nothing outside that folder can be served.
* The only query value used is a game id, which must match a strict pattern and is then only a key into
  the ledgers already read.
* A request whose Host header isn't this machine's loopback address is refused, so a web page elsewhere
  can't read the dashboard through a rebound domain name.
* A request must arrive in full within REQUEST_SECONDS; a connection that sends part of one and waits, or drips
  it a byte at a time, is closed, so a pile of them can't hold every thread and file the server has.
"""
from __future__ import annotations

import errno
import io
import json
import logging
import os
import sys
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from . import api
from .data import PROJECTS, Store
from .readers import Refused, refuse

HOST = "127.0.0.1"
STATIC_DIR = Path(__file__).resolve().parent / "static"
TYPES = {".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8",
         ".js": "text/javascript; charset=utf-8", ".svg": "image/svg+xml", ".png": "image/png"}
CSP = ("default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; "
       "base-uri 'none'; form-action 'none'; frame-ancestors 'none'")
log = logging.getLogger("vfdash")
REQUEST_SECONDS = 15.0              # the request line and headers must all arrive within this
WRITE_SECONDS = 30.0                # each send of the answer may wait this long for the browser
OPEN_FILES = 4096                   # launchd starts its jobs with a soft limit of 256; each connection holds one


def _read_not_a_link(p: Path) -> bytes | None:
    """The file's bytes, opened without following a link (None if it is one, or can't be read)."""
    try:
        fd = os.open(refuse(p), os.O_RDONLY | os.O_NOFOLLOW)
    except (OSError, ValueError, Refused):
        return None
    with os.fdopen(fd, "rb") as f:
        return f.read()


def static_table() -> dict[str, tuple[bytes, str]]:
    """{url path: (bytes, content type)} for each plain file directly inside the static folder. A link is never
    followed: it could lead anywhere, a .env file included."""
    table = {}
    for p in sorted(STATIC_DIR.iterdir()):
        if p.is_symlink() or not p.is_file() or p.suffix not in TYPES or p.name.startswith("."):
            continue
        body = _read_not_a_link(p)
        if body is not None:
            table[f"/static/{p.name}"] = (body, TYPES[p.suffix])
    if "/static/index.html" in table:
        table["/"] = table["/static/index.html"]
    return table


class _Deadline(io.RawIOBase):
    """A connection's incoming bytes, with one deadline for the whole request rather than one per read."""

    def __init__(self, sock, seconds: float):
        self.sock, self.until = sock, time.monotonic() + seconds

    def readable(self) -> bool:
        return True

    def readinto(self, b) -> int:
        left = self.until - time.monotonic()
        if left <= 0:
            raise TimeoutError("the request was not finished in time")
        self.sock.settimeout(left)
        return self.sock.recv_into(b)


class Handler(BaseHTTPRequestHandler):
    server_version = "vfdash"
    sys_version = ""
    store: Store = None                       # set by make_server
    static: dict = {}
    port: int = 0
    timeout = WRITE_SECONDS

    def setup(self):
        super().setup()
        self.rfile.close()                    # the plain reader, replaced by one with a deadline for the request
        self.rfile = io.BufferedReader(_Deadline(self.connection, REQUEST_SECONDS))

    def parse_request(self) -> bool:
        ok = super().parse_request()          # the request line and headers have been read by now
        self.connection.settimeout(WRITE_SECONDS)
        return ok

    # ------------------------------------------------------------ plumbing
    def log_message(self, fmt, *args):       # one short line per request, never a query string
        command = getattr(self, "command", None) or "-"   # not set when the first line never arrived
        path = urlsplit(getattr(self, "path", "") or "").path[:80]
        if fmt.startswith("Request timed out"):
            log.info("%s %s dropped: the request was not finished in time", command, path)
        else:
            log.info("%s %s %s", command, path, args[1] if len(args) > 1 else "")

    def _send(self, status: int, body: bytes, ctype: str, cache: bool = False):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache" if cache else "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Content-Security-Policy", CSP)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, status: int, payload: dict):
        self._send(status, json.dumps(payload, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def _text(self, status: int, text: str):
        self._send(status, text.encode("utf-8"), "text/plain; charset=utf-8")

    def _host_ok(self) -> bool:
        host = (self.headers.get("Host") or "").strip().lower()
        return host in {f"127.0.0.1:{self.port}", f"localhost:{self.port}", "127.0.0.1", "localhost"}

    # ------------------------------------------------------------ methods
    def do_GET(self):
        try:
            self._route()
        except Exception as e:                            # noqa: BLE001 (never an error page)
            log.exception("request failed")
            self._json(200, {"error": f"This screen could not be built ({type(e).__name__}). The dashboard is "
                                      "still running; try again in a minute.", "notes": []})

    def do_HEAD(self):
        self.do_GET()

    def _refuse(self):
        self.send_response(HTTPStatus.METHOD_NOT_ALLOWED)
        self.send_header("Allow", "GET, HEAD")
        self.send_header("Content-Length", "0")
        self.end_headers()

    do_POST = do_PUT = do_DELETE = do_PATCH = do_OPTIONS = _refuse

    def _route(self):
        if not self._host_ok():
            return self._text(403, "This dashboard answers only at http://127.0.0.1.")
        parts = urlsplit(self.path)
        path = parts.path
        if path in self.static:
            body, ctype = self.static[path]
            return self._send(200, body, ctype, cache=True)
        store = self.store
        if path == "/api/summary":
            with store.lock:
                return self._json(200, api.summary(store))
        if path == "/api/home":
            with store.lock:
                return self._json(200, api.home(store))
        if path == "/api/board":
            with store.lock:
                return self._json(200, api.board(store))
        if path == "/api/game":
            try:
                values = parse_qs(parts.query, keep_blank_values=True, max_num_fields=5).get("id", [""])
            except ValueError:
                values = [""]
            with store.lock:
                status, payload = api.game(store, values[0] if len(values) == 1 else "")
            return self._json(status, payload)
        if path == "/api/tests":
            for p in PROJECTS:                            # the slow part, outside the lock
                store.scorer(p, wait=True)
            with store.lock:
                return self._json(200, api.tests_screen(store))
        if path == "/api/signals":
            for p in PROJECTS:                            # the slow part, outside the lock
                store.scorer(p, wait=True)
            with store.lock:
                return self._json(200, api.signals_screen(store))
        if path == "/api/jobs":
            with store.lock:
                return self._json(200, api.jobs_screen(store))
        if path == "/api/run-records":
            with store.lock:
                return self._json(200, api.run_records(store))
        if path == "/api/pull":
            with store.lock:
                return self._json(200, api.pull(store))
        if path == "/api/backtests":
            with store.lock:
                return self._json(200, api.backtests(store))
        if path == "/api/research":
            with store.lock:
                return self._json(200, api.research(store))
        return self._text(404, "Not found.")


class LocalServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True
    request_queue_size = 64                               # a burst of requests waits instead of being dropped


def make_server(store: Store, host: str = HOST, port: int = 8787) -> LocalServer:
    """The server, bound to 127.0.0.1 and nowhere else."""
    if host != HOST:
        raise ValueError(f"the dashboard binds only to {HOST}, not {host!r}")
    handler = type("BoundHandler", (Handler,), {"store": store, "static": static_table()})
    server = LocalServer((HOST, port), handler)
    bound = server.server_address[0]
    if bound != HOST:                                     # belt and braces
        server.server_close()
        raise ValueError(f"the dashboard bound to {bound!r}, not {HOST}")
    handler.port = server.server_address[1]
    return server


class PortInUse(Exception):
    """Another program (often a second copy of the dashboard) already listens on the port."""


def raise_open_file_limit(get=None, set_=None) -> None:
    """Raise this process's soft limit on open files to OPEN_FILES (or the hard limit, if lower)."""
    import resource
    get, set_ = get or resource.getrlimit, set_ or resource.setrlimit
    try:
        soft, hard = get(resource.RLIMIT_NOFILE)
        want = OPEN_FILES if hard == resource.RLIM_INFINITY else min(OPEN_FILES, hard)
        if soft != resource.RLIM_INFINITY and soft < want:
            set_(resource.RLIMIT_NOFILE, (want, hard))
    except (ValueError, OSError):             # not allowed here: keep the limit it has
        pass


def serve(store: Store, port: int):
    logging.basicConfig(level=logging.INFO, stream=sys.stderr, format="%(asctime)s %(message)s")
    raise_open_file_limit()
    try:
        server = make_server(store, HOST, port)
    except OSError as e:
        if e.errno == errno.EADDRINUSE:
            raise PortInUse(port) from None
        raise
    store.warm()
    print(f"Value Finder dashboard (paper only, read-only): http://{HOST}:{server.server_address[1]}/", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
