"""Close capture (scripts/capture_close.py, amendment 3) writes at most one closing listing per game. A game is
matched to the feed on its two teams AND its kickoff: among the listings of those teams that start within 6 hours
of the scheduled kickoff, one with a complete Pinnacle quote first (as on the board), then the one nearest the
kickoff. Before Sep 29, 2026 it matched on the teams alone, so a feed that listed the same two
teams twice gave the game two sets of rows, and the scorer (which keeps a game's last Pinnacle row) could
grade against the wrong listing. Everything here runs offline: the Odds API call is replaced by the
project's own parser run on a made-up feed, and data/forward is a temp folder. Nothing is spent."""
import json
import runpy
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from nflweather import config, oddsapi  # noqa: E402

GAMES = pd.DataFrame([dict(game_id=a, season=2026, gameday=b, gametime=c, home_team=d, away_team=e, result=None)
                      for a, b, c, d, e in (("2026_05_PHI_CHI", "2026-10-11", "13:00", "CHI", "PHI"),
                                            ("2026_05_DET_GB", "2026-10-11", "13:00", "GB", "DET"),
                                            ("2026_05_DAL_NYG", "2026-10-11", "16:25", "NYG", "DAL"),
                                            ("2026_06_BUF_KC", "2026-10-18", "16:05", "KC", "BUF"))])
NAME = {"CHI": "Chicago Bears", "PHI": "Philadelphia Eagles", "GB": "Green Bay Packers", "DET": "Detroit Lions",
        "NYG": "New York Giants", "DAL": "Dallas Cowboys", "KC": "Kansas City Chiefs", "BUF": "Buffalo Bills"}
NOW = "2026-10-11T16:50:00Z"                   # 10 minutes before the 1 PM Eastern kickoffs (17:00 UTC)
RIGHT = {"pinnacle": (42.5, -106, -106), "draftkings": (42.5, -110, -110), "fanduel": (43.0, -112, -108)}
WRONG = {"pinnacle": (46.5, -104, -108), "draftkings": (46.0, -110, -110), "fanduel": (46.5, -105, -115)}
GB = {"pinnacle": (39.5, -103, -109), "draftkings": (39.5, -112, -108)}


def listing(eid, home, away, start, books):
    """One event as The Odds API returns it. books: {book: (total, under price, over price)}."""
    return dict(id=eid, sport_key="americanfootball_nfl", commence_time=start, home_team=NAME[home],
                away_team=NAME[away],
                bookmakers=[dict(key=b, last_update="2026-10-11T16:49:00Z",
                                 markets=[dict(key="totals", last_update="2026-10-11T16:48:30Z",
                                               outcomes=[dict(name="Over", price=o, point=t),
                                                         dict(name="Under", price=u, point=t)])])
                            for b, (t, u, o) in books.items()])


def capture(tmp_path, monkeypatch, capsys, now, events):
    """One run of scripts/capture_close.py at `now` against a feed of `events`: (closes.csv text, state, printout)."""
    monkeypatch.setattr(config, "ROOT", tmp_path)
    monkeypatch.setattr(config, "RAW", tmp_path / "raw")
    (tmp_path / "raw").mkdir(exist_ok=True)
    GAMES.to_csv(tmp_path / "raw" / "games.csv", index=False)
    payload = {"snapshot_utc": pd.Timestamp(now).strftime("%Y-%m-%dT%H%MZ"), "data": events}
    monkeypatch.setattr(oddsapi, "live", lambda markets=("totals", "spreads"), **k: oddsapi.parse(payload))
    monkeypatch.setattr(sys, "argv", ["capture_close.py", "--now", now])
    try:
        runpy.run_path(str(ROOT / "scripts" / "capture_close.py"), run_name="__main__")
    except SystemExit:
        pass
    fwd = tmp_path / "data" / "forward"
    text = (fwd / "closes.csv").read_text() if (fwd / "closes.csv").exists() else ""
    state = json.loads((fwd / "close_state.json").read_text()) if (fwd / "close_state.json").exists() else None
    return text, state, capsys.readouterr().out


def scorer_reads(tmp_path):
    """The captured close per game, read the way score_forward.py reads it (the last Pinnacle row with a total)."""
    cap = pd.read_csv(tmp_path / "data" / "forward" / "closes.csv")
    cap = cap[cap.book.eq("pinnacle")].dropna(subset=["close_total"]).drop_duplicates("game_id", keep="last")
    return dict(zip(cap.game_id, cap.close_total))


