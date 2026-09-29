"""GET /api/summary follows the menu-bar light's contract exactly, for ok, warn and fail, with the clock patched."""
from __future__ import annotations

import json
from datetime import datetime, timezone

from conftest import (Clock, FakeRunner, make_home, make_root, make_store, nfl_row, NFL_HEADER,
                      write)

from vfdash import api

KEYS = {"generated_utc", "health", "signals_live", "games_on_board", "next_run_local", "credits_remaining", "problems"}
UTC = timezone.utc


def check_contract(s: dict):
    assert set(s) == KEYS
    assert isinstance(s["generated_utc"], str) and s["generated_utc"].endswith("Z")
    datetime.strptime(s["generated_utc"], "%Y-%m-%dT%H:%M:%SZ")
    assert s["health"] in ("ok", "warn", "fail")
    assert isinstance(s["signals_live"], int) and not isinstance(s["signals_live"], bool)
    assert isinstance(s["games_on_board"], int) and not isinstance(s["games_on_board"], bool)
    assert isinstance(s["next_run_local"], str) and len(s["next_run_local"]) == 5 and s["next_run_local"][2] == ":"
    assert s["credits_remaining"] is None or (isinstance(s["credits_remaining"], int)
                                              and not isinstance(s["credits_remaining"], bool))
    assert isinstance(s["problems"], list) and all(isinstance(p, str) and p for p in s["problems"])
    assert (s["health"] == "ok") == (s["problems"] == [])


def test_ok_over_http(served):
    status, s = served.json("/api/summary")
    assert status == 200
    check_contract(s)
    assert s == {"generated_utc": "2026-10-02T17:00:00Z", "health": "ok", "signals_live": 3, "games_on_board": 8,
                 "next_run_local": "11:30", "credits_remaining": 491, "problems": []}


def test_counts(store):
    s = api.summary(store)
    # NFL: BUF_NE (Rule B) and TEN_BAL (backup price) are live; KC_DEN's latest row no longer signals; PIT_CLE
    # has kicked off; the model lean on ARI_NYG is a watch, not a rule. CFB: Rule HT on 401000002 is live;
    # 401000001's Rule B signal kicked off an hour ago.
    assert s["signals_live"] == 3
    # 5 NFL games in the latest run, 3 CFB (one has kicked off; one is an older row with only kick_et)
    assert s["games_on_board"] == 8


def test_next_run_rolls_to_tomorrow(root, home):
    s = api.summary(make_store(root, home, clock=Clock(datetime(2026, 10, 3, 3, 0, tzinfo=UTC))))  # 8 PM Pacific
    assert s["next_run_local"] == "07:30"


def test_warn_low_credits(tmp_path):
    root, home = make_root(tmp_path), make_home(tmp_path, remaining=42)
    s = api.summary(make_store(root, home))
    check_contract(s)
    assert s["health"] == "warn" and s["credits_remaining"] == 42
    assert any("42 Odds API credits" in p for p in s["problems"])


def test_no_warn_for_last_months_balance(tmp_path):
    root, home = make_root(tmp_path), make_home(tmp_path, remaining=12, quota_utc="2026-09-29T14:30:14Z")
    s = api.summary(make_store(root, home))
    assert s["health"] == "ok", s["problems"]


def test_balance_of_a_paid_plan_is_not_low(tmp_path):
    root, home = make_root(tmp_path), make_home(tmp_path, remaining=1_500)
    assert api.summary(make_store(root, home))["health"] == "ok"


def test_warn_unreadable_file(tmp_path):
    root, home = make_root(tmp_path), make_home(tmp_path)
    (root / "STATUS.md").unlink()
    s = api.summary(make_store(root, home))
    check_contract(s)
    assert s["health"] == "warn"
    assert any("STATUS.md" in p for p in s["problems"])


