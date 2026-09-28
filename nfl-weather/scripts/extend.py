"""Step 3: the extended model.

Team-game regressions, 1999-2025, with
  * offense team-season and defense team-season fixed effects (team quality
    changes every year; the thesis used franchise + season effects),
  * week-of-season fixed effects, identified off dome games, so "December"
    is not confused with "cold",
  * domes as their own category rather than 72F/calm,
  * wind and temperature bins, plus rain and snow (ERA5),
  * standard errors clustered by game (both offenses share the weather),
  * modern outcomes: EPA/dropback, CPOE, air yards, pass rate over expected.

Also: era split, home vs visitor, climate acclimation, and field goals.
Outputs: output/tables/ext_*.csv, kicking_*.csv
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

from nflweather.config import PROC, TABLES
from nflweather.features import BIN_TERMS, add_weather_features
from nflweather.models import fit, fit_many

OUTCOMES = {  # column: (label, multiplier to display units, first season available)
    "epa_db": ("EPA per dropback", 1, 1999),
    "succ_db": ("Dropback success rate (pts)", 100, 1999),
    "ypa": ("Yards per pass attempt", 1, 1999),
    "cmp_pct": ("Completion % (pts)", 100, 1999),
    "cpoe": ("CPOE (pts)", 1, 2006),
    "adot": ("Avg depth of target (yds)", 1, 2006),
    "deep_rate": ("Deep-pass share, 20+ air yds (pts)", 100, 2006),
    "sack_rate": ("Sack rate (pts)", 100, 1999),
    "int_rate": ("INT rate (pts)", 100, 1999),
    "proe": ("Pass rate over expected (pts)", 1, 2006),
    "pass_att": ("Pass attempts", 1, 1999),
    "rush_att": ("Rush attempts", 1, 1999),
    "epa_run": ("EPA per designed run", 1, 1999),
    "rush_ypa": ("Yards per carry", 1, 1999),
    "pass_yds": ("Passing yards", 1, 1999),
    "rush_yds": ("Rushing yards", 1, 1999),
    "pts": ("Points scored", 1, 1999),
    "fumbles": ("Fumbles", 1, 1999),
}
FE = ["team_season", "opp_season", "week_fe"]
VC = {"CRV1": "game_id"}
CTRL = ["home_site", "neutral", "playoff"]


def prep():
    tg = pd.read_parquet(PROC / "team_games.parquet")
    d = add_weather_features(tg[tg.season.between(1999, 2025)])
    d["team_season"] = d.franchise + "_" + d.season.astype(str)
    d["opp_season"] = d.opp_franchise + "_" + d.season.astype(str)
    d["week_fe"] = d.week.astype(str)
    d["home_site"] = d.home * (1 - d.neutral)
    d["away_site"] = (1 - d.home) * (1 - d.neutral)
    for c, (_, mult, _) in OUTCOMES.items():
        d[c] = d[c] * mult
    return d


def main_effects(d):
    rows = []
    for y, (label, _, first) in OUTCOMES.items():
        t = fit(d[d.season >= first], y, BIN_TERMS + CTRL, FE, VC)
        t["label"] = label
        t["baseline"] = d.loc[(d.outdoor == 1) & (d[BIN_TERMS].sum(axis=1) == 0) & (d.season >= first), y].mean()
        rows.append(t)
    r = pd.concat(rows, ignore_index=True)
    r.to_csv(TABLES / "ext_main_effects.csv", index=False)
    return r


def ppml_pct(d):
    """Percent effects (Poisson PML) for yardage/points, comparable to the thesis's log models."""
    d = d.assign(pass_yds=d.pass_yds.clip(lower=0))  # a handful of games have net-negative completions
    r = fit_many(d, ["pass_yds", "rush_att", "pass_att", "pts"], BIN_TERMS + CTRL, FE, VC, method="pois")
    r["pct"] = np.expm1(r.coef) * 100
    r["pct_lo"], r["pct_hi"] = np.expm1(r.lo) * 100, np.expm1(r.hi) * 100
    r.to_csv(TABLES / "ext_ppml_pct.csv", index=False)
    return r


def by_era(d):
    rows = []
    for era, (a, b) in {"1999–2013": (1999, 2013), "2014–2025": (2014, 2025)}.items():
        for y in ["epa_db", "pass_yds", "cmp_pct", "cpoe", "proe", "rush_att", "pts"]:
            first = OUTCOMES[y][2]
            s = d[d.season.between(max(a, first), b)]
            t = fit(s, y, BIN_TERMS + CTRL, FE, VC)
            t["era"], t["label"] = era, OUTCOMES[y][0]
            rows.append(t)
    r = pd.concat(rows, ignore_index=True)
    r.to_csv(TABLES / "ext_by_era.csv", index=False)
    return r


def home_vs_away(d):
    """Does the visitor suffer more? Weather x visitor interactions."""
    inter = []
    for c in ["wind_15_19", "wind_20p", "temp_le32", "rain", "snow"]:
        d[f"{c}_x_away"] = d[c] * d.away_site
        inter.append(f"{c}_x_away")
    rows = []
    for y in ["epa_db", "pass_yds", "cmp_pct", "pts"]:
        t = fit(d, y, BIN_TERMS + inter + CTRL + ["away_site"], FE, VC)
        t["label"] = OUTCOMES[y][0]
        rows.append(t)
    r = pd.concat(rows, ignore_index=True)
    r.to_csv(TABLES / "ext_home_away.csv", index=False)
    return r


