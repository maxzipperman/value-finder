"""F3's cached event-odds answers -> one row per player-game, snapshot and market: the main line at the chosen book.

Everything here is outcome-blind: no score, stat or roster is read. It is all the hub needs for the book note of
PREREGISTRATION_PROPS.md section 8 (`markets props-grade` stops after it until the note is recorded).

Reading (no lookahead, no sealed row). F3's calls are re-planned from the saved NFL schedule (`bulk.plan_calls`,
the same calls the puller made). A call the plan marks sealed (a 2026-season game) is never read at all; the rest
go through `bulk.load_rows`, which leaves out any row of a game in a sealed season window; and every row that is
left is checked again here: a game in a sealed window, or of NFL season 2026 or later by its date, is refused and
counted before anything else sees it. Each call is one game at one snapshot: its close, `bulk.close_time` of the
schedule's kickoff (the latest /events sighting before kickoff, `bulk.build_schedule`), the last 5-minute grid
point at least 5 minutes before it; or T-24h, the grid point at or before 24 hours before kickoff
(`bulk.event_snapshots`, offset 24). Prices are known at the answer's snapshot time, never `last_update`.

Player-games (2.4). A player-game is (event id, the `description` as returned), in one market at one snapshot,
present when any `us10` book lists a line for it under the market key itself (F3 asks for no `_alternate` key).
A name whose rows carry no point at any book is not a player-game under that definition, so it is not in the
coverage; it is still kept as a row and excluded under its own reason, NO_POINT (log, don't drop).

The book (2.4). In each primary market, at F3a's close snapshots (the 2025 season), the player-games with a line
at Pinnacle over the player-games with a line at any us10 book. Pinnacle only if it reaches 80% in EACH primary
market; otherwise DraftKings; one book for all four markets, never revisited on later data, no fill-in from another
book. Only which books list a line is read: no price level.

The main line (2.4, 2.5). At the chosen book, the lines (points) listed for the player. A usable line has exactly
one Over and one Under price, both readable and above 1, at a readable point. One line: it is the main line. More
than one: the one whose power-method under probability is closest to 0.5; two equally close (within 1e-9): the
player-game is excluded as a tie. Any listed line that isn't usable: the player-game is excluded as a missing price
(the rule can't be applied to every listed line; a stricter reading, listed for the hub). A player-game with no line
at the chosen book is excluded; no other book fills it in.
"""
from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import pandas as pd

from ...cache import read_status
from ...oddsapi import bulk
from ...settings import parse_ts
from . import stats

NFL = "americanfootball_nfl"
PRIMARY = ("player_reception_yds", "player_rush_yds")
CONTROLS = ("player_pass_yds", "player_receptions")
MARKETS = PRIMARY + CONTROLS
CLOSE, T24 = "close", "T-24h"
F3A = "2025"                     # F3a: the season label whose close-snapshot coverage picks the book
PINNACLE, DRAFTKINGS = "pinnacle", "draftkings"
COVERAGE_BAR = 0.80
TIE_TOL = 1e-9

# exclusion reasons (2.7), in the order a player-game is given the first that applies
GAME = "game not matched to nflverse's schedule"
MOVED = "kickoff moved before the snapshot"
NO_POINT = "no line (no point) at any us10 book"
NO_LINE = "no line at the chosen book"
MISSING = "missing price"
TIE = "two equally close main lines"
UNMATCHED = "unmatched player"
VOID = "void (player didn't play)"
MISSING_STAT = "missing or conflicting statistic"
PUSH = "push"
REASONS = (GAME, MOVED, NO_POINT, NO_LINE, MISSING, TIE, UNMATCHED, VOID, MISSING_STAT, PUSH)

ROW_COLS = ["event_id", "label", "role", "kick", "commence", "snap", "requested", "home_team", "away_team", "book",
            "market", "description", "side", "point", "price"]


def nfl_season(when: datetime) -> int:
    """The NFL season a kickoff belongs to, by its US Eastern date: September to February is one season."""
    d = pd.Timestamp(when).tz_convert("America/New_York")
    return d.year if d.month >= 3 else d.year - 1