def test_warn_stale_ledger_while_runs_are_recorded(tmp_path):
    root, home = make_root(tmp_path), make_home(tmp_path)
    ledger = root / "nfl-weather" / "data" / "forward" / "ledger.csv"
    write(ledger, NFL_HEADER + "\n" + nfl_row("2026-10-01T14:30:07Z", "2026_05_BUF_NE", "2026-10-04", "13:00", "BUF",
                                              "NE", "no_trigger") + "\n")
    s = api.summary(make_store(root, home))
    assert s["health"] == "warn"
    assert any("newest row in the NFL ledger" in p for p in s["problems"])


def test_fail_last_run_failed(tmp_path):
    root, home = make_root(tmp_path), make_home(tmp_path)
    runs = root / "cfb-weather" / "data" / "forward" / "runs.csv"
    with runs.open("a", newline="") as f:
        f.write("2026-10-02T15:10:00Z,cfb-alerts,cfb-v3-2026-09-28,failed,0,0,0,,"
                "\"while building the board: ConnectionError: apiKey=abc123 refused\",0\r\n")
    s = api.summary(make_store(root, home))
    check_contract(s)
    assert s["health"] == "fail"
    assert any("college football alerts run" in p and "while building the board" in p for p in s["problems"])
    assert not any("abc123" in p for p in s["problems"])


def test_fail_nonzero_exit(tmp_path):
    root, home = make_root(tmp_path), make_home(tmp_path)
    listing = ("PID\tStatus\tLabel\n-\t0\tcom.nflweather.alerts\n-\t0\tcom.cfbweather.alerts\n"
               "-\t1\tcom.valuefinder.closecapture\n-\t0\tcom.valuefinder.ledgersync\n")
    s = api.summary(make_store(root, home, runner=FakeRunner(listing=listing)))
    assert s["health"] == "fail"
    assert any("close capture job last ended with an error (exit status 1)" in p for p in s["problems"])


def test_fail_no_run_for_five_working_hours(root, home):
    # 1:05 PM Pacific: the 11:30 AM run never came; 5 h 35 min of the working day since 7:30 AM
    s = api.summary(make_store(root, home, clock=Clock(datetime(2026, 10, 2, 20, 5, tzinfo=UTC))))
    assert s["health"] == "fail"
    assert sum("have not recorded a run" in p for p in s["problems"]) == 2
    # the stale ledgers are not reported twice
    assert not any("newest row" in p for p in s["problems"])


def test_quiet_night_is_not_an_outage(root, home):
    # the last runs were 7:30 PM Pacific; at 5:00 AM only 4 working hours have passed
    for p, t in (("nfl-weather", "2026-10-03T02:30:07Z"), ("cfb-weather", "2026-10-03T02:30:14Z")):
        runs = root / p / "data" / "forward" / "runs.csv"
        with runs.open("a", newline="") as f:
            f.write(f"{t},x,v,ok,1,0,1,,,1\r\n")
    for p, t in (("nfl-weather", "2026-10-03T02:30:07Z"), ("cfb-weather", "2026-10-03T02:30:14Z")):
        ledger = root / p / "data" / "forward" / "ledger.csv"
        text = ledger.read_text().splitlines()
        last = text[-1].split(",", 1)[1]
        with ledger.open("a") as f:
            f.write(f"{t},{last}\n")
    s = api.summary(make_store(root, home, clock=Clock(datetime(2026, 10, 3, 12, 0, tzinfo=UTC))))
    assert s["health"] == "ok", s["problems"]


def test_missing_everything_is_warn_not_error(tmp_path):
    empty, home = tmp_path / "empty", tmp_path / "nohome"
    empty.mkdir()
    home.mkdir()
    s = api.summary(make_store(empty, home, runner=FakeRunner(listing=None)))
    check_contract(s)
    assert s["health"] == "warn"
    assert s["signals_live"] == 0 and s["games_on_board"] == 0 and s["credits_remaining"] is None
    assert s["next_run_local"] == "11:30"             # the jobs' fixed times when their files can't be read
    assert any("launchd" in p for p in s["problems"])


def test_summary_json_has_only_contract_fields(served):
    status, body, headers = served.get("/api/summary")
    assert headers["Content-Type"].startswith("application/json")
    check_contract(json.loads(body))
