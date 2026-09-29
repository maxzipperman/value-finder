"""NFL eligible-game counts and price-move SDs. Counts only; no outcome statistics."""
import json
import numpy as np
import pandas as pd

import os
from pathlib import Path

# The repo root; set VF_ROOT to run from a worktree against the main checkout's raw data.
ROOT = str(Path(os.environ.get("VF_ROOT", Path(__file__).resolve().parents[2])) / "nfl-weather")
g = pd.read_parquet(f"{ROOT}/data/processed/games.parquet")
cal = json.load(open(f"{ROOT}/data/processed/calibration.json"))
pd.set_option("display.width", 250, "display.max_columns", 60)

print("game_type values (all seasons):", g.game_type.value_counts(dropna=False).to_dict())
print("roof values (all seasons):", g.roof.value_counts(dropna=False).to_dict())
print("wx_src values (all seasons):", g.wx_src.value_counts(dropna=False).to_dict())
print("wx_wind range:", g.wx_wind.min(), g.wx_wind.max(), "| wx_temp range:", g.wx_temp.min(), g.wx_temp.max())
print("wx_precip range:", g.wx_precip.min(), g.wx_precip.max(), "| fc1_wind range:", g.fc1_wind.min(), g.fc1_wind.max())
print("seasons with any fc1_wind:", sorted(g.loc[g.fc1_wind.notna(), "season"].unique().tolist()))
print("seasons with any total_open (SBR):", sorted(g.loc[g.total_open.notna(), "season"].unique().tolist()))

d = g[g.season.between(2016, 2025)].copy()
print("\n2016-2025 rows:", len(d), "| unplayed (result NaN):", int(d.result.isna().sum()))
d = d[d.result.notna()].copy()
d["post"] = d.game_type.ne("REG")

outdoor = d.wx_src.isin(["gamebook", "era5"])          # repo definition (features.add_weather_features)
roof_out = d.roof.eq("outdoors") | d.roof.isna()       # build.py 'outdoor' mask
for c in ("fc1_wind", "fc2_wind", "fc3_wind"):
    d[c + "_cal"] = (cal["wind_intercept"] + cal["wind_slope"] * d[c]).clip(lower=0)

flags = {
    "a_games": pd.Series(True, index=d.index),
    "a_close_total": d.total_line.notna(),
    "b_outdoor_wxsrc": outdoor,
    "b_roof_outdoors": roof_out,
    "b_roof_open_retract": d.roof.eq("open"),
    "b_indoor": d.indoor.eq(1),
    "c_out_wind15": outdoor & (d.wx_wind >= 15),
    "c_out_wind15_total": outdoor & (d.wx_wind >= 15) & d.total_line.notna(),
    "d_has_fc1": d.fc1_wind.notna(),
    "d_out_fc_any_cal15": outdoor & (d[["fc1_wind_cal", "fc2_wind_cal", "fc3_wind_cal"]].max(axis=1) >= 15),
    "d_out_fc1_cal15": outdoor & (d.fc1_wind_cal >= 15),
    "d_out_fc2_cal15": outdoor & (d.fc2_wind_cal >= 15),
    "d_out_fc3_cal15": outdoor & (d.fc3_wind_cal >= 15),
    "d_out_fc_any_raw15": outdoor & (d[["fc1_wind", "fc2_wind", "fc3_wind"]].max(axis=1) >= 15),
    "e_out_temp90": outdoor & (d.wx_temp >= 90),
    "e_out_temp85": outdoor & (d.wx_temp >= 85),
    "f_out_temp32": outdoor & (d.wx_temp <= 32),
    "g_out_precip_known": outdoor & d.wx_precip.notna(),
    "g_out_rain006": outdoor & (d.wx_precip >= 0.06),
    "g_out_precip_gt0": outdoor & (d.wx_precip > 0),
    "g_out_precip_ge001": outdoor & (d.wx_precip >= 0.01),
    "g_out_snow010": outdoor & (d.wx_snow >= 0.10),
    "i_pinnacle_total": pd.Series(False, index=d.index),  # no Pinnacle column exists in games.parquet
    "sbr_open_and_close": d.total_open.notna() & d.sbr_total_close.notna(),
}
F = pd.DataFrame(flags)


def table(mask, label):
    t = F[mask].groupby(d.season[mask]).sum().astype(int)
    t.loc["2016-2025"] = t.sum()
    t.loc["2020-2025"] = t.loc[[s for s in t.index if isinstance(s, (int, np.integer)) and s >= 2020]].sum()
    print(f"\n=== NFL {label} ===")
    print(t.T.to_string())


table(pd.Series(True, index=d.index), "REG + POST (all game types)")
table(~d.post, "REG only")
table(d.post, "POST only (WC/DIV/CON/SB)")

# ---------------------------------------------------------------- CLV / price-move SDs (price statistics)
s = pd.read_parquet(f"{ROOT}/data/raw/odds/sbr_open_close.parquet")
s["tmove"] = s.total_close - s.total_open
s["smove"] = s.spread_close - s.spread_open
print("\n=== sbr_open_close: seasons", s.season.min(), "-", s.season.max(), "rows", len(s))
per = s.groupby("season").agg(n=("tmove", "size"), n_total_both=("tmove", "count"), sd_total_move=("tmove", "std"),
                              mean_abs_total_move=("tmove", lambda x: x.abs().mean()), n_spread_both=("smove", "count"),
                              sd_spread_move=("smove", "std"), mean_abs_spread_move=("smove", lambda x: x.abs().mean()))
print(per.round(3).to_string())
print("\nALL 2007-2021: n_total=%d sd_total_move=%.3f mean_total_move=%+.3f | n_spread=%d sd_spread_move=%.3f mean_spread_move=%+.3f" % (
    s.tmove.count(), s.tmove.std(), s.tmove.mean(), s.smove.count(), s.smove.std(), s.smove.mean()))
s16 = s[s.season >= 2016]
print("2016-2021: n_total=%d sd_total_move=%.3f | n_spread=%d sd_spread_move=%.3f" % (
    s16.tmove.count(), s16.tmove.std(), s16.smove.count(), s16.smove.std()))

# repo's CLV proxy (simulate_decisions.py): windy outdoor games, open - close
w = g[g.wx_src.isin(["gamebook", "era5"]) & (g.wx_wind >= 15) & g.total_open.notna() & g.sbr_total_close.notna()]
clv = w.total_open - w.sbr_total_close
print("\nsimulate_decisions proxy (outdoor, wx_wind>=15, SBR open&close, all seasons): n=%d mean=%+.3f sd=%.3f seasons %d-%d" % (
    len(w), clv.mean(), clv.std(), w.season.min(), w.season.max()))
allg = g[g.total_open.notna() & g.sbr_total_close.notna()]
print("games.parquet merged SBR rows (all games): n=%d sd(open-close total)=%.3f" % (len(allg), (allg.total_open - allg.sbr_total_close).std()))

# CLV power: n = ((z_a + z_b) * sd / delta)^2, one-sided alpha 0.05, power 0.80
za, zb = 1.6448536, 0.8416212
print("\n=== NFL CLV power (n for mean CLV delta, one-sided 95%, 80% power) ===")
for lab, sd in (("all-games SBR total move sd", s.tmove.std()), ("windy-cohort proxy sd (repo)", clv.std())):
    for delta in (0.5, 1.0, 1.5):
        n = ((za + zb) * sd / delta) ** 2
        print(f"{lab:32s} sd={sd:.3f} delta={delta:.1f} -> n={np.ceil(n):.0f}")
