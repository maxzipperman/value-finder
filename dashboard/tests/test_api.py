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
    # the model lean on ARI_NYG is a watch: counted apart from the signals (PIT_CLE's lean has kicked off)
    assert d["numbers"] == {"signals_live": 3, "games_on_board": 8, "leans_live": 1, "next_run": "11:30 AM",
                            "next_run_day": "today", "credits": 491, "credits_read": "7:30 AM"}
    names = [t["name"] for t in d["tests"]]
    assert names == ["NFL wind under (Rule B)", "NFL model lean", "College football wind under (Rule B)",
                     "College football high-total under (Rule HT)"]
    cfb_b = d["tests"][2]
    # Home doesn't wait for the scorer: until its read is in, the count is the ledger's
    assert cfb_b["progress"] == "1 signal logged; the settled count comes from the scorer"
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
    assert buf["lean_chance"] == "52%" and buf["wind_value"] == "+10.4%"
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


def test_board_is_worked_out_once_a_minute(root, home):
    from datetime import datetime, timedelta, timezone
    clock = Clock(datetime(2026, 10, 4, 16, 59, 5, tzinfo=timezone.utc))      # BUF at NE kicks off at 17:00 UTC
    store = make_store(root, home, clock=clock)
    first = api.board(store)
    assert "2026_05_BUF_NE" in {g["game_id"] for g in first["games"]}
    clock.t += timedelta(seconds=20)                                           # the same minute and snapshot
    assert api.board(store)["games"] is first["games"]
    clock.t += timedelta(seconds=40)                                           # 17:00:05: it has kicked off
    assert "2026_05_BUF_NE" not in {g["game_id"] for g in api.board(store)["games"]}


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


def paren_depth(s: str) -> int:
    depth = top = 0
    for ch in s:
        depth += (ch == "(") - (ch == ")")
        top = max(top, depth)
    return top


def test_each_results_bar_is_one_plain_sentence(store):
    ev = {e["id"]: e for e in api.research(store)["entries"]}
    assert ev["nfl-rule-b-replay-mos"]["bar_sentence"] == (
        "Does not clear the multiple-testing bar in force when it was measured: p < 0.000183 (273 variants).")
    assert ev["cfb-rule-b-replay-openmeteo-2024-25"]["bar_sentence"] == (
        "Does not clear the multiple-testing bar in force when it was measured: 0.05 split over 135 variants (this "
        "replay made the count 135).")
    assert ev["cfb-rule-b-observed-2006-25"]["bar_sentence"] == (
        "No multiple-testing bar was stated in the source, so it is not counted as clearing one.")
    assert ev["money-gate-today"]["bar_sentence"] == "Not a betting test: it adds no variants."
    for e in ev.values():
        s = e["bar_sentence"]
        assert s[:1].isupper() and s.endswith(".") and paren_depth(s) <= 1, s
    for e in api.home(store)["evidence"]:
        assert e["bar_sentence"] == ev[e["id"]]["bar_sentence"]
    js = (CONTENT.parent / "vfdash" / "static" / "app.js").read_text()
    row = js.split("function evidenceRow(", 1)[1].split("\n  }\n", 1)[0]
    assert "e.bar_sentence" in row and "in force when measured (" not in row


def test_bars_as_the_hub_may_write_them(root, home, tmp_path):
    content = copy_content(tmp_path / "content")
    base = {"title": "T", "result": "R.", "record": None, "win_rate": None, "n": 10, "p_value": None,
            "source": "STATUS.md", "date": "2026-09-01"}
    entries = [dict(base, id="a", clears_bar=False, bar=None), dict(base, id="b", clears_bar=False, bar=""),
               dict(base, id="c", clears_bar=False, bar="not stated"),
               dict(base, id="d", clears_bar=True, bar="p < 0.0001 (500 variants)", p_value=0.00001)]
    (content / "evidence.json").write_text(json.dumps(entries))
    ev = {e["id"]: e for e in api.research(make_store(root, home, content=content))["entries"]}
    none = "No multiple-testing bar was stated in the source, so it is not counted as clearing one."
    assert [ev[k]["bar_sentence"] for k in "abc"] == [none] * 3
    assert ev["d"]["bar_sentence"] == ("Clears the multiple-testing bar in force when it was measured: p < 0.0001 "
                                       "(500 variants).")


