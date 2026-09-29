"""Close capture (scripts/capture_close.py, amendment 2) writes one closing row per game. A game is matched to the
feed on its two teams AND its kickoff: among the listings of those teams that start within 6 hours of the
scheduled kickoff, one priced at Pinnacle first, then DraftKings, then neither (as on the board), then the one
nearest the kickoff. Before Sep 29, 2026 it matched on the teams alone, so a feed that listed the same two teams
twice (a relisted event, or a rematch such as a conference title game) gave the game two rows, and the scorer
(which keeps a game's last row) could grade against the wrong listing. Everything here runs offline: the Odds
API call is replaced by the project's own parser run on a made-up feed, the schedule is made up, and
data/forward is a temp folder. Nothing is spent."""
import json
import runpy
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cfbweather import board, build, config, fetch  # noqa: E402

SCHEDULE = pd.DataFrame([dict(game_id=a, season=2026, start_utc=pd.Timestamp(b), tbd=False, home_points=float("nan"),
                              home_team=c, away_team=d, home_division="fbs", away_division="fbs")
                         for a, b, c, d in ((401, "2026-11-28T20:30:00Z", "Alabama", "Auburn"),
                                            (402, "2026-11-28T20:30:00Z", "Georgia", "Georgia Tech"),
                                            (403, "2026-11-28T17:00:00Z", "Michigan", "Ohio State"),
                                            (404, "2026-11-28T20:45:00Z", "Navy", "Army"))])
NAMES = {"Alabama Crimson Tide": "Alabama", "Auburn Tigers": "Auburn", "Georgia Bulldogs": "Georgia",
         "Georgia Tech Yellow Jackets": "Georgia Tech", "Ohio State Buckeyes": "Ohio State",
         "Michigan Wolverines": "Michigan", "Navy Midshipmen": "Navy", "Army Black Knights": "Army"}
FEED = {v: k for k, v in NAMES.items()}
NOW = "2026-11-28T20:15:00Z"                   # 15 minutes before the 20:30 UTC kickoffs
RIGHT = {"pinnacle": (48.5, -105, -115), "draftkings": (48.5, -110, -110), "fanduel": (49.0, -108, -112)}
WRONG = {"pinnacle": (52.5, -110, -110), "draftkings": (52.0, -110, -110)}
UGA = {"draftkings": (55.5, -112, -108), "fanduel": (55.5, -110, -110)}


def listing(home, away, start, books, home_name=None, eid=None):
    """One event as The Odds API returns it. books: {book: (total, under price, over price)}."""
    return dict(id=eid or f"{home}-{start}", sport_key="americanfootball_ncaaf", commence_time=start,
                home_team=home_name or FEED[home], away_team=FEED[away],
                bookmakers=[dict(key=b, last_update="2026-10-11T16:49:00Z",
                                 markets=[dict(key="totals", last_update="2026-10-11T16:48:30Z",
                                               outcomes=[dict(name="Over", price=o, point=t),
                                                         dict(name="Under", price=u, point=t)])])
                            for b, (t, u, o) in books.items()])


def capture(tmp_path, monkeypatch, capsys, now, events):
    """One run of scripts/capture_close.py at `now` against a feed of `events`: (closes.csv text, state, printout)."""
    monkeypatch.setattr(config, "ROOT", tmp_path)
    monkeypatch.setattr(build, "schedules", lambda: SCHEDULE.copy())
    monkeypatch.setattr(board, "odds_team_names", lambda: NAMES)
    monkeypatch.setattr(fetch, "odds_api_totals", lambda names: fetch.parse_odds_api(events, names, now))
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
    """The captured close per game, read the way score_forward.py reads it (the last row with a total)."""
    cap = pd.read_csv(tmp_path / "data" / "forward" / "closes.csv").dropna(subset=["close_total"])
    cap = cap.drop_duplicates("game_id", keep="last")
    return dict(zip(cap.game_id, cap.close_total))


