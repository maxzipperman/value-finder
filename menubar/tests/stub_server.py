#!/usr/bin/env python3
"""A stand-in for the dashboard's /api/summary, for the menu-bar light's self-tests only.

Serves fixed answers on 127.0.0.1 at a free port, prints the port on its first line,
and writes each path it is asked for to stderr. It reads no files and writes none.
"""
import json
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def summary(**changes):
    body = {"generated_utc": "2026-09-29T17:31:00Z", "health": "ok", "signals_live": 0,
            "games_on_board": 14, "next_run_local": "15:30", "credits_remaining": 19650,
            "problems": []}
    body.update(changes)
    return body


def without(field):
    return {k: v for k, v in summary().items() if k != field}


CASES = {
    "/ok-no-signals": summary(),
    "/ok-two-signals": summary(signals_live=2, credits_remaining=412),
    "/warn-one-problem": summary(health="warn", credits_remaining=38, next_run_local="19:30",
                                 problems=["Only 38 odds credits are left on the free plan."]),
    "/fail-two-problems": summary(health="fail", signals_live=1, next_run_local="07:30", problems=[
        "The college football alert job's last run failed while building the board.",
        "The close-capture job last exited with status 1."]),
    "/invalid-json": '{"generated_utc": "2026-09-29T17:31:00Z", "health": "ok", "signals_',
    "/missing-field": without("signals_live"),
    "/wrong-type": summary(signals_live="2"),
    "/credits-null": summary(signals_live=1, credits_remaining=None, next_run_local="00:05"),
    "/boolean-count": summary(games_on_board=True),
    "/unknown-health": summary(health="green"),
    "/many-problems": summary(health="fail", problems=["Problem %d." % n for n in range(1, 10)]
                              + ["  ", "A sentence\nwith a line break in it."]),
    "/extra-field": summary(signals_live=3, version="1"),
    "/utc-offset": summary(generated_utc="2026-09-29T17:31:00+00:00"),
    "/utc-minutes": summary(generated_utc="2026-09-29T17:31Z"),
    "/credits-negative": summary(credits_remaining=-5),
    # 512 objects inside one another: 3 KB of valid JSON that used to overflow the JSON
    # reader's stack and crash the app.
    "/deep-object": '{"a":' * 512 + "1" + "}" * 512,
    # Brackets and an escaped quote inside a problem's text are not nesting.
    "/brackets-in-text": summary(health="warn", problems=[
        'A problem that quotes "{[{[{[{[{[{[{[{[{[{[" and a backslash \\ in its text.']),
    # Every kind of line break becomes a space; an emoji family's joiners are kept;
    # a right-to-left override (an invisible control character) becomes a space.
    "/separators": summary(health="warn", problems=[
        "Line one line two line three\u0085line four\r\nline five.",
        "The family \U0001F468‍\U0001F469‍\U0001F467 stays together;‮ no reversed text."]),
    "/empty": "",
    "/slow": summary(),
}

# Answers far over the light's 256 KB limit. The light should stop reading, not fill memory.
LARGE = {"/too-large-length": 1 << 30, "/too-large-stream": 256 << 20}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        print("GET " + self.path, file=sys.stderr, flush=True)
        if self.path == "/redirect":  # the light must not follow this
            self.send_response(302)
            self.send_header("Location", "/followed-a-redirect")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if self.path == "/hang":  # accepts, then never answers within the light's 10 seconds
            time.sleep(15)
            return
        if self.path in LARGE:
            # /too-large-length announces 1 GB in its length header; /too-large-stream sends
            # 256 MB with no length header, so only counting the bytes can stop it.
            size = LARGE[self.path]
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            if self.path == "/too-large-length":
                self.send_header("Content-Length", str(size))
            self.end_headers()
            chunk = b" " * (1 << 20)
            try:
                for _ in range(size // len(chunk)):
                    self.wfile.write(chunk)
            except OSError:  # the light hung up, as it should
                pass
            return
        if self.path == "/slow":  # holds the connection open so it can be observed
            time.sleep(3)
        status, body = (200, CASES[self.path]) if self.path in CASES else (500, "<h1>error</h1>")
        data = (body if isinstance(body, str) else json.dumps(body)).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass


server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
print(server.server_address[1], flush=True)
server.serve_forever()
