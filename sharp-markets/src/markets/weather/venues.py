"""Venue tables (config/venues/) and venue resolution. See config/venues/README.md for sources.

Resolution order for a game (join.py):
  1. a game-level venue from the MLB Stats API or ESPN, when cached (gamevenues.py, Mac);
  2. tournaments: the fixture table (openfootball, CC0) by date and teams;
  3. leagues: a league-wide window (team "*", e.g. the MLS is Back bubble), then the home team's
     venue on that date (relocations are dated rows).
Anything unresolved is reported, never guessed.
"""
from __future__ import annotations

import csv
import re
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from functools import lru_cache
from pathlib import Path

from ..settings import CONFIG_DIR

VENUES_DIR = CONFIG_DIR / "venues"
MLB = "baseball_mlb"
STOP = {"fc", "cf", "sc", "club", "de", "ec", "ac", "cd", "the", "afc"}   # not state codes: Atletico-MG vs -GO


def norm(name: str | None) -> str:
    """Accent-, case- and punctuation-free name without club-type words ("FC", "SC", "Club"...)."""
    if not name:
        return ""
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower().replace("&", " and ")
    return " ".join(w for w in re.sub(r"[^a-z0-9]+", " ", s).split() if w not in STOP)


@dataclass(frozen=True)
class Venue:
    venue_id: str
    name: str
    city: str
    country: str
    lat: float
    lon: float
    roof: str                 # open | retractable | dome | covered | cooled


def _rows(name: str) -> list[dict]:
    with (VENUES_DIR / name).open(newline="") as f:
        return list(csv.DictReader(f))


@lru_cache(maxsize=None)
def venues() -> dict[str, Venue]:
    out = {}
    for file in ("mlb_parks.csv", "soccer_venues.csv"):
        for r in _rows(file):
            out[r["venue_id"]] = Venue(r["venue_id"], r["name"], r["city"], r["country"], float(r["lat"]),
                                       float(r["lon"]), r["roof"])
    return out


@lru_cache(maxsize=None)
def venue_names() -> dict[str, str]:
    """Normalized venue name or alias -> venue_id (for names from the MLB Stats API or ESPN)."""
    out = {}
    for file in ("mlb_parks.csv", "soccer_venues.csv"):
        for r in _rows(file):
            for n in [r["name"], *[a for a in r["aliases"].split(";") if a]]:
                out.setdefault(norm(n), r["venue_id"])
    return out


def venue_by_name(name: str | None) -> str | None:
    return venue_names().get(norm(name))


def _d(v: str) -> date | None:
    return date.fromisoformat(v) if v else None


@lru_cache(maxsize=None)
def homes() -> list[dict]:
    out = []
    for r in _rows("mlb_homes.csv"):
        out.append({**r, "sport_key": MLB})
    out += _rows("soccer_homes.csv")
    for r in out:
        r["names"] = {norm(r["team"]), *(norm(a) for a in r["aliases"].split(";") if a)} - {""}
        r["from_d"], r["to_d"] = _d(r["from"]), _d(r["to"])
    return out


def canonical(sport_key: str, name: str | None) -> str:
    """One key per team across sources ("Athletics" and "Oakland Athletics" are the same club)."""
    n = norm(name)
    for r in homes():
        if r["sport_key"] == sport_key and n in r["names"]:
            return norm(r["team"])
    return n


def _covers(r: dict, day: date) -> bool:
    return (r["from_d"] is None or r["from_d"] <= day) and (r["to_d"] is None or day <= r["to_d"])


def home_venue(sport_key: str, home_team: str, day: date, away_team: str | None = None) -> tuple[str | None, str]:
    """(venue_id, how) for a league game: a league-wide window first, then the home team's dated venue.
    Leagues Cup 2025 was hosted entirely at MLS grounds, so its games take the MLS side's home venue,
    whichever team the odds list as home."""
    if sport_key == "soccer_concacaf_leagues_cup":
        for team in (home_team, away_team):
            vid, how = home_venue("soccer_usa_mls", team or "", day)
            if vid:
                return vid, "MLS host"
        return None, "no MLS side"
    rows = [r for r in homes() if r["sport_key"] == sport_key]
    for r in rows:
        if r["team"] == "*" and _covers(r, day):
            return r["venue_id"], "league window"
    n = norm(home_team)
    for r in rows:
        if n in r["names"] and _covers(r, day):
            return r["venue_id"], "home team"
    return None, "unknown home team" if not any(n in r["names"] for r in rows) else "no venue on that date"


@lru_cache(maxsize=None)
def fixtures() -> list[dict]:
    rows = _rows("tournament_fixtures.csv")
    for r in rows:
        r["teams"] = frozenset((norm(r["team1"]), norm(r["team2"])))
        r["kick"] = datetime.fromisoformat(r["kickoff_utc"].replace("Z", "+00:00"))
    return rows


def fixture_venue(sport_key: str, home: str, away: str, kickoff: datetime) -> str | None:
    """Tournament venue from the fixture table: same teams, kickoff within 6 hours."""
    teams = frozenset((norm(home), norm(away)))
    for r in fixtures():
        if r["sport_key"] == sport_key and r["teams"] == teams and abs(r["kick"] - kickoff) <= timedelta(hours=6):
            return r["venue_id"]
    return None


def check_tables() -> list[str]:
    """Problems in the venue tables (tests and `markets weather check`)."""
    v = venues()
    bad = [f"{r['sport_key']} {r['team']}: unknown venue {r['venue_id']}" for r in homes() if r["venue_id"] not in v]
    bad += [f"fixture {r['kickoff_utc']} {r['team1']}-{r['team2']}: unknown venue {r['venue_id']}"
            for r in fixtures() if r["venue_id"] not in v]
    bad += [f"{x.venue_id}: bad coordinates" for x in v.values() if not (-90 <= x.lat <= 90 and -180 <= x.lon <= 180)]
    bad += [f"{x.venue_id}: unknown roof {x.roof}" for x in v.values()
            if x.roof not in ("open", "retractable", "dome", "covered", "cooled")]
    return bad


def distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance (haversine, mean Earth radius)."""
    import math
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = (math.sin((p2 - p1) / 2) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2)
    return 2 * 6371.0 * math.asin(math.sqrt(a))


def csv_path(name: str) -> Path:
    return VENUES_DIR / name