def test_the_research_stamp_is_the_newest_entrys_date(root, home, tmp_path):
    """Not the evidence file's modification time, which is only when git last wrote it."""
    content = copy_content(tmp_path / "content")
    newest = max(e["date"] for e in json.loads((CONTENT / "evidence.json").read_text()))
    from datetime import date
    d = date.fromisoformat(newest)
    os.utime(content / "evidence.json", (0, 0))                        # Jan 1, 1970
    h = api.research(make_store(root, home, content=content))["header"]
    assert h["last_written"] == f"Newest entry dated {d:%a} {d:%b} {d.day}, {d.year}"
    (content / "evidence.json").write_text(json.dumps([{"id": "x", "title": "T", "result": "R.", "date": "soon"}]))
    h = api.research(make_store(root, home, content=content))["header"]
    assert h["last_written"] == "No entry in the evidence list is dated"


def test_evidence_sources_exist_in_the_repo():
    repo = CONTENT.parents[1]
    for e in json.loads((CONTENT / "evidence.json").read_text()):
        assert (repo / e["source"]).is_file(), e["source"]
        assert isinstance(e["clears_bar"], bool)
        for k in ("id", "title", "sport", "result", "record", "win_rate", "n", "p_value", "clears_bar", "bar",
                  "source", "date"):
            assert k in e, (e["id"], k)


def test_evidence_numbers_are_quoted_from_their_source():
    """Each entry's record, win rate and sample size are written in the file it names, as written there."""
    import re
    repo = CONTENT.parents[1]
    for e in json.loads((CONTENT / "evidence.json").read_text()):
        text = (repo / e["source"]).read_text()
        if e["record"] and "-" in e["record"]:
            assert e["record"].replace("-", "–") in text, (e["id"], e["record"])
        if isinstance(e["win_rate"], (int, float)) and f"{e['win_rate']:.1f}%" not in text:
            w, l_ = map(int, (e["record"] or "x-x").split("-")[:2])           # else it is the record's own rate
            assert abs(100 * w / (w + l_) - e["win_rate"]) < 0.05, (e["id"], e["win_rate"])
        if isinstance(e["n"], int) and not re.search(rf"(?<![\d,.])({e['n']:,}|{e['n']})(?![\d,])", text):
            parts = [int(x) for x in (e["record"] or "").split("-") if x.isdigit()]   # else the record's own count
            assert parts and e["n"] in (sum(parts), sum(parts[:2])), (e["id"], e["n"])
        for quote in re.findall(r"“([^”]+)”", e["result"]):
            assert quote in text, (e["id"], quote)


def test_sentences_about_files_read_well(root, home):
    """A sentence that starts with a path keeps it as written, and plural names don't take "is"."""
    for path in list(root.rglob("*")) + list(home.rglob("*")):
        if path.is_file() and path.suffix in (".csv", ".json", ".log", ".plist"):
            path.write_bytes(b"")
    (root / "ops" / "RUN_RECORDS.md").unlink()
    store = make_store(root, home)
    text = json.dumps([api.summary(store), api.home(store), api.jobs_screen(store), api.run_records(store)],
                      ensure_ascii=False)
    assert "Ops/" not in text
    assert "The guide to the run records (ops/RUN_RECORDS.md) is missing." in text
    assert "The NFL closing-line record (nfl-weather/data/forward/closes.csv) is empty." in text
    assert ("The launchd file for the NFL alerts job (~/Library/LaunchAgents/com.nflweather.alerts.plist) could "
            "not be read as a launchd job file.") in text
    import re
    assert not re.search(r"(lines|fills|descriptions) \([^)]*\) is ", text)
    assert "nfl alerts" not in text                                  # the NFL keeps its capitals mid-sentence


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
    clock.t += timedelta(minutes=91)                  # 18:31 UTC: after that run was logged
    s = api.summary(store)
    assert s["games_on_board"] == 3 + 1            # the NFL latest run now has one game
    assert s["signals_live"] == 3 + 1 - 0
    # a rewrite (new file, same name) is read from the top
    shutil.copy(nfl, nfl.with_suffix(".tmp"))
    os.replace(nfl.with_suffix(".tmp"), nfl)
    clock.t += timedelta(seconds=31)
    assert api.summary(store)["games_on_board"] == 4


