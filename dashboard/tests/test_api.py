"""Every API endpoint on synthetic fixtures, including missing, empty, half-written and widened files. None of
them may produce an error page: each says what it couldn't read and shows the rest."""
from __future__ import annotations

import json
import os
import shutil

import pytest
from conftest import (CONTENT, ENDPOINTS, Clock, FakeRunner, copy_content,
                      make_store, write)

from vfdash import api


def all_payloads(store):
    out = {"summary": api.summary(store), "home": api.home(store), "board": api.board(store),
           "tests": api.tests_screen(store), "jobs": api.jobs_screen(store), "records": api.run_records(store),
           "pull": api.pull(store), "research": api.research(store)}
    out["game"] = api.game(store, "2026_05_BUF_NE")
    return out


def test_every_endpoint_over_http(served):
    for path in ENDPOINTS:
        status, body, headers = served.get(path)
        assert status == 200, path
        assert headers["Content-Type"].startswith("application/json")
        assert headers["Cache-Control"] == "no-store"
        payload = json.loads(body)
        assert "error" not in payload, (path, payload.get("error"))
    status, body, headers = served.get("/")
    assert status == 200 and headers["Content-Type"].startswith("text/html")
    assert b"Paper only" in body


def test_home(store):
    d = api.home(store)
    assert d["header"]["last_written"] == "Last run 7:30 AM"
    assert d["header"]["read_at"] == "Read at 10:00 AM"
    assert d["numbers"] == {"signals_live": 3, "games_on_board": 8, "next_run": "11:30 AM", "next_run_day": "today",
                            "credits": 491, "credits_read": "7:30 AM"}
    names = [t["name"] for t in d["tests"]]
    assert names == ["NFL wind under (Rule B)", "NFL model lean", "College football wind under (Rule B)",
                     "College football high-total under (Rule HT)"]
    cfb_b = d["tests"][2]
    assert cfb_b["progress"].startswith("0 of 40 settled") or "signals logged" in cfb_b["progress"]
    assert d["tests"][0]["progress"] == "Starts Week 5, Thu Oct 8, 2026"
    assert all(t["money_gate"] == "Money gate: not chosen" for t in d["tests"])
    assert [j["name"] for j in d["jobs"]] == ["NFL alerts", "College football alerts", "Close capture",
                                               "Nightly ledger copy"]
    assert all(j["level"] == "ok" for j in d["jobs"])
    w = d["waiting"]
    assert [x["title"] for x in w] == ["Odds API plan", "The Oct 20 gate decisions", "Something overdue (#9)",
                                       "Scorer readings: amendment 6"]
    assert w[0]["first_sentence"] == "A free key is set in all three .env files (Sep 28)."
    assert w[0]["due"] is None
    assert w[1]["due"] == "Due Tue Oct 20" and w[1]["due_level"] == "ok"
    assert w[2]["due"] == "Due Wed Sep 30" and w[2]["due_level"] == "fail"
    assert w[3]["first_sentence"] == "The hub registered both."
    assert d["variants"] == 271 and d["bar"] == "0.000185"
    assert d["evidence"] and all(e["n_words"] for e in d["evidence"])


def test_board(store):
    d = api.board(store)
    games = d["games"]
    assert len(games) == 8
    assert [g["signal"] for g in games[:3]] == [True, True, True] and not any(g["signal"] for g in games[3:])
    by_id = {g["game_id"]: g for g in games}
    buf = by_id["2026_05_BUF_NE"]
    assert buf["kickoff"] == "Sun Oct 4, 1:00 PM ET"
    assert buf["matchup"] == "BUF at NE"
    assert buf["forecast"] == "17 mph, 61°F"
    assert (buf["total"], buf["under"], buf["source"]) == ("44.5", "−108", "Pinnacle")
    assert buf["model_chance"] == "52%" and buf["ev"] == "+10.4%"
    assert buf["rules"][0] == {"rule": "Rule B", "value": "SIGNAL", "words": "Signal", "signal": True, "lean": False}
    assert buf["best"] == "45.0 at −110 (FanDuel)"
    assert buf["days"] == 2
    assert by_id["2026_05_TEN_BAL"]["rules"][0]["words"] == "Signal at the backup price"
    assert by_id["2026_05_ARI_NYG"]["rules"][1]["words"] == "Leans under"
    assert by_id["2026_05_ARI_NYG"]["signal"] is False
    assert by_id["2026_05_ATL_NO"]["forecast"] == "Indoors"
    assert by_id["2026_05_ATL_NO"]["rules"][0]["words"] == "Indoors"
    assert by_id["401000002"]["rules"][1]["words"] == "Signal"
    assert by_id["401000003"]["rules"][1]["words"] == "Before the test starts (Week 6)"
    assert by_id["401000004"]["kickoff"] == "Sat Oct 3, 7:00 PM ET"     # older row: kick_et only
    assert "401000001" not in by_id and "2026_04_PIT_CLE" not in by_id   # kicked off


