"""Step 4: does the betting market price the weather?

1. Market vs reality: how much does weather move actual scoring, vs how much
   does it move the closing total? (same fixed effects for both)
2. Totals by weather bucket: under rate, average miss vs the closing total,
   flat-bet ROI at -110 and at the actual closing prices (2006+).
3. Open vs close (2007-2021): does the total move toward the under in bad
   weather, and how much value is left at the open vs the close?
4. Walk-forward backtest: a weather-only model of (total - closing total),
   refit each season on prior seasons only, then bet the next season.
5. Sides: favorites vs underdogs in wind; dome/warm visitors in freezing games
   (spread and implied team totals).

Caveat baked into everything here: weather is the *observed* kickoff weather.
A bettor only has the forecast. Closing lines are set with a near-kickoff
forecast, so tests against the close are fair; tests against the open are an
upper bound on what an early bettor could have captured.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd
from scipy import stats

from nflweather.config import PROC, TABLES
from nflweather.features import BIN_TERMS
from nflweather.market import fit_under_model, load_games, predict_under, record
from nflweather.models import fit

def market_vs_reality(g):
    rows = []
    x = BIN_TERMS + ["playoff", "neutral"]
    fe = ["home_ts", "away_ts", "week_fe"]
    for y, lab in [("total", "Actual points"), ("total_line", "Closing total"), ("resid_total", "Actual − closing")]:
        for era, s in [("All 1999–2025", g), *g.groupby("era")]:
            t = fit(s, y, x, fe if y != "resid_total" else None, "hetero")
            t["series"], t["era"] = lab, era
            rows.append(t)
    r = pd.concat(rows, ignore_index=True)
    r.to_csv(TABLES / "bet_market_vs_reality.csv", index=False)
    return r


def totals_by_bucket(g):
    rows = []
    o = g[g.outdoor == 1]
    buckets = {
        **{f"Wind {b}": o.wbin == b for b in o.wbin.cat.categories},
        "Wind 15+": o.wx_wind >= 15,
        "Air temp ≤32°F": o.temp_le32 == 1,
        "Rain": o.rain == 1,
        "Snow": o.snow == 1,
        "Wind 15+ & (rain or snow)": (o.wx_wind >= 15) & ((o.rain == 1) | (o.snow == 1)),
    }
    for era, s_all in [("All", o), *o.groupby("era")]:
        for name, mask in buckets.items():
            s = s_all[mask.loc[s_all.index]]
            rec = record(s.under_win.values, s.over_win.values, s.under_profit)
            rows.append(dict(era=era, bucket=name, games=len(s), mean_line=s.total_line.mean(),
                             mean_total=s.total.mean(), mean_resid=s.resid_total.mean(),
                             resid_se=s.resid_total.std() / np.sqrt(max(len(s), 1)), under=rec))
    base = g[g.outdoor == 0]
    for era, s in [("All", base), *base.groupby("era")]:
        rows.append(dict(era=era, bucket="Dome / closed roof", games=len(s), mean_line=s.total_line.mean(),
                         mean_total=s.total.mean(), mean_resid=s.resid_total.mean(),
                         resid_se=s.resid_total.std() / np.sqrt(len(s)),
                         under=record(s.under_win.values, s.over_win.values, s.under_profit)))
    r = pd.DataFrame(rows)
    r = pd.concat([r.drop(columns="under"), pd.json_normalize(r.under).add_prefix("under_")], axis=1)
    r.to_csv(TABLES / "bet_totals_by_bucket.csv", index=False)
    return r


def open_vs_close(g):
    s = g[g.total_open.notna() & (g.outdoor == 1)].copy()
    s["move"] = s.total_line - s.total_open
    s["resid_open"] = s.total - s.total_open
    s["under_open_win"] = s.total < s.total_open
    s["over_open_win"] = s.total > s.total_open
    rows = []
    groups = {**{f"Wind {b}": s.wbin == b for b in s.wbin.cat.categories}, "Wind 15+": s.wx_wind >= 15,
              "Rain": s.rain == 1, "Snow": s.snow == 1, "Air temp ≤32°F": s.temp_le32 == 1}
    for name, m in groups.items():
        d = s[m]
        rec_open = record(d.under_open_win.values, d.over_open_win.values)
        rec_close = record(d.under_win.values, d.over_win.values)
        rows.append(dict(bucket=name, games=len(d), mean_open=d.total_open.mean(), mean_close=d.total_line.mean(),
                         mean_move=d.move.mean(), move_se=d.move.std() / np.sqrt(len(d)),
                         share_moved_down=(d.move < 0).mean(), resid_vs_open=d.resid_open.mean(),
                         resid_vs_close=d.resid_total.mean(),
                         under_open_pct=rec_open["win_pct"], under_open_roi=rec_open["roi_110"],
                         under_close_pct=rec_close["win_pct"], under_close_roi=rec_close["roi_110"]))
    dome = g[g.total_open.notna() & (g.outdoor == 0)]
    rows.append(dict(bucket="Dome / closed roof", games=len(dome), mean_open=dome.total_open.mean(),
                     mean_close=dome.total_line.mean(), mean_move=(dome.total_line - dome.total_open).mean(),
                     move_se=(dome.total_line - dome.total_open).std() / np.sqrt(len(dome)),
                     share_moved_down=((dome.total_line - dome.total_open) < 0).mean(),
                     resid_vs_open=(dome.total - dome.total_open).mean(), resid_vs_close=dome.resid_total.mean(),
                     under_open_pct=np.nan, under_open_roi=np.nan, under_close_pct=np.nan, under_close_roi=np.nan))
    r = pd.DataFrame(rows)
    r.to_csv(TABLES / "bet_open_vs_close.csv", index=False)
    return r


def walk_forward(g, thresholds=(0.53, 0.55, 0.57), first_test=2006):
    """Refit P(under) ~ weather on seasons < t, bet season t whenever the model's
    probability clears the threshold (52.4% is break-even at -110)."""
    preds = []
    for t in range(first_test, 2026):
        tr, te = g[g.season < t], g[g.season == t].copy()
        m = fit_under_model(tr)
        te["p_under"] = predict_under(m, te)
        preds.append(te)
    p = pd.concat(preds)
    p["era"] = np.where(p.season <= 2013, "2006–2013", "2014–2025")
    rows = []
    for k in thresholds:
        for era, s in [("2006–2025", p), *p.groupby("era")]:
            u = s[s.p_under >= k]
            o = s[s.p_under <= 1 - k]
            rows.append(dict(threshold=k, era=era, side="under", **record(u.under_win.values, u.over_win.values, u.under_profit)))
            rows.append(dict(threshold=k, era=era, side="over", **record(o.over_win.values, o.under_win.values, o.over_profit)))
    r = pd.DataFrame(rows)
    p[["game_id", "season", "p_under", "resid_total", "under_win", "over_win", "wx_wind", "wx_temp", "rain", "snow"]].to_csv(
        TABLES / "bet_walkforward_preds.csv", index=False)
    r.to_csv(TABLES / "bet_walkforward.csv", index=False)
    by_season = p[p.p_under >= 0.55].groupby("season").apply(
        lambda s: pd.Series(record(s.under_win.values, s.over_win.values))).reset_index()
    by_season.to_csv(TABLES / "bet_walkforward_by_season.csv", index=False)
    return r, by_season


def sides(g):
    rows = []
    s = g[g.spread_line != 0].copy()
    fav_home = s.spread_line > 0
    s["fav_margin"] = np.where(fav_home, s.result, -s.result)
    s["fav_spread"] = s.spread_line.abs()
    s["fav_cover"] = s.fav_margin > s.fav_spread
    s["dog_cover"] = s.fav_margin < s.fav_spread
    o = s[s.outdoor == 1]
    for name, m in {**{f"Wind {b}": o.wbin == b for b in o.wbin.cat.categories}, "Wind 15+": o.wx_wind >= 15,
                    "Snow": o.snow == 1, "Rain": o.rain == 1, "Air temp ≤32°F": o.temp_le32 == 1}.items():
        d = o[m]
        rec = record(d.dog_cover.values, d.fav_cover.values)
        rows.append(dict(test="Underdog ATS", bucket=name, games=len(d),
                         mean_fav_resid=(d.fav_margin - d.fav_spread).mean(), **rec))
    r1 = pd.DataFrame(rows)

    # Visitor acclimation: warm-climate / dome visitors in freezing games
    tg = pd.read_parquet(PROC / "team_games.parquet")[["game_id", "side", "dome_team", "city_tavg7"]]
    v = tg[tg.side == "away"].rename(columns={"dome_team": "v_dome", "city_tavg7": "v_city_temp"})
    h = tg[tg.side == "home"].rename(columns={"dome_team": "h_dome", "city_tavg7": "h_city_temp"})
    s = s.merge(v.drop(columns="side"), on="game_id", how="left").merge(h.drop(columns="side"), on="game_id", how="left")
    s["home_cover"] = s.result > s.spread_line
    s["away_cover"] = s.result < s.spread_line
    # implied team totals from the closing lines
    s["away_implied"] = s.total_line / 2 - s.spread_line / 2
    s["away_tt_resid"] = s.away_score - s.away_implied
    s["home_implied"] = s.total_line / 2 + s.spread_line / 2
    s["home_tt_resid"] = s.home_score - s.home_implied
    cold = (s.outdoor == 1) & (s.wx_temp <= 32) & (s.neutral == 0)
    groups = {
        "Dome visitor, ≤32°F game": cold & (s.v_dome == 1),
        "Warm visitor (≥60°F week), ≤32°F game": cold & (s.v_dome == 0) & (s.v_city_temp >= 60),
        "Dome or warm visitor, ≤32°F game": cold & ((s.v_dome == 1) | (s.v_city_temp >= 60)),
        "Cold-climate visitor (<40°F week), ≤32°F game": cold & (s.v_dome == 0) & (s.v_city_temp < 40),
        "All ≤32°F games": cold,
    }
    rows = []
    for name, m in groups.items():
        for era, d in [("All", s[m]), *s[m].groupby("era")]:
            rec = record(d.home_cover.values, d.away_cover.values)
            rec_tt = record((d.away_tt_resid < 0).values, (d.away_tt_resid > 0).values)
            rows.append(dict(group=name, era=era, games=len(d), home_ats_resid=(d.result - d.spread_line).mean(),
                             home_ats_se=(d.result - d.spread_line).std() / np.sqrt(max(len(d), 1)),
                             away_team_total_resid=d.away_tt_resid.mean(),
                             home_team_total_resid=d.home_tt_resid.mean(),
                             home_cover_pct=rec["win_pct"], home_cover_roi=rec["roi_110"],
                             away_tt_under_pct=rec_tt["win_pct"], away_tt_under_roi=rec_tt["roi_110"]))
    r2 = pd.DataFrame(rows)
    r1.to_csv(TABLES / "bet_sides_wind.csv", index=False)
    r2.to_csv(TABLES / "bet_acclimation_ats.csv", index=False)
    return r1, r2


def forecast_check(g_all):
    """2024+: how well did the 1- and 3-day-ahead forecasts anticipate kickoff wind,
    and does the weather model still find the unders when fed the forecast?"""
    import json
    from nflweather.features import add_weather_features
    cal = json.loads((PROC / "calibration.json").read_text())
    g = pd.read_parquet(PROC / "games.parquet")
    g = g[g.result.notna() & g.fc1_wind.notna() & (g.roof == "outdoors")].copy() if "fc1_wind" in g else g.iloc[:0]
    if g.empty:
        return None, None
    for lead in (1, 3):
        g[f"fc{lead}_wind_cal"] = (cal["wind_intercept"] + cal["wind_slope"] * g[f"fc{lead}_wind"]).clip(lower=0)
    stats_rows = []
    for lead in (1, 3):
        f, a = g[f"fc{lead}_wind_cal"], g.wx_wind
        hit = ((f >= 15) & (a >= 15)).sum()
        ok = f.notna() & a.notna()
        stats_rows.append(dict(lead_days=lead, games=int(ok.sum()), corr=float(f[ok].corr(a[ok])), mae=(f - a)[ok].abs().mean(),
                               actual_15p=int((a >= 15).sum()), forecast_15p=int((f >= 15).sum()), both_15p=int(hit),
                               precision=hit / max((f >= 15).sum(), 1), recall=hit / max((a >= 15).sum(), 1)))
    # fit P(under) on 1999-2023 realized weather; score 2024+ games with realized vs forecast inputs
    m = fit_under_model(g_all[g_all.season <= 2023])
    g["resid_total"] = g.total - g.total_line
    g["under_win"], g["over_win"] = g.total < g.total_line, g.total > g.total_line
    rows = []
    for name, wind, temp, precip, snow in [
        ("Actual kickoff weather", g.wx_wind, g.wx_temp, g.wx_precip, g.wx_snow),
        ("1-day forecast", g.fc1_wind_cal, g.fc1_temp, g.fc1_precip, g.fc1_snow),
        ("3-day forecast", g.fc3_wind_cal, g.fc3_temp, g.fc3_precip, g.fc3_snow)]:
        x = add_weather_features(g.assign(wx_src="era5", wx_wind=wind, wx_temp=temp, wx_precip=precip, wx_snow=snow))
        pu = predict_under(m, x)
        sel = pu >= 0.53
        rows.append(dict(inputs=name, **record(g.under_win.values[sel], g.over_win.values[sel])))
        w15 = (wind >= 15).values
        rows.append(dict(inputs=name + " · wind 15+ rule", **record(g.under_win.values[w15], g.over_win.values[w15])))
    s, r = pd.DataFrame(stats_rows), pd.DataFrame(rows)
    s.to_csv(TABLES / "bet_forecast_skill.csv", index=False)
    r.to_csv(TABLES / "bet_forecast_vs_actual.csv", index=False)
    return s, r


def model_vs_market(g):
    """sharp-markets style check: on games where the weather model and the de-vigged
    closing price disagree, whose probability is better (Brier), and does betting
    the disagreement pay? Run under both de-vig methods."""
    from nflweather.market import market_p_under
    p = pd.read_csv(TABLES / "bet_walkforward_preds.csv")[["game_id", "p_under"]]
    s = g.merge(p, on="game_id")
    s = s[(s.under_win | s.over_win) & s.under_odds.notna() & s.over_odds.notna()].copy()
    y = s.under_win.astype(int)
    rows = []
    for method in ("proportional", "shin"):
        s["p_mkt"] = market_p_under(s.under_odds, s.over_odds, "shin" if method == "shin" else "prop")
        s["gap"] = s.p_under - s.p_mkt
        for thr in (0.0, 0.02, 0.04, 0.06):
            sub = s[s.gap.abs() >= thr]
            yy = sub.under_win.astype(int)
            bet_under = sub.gap > 0
            rec = record(np.where(bet_under, sub.under_win, sub.over_win), np.where(bet_under, sub.over_win, sub.under_win),
                         np.where(bet_under, sub.under_profit, sub.over_profit))
            rows.append(dict(devig=method, min_gap=thr, games=len(sub), base_rate_under=yy.mean(),
                             brier_model=((sub.p_under - yy) ** 2).mean(), brier_market=((sub.p_mkt - yy) ** 2).mean(),
                             **{k: rec[k] for k in ("bets", "win_pct", "win_lo", "win_hi", "roi_actual_odds")}))
    r = pd.DataFrame(rows)
    r.to_csv(TABLES / "bet_model_vs_market.csv", index=False)
    return r


def clv_and_stability(g):
    """Closing-line value of the walk-forward under bets where an opening line
    exists (2007-2021), and how many seasons the strategy made money."""
    p = pd.read_csv(TABLES / "bet_walkforward_preds.csv")[["game_id", "p_under"]]
    s = g.merge(p, on="game_id")
    bets = s[s.p_under >= 0.53]
    o = bets[bets.total_open.notna()]
    clv = dict(bets_with_open=len(o), mean_clv_pts=float((o.total_open - o.total_line).mean()),
               share_beat_close=float((o.total_line < o.total_open).mean()),
               share_worse_than_close=float((o.total_line > o.total_open).mean()),
               under_vs_open=record(o.total < o.total_open, o.total > o.total_open)["win_pct"],
               under_vs_close=record(o.under_win, o.over_win)["win_pct"])
    # all outdoor games as a baseline: do totals drift under from open to close in general?
    allo = s[s.total_open.notna() & (s.outdoor == 1)]
    clv["all_outdoor_mean_move_pts"] = float((allo.total_line - allo.total_open).mean())
    by = pd.read_csv(TABLES / "bet_walkforward_by_season.csv")
    stab = dict(seasons=int(len(by)), seasons_profitable=int((by.roi_110 > 0).sum()),
                seasons_with_bets=int((by.bets > 0).sum()))
    return clv, stab


def variants_tested():
    """Every betting rule looked at in this script, so readers can discount
    the best-looking one accordingly (as in sharp-markets)."""
    tb = pd.read_csv(TABLES / "bet_totals_by_bucket.csv")
    wf = pd.read_csv(TABLES / "bet_walkforward.csv")
    sw = pd.read_csv(TABLES / "bet_sides_wind.csv")
    ac = pd.read_csv(TABLES / "bet_acclimation_ats.csv")
    mm = pd.read_csv(TABLES / "bet_model_vs_market.csv")
    oc = pd.read_csv(TABLES / "bet_open_vs_close.csv")
    n = dict(totals_buckets=int(tb[["bucket", "era"]].drop_duplicates().shape[0]),
             open_close_buckets=int(len(oc)), walkforward=int(wf[["threshold", "side", "era"]].drop_duplicates().shape[0]),
             underdog_buckets=int(len(sw)), acclimation_groups=int(ac[["group", "era"]].drop_duplicates().shape[0]) * 2,
             model_vs_market=int(len(mm)))
    n["total"] = sum(n.values())
    return n


def cumulative_units(g):
    p = pd.read_csv(TABLES / "bet_walkforward_preds.csv").merge(g[["game_id", "gameday"]], on="game_id")
    p = p[p.p_under >= 0.53].sort_values("gameday")
    p["units"] = np.where(p.under_win, 100 / 110, np.where(p.over_win, -1.0, 0.0))
    p["cum_units"] = p.units.cumsum()
    p[["gameday", "season", "game_id", "p_under", "units", "cum_units"]].to_csv(TABLES / "bet_walkforward_cum.csv", index=False)
    return p


if __name__ == "__main__":
    pd.set_option("display.width", 250)
    pd.set_option("display.max_columns", 30)
    g = load_games()
    print(f"games {len(g):,}; outdoor {int(g.outdoor.sum()):,}")
    mv = market_vs_reality(g)
    show = mv[mv.term.isin(BIN_TERMS)].pivot_table(index=["era", "term"], columns="series", values="coef", sort=False)
    print("\nPoints effect: actual vs closing total vs residual\n", show.round(2).to_string())
    tb = totals_by_bucket(g)
    print("\nTotals by bucket\n", tb[["era", "bucket", "games", "mean_line", "mean_total", "mean_resid", "under_bets",
                                      "under_win_pct", "under_roi_110", "under_roi_actual_odds", "under_p_vs_breakeven"]].round(3).to_string(index=False))
    oc = open_vs_close(g)
    print("\nOpen vs close (2007–2021, outdoor)\n", oc.round(3).to_string(index=False))
    wf, bys = walk_forward(g)
    print("\nWalk-forward (P(under) model, refit each season)\n", wf[["threshold", "era", "side", "bets", "win_pct", "win_lo", "win_hi", "roi_110", "roi_actual_odds", "p_vs_breakeven"]].round(3).to_string(index=False))
    cu = cumulative_units(g)
    print(f"\ncumulative units (P(under) >= 0.53 bets): {cu.cum_units.iloc[-1]:+.1f} over {len(cu)} bets")
    fs, fr = forecast_check(g)
    if fs is not None:
        print("\nForecast skill (kickoff wind, 2024+)\n", fs.round(3).to_string(index=False))
        print("\nSame model, actual vs forecast inputs (2024+)\n", fr[["inputs", "bets", "win_pct", "roi_110"]].round(3).to_string(index=False))
    mm = model_vs_market(g)
    print("\nModel vs de-vigged closing price (walk-forward P(under), 2006+)\n", mm.round(4).to_string(index=False))
    clv, stab = clv_and_stability(g)
    print("\nCLV of walk-forward under bets (2007-2021 opens):", {k: round(v, 3) if isinstance(v, float) else v for k, v in clv.items()})
    print("Season stability:", stab)
    s1, s2 = sides(g)
    nv = variants_tested()
    print("\nVariants tested:", nv)
    import json
    (TABLES / "bet_summary.json").write_text(json.dumps(dict(clv=clv, stability=stab, variants=nv), default=float))
    print("\nUnderdogs by weather\n", s1[["bucket", "games", "mean_fav_resid", "bets", "win_pct", "roi_110", "p_vs_breakeven"]].round(3).to_string(index=False))
    print("\nAcclimation vs the spread\n", s2.round(3).to_string(index=False))
