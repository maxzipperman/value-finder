"""Final scores for the realized result at the price taken, from the repo's own processed game tables (in git).

NFL: nfl-weather/data/processed/games.parquet (nflverse): matched on the two teams (config/teams/nfl.csv names
and aliases) and the kickoff date, within a day. CFB: cfb-weather/data/processed/games.parquet (cfbfastR):
matched on the two schools and the kickoff time, within 36 hours. The Odds API names a CFB team "School Mascot";
the school comes from cfbfastR's team_info (school or alternate name plus mascot) when that raw file is on this
machine, else from the longest school name the Odds API name starts with. Home and away are matched as a pair in
either order (neutral sites), and the scores are returned on the Odds API's home and away.

Only seasons 2020-2025 are read. The 2026 seasons are sealed: their scores are never loaded here, whatever the
tables hold: the season filter is applied as the file is read (amendment 1, item 5), and checked again after. An event with no match is kept out of the realized-result columns and counted with its reason.
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


def cfb_names(schools, raw_dir: Path | None = None) -> dict[str, str]:
    """normalized Odds API name -> school, from cfbfastR team_info when the raw files are on this machine."""
    raw_dir = raw_dir or REPO / "cfb-weather/data/raw/cfbfastr"
    out: dict[str, str] = {}
    for f in sorted(raw_dir.glob("team_info_*.parquet")) if raw_dir.exists() else []:
        ti = pd.read_parquet(f)
        for col in ("school", "alt_name1", "alt_name2", "alt_name3"):
            if col not in ti:
                continue
            for a, m, s in zip(ti[col], ti.mascot, ti.school):
                if isinstance(a, str) and a and isinstance(m, str):
                    out.setdefault(norm(f"{a} {m}"), s)
    known = set(schools)
    return {k: v for k, v in out.items() if v in known}


def _school(name: str, lookup: dict[str, str], by_len: list[tuple[str, str]]) -> str | None:
    n = norm(name)
    if n in lookup:
        return lookup[n]
    return next((s for ns, s in by_len if n == ns or n.startswith(ns + " ")), None)


def match(events: pd.DataFrame, nfl: pd.DataFrame | None = None, cfb: pd.DataFrame | None = None,
          cfb_raw: Path | None = None) -> tuple[pd.DataFrame, Counter]:
    """events: sport, event_id, kickoff, home, away (one row per event). Returns sport, event_id, home_score,
    away_score for the events matched to a final score, and the unmatched count by reason."""
    why: Counter = Counter()
    out = []
    ev = events.drop_duplicates(["sport", "event_id"])
    if (ev.sport == NFL).any():
        g = nfl_games() if nfl is None else nfl
        teams = load_teams("nfl")
        code = lambda n: teams.from_name(n) or EXTRA_NFL.get(norm(n))            # noqa: E731
        idx: dict[frozenset, list] = {}
        for r in g.itertuples(index=False):
            idx.setdefault(frozenset((r.home_team, r.away_team)), []).append(r)
        for e in ev[ev.sport == NFL].itertuples(index=False):
            h, a = code(e.home), code(e.away)
            if not h or not a:
                why["nfl_team_name_unknown"] += 1
                continue
            day = e.kickoff.tz_convert("America/New_York").date()
            cands = [r for r in idx.get(frozenset((h, a)), []) if abs((r.day - day).days) <= 1]
            if len(cands) != 1:
                why["nfl_no_game" if not cands else "nfl_ambiguous"] += 1
                continue
            r = cands[0]
            hs, as_ = (r.home_score, r.away_score) if r.home_team == h else (r.away_score, r.home_score)
            out.append((NFL, e.event_id, float(hs), float(as_)))
    if (ev.sport == CFB).any():
        g = cfb_games() if cfb is None else cfb
        schools = sorted(set(g.home_team) | set(g.away_team))
        lookup = cfb_names(schools, cfb_raw)
        by_len = sorted(((norm(s), s) for s in schools), key=lambda x: -len(x[0]))
        idx = {}
        for r in g.itertuples(index=False):
            idx.setdefault(frozenset((r.home_team, r.away_team)), []).append(r)
        for e in ev[ev.sport == CFB].itertuples(index=False):
            h, a = _school(e.home, lookup, by_len), _school(e.away, lookup, by_len)
            if not h or not a or h == a:
                why["cfb_team_name_unknown"] += 1
                continue
            cands = [r for r in idx.get(frozenset((h, a)), []) if abs(r.start_utc - e.kickoff) <= CFB_WINDOW]
            if not cands:
                why["cfb_no_game"] += 1
                continue
            r = min(cands, key=lambda r: abs(r.start_utc - e.kickoff))
            hs, as_ = (r.home_score, r.away_score) if r.home_team == h else (r.away_score, r.home_score)
            out.append((CFB, e.event_id, float(hs), float(as_)))
    return pd.DataFrame(out, columns=["sport", "event_id", "home_score", "away_score"]), why
