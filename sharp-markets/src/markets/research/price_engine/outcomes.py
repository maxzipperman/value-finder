"""Final scores for the realized result at the price taken, from the repo's own processed game tables (in git).

NFL: nfl-weather/data/processed/games.parquet (nflverse): matched on the two teams (config/teams/nfl.csv names
and aliases) and the kickoff date, within a day. CFB: cfb-weather/data/processed/games.parquet (cfbfastR):
matched on the two schools and the kickoff time, within 36 hours. The Odds API names a CFB team "School Mascot";
the school comes from the alias table below (amendment 1, item 8), else from cfbfastR's team_info (school or
alternate name plus mascot) when that raw file is on this machine, else from the longest school name the Odds API
name starts with (the prefix rule, logged as such). Home and away are matched as a pair in
either order (neutral sites), and the scores are returned on the Odds API's home and away.

Only seasons 2020-2025 are read. The 2026 seasons are sealed: their scores are never loaded here, whatever the
tables hold: the season filter is applied as the file is read (amendment 1, item 5), and checked again after. An
event with no match is kept out of the realized-result columns and counted with its reason.
"""
from __future__ import annotations

import re
import unicodedata
from collections import Counter
from pathlib import Path

import pandas as pd

from ...sport import load_teams
from .model import CFB, NFL, REPO

SEASONS = range(2020, 2026)       # 2026 is the sealed holdout
SEASON_FILTER = [("season", "in", list(SEASONS))]      # applied while the parquet file is read
EXTRA_NFL = {"washington football team": "WAS", "washington redskins": "WAS", "oakland raiders": "LV"}
CFB_WINDOW = pd.Timedelta(hours=36)


def norm(name) -> str:
    """Lower-case ASCII words: "San José State" == "San Jose State", "Hawai'i" == "Hawaii"."""
    ascii_ = unicodedata.normalize("NFKD", str(name or "")).encode("ascii", "ignore").decode()
    return " ".join(re.sub(r"[^a-z0-9 ]", "", ascii_.lower()).split())


def nfl_games(path: Path | None = None) -> pd.DataFrame:
    # the filter is applied as the file is read, so no 2026 row is ever loaded (amendment 1, item 5); the check
    # after the read stays as a second layer
    g = pd.read_parquet(path or REPO / "nfl-weather/data/processed/games.parquet",
                        columns=["season", "gameday", "home_team", "away_team", "home_score", "away_score"],
                        filters=SEASON_FILTER)
    g = g[g.season.isin(SEASONS) & g.home_score.notna() & g.away_score.notna()].copy()
    g["day"] = pd.to_datetime(g.gameday).dt.date
    return g


def cfb_games(path: Path | None = None) -> pd.DataFrame:
    g = pd.read_parquet(path or REPO / "cfb-weather/data/processed/games.parquet",
                        columns=["season", "start_utc", "home_team", "away_team", "home_points", "away_points"],
                        filters=SEASON_FILTER)                          # read-time filter: see nfl_games
    g = g[g.season.isin(SEASONS) & g.home_points.notna() & g.away_points.notna()].copy()
    return g.rename(columns={"home_points": "home_score", "away_points": "away_score"})


def team_files(raw_dir: Path | None = None) -> list[Path]:
    """cfbfastR's team_info files, when the raw files are on this machine (the Mac's live checkout; not the cloud)."""
    raw_dir = raw_dir or REPO / "cfb-weather/data/raw/cfbfastr"
    return sorted(raw_dir.glob("team_info_*.parquet")) if raw_dir.exists() else []


def cfb_names(schools, raw_dir: Path | None = None) -> dict[str, str]:
    """normalized Odds API name -> school, from cfbfastR team_info when the raw files are on this machine."""
    out: dict[str, str] = {}
    for f in team_files(raw_dir):
        ti = pd.read_parquet(f)
        for col in ("school", "alt_name1", "alt_name2", "alt_name3"):
            if col not in ti:
                continue
            for a, m, s in zip(ti[col], ti.mascot, ti.school):
                if isinstance(a, str) and a and isinstance(m, str):
                    out.setdefault(norm(f"{a} {m}"), s)
    known = set(schools)
    return {k: v for k, v in out.items() if v in known}


