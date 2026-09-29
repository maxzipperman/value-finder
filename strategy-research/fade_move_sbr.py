"""H16a pre-check (#42, for #16): fade the open-to-close move, betting at the close. NFL 2007-21.

Moskowitz (2021, J. Finance, Table III) finds NFL open-to-close moves partly reverse by the outcome,
after the close, but not by enough to beat the vig. This asks the betting version on free data: take
the side the line moved AWAY from, at the closing number, and grade it on win rate and ROI at -110
(the repo's rule for bets placed at the close, #4). It must beat the break-even of 110/210 = 52.38%.

Data: SBR opening and closing lines (nfl-weather/data/raw/odds/sbr_open_close.parquet), already joined
to nflverse results in nfl-weather/data/processed/games.parquet by nflweather.odds.match_to_games.
Regular season and playoffs. Conventions (nflverse): spread > 0 means the home team is favored by that
many; result = home score - away score.

  spreads  move = close - open. Up (home more favored) -> bet the away side at the close: wins if
           result < close. Down -> bet the home side: wins if result > close.
  totals   move = close - open. Up -> bet the under at the close: wins if total < close. Down -> over.
  Pushes are neither a win nor a loss, and are counted.

Thresholds |move| >= 0.5, 1 and 1.5 points (nested), spreads and totals separately: 3 x 2 = 6 variants
(running count 192 -> 198). Each is reported pooled and per season, with a one-sided binomial p against
the -110 break-even.

Outlier-odds audit (research sweep, after Clegg & Cartlidge 2024): a row whose SBR close is more than
AUDIT_PTS from nflverse's own closing line is suspect (a typo, or a mismatched game). Such rows are
counted, listed in the log, and every variant is re-run without them.

    nfl-weather/.venv/bin/python strategy-research/fade_move_sbr.py      (from the repo root)

Writes output/fade_move_sbr.csv (pooled and per-season rows, with and without the audit's rows).
"""
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

ROOT = Path(__file__).resolve().parents[1]
OUT = Path(__file__).resolve().parent / "output"
BE_110 = 110 / 210
THRESHOLDS = (0.5, 1.0, 1.5)
AUDIT_PTS = 3.0


def load() -> pd.DataFrame:
    g = pd.read_parquet(ROOT / "nfl-weather" / "data" / "processed" / "games.parquet")
    return g[g.result.notna() & g.season.between(2007, 2021)].copy()


def bets(g: pd.DataFrame) -> pd.DataFrame:
    """One row per game and market with a nonzero open-to-close move: the fade's result at the close."""
    s = g[g.spread_open.notna() & g.sbr_spread_close.notna()].copy()
    s["market"], s["open"], s["close"] = "spread", s.spread_open, s.sbr_spread_close
    s["check"] = s.spread_line                                      # nflverse's own closing spread
    s["margin"] = s.result - s.close                                # > 0: home covered the close
    t = g[g.total_open.notna() & g.sbr_total_close.notna()].copy()
    t["market"], t["open"], t["close"] = "total", t.total_open, t.sbr_total_close
    t["check"] = t.total_line
    t["margin"] = t.total - t.close                                 # > 0: the over won
    d = pd.concat([s, t], ignore_index=True)
    d["move"] = d.close - d.open
    d = d[d.move != 0].copy()
    # fade: against the move. Up -> away / under (wins when margin < 0); down -> home / over (margin > 0)
    fade_sign = -np.sign(d.move)
    d["win"] = np.sign(d.margin) == fade_sign
    d["loss"] = np.sign(d.margin) == -fade_sign
    d["push"] = d.margin == 0
    d["suspect"] = (d.close - d.check).abs() > AUDIT_PTS
    return d[["game_id", "season", "game_type", "market", "open", "close", "check", "move", "margin", "win", "loss",
              "push", "suspect"]]


def grade(d: pd.DataFrame) -> dict:
    w, l, p = int(d.win.sum()), int(d.loss.sum()), int(d.push.sum())
    n = w + l
    return {"bets": n, "wins": w, "losses": l, "pushes": p, "win_pct": round(w / n, 4) if n else np.nan,
            "roi_110": round((w * 100 / 110 - l) / n, 4) if n else np.nan,
            "p_vs_breakeven": stats.binomtest(w, n, BE_110, alternative="greater").pvalue if n else np.nan,
            "mean_abs_move": round(d.move.abs().mean(), 2) if len(d) else np.nan}


def table(d: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for sample, dd in (("all", d), ("audit_clean", d[~d.suspect])):
        for market in ("spread", "total"):
            for th in THRESHOLDS:
                x = dd[(dd.market == market) & (dd.move.abs() >= th)]
                rows.append({"sample": sample, "market": market, "min_move": th, "season": "2007-2021", **grade(x)})
                for season, y in x.groupby("season"):
                    rows.append({"sample": sample, "market": market, "min_move": th, "season": str(season), **grade(y)})
    return pd.DataFrame(rows)


def main():
    g = load()
    d = bets(g)
    t = table(d)
    OUT.mkdir(exist_ok=True)
    t.to_csv(OUT / "fade_move_sbr.csv", index=False)
    pd.set_option("display.width", 250, "display.max_columns", 30)
    print(f"NFL 2007-21 games with a result: {len(g):,}; with an SBR spread open and close: "
          f"{int((g.spread_open.notna() & g.sbr_spread_close.notna()).sum()):,}; totals: "
          f"{int((g.total_open.notna() & g.sbr_total_close.notna()).sum()):,}")
    for m in ("spread", "total"):
        x = d[d.market == m]
        print(f"  {m}: {len(x):,} moved; SBR close vs nflverse close: mean |gap| {(x.close - x.check).abs().mean():.2f}, "
              f"exact {((x.close - x.check) == 0).mean():.0%}, suspect (> {AUDIT_PTS:g} pts) {int(x.suspect.sum())}")
    sus = d[d.suspect].sort_values(["market", "season"])
    if len(sus):
        print("\nAudit, suspect rows (SBR close vs nflverse close):")
        print(sus[["game_id", "market", "open", "close", "check", "move"]].to_string(index=False))
    pooled = t[t.season == "2007-2021"].copy()
    pooled["p_vs_breakeven"] = pooled.p_vs_breakeven.map(lambda p: f"{p:.3f}")
    print("\nFade the move at the close, graded at -110 (break-even 52.38%), pooled 2007-21:")
    print(pooled.drop(columns="season").to_string(index=False))
    seas = t[(t["sample"] == "all") & (t.season != "2007-2021")]
    wide = seas.pivot_table(index="season", columns=["market", "min_move"], values="win_pct").round(3)
    print("\nWin rate by season (all rows):")
    print(wide.to_string())
    above = seas.assign(up=seas.win_pct > BE_110).groupby(["market", "min_move"]).up.agg(["sum", "count"])
    print("\nSeasons above break-even (of 15):")
    print(above.to_string())
    return t


if __name__ == "__main__":
    main()