def acclimation(d):
    """Cold-game effect by who you are: home team vs visitors grouped by their
    home climate over the prior week (dome, warm >=60F, temperate 40-60F, cold <40F)."""
    v = d.away_site == 1
    grp = np.select(
        [~v, v & (d.dome_team == 1), v & (d.city_tavg7 >= 60), v & (d.city_tavg7 >= 40), v & (d.city_tavg7 < 40)],
        ["home", "visitor_dome", "visitor_warm", "visitor_temperate", "visitor_cold"], "other")
    terms = []
    for gname in ["home", "visitor_dome", "visitor_warm", "visitor_temperate", "visitor_cold"]:
        col = f"cold_x_{gname}"
        d[col] = d.temp_le32 * (grp == gname)
        terms.append(col)
    base = [t for t in BIN_TERMS if t != "temp_le32"]
    rows = []
    for y in ["epa_db", "pass_yds", "cmp_pct", "ypa", "pts"]:
        t = fit(d, y, base + terms + CTRL + ["away_site"], FE, VC)
        t["label"] = OUTCOMES[y][0]
        rows.append(t)
    r = pd.concat(rows, ignore_index=True)
    counts = pd.Series(grp[d.temp_le32 == 1]).value_counts()
    r["n_cold_games_group"] = r.term.str.replace("cold_x_", "").map(counts)
    r.to_csv(TABLES / "ext_acclimation.csv", index=False)
    return r


def kicking():
    k = pd.read_parquet(PROC / "kicks.parquet")
    fg = add_weather_features(k[(k.kind == "fg") & k.season.between(1999, 2025) & k.kick_distance.between(18, 70)])
    fg["altitude"] = fg.stadium_key.isin(["DEN00", "DEN99", "MEX00"]).astype(int)
    terms = " + ".join(BIN_TERMS)
    m = smf.logit(f"made ~ cr(kick_distance, df=5) + {terms} + altitude + C(season)", data=fg).fit(
        disp=0, cov_type="cluster", cov_kwds={"groups": pd.factorize(fg.game_id)[0]})
    coefs = pd.DataFrame({"coef": m.params, "se": m.bse, "p": m.pvalues}).loc[BIN_TERMS + ["altitude"]]
    coefs.to_csv(TABLES / "kicking_logit.csv")
    # predicted make % grid (2025 kicking environment)
    scen = {"Calm, 46–79°F, dry": {}, "Wind 10–14": {"wind_10_14": 1}, "Wind 15–19": {"wind_15_19": 1},
            "Wind 20+": {"wind_20p": 1}, "≤32°F": {"temp_le32": 1}, "Rain": {"rain": 1}, "Snow": {"snow": 1},
            "Dome": {"indoor": 1}, "Wind 20+ & ≤32°F": {"wind_20p": 1, "temp_le32": 1}}
    grid = []
    for name, on in scen.items():
        for dist in [30, 40, 45, 50, 55]:
            row = {t: 0 for t in BIN_TERMS} | on | {"kick_distance": dist, "altitude": 0, "season": 2025}
            grid.append(dict(scenario=name, distance=dist, make_pct=100 * float(m.predict(pd.DataFrame([row])).iloc[0])))
    grid = pd.DataFrame(grid)
    grid.to_csv(TABLES / "kicking_grid.csv", index=False)
    # attempt rates: do teams avoid long kicks in wind? share of FG attempts >= 50 yds
    fg["long"] = (fg.kick_distance >= 50).astype(int)
    lr = fg.groupby(pd.cut(fg.wx_wind.where(fg.outdoor == 1), [-1, 9.99, 14.99, 19.99, 99],
                           labels=["<10", "10–14", "15–19", "20+"]), observed=True).agg(
        attempts=("made", "size"), make_pct=("made", "mean"), long_share=("long", "mean"), avg_dist=("kick_distance", "mean"))
    lr.to_csv(TABLES / "kicking_by_wind.csv")
    return coefs, grid, lr, len(fg)


if __name__ == "__main__":
    pd.set_option("display.width", 220)
    d = prep()
    print(f"team-games: {len(d):,}  outdoor share {d.outdoor.mean():.2f}")
    for c in BIN_TERMS:
        print(f"  {c:12s} {int(d[c].sum()):>6} team-games")
    me = main_effects(d)
    piv = me[me.term.isin(BIN_TERMS)].pivot_table(index="label", columns="term", values="coef", sort=False)[BIN_TERMS]
    print("\nMain effects (vs outdoor, calm <10 mph, 46–79°F, dry):\n", piv.round(2).to_string())
    pp = ppml_pct(d)
    print("\nPercent effects (PPML):\n", pp[pp.term.isin(BIN_TERMS)].pivot_table(index="outcome", columns="term", values="pct", sort=False)[BIN_TERMS].round(1).to_string())
    era = by_era(d)
    print("\nBy era (wind 20+, ≤32°F, snow):\n", era[era.term.isin(["wind_15_19", "wind_20p", "temp_le32", "rain", "snow"])].pivot_table(index=["label", "era"], columns="term", values="coef", sort=False).round(2).to_string())
    ha = home_vs_away(d)
    print("\nVisitor extra effect (x_away):\n", ha[ha.term.str.endswith("_x_away")].pivot_table(index="label", columns="term", values="coef").round(2).to_string())
    ac = acclimation(d)
    print("\nCold-game (≤32°F) effect by group:\n", ac[ac.term.str.startswith("cold_x_")].pivot_table(index="term", columns="label", values="coef").round(2).to_string())
    print(ac[ac.term.str.startswith("cold_x_") & (ac.outcome == "epa_db")][["term", "coef", "se", "p", "n_cold_games_group"]].round(3).to_string(index=False))
    coefs, grid, lr, n = kicking()
    print(f"\nField goals (n={n:,}) logit coefficients:\n", coefs.round(3).to_string())
    print(grid.pivot(index="scenario", columns="distance", values="make_pct").round(1).to_string())
    print(lr.round(3).to_string())
