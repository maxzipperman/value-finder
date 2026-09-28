"""Copied from nfl-weather; keep the two in sync.

Alert delivery: macOS Notification Center and (optionally) an iPhone push via
ntfy (https://ntfy.sh). ntfy needs no account: install the app, subscribe to the
topic in .env, and anything POSTed to that topic arrives as a push."""
from __future__ import annotations

import os
import subprocess

from .config import ROOT
from .fetch import session


def _env(name):
    v = os.environ.get(name)
    env = ROOT / ".env"
    if not v and env.exists():
        for line in env.read_text().splitlines():
            if line.strip().startswith(name + "="):
                v = line.split("=", 1)[1].strip().strip('"').strip("'")
    return v or None


def mac(title, body, sound="Glass"):
    esc = lambda s: s.replace("\\", "\\\\").replace('"', '\\"')
    script = f'display notification "{esc(body)}" with title "{esc(title)}" sound name "{sound}"'
    subprocess.run(["osascript", "-e", script], check=False, capture_output=True)


def phone(title, body, priority=4, tags=("football",)):
    topic = _env("NTFY_TOPIC")
    if not topic:
        return False
    r = session.post("https://ntfy.sh/", json=dict(topic=topic, title=title, message=body,
                                                    priority=priority, tags=list(tags)), timeout=20)
    return r.ok


def send(title, body):
    mac(title, body)
    return phone(title, body)