def schedule(cfg: dict, cache) -> dict[str, dict]:
    """The saved NFL schedule (`markets odds5m probe` writes it), by event id. Empty until the probe has run."""
    return {g["id"]: g for g in bulk.load_schedules(cfg, cache.raw_dir, sports=[NFL]).get(NFL, [])}


def f3_calls(cfg: dict, games: dict[str, dict], now: datetime | None = None) -> list:
    return bulk.plan_calls(cfg, "F3", {NFL: list(games.values())}, now=now) if games else []


def role_of(call, kick: datetime) -> str | None:
    if call.at == bulk.close_time(kick):
        return CLOSE
    if call.at == bulk.floor5(kick - timedelta(hours=24)):
        return T24
    return None


def sealed_reason(cfg: dict, *times) -> str | None:
    """Why a row must be refused as sealed (a 2026-season game), or None."""
    for t in times:
        if t is None:
            continue
        if bulk.is_sealed(cfg, NFL, t):
            return "game in a sealed season window"
        if nfl_season(t) >= 2026:
            return "NFL season 2026 or later by the game's date"
    return None


@dataclass
class Loaded:
    rows: pd.DataFrame
    calls: int = 0
    sealed_calls: int = 0                                  # planned, never read
    status: Counter = field(default_factory=Counter)       # (season, role, "200" / "404" / "not cached")
    left_out: Counter = field(default_factory=Counter)     # by bulk.load_rows, by reason
    refused: Counter = field(default_factory=Counter)      # sealed rows refused here, by reason (expected 0)
    skipped: Counter = field(default_factory=Counter)      # rows not read, by reason (other markets, no name, ...)
    lag_minutes: dict = field(default_factory=dict)        # role -> (median, max) of requested minus returned


def load(cfg: dict, calls: list, cache, games: dict[str, dict]) -> Loaded:
    """Every outcome row of F3's open (unsealed) calls, one call at a time; see the module docstring."""
    books = set(cfg["books"][cfg["pulls"]["F3"]["books"]])
    out = Loaded(rows=pd.DataFrame(columns=ROW_COLS), calls=len(calls))
    raw, lags = [], {CLOSE: [], T24: []}
    for c in calls:
        if c.sealed:                                       # a sealed call is never read, not even its status
            out.sealed_calls += 1
            continue
        g = games[c.event_id]
        kick, label = g["commence_time"], g["season"] or "-"
        role = role_of(c, kick)
        path = cache.lookup(c.cache_sport, c.source, c.key)
        out.status[(label, role or "other", "not cached" if path is None else str(read_status(path)))] += 1
        if path is None:
            continue
        rows = bulk.load_rows(cfg, [c], cache, left_out=out.left_out)
        for r in rows:
            snap, commence = parse_ts(r["snapshot_ts"]), bulk.game_time(r["commence_time"])
            why = sealed_reason(cfg, kick, commence)
            if why:
                out.refused[why] += 1                      # never reaches anything below
                continue
            if role is None:
                out.skipped["call at neither the close nor T-24h"] += 1
            elif r["odds_event_id"] != c.event_id:
                out.skipped["row's event id differs from its call's"] += 1
            elif r["market_key"] not in MARKETS:
                out.skipped["market outside #10 (kicking markets are #21's)"] += 1
            elif not r["description"]:
                out.skipped["row with no player name"] += 1
            elif r["bookmaker"] not in books:
                out.skipped["book outside us10"] += 1
            elif snap is None:
                out.skipped["no snapshot time"] += 1
            else:
                raw.append((c.event_id, label, role, kick, commence, snap, c.at, r["home_team"], r["away_team"],
                            r["bookmaker"], r["market_key"], r["description"], r["outcome_name"], r["point"],
                            r["price_decimal"]))
        if rows and role in lags and (snap := parse_ts(rows[0]["snapshot_ts"])):
            lags[role].append((c.at - snap).total_seconds() / 60)
    out.lag_minutes = {k: (float(pd.Series(v).median()), float(max(v))) for k, v in lags.items() if v}
    if raw:
        out.rows = pd.DataFrame(raw, columns=ROW_COLS)
    return out


