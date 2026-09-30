"""Words on screen: plain sentences in sentence case, "college football" in a sentence (the short "CFB" only as a
tag beside a game), and a lean the model never ran said as such."""
from __future__ import annotations

import json
import re

import pytest
from conftest import CONTENT, make_store, nfl_row

from vfdash import api, words

LATE_NFL = "2026-10-02T14:30:07Z"


def append(path, line):
    with path.open("a", newline="") as f:
        f.write(line)


@pytest.mark.parametrize("how, words_", [
    ("remove", "The college football run record (cfb-weather/data/forward/runs.csv) is missing."),
    ("empty", "The college football run record (cfb-weather/data/forward/runs.csv) is empty."),
    ("link", "The college football run record (cfb-weather/data/forward/runs.csv) is a link to a file the dashboard "
             "never opens, so it is not read."),
])
def test_the_jobs_screens_notes_are_sentences(root, home, how, words_):
    runs = root / "cfb-weather" / "data" / "forward" / "runs.csv"
    runs.unlink()
    if how == "empty":
        runs.write_text("")
    elif how == "link":
        runs.symlink_to(root / "cfb-weather" / ".env")
    d = api.jobs_screen(make_store(root, home))
    assert d["runs"]["cfb-weather"]["note"] == words_
    for p in d["runs"].values():
        assert not p["note"] or p["note"][:1].isupper(), p["note"]


def strings(x, skip=("sport", "id", "sport_key", "game_id", "text", "error", "log_line", "log_lines", "value")):
    """Every string an answer carries to the page, except tags, ids and what is copied as the jobs printed it."""
    if isinstance(x, dict):
        for k, v in x.items():
            if k not in skip:
                yield from strings(v, skip)
    elif isinstance(x, list):
        for v in x:
            yield from strings(v, skip)
    elif isinstance(x, str):
        yield x


def test_college_football_is_written_out_in_every_sentence(root, home):
    fwd = root / "cfb-weather" / "data" / "forward"
    append(fwd / "runs.csv", "2026-12-01T00:00:00Z,cfb-alerts,cfb-v3-2026-09-28,ok,4,1,4,,,4\r\n")    # later than now
    last = (fwd / "ledger.csv").read_text().splitlines()[-1]
    append(fwd / "ledger.csv", "2026-12-01T00:00:00Z," + last.split(",", 1)[1] + "\n")
    (fwd / "alert_state.json").write_text("[]")                        # not in the form the jobs write
    (fwd / "decisions.csv").write_text("")                             # empty
    store = make_store(root, home)
    answers = [api.summary(store), api.home(store), api.board(store), api.jobs_screen(store), api.tests_screen(store),
               api.research(store), api.game(store, "401000002")[1], api.signals_screen(store)]
    said = list(strings(answers))
    assert "The college football run record has 1 row logged later than now, which is left out; check the Mac's " \
           "clock." in said
    assert any(s.startswith("The college football alert record (cfb-weather/data/forward/alert_state.json)")
               for s in said)
    assert any(s.startswith("The college football decision record") for s in said)
    assert [s for s in said if re.search(r"\bCFB\b", s)] == []
    assert api.game(store, "401000002")[1]["game"]["sport"] == "College football"      # the game's header line
    assert {g["sport"] for g in api.board(store)["games"]} == {"NFL", "CFB"}           # the tag beside a game


def test_the_new_screens_speak_plainly(root, home):
    """Sentence case, no exclamation marks, "college football" in a sentence, and none of the scorer's own words
    (FINAL, INTERIM, RULE_B, CLV) in what the Signals screen and Home's live panel say."""
    from conftest import rich_store
    store = rich_store(root, home)
    panel = {k: v for k, v in api.home(store).items() if k.startswith("live")}      # Home's own words are the hub's
    said = [s for s in strings([api.signals_screen(store), panel], skip=(
        "sport", "id", "sport_key", "game_id", "text", "error", "log_line", "log_lines", "value", "rule", "result",
        "badge", "kind", "rule_kind", "kick_utc", "logged_utc", "last_written_utc", "generated_utc", "health",
        "bar")) if s]
    assert not [s for s in said if "!" in s]
    assert not [s for s in said if re.search(r"\bCFB\b|\bFINAL\b|\bINTERIM\b|RULE_B|RULE_HT|\bCLV\b", s)]
    sentences = [s for s in said if " " in s and s.endswith(".")]
    assert sentences and all(s[:1].isupper() or s[:1] in "+−0123456789" for s in sentences), [
        s for s in sentences if not (s[:1].isupper() or s[:1] in "+−0123456789")]


def test_the_evidence_list_writes_college_football_out():
    for e in json.loads((CONTENT / "evidence.json").read_text()):
        for k in ("title", "sport", "result", "note", "n", "record", "bar"):
            assert not re.search(r"\bCFB\b", str(e.get(k) or "")), (e["id"], k)


@pytest.mark.parametrize("src, said", [("indoor", "Not an outdoor game"), ("open_roof", "Open roof, not counted"),
                                       ("missing", "No forecast yet"), ("era5", "No lean")])
def test_a_lean_the_model_never_ran_is_not_no_lean(root, home, src, said):
    """The lean model runs only for an outdoor NFL game with a forecast; elsewhere the job logs a blank lean."""
    append(root / "nfl-weather" / "data" / "forward" / "ledger.csv",
           nfl_row(LATE_NFL, "2026_05_LV_LAC", "2026-10-04", "16:05", "LV", "LAC", "not_outdoor" if src != "era5"
                   else "no_trigger", src=src, wind="" if src != "era5" else "8.1") + "\n")
    g = {g["game_id"]: g for g in api.board(make_store(root, home))["games"]}["2026_05_LV_LAC"]
    assert g["rules"][1] == {"rule": "Model lean", "value": "", "words": said, "signal": False, "lean": False,
                             "badge": ""}
    assert words.status_words("lean", "UNDER lean", src) == "Leans under"           # a logged lean is as logged


def test_the_indoor_game_in_the_fixtures(store):
    atl = {g["game_id"]: g for g in api.board(store)["games"]}["2026_05_ATL_NO"]
    assert [c["words"] for c in atl["rules"]] == ["Indoors", "Not an outdoor game"]


def test_the_home_tile_says_what_it_counts():
    """It counts every signal on the board, up to 8 days ahead, not today's."""
    js = (CONTENT.parent / "vfdash" / "static" / "app.js").read_text()
    body = js.split("function drawHome(", 1)[1].split("\n  }\n", 1)[0]
    assert 'tile("Signals on the board"' in body and "Signals today" not in js
    assert "in the latest runs\")" not in body