# ------------------------------------------------------------------ the same two teams listed twice
@pytest.mark.parametrize("other_start", ["2026-10-11T20:25:00Z",       # (a) the same day, another event id
                                         "2026-10-18T17:00:00Z",       # (b) a week later
                                         "2026-12-13T18:00:00Z"])      # (c) two months later
@pytest.mark.parametrize("wrong_first", [False, True])
def test_a_game_listed_twice_takes_the_listing_nearest_its_kickoff(tmp_path, monkeypatch, capsys, other_start,
                                                                   wrong_first):
    right = listing("e1", "CHI", "PHI", "2026-10-11T17:00:00Z", RIGHT)
    wrong = listing("e2", "CHI", "PHI", other_start, WRONG)
    events = ([wrong, right] if wrong_first else [right, wrong]) + [listing("e3", "GB", "DET", "2026-10-11T17:00:00Z", GB)]
    text, state, out = capture(tmp_path, monkeypatch, capsys, NOW, events)
    rows = pd.read_csv(tmp_path / "data" / "forward" / "closes.csv")
    chi = rows[rows.game_id == "2026_05_PHI_CHI"]
    assert list(chi.book) == ["pinnacle", "draftkings", "fanduel"]           # one row per book: one listing only
    assert list(chi.close_total) == [42.5, 42.5, 43.0]
    assert scorer_reads(tmp_path) == {"2026_05_PHI_CHI": 42.5, "2026_05_DET_GB": 39.5}
    assert state == {"captured": ["2026-10-11T17:00Z"], "tries": {"2026-10-11T17:00Z": 1}}
    assert "2026_05_PHI_CHI: 2 feed events of PHI at CHI" in out
    assert "kept e1, the nearest the kickoff with a Pinnacle quote" in out


def test_two_listings_equally_near_kickoff_are_left_unmatched_and_reported(tmp_path, monkeypatch, capsys):
    events = [listing("e1", "CHI", "PHI", "2026-10-11T17:00:00Z", RIGHT),
              listing("e2", "CHI", "PHI", "2026-10-11T17:00:00Z", WRONG),
              listing("e3", "GB", "DET", "2026-10-11T17:00:00Z", GB)]
    text, state, out = capture(tmp_path, monkeypatch, capsys, NOW, events)
    assert text.splitlines()[1] == "2026_05_PHI_CHI,2026-10-11T17:00:00Z,CHI,PHI,,,,,,"     # recorded as missing
    assert scorer_reads(tmp_path) == {"2026_05_DET_GB": 39.5}
    assert "2 are equally good and equally near the kickoff, so none is kept and the close is missing" in out
    assert state == {"captured": [], "tries": {"2026-10-11T17:00Z": 1}}       # retried, as for any missing close
    text, state, out = capture(tmp_path, monkeypatch, capsys, "2026-10-11T16:58:00Z", events)
    assert state == {"captured": ["2026-10-11T17:00Z"], "tries": {"2026-10-11T17:00Z": 2}}   # at most two calls
    assert scorer_reads(tmp_path) == {"2026_05_DET_GB": 39.5}


def test_a_listing_more_than_6_hours_from_kickoff_is_not_the_close(tmp_path, monkeypatch, capsys):
    events = [listing("e2", "CHI", "PHI", "2026-10-18T17:00:00Z", WRONG),
              listing("e3", "GB", "DET", "2026-10-11T17:00:00Z", GB)]
    text, state, out = capture(tmp_path, monkeypatch, capsys, NOW, events)
    assert text.splitlines()[1] == "2026_05_PHI_CHI,2026-10-11T17:00:00Z,CHI,PHI,,,,,,"
    assert scorer_reads(tmp_path) == {"2026_05_DET_GB": 39.5}
    assert "none starts within 6 hours of the kickoff, so the close is missing" in out


