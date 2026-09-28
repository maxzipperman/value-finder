"""Collect the output tables into one JSON blob and render report/nfl_weather_report.html
from report/template.html. Re-run after refreshing data to update the report."""
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd

from nflweather.config import OUT, PROC, ROOT, TABLES
from nflweather.features import RAIN_IN, SNOW_IN


def rows(df, cols=None, nd=4):
    df = df if cols is None else df[cols]
    out = []
    for r in df.to_dict("records"):
        clean = {}
        for k, v in r.items():
            if isinstance(v, (float, np.floating)):
                clean[k] = None if not np.isfinite(v) else round(float(v), nd)
            elif isinstance(v, (np.integer,)):
                clean[k] = int(v)
            else:
                clean[k] = v
        out.append(clean)
    return out


def read(name):
    p = TABLES / name
    return pd.read_csv(p) if p.exists() else pd.DataFrame()


def main():
    games = pd.read_parquet(PROC / "games.parquet")
    played = games[games.result.notna()]
    tg = pd.read_parquet(PROC / "team_games.parquet")
    kicks = pd.read_parquet(PROC / "kicks.parquet")
    cal = json.loads((PROC / "calibration.json").read_text())
    outdoor = played[played.wx_src.isin(["gamebook", "era5"])]
    d = {}
    d["meta"] = dict(
        generated=date.today().isoformat(),
        first_season=int(played.season.min()), last_season=int(played.season.max()),
        games=int(len(played)), team_games=int(len(tg)), plays_kicks=int(len(kicks)),
        outdoor_games=int(len(outdoor)),
        era5_games=int(played.om_temp.notna().sum()),
        gamebook_games=int(played.gb_temp.notna().sum()),
        sbr_games=int(played.total_open.notna().sum()) if "total_open" in played else 0,
        wind_cal=cal,
        thesis_games=int(played.season.between(2002, 2013).sum()),
        holdout_games=int(played.season.between(2014, 2025).sum()),
        rain_games=int(((outdoor.om_precip >= RAIN_IN) & (outdoor.om_snow < SNOW_IN)).sum()),
        snow_games=int((outdoor.om_snow >= SNOW_IN).sum()),
        rain_in=RAIN_IN, snow_in=SNOW_IN,
        wind15_games=int((outdoor.wx_wind >= 15).sum()),
        freezing_games=int((outdoor.wx_temp <= 32).sum()),
        wind20_games=int((outdoor.wx_wind >= 20).sum()),
        fg_attempts=int(((kicks.kind == "fg") & kicks.season.between(1999, 2025) & kicks.kick_distance.between(18, 70)).sum()),
            )
    # validation of ERA5 precipitation against the game-book text ("Rain", "Snow")
    o = outdoor[outdoor.gb_weather_text.fillna("").str.len() > 0].copy()
    o["era5_wet"] = o.om_precip >= RAIN_IN
    d["precip_check"] = dict(
        gamebook_says_rain=int(o.gb_rain.sum()),
        era5_wet_given_gb_rain=float(o.loc[o.gb_rain, "era5_wet"].mean()) if o.gb_rain.any() else None,
        era5_wet_given_gb_dry=float(o.loc[~o.gb_rain & ~o.gb_snow, "era5_wet"].mean()),
        gamebook_says_snow=int(o.gb_snow.sum()),
        era5_snow_given_gb_snow=float((o.loc[o.gb_snow, "om_snow"] >= SNOW_IN).mean()) if o.gb_snow.any() else None,
        gb_rain_given_era5_wet=float(o.loc[o.era5_wet, "gb_rain"].mean()),
    )
    from nflweather.features import add_weather_features
    tf = add_weather_features(tg[tg.season.between(1999, 2025)])
    d["meta"].update(team_wind20=int(tf.wind_20p.sum()), team_rain=int(tf.rain.sum()), team_snow=int(tf.snow.sum()))
    sp = TABLES / "bet_summary.json"
    d["summary"] = json.loads(sp.read_text()) if sp.exists() else {}
    d["model_vs_market"] = rows(read("bet_model_vs_market.csv"))
    d["headlines"] = rows(read("replication_headlines.csv"))
    d["audit_ladder"] = rows(read("audit_ladder.csv"))
    d["audit_home"] = rows(read("audit_home.csv"))
    d["audit_strength"] = rows(read("audit_strength.csv"))
    d["model_compare"] = rows(read("model_compare.csv"))
    d["strategies"] = rows(read("strategies.csv"))
    d["model_compare_bets"] = rows(read("model_compare_bets.csv"))
    d["ext_main"] = rows(read("ext_main_effects.csv"))
    d["ext_ppml"] = rows(read("ext_ppml_pct.csv"))
    d["ext_era"] = rows(read("ext_by_era.csv"))
    d["ext_home_away"] = rows(read("ext_home_away.csv"))
    d["ext_acclimation"] = rows(read("ext_acclimation.csv"))
    d["kicking_grid"] = rows(read("kicking_grid.csv"))
    d["kicking_by_wind"] = rows(read("kicking_by_wind.csv"))
    kl = read("kicking_logit.csv")
    d["kicking_logit"] = rows(kl.rename(columns={kl.columns[0]: "term"})) if len(kl) else []
    d["market"] = rows(read("bet_market_vs_reality.csv"))
    d["totals_bucket"] = rows(read("bet_totals_by_bucket.csv"))
    d["open_close"] = rows(read("bet_open_vs_close.csv"))
    d["walkforward"] = rows(read("bet_walkforward.csv"))
    cum = read("bet_walkforward_cum.csv")
    d["walkforward_cum"] = rows(cum[["gameday", "season", "cum_units"]]) if len(cum) else []
    d["walkforward_season"] = rows(read("bet_walkforward_by_season.csv"))
    d["dogs_wind"] = rows(read("bet_sides_wind.csv"))
    d["acclimation_ats"] = rows(read("bet_acclimation_ats.csv"))
    d["forecast_skill"] = rows(read("bet_forecast_skill.csv"))
    d["forecast_vs_actual"] = rows(read("bet_forecast_vs_actual.csv"))
    tw = OUT / "this_week.csv"
    d["this_week"] = rows(pd.read_csv(tw)) if tw.exists() else []
    (OUT / "report_data.json").write_text(json.dumps(d, ensure_ascii=False))

    tpl = (ROOT / "report" / "template.html").read_text()
    charts = (ROOT / "report" / "charts.js").read_text()
    html = tpl.replace("/*__DATA__*/null", json.dumps(d, ensure_ascii=False).replace("</", "<\\/"))
    html = html.replace("/*__CHARTS__*/", charts)
    (ROOT / "report" / "nfl_weather_report.html").write_text(html)
    print("wrote report/nfl_weather_report.html", f"({len(html) / 1e3:.0f} KB)")


if __name__ == "__main__":
    main()
