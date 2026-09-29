"""home_spreads() (issue #36): each (game, book) spread row is matched to the schedule's home or away
team, and every (game, book) that yields no home spread is counted and reported by reason and season.
No raw data needed."""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cfbweather import build  # noqa: E402

# schedule ids: home and away team per game
HOMES = pd.DataFrame(dict(game_id=[1, 2, 3, 4, 5, 6], home_id=[10, 10, 30, 50, 70, 90], away_id=[20, 40, 40, 60, 80, 20]))
# lower-cased names per team; "iow" stands in for a sportsbook code from the alias table
NAMES = {10: {"iowa", "iow"}, 20: {"troy"}, 30: {"ohio"}, 40: {"kent state"}, 50: {"army"}, 60: {"navy"},
         70: {"utah"}, 80: {"utah state"}, 90: {"tulane"}}


def rows(game_id, book, season, desc, *sides):
    return [dict(game_id=game_id, book=book, season=season, game_desc=desc, abbr=a, lines=x) for a, x in sides]


LINES = pd.DataFrame(
    rows(1, "A", 2015, "Troy@Iowa", ("IOWA", -21.5), ("TROY", 21.5))                           # clean pair
    + rows(1, "B", 2015, "Troy@Iowa", ("IOWA", -21.0), ("TROY", 21.0), ("IOWA", -21.0), ("TROY", 21.0))  # duplicated
    + rows(1, "C", 2015, "Troy@Iowa", ("TROY", 20.5))                                           # one side only
    + rows(2, "A", 2015, "Kent State@Iowa", ("IOW", -14.0), ("KNT", 14.0))                      # alias code
    + rows(3, "A", 2015, "Kent State@Ohio", ("OHI", -3.0), ("KNT", 3.0))                        # no name matches
    + rows(4, "A", 2019, "Navy@Army", ("ARMY", -7.0), ("NAVY", -7.0))                           # both favored
    + rows(5, "A", 2019, "Utah State@Utah", ("UTAH", -10.0), ("UTAH STATE", 10.0), ("BYU", -3.0))  # stray row
    + rows(6, "A", 2019, "Troy@Tulane", ("TROY", 7.0), ("TROY", 7.0))                           # one team twice
    + rows(99, "A", 2019, "X@Y", ("X", 1.0), ("Y", -1.0))                                       # not in the schedule
)


def test_each_book_is_matched_to_the_home_team():
    per_book, _ = build.spread_pairs(LINES, HOMES, NAMES)
    got = per_book.set_index(["game_id", "book"]).home_spread.to_dict()
    assert got == {(1, "A"): -21.5, (1, "B"): -21.0, (1, "C"): -20.5, (2, "A"): -14.0, (5, "A"): -10.0,
                   (6, "A"): -7.0}                                # Troy +7 twice: Tulane is the 7-point favorite


def test_drops_are_counted_by_reason_and_season():
    _, pairs = build.spread_pairs(LINES, HOMES, NAMES)
    assert len(pairs) == 9                                        # every (game, book) is accounted for
    t = build.drop_table(pairs)
    assert t.loc["no_match", 2015] == 1
    assert t.loc["conflict", 2019] == 1
    assert t.loc["not_in_schedule", 2019] == 1
    assert t.loc["matched", 2015] == 4 and t.loc["matched", 2019] == 2
    assert t.loc["dropped", "total"] == 3


def test_home_spreads_reports_the_drops(capsys):
    h = build.home_spreads(LINES, HOMES, NAMES)
    assert h.set_index("game_id").home_spread.to_dict() == {1: -21.0, 2: -14.0, 5: -10.0, 6: -7.0}
    out = capsys.readouterr().out
    assert "home spreads: 9 (game, book) pairs, 6 matched, 3 dropped" in out
    for reason in ("no_match", "conflict", "not_in_schedule"):
        assert reason in out