def test_a_listing_a_few_minutes_off_the_schedule_still_matches(tmp_path, monkeypatch, capsys):
    """The feed moves a game's start to the actual kickoff once it's under way (seen: 3 minutes)."""
    events = [listing("e1", "CHI", "PHI", "2026-10-11T17:03:12Z", RIGHT), listing("e3", "GB", "DET", "2026-10-11T17:00:00Z", GB)]
    _, _, out = capture(tmp_path, monkeypatch, capsys, NOW, events)
    assert scorer_reads(tmp_path) == {"2026_05_PHI_CHI": 42.5, "2026_05_DET_GB": 39.5}
    assert "feed event" not in out and "listing" not in out  # nothing to report


# ------------------------------------------------------------------ a listing Pinnacle prices comes first, as on the board
# board.one_row_per_game keeps the listing with a complete Pinnacle quote when a game is listed twice. Close
# capture ranks the listings within 6 hours the same way before it looks at the time, so a stale relisting
# without Pinnacle never displaces the priced one. origin/main recorded 42.5 in these cases too (it wrote both
# listings, and the scorer reads only Pinnacle's row).
STALE = {"draftkings": (44.5, -110, -110), "fanduel": (44.5, -110, -110)}          # no Pinnacle


@pytest.mark.parametrize("fresh_start", ["2026-10-11T17:00:00Z",       # a relisted event at the same time
                                         "2026-10-11T17:05:00Z"])      # the unpriced one is nearer the kickoff
@pytest.mark.parametrize("stale_first", [False, True])
def test_a_listing_with_a_pinnacle_quote_beats_a_nearer_one_without(tmp_path, monkeypatch, capsys, fresh_start,
                                                                    stale_first):
    stale = listing("e_stale", "CHI", "PHI", "2026-10-11T17:00:00Z", STALE)
    fresh = listing("e_fresh", "CHI", "PHI", fresh_start, RIGHT)
    events = ([stale, fresh] if stale_first else [fresh, stale]) + [listing("e3", "GB", "DET", "2026-10-11T17:00:00Z", GB)]
    text, state, out = capture(tmp_path, monkeypatch, capsys, NOW, events)
    rows = pd.read_csv(tmp_path / "data" / "forward" / "closes.csv")
    chi = rows[rows.game_id == "2026_05_PHI_CHI"]
    assert list(chi.book) == ["pinnacle", "draftkings", "fanduel"]           # the priced listing's books only
    assert list(chi.close_total) == [42.5, 42.5, 43.0]
    assert scorer_reads(tmp_path) == {"2026_05_PHI_CHI": 42.5, "2026_05_DET_GB": 39.5}
    assert state == {"captured": ["2026-10-11T17:00Z"], "tries": {"2026-10-11T17:00Z": 1}}   # one call, complete
    assert "kept e_fresh, the nearest the kickoff with a Pinnacle quote" in out


def test_two_listings_without_pinnacle_at_the_same_time_are_a_tie(tmp_path, monkeypatch, capsys):
    """Neither gives a close the scorer can use, and the game takes neither: one empty row, retried once."""
    events = [listing("e1", "CHI", "PHI", "2026-10-11T17:00:00Z", STALE),
              listing("e2", "CHI", "PHI", "2026-10-11T17:00:00Z", {"draftkings": (45.0, -110, -110)}),
              listing("e3", "GB", "DET", "2026-10-11T17:00:00Z", GB)]
    text, state, out = capture(tmp_path, monkeypatch, capsys, NOW, events)
    assert text.splitlines()[1] == "2026_05_PHI_CHI,2026-10-11T17:00:00Z,CHI,PHI,,,,,,"
    assert "2 are equally good and equally near the kickoff" in out
    assert state == {"captured": [], "tries": {"2026-10-11T17:00Z": 1}}


