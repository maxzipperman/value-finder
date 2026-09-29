"""Props pre-check (#41, for #10): how far does the mean of a player's outcome sit above its median?

No prop prices exist on disk; that is the point. This measures the skew a line-setter faces, so the
#10 hypothesis can be registered as "the posted line sits above the empirical median" before F3's
prop lines are pulled. Descriptive only: no bet is graded, so it adds no variant. The pre-registration
draft it feeds (README, idea 7) is the variant.

Data: nfl-weather/data/processed/player_games.parquet, 2023-25 (the seasons F3 covers). Its roles are
picked without hindsight (nflweather/players.py): QB = the starter, RB1 = last game's designed-carry
leader, WR1 = last game's target leader. Markets: QB passing yards, RB1 rushing yards, WR1 receiving
yards and receptions.

Games where the player had no attempt in the market (RB1 with no carry, WR1 with no target) are left
out and counted: the table can't tell an inactive player (whose prop is void) from one who played and
was never used. For each player-market-season with at least MIN_GAMES games: median, mean,
mean - median, and the share of games below the mean (the under's hit rate if a line sat at the mean)
and below the median. These use the whole season, so they describe the distribution; they are not
lines anyone could have set.

A caution, also printed: a line-setter works from past games. Against a trailing window (the player's
previous 6-16 regular-season games with an attempt, player_week.parquet, every player at a prop-sized
level, no role selection), outcomes fall short of the trailing mean AND the trailing median more often
than half the time (regression to the mean, injury exits, usage changes). So "line above a trailing
median" can't be the test of #10: books shade for that anyway. Only the posted line and its price can
answer it, which is why the draft grades the under at the de-vigged price.

    nfl-weather/.venv/bin/python strategy-research/props_median_check.py      (from the repo root)

Writes output/props_median_check.csv (one row per player-market-season) and prints the summary by market.
"""
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = Path(__file__).resolve().parent / "output"
SEASONS = (2023, 2024, 2025)
MIN_GAMES = 8
TRAIL_MIN, TRAIL_MAX = 6, 16
# market: (player_week stat, attempt column, positions, a prop-sized trailing median)
TRAIL = {"pass_yds": ("passing_yards", "attempts", ["QB"], 150), "rush_yds": ("rushing_yards", "carries", ["RB", "QB", "WR"], 30),
         "rec_yds": ("receiving_yards", "targets", ["WR", "TE", "RB"], 30),
         "receptions": ("receptions", "targets", ["WR", "TE", "RB"], 2.5)}
# market: (role, outcome column, the attempt column that says the player was used)
MARKETS = {"pass_yds": ("QB", "pass_yds", "pass_att"), "rush_yds": ("RB1", "rush_yds", "rush_att"),
           "rec_yds": ("WR1", "rec_yds", "targets"), "receptions": ("WR1", "rec", "targets")}


