"""A synthetic F3 fixture: made-up event-odds answers for a handful of made-up 2025 games, written into a scratch
cache in the Odds API's format, with made-up schedule, roster and player_week tables beside them, so the whole
grader runs end to end with no network and no real data. Nothing here is data: the names are real players' only so
the name matching is exercised on real spellings; every line, price and outcome is invented.

Planted on purpose, at the close (DraftKings is the book: Pinnacle lists 2 of 13 receiving and 1 of 10 rushing
player-games):
  f1 KC-BAL  Kelce 55.5 (under wins), Flowers 60.5 (loses), Andrews 40.0 lands on 40 (push), Rice has no
             player_week row (void); Henry has two lines, 85.5 at even money is the main one (wins); Pacheco has
             49.5 and 50.5 at mirror-image prices (a tie, excluded); Jackson 45.5 at 1/0.6 and 1.25 (power-method
             under probability exactly 0.64, k = 2; wins); controls: Mahomes passing 250.5 (loses), Kelce
             receptions 5.5 (wins); a kicking-market row (not #10's, skipped).
  f2 PHI-DAL "A.J. Brown" (wins), Lamb (loses), "Nobody Known" (no such player: unmatched), Ferguson listed at
             Pinnacle only (no line at the chosen book); Barkley (wins), Hurts with no under price (missing price),
             Javonte Williams with a player_week row and no carry (0 yards: the under wins).
  f3 BUF-MIA nflverse's kickoff is an hour before the schedule's, so before the close: every close line is
             "kickoff moved" (the T-24h lines are not).
  f4 DET-CHI St. Brown (loses), "D.J. Moore" against the roster's "DJ Moore" (wins), "Chris Smith" on both rosters
             (more than one player: unmatched); Gibbs (wins), Swift (loses); "Pointless Guy" quoted with no point
             at any book (not a player-game: no line anywhere; excluded and counted, never dropped).
  f5 GB-MIN  not in the nflverse schedule table (game not matched); its T-24h answer is a cached 404.
  s1 a 2026 game with absurd prices: sealed, never read.
The 12 graded primary lines at the close: 8 under wins against 11 probabilities of 0.5 and one of 0.64, so the
excess under rate is (8 - 5.5 - 0.64) / 12 = 0.155. At T-24h every receiving line is a point lower.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import yaml

from ...cache import Fetched, RawCache
from ...oddsapi import bulk
from . import registration

UTC = timezone.utc
NOW = datetime(2026, 10, 1, tzinfo=UTC)
NFL = "americanfootball_nfl"
US10 = ["pinnacle", "lowvig", "betonlineag", "draftkings", "fanduel", "betmgm", "williamhill_us", "fanatics",
        "betrivers", "espnbet"]
CFG = {
    "books": {"us10": US10},
    "featured": "h2h,spreads,totals",
    "sports": {NFL: {"history_from": "2020-06-06", "sweep_every_days": 2, "windows": [
        {"label": "2025", "from": "2025-09-01", "to": "2026-02-15"},
        {"label": "2026", "from": "2026-09-01", "to": "2027-02-20", "sealed": True}]}},
    "pulls": {"F3": {"kind": "event", "sports": [NFL], "books": "us10", "from": "2023-05-03", "offsets": [24, 0],
                     "markets": "player_pass_yds,player_rush_yds,player_reception_yds,player_receptions,"
                                "player_kicking_points,player_field_goals"}},
}
# id: (kickoff in the saved schedule, home, away, nflverse game id or None, nflverse kickoff ET "YYYY-MM-DD HH:MM")
GAMES = {
    "f1": ("2025-09-07T17:00:00Z", "Kansas City Chiefs", "Baltimore Ravens", "2025_01_BAL_KC", "2025-09-07 13:00"),
    "f2": ("2025-09-07T20:25:00Z", "Philadelphia Eagles", "Dallas Cowboys", "2025_01_DAL_PHI", "2025-09-07 16:25"),
    "f3": ("2025-09-14T17:00:00Z", "Buffalo Bills", "Miami Dolphins", "2025_02_MIA_BUF", "2025-09-14 12:00"),
    "f4": ("2025-09-14T20:25:00Z", "Detroit Lions", "Chicago Bears", "2025_02_CHI_DET", "2025-09-14 16:25"),
    "f5": ("2025-09-21T17:00:00Z", "Green Bay Packers", "Minnesota Vikings", None, None),
    "s1": ("2026-09-13T17:00:00Z", "Kansas City Chiefs", "Buffalo Bills", "2026_01_BUF_KC", "2026-09-13 13:00"),
}
CODES = {"Kansas City Chiefs": "KC", "Baltimore Ravens": "BAL", "Philadelphia Eagles": "PHI", "Dallas Cowboys": "DAL",
         "Buffalo Bills": "BUF", "Miami Dolphins": "MIA", "Detroit Lions": "DET", "Chicago Bears": "CHI",
         "Green Bay Packers": "GB", "Minnesota Vikings": "MIN"}
EVEN = (1.91, 1.91)
REC, RUSH, PASS, RECS = "player_reception_yds", "player_rush_yds", "player_pass_yds", "player_receptions"
# DraftKings at the close: game -> [(market, name as the book spells it, [(point, over, under), ...])];
# an under of None is a missing price
DK = {
    "f1": [(REC, "Travis Kelce", [(55.5, *EVEN)]), (REC, "Zay Flowers", [(60.5, *EVEN)]),
           (REC, "Mark Andrews", [(40.0, *EVEN)]), (REC, "Rashee Rice", [(65.5, *EVEN)]),
           (RUSH, "Derrick Henry", [(85.5, *EVEN), (89.5, 1.70, 2.15)]),
           (RUSH, "Isiah Pacheco", [(49.5, 1.80, 2.02), (50.5, 2.02, 1.80)]),
           (RUSH, "Lamar Jackson", [(45.5, 1 / 0.6, 1.25)]),
           (PASS, "Patrick Mahomes", [(250.5, *EVEN)]), (RECS, "Travis Kelce", [(5.5, *EVEN)])],
    "f2": [(REC, "A.J. Brown", [(70.5, *EVEN)]), (REC, "CeeDee Lamb", [(80.5, *EVEN)]),
           (REC, "Nobody Known", [(30.5, *EVEN)]),
           (RUSH, "Saquon Barkley", [(90.5, *EVEN)]), (RUSH, "Jalen Hurts", [(35.5, 1.91, None)]),
           (RUSH, "Javonte Williams", [(45.5, *EVEN)])],
    "f3": [(RUSH, "James Cook", [(70.5, *EVEN)]), (REC, "Tyreek Hill", [(75.5, *EVEN)])],
    "f4": [(REC, "Amon-Ra St. Brown", [(80.5, *EVEN)]), (REC, "D.J. Moore", [(55.5, *EVEN)]),
           (REC, "Chris Smith", [(20.5, *EVEN)]),
           (RUSH, "Jahmyr Gibbs", [(75.5, *EVEN)]), (RUSH, "D'Andre Swift", [(55.5, *EVEN)]),
           (RUSH, "Pointless Guy", [(None, *EVEN)])],
    "f5": [(REC, "Justin Jefferson", [(85.5, *EVEN)]), (RUSH, "Josh Jacobs", [(70.5, *EVEN)]),
           (PASS, "Jordan Love", [(230.5, *EVEN)])],
    "s1": [(REC, "Travis Kelce", [(5.5, 1.01, 50.0)]), (RUSH, "James Cook", [(5.5, 1.01, 50.0)])],
}
PINNACLE_ONLY = {"f2": [(REC, "Jake Ferguson", [(30.5, *EVEN)])]}
PINNACLE_ALSO = {("f1", "Travis Kelce", REC), ("f1", "Derrick Henry", RUSH)}
# roster rows (season, team, player_id, full_name, first_name, football_name, last_name)
ROSTER = [
    (2025, "KC", "00-K1", "Travis Kelce", "Travis", "Travis", "Kelce"),
    (2025, "KC", "00-K2", "Rashee Rice", "Rashee", "Rashee", "Rice"),
    (2025, "KC", "00-K3", "Isiah Pacheco", "Isiah", "Isiah", "Pacheco"),
    (2025, "KC", "00-K4", "Patrick Mahomes", "Patrick", "Patrick", "Mahomes"),
    (2025, "BAL", "00-B1", "Zay Flowers", "Zay", "Zay", "Flowers"),
    (2025, "BAL", "00-B2", "Mark Andrews", "Mark", "Mark", "Andrews"),
    (2025, "BAL", "00-B3", "Derrick Henry", "Derrick", "Derrick", "Henry"),
    (2025, "BAL", "00-B4", "Lamar Jackson", "Lamar", "Lamar", "Jackson"),
    (2025, "PHI", "00-P1", "A.J. Brown", "Arthur", "A.J.", "Brown"),
    (2025, "PHI", "00-P2", "Saquon Barkley", "Saquon", "Saquon", "Barkley"),
    (2025, "PHI", "00-P3", "Jalen Hurts", "Jalen", "Jalen", "Hurts"),
    (2025, "DAL", "00-D1", "CeeDee Lamb", "CeeDee", "CeeDee", "Lamb"),
    (2025, "DAL", "00-D2", "Javonte Williams", "Javonte", "Javonte", "Williams"),
    (2025, "DAL", "00-D3", "Jake Ferguson", "Jake", "Jake", "Ferguson"),
    (2025, "BUF", "00-U1", "James Cook", "James", "James", "Cook"),
    (2025, "MIA", "00-M1", "Tyreek Hill", "Tyreek", "Tyreek", "Hill"),
    (2025, "DET", "00-T1", "Amon-Ra St. Brown", "Amon-Ra", "Amon-Ra", "St. Brown"),
    (2025, "DET", "00-T2", "Jahmyr Gibbs", "Jahmyr", "Jahmyr", "Gibbs"),
    (2025, "DET", "00-T3", "Chris Smith", "Christopher", "Chris", "Smith"),
    (2025, "CHI", "00-C1", "DJ Moore", "Denniston", "D.J.", "Moore"),
    (2025, "CHI", "00-C2", "D'Andre Swift", "D'Andre", "D'Andre", "Swift"),
    (2025, "CHI", "00-C3", "Chris Smith", "Chris", "Chris", "Smith"),
]
# player_week: player -> (the fixture game's row: game, market stat, value), plus two more 2025 games for the median
STAT = {REC: "receiving_yards", RUSH: "rushing_yards", PASS: "passing_yards", RECS: "receptions"}
OUTCOMES = {   # player_id: {stat: [this game's value, week 3, week 4]}; None = a row with no attempt
    "00-K1": {"receiving_yards": [40, 60, 70], "receptions": [4, 6, 7]},
    "00-K3": {"rushing_yards": [50, 50, 50]},
    "00-K4": {"passing_yards": [270, 240, 260]},
    "00-B1": {"receiving_yards": [72, 50, 55]},
    "00-B2": {"receiving_yards": [40, 30, 20]},
    "00-B3": {"rushing_yards": [70, 100, 90]},
    "00-B4": {"rushing_yards": [30, 50, 40]},
    "00-P1": {"receiving_yards": [50, 60, 80]},
    "00-P2": {"rushing_yards": [60, 80, 85]},
    "00-P3": {"rushing_yards": [20, 30, 40]},
    "00-D1": {"receiving_yards": [95, 70, 75]},
    "00-D2": {"rushing_yards": [None, 40, 30]},
    "00-D3": {"receiving_yards": [25, 30, 35]},
    "00-U1": {"rushing_yards": [65, 70, 80]},
    "00-M1": {"receiving_yards": [90, 60, 70]},
    "00-T1": {"receiving_yards": [100, 70, 72]},
    "00-T2": {"rushing_yards": [74, 70, 60]},
    "00-C1": {"receiving_yards": [30, 50, 45]},
    "00-C2": {"rushing_yards": [80, 50, 40]},
}
GAME_OF = {"K": "f1", "B": "f1", "P": "f2", "D": "f2", "U": "f3", "M": "f3", "T": "f4", "C": "f4"}
EXCESS = (8 - 5.5 - 0.64) / 12          # the hand-computed excess under rate of the 12 graded primary close lines


def t(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


@dataclass
class Fixture:
    cfg: dict
    cache: RawCache
    roster: Path
    games: Path
    player_week: Path
    status: Path
    prereg: Path
    book: str = "draftkings"


def config(tmp: Path) -> dict:
    p = tmp / "odds5m_fixture.yaml"
    p.write_text(yaml.safe_dump(CFG))
    return bulk.load_config(p)


def _outcomes(name: str, quotes: list[tuple]) -> list[dict]:
    out = []
    for point, over, under in quotes:
        out.append({"name": "Over", "description": name, "price": over, "point": point})
        if under is not None:
            out.append({"name": "Under", "description": name, "price": under, "point": point})
    return out


def body(gid: str, at: datetime, role: str) -> dict:
    kick, home, away, *_ = GAMES[gid]
    shift = -1.0 if role == "T-24h" else 0.0                 # every receiving line a point lower at T-24h
    books: dict[str, dict[str, list]] = {}
    for market, name, quotes in DK[gid]:
        q = [(p + shift if market == REC and p is not None else p, o, u) for p, o, u in quotes]
        for b in ("draftkings", "fanduel"):
            books.setdefault(b, {}).setdefault(market, []).extend(_outcomes(name, q))
        if (gid, name, market) in PINNACLE_ALSO:
            books.setdefault("pinnacle", {}).setdefault(market, []).extend(_outcomes(name, q))
    for market, name, quotes in PINNACLE_ONLY.get(gid, []):
        books.setdefault("pinnacle", {}).setdefault(market, []).extend(_outcomes(name, quotes))
    if gid == "f1":                                          # F3's kicking markets are #21's: skipped, counted
        books["draftkings"]["player_field_goals"] = _outcomes("Harrison Butker", [(1.5, *EVEN)])
    upd = bulk.iso(at - timedelta(minutes=1))
    bms = [{"key": b, "last_update": upd, "markets": [{"key": m, "last_update": upd, "outcomes": o}
                                                      for m, o in mk.items()]} for b, mk in books.items()]
    return {"timestamp": bulk.iso(at), "previous_timestamp": None, "next_timestamp": None,
            "data": {"id": gid, "sport_key": NFL, "commence_time": kick, "home_team": home, "away_team": away,
                     "bookmakers": bms}}


def _games_table() -> pd.DataFrame:
    rows = []
    for gid, (_, home, away, game_id, ko) in GAMES.items():
        if game_id:
            day, tm = ko.split()
            rows.append({"game_id": game_id, "season": int(game_id[:4]), "game_type": "REG", "gameday": day,
                         "gametime": tm, "home_team": CODES.get(home, "KC"), "away_team": CODES.get(away, "BUF"),
                         "home_score": 99, "away_score": 99})        # scores present, never read
    return pd.DataFrame(rows)


def _player_week() -> pd.DataFrame:
    rows = []
    for pid, stats in OUTCOMES.items():
        gid = GAMES[GAME_OF[pid[3]]][3]
        for week, game_id in ((int(gid[5:7]), gid), (3, f"2025_03_{pid}"), (4, f"2025_04_{pid}")):
            i = {1: 0, 2: 0, 3: 1, 4: 2}[week]
            row = {"season": 2025, "season_type": "REG", "game_id": game_id, "player_id": pid}
            row.update({c: None for c in STAT.values()})
            row.update({c: v[i] for c, v in stats.items()})
            rows.append(row)
        # the sealed season: a 2026 row with an absurd value, which must never be read
        rows.append({"season": 2026, "season_type": "REG", "game_id": "2026_01_BUF_KC", "player_id": pid,
                     **{c: 999 for c in STAT.values()}})
    w = pd.DataFrame(rows)
    for c in STAT.values():
        w[c] = w[c].astype("Int32")
    return w


def _prereg(tmp: Path, book: str) -> Path:
    """The registration as committed, with a section 8 note naming the fixture's book (only in the scratch copy)."""
    text = registration.PREREG.read_text()
    note = (f"- **2026-10-01 (fixture, not data):** the book is {registration.BOOK_NAMES[book]}, by the rule of "
            "section 2.4 on F3a's coverage at the close.")
    p = tmp / "PREREGISTRATION_PROPS.md"
    p.write_text(text.rstrip("\n") + "\n\n" + note + "\n")
    return p