def test_game(store):
    status, d = api.game(store, "2026_05_KC_DEN")
    assert status == 200
    assert [r["rules"][0]["words"] for r in d["rows"]] == ["Signal", "No wind trigger"]
    assert [p[1] for p in d["charts"]["wind"]] == [15.8, 12.0]
    status, d = api.game(store, "2026_05_BUF_NE")
    assert [s["words"] for s in d["alerts"]["sent"]] == ["Rule B signal", "Model lean watch: under"]
    assert d["alerts"]["sent"][0]["first_seen"] == "First logged on the run of Fri Oct 2, 7:30 AM"
    assert d["alerts"]["log_lines"][0].startswith("ALERT  RULE B WIND UNDER 44.5")
    assert "abcdef0123" not in json.dumps(d)                          # a key in the log is blanked
    assert d["fills"] == [{"when": "8:05 AM", "rule": "Rule B", "line": "44.5", "price": "−108",
                           "book": "FanDuel"}]
    status, d = api.game(store, "2026_04_PIT_CLE")
    assert [(c["book"], c["total"], c["under"]) for c in d["closes"]] == [("Pinnacle", "38.0", "−106"),
                                                                        ("DraftKings", "38.5", "−112")]
    assert d["rows"][0]["rules"][0]["words"] == "Not logged on this row"     # a row from before the widening
    status, d = api.game(store, "401000001")
    assert d["closes"][0]["book"] == "Pinnacle"
    status, d = api.game(store, "999")
    assert status == 404 and "No game" in d["error"]


def test_tests_screen(store, runner):
    d = api.tests_screen(store)
    nfl, cfb = d["groups"]
    assert nfl["scorer"]["status"] == "ok"
    assert nfl["scorer"]["text"].startswith("ledger rows: 8")            # exactly as printed
    assert cfb["tests"][0]["decisions"][0]["text"].startswith("Decision recorded: KEEP")
    assert cfb["tests"][0]["progress"] == "0 of 40 settled, 1 waiting for a result"
    assert cfb["tests"][1]["progress"].startswith("Starts Week 6")
    assert nfl["tests"][0]["counts"]["games_logged"] == 0                # nothing from Week 5 yet
    counts = cfb["tests"][0]["counts"]
    assert counts["games_logged"] == 4 and counts["signals"] == 1
    scorer_calls = [c for c, cwd, t in runner.calls if "--now" in c]
    assert len(scorer_calls) == 2


@pytest.mark.parametrize("mode, words", [("timeout", "took more than 60 seconds"), ("missing", "can't be run here"),
                                         ("failed", "stopped with an error")])
def test_scorer_trouble_is_said_in_plain_words(root, home, mode, words):
    store = make_store(root, home, runner=FakeRunner(scorer=mode))
    d = api.tests_screen(store)
    for g in d["groups"]:
        assert words in g["scorer"]["words"]
        assert g["tests"][0]["counts"] is not None                      # the rest is still shown


def test_scorer_preview_is_cached_for_ten_minutes(root, home):
    runner, clock = FakeRunner(), Clock()
    store = make_store(root, home, clock=clock, runner=runner)
    api.tests_screen(store)
    api.tests_screen(store)
    from datetime import timedelta
    clock.t = clock.t + timedelta(minutes=11)
    api.tests_screen(store)
    assert sum(1 for c, _, _ in runner.calls if "--now" in c) == 4


def test_snapshot_is_cached_for_thirty_seconds(root, home):
    from datetime import timedelta
    clock = Clock()
    store = make_store(root, home, clock=clock)
    first = store.snapshot()
    assert store.snapshot() is first
    clock.t += timedelta(seconds=29)
    assert store.snapshot() is first
    clock.t += timedelta(seconds=2)
    assert store.snapshot() is not first


def test_jobs(store):
    d = api.jobs_screen(store)
    assert d["runs"]["nfl-weather"]["rows"][0]["when"] == "Fri Oct 2, 7:30 AM"   # newest first
    assert d["runs"]["cfb-weather"]["rows"][0]["unmapped"] == "Some Team"
    jobs = {j["label"]: j for j in d["jobs"]}
    assert jobs["com.nflweather.alerts"]["schedule"] == "Four times a day: 7:30 AM, 11:30 AM, 3:30 PM and 7:30 PM"
    assert jobs["com.valuefinder.closecapture"]["schedule"] == "Every 15 minutes"
    assert jobs["com.valuefinder.ledgersync"]["schedule"] == "Every day at 11:45 PM"
    assert jobs["com.valuefinder.ledgersync"]["result"] == "Copied the records to the ledgers branch"
    assert d["credits"]["remaining"] == 491 and d["credits"]["plan"] == 500
    assert d["credits"]["read"] == "Fri Oct 2, 7:30 AM"
    assert [c["matchup"] for c in d["closes"]] == ["Army at Navy", "PIT at CLE"]
    assert d["closes"][1]["line"] == "38.0, under −106 (Pinnacle)" and d["closes"][1]["books"] == 2
    text = json.dumps(d)
    assert "plist-SECRET" not in text and "fp0SECRET" not in text