# Amendment 1, item 8: Odds API spellings of college teams that the prefix rule sends to the wrong school or can't
# resolve (the names checker's alias_proposal.csv of September 29, 2026). Every row was checked by eye against the
# score table's spelling of the school (cfb-weather/data/processed/games.parquet, seasons 2020-25) before any F1
# price exists. Keys are normalized names (norm()). Consulted before the team files and the prefix rule. Adding a
# row is a dated amendment, made from the names-only preflight (names_preflight.py) before any F1 price is opened.
CFB_ALIASES = {
    "umass minutemen": "Massachusetts",
    "miami redhawks": "Miami (OH)",
    "miami ohio redhawks": "Miami (OH)",
    "miamiohio redhawks": "Miami (OH)",
    "louisiana monroe warhawks": "UL Monroe",
    "louisianamonroe warhawks": "UL Monroe",
    "ulmonroe warhawks": "UL Monroe",
    "louisianalafayette ragin cajuns": "Louisiana",
    "north carolina state wolfpack": "NC State",
    "southern california trojans": "USC",
    "mississippi rebels": "Ole Miss",
    "texas el paso miners": "UTEP",
    "ut san antonio roadrunners": "UTSA",
    "nevada las vegas rebels": "UNLV",
    "alabama birmingham blazers": "UAB",
    "southeastern louisiana lions": "SE Louisiana",
    "tennesseemartin skyhawks": "UT Martin",
    "albany great danes": "UAlbany",
    "citadel bulldogs": "The Citadel",
    "saint francis pa red flash": "St. Francis (PA)",
    "saint francis red flash": "St. Francis (PA)",
    "tarleton texans": "Tarleton State",
    "se missouri state redhawks": "Southeast Missouri State",
    "appalachian state mountaineers": "App State",
    "southern mississippi golden eagles": "Southern Miss",
    "connecticut huskies": "UConn",
    "houston baptist huskies": "Houston Christian",
    "texas amcommerce lions": "East Texas A&M",
    "dixie state trailblazers": "Utah Tech",
    "central florida knights": "UCF",
    "southern methodist mustangs": "SMU",
    "texas christian horned frogs": "TCU",
    "louisiana state tigers": "LSU",
    "brigham young cougars": "BYU",
    "tennessee martin skyhawks": "UT Martin",
    "arkansas pine bluff golden lions": "Arkansas-Pine Bluff",
    "san diego st aztecs": "San Diego State",
    "ohio st buckeyes": "Ohio State",
    "iowa st cyclones": "Iowa State",
    "utah st aggies": "Utah State",
}
# how a name was resolved; the prefix rule and "unresolved" are the name problems the report lists
ALIAS, TEAM_FILES, SCHOOL_NAME, PREFIX, UNRESOLVED = ("alias table", "team files", "school name", "prefix rule",
                                                      "unresolved")


def resolve_cfb(name: str, lookup: dict[str, str], by_len: list[tuple[str, str]]) -> tuple[str | None, str]:
    """(school, how) for an Odds API college name: the alias table first, then cfbfastR's team files (`lookup`),
    then a name that is exactly a school's, then the longest school name the name starts with (the prefix rule)."""
    n = norm(name)
    if n in CFB_ALIASES:
        return CFB_ALIASES[n], ALIAS
    if n in lookup:
        return lookup[n], TEAM_FILES
    for ns, s in by_len:
        if n == ns:
            return s, SCHOOL_NAME
        if n.startswith(ns + " "):
            return s, PREFIX
    return None, UNRESOLVED


def _school(name: str, lookup: dict[str, str], by_len: list[tuple[str, str]]) -> str | None:
    return resolve_cfb(name, lookup, by_len)[0]


