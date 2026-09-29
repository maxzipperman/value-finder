"""CFB eligible-game counts, Rule HT population (exactly as strategy-research/screen.py), and price-move SDs.
Counts only; no outcome statistics."""
import numpy as np
import pandas as pd

import os
from pathlib import Path

# The repo root; set VF_ROOT to run from a worktree against the main checkout's raw data.
ROOT = str(Path(os.environ.get("VF_ROOT", Path(__file__).resolve().parents[2])) / "cfb-weather")
g = pd.read_parquet(f"{ROOT}/data/processed/games.parquet")
pd.set_option("display.width", 250, "display.max_columns", 60)

print("season_type values:", g.season_type.value_counts(dropna=False).to_dict())
print("roof values:", g.roof.value_counts(dropna=False).to_dict())
print("wx_src values:", g.wx_src.value_counts(dropna=False).to_dict())
print("home_division values:", g.home_division.value_counts(dropna=False).to_dict())
print("wx_wind range:", g.wx_wind.min(), g.wx_wind.max(), "| wx_wind_kick range:", g.wx_wind_kick.min(), g.wx_wind_kick.max())
print("wx_temp range:", g.wx_temp.min(), g.wx_temp.max(), "| wx_precip range:", g.wx_precip.min(), g.wx_precip.max(),
      "| wx_precip NaN count:", int(g.wx_precip.isna().sum()))
print("seasons with station weather:", sorted(g.loc[g.wx_src.eq("station"), "season"].unique().tolist()))
print("seasons with pin_total:", sorted(g.loc[g.pin_total.notna(), "season"].unique().tolist()))
print("seasons with open_total:", sorted(g.loc[g.open_total.notna(), "season"].unique().tolist()))

# ---------------------------------------------------------------- Rule HT population, exactly as screen.py / board.ht_threshold
c = g[g.result.notna() & g.home_spread.notna() & g.season.between(2006, 2025) & (g.home_spread != 0)].copy()
ct = c[c.close_total.notna()]
season_mean = ct.groupby("season").close_total.mean()
season_n = ct.groupby("season").size()
assert list(season_mean.index) == list(range(2006, 2026)), "seasons not contiguous; shift(1) would misalign"
prev_mean = season_mean.shift(1)                       # screen.py line 311
ht = ct[(ct.close_total >= ct.season.map(prev_mean) + 10) & ct.season.between(2016, 2025)]
tab = pd.DataFrame({"n_games_in_mean_set": season_n, "mean_close_total": season_mean.round(3),
                    "prior_season_mean": prev_mean.round(3), "ht_threshold": (prev_mean + 10).round(2)})
tab["ht_eligible"] = ht.groupby("season").size()
tab["ht_eligible_regular"] = ht[ht.season_type.eq("regular")].groupby("season").size()
tab["ht_eligible_postseason"] = ht[ht.season_type.ne("regular")].groupby("season").size()
tab["ht_eligible_week6plus_or_post"] = ht[(ht.week >= 6) | ht.season_type.ne("regular")].groupby("season").size()
tab["ht_eligible_fbs_involved"] = ht[ht.home_division.astype(str).str.lower().eq("fbs") | ht.away_division.astype(str).str.lower().eq("fbs")].groupby("season").size()
tab["ht_eligible_outdoor_wind_lt15"] = ht[(ht.roof != "dome") & ~(ht.wx_wind >= 15)].groupby("season").size()
tab = tab.fillna(0)
print("\n=== CFB Rule HT (prior-season mean + 10), screen.py set: result & home_spread notna & home_spread != 0 & close_total notna ===")
print(tab.loc[2006:2025].to_string())
sub = tab.loc[2016:2025]
print("2016-2025 ht_eligible total:", int(sub.ht_eligible.sum()), "| 2020-2025:", int(tab.loc[2020:2025].ht_eligible.sum()))
print("2016-2025 regular:", int(sub.ht_eligible_regular.sum()), "post:", int(sub.ht_eligible_postseason.sum()),
      "| week6+/post:", int(sub.ht_eligible_week6plus_or_post.sum()), "| fbs-involved:", int(sub.ht_eligible_fbs_involved.sum()))
