"""H3 for the NFL: closing betting splits at one retail book (BetMGM), 2021-25. The registered test (issue #75).

Data: Kaggle caseydurfee/mgm-grand-nfl-betting-data (CC BY-SA 4.0), one file, all_odds.csv, read on the layout of the
same author's NBA file. Registration: docs/H3_KAGGLE_NFL_PREREGISTRATION.md, pushed before the file is downloaded.
6 variants on spreads and totals: family A (money share minus ticket share >= 10 points), family B (the regression per
10 points of divergence) and family C (the side with 30% of the tickets or fewer).

What differs from the NBA test (kaggle_h3.py, whose download, credential and statistics this module uses unchanged):
- a game's result comes from the repo's own scores (nfl-weather/data/processed/games.parquet, seasons 2021-25 only);
  the file's won flags are only a cross-check, and disagreements are counted;
- exact duplicate rows are dropped to one; a bet that lands exactly on its line is a push and is left out;
- no game of the 2026 season or later is read: such rows are counted and nothing else;
- team names are read through an explicit mapping (TEAM_NAMES); a name it lacks is counted and never guessed, except
  "New York" and "Los Angeles" (CITY_NAMES), resolved from the schedule alone by the registered rule or left out;
- shares are rounded to 9 decimals wherever they meet a threshold (round(div, 9) >= 10, round(tickets, 9) <= 30);
- an unnamed row-index column ("" or "Unnamed: 0") is ignored by the exact-duplicate check.

`markets h3-kaggle --sport nfl --check-only` checks the layout, the team names, the join to the repo's schedule and the
format of the lines, shares and prices (counts only), and computes no result. It reads no score and no won flag: the
exact-duplicate check compares every column of a row as text, so the won flags are touched only for that equality check,
and no flag's value is read. Prices, shares and lines are read only to count their format (the share scale and sums,
American or decimal prices, margins, missing, unreadable, whole-number and unmirrored lines) and to check the sign and
mapping of the lines against nflverse's closing spread_line and total_line in games.parquet and, when the file has them,
the moneyline favourite (line_checks). The full report shows the same counts from the same code.
"""
from __future__ import annotations

import csv
import hashlib
import io
import math
import re
import subprocess
import zipfile
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
from scipy import stats as sps

from . import kaggle_h3 as k
from ..settings import REPORTS_DIR, ROOT

# ---- the registration (docs/H3_KAGGLE_NFL_PREREGISTRATION.md); changing any of these is a dated amendment ----
SPORT = "nfl"
DATASET = k.DATASETS[SPORT]
FIRST_SEASON, LAST_SEASON = 2021, 2025               # a later season (2026 on) is counted and nothing else
# The cut: a game dated August 1, 2026 or later is in the 2026 season, which is a sealed holdout in the project's Odds API
# plan (config/odds5m.yaml, americanfootball_nfl window "2026", sealed: true: never analysed until a hypothesis about it
# is pre-registered). Nothing of it is read here.
SEALED_FROM = date(LAST_SEASON + 1, 8, 1)
SEASONS = tuple(str(y) for y in range(FIRST_SEASON, LAST_SEASON + 1))
MARKETS = ("spread", "total")                        # no moneylines
MARKET_LABEL = {"spread": "spread", "total": "total"}
SIDES = {m: k.SIDES[m] for m in MARKETS}             # spread: home, away; total: over, under
THRESHOLD = 10                                       # family A: round(money share - ticket share, 9) >= 10 points
FADE_MAX_TICKETS = 30                                # family C: round(ticket share, 9) <= 30
SHARE_DIGITS = 9                                     # every share compared with a threshold is rounded to 9 decimals
MAX_MARGIN = k.MAX_MARGIN                            # a margin below 0 or above 20% is a missing figure
N_VARIANTS = 3 * len(MARKETS)                        # A, B and C on spreads and totals: 6
PRIOR_COUNT = 288                                    # the brief said 287; the academy check (#54) made it 288
RUNNING_COUNT = PRIOR_COUNT + N_VARIANTS             # 294
BAR = 0.05 / RUNNING_COUNT                           # 0.000170
SEASONS_NEEDED = k.SEASONS_NEEDED                    # the same sign in at least 4 of the 5 seasons
Z_BAR = float(sps.norm.isf(BAR / 2))                 # about 3.76
DATE_SLACK_DAYS = 1                                  # the file's date may be the Eastern date or one day either side
TICKET_BINS = tuple(range(0, 100, 10))               # the Rule B description: 0-10, 10-20, ... 90-100 (upper bin shut)
REPORT_NAME = "h3_kaggle_nfl.md"
REGISTRATION_DOC = "docs/H3_KAGGLE_NFL_PREREGISTRATION.md"
CSV_NAME = "all_odds.csv"
HAND_SECTION = "## Notes written by hand"            # kept when the run rewrites the report
MIRROR = "lines that don't mirror"                   # spread: home line + away line != 0; total: over != under
MARGIN = "margin below 0% or above 20%"
# The check of the file's lines against nflverse's closing lines in games.parquet (prices, not results). nflverse's
# spread_line is the home side's expected margin (positive: the home side is favoured), so the file's home spread line
# should be about -spread_line (+spread_line when the join swapped home and away); its total line about total_line.
SCHEDULE_LINES = ("spread_line", "total_line")
LINE_TOLERANCE = 3.0                                 # points: "within 3 points" of nflverse's closing line
BLANK_FLAG = "file's flag blank or unreadable"

# Kaggle column names, the NBA file's layout (kaggle_h3.FIELD): {market}_{side}_{decimal_odds | stake_percentage (money)
# | wager_percentage (tickets) | points (the line) | won}.
FIGURES = ("dec", "stake", "wager", "line", "won")
REQUIRED = (k.COL_DATE, k.COL_HOME, k.COL_AWAY) + tuple(k._col(m, s, w) for m in MARKETS for s in SIDES[m]
                                                         for w in FIGURES)


def is_row_index(column: str) -> bool:
    """An unnamed row-index column (a running row number written by the tool that saved the file): a column named ""
    or "Unnamed: 0" (pandas's name for it). The exact-duplicate check ignores it; nothing else reads it."""
    c = str(column).strip()
    return c == "" or re.fullmatch(r"Unnamed: \d+", c) is not None


def _share(x: float) -> float:
    """A share as compared with a threshold: rounded to 9 decimals, so 16.4 - 6.4 (9.999999999999998 in a computer's
    arithmetic) is 10, and 0.57 and 0.47 given as fractions are 57 and 47 points apart."""
    return round(x, SHARE_DIGITS)


def money_ahead(o: dict) -> bool:
    """Family A: the side's share of money beats its share of tickets by at least THRESHOLD points."""
    return _share(o["div"]) >= THRESHOLD


def few_tickets(o: dict) -> bool:
    """Family C: the side has FADE_MAX_TICKETS% of the tickets or fewer."""
    return _share(o["wager"]) <= FADE_MAX_TICKETS