def match(events: pd.DataFrame, nfl: pd.DataFrame | None = None, cfb: pd.DataFrame | None = None,
          cfb_raw: Path | None = None, detail: dict | None = None) -> tuple[pd.DataFrame, Counter]:
    """events: sport, event_id, kickoff, home, away (one row per event). Returns sport, event_id, home_score,
    away_score for the events matched to a final score, and the unmatched count by reason.

    A college game with a name resolved only by the prefix rule that finds no game is counted as
    cfb_prefix_name_no_game, not cfb_no_game (amendment 1, item 8); a name that doesn't resolve is
    cfb_team_name_unknown. `detail`, if given, is filled with: names (sport, name, resolves_to, how, games),
    unmatched (sport, event_id, reason) and cfb_team_files (how many team_info files were found)."""
    why: Counter = Counter()
    out, names, missed = [], {}, []

    def miss(sport, eid, reason):
        why[reason] += 1
        missed.append((sport, eid, reason))

    def seen(sport, name, school, how):
        names[(sport, name)] = [school, how, names.get((sport, name), [None, None, 0])[2] + 1]

    ev = events.drop_duplicates(["sport", "event_id"])
    if (ev.sport == NFL).any():
        g = nfl_games() if nfl is None else nfl
        teams = load_teams("nfl")

        def code(n):
            c = teams.from_name(n)
            if c:
                return c, "team table"
            c = EXTRA_NFL.get(norm(n))
            return (c, "EXTRA_NFL") if c else (None, UNRESOLVED)
        idx: dict[frozenset, list] = {}
        for r in g.itertuples(index=False):
            idx.setdefault(frozenset((r.home_team, r.away_team)), []).append(r)
        for e in ev[ev.sport == NFL].itertuples(index=False):
            (h, hh), (a, ah) = code(e.home), code(e.away)
            seen(NFL, e.home, h, hh)
            seen(NFL, e.away, a, ah)
            if not h or not a:
                miss(NFL, e.event_id, "nfl_team_name_unknown")
                continue
            day = e.kickoff.tz_convert("America/New_York").date()
            cands = [r for r in idx.get(frozenset((h, a)), []) if abs((r.day - day).days) <= 1]
            if len(cands) != 1:
                miss(NFL, e.event_id, "nfl_no_game" if not cands else "nfl_ambiguous")
                continue
            r = cands[0]
            hs, as_ = (r.home_score, r.away_score) if r.home_team == h else (r.away_score, r.home_score)
            out.append((NFL, e.event_id, float(hs), float(as_)))
    if (ev.sport == CFB).any():
        g = cfb_games() if cfb is None else cfb
        schools = sorted(set(g.home_team) | set(g.away_team))
        lookup = cfb_names(schools, cfb_raw)
        if detail is not None:
            detail["cfb_team_files"] = len(team_files(cfb_raw))
        by_len = sorted(((norm(s), s) for s in schools), key=lambda x: -len(x[0]))
        idx = {}
        for r in g.itertuples(index=False):
            idx.setdefault(frozenset((r.home_team, r.away_team)), []).append(r)
        for e in ev[ev.sport == CFB].itertuples(index=False):
            (h, hh), (a, ah) = resolve_cfb(e.home, lookup, by_len), resolve_cfb(e.away, lookup, by_len)
            seen(CFB, e.home, h, hh)
            seen(CFB, e.away, a, ah)
            if not h or not a or h == a:
                miss(CFB, e.event_id, "cfb_team_name_unknown")
                continue
            cands = [r for r in idx.get(frozenset((h, a)), []) if abs(r.start_utc - e.kickoff) <= CFB_WINDOW]
            if not cands:
                miss(CFB, e.event_id, "cfb_prefix_name_no_game" if PREFIX in (hh, ah) else "cfb_no_game")
                continue
            r = min(cands, key=lambda r: abs(r.start_utc - e.kickoff))
            hs, as_ = (r.home_score, r.away_score) if r.home_team == h else (r.away_score, r.home_score)
            out.append((CFB, e.event_id, float(hs), float(as_)))
    if detail is not None:
        detail["names"] = pd.DataFrame([(sp, n, s, how, k) for (sp, n), (s, how, k) in sorted(names.items())],
                                       columns=["sport", "name", "resolves_to", "how", "games"])
        detail["unmatched"] = pd.DataFrame(missed, columns=["sport", "event_id", "reason"])
    return pd.DataFrame(out, columns=["sport", "event_id", "home_score", "away_score"]), why
