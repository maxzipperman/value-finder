"""The join and the registered reads (PREREGISTRATION_PROPS.md, 2.4 to 2.10 and section 3).

`assign` gives every player-game line its fate: graded, or the first exclusion reason that applies, in this order
(each line is counted once, under one reason; `lines.REASONS`):
  game not matched to nflverse's schedule   the event matches no single 2023-25 nflverse game (or it has no kickoff)
  kickoff moved before the snapshot         nflverse's kickoff, the schedule's or the one listed in the snapshot is
                                            at or before the snapshot (the later of the requested and returned time)
  no line at the chosen book, missing price, two equally close main lines   (lines.player_lines)
  unmatched player                          the name maps to no player, or to more than one, on either team that
                                            season (roster.NameMap), or to a roster row with no player_id
  void (player didn't play)                 a matched player with no player_week row for that game
  push                                      the outcome equals the line
A player with a player_week row but no attempt in the market is graded at 0 (the under wins at any positive line).

No lookahead: a line's grade uses the prices of its own snapshot (the close, or T-24h for the secondary) and the
game's outcome; nothing else from after its close. The same-season median of 2.8 is known only after the season and
is descriptive, as registered.
"""
from __future__ import annotations

import math
from collections import Counter

import numpy as np
import pandas as pd

from . import lines as L
from .outcomes import STAT
from .roster import NameMap
from .stats import excess_test

SEASONS = (2023, 2024, 2025)
CHECK_P = 0.01                    # 2.9, condition 2: each of the five checks


def assign(pl: pd.DataFrame, games: pd.DataFrame, names: NameMap, pw: pd.DataFrame) -> pd.DataFrame:
    """pl: lines.player_lines; games: outcomes.match_events (matched events only); pw: outcomes.player_week.
    Adds season, game_id, player_id, detail, y, win and the final `status` ("" = graded)."""
    df = pl.merge(games, on="event_id", how="left")
    status = pd.Series("", index=df.index, dtype=object)
    no_game = df.game_id.isna()
    status[no_game] = L.GAME
    when = pd.concat([pd.to_datetime(df.snap, utc=True), pd.to_datetime(df.requested, utc=True)], axis=1).max(axis=1)
    kicks = [pd.to_datetime(df[c], utc=True) for c in ("kick", "commence", "kick_nflverse")]
    moved = ~no_game & np.logical_or.reduce([(k <= when).fillna(False).to_numpy() for k in kicks])
    status[(status == "") & moved] = L.MOVED
    open_ = (status == "") & (df.status != "")
    status[open_] = df.status[open_]                           # no line at the book, missing price, tie
    df["season"] = df.season.astype("Int64")
    pids, details = [None] * len(df), [""] * len(df)
    for j, (i, r) in enumerate(zip(df.index, df.itertuples(index=False))):
        if status[i] == "":
            pids[j], details[j] = names.match(int(r.season), (r.home, r.away), r.description)
            if pids[j] is None:
                status[i] = L.UNMATCHED
    df["player_id"], df["detail"] = pids, details
    played = set(zip(pw.game_id, pw.player_id))
    void = (status == "") & ~pd.Series([k in played for k in zip(df.game_id, df.player_id)], index=df.index)
    status[void] = L.VOID
    long = pw.melt(id_vars=["game_id", "player_id"], value_vars=list(STAT.values()), var_name="stat", value_name="y")
    long = long.groupby(["game_id", "player_id", "stat"], as_index=False).y.sum(min_count=1)   # one row a game
    df = df.assign(stat=df.market.map(STAT)).merge(long, on=["game_id", "player_id", "stat"], how="left")
    status.index = df.index
    df["y"] = np.where(status == "", df.y.fillna(0).astype(float), np.nan)   # a row with no attempt: 0
    push = (status == "") & (df.y == df.line)
    status[push] = L.PUSH
    df["status"] = status
    df["win"] = np.where(status == "", (df.y < df.line).astype(float), np.nan)
    return df


def exclusions(df: pd.DataFrame) -> pd.DataFrame:
    """Every excluded line, by snapshot, market and reason (2.7: counted by reason, listed on request)."""
    x = df[df.status != ""]
    cols = ["role", "market", "status"]
    t = x.groupby(cols).size().rename("lines").reset_index() if len(x) else pd.DataFrame(columns=cols + ["lines"])
    t["status"] = pd.Categorical(t.status, categories=L.REASONS, ordered=True)
    t["role"] = pd.Categorical(t.role, categories=[L.CLOSE, L.T24], ordered=True)
    return t.sort_values(["role", "market", "status"]).rename(columns={"status": "reason"}).reset_index(drop=True)