# ---- team names: an explicit mapping to nflverse codes (games.parquet), 2021-25 ----
# Full names, city names and nicknames, and the short forms Yahoo uses. Washington played as the Washington Football
# Team in 2021 and as the Commanders from 2022; both map to WAS. The Raiders (LV) and the Rams and Chargers (LA, LAC)
# had already moved before 2021. "New York" and "Los Angeles" alone name two teams each and are not in TEAM_NAMES:
# CITY_NAMES resolves them from the schedule alone (see resolve_city), or the game is counted and left out.
_TEAMS = {
    "ARI": ("Arizona Cardinals", "Arizona", "Cardinals"),
    "ATL": ("Atlanta Falcons", "Atlanta", "Falcons"),
    "BAL": ("Baltimore Ravens", "Baltimore", "Ravens"),
    "BUF": ("Buffalo Bills", "Buffalo", "Bills"),
    "CAR": ("Carolina Panthers", "Carolina", "Panthers"),
    "CHI": ("Chicago Bears", "Chicago", "Bears"),
    "CIN": ("Cincinnati Bengals", "Cincinnati", "Bengals"),
    "CLE": ("Cleveland Browns", "Cleveland", "Browns"),
    "DAL": ("Dallas Cowboys", "Dallas", "Cowboys"),
    "DEN": ("Denver Broncos", "Denver", "Broncos"),
    "DET": ("Detroit Lions", "Detroit", "Lions"),
    "GB": ("Green Bay Packers", "Green Bay", "Packers"),
    "HOU": ("Houston Texans", "Houston", "Texans"),
    "IND": ("Indianapolis Colts", "Indianapolis", "Colts"),
    "JAX": ("Jacksonville Jaguars", "Jacksonville", "Jaguars"),
    "KC": ("Kansas City Chiefs", "Kansas City", "Chiefs"),
    "LA": ("Los Angeles Rams", "LA Rams", "L.A. Rams", "Rams"),
    "LAC": ("Los Angeles Chargers", "LA Chargers", "L.A. Chargers", "Chargers"),
    "LV": ("Las Vegas Raiders", "Las Vegas", "Raiders"),
    "MIA": ("Miami Dolphins", "Miami", "Dolphins"),
    "MIN": ("Minnesota Vikings", "Minnesota", "Vikings"),
    "NE": ("New England Patriots", "New England", "Patriots"),
    "NO": ("New Orleans Saints", "New Orleans", "Saints"),
    "NYG": ("New York Giants", "NY Giants", "N.Y. Giants", "Giants"),
    "NYJ": ("New York Jets", "NY Jets", "N.Y. Jets", "Jets"),
    "PHI": ("Philadelphia Eagles", "Philadelphia", "Eagles"),
    "PIT": ("Pittsburgh Steelers", "Pittsburgh", "Steelers"),
    "SEA": ("Seattle Seahawks", "Seattle", "Seahawks"),
    "SF": ("San Francisco 49ers", "San Francisco", "49ers"),
    "TB": ("Tampa Bay Buccaneers", "Tampa Bay", "Buccaneers"),
    "TEN": ("Tennessee Titans", "Tennessee", "Titans"),
    "WAS": ("Washington Commanders", "Washington Football Team", "Washington", "Commanders", "Football Team"),
}


def _norm(name) -> str:
    """Case, full stops and extra spaces don't matter: "L.A. Rams" and "la  rams" are the same name."""
    return " ".join(str(name or "").lower().replace(".", "").split())


TEAM_NAMES = {_norm(n): code for code, names in _TEAMS.items() for n in names}
assert len(TEAM_NAMES) == len({(_norm(n), c) for c, names in _TEAMS.items() for n in names}), \
    "a team name maps to two codes"


def team_code(name) -> str | None:
    return TEAM_NAMES.get(_norm(name))


# Two-team city names. Resolved by a rule declared before the download that reads no result: the name is the one of its
# two codes that has a game against the other named team (in either home/away order) within DATE_SLACK_DAYS of the
# file's date in the repo's schedule, when exactly one of them does. Otherwise (neither, both, or the other name is
# itself a two-team city name) the game is counted and left out.
CITY_NAMES = {_norm(n): codes for codes, names in ((("NYG", "NYJ"), ("New York", "NY", "N.Y.")),
                                                    (("LA", "LAC"), ("Los Angeles", "LA", "L.A.")))
              for n in names}
assert not set(CITY_NAMES) & set(TEAM_NAMES), "a two-team city name is also in the mapping"


def resolve_city(name, other: str | None, d: date, schedule_pairs) -> str | None:
    """The code a two-team city name stands for, or None. other: the other team's code (None when it is unmapped or is
    itself a two-team city name). schedule_pairs: {(home, away): [Eastern dates]} from the repo's schedule."""
    codes = CITY_NAMES.get(_norm(name))
    if not codes or other is None:
        return None
    slack = timedelta(days=DATE_SLACK_DAYS)
    hits = [c for c in codes if any(abs(g - d) <= slack for pair in ((c, other), (other, c))
                                    for g in schedule_pairs.get(pair, ()))]
    return hits[0] if len(hits) == 1 else None


def season_of(d: date) -> int:
    """An NFL season is named for the year it starts: a game dated in August or later belongs to that year's season,
    one dated before August to the previous year's (January 4, 2026 is in the 2025 season)."""
    return d.year if d.month >= 8 else d.year - 1


# ================================================================ the file

def load_rows(blob: bytes) -> tuple[list[dict], list[str]]:
    """The rows of all_odds.csv in the zip. A zip without a file of that name stops the run (the registration names
    the file)."""
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        names = [n for n in z.namelist() if Path(n).name == CSV_NAME]
        if len(names) != 1:
            raise SystemExit(f"The NFL zip holds {len(names)} files named {CSV_NAME} (files: "
                             f"{', '.join(z.namelist()) or 'none'}). Nothing was computed.")
        text = z.read(names[0]).decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    return list(reader), list(reader.fieldnames or [])


def check_columns(fields: list[str]) -> None:
    """The file must have the NBA file's columns for spreads and totals. Anything missing stops the run before any
    figure is read, naming every missing column; the hub then adapts only the column mapping, by a dated note in the
    registration, before any result is read."""
    missing = [c for c in REQUIRED if c not in fields]
    if missing:
        raise SystemExit(f"{CSV_NAME} for the NFL is not on the NBA file's layout: {len(missing)} expected columns are "
                         f"missing: {', '.join(missing)}. Columns in the file: {', '.join(fields) or 'none'}. "
                         "Nothing was computed. Adapt only the column mapping, by a dated note in "
                         f"{REGISTRATION_DOC}, before any result is read.")


def _path_sql(p: Path) -> str:
    return "'" + str(p).replace("'", "''") + "'"


def load_schedule(nfl_dir: Path, with_scores: bool = False) -> list[dict]:
    """The repo's own NFL schedule for the 2021-25 seasons: game id, season, type, Eastern date and teams, nflverse's
    closing spread_line and total_line (prices, not results; for the check of the file's lines), and the final score
    only when asked. No row of a later season is read."""
    import duckdb
    path = Path(nfl_dir) / "data" / "processed" / "games.parquet"
    if not path.is_file():
        raise SystemExit(f"The repo's NFL games table is missing: {path}. Nothing was computed.")
    cols = ["game_id", "season", "game_type", "gameday", "home_team", "away_team"]
    con = duckdb.connect()
    try:
        present = {r[0] for r in con.execute(f"DESCRIBE SELECT * FROM read_parquet({_path_sql(path)})").fetchall()}
        cols += [c for c in SCHEDULE_LINES if c in present]
        cols += ["home_score", "away_score"] if with_scores else []
        rows = con.execute(f"SELECT {', '.join(cols)} FROM read_parquet({_path_sql(path)}) "
                           f"WHERE season BETWEEN {FIRST_SEASON} AND {LAST_SEASON}").fetchall()
    finally:
        con.close()
    out = []
    for r in rows:
        g = dict(zip(cols, r))
        g["gameday"] = date.fromisoformat(str(g["gameday"])[:10])
        out.append(g)
    return out


