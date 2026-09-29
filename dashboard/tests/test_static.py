"""The page loads nothing from the internet: the static files reference no http:// or https:// address other
than 127.0.0.1, and every script and stylesheet is local."""
from __future__ import annotations

import re
from pathlib import Path

STATIC = Path(__file__).resolve().parents[1] / "vfdash" / "static"


def test_no_outside_addresses():
    files = [p for p in STATIC.iterdir() if p.is_file()]
    assert {p.name for p in files} == {"index.html", "app.css", "app.js"}
    for p in files:
        text = p.read_text()
        for url in re.findall(r"(?i)\bhttps?://[^\s\"'<>)]*", text):
            assert url.lower().startswith(("http://127.0.0.1", "https://127.0.0.1")), (p.name, url)
        assert not re.search(r"(?i)(src|href)\s*=\s*[\"']//", text), p.name        # no scheme-relative links


def test_html_references_only_local_files():
    html = (STATIC / "index.html").read_text()
    for ref in re.findall(r'(?:src|href)="([^"]+)"', html):
        assert ref.startswith(("/static/", "#")) or ref == "data:,", ref
    assert "<script src=\"/static/app.js\">" in html
    assert re.search(r"@import|url\(\s*['\"]?https?:", (STATIC / "app.css").read_text()) is None


def test_no_network_calls_but_its_own_api():
    js = (STATIC / "app.js").read_text()
    for m in re.findall(r"fetch\(([^,)]+)", js):
        assert "screen.url" in m, m
    for m in re.findall(r'url: \([^)]*\) => ([^,}]+)', js):
        assert m.strip().startswith(('"/api/', '(r.arg')), m
    for banned in ("XMLHttpRequest", "WebSocket", "EventSource", "sendBeacon", "import(", "eval(", "new Function"):
        assert banned not in js


def test_a_damaged_address_falls_back_to_home():
    """decodeURIComponent throws on a damaged address (#game/%E0%A4%A); the page must not get stuck."""
    js = (STATIC / "app.js").read_text()
    body = js.split("function parseHash()", 1)[1].split("\n  }\n", 1)[0]
    assert re.search(r"try\s*\{\s*raw = decodeURIComponent\(", body) and "catch" in body
    assert js.count("decodeURIComponent(") == 1


def test_paper_only_label_and_dark_mode():
    html = (STATIC / "index.html").read_text()
    assert "Paper only" in html
    css = (STATIC / "app.css").read_text()
    assert "prefers-color-scheme: dark" in css and ':root[data-theme="dark"]' in css
    assert not re.search(r"gradient\(|box-shadow|text-shadow", css)                  # flat: no gradients or shadows
    assert "!" not in html.split("<body>", 1)[1]                                # no exclamation marks on screen
