"""Step 1 & 2: replicate the thesis (2002-2013) with rebuilt data, then run the
identical specifications on the 12 seasons since (2014-2025) as a true
out-of-sample test.

Outputs: output/tables/replication_long.csv, replication_headlines.csv
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd
from scipy import stats

from nflweather import thesis
from nflweather.config import PROC, TABLES
from nflweather.models import fit_many, safe_log, stars

PERIODS = {"replication": (2002, 2013), "holdout": (2014, 2025)}
FE = ["franchise", "opp_franchise", "season"]


def thesis_vars(tg):
    d = tg.copy()
    d["temp"], d["wind"] = d.th_wchill, d.th_wind
    d["freezing"], d["hot"] = d.th_freezing, d.th_hot
    for v in ["temp", "wind", "freezing", "hot"]:
        d[f"home_{v}"] = d.home * d[v]
    d["ln_pass_yds"] = safe_log(d.pass_yds)
    d["ln_cmp_pct"] = safe_log(d.cmp_pct)
    d["ln_yds_per_cmp"] = safe_log(d.yds_per_cmp)
    d["ln_rush_pct"] = safe_log(d.rush_pct)
    d["ln_rush_att"] = safe_log(d.rush_att)
    d["ln_rush_yds"] = safe_log(d.rush_yds)
    d["ln_rush_ypa"] = safe_log(d.rush_ypa)
    d["ln_int_rate"] = safe_log(d.int_rate)
    d["ln_sacks"] = safe_log(d.sacks)
    d["ln_total_yds"] = safe_log(d.pass_yds + d.rush_yds)  # thesis: gross pass + rush
    d["ln_fumbles"] = safe_log(d.fumbles)
    d["ln_penalties"] = safe_log(d.penalties)
    d["ln_turnovers"] = safe_log(d.turnovers)
    # visitor acclimation segments (thesis Table 1)
    dome = d.dome_fixed == 1
    light = ~dome & (d.home_avg_wind_th < 10)
    high = ~dome & (d.home_avg_wind_th >= 10)
    d["vt_dome_wind"] = d.wind * dome
    d["vt_mid_wind"] = d.wind * light
    d["vt_high_wind"] = d.wind * high
    pt = d.practice_temp_th
    warm, cold = pt >= 70, pt <= 32
    mid = ~warm & ~cold
    tdiff = d.temp - pt
    fr = d.freezing == 1
    for name, seg in (("warm", warm), ("mid", mid), ("cold", cold)):
        d[f"vt_{name}_freezing"] = tdiff * (seg & fr)
        d[f"vt_{name}_notfreezing"] = tdiff * (seg & ~fr)
    d.loc[pt.isna(), [c for c in d.columns if c.startswith("vt_") and "wind" not in c]] = np.nan
    return d


def run(tg):
    d = thesis_vars(tg)
    res = []
    x5 = list(thesis.T5_ROWS)
    x67 = ["temp", "wind", "freezing", "hot"]
    for period, (a, b) in PERIODS.items():
        p = d[d.season.between(a, b)]
        res.append(fit_many(p, thesis.T5_OUT, x5, FE, table="T5", period=period, side="pooled"))
        for side in ("home", "away"):
            res.append(fit_many(p[p.side == side], list(thesis.T67), x67, FE, table="T67", period=period, side=side))
        vis = p[p.side == "away"]
        res.append(fit_many(vis, list(thesis.T89), thesis.T89_ROWS, FE, table="T89", period=period, side="away"))
    return pd.concat(res, ignore_index=True), d


def attach_thesis(r):
    t5, t89 = thesis.table5(), thesis.table89()
    def lookup(row):
        if row.table == "T5":
            return t5.get(row.outcome, {}).get(row.term, (np.nan, np.nan))
        if row.table == "T67":
            v = thesis.T67.get(row.outcome, {}).get(row.term)
            return v[0 if row.side == "home" else 1] if v else (np.nan, np.nan)
        return t89.get(row.outcome, {}).get(row.term, (np.nan, np.nan))
    th = r.apply(lookup, axis=1, result_type="expand")
    r["thesis_coef"], r["thesis_se"] = th[0], th[1]
    return r


HEADLINES = [
    # (label, table, side, outcome, term, expected sign, scale, unit)
    ("Wind lowers passing yards", "T5", "pooled", "ln_pass_yds", "wind", -1, 1000, "% per 10 mph"),
    ("Wind lowers completion %", "T5", "pooled", "ln_cmp_pct", "wind", -1, 1000, "% per 10 mph"),
    ("Wind shifts play mix to the run", "T5", "pooled", "ln_rush_pct", "wind", 1, 1000, "% per 10 mph"),
    ("Wind raises rushing yards", "T5", "pooled", "ln_rush_yds", "wind", 1, 1000, "% per 10 mph"),
    ("Cold lowers passing yards", "T5", "pooled", "ln_pass_yds", "temp", 1, -1000, "% per 10°F colder"),
    ("Cold lowers completion %", "T5", "pooled", "ln_cmp_pct", "temp", 1, -1000, "% per 10°F colder"),
    ("Heat (80°F+) lowers passing yards", "T5", "pooled", "ln_pass_yds", "hot", -1, 100, "% vs. not hot"),
    ("Heat (80°F+) lowers completion %", "T5", "pooled", "ln_cmp_pct", "hot", -1, 100, "% vs. not hot"),
    ("Visitors: wind lowers passing yards", "T67", "away", "ln_pass_yds", "wind", -1, 1000, "% per 10 mph"),
    ("Home teams: wind lowers passing yards", "T67", "home", "ln_pass_yds", "wind", -1, 1000, "% per 10 mph"),
    ("Visitors: cold lowers passing yards", "T67", "away", "ln_pass_yds", "temp", 1, -1000, "% per 10°F colder"),
    ("Home teams: cold lowers passing yards", "T67", "home", "ln_pass_yds", "temp", 1, -1000, "% per 10°F colder"),
    ("Visitors: wind raises run share", "T67", "away", "ln_rush_pct", "wind", 1, 1000, "% per 10 mph"),
    ("Home teams: cold raises run share", "T67", "home", "ln_rush_pct", "temp", -1, -1000, "% per 10°F colder"),
    ("Warm-climate visitors in freezing games: pass yds", "T89", "away", "ln_pass_yds", "vt_warm_freezing", 1, -1000, "% per 10°F colder than home"),
    ("Mid-climate visitors in freezing games: pass yds", "T89", "away", "ln_pass_yds", "vt_mid_freezing", 1, -1000, "% per 10°F colder than home"),
    ("Warm-climate visitors in freezing games: comp %", "T89", "away", "ln_cmp_pct", "vt_warm_freezing", 1, -1000, "% per 10°F colder than home"),
    ("Cold-climate visitors in freezing games: pass yds", "T89", "away", "ln_pass_yds", "vt_cold_freezing", 0, -1000, "% per 10°F colder than home"),
    ("Visitors from windy stadiums: wind & pass yds", "T89", "away", "ln_pass_yds", "vt_high_wind", -1, 1000, "% per 10 mph"),
    ("Visitors from calm stadiums: wind & pass yds", "T89", "away", "ln_pass_yds", "vt_mid_wind", -1, 1000, "% per 10 mph"),
    ("Visitors from domes: wind & pass yds", "T89", "away", "ln_pass_yds", "vt_dome_wind", -1, 1000, "% per 10 mph"),
]


def headlines(r):
    rows = []
    for label, table, side, out, term, sign, scale, unit in HEADLINES:
        sel = r[(r.table == table) & (r.side == side) & (r.outcome == out) & (r.term == term)]
        rep = sel[sel.period == "replication"].iloc[0]
        hold = sel[sel.period == "holdout"].iloc[0]
        # scale: log-points per unit -> percent per displayed unit (x1000 = % per 10 units)
        f = scale
        diff_z = (hold.coef - rep.coef) / np.hypot(hold.se, rep.se)
        if sign == 0:
            verdict = "holds (still ~0)" if hold.p > 0.10 else "changed"
        elif np.sign(hold.coef) == sign and hold.p < 0.05:
            verdict = "holds"
        elif np.sign(hold.coef) == sign and hold.p < 0.10:
            verdict = "holds (weaker)"
        elif np.sign(hold.coef) == sign:
            verdict = "same sign, not significant"
        else:
            verdict = "reversed" if hold.p < 0.10 else "gone"
        rows.append(dict(finding=label, unit=unit,
                         thesis=rep.thesis_coef * f, thesis_sig=stars(2 * stats.norm.sf(abs(rep.thesis_coef / rep.thesis_se))),
                         thesis_lo=(rep.thesis_coef - 1.96 * rep.thesis_se) * f,
                         thesis_hi=(rep.thesis_coef + 1.96 * rep.thesis_se) * f,
                         replication=rep.coef * f, replication_sig=stars(rep.p),
                         rep_lo=rep.lo * f, rep_hi=rep.hi * f,
                         holdout=hold.coef * f, holdout_lo=hold.lo * f, holdout_hi=hold.hi * f,
                         holdout_sig=stars(hold.p), holdout_p=hold.p, change_z=diff_z, verdict=verdict,
                         n_rep=int(rep.n), n_hold=int(hold.n)))
    return pd.DataFrame(rows)


if __name__ == "__main__":
    tg = pd.read_parquet(PROC / "team_games.parquet")
    r, d = run(tg)
    r = attach_thesis(r)
    r.to_csv(TABLES / "replication_long.csv", index=False)
    h = headlines(r)
    h.to_csv(TABLES / "replication_headlines.csv", index=False)
    pd.set_option("display.width", 250)
    pd.set_option("display.max_colwidth", 52)
    fmt = h.copy()
    for c in ["thesis", "replication", "holdout"]:
        fmt[c] = fmt[c].map(lambda v: f"{v:+.1f}") + fmt[f"{c}_sig"]
    print(fmt[["finding", "unit", "thesis", "replication", "holdout", "verdict", "n_hold"]].to_string(index=False))
