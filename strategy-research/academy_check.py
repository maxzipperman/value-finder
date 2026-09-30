"""Issue #54: service-academy unders on the rebuilt CFB games table. Verify before believing.

Reads only committed files: cfb-weather/data/processed/games.parquet (current) and, from git history, the
table before #48/#36 rebuilt it (commit bb4e6da's parent), plus cfbd_lines.parquet (2014-25 multi-book lines)
and the committed screen output before the rebuild (commit 1a2a9a8). No 2026 game is read. No new data.

Outputs (strategy-research/output/): academy_games.csv (all games that pass the screen's filter on either table),
academy_eras.csv, academy_screen_row_changes.csv (the CFB screen rows that moved), academy_check.log.
Run from the repo root:  nfl-weather/.venv/bin/python strategy-research/academy_check.py
"""
import io
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

ROOT = Path(__file__).resolve().parents[1]
OUT = Path(__file__).resolve().parent / "output"
ACAD = {"Army", "Navy", "Air Force"}
BE = 110 / 210
REBUILD = "bb4e6da"          # "Rebuild the CFB games table on the #36 spread fix"
SCREEN_COMMIT = "1a2a9a8"    # last commit that changed output/screens.csv before the rebuild's rerun


def git_show(rev, path):
    return subprocess.run(["git", "show", f"{rev}:{path}"], cwd=ROOT, check=True, capture_output=True).stdout


def screen_filter(d):
    """The screen's CFB filter (screen.py): result, home_spread present and non-zero, 2006-2025; then close_total present."""
    return d[d.result.notna() & d.home_spread.notna() & d.season.between(2006, 2025) & (d.home_spread != 0) & d.close_total.notna()]


new = pd.read_parquet(ROOT / "cfb-weather/data/processed/games.parquet")
old = pd.read_parquet(io.BytesIO(git_show(f"{REBUILD}^", "cfb-weather/data/processed/games.parquet")))


def both_acad(d):
    return d[d.home_team.isin(ACAD) & d.away_team.isin(ACAD)]


# ---- Task 2: all academy-vs-academy games, with what the rebuild did to each
cols = ["game_id", "season", "week", "season_type", "start_utc", "home_team", "away_team", "neutral_site",
        "close_total", "open_total", "pin_total", "n_books", "home_spread", "total", "result"]
a_new, a_old = both_acad(new), both_acad(old)
in_new = set(screen_filter(a_new).game_id)
in_old = set(screen_filter(a_old).game_id)
g = a_new[a_new.season.between(2006, 2025)][cols].copy()
g = g.merge(a_old[["game_id", "close_total", "open_total", "home_spread"]].rename(
    columns={"close_total": "close_total_old", "open_total": "open_total_old", "home_spread": "home_spread_old"}), on="game_id", how="left")
g["in_screen_now"] = g.game_id.isin(in_new)
g["in_screen_before"] = g.game_id.isin(in_old)


def why(r):
    if r.in_screen_now and r.in_screen_before:
        return "in both" + ("; close total changed" if r.close_total != r.close_total_old else "")
    if r.in_screen_now:
        return "ADDED by rebuild: home_spread was missing, now filled" if pd.isna(r.home_spread_old) else "ADDED by rebuild"
    if pd.isna(r.close_total):
        return "no closing total"
    if pd.isna(r.home_spread):
        return "no spread even now"
    if r.home_spread == 0:
        return "pick'em (spread 0), excluded by the screen's filter"
    return "not in screen"


g["status"] = g.apply(why, axis=1)

# second source: cfbd multi-book lines, 2014-25 (median across providers, at whatever time cfbd snapshotted)
lines = pd.read_parquet(ROOT / "cfb-weather/data/processed/cfbd_lines.parquet")
lm = lines.groupby("game_id").agg(cfbd_median_total=("total", "median"), cfbd_books=("total", "count"),
                                  cfbd_median_open=("total_open", "median")).reset_index()
