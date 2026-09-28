"""Audit of the 2014 model: start from the exact thesis specification and apply
one fix at a time, on the thesis's own seasons (2002-2013), so each change in
the headline numbers can be attributed to a specific fix. Then: how much of
the game-to-game variation does weather actually explain?

Outputs: output/tables/audit_ladder.csv, audit_home.csv, audit_strength.csv
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd
import pyfixest as pf

from nflweather.config import PROC, TABLES
from nflweather.features import add_weather_features
from nflweather.models import fit, safe_log

SEASONS = (2002, 2013)


def prep(seasons=SEASONS):
    tg = pd.read_parquet(PROC / "team_games.parquet")
    d = add_weather_features(tg[tg.season.between(*seasons)])
    d["ln_pass_yds"] = safe_log(d.pass_yds)
    d["ln_cmp_pct"] = safe_log(d.cmp_pct)
    d["ln_rush_yds"] = safe_log(d.rush_yds)
    # thesis variables: wind chill, domes = 72F / 0 mph
    d["temp"], d["wind"], d["freezing"], d["hot"] = d.th_wchill, d.th_wind, d.th_freezing, d.th_hot
    for v in ["temp", "wind", "freezing", "hot"]:
        d[f"home_{v}"] = d.home * d[v]
    # centered versions: home = +/-0.5, temperature relative to 60F
    d["home_c"] = d.home - 0.5
    d["temp_c"] = d.temp - 60
    for v, src in [("temp", "temp_c"), ("wind", "wind"), ("freezing", "freezing"), ("hot", "hot")]:
        d[f"homec_{v}"] = d.home_c * d[src]
    # outdoor-only weather: indoor games sit at the reference (60F, calm) with their own dummy
    out = d.outdoor
    d["o_wchill_c"] = out * (d.wx_wchill.fillna(60) - 60)
    d["o_air_c"] = out * (d.wx_temp.fillna(60) - 60)
    d["o_wind"] = out * d.wx_wind.fillna(0)
    d["o_freezing_wc"] = out * (d.wx_wchill <= 32).astype(int)
    d["o_freezing_air"] = out * (d.wx_temp <= 32).astype(int)
    d["o_hot"] = out * (d.wx_temp >= 80).astype(int)
    d["team_season"] = d.franchise + "_" + d.season.astype(str)
    d["opp_season"] = d.opp_franchise + "_" + d.season.astype(str)
    d["week_fe"] = d.week.astype(str)
    return d


FRANCHISE_FE = ["franchise", "opp_franchise", "season"]
TS_FE = ["team_season", "opp_season"]
TS_WEEK_FE = ["team_season", "opp_season", "week_fe"]
CL = {"CRV1": "game_id"}

LADDER = [
    # (step label, what changed, regressors, wind term, temp term, FE, vcov)
    ("0. Thesis specification", "Your Table 5, rebuilt data",
     ["temp", "wind", "freezing", "hot", "home", "home_temp", "home_wind", "home_freezing", "home_hot"],
     "wind", "temp", FRANCHISE_FE, "hetero"),
    ("1. Center the interactions", "Home coded ±½ and temperature measured from 60°F, so the main effects describe an average team in a normal game",
     ["temp_c", "wind", "freezing", "hot", "home_c", "homec_temp", "homec_wind", "homec_freezing", "homec_hot"],
     "wind", "temp_c", FRANCHISE_FE, "hetero"),
    ("2. Cluster by game", "Both offenses in a game share its weather; standard errors account for that",
     ["temp_c", "wind", "freezing", "hot", "home_c", "homec_temp", "homec_wind", "homec_freezing", "homec_hot"],
     "wind", "temp_c", FRANCHISE_FE, CL),
    ("3. Domes as their own category", "Weather slopes come from outdoor games only; domes and retractable roofs get dummies instead of 72°F and calm",
     ["o_wchill_c", "o_wind", "o_freezing_wc", "o_hot", "indoor", "roof_open", "home_c"],
     "o_wind", "o_wchill_c", FRANCHISE_FE, CL),
    ("4. Air temperature, not wind chill", "Wind no longer enters twice, so the wind coefficient is the whole wind effect",
     ["o_air_c", "o_wind", "o_freezing_air", "o_hot", "indoor", "roof_open", "home_c"],
     "o_wind", "o_air_c", FRANCHISE_FE, CL),
    ("5. Team-season fixed effects", "Each team's offense and defense get a new baseline every season",
     ["o_air_c", "o_wind", "o_freezing_air", "o_hot", "indoor", "roof_open", "home_c"],
     "o_wind", "o_air_c", TS_FE, CL),
    ("6. Week of season + playoffs", "December and January are compared with other games in the same week, using dome games as the benchmark",
     ["o_air_c", "o_wind", "o_freezing_air", "o_hot", "indoor", "roof_open", "home_c", "playoff"],
     "o_wind", "o_air_c", TS_WEEK_FE, CL),
    ("7. Add rain and snow", "Precipitation during the game window from ERA5",
     ["o_air_c", "o_wind", "o_freezing_air", "o_hot", "rain", "snow", "indoor", "roof_open", "home_c", "playoff"],
     "o_wind", "o_air_c", TS_WEEK_FE, CL),
]


def ladder(d, outcomes=("ln_pass_yds", "ln_cmp_pct")):
    rows = []
    for label, what, x, wterm, tterm, fe, vc in LADDER:
        for y in outcomes:
            t = fit(d, y, x, fe, vc).set_index("term")
            w, tm = t.loc[wterm], t.loc[tterm]
            rows.append(dict(step=label, change=what, outcome=y, n=int(t.n.iloc[0]),
                             wind_pct=1000 * w.coef, wind_lo=1000 * w.lo, wind_hi=1000 * w.hi, wind_se=1000 * w.se, wind_p=w.p,
                             cold_pct=-1000 * tm.coef, cold_lo=-1000 * tm.hi, cold_hi=-1000 * tm.lo, cold_se=1000 * tm.se, cold_p=tm.p))
    r = pd.DataFrame(rows)
    r.to_csv(TABLES / "audit_ladder.csv", index=False)
    return r


def home_effect(d):
    """What the Home coefficient means with and without centering (rush yards)."""
    rows = []
    for label, x, hterm in [
        ("As estimated (home effect at 0°F, 0 mph)", LADDER[0][2], "home"),
        ("Centered (home effect at 60°F, average wind)", ["temp_c", "wind_c", "freezing", "hot", "home", "homec2_temp", "homec2_wind", "homec2_freezing", "homec2_hot"], "home"),
    ]:
        if "wind_c" in x:
            d = d.assign(wind_c=d.wind - d.wind.mean())
            d = d.assign(homec2_temp=d.home * d.temp_c, homec2_wind=d.home * d.wind_c,
                         homec2_freezing=d.home * d.freezing, homec2_hot=d.home * d.hot)
        for y in ["ln_rush_yds", "ln_pass_yds"]:
            t = fit(d, y, x, FRANCHISE_FE, "hetero").set_index("term").loc[hterm]
            rows.append(dict(version=label, outcome=y, home_pct=100 * t.coef, lo=100 * t.lo, hi=100 * t.hi, p=t.p))
    r = pd.DataFrame(rows)
    r.to_csv(TABLES / "audit_home.csv", index=False)
    return r


def partial_r2(d, y, weather, controls, fe):
    cols = list(dict.fromkeys([y] + weather + controls + fe))
    s = d[cols].replace([np.inf, -np.inf], np.nan).dropna()
    full = pf.feols(f"{y} ~ {' + '.join(weather + controls)} | {' + '.join(fe)}", data=s)
    base = pf.feols(f"{y} ~ {' + '.join(controls)} | {' + '.join(fe)}", data=s)
    rss_f, rss_b = float((full.resid() ** 2).sum()), float((base.resid() ** 2).sum())
    tss = float(((s[y] - s[y].mean()) ** 2).sum())
    return dict(outcome=y, n=len(s), r2_total=1 - rss_f / tss, r2_fe_only=1 - rss_b / tss,
                partial_r2_weather=(rss_b - rss_f) / rss_b)


def strength():
    """Share of variation explained: total R2 (what the thesis reported, mostly fixed
    effects) vs the weather terms' partial R2 after the fixed effects, overall and
    among outdoor games with 15+ mph wind or freezing temperatures."""
    tg = pd.read_parquet(PROC / "team_games.parquet")
    d = add_weather_features(tg[tg.season.between(1999, 2025)])
    d["ln_pass_yds"] = safe_log(d.pass_yds)
    d["team_season"] = d.franchise + "_" + d.season.astype(str)
    d["opp_season"] = d.opp_franchise + "_" + d.season.astype(str)
    d["week_fe"] = d.week.astype(str)
    d["home_site"] = d.home * (1 - d.neutral)
    w = ["wind_10_14", "wind_15_19", "wind_20p", "temp_le32", "temp_33_45", "temp_80p", "rain", "snow", "indoor", "roof_open"]
    rows = []
    for y in ["ln_pass_yds", "epa_db", "cmp_pct", "pts"]:
        rows.append(partial_r2(d, y, w, ["home_site", "neutral", "playoff"], TS_WEEK_FE))
    # game totals vs the closing line: how much of the miss does weather explain?
    g = pd.read_parquet(PROC / "games.parquet")
    g = add_weather_features(g[g.result.notna() & g.season.between(1999, 2025)])
    g["miss"] = g.total - g.total_line
    import statsmodels.formula.api as smf
    m = smf.ols("miss ~ " + " + ".join(w), data=g).fit()
    rows.append(dict(outcome="total points − closing total", n=int(m.nobs), r2_total=m.rsquared, r2_fe_only=0.0,
                     partial_r2_weather=m.rsquared))
    r = pd.DataFrame(rows)
    r.to_csv(TABLES / "audit_strength.csv", index=False)
    return r


if __name__ == "__main__":
    pd.set_option("display.width", 250)
    pd.set_option("display.max_colwidth", 40)
    d = prep()
    lad = ladder(d)
    print(lad[["step", "outcome", "n", "wind_pct", "wind_se", "wind_p", "cold_pct", "cold_se", "cold_p"]].round(3).to_string(index=False))
    print(home_effect(d).round(3).to_string(index=False))
    print(strength().round(4).to_string(index=False))