# ------------------------------------------------------------------ the same two teams listed twice
@pytest.mark.parametrize("other_start", ["2026-11-29T00:00:00Z",       # (a) the same day, another listing
                                         "2026-12-05T21:00:00Z",       # (b) a week later: the conference title game
                                         "2027-01-11T00:30:00Z"])      # (c) months later: a bowl
@pytest.mark.parametrize("wrong_first", [False, True])
def test_a_game_listed_twice_takes_the_listing_nearest_its_kickoff(tmp_path, monkeypatch, capsys, other_start,
                                                                   wrong_first):
    right = listing("Alabama", "Auburn", "2026-11-28T20:30:00Z", RIGHT)
    wrong = listing("Alabama", "Auburn", other_start, WRONG)
    events = ([wrong, right] if wrong_first else [right, wrong]) + [listing("Georgia", "Georgia Tech",
                                                                            "2026-11-28T20:30:00Z", UGA)]
    text, state, out = capture(tmp_path, monkeypatch, capsys, NOW, events)
    rows = pd.read_csv(tmp_path / "data" / "forward" / "closes.csv")
    assert list(rows.game_id) == [401, 402]                                   # one row per game
    assert scorer_reads(tmp_path) == {401: 48.5, 402: 55.5}
    assert state == {"captured": ["2026-11-28T20:30Z"], "tries": {"2026-11-28T20:30Z": 1}}
    assert "401: 2 feed listings of Auburn at Alabama" in out
    assert "kept the one starting 2026-11-28T20:30:00Z, the nearest the kickoff priced at Pinnacle" in out


def test_two_listings_equally_near_kickoff_are_left_unmatched_and_reported(tmp_path, monkeypatch, capsys):
    events = [listing("Alabama", "Auburn", "2026-11-28T20:30:00Z", RIGHT),
              listing("Alabama", "Auburn", "2026-11-28T20:30:00Z", WRONG, eid="relisted"),
              listing("Georgia", "Georgia Tech", "2026-11-28T20:30:00Z", UGA)]
    text, state, out = capture(tmp_path, monkeypatch, capsys, NOW, events)
    assert text.splitlines()[1] == ",401,2026-11-28T20:30:00Z,Alabama,Auburn,,,,"         # recorded as missing
    assert scorer_reads(tmp_path) == {402: 55.5}
    assert "2 are equally good and equally near the kickoff, so none is kept and the close is missing" in out
    assert state == {"captured": [], "tries": {"2026-11-28T20:30Z": 1}}       # retried, as for any missing close
    text, state, out = capture(tmp_path, monkeypatch, capsys, "2026-11-28T20:25:00Z", events)
    assert state["tries"]["2026-11-28T20:30Z"] == 2 and "2026-11-28T20:30Z" in state["captured"]   # at most two calls
    assert scorer_reads(tmp_path) == {402: 55.5}


def test_a_listing_more_than_6_hours_from_kickoff_is_not_the_close(tmp_path, monkeypatch, capsys):
    events = [listing("Alabama", "Auburn", "2026-12-05T21:00:00Z", WRONG),
              listing("Georgia", "Georgia Tech", "2026-11-28T20:30:00Z", UGA)]
    text, state, out = capture(tmp_path, monkeypatch, capsys, NOW, events)
    assert text.splitlines()[1] == ",401,2026-11-28T20:30:00Z,Alabama,Auburn,,,,"
    assert scorer_reads(tmp_path) == {402: 55.5}
    assert "none starts within 6 hours of the kickoff, so the close is missing" in out


# ------------------------------------------------------------------ Pinnacle, then DraftKings, then neither, as on the board
# Registered text (amendment 2): "Pinnacle when it lists the game, else DraftKings, the same as the board".
# board.one_row_per_game keeps the listing priced at the first of fetch.RULE_BOOKS when a game is listed twice.
# Close capture ranks the listings within 6 hours the same way before it looks at the time. With an unpriced
# relisting, origin/main also recorded 48.5 (its unpriced row has no total, and the scorer skips it); with a
# DraftKings relisting, main recorded whichever listing the feed gave last.
FD_ONLY = {"fanduel": (51.5, -110, -110)}                                     # priced at neither rule book
DK_ONLY = {"draftkings": (50.5, -110, -110), "fanduel": (50.5, -110, -110)}