# ---------------------------------------------------------------- the statistic, by scope
def scopes(g: pd.DataFrame, markets) -> list[tuple[str, pd.DataFrame]]:
    """The pooled lines over `markets`, then each season, each market, and each season x market."""
    g = g[g.market.isin(markets)]
    out = [("pooled", g)]
    out += [(f"season {s}", g[g.season == s]) for s in sorted(g.season.dropna().unique())]
    if len(markets) > 1:
        out += [(m, g[g.market == m]) for m in markets]
        out += [(f"{m}, {s}", g[(g.market == m) & (g.season == s)])
                for m in markets for s in sorted(g.season.dropna().unique())]
    return out


def table(graded: pd.DataFrame, role: str, markets) -> pd.DataFrame:
    g = graded[(graded.role == role) & (graded.status == "")]
    rows = [{"scope": name, **excess_test(sub)} for name, sub in scopes(g, markets)]
    return pd.DataFrame(rows)


def controls(graded: pd.DataFrame, role: str = L.CLOSE) -> pd.DataFrame:
    g = graded[(graded.role == role) & (graded.status == "")]
    rows = []
    for m in L.CONTROLS:
        for name, sub in [(m, g[g.market == m])] + [(f"{m}, {s}", g[(g.market == m) & (g.season == s)])
                                                     for s in sorted(g[g.market == m].season.dropna().unique())]:
            rows.append({"scope": name, **excess_test(sub)})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- 2.8, the mechanism readout
def season_medians(pw: pd.DataFrame) -> pd.DataFrame:
    """season, player_id, market -> the median of his outcome over every 2023-25 game (regular season and playoffs)
    in which he has a player_week row (no attempt = 0)."""
    parts = []
    for m, col in STAT.items():
        if m in L.PRIMARY:
            med = pw.assign(v=pw[col].fillna(0).astype(float)).groupby(["season", "player_id"]).v.median()
            parts.append(med.rename("median").reset_index().assign(market=m))
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=["season", "player_id", "median",
                                                                                    "market"])


def readout(graded: pd.DataFrame, med: pd.DataFrame, role: str = L.CLOSE) -> pd.DataFrame:
    """Per primary market and season, over the graded lines: the mean of (line - same-season median) and the share
    of lines strictly above it (a line equal to the median is not above)."""
    g = graded[(graded.role == role) & (graded.status == "") & graded.market.isin(L.PRIMARY)]
    g = g.assign(season=g.season.astype(int)).merge(med, on=["season", "player_id", "market"], how="left")
    rows = []
    for (m, s), sub in g.groupby(["market", "season"]):
        d = sub.line - sub["median"]
        rows.append({"market": m, "season": int(s), "lines": len(sub), "no_median": int(d.isna().sum()),
                     "mean_line_minus_median": float(d.mean()), "share_above": float((d > 0).mean())})
    return pd.DataFrame(rows, columns=["market", "season", "lines", "no_median", "mean_line_minus_median",
                                       "share_above"])


# ---------------------------------------------------------------- 2.10, the line move
def line_move(df: pd.DataFrame) -> pd.DataFrame:
    """Primary player-games with a main line at the chosen book at both T-24h and the close (and neither snapshot
    excluded for the game or its kickoff): the close line minus the T-24h line. Reads no outcome."""
    ok = df[df.status.isin(["", L.UNMATCHED, L.VOID, L.PUSH]) & df.market.isin(L.PRIMARY)]
    k = ["event_id", "market", "description"]
    both = ok[ok.role == L.CLOSE][k + ["season", "line"]].merge(ok[ok.role == L.T24][k + ["line"]], on=k,
                                                                suffixes=("", "_t24"))
    both["move"] = both.line - both.line_t24
    rows = []
    for name, sub in [(m, both[both.market == m]) for m in L.PRIMARY] + [("pooled", both)]:
        rows.append({"scope": name, "pairs": len(sub), "mean_move": float(sub.move.mean()) if len(sub) else np.nan,
                     "share_up": float((sub.move > 0).mean()) if len(sub) else np.nan,
                     "share_down": float((sub.move < 0).mean()) if len(sub) else np.nan,
                     "share_same": float((sub.move == 0).mean()) if len(sub) else np.nan})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- section 3 and 2.9