def build(tmp: Path) -> Fixture:
    tmp = Path(tmp)
    cfg = config(tmp)
    cache = RawCache(tmp / "raw")
    games = [bulk._label(cfg, {"id": gid, "sport": NFL, "commence_time": t(k), "home_team": h, "away_team": a,
                               "first_seen": None}) for gid, (k, h, a, *_) in GAMES.items()]
    bulk.save_schedule(cache.raw_dir, NFL, games)
    calls = bulk.plan_calls(cfg, "F3", bulk.load_schedules(cfg, cache.raw_dir), now=NOW)
    for c in calls:
        kick = t(GAMES[c.event_id][0])
        role = "close" if c.at == bulk.close_time(kick) else "T-24h"
        if c.event_id == "f5" and role == "T-24h":
            fetched = Fetched(404, {}, json.dumps({"message": "no data"}))
        else:
            fetched = Fetched(200, {}, json.dumps(body(c.event_id, c.at, role)))
        cache.get_or_fetch(sport=c.cache_sport, source=c.source, data_date=c.at.date().isoformat(), url=c.url,
                           params=dict(c.params), fetch=lambda f=fetched: f)
    roster = tmp / "roster.csv"
    pd.DataFrame(ROSTER, columns=["season", "team", "player_id", "full_name", "first_name", "football_name",
                                  "last_name"]).to_csv(roster, index=False)
    games_path, pw_path = tmp / "games.parquet", tmp / "player_week.parquet"
    _games_table().to_parquet(games_path, index=False)
    _player_week().to_parquet(pw_path, index=False)
    return Fixture(cfg, cache, roster, games_path, pw_path, registration.STATUS, _prereg(tmp, "draftkings"))