def load_rule_b_triggers(nfl_dir: Path) -> dict | None:
    """The repo's own table of games that met Rule B's wind trigger: the forecast replay on NWS MOS
    (nfl-weather/data/processed/mos_replay.parquet, column mos_signal), seasons 2021-25. Only the game ids and seasons
    are read; nothing about how the games ended."""
    import duckdb
    path = Path(nfl_dir) / "data" / "processed" / "mos_replay.parquet"
    if not path.is_file():
        return None
    con = duckdb.connect()
    try:
        rows = con.execute(f"SELECT game_id, season FROM read_parquet({_path_sql(path)}) WHERE season BETWEEN "
                           f"{FIRST_SEASON} AND {LAST_SEASON} AND mos_signal").fetchall()
    finally:
        con.close()
    return {gid: str(season) for gid, season in rows}


def prepare(rows: list[dict], schedule: list[dict]) -> tuple[list[dict], dict]:
    """Rows -> one game per row of the 2021-25 seasons joined to the repo's schedule, plus counts. Reads the date and
    the two team names of every row; rows of a later season stop there. Reads no result and no figure: the
    exact-duplicate check compares every column but an unnamed row index as text, for equality only."""
    info = {"n_rows": len(rows), "bad_date": 0, "later_seasons": Counter(), "earlier_seasons": Counter(),
            "exact_duplicate_rows": 0, "unknown_teams": Counter(), "left_out": Counter(), "date_offsets": Counter(),
            "swapped": 0, "game_types": Counter(), "unjoined_examples": [], "city_names": Counter(),
            "index_columns": sorted({c for r in rows[:1] for c in r if is_row_index(c)})}
    kept, seen = [], set()
    for r in rows:
        d = k._date(r.get(k.COL_DATE))
        if d is None:
            info["bad_date"] += 1
            continue
        season = season_of(d)
        if season > LAST_SEASON:                        # counted, and nothing else about the row is read
            info["later_seasons"][season] += 1
            continue
        if season < FIRST_SEASON:
            info["earlier_seasons"][season] += 1
            continue
        sig = tuple(sorted((str(key), str(val)) for key, val in r.items() if not is_row_index(key)))
        if sig in seen:                                 # an exact duplicate row is dropped to one
            info["exact_duplicate_rows"] += 1
            continue
        seen.add(sig)
        kept.append((d, r))
    info["n_kept_rows"] = len(kept)
    by_pair = defaultdict(list)
    for g in schedule:
        by_pair[(g["home_team"], g["away_team"])].append(g)
    pair_dates = {pair: [g["gameday"] for g in gs] for pair, gs in by_pair.items()}
    slack = timedelta(days=DATE_SLACK_DAYS)
    joined = []
    for d, r in kept:
        names = (r.get(k.COL_HOME), r.get(k.COL_AWAY))
        codes = [team_code(x) for x in names]
        cities = [_norm(x) in CITY_NAMES for x in names]
        for i in (0, 1):                                # a two-team city name, from the schedule alone
            if cities[i]:
                codes[i] = resolve_city(names[i], codes[1 - i], d, pair_dates)
                info["city_names"][(str(names[i]), codes[i] or "left out")] += 1
        home, away = codes
        if home is None or away is None:
            if any(c is None and not city for c, city in zip(codes, cities)):
                for name, code, city in zip(names, codes, cities):
                    if code is None and not city:
                        info["unknown_teams"][str(name)] += 1
                info["left_out"]["team name not in the mapping"] += 1
            else:
                info["left_out"]["two-team city name not resolved"] += 1
            continue
        swapped = False
        cands = [g for g in by_pair[(home, away)] if abs(g["gameday"] - d) <= slack]
        if not cands:
            cands = [g for g in by_pair[(away, home)] if abs(g["gameday"] - d) <= slack]
            swapped = bool(cands)
        if len(cands) != 1:
            info["left_out"]["no game in the repo's schedule" if not cands else "more than one game matches"] += 1
            if len(info["unjoined_examples"]) < 10:
                info["unjoined_examples"].append((d.isoformat(), str(names[0]), str(names[1])))
            continue
        s = cands[0]
        joined.append({"game_id": s["game_id"], "date": s["gameday"], "file_date": d, "season": str(s["season"]),
                       "game_type": s["game_type"], "home": home, "away": away, "names": names, "swapped": swapped,
                       "row": r, **{c: s.get(c) for c in SCHEDULE_LINES}})
    per_game = Counter(g["game_id"] for g in joined)
    twice = {gid for gid, n in per_game.items() if n > 1}
    if twice:                                           # neither row is chosen over the other: both are left out
        info["left_out"]["the same game on two rows that differ"] += sum(per_game[gid] for gid in twice)
    games = [g for g in joined if g["game_id"] not in twice]
    for g in games:
        info["game_types"][g["game_type"]] += 1
        info["date_offsets"][(g["date"] - g["file_date"]).days] += 1
        info["swapped"] += g["swapped"]
    return games, info


def read_figures(games: list[dict], info: dict) -> None:
    """Prices, shares and lines of each game (no result). Shares given as fractions are multiplied by 100 and American
    odds converted to decimal, as in the NBA registration, judged over the joined games."""
    share_cols = [k._col(m, s, w) for m in MARKETS for s in SIDES[m] for w in ("stake", "wager")]
    shares = [x for g in games for c in share_cols if (x := k._num(g["row"].get(c))) is not None]
    info["share_scale"] = 100.0 if shares and max(shares) <= 1.0 else 1.0
    prices = [x for g in games for m in MARKETS for s in SIDES[m]
              if (x := k._num(g["row"].get(k._col(m, s, "dec")))) is not None]
    info["american_prices"] = bool(prices) and min(prices) < 0
    for g in games:
        r, g["m"] = g["row"], {}
        for m in MARKETS:
            g["m"][m] = {}
            for s in SIDES[m]:
                dec = k._num(r.get(k._col(m, s, "dec")))
                if info["american_prices"]:
                    dec = k._american_to_decimal(dec)
                st, wg = k._num(r.get(k._col(m, s, "stake"))), k._num(r.get(k._col(m, s, "wager")))
                g["m"][m][s] = {"dec": dec, "stake": None if st is None else st * info["share_scale"],
                                "wager": None if wg is None else wg * info["share_scale"],
                                "line": k._num(r.get(k._col(m, s, "line")))}


def attach_scores(games: list[dict], scores: list[dict], info: dict) -> list[dict]:
    """Each game's final score from the repo's table, as the file's home and away team scored. A game with no final
    score is left out and counted."""
    by_id = {s["game_id"]: s for s in scores}
    out = []
    for g in games:
        s = by_id.get(g["game_id"])
        if s is None or s.get("home_score") is None or s.get("away_score") is None \
                or any(isinstance(x, float) and math.isnan(x) for x in (s["home_score"], s["away_score"])):
            info["left_out"]["no final score in the repo's table"] += 1
            continue
        hs, as_ = float(s["home_score"]), float(s["away_score"])
        out.append(g | {"home_pts": as_ if g["swapped"] else hs, "away_pts": hs if g["swapped"] else as_})
    return out


# ================================================================ results from the scores