g = g.merge(lm, on="game_id", how="left")
g["cfbd_diff"] = g.cfbd_median_total - g.close_total
g["final_total"] = g.total
g["under_close"] = np.where(g.final_total < g.close_total, "U", np.where(g.final_total > g.close_total, "O", "P"))
g["under_open"] = np.where(g.open_total.isna(), "", np.where(g.final_total < g.open_total, "U", np.where(g.final_total > g.open_total, "O", "P")))
g["margin_under_close"] = g.close_total - g.final_total
g["era"] = pd.cut(g.season, [2005, 2015, 2020, 2025], labels=["2006–15", "2016–20", "2021–25"])
g = g.sort_values("start_utc")
gcols = ["season", "week", "start_utc", "home_team", "away_team", "neutral_site", "close_total", "close_total_old", "open_total",
         "cfbd_median_total", "cfbd_books", "final_total", "margin_under_close", "under_close", "under_open", "home_spread",
         "home_spread_old", "in_screen_before", "in_screen_now", "status", "game_id", "era"]
g[gcols].to_csv(OUT / "academy_games.csv", index=False)

lg = []
P = lg.append
P("Issue #54: academy vs academy -> under, the 59 games\n")
sc = g[g.in_screen_now]
w, l, p_ = int((sc.under_close == "U").sum()), int((sc.under_close == "O").sum()), int((sc.under_close == "P").sum())
P(f"Games in the screen now: {len(sc)} ({w}-{l}-{p_}); before the rebuild: {int(g.in_screen_before.sum())} "
  f"({int(((g.in_screen_before) & (g.under_close == 'U')).sum())}-{int(((g.in_screen_before) & (g.under_close == 'O')).sum())})")
P(f"One-sided p vs break-even {BE:.4f}, now: {stats.binomtest(w, w + l, BE, alternative='greater').pvalue:.6f}\n")
P("Status of every academy-vs-academy game 2006-2025 that exists in the table:")
P(g.status.value_counts().to_string())
P("")
add = g[g.status.str.startswith("ADDED")]
P(f"The {len(add)} games the rebuild ADDED: {int((add.under_close == 'U').sum())}-{int((add.under_close == 'O').sum())}-{int((add.under_close == 'P').sum())} "
  f"(mean closing total {add.close_total.mean():.1f}, mean margin under {add.margin_under_close.mean():.1f})")
kept = g[g.in_screen_before & g.in_screen_now]
P(f"The {len(kept)} games in both: {int((kept.under_close == 'U').sum())}-{int((kept.under_close == 'O').sum())}-{int((kept.under_close == 'P').sum())}")
ch = kept[kept.close_total != kept.close_total_old]
P(f"Games in both whose closing total changed in the rebuild: {len(ch)}")
P("")
oc = g[g.close_total.notna() & g.home_spread.isna()]
P(f"Games with a closing total but still no spread: {len(oc)}")
allc = g[g.close_total.notna()]
P(f"ALL academy-vs-academy games with a closing total, whatever the spread (drops the spread filter): "
  f"{int((allc.under_close == 'U').sum())}-{int((allc.under_close == 'O').sum())}-{int((allc.under_close == 'P').sum())} of {len(allc)}\n")

# ---- Task 3 and 4: eras, average close, margin under, opener
rows = []
for era, d in list(sc.groupby("era", observed=True)) + [("2006–25", sc)]:
    w, l = int((d.under_close == "U").sum()), int((d.under_close == "O").sum())
    do = d[d.open_total.notna()]
    wo, lo = int((do.under_open == "U").sum()), int((do.under_open == "O").sum())
    rows.append(dict(era=era, games=len(d), under=w, over=l, push=int((d.under_close == "P").sum()), win_pct=w / (w + l),
                     p_vs_breakeven=stats.binomtest(w, w + l, BE, alternative="greater").pvalue,
                     mean_close_total=d.close_total.mean(), mean_final_total=d.final_total.mean(),
                     mean_margin_under=d.margin_under_close.mean(), open_games=len(do), open_under=wo, open_over=lo,
                     open_win_pct=wo / (wo + lo) if wo + lo else np.nan,
                     open_p_vs_breakeven=stats.binomtest(wo, wo + lo, BE, alternative="greater").pvalue if wo + lo else np.nan,
                     mean_open_total=do.open_total.mean() if len(do) else np.nan))