@pytest.mark.parametrize("other", [FD_ONLY, DK_ONLY], ids=["unpriced", "draftkings"])
@pytest.mark.parametrize("pin_start", ["2026-11-28T20:30:00Z",         # a relisted event at the same time
                                       "2026-11-28T20:35:00Z"])        # the other listing is nearer the kickoff
@pytest.mark.parametrize("other_first", [False, True])
def test_a_listing_priced_at_pinnacle_beats_a_nearer_one_that_is_not(tmp_path, monkeypatch, capsys, other,
                                                                     pin_start, other_first):
    stale = listing("Alabama", "Auburn", "2026-11-28T20:30:00Z", other, eid="stale")
    fresh = listing("Alabama", "Auburn", pin_start, RIGHT, eid="fresh")
    events = ([stale, fresh] if other_first else [fresh, stale]) + [listing("Georgia", "Georgia Tech",
                                                                            "2026-11-28T20:30:00Z", UGA)]
    text, state, out = capture(tmp_path, monkeypatch, capsys, NOW, events)
    rows = pd.read_csv(tmp_path / "data" / "forward" / "closes.csv")
    assert list(rows.game_id) == [401, 402] and list(rows.line_src) == ["pinnacle", "draftkings"]   # one row each
    assert list(rows.close_total) == [48.5, 55.5] and list(rows.close_under) == [-105, -112]
    assert state == {"captured": ["2026-11-28T20:30Z"], "tries": {"2026-11-28T20:30Z": 1}}   # one call, complete
    assert f"kept the one starting {pin_start}, the nearest the kickoff priced at Pinnacle" in out


def test_draftkings_beats_a_listing_priced_at_neither(tmp_path, monkeypatch, capsys):
    events = [listing("Alabama", "Auburn", "2026-11-28T20:30:00Z", FD_ONLY, eid="stale"),
              listing("Alabama", "Auburn", "2026-11-28T20:40:00Z", DK_ONLY, eid="dk"),
              listing("Georgia", "Georgia Tech", "2026-11-28T20:30:00Z", UGA)]
    text, state, out = capture(tmp_path, monkeypatch, capsys, NOW, events)
    assert scorer_reads(tmp_path) == {401: 50.5, 402: 55.5}
    assert "kept the one starting 2026-11-28T20:40:00Z, the nearest the kickoff priced at DraftKings" in out


# ------------------------------------------------------------------ amendment 5, reading 2: the same game listed twice
# Two listings equally near the kickoff, priced at the same rule book with the same quote (the same total and
# prices), are the same game listed twice: the first listed is taken. Before, it was a tie and the close was lost
# (the second review of PR 62: main recorded Georgia's 55.5 there, PR 62 recorded nothing).
@pytest.mark.parametrize("book", ["pinnacle", "draftkings"])
@pytest.mark.parametrize("extra_first", [False, True])
def test_two_listings_with_the_same_rule_book_quote_are_one_game_listed_twice(tmp_path, monkeypatch, capsys, book,
                                                                             extra_first):
    quote = RIGHT[book]
    plain = listing("Alabama", "Auburn", "2026-11-28T20:30:00Z", {book: quote}, eid="plain")
    extra = listing("Alabama", "Auburn", "2026-11-28T20:30:00Z", {book: quote, "fanduel": (49.0, -108, -112)},
                    eid="extra")
    events = ([extra, plain] if extra_first else [plain, extra]) + [listing("Georgia", "Georgia Tech",
                                                                            "2026-11-28T20:30:00Z", UGA)]
    text, state, out = capture(tmp_path, monkeypatch, capsys, NOW, events)
    rows = pd.read_csv(tmp_path / "data" / "forward" / "closes.csv")
    assert list(rows.game_id) == [401, 402] and list(rows.line_src) == [book, "draftkings"]     # one row each
    assert list(rows.close_total) == [48.5, 55.5] and list(rows.close_under) == [quote[1], -112]
    assert state == {"captured": ["2026-11-28T20:30Z"], "tries": {"2026-11-28T20:30Z": 1}}   # one call, complete
    name = {"pinnacle": "Pinnacle", "draftkings": "DraftKings"}[book]
    assert (f"kept the one starting 2026-11-28T20:30:00Z, the first listed: the 2 listings equally near the kickoff "
            f"carry the same {name} quote, so they are the same game listed twice") in out