def test_run_records(store):
    d = api.run_records(store)
    assert d["text"].startswith("# Run records")


def test_pull_not_started(store):
    d = api.pull(store)
    assert d["started"] is False
    assert d["text"] == "The pull has not started. It is planned for Thursday, October 1."


def test_pull_from_manifest(root, home):
    fields = ("logged_at,pull,sport,source,path,event_id,requested_ts,returned_ts,previous_ts,next_ts,markets,books,"
              "n_events,expected_credits,credits_last,remaining,http_status,sha256,cache_key,sealed")
    rows = ["2026-10-01T15:00:00Z,account,,,/sports,,,,,,,,,,,20000000,200,x,,",
            "2026-10-01T15:00:01Z,F1,americanfootball_nfl,a,/x,,,,,,totals,,5,10,10,19999990,200,x,k,False",
            "2026-10-01T15:00:02Z,F1,americanfootball_nfl,a,/x,,,,,,totals,,5,10,,19999980,200,x,k,False",
            "2026-10-01T15:00:03Z,F2,americanfootball_nfl,a,/x,,,,,,alt,,5,30,20,19999960,200,x,k,False"]
    write(root / "sharp-markets" / "data" / "raw" / "_manifest" / "oddsapi_manifest.csv",
          fields + "\n" + "\n".join(rows) + "\n")
    d = api.pull(make_store(root, home))
    assert d["started"] is True
    pulls = {p["pull"]: p for p in d["pulls"]}
    assert pulls["F1"] == {"pull": "F1", "requests": 2, "billed": 20, "upper": 20, "lowest": 19999980,
                           "unreadable": 1, "name": "F1"}
    assert pulls["F2"]["billed"] == 20 and pulls["F2"]["upper"] == 30
    assert d["total"] == {"requests": 4, "billed": 40, "upper": 50, "unreadable": 1, "lowest": 19999960}
    assert d["header"]["last_written"] == "Last request Thu Oct 1, 8:00 AM"


def test_research(store):
    d = api.research(store)
    assert d["variants"] == 271 and d["bar"] == "0.000185"
    assert len(d["entries"]) >= 10
    for e in d["entries"]:
        assert e["n_words"] and e["bar_words"] and e["source"]
        assert e["clears_bar"] is False                                 # nothing on main clears its bar
        assert e["bar_words"] == "Does not clear the multiple-testing bar"


def test_evidence_sources_exist_in_the_repo():
    repo = CONTENT.parents[1]
    for e in json.loads((CONTENT / "evidence.json").read_text()):
        assert (repo / e["source"]).is_file(), e["source"]
        assert isinstance(e["clears_bar"], bool)
        for k in ("id", "title", "sport", "result", "record", "win_rate", "n", "p_value", "clears_bar", "bar",
                  "source", "date"):
            assert k in e, (e["id"], k)


# ---------------------------------------------------------------- damaged files

def test_everything_missing(tmp_path):
    empty, home = tmp_path / "empty", tmp_path / "nohome"
    empty.mkdir()
    home.mkdir()
    store = make_store(empty, home, runner=FakeRunner(listing=None, scorer="missing"))
    p = all_payloads(store)
    assert p["board"]["games"] == []
    assert any("NFL ledger" in n for n in p["board"]["notes"])
    assert p["home"]["numbers"]["credits"] is None
    assert p["game"][0] == 404
    assert p["pull"]["started"] is False
    assert p["research"]["variants"] is None
    assert any("could not be read" in n or "missing" in n for n in p["home"]["notes"] + p["home"]["header"]["problems"])


def test_empty_files(root, home):
    for path in list(root.rglob("*")) + list(home.rglob("*")):
        if path.is_file() and path.suffix in (".csv", ".json", ".md", ".log", ".plist"):
            path.write_bytes(b"")
    p = all_payloads(make_store(root, home))
    assert p["summary"]["health"] == "warn"
    assert any("is empty" in x for x in p["summary"]["problems"])
    assert p["board"]["games"] == []


