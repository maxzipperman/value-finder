"""What the Board and Game screens show beside a game, and on which games.

Rule B's expected value (ev_under) and its value at the best number (ev_best_line) are logged on nearly every
priced row, because the jobs price every game; but the price is that of an under in a windy game (the pricing
cohort is outdoor games with 15+ mph wind). So the value is shown only on a Rule B signal, at either price, and on
a row whose status is "negative_ev", where the value (not above zero) is why there is no signal. Everywhere else a
positive value would read as a priced edge on a game that is not a signal: a dash is shown, and the Rules column
says why. The value at the best number is shown on a signal only. The NFL lean model's chance of the under
(p_under) is a different model: it has its own column, for outdoor NFL games only."""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from conftest import CONTENT, cfb_row, copy_content, make_store, nfl_row

from vfdash import api

APP_JS = Path(__file__).resolve().parents[1] / "vfdash" / "static" / "app.js"
LATE_NFL, LATE_CFB = "2026-10-02T14:30:07Z", "2026-10-02T14:30:14Z"
TRIGGER_MET = ("SIGNAL", "SIGNAL_SECONDARY", "price_too_high", "negative_ev", "no_price", "outside_horizon")
NOT_MET = ("no_trigger", "not_outdoor", "time_tbd", "no_venue", "no_forecast", "missing", "", "something_new")
VALUE_SHOWN = ("SIGNAL", "SIGNAL_SECONDARY", "negative_ev")
BEST_SHOWN = ("SIGNAL", "SIGNAL_SECONDARY")


def append(path, line):
    with path.open("a", newline="") as f:
        f.write(line + "\n")


def board_by_id(store):
    return {g["game_id"]: g for g in api.board(store)["games"]}


def with_values(line: str, ev_under: str, ev_best: str) -> str:
    """A fixture row with its own ev_under and ev_best_line (the fixtures log +10.4%/+12.0% or +8.0%/+8.7%)."""
    return line.replace(",0.104,", f",{ev_under},").replace(",0.12,", f",{ev_best},").replace(
        ",0.08,", f",{ev_under},").replace(",0.087,", f",{ev_best},")


def test_the_wind_rules_value_only_on_a_signal(store):
    by_id = board_by_id(store)
    buf = by_id["2026_05_BUF_NE"]                                     # Rule B signal at Pinnacle
    assert (buf["wind_value"], buf["wind_value_best"]) == ("+10.4%", "+12.0%")
    assert by_id["2026_05_TEN_BAL"]["wind_value"] == "+10.4%"         # at the backup price
    # every other row logs ev_under and ev_best_line too, as the jobs do; none signalled under Rule B
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
    for gid, value, best in (("2026_05_LV_LAC", "+10.4%", "+12.0%"), ("401000009", "+8.0%", "+8.7%")):
        g = by_id[gid]
        assert g["wind_value"] == (value if status in VALUE_SHOWN else ""), gid
        assert g["wind_value_best"] == (best if status in BEST_SHOWN else ""), gid
        assert g["wind_rule_met"] is (status in TRIGGER_MET), gid


def test_a_trigger_that_did_not_signal_shows_no_value(root, home):
    """The review's case on the live data: a college game with the wind trigger met but outside the 1 to 3 day
    window logged +8.1%, which read as a priced edge on a game that is not a signal. A price too high is the same."""
    cfb = root / "cfb-weather" / "data" / "forward" / "ledger.csv"
    append(cfb, with_values(cfb_row(LATE_CFB, "401856821", "Sat 10-03 19:30", "Texas Tech", "Colorado",
                                    "outside_horizon", "before_window", "2026-10-03 23:30:00+00:00"),
                            "0.08070175438596483", "0.08070175438596483"))
    append(cfb, with_values(cfb_row(LATE_CFB, "401000020", "Sat 10-03 15:30", "Iowa", "Minnesota", "price_too_high",
                                    "before_window", "2026-10-03 19:30:00+00:00"), "0.051", "0.062"))
    by_id = board_by_id(make_store(root, home))
    for gid, words in (("401856821", "Wind trigger, outside the 1 to 3 day window"),
                       ("401000020", "Wind trigger, price too high")):
        g = by_id[gid]
        assert (g["wind_value"], g["wind_value_best"]) == ("", ""), gid
        assert g["rules"][0]["words"] == words and g["signal"] is False
        assert "8.1%" not in json.dumps(g, ensure_ascii=False) and "+5.1%" not in json.dumps(g, ensure_ascii=False)


def test_a_value_below_zero_is_shown_as_the_reason_but_not_the_best_number(root, home):
    """negative_ev: the value, not above zero, is what says why there is no signal. The value at another book's
    best number may be above zero; it is shown on a signal only."""
    append(root / "nfl-weather" / "data" / "forward" / "ledger.csv",
           with_values(nfl_row(LATE_NFL, "2026_05_LV_LAC", "2026-10-04", "16:05", "LV", "LAC", "negative_ev",
                               wind="16.4"), "-0.012", "0.031"))
    g = board_by_id(make_store(root, home))["2026_05_LV_LAC"]
    assert (g["wind_value"], g["wind_value_best"]) == ("−1.2%", "")
    assert g["rules"][0]["words"] == "Wind trigger, expected value below zero" and g["signal"] is False


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


WIND_WORDS = ("Wind rule’s value is Rule B’s expected value for the under, from the rule’s registered pricing model. "
              "It is shown only when the wind rule has signalled, or when the value is not above zero, which is why it "
              "did not signal.")


@pytest.mark.parametrize("fn", ["drawBoard", "drawGame"])
def test_the_page_says_when_the_value_is_shown(fn):
    assert "windValueWords(d.wind_rule_bar)" in js_function(fn)
    words = js_function("windValueWords")
    assert WIND_WORDS in words and "trigger was met" not in words
    assert "Neither is a proven edge." in js_function(fn)


def rule_b_results() -> int:
    return sum(1 for e in json.loads((CONTENT / "evidence.json").read_text()) if "rule-b" in e["id"])


def test_whether_rule_b_clears_the_bar_is_read_from_the_evidence_list(root, home, tmp_path, store):
    n = rule_b_results()
    assert n >= 1
    expected = (f"Rule B has not cleared the project’s multiple-testing bar: none of its {n} results on the Research "
                "screen does.")
    assert api.board(store)["wind_rule_bar"] == expected
    assert api.game(store, "2026_05_BUF_NE")[1]["wind_rule_bar"] == expected
    # the hub marks one as clearing: the sentence follows the list, and still says a signal isn't a proven bet
    content = copy_content(tmp_path / "content")
    entries = json.loads((content / "evidence.json").read_text())
    next(e for e in entries if "rule-b" in e["id"])["clears_bar"] = True
    (content / "evidence.json").write_text(json.dumps(entries))
    assert api.board(make_store(root, home, content=content))["wind_rule_bar"] == (
        f"1 of Rule B’s {n} results on the Research screen clears the project’s multiple-testing bar; a signal is "
        "still a paper entry for the forward test, not a proven bet.")
    # a list that can't be read: not counted as clearing it
    (content / "evidence.json").write_text("[{")
    assert api.board(make_store(root, home, content=content))["wind_rule_bar"] == (
        "Rule B is not counted as clearing the project’s multiple-testing bar: the evidence list has no Rule B result "
        "that can be read.")