m25 = ct[ct.season == 2025]
print(f"board.ht_threshold(2026) recompute: 2025 mean={m25.close_total.mean():.6f} over {len(m25)} games -> threshold {m25.close_total.mean() + 10:.2f} (STRATEGY.md says 52.62 / 955 / 62.6)")

# ---------------------------------------------------------------- weather / total counts, 2016-2025
d = g[g.season.between(2016, 2025)].copy()
print("\n2016-2025 rows:", len(d), "| unplayed (home_points NaN):", int(d.home_points.isna().sum()), "| completed flag False:", int((~d.completed.astype(bool)).sum()))
d = d[d.home_points.notna()].copy()
fbs = d.home_division.astype(str).str.lower().eq("fbs") | d.away_division.astype(str).str.lower().eq("fbs")
outdoor = ~d.dome.astype(bool)
station = d.wx_src.eq("station")
ruleb_elig = fbs & outdoor & d.lat.notna() & d.lon.notna() & ~d.tbd.astype(bool) & d.total.notna() & d.close_total.notna()  # forecast_replay.eligible_games

flags = {
    "a_games": pd.Series(True, index=d.index),
    "a_fbs_involved": fbs,
    "a_close_total": d.close_total.notna(),
    "a_fbs_close_total": fbs & d.close_total.notna(),
    "b_outdoor_notdome": outdoor,
    "b_fbs_outdoor": fbs & outdoor,
    "b_fbs_outdoor_station_wx": fbs & outdoor & station,
    "b_ruleB_eligible_replay_def": ruleb_elig,
    "c_fbs_out_wind15_mean": fbs & station & (d.wx_wind >= 15),
    "c_fbs_out_wind15_kick": fbs & station & (d.wx_wind_kick >= 15),
    "c_ruleB_elig_wind15_mean": ruleb_elig & (d.wx_wind >= 15),
    "c_all_out_wind15_mean": station & (d.wx_wind >= 15),
    "e_fbs_out_temp90": fbs & station & (d.wx_temp >= 90),
    "e_fbs_out_temp85": fbs & station & (d.wx_temp >= 85),
    "f_fbs_out_temp32": fbs & station & (d.wx_temp <= 32),
    "g_fbs_out_rain006": fbs & station & (d.wx_precip >= 0.06),
    "g_fbs_out_precip_gt0": fbs & station & (d.wx_precip > 0),
    "g_fbs_out_precip_ge001": fbs & station & (d.wx_precip >= 0.01),
    "g_fbs_out_rain_code": fbs & station & d.wx_rain_code.eq(1),
    "g_fbs_out_snow010": fbs & station & (d.wx_snow >= 0.10),
    "i_pin_total": d.pin_total.notna(),
    "i_fbs_pin_total": fbs & d.pin_total.notna(),
    "open_and_close_total": d.open_total.notna() & d.close_total.notna(),
}
F = pd.DataFrame(flags)


def table(mask, label):
    t = F[mask].groupby(d.season[mask]).sum().astype(int)
    t.loc["2016-2025"] = t.sum()
    t.loc["2020-2025"] = t.loc[[s for s in t.index if isinstance(s, (int, np.integer)) and s >= 2020]].sum()
    print(f"\n=== CFB {label} ===")
    print(t.T.to_string())


table(pd.Series(True, index=d.index), "regular + postseason")
table(d.season_type.eq("regular"), "regular only")
table(d.season_type.ne("regular"), "postseason only")

# pin_total by season for all seasons (to show where Pinnacle stops)
pin = g.groupby("season").agg(games=("game_id", "size"), pin_total=("pin_total", "count"), close_total=("close_total", "count"),
                              open_total=("open_total", "count"))
print("\n=== CFB per-season line availability, all seasons in file ===")
print(pin.to_string())