# ---------------------------------------------------------------- unexpected values in the jobs' own columns

def append(path, line):
    with path.open("a", newline="") as f:
        f.write(line)


def test_a_logging_time_that_cant_be_read_is_left_out(root, home):
    """The latest run is the latest time that can be read, never the largest text: one 'pending' row, or a
    time written without its leading zero, doesn't empty or replace the board."""
    from conftest import nfl_row
    ledger = root / "nfl-weather" / "data" / "forward" / "ledger.csv"
    last = ledger.read_text().splitlines()[-1]
    append(ledger, "pending," + last.split(",", 1)[1] + "\n")
    # 2:30 AM UTC written as "T2:30": larger than "T14:30" as text, earlier as a time
    append(ledger, nfl_row("2026-10-02T2:30:07Z", "2026_05_NYJ_MIA", "2026-10-04", "13:00", "NYJ", "MIA", "SIGNAL")
           + "\n")
    # the latest run's time in another format joins that run
    append(ledger, nfl_row("2026-10-02 14:30:07+00:00", "2026_05_LV_LAC", "2026-10-04", "16:05", "LV", "LAC",
                           "no_trigger") + "\n")
    store = make_store(root, home)
    s = api.summary(store)
    assert s["health"] == "ok", s["problems"]
    # LV_LAC joins the board; NYJ_MIA isn't in the latest run, but its latest row signals and it hasn't kicked off
    assert s["games_on_board"] == 8 + 1 and s["signals_live"] == 3 + 1
    b = api.board(store)
    assert b["runs"]["nfl"] == {"sport": "NFL", "latest_run": "7:30 AM", "games": 6}
    assert "2026_05_NYJ_MIA" not in {g["game_id"] for g in b["games"]}
    assert ("1 row of the NFL ledger (nfl-weather/data/forward/ledger.csv) has a logging time (snapshot_utc) that "
            "can't be read; it is left out.") in b["notes"]
    assert b["header"]["last_written"] == "Last run 7:30 AM"


def test_a_ledger_with_no_readable_logging_time_is_unreadable(root, home):
    ledger = root / "nfl-weather" / "data" / "forward" / "ledger.csv"
    lines = ledger.read_text().splitlines()
    ledger.write_text("\n".join([lines[0]] + ["pending," + ln.split(",", 1)[1] for ln in lines[1:]]) + "\n")
    s = api.summary(make_store(root, home))
    assert s["health"] == "warn"
    assert any("No row of the NFL ledger" in p and "snapshot_utc" in p for p in s["problems"])
    assert s["games_on_board"] == 3                                   # the college games are still shown


@pytest.mark.parametrize("project, old, new, words", [
    ("nfl-weather", "snapshot_utc,", "snapshot_time,", "is missing its snapshot_utc column"),
    ("nfl-weather", "game_id,gameday,gametime,", "gid,day,clock,", "is missing its game_id, gameday and gametime columns"),
    ("cfb-weather", "kick_et,", "kickoff_et,", None),                 # start_utc is still there: fine
])
def test_a_ledger_without_a_column_it_needs(root, home, project, old, new, words):
    ledger = root / project / "data" / "forward" / "ledger.csv"
    text = ledger.read_text()
    ledger.write_text(text.replace(old, new, 1))
    store = make_store(root, home)
    s = api.summary(store)
    b = api.board(store)
    if words is None:                                 # readable; only the row with no start_utc loses its kickoff
        assert s["health"] == "ok" and s["games_on_board"] == 7
        return
    assert s["health"] == "warn"
    assert any(words in p and "so it can't be read" in p for p in s["problems"]), s["problems"]
    assert any(words in n for n in b["notes"])
    assert b["runs"]["nfl"]["games"] == 0 and b["runs"]["cfb"]["games"] == 3