er = pd.DataFrame(rows)
er.to_csv(OUT / "academy_eras.csv", index=False)
P("By era (screen's 59 games; openers where the table has one):")
P(er.round(4).to_string(index=False))
P("")
by_s = sc.groupby("season").agg(games=("game_id", "size"), under=("under_close", lambda s: (s == "U").sum()), close=("close_total", "mean"), final=("final_total", "mean"))
P("By season:")
P(by_s.round(1).to_string())
P("")
P("Rank correlation of closing total with season, screen games: %.3f (p = %.3f)" % stats.spearmanr(sc.season, sc.close_total))
P("Rank correlation of closing total with season, ALL college games with a closing total: %.3f" % stats.spearmanr(
    new[new.close_total.notna() & new.season.between(2006, 2025)].season, new[new.close_total.notna() & new.season.between(2006, 2025)].close_total)[0])
P("")

# ---- Army-Navy vs the other pairings (one Army-Navy game a season is most of the sample)
an = sc[sc.home_team.isin(["Army", "Navy"]) & sc.away_team.isin(["Army", "Navy"])]
rest = sc[~sc.game_id.isin(an.game_id)]
for lab, d in (("Army-Navy", an), ("Air Force vs Army or Navy", rest)):
    w, l = int((d.under_close == "U").sum()), int((d.under_close == "O").sum())
    P(f"{lab}: {len(d)} games, {w}-{l}-{len(d) - w - l} at the close, one-sided p vs break-even {stats.binomtest(w, w + l, BE, alternative='greater').pvalue:.4f}; "
      f"mean close {d.close_total.mean():.1f}, mean final {d.final_total.mean():.1f}")
P(f"Army-Navy games among the {len(add)} added: {int(add.game_id.isin(an.game_id).sum())}")
P("")

# ---- Second source
cf = sc[sc.cfbd_median_total.notna()]
P(f"Second source (cfbd multi-book median total, 2014-25): {len(cf)} of {len(sc)} screen games have one.")
P(f"  cfbd minus table close: mean {cf.cfbd_diff.mean():.2f}, mean abs {cf.cfbd_diff.abs().mean():.2f}, max abs {cf.cfbd_diff.abs().max():.1f}, "
  f"differ by >= 1: {int((cf.cfbd_diff.abs() >= 1).sum())}")
cu = cf[cf.final_total != cf.cfbd_median_total]
P(f"  graded on cfbd total instead: {int((cu.final_total < cu.cfbd_median_total).sum())}-{int((cu.final_total > cu.cfbd_median_total).sum())} "
  f"(table close on the same games: {int((cf.under_close == 'U').sum())}-{int((cf.under_close == 'O').sum())})")
pin = sc[sc.pin_total.notna()]
P(f"  Pinnacle total in the table: {len(pin)} games; graded on it: "
  f"{int((pin.final_total < pin.pin_total).sum())}-{int((pin.final_total > pin.pin_total).sum())}")
P("")

# ---- Screen row changes (task 1)
oldscr = pd.read_csv(io.BytesIO(git_show(SCREEN_COMMIT, "strategy-research/output/screens.csv")))
newscr = pd.read_csv(OUT / "screens.csv")
k = ["screen", "thesis", "era"]
m = oldscr.merge(newscr, on=k, suffixes=("_old", "_new"))
mv = m[(m.bets_old != m.bets_new) | (m.wins_old != m.wins_new)]
mv[k + ["wins_old", "bets_old", "win_pct_old", "p_vs_breakeven_old", "wins_new", "bets_new", "win_pct_new", "p_vs_breakeven_new"]].to_csv(
    OUT / "academy_screen_row_changes.csv", index=False)
P(f"Screen rows that moved when the table was rebuilt: {len(mv)} of {len(m)} (all CFB); every NFL row and every other row is unchanged.")
(OUT / "academy_check.log").write_text("\n".join(lg) + "\n")
print("\n".join(lg))
