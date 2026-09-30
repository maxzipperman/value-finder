"""The page as drawn, not only the server's answer: app.js is run in Node with a small stand-in for the browser
(render_page.mjs) on the Board and Game answers of the fixtures. Skipped where Node isn't installed."""
from __future__ import annotations

import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pytest
from conftest import Clock, cfb_row, make_store

from vfdash import api

HERE = Path(__file__).resolve().parent
APP_JS = HERE.parent / "vfdash" / "static" / "app.js"
NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="Node is not installed")


def draw(tmp_path, hash_: str, answer: dict) -> dict:
    f = tmp_path / "answer.json"
    f.write_text(json.dumps(answer, ensure_ascii=False))
    out = subprocess.run([NODE, str(HERE / "render_page.mjs"), str(APP_JS), hash_, str(f)], capture_output=True,
                         text=True, timeout=60, check=True)
    return json.loads(out.stdout)


def text(n) -> str:
    return n["text"] if "text" in n else "".join(text(k) for k in n["kids"])


def find(n, tag):
    if "tag" in n:
        if n["tag"] == tag:
            yield n
        for k in n["kids"]:
            yield from find(k, tag)


def table(n, first_head: str):
    """(headers, {first link or cell text: [cell texts]}) of the tables whose first header is `first_head`, in order
    (the Board draws its signals and everything else as two tables with the same headers)."""
    found, rows = None, {}
    for t in find(n, "table"):
        heads = [text(th) for th in find(t, "th")]
        if heads and heads[0] == first_head:
            found = heads
            for tr in find(next(find(t, "tbody")), "tr"):
                cells = [text(td) for td in find(tr, "td")]
                links = [text(a) for a in find(tr, "a")]
                rows[links[0] if links else cells[0]] = cells
    if found is None:
        raise AssertionError(f"no table headed {first_head!r}")
    return found, rows


def test_the_board_as_drawn(root, home, tmp_path):
    with (root / "cfb-weather" / "data" / "forward" / "ledger.csv").open("a") as f:
        f.write(cfb_row("2026-10-02T14:30:14Z", "401000010", "Sat 10-10 00:00", "Air Force", "Army", "time_tbd",
                        "no_price", "2026-10-10 04:00:00+00:00", src="time_tbd") + "\n")
    store = make_store(root, home, clock=Clock(datetime(2026, 10, 3, 17, 0, tzinfo=timezone.utc)))
    page = draw(tmp_path, "#board", api.board(store))
    heads, rows = table(page, "Kickoff (ET)")
    assert heads == ["Kickoff (ET)", "Matchup", "Forecast", "Total and under", "Wind rule’s value",
                     "Lean model’s chance of the under", "Rules", "Best number"]
    w, lean = heads.index("Wind rule’s value"), heads.index("Lean model’s chance of the under")
    assert (rows["BUF at NE"][w], rows["BUF at NE"][lean]) == ("+10.4%+12.0% at the best number", "52%")
    assert (rows["ARI at NYG"][w], rows["ARI at NYG"][lean]) == ("—", "52%")       # no wind trigger
    assert (rows["ATL at NO"][w], rows["ATL at NO"][lean]) == ("—", "—")           # indoors
    assert (rows["Ohio State at Michigan"][w], rows["Ohio State at Michigan"][lean]) == ("—", "—")
    assert rows["Air Force at Army"][0] == "Sat Oct 10Time not setin 7 days"
    drawn = text(page)
    assert "EV " not in drawn and "12:00 AM" not in drawn
    assert ("Wind rule’s value is Rule B’s expected value for the under, from the rule’s registered pricing model. It "
            "is shown only when the wind rule has signalled, or when the value is not above zero, which is why it did "
            "not signal. Rule B has not cleared the project’s multiple-testing bar: none of its ") in drawn
    assert "trigger was met" not in drawn and "Neither is a proven edge." in drawn


def test_a_game_the_latest_run_no_longer_lists_as_drawn(root, home, tmp_path):
    """A game whose time isn't set, after the college job has stopped logging it: on the board with its last row,
    and the words the hub chose."""
    cfb = root / "cfb-weather" / "data" / "forward" / "ledger.csv"
    with cfb.open("a") as f:
        f.write(cfb_row("2026-10-10T02:30:14Z", "401000010", "Sat 10-10 00:00", "Air Force", "Army", "time_tbd",
                        "SIGNAL", "2026-10-10 04:00:00+00:00", total="66.5", src="time_tbd") + "\n")
        f.write(cfb_row("2026-10-10T14:30:14Z", "401000002", "Sat 10-10 15:30", "Ohio State", "Michigan",
                        "no_trigger", "below_threshold", "2026-10-10 19:30:00+00:00") + "\n")
    store = make_store(root, home, clock=Clock(datetime(2026, 10, 10, 16, 0, tzinfo=timezone.utc)))   # noon ET
    heads, rows = table(draw(tmp_path, "#board", api.board(store)), "Kickoff (ET)")
    assert rows["Air Force at Army"][0] == "Sat Oct 10Time not set. Last logged Fri Oct 9, 7:30 PM.today"
    assert "Rule HT: Signal" in rows["Air Force at Army"][heads.index("Rules")]
    home_ = draw(tmp_path, "#home", api.home(store))
    tiles = {text(t["kids"][0]): text(t["kids"][1]) for t in find(home_, "div") if t["cls"] == "tile"}
    assert tiles["Signals on the board"] == "1" and tiles["Games on the board"] == "2"


def test_a_game_as_drawn(store, tmp_path):
    status, answer = api.game(store, "2026_05_KC_DEN")
    heads, rows = table(draw(tmp_path, "#game/2026_05_KC_DEN", answer), "Logged")
    w, lean = heads.index("Wind rule’s value"), heads.index("Lean model’s chance of the under")
    assert [(cells[w], cells[lean]) for cells in rows.values()] == [("+10.4%+12.0% at the best number", "52%"),
                                                                    ("—", "52%")]