def gate(graded: pd.DataFrame, ro: pd.DataFrame) -> dict:
    """The F3b gate (section 3), on the 2025 season only: the pooled primary excess above zero, and in EACH primary
    market both readout numbers above their marks (mean of line - median > 0, share above > 0.5)."""
    g = graded[(graded.role == L.CLOSE) & (graded.status == "") & graded.market.isin(L.PRIMARY)
               & (graded.season == 2025)]
    if g.empty:
        return {"read": False, "why": "no graded 2025 line in the primary markets"}
    pooled = excess_test(g)
    checks = {"pooled excess above zero": pooled["excess"] > 0}
    r25 = ro[ro.season == 2025].set_index("market") if len(ro) else pd.DataFrame()
    for m in L.PRIMARY:
        has = m in r25.index
        checks[f"{m}: mean (line - median) above zero"] = bool(has and r25.loc[m, "mean_line_minus_median"] > 0)
        checks[f"{m}: more than half the lines above the median"] = bool(has and r25.loc[m, "share_above"] > 0.5)
    return {"read": True, "pooled": pooled, "checks": checks, "passes": all(checks.values()),
            "markets": {m: excess_test(g[g.market == m]) for m in L.PRIMARY}}


def decision(graded: pd.DataFrame, alpha: float | None, uncached: dict | None = None) -> dict:
    """Section 2.9: "Read once, on 2023-25, after F3b is in and joined." So it is read only when 2023, 2024 and 2025
    all have graded primary lines at the close AND no unsealed 2023-25 F3 call is uncached (`uncached`: season label
    -> planned calls not in the cache). Until then the verdict is withheld and nothing is decided; the tables are
    still reported.

    "Carries it" (Drop): with one market or one season removed, the pooled excess of what remains is at or below
    zero. When nothing remains (a primary market with no graded line at all), the stricter reading applies: the
    other market carries it, so Drop."""
    g = graded[(graded.role == L.CLOSE) & (graded.status == "") & graded.market.isin(L.PRIMARY)]
    have = sorted(int(s) for s in g.season.dropna().unique())
    if not set(SEASONS) <= set(have):
        return {"read": False, "why": f"section 2.9 is read only on 2023-25; graded seasons: "
                                      f"{', '.join(map(str, have)) or 'none'}"}
    missing = {s: int(n) for s, n in sorted((uncached or {}).items()) if s in {str(x) for x in SEASONS} and n}
    if missing:
        return {"read": False, "withheld": True,
                "why": f"F3 is not all in: {sum(missing.values()):,} planned 2023-25 calls are not cached ("
                       + ", ".join(f"{s}: {n:,}" for s, n in missing.items()) + "). Section 2.9 is read once, "
                       "\"after F3b is in and joined\", so the verdict is withheld and nothing is decided; the tables "
                       "above are reported as they stand"}
    pooled = excess_test(g)
    cond1 = bool(alpha is not None and pooled["p"] < alpha)
    checks = {}
    for s in SEASONS:
        t = excess_test(g[g.season == s])
        checks[f"season {s}"] = (t["excess"], t["p"], bool(t["excess"] > 0 and t["p"] < CHECK_P))
    for m in L.PRIMARY:
        t = excess_test(g[g.market == m])
        checks[m] = (t["excess"], t["p"], bool(t["excess"] > 0 and t["p"] < CHECK_P))
    without = {f"without {m}": excess_test(g[g.market != m])["excess"] for m in L.PRIMARY}
    without |= {f"without {s}": excess_test(g[g.season != s])["excess"] for s in SEASONS}
    act = cond1 and all(ok for *_, ok in checks.values())
    carried = [k for k, v in without.items() if math.isnan(v) or v <= 0]       # nothing left: carried (stricter)
    drop = pooled["excess"] <= 0 or bool(carried)
    verdict = "Act" if act else "Drop" if drop else "Otherwise"
    return {"read": True, "pooled": pooled, "condition_1": cond1, "checks": checks, "without": without,
            "carried": carried, "act": act, "drop": bool(drop), "verdict": verdict}


def summary_counts(df: pd.DataFrame) -> Counter:
    return Counter(df.status.replace("", "graded"))
