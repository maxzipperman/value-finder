"""The repo's committed nflverse tables, for the join (PREREGISTRATION_PROPS.md, 2.4 and 2.7). Read only after the
book note of section 8 is recorded.

  games.parquet        nfl-weather/data/processed/games.parquet: the game id, season and teams for each Odds API
                       event, and the kickoff for the "kickoff moved" check (2.4). The registration names nflverse's
                       games.csv `gameday` and `gametime` (US Eastern); this committed table is built from that file
                       and carries the same two columns, so it is the source here. No score column is ever read.
  player_week.parquet  nfl-weather/data/processed/player_week.parquet (nflverse weekly stats): the outcomes (2.7) and
                       the same-season medians (2.8).

Both hold rows for the sealed 2026 season. Every read here passes a season filter to the parquet reader, so what it
hands over holds only 2023-25 (the registration's header: "every reader of it for this test filters on season 2025
or earlier as it reads, before anything is counted"); the check after the read is a second layer.
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path

import pandas as pd

from ...sport import load_teams
from ..price_engine.outcomes import EXTRA_NFL, norm

REPO = Path(__file__).resolve().parents[5]       # .../value-finder (this file is sharp-markets/src/markets/research/...)
GAMES = REPO / "nfl-weather" / "data" / "processed" / "games.parquet"
PLAYER_WEEK = REPO / "nfl-weather" / "data" / "processed" / "player_week.parquet"
SEASONS = (2023, 2024, 2025)                     # F3's tested sample; 2026 is sealed
SEASON_FILTER = [("season", "in", list(SEASONS))]       # applied while the parquet file is read
GAME_COLS = ["game_id", "season", "game_type", "gameday", "gametime", "home_team", "away_team"]   # no score
STAT = {"player_reception_yds": "receiving_yards", "player_rush_yds": "rushing_yards",
        "player_pass_yds": "passing_yards", "player_receptions": "receptions"}
PW_COLS = ["season", "season_type", "game_id", "player_id", *STAT.values()]


def nfl_schedule(path: Path = GAMES) -> pd.DataFrame:
    """2023-25 games: id, season, teams, and nflverse's kickoff in UTC (`kick_nflverse`, NaT when unreadable)."""
    g = pd.read_parquet(path, columns=GAME_COLS, filters=SEASON_FILTER)
    g = g[g.season.isin(SEASONS)].copy()
    local = pd.to_datetime(g.gameday.astype(str) + " " + g.gametime.astype(str), errors="coerce",
                           format="%Y-%m-%d %H:%M")
    g["kick_nflverse"] = local.dt.tz_localize("America/New_York", ambiguous="NaT", nonexistent="NaT").dt.tz_convert(
        "UTC")
    g["day"] = pd.to_datetime(g.gameday, errors="coerce").dt.date
    return g.reset_index(drop=True)


def player_week(path: Path = PLAYER_WEEK) -> pd.DataFrame:
    """2023-25 weekly stats: season, season_type, game_id, player_id and the four markets' stat columns."""
    w = pd.read_parquet(path, columns=PW_COLS, filters=SEASON_FILTER)
    return w[w.season.isin(SEASONS)].reset_index(drop=True)


def match_events(events: pd.DataFrame, games: pd.DataFrame) -> tuple[pd.DataFrame, Counter, dict]:
    """events: event_id, kick (the schedule's), home_team, away_team (Odds API names). Each is matched to the one
    nflverse game with the same two teams whose Eastern date is within a day of the kickoff (as the price engine
    matches NFL games). Returns event_id, game_id, season, home, away, kick_nflverse for the matched events, the
    unmatched count by reason, and event_id -> reason for the unmatched ones."""
    teams = load_teams("nfl")

    def code(name):
        return teams.from_name(name) or EXTRA_NFL.get(norm(name))

    idx: dict[frozenset, list] = {}
    for r in games.itertuples(index=False):
        idx.setdefault(frozenset((r.home_team, r.away_team)), []).append(r)
    out, why, missed = [], Counter(), {}
    for e in events.drop_duplicates("event_id").itertuples(index=False):
        h, a = code(e.home_team), code(e.away_team)
        if not h or not a:
            reason = "team name unknown"
        else:
            day = pd.Timestamp(e.kick).tz_convert("America/New_York").date()
            cands = [r for r in idx.get(frozenset((h, a)), []) if pd.notna(r.day) and abs((r.day - day).days) <= 1]
            if len(cands) == 1 and pd.notna(cands[0].kick_nflverse):
                r = cands[0]
                out.append((e.event_id, r.game_id, int(r.season), r.home_team, r.away_team, r.kick_nflverse))
                continue
            reason = ("no nflverse game" if not cands else "more than one nflverse game" if len(cands) > 1
                      else "no nflverse kickoff time")
        why[reason] += 1
        missed[e.event_id] = reason
    cols = ["event_id", "game_id", "season", "home", "away", "kick_nflverse"]
    return pd.DataFrame(out, columns=cols), why, missed
