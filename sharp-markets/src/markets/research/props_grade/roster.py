"""The season roster that matches a prop's player name to an nflverse player_id (PREREGISTRATION_PROPS.md, 2.7).

The registration: the name -> player_id map "is built from a season roster (one row per player per team-season:
name, team, player_id; for example nflverse's season rosters), with no outcome column, and committed before the
first join. A prop row matches when its name maps to exactly one player on either team in its game that season.
A row with no match, or more than one, is unmatched."

The committed file is config/props/nfl_rosters_2023_2025.csv. It is re-created by

    uv run python -m markets.research.props_grade.roster          (from sharp-markets/; GET only, GitHub)

from nflverse's weekly rosters (the `weekly_rosters` release of nflverse/nflverse-data), reduced to one row per
player, team, season and spelling. Only the columns the map needs are read from nflverse's file and kept: season,
team, player_id (nflverse's gsis_id, the id `player_week.parquet` uses) and the names (full_name, first_name,
football_name, last_name). No week, status, position, depth chart or anything else that could say who played.
Rows with no player_id are left out (`reduce`).
nflverse's one-row-per-player season file keeps only each player's last team, so a player traded mid-season would
not match his earlier team's games; the weekly files, reduced, give every team-season he was on.

Only 2023, 2024 and 2025 are fetched. The 2026 season is sealed: it is never fetched, and `load` refuses a file
that holds it.

Names are compared by `key()`: ASCII, lower case, a trailing Jr, Sr, II, III, IV or V dropped, then every character
that isn't a letter or a digit removed ("Amon-Ra St. Brown" -> "amonrastbrown"; "D.J. Moore" and "DJ Moore" agree;
"Kenneth Walker III" and "Kenneth Walker" agree). A roster row answers to three spellings: full_name,
first_name + last_name, and football_name + last_name ("Gabe Davis" and "Gabriel Davis").
"""
from __future__ import annotations

import os
import re
import sys
import unicodedata
from pathlib import Path

import pandas as pd

from ...settings import CONFIG_DIR, RAW_DIR

SEASONS = (2023, 2024, 2025)            # F3's tested sample; 2026 is sealed and never fetched
ROSTER = CONFIG_DIR / "props" / "nfl_rosters_2023_2025.csv"
URL = "https://github.com/nflverse/nflverse-data/releases/download/weekly_rosters/roster_weekly_{season}.parquet"
RAW = RAW_DIR / "nflverse" / "weekly_rosters"
SOURCE_COLUMNS = ["season", "team", "gsis_id", "full_name", "first_name", "football_name", "last_name"]
COLUMNS = ["season", "team", "player_id", "full_name", "first_name", "football_name", "last_name"]
SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "v"}

# why a name did not match (all are the registration's one reason, "unmatched player"; the detail is listed)
NO_PLAYER, SEVERAL, NO_ID = "no player of that name on either team", "more than one player", "player has no player_id"


def key(name) -> str:
    """The form names are compared in: see the module docstring."""
    ascii_ = unicodedata.normalize("NFKD", str(name or "")).encode("ascii", "ignore").decode().lower()
    words = re.sub(r"[^a-z0-9]+", " ", ascii_.replace(".", "").replace("'", "")).split()
    while len(words) > 1 and words[-1] in SUFFIXES:
        words.pop()
    return "".join(words)


# ---------------------------------------------------------------- building the committed file
def _fetch(season: int, raw_dir: Path) -> Path:
    """nflverse's weekly roster for one season, cache first: downloaded once into data/raw (gitignored), then read
    from there. GET only."""
    if season not in SEASONS:
        raise SystemExit(f"refused: season {season}. Only {SEASONS} are fetched; 2026 is sealed.")
    path = raw_dir / f"roster_weekly_{season}.parquet"
    if path.exists():
        return path
    from ...http import RateLimiter, http_get, new_session
    resp = http_get(new_session(), URL.format(season=season), {}, RateLimiter(2.0))
    if resp.status_code != 200:
        raise SystemExit(f"nflverse weekly roster {season}: HTTP {resp.status_code}")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".parquet.tmp")
    tmp.write_bytes(resp.content)
    os.replace(tmp, path)
    return path


def reduce(weekly: pd.DataFrame, season: int) -> pd.DataFrame:
    """One season's weekly roster -> one row per player, team and spelling, the map's columns only. A row with no
    player_id is left out: it can't be part of a name -> player_id map (nflverse has a few; one 2025 row carries
    another player's name and no id, and would otherwise make that player's name ambiguous)."""
    seasons = set(weekly.season.astype(int))
    if seasons != {season}:
        raise SystemExit(f"the {season} roster file holds seasons {sorted(seasons)}")
    r = weekly[SOURCE_COLUMNS].rename(columns={"gsis_id": "player_id"})
    r = r.astype({"season": int}).fillna({c: "" for c in COLUMNS if c != "season"})
    return r[r.player_id.str.strip() != ""][COLUMNS].drop_duplicates()


def build(seasons=SEASONS, raw_dir: Path = RAW, out: Path = ROSTER) -> pd.DataFrame:
    parts = [reduce(pd.read_parquet(_fetch(s, raw_dir), columns=SOURCE_COLUMNS), s) for s in seasons]
    r = pd.concat(parts, ignore_index=True).sort_values(COLUMNS).reset_index(drop=True)
    out.parent.mkdir(parents=True, exist_ok=True)
    r.to_csv(out, index=False)
    return r


# ---------------------------------------------------------------- reading it and matching names
def load(path: Path = ROSTER) -> pd.DataFrame:
    """The committed roster. Refuses a file with any column the map doesn't need (an outcome column could hide
    there) or with any season outside 2023-25."""
    r = pd.read_csv(path, dtype=str, keep_default_na=False)
    if list(r.columns) != COLUMNS:
        raise SystemExit(f"{path}: columns {list(r.columns)}, expected exactly {COLUMNS}")
    r["season"] = r.season.astype(int)
    bad = sorted(set(r.season) - set(SEASONS))
    if bad:
        raise SystemExit(f"{path}: refused, it holds seasons {bad}; only {SEASONS} may be in the roster")
    return r


class NameMap:
    """(season, team) -> name key -> the players on that team-season who answer to it."""

    def __init__(self, roster: pd.DataFrame):
        self.idx: dict[tuple[int, str], dict[str, set[str]]] = {}
        for r in roster.itertuples(index=False):
            who = r.player_id or f"(no player_id) {r.team} {r.full_name}"
            names = self.idx.setdefault((int(r.season), r.team), {})
            spellings = [r.full_name] + [f"{first} {r.last_name}" for first in (r.first_name, r.football_name)
                                         if first and r.last_name]       # never a last name on its own
            for k in {key(s) for s in spellings} - {""}:
                names.setdefault(k, set()).add(who)

    def match(self, season: int, teams, name) -> tuple[str | None, str]:
        """(player_id, "") when `name` maps to exactly one player on either team that season, else (None, why)."""
        k = key(name)
        found = set().union(*(self.idx.get((int(season), t), {}).get(k, set()) for t in teams)) if k else set()
        if not found:
            return None, NO_PLAYER
        if len(found) > 1:
            return None, SEVERAL
        (who,) = found
        return (None, NO_ID) if who.startswith("(no player_id)") else (who, "")


def main(argv: list[str] | None = None) -> int:
    r = build()
    print(f"wrote {ROSTER}: {len(r):,} rows, {r.player_id.nunique():,} players, seasons "
          + ", ".join(f"{s} ({n:,})" for s, n in r.season.value_counts().sort_index().items()))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