# ------------------------------------------------------------------ amendment 7, reading 2: the same game listed twice
# Two feed events equally near the kickoff that carry the same complete Pinnacle quote (the same total and prices)
# are the same game listed twice: the first in the feed is taken. Before, it was a tie and the close was lost (the
# second review of PR 62: main recorded 42.5 there, PR 62 recorded nothing and spent a second credit).
@pytest.mark.parametrize("first", ["e1", "e2"])
def test_two_listings_with_the_same_pinnacle_quote_are_one_game_listed_twice(tmp_path, monkeypatch, capsys, first):
    e1 = listing("e1", "CHI", "PHI", "2026-10-11T17:00:00Z", RIGHT)                      # Pinnacle, DK and FanDuel
    e2 = listing("e2", "CHI", "PHI", "2026-10-11T17:00:00Z", {"pinnacle": RIGHT["pinnacle"]})   # Pinnacle alone
    events = ([e1, e2] if first == "e1" else [e2, e1]) + [listing("e3", "GB", "DET", "2026-10-11T17:00:00Z", GB)]
    text, state, out = capture(tmp_path, monkeypatch, capsys, NOW, events)
    rows = pd.read_csv(tmp_path / "data" / "forward" / "closes.csv")
    chi = rows[rows.game_id == "2026_05_PHI_CHI"]
    assert list(chi.book) == (["pinnacle", "draftkings", "fanduel"] if first == "e1" else ["pinnacle"])  # the first's
    assert scorer_reads(tmp_path) == {"2026_05_PHI_CHI": 42.5, "2026_05_DET_GB": 39.5}
    assert state == {"captured": ["2026-10-11T17:00Z"], "tries": {"2026-10-11T17:00Z": 1}}   # one call, complete
    assert (f"kept {first}, the first in the feed: the 2 feed events equally near the kickoff carry the same Pinnacle "
            "quote, so they are the same game listed twice") in out


@pytest.mark.parametrize("other", [(42.5, -110, -102), (43.0, -106, -106)], ids=["prices", "total"])
def test_equally_near_listings_whose_pinnacle_quotes_differ_are_still_a_tie(tmp_path, monkeypatch, capsys, other):
    events = [listing("e1", "CHI", "PHI", "2026-10-11T17:00:00Z", RIGHT),
              listing("e2", "CHI", "PHI", "2026-10-11T17:00:00Z", {"pinnacle": other}),
              listing("e3", "GB", "DET", "2026-10-11T17:00:00Z", GB)]
    text, state, out = capture(tmp_path, monkeypatch, capsys, NOW, events)
    assert text.splitlines()[1] == "2026_05_PHI_CHI,2026-10-11T17:00:00Z,CHI,PHI,,,,,,"
    assert "2 are equally good and equally near the kickoff, so none is kept and the close is missing" in out
    assert state == {"captured": [], "tries": {"2026-10-11T17:00Z": 1}}


# ------------------------------------------------------------------ amendment 7, reading 2: no usable feed event
# The second review of pull request 64 ran a feed with one event whose books list was empty: the note said "the odds
# feed returned no events at all", which wasn't what happened. The note now says which of the two it was.
UNPRICED = [dict(listing("e1", "CHI", "PHI", "2026-10-11T17:00:00Z", {}), bookmakers=[]),
            dict(listing("e3", "GB", "DET", "2026-10-11T17:00:00Z", {}), bookmakers=[])]


@pytest.mark.parametrize("events, said", [
    ([], "the odds feed returned no events, so every game in the slot is recorded with no feed event"),
    (UNPRICED, "the odds feed returned 2 events, none priced by any logged book, so every game in the slot is "
               "recorded with no feed event"),
    (UNPRICED[:1], "the odds feed returned 1 event, none priced by any logged book, so every game in the slot is "
                   "recorded with no feed event")], ids=["no events", "two events no book prices", "one such event"])
def test_a_feed_with_no_usable_event_records_the_slot_and_says_what_happened(tmp_path, monkeypatch, capsys, events,
                                                                             said):
    """Before: AttributeError ('DataFrame' object has no attribute 'market') before the state was written, so the
    try was never counted. Now every due game is written with no feed event, like a game the feed doesn't list, and
    the state is written as for any incomplete slot: tried once more, then closed."""
    blank = ("2026_05_PHI_CHI,2026-10-11T17:00:00Z,CHI,PHI,,,,,,\n"
             "2026_05_DET_GB,2026-10-11T17:00:00Z,GB,DET,,,,,,\n")
    text, state, out = capture(tmp_path, monkeypatch, capsys, NOW, events)
    assert text == HEADER + blank
    assert state == {"captured": [], "tries": {"2026-10-11T17:00Z": 1}}
    assert "Pinnacle close for 0/2 games, 0 books logged, for 2026-10-11T17:00Z" in out
    assert said in out and out.count("close capture:") == 2                 # the summary line and this one note
    text, state, out = capture(tmp_path, monkeypatch, capsys, "2026-10-11T16:58:00Z", events)
    assert text == HEADER + blank + blank
    assert state == {"captured": ["2026-10-11T17:00Z"], "tries": {"2026-10-11T17:00Z": 2}}   # at most two calls
    assert oddsapi.parse.__name__ == "parse"                               # the parser is left as it was


