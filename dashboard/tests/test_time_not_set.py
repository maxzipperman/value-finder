"""A game whose kickoff time isn't set yet.

The college job logs such a game with cfbfastR's placeholder kickoff, midnight Eastern at the start of the game's
date (start_utc "2026-10-10 04:00:00+00:00", kick_et "Sat 10-10 00:00"), and at an outdoor venue with wx_src and
rule_b "time_tbd" (indoors they are "indoor" and "not_outdoor", with the same placeholder). It is shown as
"Time not set" with its date, never with the placeholder as a kickoff, and it stays on the board and in
games_on_board until its date has passed in Eastern time, also after the job stops logging it (then with its last
row and when that was logged). The board, Home and the light count the same games. An NFL row with a gameday but no
gametime is the same."""
from __future__ import annotations

from datetime import datetime, timezone

import json

from conftest import Clock, cfb_row, make_store, nfl_row, write

from vfdash import api

UTC = timezone.utc
LATE_NFL, LATE_CFB = "2026-10-02T14:30:07Z", "2026-10-02T14:30:14Z"
PLACEHOLDER = "2026-10-10 04:00:00+00:00"                    # midnight Eastern, Sat Oct 10


def append(path, line):
    with path.open("a", newline="") as f:
        f.write(line + "\n")


def add_rows(root, ht="no_price"):
    cfb = root / "cfb-weather" / "data" / "forward" / "ledger.csv"
    # an outdoor game, logged the way the college job logs it
    append(cfb, cfb_row(LATE_CFB, "401000010", "Sat 10-10 00:00", "Air Force", "Army", "time_tbd", ht, PLACEHOLDER,
                        src="time_tbd"))
    # an indoor game: only the placeholder midnight says its time isn't set
    append(cfb, cfb_row(LATE_CFB, "401000011", "Sat 10-10 00:00", "Tulane", "UTSA", "not_outdoor", "below_threshold",
                        PLACEHOLDER, src="indoor"))
    # a game with a time, late on the same date
    append(cfb, cfb_row(LATE_CFB, "401000012", "Sat 10-10 19:30", "Utah State", "Wyoming", "no_trigger",
                        "below_threshold", "2026-10-10 23:30:00+00:00"))
    nfl = root / "nfl-weather" / "data" / "forward" / "ledger.csv"
    append(nfl, nfl_row(LATE_NFL, "2026_05_LV_LAC", "2026-10-04", "", "LV", "LAC", "no_trigger"))


def at(root, home, t):
    return make_store(root, home, clock=Clock(t))


def test_shown_as_time_not_set_with_its_date(root, home):
    add_rows(root)
    store = at(root, home, datetime(2026, 10, 3, 17, 0, tzinfo=UTC))           # Sat Oct 3, 1:00 PM ET
    games = api.board(store)["games"]
    by_id = {g["game_id"]: g for g in games}
    for gid in ("401000010", "401000011"):
        g = by_id[gid]
        assert g["time_set"] is False and g["kick_day"] == "Sat Oct 10"
        assert g["kickoff"] == "Sat Oct 10, time not set"
        assert g["kick_utc"] is None                                            # nothing to count down to
        assert "12:00 AM" not in str(g)
        assert g["days"] == 7
    assert by_id["401000010"]["forecast"] == "Kickoff time not set"
    assert by_id["401000010"]["rules"][0]["words"] == "Kickoff time not set"
    assert by_id["401000012"]["time_set"] is True and by_id["401000012"]["kickoff"] == "Sat Oct 10, 7:30 PM ET"
    lv = by_id["2026_05_LV_LAC"]
    assert lv["time_set"] is False and lv["kickoff"] == "Sun Oct 4, time not set"
    # a game with no time set is listed after the games with a time on its date
    order = [g["game_id"] for g in games if not g["signal"]]
    assert order.index("401000012") < order.index("401000010") and order.index("401000012") < order.index("401000011")
    status, d = api.game(store, "401000010")
    assert status == 200 and d["game"]["kickoff"] == "Sat Oct 10, time not set"


