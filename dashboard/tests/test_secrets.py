"""No code path opens a file whose name is or ends with .env, and no key, key fingerprint or launchd
environment value ever appears in what the dashboard serves."""
from __future__ import annotations

import ast
import builtins
import csv
import io
import json
import os
import re
from pathlib import Path

import pytest
from conftest import (ENDPOINTS, FINGERPRINT, LATER, PLIST_SECRET, RICH_CFB_DOC, RICH_NFL_DOC, SECRET_KEY, Clock,
                      FakeRunner, Running, make_home, make_root, make_store)

from vfdash import api, readers, words
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


def test_a_link_to_an_env_file_is_never_opened(root, home, monkeypatch):
    """A data file that is a link to a .env file is not opened: the screen says so and shows the rest."""
    runs = root / "nfl-weather" / "data" / "forward" / "runs.csv"
    ledger = root / "cfb-weather" / "data" / "forward" / "ledger.csv"
    runs.unlink()
    ledger.unlink()
    os.symlink(root / "nfl-weather" / ".env", runs)
    os.symlink(root / "cfb-weather" / ".env", ledger)
    opened = []
    real_open, real_os_open = builtins.open, os.open

    def spy_open(file, *a, **k):
        if isinstance(file, (str, os.PathLike)):
            opened.append(os.path.realpath(file))
        return real_open(file, *a, **k)

    def spy_os_open(path, *a, **k):
        opened.append(os.path.realpath(path))
        return real_os_open(path, *a, **k)
    monkeypatch.setattr(builtins, "open", spy_open)
    monkeypatch.setattr(io, "open", spy_open)
    monkeypatch.setattr(os, "open", spy_os_open)
    store = make_store(root, home)
    s = api.summary(store)
    b = api.board(store)
    assert not [p for p in opened if is_env(p)], opened
    assert s["health"] == "warn"
    assert ("The NFL run record (nfl-weather/data/forward/runs.csv) is a link to a file the dashboard never opens, "
            "so it is not read.") in s["problems"]
    assert ("The college football ledger (cfb-weather/data/forward/ledger.csv) is a link to a file the dashboard "
            "never opens, so it is not read.") in b["notes"]
    assert b["runs"]["nfl"]["games"] == 5                             # the rest is shown
    for r in (readers.read_text(runs, "x"), readers.read_json(runs, "x")):
        assert r.data is None and "never opens" in r.note
    assert SECRET_KEY not in json.dumps([s, b])


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


# ---------------------------------------------------------------- the scrub, against the jobs' own

REPO = Path(__file__).resolve().parents[2]
RUNLOGS = [REPO / "nfl-weather" / "nflweather" / "runlog.py", REPO / "cfb-weather" / "cfbweather" / "runlog.py"]


def jobs_patterns(path: Path) -> dict:
    """_VALUE, SECRET and BEARER as the jobs' runlog.py builds them (their assignments only; runlog.py itself
    needs pandas, which the dashboard doesn't have)."""
    tree = ast.parse(path.read_text())
    ns = {"re": re}
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id in ("_VALUE", "SECRET", "BEARER")
                                                for t in node.targets):
            exec(compile(ast.Module([node], []), str(path), "exec"), ns)
    return ns


@pytest.mark.parametrize("path", RUNLOGS, ids=["nfl", "cfb"])
def test_the_scrub_is_the_jobs_scrub(path):
    if not path.exists():
        pytest.skip(f"{path} is not in this checkout")
    ns = jobs_patterns(path)
    assert ns["_VALUE"] == words._VALUE
    for name in ("SECRET", "BEARER"):
        assert (ns[name].pattern, ns[name].flags) == (getattr(words, name).pattern, getattr(words, name).flags), name

    def jobs_scrub(text):                                             # runlog.scrub, without pandas
        text = " ".join(str(text).split())
        text = ns["SECRET"].sub(lambda m: f"{m['name']}{m['mid']}***", text)
        return ns["BEARER"].sub(lambda m: f"{m['name']}***", text)
    for s in SHAPES + HARMLESS:
        assert words.scrub(s) == jobs_scrub(s), s


SHAPES = ["ODDS_API_KEY=abc123secret", '{"key": "abc123secret"}', "oddsApiKey=abc123secret",
          "Authorization: Bearer abc123secret", "GET /v4/sports?apiKey=abc123secret&regions=us",
          "x-api-key: abc123secret", "'token': 'abc123secret'", "?apiKey%3Dabc123secret", "bearer abc123secret",
          "password=abc123secret; next", "CFBD_API_KEY = abc123secret"]
HARMLESS = ["monkey business", "KeyError: 'total'", "keyword arguments", "a turkey sandwich", "tokenizer ready"]