def test_a_feed_with_no_events_and_then_a_price_records_the_price(tmp_path, monkeypatch, capsys):
    capture(tmp_path, monkeypatch, capsys, NOW, [])
    events = [listing("e1", "CHI", "PHI", "2026-10-11T17:00:00Z", RIGHT),
              listing("e3", "GB", "DET", "2026-10-11T17:00:00Z", GB)]
    text, state, out = capture(tmp_path, monkeypatch, capsys, "2026-10-11T16:58:00Z", events)
    assert scorer_reads(tmp_path) == {"2026_05_PHI_CHI": 42.5, "2026_05_DET_GB": 39.5}
    assert state == {"captured": ["2026-10-11T17:00Z"], "tries": {"2026-10-11T17:00Z": 2}}


# ------------------------------------------------------------------ a malformed start time costs only its own game
def test_a_listing_with_no_start_time_leaves_only_its_own_game_missing(tmp_path, monkeypatch, capsys):
    events = [listing("e1", "CHI", "PHI", None, RIGHT), listing("e3", "GB", "DET", "2026-10-11T17:00:00Z", GB)]
    text, state, out = capture(tmp_path, monkeypatch, capsys, NOW, events)
    assert text.splitlines()[1] == "2026_05_PHI_CHI,2026-10-11T17:00:00Z,CHI,PHI,,,,,,"
    assert scorer_reads(tmp_path) == {"2026_05_DET_GB": 39.5}
    assert "1 feed event of PHI at CHI (e1, no start time); none starts within 6 hours" in out
    assert state == {"captured": [], "tries": {"2026-10-11T17:00Z": 1}}       # the run finished and counted its call


def test_start_times_in_two_formats_both_match(tmp_path, monkeypatch, capsys):
    events = [listing("e1", "CHI", "PHI", "2026-10-11T17:00:00.000Z", RIGHT),
              listing("e3", "GB", "DET", "2026-10-11T17:00:00Z", GB)]
    text, state, out = capture(tmp_path, monkeypatch, capsys, NOW, events)
    assert scorer_reads(tmp_path) == {"2026_05_PHI_CHI": 42.5, "2026_05_DET_GB": 39.5}
    assert state == {"captured": ["2026-10-11T17:00Z"], "tries": {"2026-10-11T17:00Z": 1}}
    assert "feed event" not in out and "listing" not in out