def test_a_college_ledger_with_neither_kickoff_column(root, home):
    ledger = root / "cfb-weather" / "data" / "forward" / "ledger.csv"
    ledger.write_text(ledger.read_text().replace("kick_et,", "k1,", 1).replace("start_utc,", "k2,", 1))
    s = api.summary(make_store(root, home))
    assert s["health"] == "warn"
    assert any("is missing its start_utc (or kick_et) column" in p for p in s["problems"])
    assert s["games_on_board"] == 5


@pytest.mark.parametrize("content, words", [
    (None, "NFL run record (nfl-weather/data/forward/runs.csv)"),                    # random bytes
    ("when,job,result\r\n2026-10-02T14:30:07Z,nfl-alerts,ok\r\n", "is missing its run_utc and status columns"),
    ("run_utc,job,state\r\n2026-10-02T14:30:07Z,nfl-alerts,ok\r\n", "is missing its status column"),
    ("run_utc,job,status\r\nsoon,nfl-alerts,ok\r\nlater,nfl-alerts,failed\r\n", "No row of the NFL run record"),
])
def test_a_run_record_that_cant_be_read_is_a_warning(root, home, content, words):
    import random
    runs = root / "nfl-weather" / "data" / "forward" / "runs.csv"
    if content is None:
        runs.write_bytes(random.Random(7).randbytes(4096))
    else:
        runs.write_text(content)
    s = api.summary(make_store(root, home))
    assert s["health"] == "warn", s["problems"]
    assert any(words in p for p in s["problems"]), s["problems"]


def test_one_run_time_that_cant_be_read_is_left_out(root, home):
    runs = root / "nfl-weather" / "data" / "forward" / "runs.csv"
    append(runs, "pending,nfl-alerts,v3-2026-09-28,failed,0,0,0,,boom,0\r\n")
    store = make_store(root, home)
    s = api.summary(store)
    assert s["health"] == "ok", s["problems"]                          # the unreadable row isn't the last run
    j = api.jobs_screen(store)
    assert "1 row of the NFL run record" in " ".join(j["notes"])
    assert len(j["runs"]["nfl-weather"]["rows"]) == 2


def test_a_failed_scorer_is_not_read_as_progress(root, home):
    """A scorer that stops with an error may still have printed its counts; they aren't shown as progress,
    on the Forward tests screen or on Home."""
    from datetime import datetime, timezone
    clock = Clock(datetime(2026, 10, 10, 17, 0, tzinfo=timezone.utc))          # both Rule B tests have started
    store = make_store(root, home, clock=clock, runner=FakeRunner(scorer="failed_after_printing"))
    tests = api.tests_screen(store)
    home_ = api.home(store)
    for listed in ([t for g in tests["groups"] for t in g["tests"]], home_["tests"]):
        by_id = {t["id"]: t for t in listed}
        for tid in ("nfl_rule_b", "cfb_rule_b"):
            assert by_id[tid]["progress"].startswith("The scorer stopped with an error; "), by_id[tid]["progress"]
            assert "settled" not in by_id[tid]["progress"] and by_id[tid]["scorer_counts"] is None
    assert tests["groups"][0]["scorer"]["text"].startswith("ledger rows: 8")        # what it printed is shown


