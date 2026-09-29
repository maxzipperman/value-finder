"""Free pre-checks for three backlog issues (public GitHub data only; no Odds API or other paid calls).

  #17  Favorite-longshot bias by odds band: nflverse closing moneylines, NFL 2006-25.
  #6   Part 1, crosswind vs along-field wind: stadium headings from greerreNFL/stadiums (checked
       against ThompsonJamesBliss/WeatherData), ERA5 kickoff wind direction already in games.parquet.
       Part 2 pre-check, derivative markets: nflverse play-by-play halftime scores. Does wind change
       the first-half share of points, or the favorite's margin against the spread? If not, first-half
       and team totals derived from the main line have nothing to lag, and there's nothing to buy.
  #4   Rule HT split by spread size. Descriptive only: run after Rule HT was pre-registered, so it
       can't change the rule.
  #16  Line shopping in college football, from CollegeFootballData's lines by sportsbook (2016-25):
       Rule HT and CFB Rule B (observed 15+ mph wind) graded at the best total any book posted vs the
       consensus close, and whether high totals rise from open to close (the "bet at the close" advice).
       CFBD has no over/under prices, so every book is priced at -110: this is points, not price.

Every test counts toward the running variant total, which starts at the screen's 109 (screen.py).
Seasons stop at 2025, so 2026 stays clean for forward tests.

Inputs (read-only)
  nfl-weather/data/processed/games.parquet, team_games.parquet     lines, results, weather
  cfb-weather/data/processed/games.parquet                          cfbfastR consensus lines
  cfb-weather/data/processed/cfbd_lines.parquet                     CFBD lines by sportsbook (pulled on the Mac)
  nflverse play-by-play (GitHub), read from nfl-weather/data/raw/pbp/ when cached there, otherwise
  downloaded one season at a time and summarized into strategy-research/data/ (gitignored)
  stadium headings (GitHub), cached in strategy-research/data/

Outputs: output/prechecks.csv, output/prechecks.log (console)
Run from the repo root:  nfl-weather/.venv/bin/python strategy-research/prechecks.py
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import requests
import statsmodels.formula.api as smf
from scipy import stats

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "nfl-weather"))

from nflweather.market import american_to_prob, american_to_profit  # noqa: E402

OUT = Path(__file__).resolve().parent / "output"
CACHE = Path(__file__).resolve().parent / "data"
SCREEN_VARIANTS = 109
PBP_URL = "https://github.com/nflverse/nflverse-data/releases/download/pbp/play_by_play_{season}.parquet"
HEADINGS = {
    "greerre": "https://raw.githubusercontent.com/greerreNFL/stadiums/main/data/stadiums.csv",
    "bliss": "https://raw.githubusercontent.com/ThompsonJamesBliss/WeatherData/master/data/stadium_coordinates.csv",
}
rows = []


def record(issue, test, subset, n, estimate, se=np.nan, p=np.nan, note=""):
    rows.append(dict(issue=issue, test=test, subset=subset, n=int(n), estimate=estimate, se=se, p=p, note=note))


def fetch(url, dest):
    if not dest.exists():
        dest.parent.mkdir(parents=True, exist_ok=True)
        r = requests.get(url, timeout=120)
        r.raise_for_status()
        dest.write_bytes(r.content)
    return dest


# ---------------------------------------------------------------- data
g = pd.read_parquet(ROOT / "nfl-weather/data/processed/games.parquet")
g = g[g.result.notna() & g.season.between(1999, 2025)].copy()
g["outdoor"] = g.wx_src.isin(["gamebook", "era5"])

# ---------------------------------------------------------------- #17 favorite-longshot bias
m = g[g.season.between(2006, 2025) & g.home_moneyline.notna() & g.away_moneyline.notna() & (g.result != 0)]
ph, pa = american_to_prob(m.home_moneyline), american_to_prob(m.away_moneyline)
sides = pd.concat([
    pd.DataFrame(dict(season=m.season, p=ph / (ph + pa), won=m.result > 0, profit=american_to_profit(m.home_moneyline))),
    pd.DataFrame(dict(season=m.season, p=pa / (ph + pa), won=m.result < 0, profit=american_to_profit(m.away_moneyline))),
], ignore_index=True)
sides["profit"] = np.where(sides.won, sides.profit, -1.0)
sides["band"] = pd.cut(sides.p, [0, 0.20, 0.35, 0.5000001, 1], labels=["dog <20%", "dog 20-35%", "35-50%", "fav >50%"],
                       include_lowest=True)
for era, (a, b) in {"2006-2025": (2006, 2025), "2006-2015": (2006, 2015), "2016-2025": (2016, 2025)}.items():
    for band, d in sides[sides.season.between(a, b)].groupby("band", observed=True):
        se = d.profit.std(ddof=1) / np.sqrt(len(d))
        bias = d.won - d.p                                     # outcome minus the no-vig price: the bias itself
        record("#17", f"ROI backing this band at the consensus close, {band}", era, len(d), d.profit.mean(), se,
               stats.ttest_1samp(d.profit, 0, alternative="greater").pvalue,
               f"win {d.won.mean():.3f} vs no-vig {d.p.mean():.3f}: bias {bias.mean():+.3f} "
               f"(se {bias.std(ddof=1) / np.sqrt(len(d)):.3f})")

# ---------------------------------------------------------------- #6 part 1: crosswind vs along-field wind
gr = pd.read_csv(fetch(HEADINGS["greerre"], CACHE / "stadiums_greerre.csv"))
bl = pd.read_csv(fetch(HEADINGS["bliss"], CACHE / "stadiums_bliss.csv"))
bl = bl[bl.RoofType.str.lower() != "indoor"]


def axis_gap(a, b):
    """Difference between two field axes in degrees (an axis, so modulo 180), 0-90."""
    d = np.abs((np.asarray(a) - np.asarray(b)) % 180)
    return np.minimum(d, 180 - d)


# cross-check the two sources: nearest stadium within 2 km
km = lambda la1, lo1, la2, lo2: 111 * np.hypot(la1 - la2, (lo1 - lo2) * np.cos(np.radians(la1)))  # noqa: E731
pairs = []
for r in bl.itertuples():
    d = km(r.Latitude, r.Longitude, gr.lat.to_numpy(), gr.lon.to_numpy())
    if d.min() < 2:
        pairs.append(dict(stadium=r.StadiumName, stadium_id=gr.stadium_id.iloc[d.argmin()],
                          gap=float(axis_gap(r.StadiumAzimuthAngle, gr.heading.iloc[d.argmin()]))))
pairs = pd.DataFrame(pairs)
record("#6", "heading agreement between sources (degrees, median)", "outdoor stadiums in both", len(pairs),
       pairs.gap.median(), note=f"max {pairs.gap.max():.0f} deg; > 15 deg at {int((pairs.gap > 15).sum())} stadiums: "
       + ", ".join(pairs[pairs.gap > 15].stadium))
bad = set(pairs[pairs.gap > 15].stadium_id)                    # sources disagree: leave those stadiums out

w = g[g.outdoor & g.om_wind_dir.notna() & g.wx_wind.notna() & g.total_line.notna()].merge(
    gr[["stadium_id", "heading", "lat", "lon"]].rename(columns={"lat": "s_lat", "lon": "s_lon"}), on="stadium_id", how="inner")
w = w[~w.stadium_id.isin(bad)].copy()
w["angle"] = axis_gap(w.om_wind_dir, w.heading)                  # 0 = straight down the field, 90 = straight across
w["along"] = w.wx_wind * np.cos(np.radians(w.angle))
w["cross"] = w.wx_wind * np.sin(np.radians(w.angle))
w["resid"] = w.total - w.total_line
fit = smf.ols("resid ~ along + cross", data=w).fit(cov_type="HC1")
diff = fit.t_test("cross - along = 0")
record("#6", "total - closing total per mph: crosswind minus along-field", "outdoor 1999-2025", len(w),
       float(diff.effect[0]), float(diff.sd[0][0]), float(diff.pvalue),
       f"along {fit.params.along:+.3f} (se {fit.bse.along:.3f}), cross {fit.params.cross:+.3f} (se {fit.bse.cross:.3f})")
windy = w[w.wx_wind >= 15]
for lab, d in {"mostly across (angle >= 45)": windy[windy.angle >= 45],
               "mostly along (angle < 45)": windy[windy.angle < 45]}.items():
    dd = d[d.resid != 0]
    wins = int((dd.resid < 0).sum())
    record("#6", f"under vs the close, wind >= 15 mph, {lab}", "outdoor 1999-2025", len(dd), wins / len(dd),
           p=stats.binomtest(wins, len(dd), 110 / 210, alternative="greater").pvalue,
           note=f"{wins}-{len(dd) - wins}; mean total - close {d.resid.mean():+.2f}")
t = pd.read_parquet(ROOT / "nfl-weather/data/processed/team_games.parquet", columns=["game_id", "team", "pass_att", "net_pass_yds", "ypa"])
tw = t.merge(w[["game_id", "along", "cross", "season"]], on="game_id")
tw = tw[tw.pass_att >= 10]
pf = smf.ols("ypa ~ along + cross + C(season)", data=tw).fit(cov_type="cluster", cov_kwds={"groups": tw.game_id.astype("category").cat.codes})
pdiff = pf.t_test("cross - along = 0")
record("#6", "yards per pass attempt per mph: crosswind minus along-field", "team-games 1999-2025", len(tw),
       float(pdiff.effect[0]), float(pdiff.sd[0][0]), float(pdiff.pvalue),
       f"along {pf.params.along:+.3f} (se {pf.bse.along:.3f}), cross {pf.params.cross:+.3f} (se {pf.bse.cross:.3f}); "
       "season fixed effects, game-clustered SEs")

# ---------------------------------------------------------------- #6 part 2 pre-check: halftime split
def halftime(season):
    cached = CACHE / "halftime" / f"{season}.parquet"
    if cached.exists():
        return pd.read_parquet(cached)
    local = ROOT / "nfl-weather/data/raw/pbp" / f"play_by_play_{season}.parquet"
    tmp = None
    if not local.exists():
        tmp = CACHE / "halftime" / f"pbp_{season}.parquet"
        fetch(PBP_URL.format(season=season), tmp)
        local = tmp
    p = pd.read_parquet(local, columns=["game_id", "qtr", "total_home_score", "total_away_score"])
    h = p[p.qtr <= 2].groupby("game_id")[["total_home_score", "total_away_score"]].max()
    h = h.rename(columns={"total_home_score": "h1_home", "total_away_score": "h1_away"}).reset_index()
    cached.parent.mkdir(parents=True, exist_ok=True)
    h.to_parquet(cached, index=False)
    if tmp is not None:
        tmp.unlink()
    return h


ht = pd.concat([halftime(s) for s in range(2006, 2026)], ignore_index=True)
hg = g[g.outdoor & g.season.between(2006, 2025) & (g.total > 0) & g.spread_line.notna() & (g.spread_line != 0)].merge(ht, on="game_id")
hg["h1_share"] = (hg.h1_home + hg.h1_away) / hg.total
hg["fav_resid"] = np.where(hg.spread_line > 0, hg.result, -hg.result) - hg.spread_line.abs()   # favorite's margin vs spread
for col, lab in (("h1_share", "first-half share of points"), ("fav_resid", "favorite's margin minus the spread")):
    f = smf.ols(f"{col} ~ wx_wind", data=hg).fit(cov_type="HC1")
    calm, windy15 = hg[hg.wx_wind < 10][col], hg[hg.wx_wind >= 15][col]
    record("#6", f"{lab}, per mph of wind", "outdoor 2006-2025", len(hg), f.params.wx_wind, f.bse.wx_wind,
           f.pvalues.wx_wind, f"calm (< 10 mph) {calm.mean():.3f} (n {len(calm)}), 15+ mph {windy15.mean():.3f} "
           f"(n {len(windy15)})")

# ---------------------------------------------------------------- #4 Rule HT by spread size (descriptive)
c = pd.read_parquet(ROOT / "cfb-weather/data/processed/games.parquet")
c = c[c.result.notna() & c.home_spread.notna() & c.season.between(2006, 2025) & (c.home_spread != 0) & c.close_total.notna()]
prev = c.groupby("season").close_total.mean().shift(1)
hi = c[(c.close_total >= c.season.map(prev) + 10) & c.season.between(2016, 2025)]
for lab, d in {"spread >= 14": hi[hi.home_spread.abs() >= 14], "spread < 14": hi[hi.home_spread.abs() < 14]}.items():
    dd = d[d.total != d.close_total]
    wins = int((dd.total < dd.close_total).sum())
    record("#4", f"Rule HT under vs the close, {lab}", "CFB 2016-2025", len(dd), wins / len(dd),
           p=stats.binomtest(wins, len(dd), 110 / 210, alternative="greater").pvalue, note=f"{wins}-{len(dd) - wins}")

# ---------------------------------------------------------------- #16 line shopping, CFB (CFBD lines by book)
AGGREGATORS = {"consensus", "numberfire", "teamrankings"}          # not bettable books
bk = pd.read_parquet(ROOT / "cfb-weather/data/processed/cfbd_lines.parquet")
bk = bk[~bk.provider.isin(AGGREGATORS) & bk.total.notna()]
best = bk.groupby("game_id").agg(best_total=("total", "max"), books=("provider", "nunique")).reset_index()
cc = c.merge(best, on="game_id", how="inner")                        # c: the screen's CFB set, 2006-25
cc = cc[cc.season.between(2016, 2025) & (cc.books >= 2)]
sets = {"Rule HT (total >= prior-season mean + 10)": cc[cc.close_total >= cc.season.map(prev) + 10],
        "CFB Rule B (observed wind >= 15, outdoor)": cc[(cc.wx_src == "station") & (cc.wx_wind >= 15)]}
for lab, d in sets.items():
    for line, col in (("consensus close", "close_total"), ("best book", "best_total")):
        dd = d[d.total != d[col]]
        wins = int((dd.total < dd[col]).sum())
        record("#16", f"{lab}: under at the {line}", "CFB 2016-2025, games with 2+ books", len(dd), wins / len(dd),
               p=stats.binomtest(wins, len(dd), 110 / 210, alternative="greater").pvalue,
               note=f"{wins}-{len(dd) - wins}; best book beats consensus by {(d.best_total - d.close_total).mean():+.2f} "
                    f"pts on average ({(d.best_total > d.close_total).mean():.0%} of games), mean {d.books.mean():.1f} books"
               if line == "best book" else f"{wins}-{len(dd) - wins}")
op = bk[bk.total_open.notna()].merge(sets["Rule HT (total >= prior-season mean + 10)"][["game_id"]], on="game_id")
mv = op.total - op.total_open
record("#16", "Rule HT: total move from the book's open to its close", "CFB 2016-2025, books with an opener", len(op),
       mv.mean(), mv.std(ddof=1) / np.sqrt(len(op)), stats.ttest_1samp(mv, 0).pvalue,
       f"rose in {(mv > 0).mean():.0%}, fell in {(mv < 0).mean():.0%}; providers {sorted(op.provider.unique())}")

# ---------------------------------------------------------------- output
res = pd.DataFrame(rows)
tests = res[~res.test.str.startswith("heading agreement")]
total = SCREEN_VARIANTS + len(tests)
res.to_csv(OUT / "prechecks.csv", index=False)
pd.set_option("display.width", 250, "display.max_colwidth", 140)
print(res.round(4).to_string(index=False))
print(f"\nNew variants: {len(tests)}. Running total with the screen: {total}. Bonferroni bar: p < {0.05 / total:.5f}.")