@pytest.mark.parametrize("text", SHAPES + ["NTFY_TOPIC=abc123secret", '"NTFY_TOPIC": "abc123secret"',
                                           "ntfy_topic => abc123secret"])
def test_every_shape_of_key_is_blanked(text):
    out = words.scrub(text)
    assert "abc123secret" not in out and "***" in out, out


@pytest.mark.parametrize("text", HARMLESS + ["ledger rows: 8; in the test: 0",
                                             "RULE_B (wind under): 3 signals, 1 settled, 2 pending, 0 void"])
def test_ordinary_words_are_left_alone(text):
    assert words.scrub(text) == text


def test_line_breaks_are_kept():
    assert words.scrub("first line\napiKey=abc123secret\nthird line") == "first line\napiKey=***\nthird line"


def test_a_value_already_blanked_is_left_as_written():
    """ops/RUN_RECORDS.md says keys are blanked (`apiKey=***`); the closing mark stays."""
    text = "Keys are blanked (`apiKey=***`) before anything is printed."
    assert words.scrub(text) == text


PLANTED = ('error apiKey=PLANTED0 and {"key": "PLANTED1"} ODDS_API_KEY=PLANTED2 oddsApiKey=PLANTED3 '
           "Authorization: Bearer PLANTED4 NTFY_TOPIC=PLANTED5")


def test_planted_keys_are_never_served(tmp_path):
    """Every shape at once, in each place the page shows text the jobs wrote: a job's log, a run's error, the
    alert log, and a scorer's output and error output."""
    root, home = make_root(tmp_path), make_home(tmp_path)
    for log in ("valuefinder-closecapture.log", "valuefinder-ledgersync.log"):
        (home / "Library" / "Logs" / log).write_text(f"2026-10-02 00:02Z close capture: {PLANTED}\n")
    runs = root / "cfb-weather" / "data" / "forward" / "runs.csv"
    with runs.open("a", newline="") as f:
        csv.writer(f, lineterminator="\r\n").writerow(
            ["2026-10-02T15:10:00Z", "cfb-alerts", "cfb-v3", "failed", 0, 0, 0, "", f"while pricing: {PLANTED}", 0])
    alerts = root / "nfl-weather" / "data" / "forward" / "alerts.log"
    alerts.write_text(alerts.read_text().replace("apiKey=abcdef0123", PLANTED))
    runner = FakeRunner(scorer="failed_after_printing", nfl_text=f"ledger rows: 8\n{PLANTED}\n",
                        stderr=f"Traceback ...\nValueError: {PLANTED}")
    store = make_store(root, home, runner=runner)
    s = Running(store)
    try:
        for path in ENDPOINTS:
            status, body, _ = s.get(path)
            text = body.decode("utf-8")
            assert "PLANTED" not in text, (path, [t for t in re.findall(r"\S*PLANTED\S*", text)])
        _, body, _ = s.get("/api/jobs")
        assert "***" in body.decode("utf-8")                             # the lines are shown, blanked
    finally:
        s.close()


@pytest.mark.parametrize("mode", ["document", "not_document"])
def test_planted_keys_in_a_scorer_document_are_never_served(tmp_path, mode):
    """A key in any string of a scorer's --json document (its report, a bet's source, teams, void reason, a decision's
    text), or in what it printed when that is not the document, is blanked everywhere the dashboard shows it."""
    root, home = make_root(tmp_path), make_home(tmp_path)
    nfl, cfb = json.loads(json.dumps(RICH_NFL_DOC)), json.loads(json.dumps(RICH_CFB_DOC))
    rb = nfl["tests"][0]
    rb["bets"][0]["price_source"] = PLANTED
    rb["bets"][1]["away_team"] = PLANTED
    rb["bets"][4]["void_reason"] = PLANTED
    rb["decisions"][0]["text"] += PLANTED
    cfb["tests"][0]["bets"][1]["close_source"] = PLANTED
    runner = (FakeRunner(nfl_doc=nfl, cfb_doc=cfb, nfl_text=f"ledger rows: 8\n{PLANTED}\n") if mode == "document" else
              FakeRunner(raw=f"ledger rows: 8\n{PLANTED}\n", cfb_doc=cfb))
    store = make_store(root, home, runner=runner, clock=Clock(LATER))
    s = Running(store)
    try:
        for path in ENDPOINTS:
            status, body, _ = s.get(path)
            text = body.decode("utf-8")
            assert "PLANTED" not in text, (path, [t for t in re.findall(r"\S*PLANTED\S*", text)])
        _, body, _ = s.get("/api/signals" if mode == "document" else "/api/tests")
        assert "***" in body.decode("utf-8")                               # shown, blanked
    finally:
        s.close()