def test_a_row_logged_later_than_now_is_not_the_latest_run(root, home):
    """One row stamped in the future (a clock set ahead) is left out until its time comes: it doesn't become the
    latest run or empty a sport's board. It is counted and named in the notes, and health turns to warn."""
    from datetime import datetime, timedelta, timezone
    ledger = root / "nfl-weather" / "data" / "forward" / "ledger.csv"
    last = ledger.read_text().splitlines()[-1]                        # ATL at NO, in the 7:30 AM run
    append(ledger, "2026-12-01T00:00:00Z," + last.split(",", 1)[1] + "\n")
    clock = Clock()
    store = make_store(root, home, clock=clock)
    b = api.board(store)
    assert b["runs"]["nfl"] == {"sport": "NFL", "latest_run": "7:30 AM", "games": 5}
    assert b["header"]["last_written"] == "Last run 7:30 AM"
    note = ("1 row of the NFL ledger (nfl-weather/data/forward/ledger.csv) is logged later than now: game "
            "2026_05_ATL_NO at Mon Nov 30, 4:00 PM. It is left out until then.")
    assert note in b["notes"]
    s = api.summary(store)
    assert s["games_on_board"] == 8 and s["signals_live"] == 3
    assert s["health"] == "warn"
    assert s["problems"] == ["The NFL ledger has 1 row logged later than now, which is left out; check the Mac's "
                             "clock."]
    status, g = api.game(store, "2026_05_ATL_NO")                     # the game's own rows leave it out too
    assert [r["logged"] for r in g["rows"]] == ["7:30 AM"]
    # once that time has come, the row is read like any other
    clock.t = datetime(2026, 12, 1, 0, 1, tzinfo=timezone.utc)        # Mon Nov 30, 4:01 PM Pacific
    b = api.board(store)
    assert b["runs"]["nfl"]["latest_run"] == "4:00 PM"
    assert not any("later than now" in n for n in b["notes"])
    clock.t += timedelta(seconds=31)
    assert "later than now" not in " ".join(api.summary(store)["problems"])


def test_several_rows_logged_later_than_now_are_counted(root, home):
    ledger = root / "cfb-weather" / "data" / "forward" / "ledger.csv"
    lines = ledger.read_text().splitlines()[1:]
    for i, ln in enumerate(lines):
        append(ledger, f"2027-01-0{i + 1}T12:00:00Z," + ln.split(",", 1)[1] + "\n")
    store = make_store(root, home)
    b = api.board(store)
    assert b["runs"]["cfb"]["games"] == 3
    note = next(n for n in b["notes"] if "later than now" in n)
    assert note.startswith("5 rows of the college football ledger (cfb-weather/data/forward/ledger.csv) are logged "
                           "later than now: game 401000001 at Fri Jan 1, 4:00 AM; game 401000002 at Sat Jan 2, 4:00 AM;")
    assert note.endswith("; and 2 more. They are left out until then.")
    assert ("The college football ledger has 5 rows logged later than now, which are left out; check the Mac's clock."
            in api.summary(store)["problems"])


def test_a_run_recorded_later_than_now_does_not_hide_a_stopped_job(root, home):
    """The same for runs.csv: a run stamped in the future is not taken as the last run, so a job that stopped
    still fails health."""
    from datetime import datetime, timezone
    runs = root / "nfl-weather" / "data" / "forward" / "runs.csv"
    append(runs, "2026-12-01T00:00:00Z,nfl-alerts,v3-2026-09-28,ok,5,2,5,,,4\r\n")
    store = make_store(root, home, clock=Clock(datetime(2026, 10, 3, 17, 0, tzinfo=timezone.utc)))   # a day on
    s = api.summary(store)
    assert s["health"] == "fail"
    assert any(p.startswith("The NFL alerts have not recorded a run since Fri Oct 2, 7:30 AM") for p in s["problems"])
    assert ("The NFL run record has 1 row logged later than now, which is left out; check the Mac's clock."
            in s["problems"])
    j = api.jobs_screen(store)
    assert ("1 row of the NFL run record (nfl-weather/data/forward/runs.csv) is logged later than now: Mon Nov 30, "
            "4:00 PM. It is left out until then.") in j["notes"]
    assert j["runs"]["nfl-weather"]["rows"][0]["when"] == "Fri Oct 2, 7:30 AM"


@pytest.mark.parametrize("how, words", [("remove", "is missing."), ("empty", "is empty."),
                                        ("cut", "has only a partly written first line.")])
def test_a_ledger_that_cant_be_read_is_named_in_a_full_sentence(root, home, how, words):
    ledger = root / "nfl-weather" / "data" / "forward" / "ledger.csv"
    if how == "remove":
        ledger.unlink()
    else:
        ledger.write_text("" if how == "empty" else "snapshot_utc,game")
    b = api.board(make_store(root, home))
    assert f"The NFL ledger (nfl-weather/data/forward/ledger.csv) {words}" in b["notes"]
    assert not any(n[:1].islower() for n in b["notes"])
