"""Close capture (scripts/capture_close.py, amendment 3) writes one closing listing per game. A game is matched
to the feed on its two teams AND its kickoff: the listing of those teams that starts nearest the scheduled
kickoff, within 6 hours. Before Sep 29, 2026 it matched on the teams alone, so a feed that listed the same two
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
    assert "2026_05_PHI_CHI: 2 feed listings of PHI at CHI" in out and "kept e1, the one nearest the kickoff" in out


def test_two_listings_equally_near_kickoff_are_left_unmatched_and_reported(tmp_path, monkeypatch, capsys):
    events = [listing("e1", "CHI", "PHI", "2026-10-11T17:00:00Z", RIGHT),
              listing("e2", "CHI", "PHI", "2026-10-11T17:00:00Z", WRONG),
              listing("e3", "GB", "DET", "2026-10-11T17:00:00Z", GB)]
    text, state, out = capture(tmp_path, monkeypatch, capsys, NOW, events)
    assert text.splitlines()[1] == "2026_05_PHI_CHI,2026-10-11T17:00:00Z,CHI,PHI,,,,,,"     # recorded as missing
    assert scorer_reads(tmp_path) == {"2026_05_DET_GB": 39.5}
    assert "2 are equally near the kickoff, so none is kept and the close is missing" in out
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
    assert "listing" not in out                                                 # nothing to report


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
        assert "listing" not in out                                             # no duplicate, nothing to report
    assert text == want_csv
    assert state == want_state