def test_on_the_board_until_its_date_has_passed_in_eastern_time(root, home):
    sat = datetime(2026, 10, 3, 17, 0, tzinfo=UTC)
    before = api.summary(at(root, home, sat))["games_on_board"]
    add_rows(root)
    # Sat Oct 3: all four added games count, the two college games and the NFL game with no time among them
    assert api.summary(at(root, home, sat))["games_on_board"] == before + 4
    # on Oct 10 the NFL games have all been played; the college games of that day are left
    for t, on, n in ((datetime(2026, 10, 10, 4, 30, tzinfo=UTC), True, 4),      # 12:30 AM ET on the day
                     (datetime(2026, 10, 10, 20, 0, tzinfo=UTC), True, 3),      # 4:00 PM ET: 401000002 has started
                     (datetime(2026, 10, 11, 0, 0, tzinfo=UTC), True, 2),       # 8:00 PM ET: so has 401000012
                     (datetime(2026, 10, 11, 3, 59, tzinfo=UTC), True, 2),      # 11:59 PM ET
                     (datetime(2026, 10, 11, 4, 0, tzinfo=UTC), False, 0)):     # midnight: the date has passed
        store = at(root, home, t)
        ids = {g["game_id"] for g in api.board(store)["games"]}
        assert ("401000010" in ids, "401000011" in ids) == (on, on), t
        assert api.summary(store)["games_on_board"] == n, t
    # the NFL game with no time stays until the end of Sun Oct 4, Eastern
    for t, on in ((datetime(2026, 10, 5, 3, 59, tzinfo=UTC), True), (datetime(2026, 10, 5, 4, 0, tzinfo=UTC), False)):
        assert ("2026_05_LV_LAC" in {g["game_id"] for g in api.board(at(root, home, t))["games"]}) == on, t


def test_a_signal_on_a_game_with_no_time_counts_while_it_is_on_the_board(root, home):
    """Rule B can't signal on such a game (it has no forecast), but Rule HT is priced without one. If the
    college job logs Rule HT SIGNAL on it, Signals on the board counts it for as long as the board shows it."""
    add_rows(root, ht="SIGNAL")
    for t, n in ((datetime(2026, 10, 10, 4, 30, tzinfo=UTC), 2),         # 401000002 (Rule HT) and 401000010
                 (datetime(2026, 10, 10, 20, 0, tzinfo=UTC), 1),         # 401000002 has kicked off
                 (datetime(2026, 10, 11, 4, 0, tzinfo=UTC), 0)):
        store = at(root, home, t)
        assert api.summary(store)["signals_live"] == n, t
        assert sum(g["signal"] for g in api.board(store)["games"]) == n, t


RUN_A, RUN_B = "2026-10-10T02:30:14Z", "2026-10-10T14:30:14Z"     # Fri Oct 9, 7:30 PM and Sat Oct 10, 7:30 AM PDT


def agree(store) -> dict:
    """The board, Home and the light's summary, from one store at one time: they must count the same games."""
    s, b, h = api.summary(store), api.board(store), api.home(store)
    games = b["games"]
    assert s["games_on_board"] == len(games) == h["numbers"]["games_on_board"] == sum(
        r["games"] for r in b["runs"].values())
    assert s["signals_live"] == b["signals"] == sum(g["signal"] for g in games) == h["numbers"]["signals_live"]
    assert h["numbers"]["leans_live"] == sum(any(c["lean"] for c in g["rules"]) for g in games)
    return {g["game_id"]: g for g in games}


def run_a(root):
    """Run A, the evening before: two games with no time set (one outdoor with a Rule HT signal, one indoor) and two
    with a time."""
    cfb = root / "cfb-weather" / "data" / "forward" / "ledger.csv"
    append(cfb, cfb_row(RUN_A, "401000010", "Sat 10-10 00:00", "Air Force", "Army", "time_tbd", "SIGNAL", PLACEHOLDER,
                        total="66.5", src="time_tbd"))
    append(cfb, cfb_row(RUN_A, "401000011", "Sat 10-10 00:00", "Tulane", "UTSA", "not_outdoor", "below_threshold",
                        PLACEHOLDER, src="indoor"))
    timed(root, RUN_A)


def timed(root, run):
    cfb = root / "cfb-weather" / "data" / "forward" / "ledger.csv"
    append(cfb, cfb_row(run, "401000012", "Sat 10-10 19:30", "Utah State", "Wyoming", "no_trigger", "below_threshold",
                        "2026-10-10 23:30:00+00:00"))
    append(cfb, cfb_row(run, "401000002", "Sat 10-10 15:30", "Ohio State", "Michigan", "no_trigger",
                        "below_threshold", "2026-10-10 19:30:00+00:00", total="64.5"))


AFTER_B = ((datetime(2026, 10, 10, 16, 0, tzinfo=UTC), {"401000010", "401000011", "401000012", "401000002"}),  # noon ET
           (datetime(2026, 10, 10, 20, 0, tzinfo=UTC), {"401000010", "401000011", "401000012"}),               # 4 PM ET
           (datetime(2026, 10, 11, 3, 59, tzinfo=UTC), {"401000010", "401000011"}),                   # 11:59 PM ET
           (datetime(2026, 10, 11, 4, 0, tzinfo=UTC), set()))                                         # midnight: over