# ------------------------------------------------------------------ ordinary slots: unchanged, byte for byte
# The expected files are what origin/main's script (commit e83c7f8, before this change) wrote from these same
# made-up responses. Listings of games not due (DAL at NYG later that day, BUF at KC next week) are ignored.
HEADER = "game_id,kick_utc,home_team,away_team,capture_utc,book,close_total,close_under,close_over,book_update\n"
ORDINARY = {
    "one slot, two games, other games listed": (
        [(NOW, [listing("e1", "CHI", "PHI", "2026-10-11T17:00:00Z", RIGHT),
                listing("e3", "GB", "DET", "2026-10-11T17:00:00Z", GB),
                listing("e4", "NYG", "DAL", "2026-10-11T20:25:00Z", WRONG),
                listing("e5", "KC", "BUF", "2026-10-18T20:05:00Z", RIGHT)])],
        HEADER
        + "2026_05_PHI_CHI,2026-10-11T17:00:00Z,CHI,PHI,2026-10-11T1650Z,pinnacle,42.5,-106,-106,2026-10-11T16:48:30Z\n"
        "2026_05_PHI_CHI,2026-10-11T17:00:00Z,CHI,PHI,2026-10-11T1650Z,draftkings,42.5,-110,-110,2026-10-11T16:48:30Z\n"
        "2026_05_PHI_CHI,2026-10-11T17:00:00Z,CHI,PHI,2026-10-11T1650Z,fanduel,43.0,-112,-108,2026-10-11T16:48:30Z\n"
        "2026_05_DET_GB,2026-10-11T17:00:00Z,GB,DET,2026-10-11T1650Z,pinnacle,39.5,-103,-109,2026-10-11T16:48:30Z\n"
        "2026_05_DET_GB,2026-10-11T17:00:00Z,GB,DET,2026-10-11T1650Z,draftkings,39.5,-112,-108,2026-10-11T16:48:30Z\n",
        {"captured": ["2026-10-11T17:00Z"], "tries": {"2026-10-11T17:00Z": 1}}),
    "no Pinnacle for one game: retried once, then closed": (
        [(NOW, [listing("e1", "CHI", "PHI", "2026-10-11T17:00:00Z", RIGHT),
                listing("e3", "GB", "DET", "2026-10-11T17:00:00Z", {"draftkings": (39.5, -112, -108)})]),
         ("2026-10-11T16:58:00Z", [listing("e1", "CHI", "PHI", "2026-10-11T17:01:00Z", RIGHT),
                                   listing("e3", "GB", "DET", "2026-10-11T17:00:00Z", {"draftkings": (40.0, -110, -110)})]),
         ("2026-10-11T16:59:00Z", [listing("e3", "GB", "DET", "2026-10-11T17:00:00Z", GB)])],
        HEADER
        + "2026_05_PHI_CHI,2026-10-11T17:00:00Z,CHI,PHI,2026-10-11T1650Z,pinnacle,42.5,-106,-106,2026-10-11T16:48:30Z\n"
        "2026_05_PHI_CHI,2026-10-11T17:00:00Z,CHI,PHI,2026-10-11T1650Z,draftkings,42.5,-110,-110,2026-10-11T16:48:30Z\n"
        "2026_05_PHI_CHI,2026-10-11T17:00:00Z,CHI,PHI,2026-10-11T1650Z,fanduel,43.0,-112,-108,2026-10-11T16:48:30Z\n"
        "2026_05_DET_GB,2026-10-11T17:00:00Z,GB,DET,2026-10-11T1650Z,draftkings,39.5,-112,-108,2026-10-11T16:48:30Z\n"
        "2026_05_PHI_CHI,2026-10-11T17:00:00Z,CHI,PHI,2026-10-11T1658Z,pinnacle,42.5,-106,-106,2026-10-11T16:48:30Z\n"
        "2026_05_PHI_CHI,2026-10-11T17:00:00Z,CHI,PHI,2026-10-11T1658Z,draftkings,42.5,-110,-110,2026-10-11T16:48:30Z\n"
        "2026_05_PHI_CHI,2026-10-11T17:00:00Z,CHI,PHI,2026-10-11T1658Z,fanduel,43.0,-112,-108,2026-10-11T16:48:30Z\n"
        "2026_05_DET_GB,2026-10-11T17:00:00Z,GB,DET,2026-10-11T1658Z,draftkings,40.0,-110,-110,2026-10-11T16:48:30Z\n",
        {"captured": ["2026-10-11T17:00Z"], "tries": {"2026-10-11T17:00Z": 2}}),
    "a game the feed doesn't list": (
        [(NOW, [listing("e1", "CHI", "PHI", "2026-10-11T17:00:00Z", RIGHT),
                listing("e4", "NYG", "DAL", "2026-10-11T20:25:00Z", WRONG)])],
        HEADER
        + "2026_05_PHI_CHI,2026-10-11T17:00:00Z,CHI,PHI,2026-10-11T1650Z,pinnacle,42.5,-106.0,-106.0,2026-10-11T16:48:30Z\n"
        "2026_05_PHI_CHI,2026-10-11T17:00:00Z,CHI,PHI,2026-10-11T1650Z,draftkings,42.5,-110.0,-110.0,2026-10-11T16:48:30Z\n"
        "2026_05_PHI_CHI,2026-10-11T17:00:00Z,CHI,PHI,2026-10-11T1650Z,fanduel,43.0,-112.0,-108.0,2026-10-11T16:48:30Z\n"
        "2026_05_DET_GB,2026-10-11T17:00:00Z,GB,DET,,,,,,\n",
        {"captured": [], "tries": {"2026-10-11T17:00Z": 1}}),
}


@pytest.mark.parametrize("case", list(ORDINARY))
def test_an_ordinary_slot_writes_exactly_what_it_wrote_before(tmp_path, monkeypatch, capsys, case):
    runs, want_csv, want_state = ORDINARY[case]
    for now, events in runs:
        text, state, out = capture(tmp_path, monkeypatch, capsys, now, events)
        assert "feed event" not in out and "listing" not in out  # no duplicate, nothing to report
    assert text == want_csv
    assert state == want_state
