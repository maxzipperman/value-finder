"""A game whose kickoff time isn't set yet.

The college job logs such a game with cfbfastR's placeholder kickoff, midnight Eastern at the start of the game's
date (start_utc "2026-10-10 04:00:00+00:00", kick_et "Sat 10-10 00:00"), and at an outdoor venue with wx_src and
rule_b "time_tbd" (indoors they are "indoor" and "not_outdoor", with the same placeholder). It is shown as
"Time not set" with its date, never with the placeholder as a kickoff, and it stays on the board and in
games_on_board until its date has passed in Eastern time. An NFL row with a gameday but no gametime is the same."""
from __future__ import annotations

from datetime import datetime, timezone

from conftest import Clock, cfb_row, make_store, nfl_row

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
    college job logs Rule HT SIGNAL on it, Signals today counts it for as long as the board shows it."""
    add_rows(root, ht="SIGNAL")
    for t, n in ((datetime(2026, 10, 10, 4, 30, tzinfo=UTC), 2),         # 401000002 (Rule HT) and 401000010
                 (datetime(2026, 10, 10, 20, 0, tzinfo=UTC), 1),         # 401000002 has kicked off
                 (datetime(2026, 10, 11, 4, 0, tzinfo=UTC), 0)):
        store = at(root, home, t)
        assert api.summary(store)["signals_live"] == n, t
        assert sum(g["signal"] for g in api.board(store)["games"]) == n, t


def test_the_board_never_shows_the_placeholder_as_a_kickoff():
    from pathlib import Path
    js = (Path(__file__).resolve().parents[1] / "vfdash" / "static" / "app.js").read_text()
    body = js.split("function drawBoard(", 1)[1].split("\n  }\n", 1)[0]
    assert "g.time_set === false" in body and "“Time not set”" not in body and '"Time not set"' in body
