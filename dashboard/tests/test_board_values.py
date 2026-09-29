"""What the Board and Game screens show beside a game, and on which games.

Rule B's expected value (ev_under) and its value at the best number (ev_best_line) are logged on nearly every
priced row, because the jobs price every game; but the price is that of an under in a windy game (the pricing
cohort is outdoor games with 15+ mph wind). So they are shown only on a row whose Rule B status says the wind
trigger was met. The NFL lean model's chance of the under (p_under) is a different model: it has its own column,
for outdoor NFL games only."""
from __future__ import annotations

import re
from pathlib import Path

import pytest
from conftest import cfb_row, make_store, nfl_row

from vfdash import api

APP_JS = Path(__file__).resolve().parents[1] / "vfdash" / "static" / "app.js"
LATE_NFL, LATE_CFB = "2026-10-02T14:30:07Z", "2026-10-02T14:30:14Z"
TRIGGER_MET = ("SIGNAL", "SIGNAL_SECONDARY", "price_too_high", "negative_ev", "no_price", "outside_horizon")
NOT_MET = ("no_trigger", "not_outdoor", "time_tbd", "no_venue", "no_forecast", "missing", "", "something_new")


def append(path, line):
    with path.open("a", newline="") as f:
        f.write(line + "\n")


def board_by_id(store):
    return {g["game_id"]: g for g in api.board(store)["games"]}


def test_the_wind_rules_value_only_where_its_trigger_was_met(store):
    by_id = board_by_id(store)
    buf = by_id["2026_05_BUF_NE"]                                     # Rule B signal at Pinnacle
    assert (buf["wind_value"], buf["wind_value_best"]) == ("+10.4%", "+12.0%")
    assert by_id["2026_05_TEN_BAL"]["wind_value"] == "+10.4%"         # at the backup price
    # every other row logs ev_under and ev_best_line too, as the jobs do; none met the wind trigger
    for gid in ("2026_05_KC_DEN", "2026_05_ARI_NYG", "2026_05_ATL_NO", "401000002", "401000003", "401000004"):
        assert (by_id[gid]["wind_value"], by_id[gid]["wind_value_best"]) == ("", ""), gid
        assert by_id[gid]["wind_rule_met"] is False
    assert buf["wind_rule_met"] is True
    for g in by_id.values():                                          # no ungated copy travels with the row
        assert "ev" not in g and "model_chance" not in g


def test_the_lean_models_chance_only_on_outdoor_nfl_games(store):
    by_id = board_by_id(store)
    assert by_id["2026_05_ARI_NYG"]["lean_chance"] == "52%"           # outdoor, with a forecast
    assert by_id["2026_05_BUF_NE"]["lean_chance"] == "52%"
    assert by_id["2026_05_ATL_NO"]["lean_chance"] == ""               # indoors: the lean model doesn't apply
    for gid in ("401000002", "401000003", "401000004"):               # college football has no lean model
        assert by_id[gid]["lean_chance"] == "", gid


@pytest.mark.parametrize("status", TRIGGER_MET + NOT_MET)
def test_each_rule_b_status(root, home, status):
    append(root / "nfl-weather" / "data" / "forward" / "ledger.csv",
           nfl_row(LATE_NFL, "2026_05_LV_LAC", "2026-10-04", "16:05", "LV", "LAC", status))
    append(root / "cfb-weather" / "data" / "forward" / "ledger.csv",
           cfb_row(LATE_CFB, "401000009", "Sat 10-03 15:30", "Iowa", "Minnesota", status, "before_window",
                   "2026-10-03 19:30:00+00:00"))
    by_id = board_by_id(make_store(root, home))
    shown = status in TRIGGER_MET
    assert by_id["2026_05_LV_LAC"]["wind_value"] == ("+10.4%" if shown else "")
    assert by_id["2026_05_LV_LAC"]["wind_value_best"] == ("+12.0%" if shown else "")
    assert by_id["401000009"]["wind_value"] == ("+8.0%" if shown else "")
    assert by_id["401000009"]["wind_value_best"] == ("+8.7%" if shown else "")


def test_the_game_screen_gates_each_logged_row(store):
    status, d = api.game(store, "2026_05_KC_DEN")                     # a signal, then no wind trigger
    assert status == 200
    assert [r["wind_value"] for r in d["rows"]] == ["+10.4%", ""]
    assert [r["lean_chance"] for r in d["rows"]] == ["52%", "52%"]
    status, d = api.game(store, "2026_05_ATL_NO")                     # indoors
    assert [(r["wind_value"], r["lean_chance"]) for r in d["rows"]] == [("", "")]


def js_function(name: str) -> str:
    js = APP_JS.read_text()
    return js.split(f"function {name}(", 1)[1].split("\n  }\n", 1)[0]


@pytest.mark.parametrize("fn", ["drawBoard", "drawGame"])
def test_the_two_columns_are_headed_apart(fn):
    body = js_function(fn)
    heads = re.findall(r'\[("Kickoff[^\]]*|"Logged[^\]]*)\]', body)
    assert heads, fn
    cells = [c.strip().strip('"') for c in heads[0].split(",")]
    assert "Model" not in cells
    i, j = cells.index("Wind rule’s value"), cells.index("Lean model’s chance of the under")
    assert j == i + 1 and cells[i + 2] == "Rules"
    assert "g.ev" not in body and "r.ev" not in body and "model_chance" not in body


def test_the_board_says_what_the_two_columns_are():
    body = js_function("drawBoard")
    line = ("Wind rule’s value is Rule B’s expected value for the under, priced as if the game were played in wind "
            "of 15 mph or more, so it is shown only where the wind trigger was met. Lean model’s chance of the under "
            "is the NFL lean model’s own estimate, for outdoor NFL games only. Neither is a proven edge.")
    assert line in body