@pytest.mark.parametrize("other", [{"pinnacle": (48.5, -110, -110)}, {"pinnacle": (49.5, -105, -115)}],
                         ids=["prices", "total"])
def test_equally_near_listings_whose_quotes_differ_are_still_a_tie(tmp_path, monkeypatch, capsys, other):
    events = [listing("Alabama", "Auburn", "2026-11-28T20:30:00Z", RIGHT),
              listing("Alabama", "Auburn", "2026-11-28T20:30:00Z", other, eid="relisted"),
              listing("Georgia", "Georgia Tech", "2026-11-28T20:30:00Z", UGA)]
    text, state, out = capture(tmp_path, monkeypatch, capsys, NOW, events)
    assert text.splitlines()[1] == ",401,2026-11-28T20:30:00Z,Alabama,Auburn,,,,"
    assert "2 are equally good and equally near the kickoff, so none is kept and the close is missing" in out
    assert state == {"captured": [], "tries": {"2026-11-28T20:30Z": 1}}


def test_equally_near_listings_priced_at_neither_book_are_still_a_tie(tmp_path, monkeypatch, capsys):
    """Neither carries a rule-book quote, so neither gives a close: the tie stands."""
    events = [listing("Alabama", "Auburn", "2026-11-28T20:30:00Z", FD_ONLY),
              listing("Alabama", "Auburn", "2026-11-28T20:30:00Z", FD_ONLY, eid="relisted"),
              listing("Georgia", "Georgia Tech", "2026-11-28T20:30:00Z", UGA)]
    text, state, out = capture(tmp_path, monkeypatch, capsys, NOW, events)
    assert text.splitlines()[1] == ",401,2026-11-28T20:30:00Z,Alabama,Auburn,,,,"
    assert "2 are equally good and equally near the kickoff" in out


# ------------------------------------------------------------------ a malformed start time costs only its own game
def test_a_listing_with_no_start_time_leaves_only_its_own_game_missing(tmp_path, monkeypatch, capsys):
    events = [listing("Alabama", "Auburn", None, RIGHT, eid="nostart"),
              listing("Georgia", "Georgia Tech", "2026-11-28T20:30:00Z", UGA)]
    text, state, out = capture(tmp_path, monkeypatch, capsys, NOW, events)
    assert text.splitlines()[1:] == [",401,2026-11-28T20:30:00Z,Alabama,Auburn,,,,",
                                     "2026-11-28T20:15:00Z,402,2026-11-28T20:30:00Z,Georgia,Georgia Tech,draftkings,"
                                     "55.5,-112.0,-108.0"]
    assert "401: 1 feed listing of Auburn at Alabama (no start time); none starts within 6 hours" in out
    assert state == {"captured": [], "tries": {"2026-11-28T20:30Z": 1}}       # the run finished and counted its call


def test_start_times_in_two_formats_both_match(tmp_path, monkeypatch, capsys):
    events = [listing("Alabama", "Auburn", "2026-11-28T20:30:00.000Z", RIGHT),
              listing("Georgia", "Georgia Tech", "2026-11-28T20:30:00Z", UGA)]
    text, state, out = capture(tmp_path, monkeypatch, capsys, NOW, events)
    assert scorer_reads(tmp_path) == {401: 48.5, 402: 55.5}
    assert state == {"captured": ["2026-11-28T20:30Z"], "tries": {"2026-11-28T20:30Z": 1}}
    assert "listing" not in out


