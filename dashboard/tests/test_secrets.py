"""No code path opens a file whose name is or ends with .env, and no key, key fingerprint or launchd
environment value ever appears in what the dashboard serves."""
from __future__ import annotations

import builtins
import io
import json
import os
from pathlib import Path

import pytest
from conftest import ENDPOINTS, FINGERPRINT, PLIST_SECRET, SECRET_KEY

from vfdash import api, readers
from vfdash.server import static_table


def is_env(p) -> bool:
    name = Path(str(p)).name.lower()
    return name == ".env" or name.endswith(".env") or name.startswith(".env.")


def test_no_env_file_is_ever_opened(store, monkeypatch):
    opened = []
    real_open, real_os_open = builtins.open, os.open

    def spy_open(file, *a, **k):
        opened.append(str(file))
        assert not is_env(file), f"opened {file}"
        return real_open(file, *a, **k)

    def spy_os_open(path, *a, **k):
        opened.append(str(path))
        assert not is_env(path), f"opened {path}"
        return real_os_open(path, *a, **k)
    monkeypatch.setattr(builtins, "open", spy_open)
    monkeypatch.setattr(io, "open", spy_open)
    monkeypatch.setattr(os, "open", spy_os_open)
    static_table()
    api.summary(store)
    api.home(store)
    api.board(store)
    for gid in ("2026_05_BUF_NE", "401000002", "2026_04_PIT_CLE", ".env"):
        api.game(store, gid)
    api.tests_screen(store)
    api.jobs_screen(store)
    api.run_records(store)
    api.pull(store)
    api.research(store)
    assert opened, "the spy saw no file opened at all"
    assert not [p for p in opened if is_env(p)]


@pytest.mark.parametrize("name", [".env", "prod.env", ".ENV", ".env.local", "x/.env"])
def test_readers_refuse_env_names(tmp_path, name):
    p = tmp_path / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("ODDS_API_KEY=x\n")
    with pytest.raises(readers.Refused):
        readers.read_text(p, "x")
    with pytest.raises(readers.Refused):
        readers.AppendOnlyCSV(p, "x", lambda h: (lambda r: r)).refresh()


def test_nothing_secret_is_served(served):
    for path in ENDPOINTS + ["/", "/static/app.js"]:
        status, body, _ = served.get(path)
        text = body.decode("utf-8", "replace")
        for secret in (SECRET_KEY, FINGERPRINT, PLIST_SECRET, "abcdef0123"):
            assert secret not in text, (path, secret)
        assert '"key"' not in text


def test_credit_file_keeps_only_whitelisted_fields(store):
    snap = store.snapshot()
    assert set(snap.quota) <= {"utc", "remaining", "used", "last", "project", "status"}
    assert FINGERPRINT not in json.dumps(snap.quota)