def _line_problem(market: str, a: dict, b: dict) -> bool:
    off = (a["line"] + b["line"]) if market == "spread" else (a["line"] - b["line"])
    return abs(off) > 1e-9


def outcome(g: dict, market: str) -> str | None:
    """Which side won at the file's closing line, from the repo's score: side 1 (home, over), side 2, or "push" when
    the score lands exactly on the line. None when the line is missing or the two sides' lines don't mirror."""
    s1, s2 = SIDES[market]
    a, b = g["m"][market][s1], g["m"][market][s2]
    if a["line"] is None or b["line"] is None or _line_problem(market, a, b):
        return None
    if market == "spread":                 # the home side covers when its score plus its line beats the away score
        x = g["home_pts"] + a["line"] - g["away_pts"]
    else:                                  # the over wins when the total points beat the line
        x = g["home_pts"] + g["away_pts"] - a["line"]
    if abs(x) < 1e-9:
        return "push"
    return s1 if x > 0 else s2


def market_records(games: list[dict], market: str) -> tuple[list[dict], Counter]:
    """One record per game with every figure of this market present and a decided result; the rest counted by
    reason, in this order: a missing figure, the margin, lines that don't mirror, a push."""
    s1, s2 = SIDES[market]
    recs, excl = [], Counter()
    for g in games:
        a, b = g["m"][market][s1], g["m"][market][s2]
        if any(v is None for o in (a, b) for v in (o["dec"], o["stake"], o["wager"], o["line"])) \
                or a["dec"] <= 1 or b["dec"] <= 1:
            excl["missing figure"] += 1
            continue
        margin = 1 / a["dec"] + 1 / b["dec"] - 1
        if margin < 0 or margin > MAX_MARGIN:
            excl[MARGIN] += 1
            continue
        if _line_problem(market, a, b):
            excl[MIRROR] += 1
            continue
        won = outcome(g, market)
        if won == "push":
            excl["push"] += 1
            continue
        fair_a = (1 / a["dec"]) / (1 / a["dec"] + 1 / b["dec"])
        sides = {}
        for s, o, fair in ((s1, a, fair_a), (s2, b, 1 - fair_a)):
            sides[s] = {"fair": fair, "won": int(won == s), "dec": o["dec"], "div": o["stake"] - o["wager"],
                        "wager": o["wager"]}
        recs.append({"date": g["date"], "season": g["season"], "game_id": g["game_id"], "sides": sides})
    return recs, excl


def won_flag_check(games: list[dict]) -> dict:
    """The file's won flags against the result from the repo's score, per market, over the games whose line allows a
    result. Counted only: a disagreement changes nothing in the test. The games joined with home and away the other
    way round are also counted on their own ("swapped"), since a flag written for the schedule's home side would
    disagree there."""
    out = {}
    for m in MARKETS:
        s1, s2 = SIDES[m]
        c, pairs, sw = Counter(), Counter(), Counter()
        for g in games:
            ours = outcome(g, m)
            if ours is None:
                continue
            f1, f2 = (k._b(g["row"].get(k._col(m, s, "won"))) for s in (s1, s2))
            if f1 is None or f2 is None:
                verdict = BLANK_FLAG
            else:
                theirs = {(True, False): s1, (False, True): s2, (False, False): "push"}.get((f1, f2), "both sides won")
                verdict = "agree" if theirs == ours else "disagree"
                if verdict == "disagree":
                    pairs[(theirs, ours)] += 1
            c[verdict] += 1
            if g["swapped"]:
                sw[verdict] += 1
        out[m] = {"counts": c, "pairs": pairs, "swapped": sw}
    return out


# ================================================================ the 6 variants

def analyse(games: list[dict]) -> dict:
    """The 6 registered variants, on games of the 2021-25 seasons with a final score."""
    recs, excluded, variants = {}, {}, []
    for m in MARKETS:
        recs[m], excluded[m] = market_records(games, m)
    for m in MARKETS:                                                   # family A
        bets, both = k.pick_bets(recs[m], m, money_ahead)
        res = k.mean_test(bets, z_bar=Z_BAR) | {"season": k._season_means(bets, SEASONS), "both_sides": both}
        variants.append(k._sign_check(res, bar=BAR) | {"family": "A", "market": m, "k": THRESHOLD})
    for m in MARKETS:                                                   # family B
        res = k.regression_test(recs[m], m, seasons=SEASONS, z_bar=Z_BAR) | {"both_sides": 0}
        variants.append(k._sign_check(res, bar=BAR) | {"family": "B", "market": m, "k": None})
    for m in MARKETS:                                                   # family C
        bets, both = k.pick_bets(recs[m], m, few_tickets)
        res = k.mean_test(bets, z_bar=Z_BAR) | {"season": k._season_means(bets, SEASONS), "both_sides": both}
        variants.append(k._sign_check(res, bar=BAR) | {"family": "C", "market": m, "k": FADE_MAX_TICKETS})
    if len(variants) != N_VARIANTS:
        raise RuntimeError(f"{len(variants)} variants computed, {N_VARIANTS} registered")
    return {"variants": variants, "excluded": excluded, "n_records": {m: len(recs[m]) for m in MARKETS},
            "n_variants": len(variants)}


# ================================================================ the Rule B description (0 variants, counts only)