# ------------------------------------------------------------------ ordinary slots: unchanged, byte for byte
# The expected files are what origin/main's script (commit e83c7f8, before this change) wrote from these same
# made-up responses. Listings of games not due (Michigan, earlier that day) and a feed name no school matches are
# ignored.
HEADER = "capture_utc,game_id,start_utc,home_team,away_team,line_src,close_total,close_under,close_over\n"
ORDINARY = {
    "one slot, two games, other games listed": (
        [(NOW, [listing("Alabama", "Auburn", "2026-11-28T20:30:00Z", RIGHT),
                listing("Georgia", "Georgia Tech", "2026-11-28T20:30:00Z", UGA),
                listing("Michigan", "Ohio State", "2026-11-28T17:00:00Z", WRONG),
                listing("Alabama", "Auburn", "2026-11-28T20:30:00Z", WRONG, home_name="Unknown Team Mascots")])],
        HEADER
        + "2026-11-28T20:15:00Z,401,2026-11-28T20:30:00Z,Alabama,Auburn,pinnacle,48.5,-105,-115\n"
        "2026-11-28T20:15:00Z,402,2026-11-28T20:30:00Z,Georgia,Georgia Tech,draftkings,55.5,-112,-108\n",
        {"captured": ["2026-11-28T20:30Z"], "tries": {"2026-11-28T20:30Z": 1}}),
    "no rule-book price for one game: retried once, then closed": (
        [(NOW, [listing("Alabama", "Auburn", "2026-11-28T20:30:00Z", RIGHT),
                listing("Georgia", "Georgia Tech", "2026-11-28T20:30:00Z", {"fanduel": (55.5, -110, -110)})]),
         ("2026-11-28T20:25:00Z", [listing("Alabama", "Auburn", "2026-11-28T20:31:00Z", RIGHT),
                                   listing("Georgia", "Georgia Tech", "2026-11-28T20:30:00Z",
                                           {"fanduel": (55.0, -110, -110)})]),
         ("2026-11-28T20:27:00Z", [listing("Georgia", "Georgia Tech", "2026-11-28T20:30:00Z", UGA)])],
        HEADER
        + "2026-11-28T20:15:00Z,401,2026-11-28T20:30:00Z,Alabama,Auburn,pinnacle,48.5,-105.0,-115.0\n"
        "2026-11-28T20:15:00Z,402,2026-11-28T20:30:00Z,Georgia,Georgia Tech,,,,\n"
        "2026-11-28T20:25:00Z,401,2026-11-28T20:30:00Z,Alabama,Auburn,pinnacle,48.5,-105.0,-115.0\n"
        "2026-11-28T20:25:00Z,402,2026-11-28T20:30:00Z,Georgia,Georgia Tech,,,,\n"
        ",404,2026-11-28T20:45:00Z,Navy,Army,,,,\n"
        ",404,2026-11-28T20:45:00Z,Navy,Army,,,,\n",
        {"captured": ["2026-11-28T20:30Z", "2026-11-28T20:45Z"],
         "tries": {"2026-11-28T20:30Z": 2, "2026-11-28T20:45Z": 2}}),
    "a game the feed doesn't list": (
        [(NOW, [listing("Alabama", "Auburn", "2026-11-28T20:30:00Z", RIGHT)])],
        HEADER
        + "2026-11-28T20:15:00Z,401,2026-11-28T20:30:00Z,Alabama,Auburn,pinnacle,48.5,-105.0,-115.0\n"
        ",402,2026-11-28T20:30:00Z,Georgia,Georgia Tech,,,,\n",
        {"captured": [], "tries": {"2026-11-28T20:30Z": 1}}),
}


@pytest.mark.parametrize("case", list(ORDINARY))
def test_an_ordinary_slot_writes_exactly_what_it_wrote_before(tmp_path, monkeypatch, capsys, case):
    runs, want_csv, want_state = ORDINARY[case]
    for now, events in runs:
        text, state, out = capture(tmp_path, monkeypatch, capsys, now, events)
        assert "listing" not in out                                             # no duplicate, nothing to report
    assert text == want_csv
    assert state == want_state