# ---------------------------------------------------------------- the book
def coverage(rows: pd.DataFrame) -> dict[str, tuple[int, int]]:
    """Per primary market at F3a's close: (player-games with a line at Pinnacle, player-games with a line at any
    us10 book). Counts which books list a line; reads no price."""
    r = rows[(rows.label == F3A) & (rows.role == CLOSE) & rows.market.isin(PRIMARY) & rows.point.notna()]
    out = {}
    for m in PRIMARY:
        pg = r[r.market == m].groupby(["event_id", "description"]).book.agg(set)
        out[m] = (int(sum(PINNACLE in b for b in pg)), len(pg))
    return out


def choose_book(cov: dict[str, tuple[int, int]]) -> str | None:
    """Pinnacle if it lists at least 80% of player-games in EACH primary market; otherwise DraftKings. None when
    F3a has no close-snapshot line in either primary market (nothing to choose on)."""
    if not any(den for _, den in cov.values()):
        return None
    clears = all(den and num / den >= COVERAGE_BAR for num, den in cov.values())
    return PINNACLE if clears else DRAFTKINGS


# ---------------------------------------------------------------- the main line
def _num(v) -> float:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return float("nan")
    return x if math.isfinite(x) else float("nan")


def main_line(outcomes: list[tuple]) -> dict | str:
    """One book's (side, point, price) rows for one player-game -> the main line, or the exclusion reason."""
    by_point: dict[float, dict[str, set]] = {}
    for side, point, price in outcomes:
        sides = by_point.setdefault(_num(point), {})
        sides.setdefault(side, set()).add(_num(price))
    lines = []
    for point, sides in by_point.items():
        over, under = sides.get("Over", set()), sides.get("Under", set())
        if math.isnan(point) or set(sides) - {"Over", "Under"} or len(over) != 1 or len(under) != 1:
            return MISSING
        (d_o,), (d_u,) = over, under
        if not (d_o > 1 and d_u > 1):                      # NaN fails too
            return MISSING
        lines.append({"line": float(point), "d_over": d_o, "d_under": d_u, "p_power": stats.devig_power(d_o, d_u),
                      "p_add": stats.devig_additive(d_o, d_u), "p_mult": stats.devig_multiplicative(d_o, d_u)})
    if not lines:
        return MISSING
    lines.sort(key=lambda x: abs(x["p_power"] - 0.5))
    if len(lines) > 1 and abs(abs(lines[1]["p_power"] - 0.5) - abs(lines[0]["p_power"] - 0.5)) <= TIE_TOL:
        return TIE
    return {**lines[0], "lines_listed": len(lines)}


LINE_COLS = ["event_id", "label", "role", "kick", "commence", "snap", "requested", "home_team", "away_team", "market",
             "description", "book", "status", "line", "d_over", "d_under", "p_power", "p_add", "p_mult",
             "lines_listed"]


def player_lines(rows: pd.DataFrame, book: str) -> pd.DataFrame:
    """One row per player name, market and snapshot in the rows: the chosen book's main line, or the reason it has
    none (`status`: "" for a main line, else NO_POINT, NO_LINE, MISSING or TIE)."""
    if rows.empty:
        return pd.DataFrame(columns=LINE_COLS)
    groups: dict[tuple, list] = {}
    cols = [rows[c].tolist() for c in ("event_id", "role", "market", "description", "book", "side", "point", "price")]
    for i, (eid, role, market, desc, b, side, point, price) in enumerate(zip(*cols)):
        groups.setdefault((eid, role, market, desc), []).append((i, b, side, point, price))
    keys = sorted(groups, key=lambda k: tuple(map(str, k)))
    meta = ["label", "kick", "commence", "snap", "requested", "home_team", "away_team"]   # the same within a call
    firsts = rows.iloc[[groups[k][0][0] for k in keys]][meta].to_dict("records")
    out = []
    for (eid, role, market, desc), first in zip(keys, firsts):
        g = groups[(eid, role, market, desc)]
        base = {"event_id": eid, "role": role, "market": market, "description": desc, "book": book, **first}
        at = [(side, point, price) for _, b, side, point, price in g if b == book]
        if all(point is None or pd.isna(point) for *_, point, _ in g):
            got = NO_POINT                                 # no book lists a line: counted, never dropped
        else:
            got = NO_LINE if not at else main_line(at)
        out.append({**base, "status": got} if isinstance(got, str) else {**base, "status": "", **got})
    return pd.DataFrame(out).reindex(columns=LINE_COLS)