def test_a_later_run_that_leaves_the_game_out(root, home):
    """The college job logs only games whose start_utc is after now, so its first run after the placeholder
    midnight (run B, 7:30 AM Pacific on game day) no longer lists a game whose time isn't set, hours before it is
    played. The game stays on the board with its last row, the light counts it, and the board, Home and the light
    agree until the end of its date."""
    run_a(root)
    by_id = agree(at(root, home, datetime(2026, 10, 10, 4, 30, tzinfo=UTC)))           # 12:30 AM ET, before run B
    assert set(by_id) == {"401000010", "401000011", "401000012", "401000002"}
    timed(root, RUN_B)                                                                  # run B: only the timed games
    for t, ids in AFTER_B:
        store = at(root, home, t)
        by_id = agree(store)
        assert set(by_id) == ids, t
        assert api.summary(store)["signals_live"] == ("401000010" in ids), t
        if ids:
            assert by_id["401000010"]["signal"] is True and by_id["401000010"]["rules"][1]["words"] == "Signal"
    # a game with a time that the latest run no longer lists is on neither the board nor the count, whatever its
    # newest row says: a manual run logs a Rule HT signal on 401000012, then the 11:30 AM run lists only 401000002
    cfb = root / "cfb-weather" / "data" / "forward" / "ledger.csv"
    append(cfb, cfb_row("2026-10-10T15:30:14Z", "401000012", "Sat 10-10 19:30", "Utah State", "Wyoming", "no_trigger",
                        "SIGNAL", "2026-10-10 23:30:00+00:00"))
    append(cfb, cfb_row("2026-10-10T18:30:14Z", "401000002", "Sat 10-10 15:30", "Ohio State", "Michigan",
                        "no_trigger", "below_threshold", "2026-10-10 19:30:00+00:00", total="64.5"))
    store = at(root, home, datetime(2026, 10, 10, 19, 0, tzinfo=UTC))
    by_id = agree(store)
    assert set(by_id) == {"401000010", "401000011", "401000002"}
    assert api.summary(store)["signals_live"] == 1                  # 401000010's Rule HT, not 401000012's


def test_a_game_the_latest_run_no_longer_lists_says_when_it_was_last_logged(root, home):
    run_a(root)
    g = {g["game_id"]: g for g in api.board(at(root, home, datetime(2026, 10, 10, 4, 30, tzinfo=UTC)))["games"]}
    assert g["401000010"]["time_note"] == "Time not set" and g["401000010"]["listed"] is True
    assert g["401000012"]["time_note"] == "" and g["401000012"]["listed"] is True
    timed(root, RUN_B)
    for t, ids in AFTER_B[:3]:
        by_id = {g["game_id"]: g for g in api.board(at(root, home, t))["games"]}
        for gid in ("401000010", "401000011"):
            g = by_id[gid]
            assert g["listed"] is False and g["time_set"] is False and g["kick_utc"] is None
            assert g["time_note"] == "Time not set. Last logged Fri Oct 9, 7:30 PM.", t
            assert g["logged"] == "Fri Oct 9, 7:30 PM" and g["days"] == 0 and g["kick_day"] == "Sat Oct 10"
        assert all(by_id[gid]["listed"] is True for gid in ids - {"401000010", "401000011"})


def test_the_board_never_shows_the_placeholder_as_a_kickoff():
    from pathlib import Path
    js = (Path(__file__).resolve().parents[1] / "vfdash" / "static" / "app.js").read_text()
    body = js.split("function drawBoard(", 1)[1].split("\n  }\n", 1)[0]
    assert "g.time_set === false" in body and "“Time not set”" not in body and '"Time not set"' in body


def test_the_not_eligible_notice_shows_when_it_was_first_logged(root, home):
    """cfb-weather amendment 6 (draft): the alert's key for a Rule HT game with no kickoff time set is "ht_time_tbd",
    and the game page finds the first row logged with Rule HT status "time_tbd", as it does for "ht" and "SIGNAL"."""
    add_rows(root, ht="time_tbd")
    write(root / "cfb-weather" / "data" / "forward" / "alert_state.json",
          json.dumps({"401000010": {"sent": ["ht_time_tbd"]}}))
    store = at(root, home, datetime(2026, 10, 3, 17, 0, tzinfo=UTC))
    status, d = api.game(store, "401000010")
    assert status == 200
    sent = d["alerts"]["sent"]
    assert [s["words"] for s in sent] == ["Rule HT: not eligible, no kickoff time set"]
    assert sent[0]["first_seen"].startswith("First logged on the run of Fri Oct 2")
    assert api.FIRST_SEEN["ht_time_tbd"] == ("rule_ht", "time_tbd")