# ---------------------------------------------------------------- forecasts (2024-25 only, forecast_replay.parquet)
fr = pd.read_parquet(f"{ROOT}/data/processed/forecast_replay.parquet")
fr["any_cal15"] = fr[["fc1_wind", "fc2_wind", "fc3_wind"]].max(axis=1) >= 15
fr["any_raw15"] = fr[["fc1_raw", "fc2_raw", "fc3_raw"]].max(axis=1) >= 15
ft = fr.groupby("season").agg(eligible=("game_id", "size"), no_forecast=("no_forecast", "sum"),
                              fc1_cal15=("fc1_wind", lambda x: (x >= 15).sum()), fc2_cal15=("fc2_wind", lambda x: (x >= 15).sum()),
                              fc3_cal15=("fc3_wind", lambda x: (x >= 15).sum()), any_cal15=("any_cal15", "sum"), any_raw15=("any_raw15", "sum"),
                              fc_trigger=("fc_trigger", "sum"), fc_signal_after_price_gates=("fc_signal", "sum"),
                              obs_trigger_wx_wind15=("obs_trigger", "sum"))
print("\n=== CFB forecast_replay.parquet (Rule B eligible games 2024-25; fc*_wind = calibrated station scale, fc*_raw = Open-Meteo) ===")
print(ft.to_string())
print("weeks/season_type in replay:", fr.season_type.value_counts().to_dict())

# ---------------------------------------------------------------- CLV / price-move SDs (price statistics)
co = g[g.open_total.notna() & g.close_total.notna()].copy()
co["move"] = co.close_total - co.open_total
per = co.groupby("season").agg(n=("move", "size"), sd_total_move=("move", "std"), mean_move=("move", "mean"),
                               mean_abs_move=("move", lambda x: x.abs().mean()))
print("\n=== CFB consensus open->close total move by season (games.parquet, median across books) ===")
print(per.round(3).to_string())
c16 = co[co.season.between(2016, 2025)]
print("2016-2025 all games: n=%d sd=%.3f mean=%+.3f" % (len(c16), c16.move.std(), c16.move.mean()))
cf = c16[c16.home_division.astype(str).str.lower().eq("fbs") | c16.away_division.astype(str).str.lower().eq("fbs")]
print("2016-2025 FBS-involved: n=%d sd=%.3f" % (len(cf), cf.move.std()))
w = c16[(c16.wx_src == "station") & (c16.wx_wind >= 15)]
print("simulate_decisions proxy (station, wx_wind>=15, 2016-25): n=%d mean(open-close)=%+.3f sd=%.3f" % (len(w), (w.open_total - w.close_total).mean(), (w.open_total - w.close_total).std()))

# raw line_odds per-book check
b = pd.read_parquet(f"{ROOT}/data/raw/cfbfastr/line_odds.parquet")
print("\nline_odds market_type values:", b.market_type.value_counts().to_dict())
print("line_odds books:", b.book.value_counts().to_dict())
bt = b[(b.market_type == "total") & b.lines.notna() & b.opening_lines.notna()].copy()
bt["move"] = bt.lines - bt.opening_lines
print("per-book total rows with open&close: n=%d sd=%.3f; by season:" % (len(bt), bt.move.std()))
print(bt.groupby("season").agg(n=("move", "size"), sd=("move", "std")).round(3).T.to_string())
bs = b[(b.market_type == "spread") & b.lines.notna() & b.opening_lines.notna()].copy()
bs["move"] = bs.lines - bs.opening_lines
print("per-book spread rows with open&close: n=%d sd=%.3f" % (len(bs), bs.move.std()))
pinb = bt[bt.book.str.upper().str.contains("PINNACLE")]
print("Pinnacle total rows with open&close by season:", pinb.groupby("season").size().to_dict())

za, zb = 1.6448536, 0.8416212
print("\n=== CFB CLV power (n for mean CLV delta, one-sided 95%, 80% power) ===")
for lab, sd in (("all-games consensus total move sd 2016-25", c16.move.std()), ("windy-cohort proxy sd (repo)", (w.open_total - w.close_total).std())):
    for delta in (0.5, 1.0, 1.5):
        n = ((za + zb) * sd / delta) ** 2
        print(f"{lab:42s} sd={sd:.3f} delta={delta:.1f} -> n={np.ceil(n):.0f}")