def _bin(x: float) -> int:
    return min(int(_share(x) // 10) * 10, TICKET_BINS[-1])


def rule_b_description(games: list[dict], triggers: dict | None) -> dict | None:
    """For the games that met Rule B's wind trigger (the repo's replay table), how many of each 10-point band of the
    share of tickets on the over; beside it, the same count for every joined game. No result is read or compared."""
    if triggers is None:
        return None
    ids = {g["game_id"] for g in games}
    rows = {"trigger": Counter(), "all": Counter()}
    blank = {"trigger": 0, "all": 0}
    for g in games:
        w = g["m"]["total"]["over"]["wager"]
        for key in ("all",) + (("trigger",) if g["game_id"] in triggers else ()):
            if w is None or not (0 <= _share(w) <= 100):
                blank[key] += 1
            else:
                rows[key][_bin(w)] += 1
    return {"n_triggers": len(triggers), "by_season": Counter(triggers.values()),
            "in_file": sum(1 for gid in triggers if gid in ids), "bins": rows, "no_share": blank}


# ================================================================ the run

# The hub pins these after it registers the test (as kaggle_h3.REGISTRATION does for the NBA test): the commit that first
# added the registration file, its commit time and the time GitHub records for it, from GitHub's own record. Until they
# are pinned, the report reads the commit and its time from git and leaves the GitHub time to the hub. Never guessed.
REGISTRATION = {"commit": None, "committed_utc": None, "github_utc": None}


def _registration_commit() -> dict | None:
    """The registration commit: REGISTRATION once the hub has pinned it, else the commit that first added the
    registration file, from git's own record (hash and commit time; the time it reached GitHub is then the hub's to
    add by hand)."""
    if REGISTRATION.get("commit"):
        return {"commit": REGISTRATION["commit"], "committed": REGISTRATION["committed_utc"],
                "github": REGISTRATION.get("github_utc"), "pinned": True}
    try:
        out = subprocess.run(["git", "log", "--diff-filter=A", "--format=%H %cI", "--", REGISTRATION_DOC],
                             cwd=ROOT, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    lines = [ln.split() for ln in out.stdout.strip().splitlines() if ln.strip()]
    if out.returncode != 0 or not lines:
        return None
    h, t = lines[-1][:2]
    return {"commit": h, "committed": t, "github": None, "pinned": False}


def _sha256_file(path: Path) -> str | None:
    path = Path(path)
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def input_hashes(nfl_dir: Path) -> dict:
    """The sha256 of the repo's two tables this run reads (the whole files), for the report's record."""
    base = Path(nfl_dir) / "data" / "processed"
    return {name: _sha256_file(base / name) for name in ("games.parquet", "mos_replay.parquet")}


def default_nfl_dir() -> Path:
    return ROOT.parent / "nfl-weather"


def _counts(c: Counter) -> str:
    return "; ".join(f"{key} {n:,}" for key, n in c.items())


def line_check_lines(lc: dict) -> list[str]:
    """The sign and mapping of the lines, as plain lines (the --check-only output and the report)."""
    L = [f"spread lines against nflverse's closing spread_line (the file's home line should be about -spread_line; "
         f"+spread_line when home and away were swapped in the join): {_counts(lc['spread'])}",
         f"total lines against nflverse's total_line: {_counts(lc['total'])}"]
    L.append("sign of the home spread against the moneyline favourite: "
             + (_counts(lc["moneyline"]) if lc["moneyline"] is not None else "no moneyline prices in the file"))
    return L


def check_summary(games: list[dict], info: dict, triggers: dict | None, fmt: dict | None = None,
                  inputs: dict | None = None) -> list[str]:
    """The --check-only lines: layout, rows, team names, the join, and the format of the lines, shares and prices
    (counts only). No score and no won flag."""
    lo = info["left_out"]
    L = [f"columns: all {len(REQUIRED)} expected columns are present; unnamed row index ignored by the duplicate "
         f"check: {info['index_columns'] or 'none'}",
         f"rows: {info['n_rows']:,}; unreadable date {info['bad_date']:,}; "
         f"later seasons (counted only) {dict(sorted(info['later_seasons'].items()))}; "
         f"earlier seasons {dict(sorted(info['earlier_seasons'].items()))}; "
         f"exact duplicate rows dropped {info['exact_duplicate_rows']:,}",
         f"team names not in the mapping: {dict(info['unknown_teams']) or 'none'}",
         "two-team city names (name, resolved to): "
         + (", ".join(f"{a} -> {b}: {c:,}" for (a, b), c in sorted(info["city_names"].items())) or "none"),
         f"joined to the repo's schedule: {len(games):,} games; home and away swapped {info['swapped']:,}; "
         f"date offsets (schedule minus file, days) {dict(sorted(info['date_offsets'].items()))}",
         f"left out before any figure: {dict(lo) or 'none'}",
         f"game types: {dict(info['game_types'])}"]
    if info["unjoined_examples"]:
        L.append("rows with no game in the schedule (first 10: file date, home, away): "
                 + "; ".join(", ".join(x) for x in info["unjoined_examples"]))
    if triggers is not None:
        ids = {g["game_id"] for g in games}
        L.append(f"Rule B trigger games 2021-25 in the repo's table: {len(triggers):,}; in the file: "
                 f"{sum(1 for gid in triggers if gid in ids):,}")
    if fmt is not None:
        L.append(f"shares read as {'fractions (multiplied by 100)' if info['share_scale'] == 100 else 'percentages'}; "
                 f"prices read as {'American odds (converted to decimal)' if info['american_prices'] else 'decimal odds'}")
        for m in MARKETS:
            c, n_ = fmt[m], fmt[m]["counts"]
            L.append(f"{m}s ({c['n']:,} joined games): missing splits {n_['missing splits']:,}; tickets add to 100 "
                     f"(±1) {k._pct(c['wager_sum_within_1'])}; money adds to 100 (±1) {k._pct(c['stake_sum_within_1'])}; "
                     f"missing or impossible price {n_['missing or impossible price']:,}; margin below 0% or above 20% "
                     f"{n_[MARGIN]:,}; median margin {k._pct(c['margin_median'], 2)}; missing line "
                     f"{n_['missing line']:,}; unreadable line {n_['unreadable line']:,}; {MIRROR} {n_[MIRROR]:,}; "
                     f"whole-number line {n_['whole-number line']:,}")
    if fmt is not None:
        L += line_check_lines(fmt["lines"])
    if inputs is not None:
        L.append("the repo's tables read (sha256): " + "; ".join(f"{a} {b or 'missing'}" for a, b in inputs.items()))
    return L


def run_h3_nfl(blob: bytes | None = None, nfl_dir=None, reports_dir=None, check_only: bool = False) -> dict:
    nfl_dir = Path(nfl_dir) if nfl_dir else default_nfl_dir()
    blob = k.download(sport=SPORT) if blob is None else blob
    rows, fields = load_rows(blob)
    check_columns(fields)
    schedule = load_schedule(nfl_dir, with_scores=False)
    games, info = prepare(rows, schedule)
    triggers = load_rule_b_triggers(nfl_dir)
    inputs = input_hashes(nfl_dir)
    base = {"fields": fields, "info": info, "n_rows": info["n_rows"], "unknown_teams": dict(info["unknown_teams"]),
            "sha256": hashlib.sha256(blob).hexdigest(), "n_joined": len(games), "inputs": inputs}
    read_figures(games, info)                             # prices, shares and lines; no score and no won flag
    fmt = format_checks(games, info["american_prices"])
    if check_only:                                        # counts only: no score or won flag has been read
        return base | {"check": check_summary(games, info, triggers, fmt, inputs), "format": fmt, "report": None,
                       "n_variants": 0}
    rule_b = rule_b_description(games, triggers)          # before any score is loaded
    scored = attach_scores(games, load_schedule(nfl_dir, with_scores=True), info)
    res = analyse(scored)
    res.update(base, n_games=len(scored), flags=won_flag_check(scored), rule_b=rule_b,
               checks=file_checks(games, scored, fmt), download=k.download_record(SPORT),
               registration=_registration_commit())
    res["report"] = write_report(res, reports_dir or REPORTS_DIR)
    return res


# ================================================================ the file itself (counts only)

def _sign(x: float) -> int:
    return 0 if abs(x) < 1e-9 else (1 if x > 0 else -1)


def line_checks(games: list[dict], american: bool = False) -> dict:
    """The sign and mapping of the file's spread and total lines, with no score and no won flag: (a) the file's home
    spread line against nflverse's closing spread_line (sign, and within LINE_TOLERANCE points); (b) the file's total
    line against nflverse's total_line; (c) when the file has moneyline prices, the sign of the home spread against the
    moneyline favourite. A flipped sign or a column read for the wrong side shows here as disagreements."""
    sp, tt, ml = Counter(), Counter(), Counter()
    for c, keys in ((sp, ("same sign", "opposite sign", "a line of zero", "missing", "within 3 points")),
                    (tt, ("within 3 points", "more than 3 points apart", "missing")),
                    (ml, ("agree", "disagree", "no favourite or a line of zero", "missing"))):
        for key in keys:
            c[key] += 0
    has_ml = bool(games) and all(k._col("money", s, "dec") in games[0]["row"] for s in ("home", "away"))
    for g in games:
        h, sl = g["m"]["spread"]["home"]["line"], g.get("spread_line")
        if h is None or sl is None or (isinstance(sl, float) and math.isnan(sl)):
            sp["missing"] += 1
        else:
            want = float(sl) if g["swapped"] else -float(sl)
            if _sign(h) == 0 or _sign(want) == 0:
                sp["a line of zero"] += 1
            else:
                sp["same sign" if _sign(h) == _sign(want) else "opposite sign"] += 1
            sp["within 3 points"] += abs(h - want) <= LINE_TOLERANCE
        o, tl = g["m"]["total"]["over"]["line"], g.get("total_line")
        if o is None or tl is None or (isinstance(tl, float) and math.isnan(tl)):
            tt["missing"] += 1
        else:
            tt["within 3 points" if abs(o - float(tl)) <= LINE_TOLERANCE else "more than 3 points apart"] += 1
        if has_ml:
            mh, ma = (k._num(g["row"].get(k._col("money", s, "dec"))) for s in ("home", "away"))
            if american:
                mh, ma = k._american_to_decimal(mh), k._american_to_decimal(ma)
            if h is None or mh is None or ma is None or mh <= 1 or ma <= 1:
                ml["missing"] += 1
            elif abs(mh - ma) < 1e-9 or _sign(h) == 0:
                ml["no favourite or a line of zero"] += 1
            else:
                ml["agree" if (mh < ma) == (h < 0) else "disagree"] += 1
    return {"spread": sp, "total": tt, "moneyline": ml if has_ml else None}


def format_checks(games: list[dict], american: bool = False) -> dict:
    """The format of the lines, shares and prices of the joined games, per market, and the sign and mapping of the
    lines (line_checks, under "lines"): counts only, no score and no won flag. The same code gives the --check-only
    output and the report's format counts."""
    markets = {"lines": line_checks(games, american)}
    for m in MARKETS:
        s1, s2 = SIDES[m]
        c, sums, margins = Counter(), {"stake": [], "wager": []}, []
        for key in ("missing splits", "missing or impossible price", MARGIN, "missing line", "unreadable line", MIRROR,
                    "whole-number line"):
            c[key] += 0
        for g in games:
            a, b = g["m"][m][s1], g["m"][m][s2]
            if any(o[w] is None for o in (a, b) for w in ("stake", "wager")):
                c["missing splits"] += 1
            for w in ("stake", "wager"):
                if a[w] is not None and b[w] is not None:
                    sums[w].append(a[w] + b[w])
            if a["dec"] is None or b["dec"] is None or a["dec"] <= 1 or b["dec"] <= 1:
                c["missing or impossible price"] += 1
            else:
                margin = 1 / a["dec"] + 1 / b["dec"] - 1
                margins.append(margin)
                c[MARGIN] += margin < 0 or margin > MAX_MARGIN
            if a["line"] is None or b["line"] is None:
                raw = [str(g["row"].get(k._col(m, s, "line")) or "").strip() for s in (s1, s2)]
                c["unreadable line" if any(x and k._num(x) is None for x in raw) else "missing line"] += 1
            else:
                c[MIRROR] += _line_problem(m, a, b)
                c["whole-number line"] += float(a["line"]).is_integer()
        markets[m] = {"counts": c, "n": len(games),
                      **{f"{w}_sum_within_1": (sum(abs(_share(x - 100)) <= 1 for x in v) / len(v)) if v
                         else float("nan") for w, v in sums.items()},
                      "margin_median": float(np.median(margins)) if margins else float("nan")}
    return markets


def file_checks(games: list[dict], scored: list[dict], fmt: dict) -> dict:
    per_season = {}
    for s in SEASONS:
        gs = [g for g in games if g["season"] == s]
        per_season[s] = {"games": len(gs), "scored": sum(1 for g in scored if g["season"] == s),
                         "first": min((g["date"] for g in gs), default=None),
                         "last": max((g["date"] for g in gs), default=None),
                         "missing_splits": sum(1 for g in gs if any(
                             g["m"][m][sd][w] is None for m in MARKETS for sd in SIDES[m] for w in ("stake", "wager")))}
    return {"per_season": per_season, "markets": fmt}


# ================================================================ the report

def _name(v: dict) -> str:
    mk = MARKET_LABEL[v["market"]]
    if v["family"] == "A":
        return f"A: {mk}, money − tickets ≥ {v['k']}"
    if v["family"] == "B":
        return f"B: {mk}, per 10 points ({'over' if v['market'] == 'total' else 'home side'})"
    return f"C: {mk}, tickets ≤ {v['k']}%"


def _plain(v: dict) -> str:
    mk, x = MARKET_LABEL[v["market"]], abs(v["est"]) * 100
    more = "more" if v["est"] > 0 else "less"
    if v["family"] == "A":
        return (f"backing the {mk} side with at least {v['k']} points more of the money than of the tickets (it won "
                f"{x:.1f} points {more} often than its fair chance)")
    if v["family"] == "B":
        side = "over" if v["market"] == "total" else "home side"
        return (f"the {mk} regression (the {side} won {x:.1f} points {more} often than its fair chance for every 10 "
                "points by which its share of money beat its share of tickets)")
    return (f"fading the public on {mk}s, backing the side with {v['k']}% of the tickets or fewer (it won {x:.1f} "
            f"points {more} often than its fair chance)")


def _signs(v: dict) -> str:
    return " ".join({1: "+", -1: "−", 0: "0", None: "·"}[v["signs"][s]] for s in SEASONS)


def finding_text(res: dict) -> list[str]:
    vs = res["variants"]
    passed = [v for v in vs if v["passes"]]
    ps = [v for v in vs if not math.isnan(v["p"])]
    best = min(ps, key=lambda v: v["p"]) if ps else None
    below05 = sum(v["p"] < 0.05 for v in ps)
    det = [v["detectable"] for v in vs if v["family"] in "AC" and not math.isnan(v["detectable"])]
    if not passed:
        s1 = (f"**None of the {N_VARIANTS} variants passes the bar** (p below {BAR:.6f} and the same sign in at least "
              f"{SEASONS_NEEDED} of the {len(SEASONS)} seasons): at BetMGM's close in the NFL, {SEASONS[0]} to "
              f"{SEASONS[-1]}, the split between tickets and money says nothing detectable that BetMGM's own closing "
              "price hadn't already priced in.")
        s2 = (f"The closest was {_plain(best)}, with p = {k._p(best['p'])}, about {best['p'] / BAR:,.0f} times too "
              f"large for the bar; {below05} of the {N_VARIANTS} {'was' if below05 == 1 else 'were'} below an ordinary "
              f"0.05, where chance alone would give about {0.05 * N_VARIANTS:.1f}." if best
              else "No variant had enough games to test.")
        s3 = (f"The test could only have detected effects of about {min(det) * 100:.1f} points of win chance or more "
              "in its biggest variant, and more in the others, so a small edge of the size that matters in betting is "
              "not ruled out: a null was the expected result." if det else "")
        return [s for s in (s1, s2, s3) if s]
    names = "; ".join(f"{_plain(v)}, p = {k._p(v['p'])}" for v in passed)
    return [f"**{len(passed)} of the {N_VARIANTS} variants pass the bar:** {names}.",
            "That is a lead, not a rule. No rule is registered from it, no money follows, and no football splits data "
            "is bought on the strength of it."]


def _table(vs: list[dict], family: str) -> list[str]:
    reg = family == "B"
    head = ("| Variant | n | Win rate | Mean fair chance | " + ("Coefficient per 10 points" if reg else "Won − fair")
            + " | SE plain" + (" (HC1)" if reg else "") + " | SE by date | Wider | p | Bar | Passes | Signs by season"
            " | Same sign | Smallest detectable | Return at the close |")
    L = [head, "|" + "---|" * 15]
    for v in vs:
        if v["family"] != family:
            continue
        L.append(f"| {_name(v)} | {v['n']:,} | {k._pct(v['win_rate'])} | {k._pct(v['mean_fair'])} | "
                 f"{k._pts(v['est'])} | {k._se(v['se_plain'])} | {k._se(v['se_grouped'])} ({v['G']:,} dates) | "
                 f"{v['wider']} | {k._p(v['p'])} | {BAR:.6f} | {'**yes**' if v['passes'] else 'no'} | "
                 f"{_signs(v)} | {v['same_sign']} of {len(SEASONS)} | {k._se(v['detectable'])} | "
                 f"{'no bet' if reg else k._pct(v['roi'], 2)} |")
    return L


def _order_note(reg: dict | None, dl: dict) -> str:
    """Once the hub has pinned the time GitHub records for the registration, that time is compared with the download;
    until then, the commit time is, and the line says so."""
    if not reg or not dl.get("downloaded_utc"):
        return ""
    on_github = bool(reg.get("github"))
    try:
        when = datetime.fromisoformat((reg["github"] if on_github else reg["committed"]).replace("Z", "+00:00"))
        before = when < datetime.fromisoformat(dl["downloaded_utc"].replace("Z", "+00:00"))
    except (ValueError, AttributeError, TypeError):
        return ""
    if on_github:
        return " It was on GitHub before the download." if before else " **It reached GitHub after the download.**"
    return (" Its commit time is before the download (the commit time, not the time it reached GitHub)." if before
            else " **Its commit time is after the download.**")


def _registration_line(reg: dict | None, dl: dict) -> str:
    if not reg:
        return "- **Registration:** the commit that first added the registration file could not be read from git."
    if reg.get("pinned"):
        gh = f"; on GitHub at {reg['github']} (UTC, GitHub's record)" if reg.get("github") else ""
        return (f"- **Registration:** commit `{reg['commit']}`, committed {reg['committed']}{gh}."
                + _order_note(reg, dl))
    return ("- **Registration:** the commit that first added the registration file is "
            f"`{reg['commit']}`, committed {reg['committed']} (git's record; the hub pins it and the time it reached "
            "GitHub in `REGISTRATION` in the code, and adds the GitHub time below)." + _order_note(reg, dl))


def write_report(res: dict, reports_dir) -> Path:
    reports_dir = Path(reports_dir)
    reports_dir.mkdir(parents=True, exist_ok=True)
    path = reports_dir / REPORT_NAME
    kept = ""
    if path.exists():
        old = path.read_text()
        if HAND_SECTION in old:
            kept = old[old.index(HAND_SECTION):]
    vs, info, ch = res["variants"], res["info"], res["checks"]
    dl, reg = res.get("download") or {}, res.get("registration")
    passed = [v for v in vs if v["passes"]]
    later = sum(info["later_seasons"].values())
    L = ["# Betting splits, NFL test (H3): money versus tickets at BetMGM's close, 2021 to 2025", "",
         f"Registered in [`{REGISTRATION_DOC}`](../{REGISTRATION_DOC}) before the file was downloaded. Data: Kaggle "
         f"`{DATASET}` (CC BY-SA 4.0). Issue [#75](https://github.com/maxzipperman/value-finder/issues/75), part of "
         "[#66](https://github.com/maxzipperman/value-finder/issues/66). "
         f"**n_variants_tested = {res['n_variants']}**; the project's running count goes from {PRIOR_COUNT} to "
         f"{RUNNING_COUNT}, so the bar is p < 0.05 / {RUNNING_COUNT} = {BAR:.6f}, and the same sign in at least "
         f"{SEASONS_NEEDED} of the {len(SEASONS)} seasons.", "",
         "## The finding", "", " ".join(finding_text(res)), "",
         "## Limits", "",
         "- **One retail book.** BetMGM's own tickets and money, not the market's.",
         "- **Closing figures only.** Line moves against the public and timing can't be tested.",
         "- **The benchmark is BetMGM's own close,** with the margin removed proportionally, not Pinnacle's.",
         "- **Scraped by a third party from Yahoo.**",
         "- **Results come from the repo's own scores** (`nfl-weather/data/processed/games.parquet`) at the file's "
         "closing line; the file's won flags are only a cross-check (below).",
         f"- **No game of the 2026 season or later was read** ({later:,} rows, counted and nothing else).",
         "- **Only large effects are detectable.** See the \"Smallest detectable\" column: a null here means any "
         "effect is smaller than that, not that there is none.", "",
         "## Results", "",
         "Differences, standard errors and detectable effects are in percentage points of win chance (for family B, "
         "per 10 points of divergence). \"Won − fair\" is how much more often the backed side won than BetMGM's "
         "closing price, margin removed, said it would. Standard errors by date group the bets by the game's Eastern "
         f"date in the repo's schedule. Signs by season run {', '.join(SEASONS)}; \"·\" is a season with no bets, and "
         "\"0\" a season whose figure is zero, which counts as neither sign. The return at the close decides nothing.",
         "",
         f"### Family A: back the side whose share of money exceeds its share of tickets by at least {THRESHOLD} "
         "points", "", *_table(vs, "A"), "",
         "### Family B: the same idea without a threshold (regression with fair-chance tenths)", "",
         *_table(vs, "B"), "",
         f"### Family C: fade the public (back the side with {FADE_MAX_TICKETS}% of the tickets or fewer)", "",
         *_table(vs, "C"), "",
         "### Season figures (used only for the sign check; no standard error or p-value is computed for a season)",
         "", "| Variant | " + " | ".join(SEASONS) + " |", "|" + "---|" * (len(SEASONS) + 1)]
    for v in vs:
        L.append(f"| {_name(v)} | " + " | ".join(
            f"{k._pts(v['season'][s][0])} (n {v['season'][s][1]:,})" for s in SEASONS) + " |")
    reasons = ("missing figure", "margin below 0% or above 20%", "lines that don't mirror", "push")
    L += ["", "### Games left out, by market and reason", "",
          f"Out of {res['n_games']:,} games of the {SEASONS[0]} to {SEASONS[-1]} seasons joined to the repo's schedule "
          "with a final score.", "",
          "| Market | Games tested | " + " | ".join(reasons) + " |", "|" + "---|" * (len(reasons) + 2)]
    for m in MARKETS:
        e = res["excluded"][m]
        L.append(f"| {MARKET_LABEL[m]} | {res['n_records'][m]:,} | " + " | ".join(f"{e.get(r, 0):,}" for r in reasons)
                 + " |")
    both = [(v, v["both_sides"]) for v in vs if v["both_sides"]]
    L += ["", "Games where both sides met a family A or C rule (left out of that variant): "
          + ("; ".join(f"{_name(v)}: {n}" for v, n in both) if both else "none") + "."]
    L += ["", "## What it means", ""]
    if passed:
        L += ["**Something passes.** A lead, not a rule. No rule is registered from this test and no money follows "
              "from it.", ""]
    else:
        L += ["**Nothing passes: recorded as a null.** Closing splits at one retail book add nothing detectable to "
              "that book's own closing price in the NFL, within what this sample can see.", ""]
    L += ["Either way, no football splits data is bought on the strength of this test.", ""]
    rb = res.get("rule_b")
    L += ["## Rule B's windy games: the share of tickets on the over (a description, 0 variants)", ""]
    if rb is None:
        L += ["The repo's Rule B table (`nfl-weather/data/processed/mos_replay.parquet`) was not found, so there is "
              "no description.", ""]
    else:
        by_season = ", ".join(f"{s}: {rb['by_season'].get(s, 0):,}" for s in SEASONS)
        L += [f"The games that met Rule B's wind trigger in the repo's forecast replay (`mos_replay.parquet`, "
              f"`mos_signal`): {rb['n_triggers']:,} in {SEASONS[0]} to {SEASONS[-1]} ({by_season}), "
              f"{rb['in_file']:,} of them in the file. Counts only: no result is read for them or compared with "
              "this table. Every joined game is shown beside them for scale.", "",
              "| Share of tickets on the over | Rule B trigger games | Every joined game |", "|---|---|---|"]
        for lo_ in TICKET_BINS:
            hi = lo_ + 10
            label = f"{lo_}% to {hi}%" if hi == 100 else f"{lo_}% to under {hi}%"
            L.append(f"| {label} | {rb['bins']['trigger'].get(lo_, 0):,} | {rb['bins']['all'].get(lo_, 0):,} |")
        L += [f"| no share | {rb['no_share']['trigger']:,} | {rb['no_share']['all']:,} |", ""]
    lo = info["left_out"]
    fl = res["flags"]
    flag_text = "; ".join(f"{MARKET_LABEL[m]}s: {fl[m]['counts'].get('agree', 0):,} agree, "
                          f"{fl[m]['counts'].get('disagree', 0):,} disagree, "
                          f"{fl[m]['counts'].get(BLANK_FLAG, 0):,} blank (of which on games joined with home and away "
                          f"swapped: {fl[m]['swapped'].get('agree', 0):,} agree, "
                          f"{fl[m]['swapped'].get('disagree', 0):,} disagree, "
                          f"{fl[m]['swapped'].get(BLANK_FLAG, 0):,} blank)" for m in MARKETS)
    L += ["## The file itself", "",
          f"- **Columns ({len(res['fields'])}):** " + ", ".join(k._colname(c) for c in res["fields"]) + ".",
          f"- **Rows:** {info['n_rows']:,} in all; {later:,} of the 2026 season or later (counted, nothing else read"
          + (f": {', '.join(f'{s}: {n:,}' for s, n in sorted(info['later_seasons'].items()))}" if later else "")
          + f"); {sum(info['earlier_seasons'].values()):,} before {FIRST_SEASON}; {info['bad_date']:,} with an "
          f"unreadable date; {info['exact_duplicate_rows']:,} exact duplicate rows dropped to one.",
          f"- **Shares** were read as {'fractions and multiplied by 100' if info['share_scale'] == 100 else 'percentages'}"
          f"; prices as {'American odds, converted to decimal' if info['american_prices'] else 'decimal odds'}.",
          "- **Team names not in the mapping:** "
          + (", ".join(f"\"{n}\" ({c:,} appearances)" for n, c in sorted(res["unknown_teams"].items()))
             if res["unknown_teams"] else "none") + ".",
          "- **Two-team city names** (\"New York\", \"Los Angeles\"; resolved from the schedule alone, or left out): "
          + (", ".join(f"\"{a}\" → {b} ({c:,})" for (a, b), c in sorted(info["city_names"].items())) or "none")
          + ".",
          "- **Unnamed row index** (ignored by the exact-duplicate check): "
          + (", ".join(f"\"{c}\"" for c in info["index_columns"]) or "none") + ".",
          f"- **The join to the repo's schedule** (both teams, and the date or one day either side): "
          f"{res['n_joined']:,} games; {info['swapped']:,} with home and away the other way round; date offsets "
          "(schedule minus file, in days): "
          + (", ".join(f"{d:+d}: {n:,}" for d, n in sorted(info["date_offsets"].items())) or "none") + ".",
          "- **Left out before any figure was read:** "
          + ("; ".join(f"{r}: {n:,}" for r, n in lo.items() if n) or "none") + ".",
          "- **Game types** (the repo's schedule): "
          + (", ".join(f"{t}: {n:,}" for t, n in sorted(info["game_types"].items())) or "none") + ".",
          "- **The file's won flags against the repo's scores** (a cross-check; it changes nothing in the test): "
          + flag_text + "."]
    dis = [(m, p, n) for m in MARKETS for p, n in fl[m]["pairs"].most_common(3)]
    if dis:
        L.append("- **The most common disagreements** (the file's flag, then the scores): "
                 + "; ".join(f"{MARKET_LABEL[m]}: file {a}, scores {b} ({n:,})" for m, (a, b), n in dis) + ".")
    L += ["", "| Season | Games joined | With a final score | First date | Last date | Games missing any split |",
          "|---|---|---|---|---|---|"]
    for s, d in ch["per_season"].items():
        L.append(f"| {s} | {d['games']:,} | {d['scored']:,} | {d['first'] or '—'} | {d['last'] or '—'} | "
                 f"{d['missing_splits']:,} |")
    L += ["", "| Market | Games | Missing splits | Tickets add to 100 (±1) | Money adds to 100 (±1) | Missing or "
          "impossible price | Margin below 0% or above 20% | Median margin | Missing line | Unreadable line | Lines that "
          "don't mirror | Whole-number line |",
          "|" + "---|" * 12]
    for m in MARKETS:
        c = ch["markets"][m]
        n_ = c["counts"]
        L.append(f"| {MARKET_LABEL[m]} | {c['n']:,} | {n_['missing splits']:,} | {k._pct(c['wager_sum_within_1'])} | "
                 f"{k._pct(c['stake_sum_within_1'])} | {n_['missing or impossible price']:,} | {n_[MARGIN]:,} | "
                 f"{k._pct(c['margin_median'], 2)} | {n_['missing line']:,} | {n_['unreadable line']:,} | "
                 f"{n_[MIRROR]:,} | "
                 f"{n_['whole-number line']:,} |")
    L += ["", "The sign and mapping of the lines (no score and no won flag; a flipped sign or a column read for the "
          "wrong side shows as disagreements):", ""] + [f"- {x}" for x in line_check_lines(ch["markets"]["lines"])]
    L += ["", "These format counts, and the line checks, come from the same code as the check-only output "
          "(`uv run markets h3-kaggle --sport nfl --check-only`), which the registration requires to be read, and any dated note made, before this run."]
    L += ["", "## Record", "",
          _registration_line(reg, dl),
          f"- **Download:** {dl.get('downloaded_utc', 'not recorded')} (UTC), {dl.get('bytes', 0):,} bytes.",
          f"- **The file's sha256** (the zip as downloaded): `{res['sha256']}`.",
          "- **The repo's tables read** (sha256 of each whole file, in `nfl-weather/data/processed/`): "
          + "; ".join(f"`{a}` `{b}`" if b else f"`{a}` not found" for a, b in (res.get("inputs") or {}).items())
          + ".",
          f"- **Variants:** {res['n_variants']} (2 in family A, 2 in B, 2 in C); running count {PRIOR_COUNT} → "
          f"{RUNNING_COUNT}; bar p < {BAR:.6f}; the smallest detectable effect is {Z_BAR:.2f} × 0.5 / √n.",
          "- Command: `uv run markets h3-kaggle --sport nfl` in `sharp-markets/`.", ""]
    text = "\n".join(L) + "\n"
    if kept:
        text += "\n" + kept
    path.write_text(text)
    return path