def test_half_written_files(root, home, tmp_path):
    content = copy_content(tmp_path / "content")
    (content / "evidence.json").write_text((CONTENT / "evidence.json").read_text()[:500])
    nfl = root / "nfl-weather" / "data" / "forward"
    text = (nfl / "ledger.csv").read_text()
    (nfl / "ledger.csv").write_text(text + "2026-10-02T15:00:00Z,v3,2026_05_NYJ_MIA,2026-10-0")   # cut mid-line
    (nfl / "runs.csv").write_text((nfl / "runs.csv").read_text() + "2026-10-02T15:10:00Z,nfl-al")
    (nfl / "alert_state.json").write_text('{"2026_05_BUF_NE": {"sent": ["ru')
    (root / "cfb-weather" / "data" / "forward" / "closes.csv").write_text("capture_utc,game_id,start")
    store = make_store(root, home, content=content)
    p = all_payloads(store)
    assert "2026_05_NYJ_MIA" not in {g["game_id"] for g in p["board"]["games"]}
    assert len(p["board"]["games"]) == 8
    notes = " ".join(p["board"]["notes"] + p["home"]["notes"] + p["summary"]["problems"])
    assert "incomplete" in notes
    assert any("evidence list" in x for x in p["summary"]["problems"])
    assert any("alert record" in x for x in p["summary"]["problems"])
    assert p["game"][1]["alerts"]["note"]                                     # says the record couldn't be read
    assert p["research"]["entries"] == []


def test_widened_and_unknown_columns(root, home):
    """Extra columns the dashboard has never seen are ignored; columns it expects but that are missing are blank."""
    nfl = root / "nfl-weather" / "data" / "forward" / "ledger.csv"
    lines = nfl.read_text().splitlines()
    lines[0] += ",brand_new_column,another"
    lines[1:] = [ln + ",x,y" for ln in lines[1:]]
    nfl.write_text("\n".join(lines) + "\n")
    cfb = root / "cfb-weather" / "data" / "forward" / "ledger.csv"
    narrow = "snapshot_utc,game_id,kick_et,away_team,home_team,rule_b\n" \
             "2026-10-02T14:30:14Z,401000009,Sat 10-03 12:00,Iowa,Minnesota,no_trigger\n"
    cfb.write_text(narrow)
    runs = root / "nfl-weather" / "data" / "forward" / "runs.csv"
    runs.write_text("run_utc,job,status,games,a_new_one\r\n2026-10-02T14:30:07Z,nfl-alerts,ok,5,z\r\n")
    store = make_store(root, home)
    p = all_payloads(store)
    ids = {g["game_id"] for g in p["board"]["games"]}
    assert "2026_05_BUF_NE" in ids and "401000009" in ids
    g = next(g for g in p["board"]["games"] if g["game_id"] == "401000009")
    assert g["total"] == "" and g["rules"][1]["words"] == "Not logged on this row"
    assert p["jobs"]["runs"]["nfl-weather"]["rows"][0]["rule_priced"] == ""


def test_rows_with_the_wrong_number_of_fields_are_left_out(root, home):
    nfl = root / "nfl-weather" / "data" / "forward" / "ledger.csv"
    with nfl.open("a") as f:
        f.write("2026-10-02T14:30:07Z,only,four,fields\n")
    p = all_payloads(make_store(root, home))
    assert len(p["board"]["games"]) == 8
    assert any("could not be read and is left out" in n for n in p["board"]["notes"] + p["home"]["notes"])


def test_garbage_bytes(root, home):
    (root / "nfl-weather" / "data" / "forward" / "ledger.csv").write_bytes(os.urandom(4096))
    (root / "STATUS.md").write_bytes(b"\xff\xfe\x00garbage")
    (home / "Library" / "LaunchAgents" / "com.nflweather.alerts.plist").write_bytes(b"not a plist")
    p = all_payloads(make_store(root, home))
    assert p["summary"]["health"] in ("warn", "fail")
    assert any("launchd file" in x for x in p["summary"]["problems"])


def test_ledger_grows_between_reads(root, home):
    from datetime import timedelta
    clock = Clock()
    store = make_store(root, home, clock=clock)
    assert api.summary(store)["games_on_board"] == 8
    nfl = root / "nfl-weather" / "data" / "forward" / "ledger.csv"
    from conftest import nfl_row
    with nfl.open("a") as f:
        f.write(nfl_row("2026-10-02T18:30:07Z", "2026_05_NYJ_MIA", "2026-10-04", "13:00", "NYJ", "MIA", "SIGNAL") + "\n")
    clock.t += timedelta(seconds=31)
    s = api.summary(store)
    assert s["games_on_board"] == 3 + 1            # the NFL latest run now has one game
    assert s["signals_live"] == 3 + 1 - 0
    # a rewrite (new file, same name) is read from the top
    shutil.copy(nfl, nfl.with_suffix(".tmp"))
    os.replace(nfl.with_suffix(".tmp"), nfl)
    clock.t += timedelta(seconds=31)
    assert api.summary(store)["games_on_board"] == 4
