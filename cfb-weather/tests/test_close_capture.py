"""Close capture (scripts/capture_close.py, amendment 2) writes one closing row per game. A game is matched to the
feed on its two teams AND its kickoff: the listing of those teams that starts nearest the scheduled kickoff,
within 6 hours. Before Sep 29, 2026 it matched on the teams alone, so a feed that listed the same two teams
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
    assert "kept the one starting 2026-11-28T20:30:00Z, nearest the kickoff" in out


def test_two_listings_equally_near_kickoff_are_left_unmatched_and_reported(tmp_path, monkeypatch, capsys):
    events = [listing("Alabama", "Auburn", "2026-11-28T20:30:00Z", RIGHT),
              listing("Alabama", "Auburn", "2026-11-28T20:30:00Z", WRONG, eid="relisted"),
              listing("Georgia", "Georgia Tech", "2026-11-28T20:30:00Z", UGA)]
    text, state, out = capture(tmp_path, monkeypatch, capsys, NOW, events)
    assert text.splitlines()[1] == ",401,2026-11-28T20:30:00Z,Alabama,Auburn,,,,"         # recorded as missing
    assert scorer_reads(tmp_path) == {402: 55.5}
    assert "2 are equally near the kickoff, so none is kept and the close is missing" in out
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