def long_table(pg: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """One row per player-game-market, with games order kept (game_id sorts by season and week)."""
    rows, dropped = [], {}
    for market, (role, col, att) in MARKETS.items():
        d = pg[pg.role == role][["game_id", "season", "player_id", "name", col, att]].copy()
        used = d[att].fillna(0) > 0
        dropped[market] = int((~used & d.season.isin(SEASONS)).sum())
        d = d[used].rename(columns={col: "y"}).drop(columns=att)
        d["market"] = market
        rows.append(d)
    out = pd.concat(rows, ignore_index=True).sort_values(["market", "player_id", "game_id"]).reset_index(drop=True)
    return out, dropped


def trailing_caution() -> pd.DataFrame:
    """Each 2023-25 regular-season game against the player's previous TRAIL_MIN-TRAIL_MAX games (from 2022)."""
    w = pd.read_parquet(ROOT / "nfl-weather" / "data" / "processed" / "player_week.parquet")
    w = w[w.season.between(2022, max(SEASONS)) & (w.season_type == "REG")].sort_values(["player_id", "season", "week"])
    rows = []
    for market, (col, att, pos, floor) in TRAIL.items():
        d = w[w.position.isin(pos) & (w[att].fillna(0) > 0)][["player_id", "season", col]].rename(columns={col: "y"})
        g = d.groupby("player_id").y
        d = d.assign(tm=g.transform(lambda s: s.shift(1).rolling(TRAIL_MAX, min_periods=TRAIL_MIN).mean()),
                     tmed=g.transform(lambda s: s.shift(1).rolling(TRAIL_MAX, min_periods=TRAIL_MIN).median()))
        e = d[d.season.isin(SEASONS) & d.tm.notna() & (d.tmed >= floor)]
        rows.append({"market": market, "games": len(e), "under_rate_at_trailing_mean": round((e.y < e.tm).mean(), 3),
                     "under_rate_at_trailing_median": round((e.y < e.tmed).mean(), 3),
                     "outcome_minus_trailing_mean": round((e.y - e.tm).mean(), 2)})
    return pd.DataFrame(rows)


def per_player_season(d: pd.DataFrame) -> pd.DataFrame:
    def f(s: pd.DataFrame) -> pd.Series:
        y = s.y.to_numpy(float)
        mean, med = y.mean(), np.median(y)
        return pd.Series({"name": s.name_.iloc[-1], "games": len(y), "median": med, "mean": round(mean, 2),
                          "mean_minus_median": round(mean - med, 2),
                          "share_below_mean": round((y < mean).mean(), 3),
                          "share_below_median": round((y < med).mean(), 3),
                          "share_at_median": round((y == med).mean(), 3)})
    d = d.rename(columns={"name": "name_"})
    t = d.groupby(["market", "season", "player_id"]).apply(f, include_groups=False).reset_index()
    return t[t.games >= MIN_GAMES].reset_index(drop=True)


def summary(t: pd.DataFrame, dropped: dict) -> pd.DataFrame:
    rows = []
    for market, s in t.groupby("market", sort=False):
        games = s.games.sum()
        below = (s.share_below_mean * s.games).sum() / games
        rows.append({
            "market": market, "player_seasons": len(s), "games": int(games), "no_attempt_games_left_out": dropped[market],
            "mean_minus_median_avg": round(s.mean_minus_median.mean(), 2),
            "mean_minus_median_median": round(s.mean_minus_median.median(), 2),
            "skew_pct_of_mean": round(100 * s.mean_minus_median.sum() / s["mean"].sum(), 1),
            "player_seasons_mean_above_median_pct": round(100 * (s.mean_minus_median > 0).mean(), 1),
            "under_rate_line_at_season_mean": round(below, 3),
            "under_rate_se": round(np.sqrt(below * (1 - below) / games), 3),
            "under_rate_line_at_season_median": round((s.share_below_median * s.games).sum() / games, 3)})
    return pd.DataFrame(rows)


def main():
    pg = pd.read_parquet(ROOT / "nfl-weather" / "data" / "processed" / "player_games.parquet")
    pg = pg[pg.season.isin(SEASONS)]
    d, dropped = long_table(pg)
    t = per_player_season(d)
    s = summary(t, dropped)
    OUT.mkdir(exist_ok=True)
    t.to_csv(OUT / "props_median_check.csv", index=False)
    pd.set_option("display.width", 250, "display.max_columns", 30)
    print(f"Player-market-seasons with >= {MIN_GAMES} games, {SEASONS[0]}-{SEASONS[-1]}:")
    print(s.set_index("market").T.to_string())
    by_season = t.assign(w=t.share_below_mean * t.games).groupby(["market", "season"]).agg(
        games=("games", "sum"), w=("w", "sum"), skew=("mean_minus_median", "mean"))
    by_season["under_rate_line_at_season_mean"] = (by_season.w / by_season.games).round(3)
    print("\nBy season:")
    print(by_season.drop(columns="w").round(2).to_string())
    print(f"\nCaution, not a test: each game vs the player's previous {TRAIL_MIN}-{TRAIL_MAX} games (player_week, "
          "no role selection, prop-sized players):")
    print(trailing_caution().set_index("market").T.to_string())
    return t, s


if __name__ == "__main__":
    main()
