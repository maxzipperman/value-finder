"""Replay NFL Rule B on GFS MOS forecasts as they were issued, 2004-25 (issue #40).

The NFL Rule B evidence (57.2% under vs the close in 682 observed-wind games since 1999, STRATEGY.md)
uses the wind OBSERVED at kickoff (the game book). The live rule bets on a FORECAST 1-3 days
out. This replays it on the NWS GFS MOS archive at the Iowa Environmental Mesonet, which keeps
every run with its run time.

* Games: outdoor (roof "outdoors"), 2004-25, a closing total and a final score, at a stadium
  with a GFS MOS station within 40 km (data/processed/mos_station_map.csv, scripts/mos_fetch.py).
* Forecast: MOS wind (knots -> mph) at the kickoff instant, interpolated between the 3-hourly
  MOS steps, as the live rule reads its forecast at kickoff (nflweather/weather.summarize_hourly).
* Timing: lead L uses the last MOS run on date (kickoff's Eastern date - L), the way amendment 5
  counts lead time; the run was published before that day's last alert run (nflweather/mos.py).
* Trigger (the primary, 1 variant): MOS wind >= 15 mph at any available lead 1-3. MOS is an
  airport forecast and the rule's scale is the game book's stadium wind; the bias table shows
  how the two compare. The threshold isn't tuned.
* Entry: the closing total (nflverse total_line) at an assumed -110. Also: at nflverse's under
  price where it exists, with the board's -115 cap; and at the SBR opener (2007-21).
* Next to it: the same games on observed (game-book) wind, and for 2024-25 the Open-Meteo
  previous-run forecasts on the frozen calibration.

Reads only the MOS cache (data/raw/mos/); fetches nothing.

    python scripts/mos_replay.py [--seasons 2023-2025]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np
import pandas as pd
from scipy import stats

from nflweather import mos
from nflweather.config import OUT, PROC, TABLES

WIND = 15.0                  # board.RULE_B_WIND
ENTRY_ODDS = -110
MIN_UNDER_ODDS = -115        # market.MIN_UNDER_ODDS, the board's price cap
BREAK_EVEN = 110 / 210
VARIANTS_BEFORE = 200        # STATUS.md running total on Sep 29, 2026; the CFB replay adds 1, this adds 1
LEADS = mos.LEADS
MIN_BIAS_N = 20             # a lead with fewer games with both winds gets no bias row


def wilson(w, n, z=1.96):
    if n == 0:
        return np.nan, np.nan
    p = w / n
    c = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    m = (p + z * z / (2 * n)) / (1 + z * z / n)
    return m - c, m + c


def roi_from_rate(p):
    return p * (100 / abs(ENTRY_ODDS)) - (1 - p)


def attach_mos(g: pd.DataFrame, smap: pd.DataFrame) -> pd.DataFrame:
    rows, cache = [], {}
    ranks = smap.sort_values("rank").groupby("stadium_key")[["icao", "km", "rank"]].apply(
        lambda d: list(d.itertuples(index=False, name=None))).to_dict()
    for r in g.itertuples():
        out = dict(game_id=r.game_id, mos_station="", mos_km=np.nan, mos_rank=np.nan)
        for n in LEADS:
            out[f"mos{n}_mph"], out[f"mos{n}_runtime"] = np.nan, pd.NaT
        for icao, km, rank in ranks.get(r.stadium_key, []):
            if icao not in cache:
                cache[icao] = mos.load_station(icao)
            sel = mos.select_runs(cache[icao], r.start_utc, how="kickoff")
            if all(v is None for v in sel.values()):
                continue
            out.update(mos_station=icao, mos_km=km, mos_rank=rank)
            for n, v in sel.items():
                if v is not None:
                    out[f"mos{n}_mph"], out[f"mos{n}_runtime"] = v["wind_mph"], v["runtime"]
            break
        rows.append(out)
    return g.merge(pd.DataFrame(rows), on="game_id", how="left")


def american_profit(odds):
    o = pd.to_numeric(odds, errors="coerce")
    return np.where(o > 0, o / 100, 100 / o.abs())


def replay(g: pd.DataFrame) -> pd.DataFrame:
    d = g.copy()
    have = [f"mos{n}_mph" for n in LEADS]
    d["has_mos"] = d[have].notna().any(axis=1)
    trig = pd.DataFrame({n: d[f"mos{n}_mph"] >= WIND for n in LEADS})
    d["mos_signal"] = trig.any(axis=1)
    d["first_lead"] = trig.apply(lambda t: max([n for n in LEADS if t[n]], default=np.nan), axis=1)
    d["obs_signal"] = d.wx_wind >= WIND
    d["push"] = d.total == d.total_line
    d["under_win"] = d.total < d.total_line
    d["price_ok"] = d.under_odds.notna() & (d.under_odds >= MIN_UNDER_ODDS)
    d["profit_at_price"] = np.where(d.push, 0.0, np.where(d.under_win, american_profit(d.under_odds), -1.0))
    d["opener_push"] = d.total == d.total_open
    d["opener_win"] = d.total < d.total_open
    d["opener_move"] = d.total_line - d.total_open
    return d


def record(d, win="under_win", push="push"):
    w, p = int(d[win].sum()), int(d[push].sum())
    return w, len(d) - w - p, p


def grade(d, win="under_win", push="push", prefix=""):
    w, l, p = record(d, win, push)
    n = w + l
    lo, hi = wilson(w, n)
    pv = stats.binomtest(w, n, BREAK_EVEN, alternative="greater").pvalue if n else np.nan
    return {f"{prefix}n": len(d), f"{prefix}record": f"{w}-{l}-{p}",
            f"{prefix}win_pct": round(100 * w / n, 1) if n else np.nan,
            f"{prefix}win_ci": f"{100 * lo:.1f}-{100 * hi:.1f}" if n else "",
            f"{prefix}roi_pct": round(100 * roi_from_rate(w / n), 1) if n else np.nan,
            f"{prefix}roi_ci": f"{100 * roi_from_rate(lo):+.1f} to {100 * roi_from_rate(hi):+.1f}" if n else "",
            f"{prefix}p_one_sided": round(pv, 4) if n else np.nan}


def season_table(d: pd.DataFrame) -> pd.DataFrame:
    out = []
    for label, s in [(str(x), d[d.season == x]) for x in sorted(d.season.unique())] + [("pooled", d)]:
        m = s[s.has_mos]
        sig = m[m.mos_signal]
        row = dict(sample=label, games=len(s), with_mos=len(m),
                   **{f"lead{n}": int(m[f"mos{n}_mph"].notna().sum()) for n in LEADS})
        row.update(grade(sig, prefix="close_"))
        pr = sig[sig.price_ok]
        w, l, p = record(pr)
        row.update(price_n=len(pr), price_record=f"{w}-{l}-{p}",
                   price_roi_pct=round(100 * pr.profit_at_price.sum() / max(w + l, 1), 1) if len(pr) else np.nan)
        op = sig[sig.total_open.notna()]
        row.update(grade(op, "opener_win", "opener_push", prefix="open_"))
        row["open_move_mean"] = round(op.opener_move.mean(), 2) if len(op) else np.nan
        row.update(grade(m[m.obs_signal], prefix="obs_"))
        b = m[m.mos1_mph.notna() & m.wx_wind.notna()]
        row.update(l1_bias=round((b.mos1_mph - b.wx_wind).mean(), 2) if len(b) else np.nan,
                   l1_mos15_pct=round(100 * (b.mos1_mph >= WIND).mean(), 1) if len(b) else np.nan,
                   obs15_pct=round(100 * (b.wx_wind >= WIND).mean(), 1) if len(b) else np.nan,
                   sig_obs15_pct=round(100 * (sig.wx_wind >= WIND).mean(), 1) if len(sig) else np.nan)
        out.append(row)
    return pd.DataFrame(out)


def bias_table(d: pd.DataFrame) -> pd.DataFrame:
    out = []
    for n in LEADS:
        col = f"mos{n}_mph"
        for label, s in (("all", d), ("game book", d[d.wx_src == "gamebook"])):
            s = s[s[col].notna() & s.wx_wind.notna()]
            if len(s) < MIN_BIAS_N:
                continue
            e = s[col] - s.wx_wind
            out.append(dict(lead=n, observed=label, n=len(s), mean_error=round(e.mean(), 2), mae=round(e.abs().mean(), 2),
                            rmse=round(float(np.sqrt((e ** 2).mean())), 2), corr=round(s[col].corr(s.wx_wind), 3),
                            mos_ge15_pct=round(100 * (s[col] >= WIND).mean(), 2),
                            obs_ge15_pct=round(100 * (s.wx_wind >= WIND).mean(), 2),
                            mos_mean=round(s[col].mean(), 2), obs_mean=round(s.wx_wind.mean(), 2)))
    return pd.DataFrame(out)


def openmeteo_compare(d: pd.DataFrame) -> list[str]:
    cal = json.loads((PROC / "calibration.json").read_text())
    m = d[d.has_mos & d.fc1_wind.notna()].copy()
    if not len(m):
        return ["  no games with both"]
    lines = [f"  games with both (2023-25): {len(m)}"]
    for n in LEADS:
        m[f"om{n}"] = (cal["wind_intercept"] + cal["wind_slope"] * m[f"fc{n}_wind"]).clip(lower=0)
        s = m[m[f"mos{n}_mph"].notna() & m[f"om{n}"].notna()]
        if not len(s):
            lines.append(f"  lead {n}: no games with both")
            continue
        lines.append(f"  lead {n} (n={len(s)}): MOS minus Open-Meteo (game-book scale) "
                     f"{(s[f'mos{n}_mph'] - s[f'om{n}']).mean():+.2f} mph, corr {s[f'mos{n}_mph'].corr(s[f'om{n}']):.2f}; "
                     f"vs game-book wind: MOS MAE {(s[f'mos{n}_mph'] - s.wx_wind).abs().mean():.2f}, "
                     f"Open-Meteo MAE {(s[f'om{n}'] - s.wx_wind).abs().mean():.2f}")
    om_sig = pd.concat([m[f"om{n}"] >= WIND for n in LEADS], axis=1).any(axis=1)
    fmt = lambda s: "{}-{}-{}".format(*record(s))
    lines.append(f"  signals: MOS {int(m.mos_signal.sum())} ({fmt(m[m.mos_signal])}), Open-Meteo {int(om_sig.sum())} "
                 f"({fmt(m[om_sig])}), both {int((m.mos_signal & om_sig).sum())}")
    return lines


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seasons", help="e.g. 2023-2025 (default 2004-2025)")
    args = ap.parse_args()
    from mos_fetch import eligible_games, parse_seasons
    seasons = parse_seasons(args.seasons)
    g = eligible_games(seasons)
    smap = pd.read_csv(PROC / "mos_station_map.csv")
    n_all = len(g)
    g = g[g.stadium_key.isin(smap.stadium_key)].copy()
    d = replay(attach_mos(g, smap))
    tab, bias = season_table(d), bias_table(d[d.has_mos])

    keep = ["game_id", "season", "week", "gameday", "gametime", "start_utc", "away_team", "home_team", "stadium_key",
            "mos_station", "mos_km", "mos_rank", *[c for n in LEADS for c in (f"mos{n}_mph", f"mos{n}_runtime")],
            "has_mos", "mos_signal", "first_lead", "wx_src", "wx_wind", "obs_signal", "total_line", "under_odds",
            "price_ok", "total_open", "opener_move", "total", "under_win", "push", "opener_win", "opener_push"]
    tag = "" if seasons == (2004, 2025) else f"_{seasons[0]}_{seasons[1]}"
    d[keep].to_parquet(PROC / f"mos_replay{tag}.parquet", index=False)
    TABLES.mkdir(parents=True, exist_ok=True)
    tab.to_csv(TABLES / f"mos_replay_seasons{tag}.csv", index=False)
    bias.to_csv(TABLES / f"mos_bias{tag}.csv", index=False)

    m = d[d.has_mos]
    sig = m[m.mos_signal]
    pooled = tab[tab["sample"] == "pooled"].iloc[0]
    bar = 0.05 / (VARIANTS_BEFORE + 2)
    lines = [f"NFL Rule B replay on GFS MOS forecasts as issued, {seasons[0]}-{seasons[1]} "
             f"(trigger: MOS wind at kickoff >= {WIND:.0f} mph at lead 1-3; entry at the close, -110)",
             f"  eligible outdoor games {n_all}; at a stadium with a MOS station within {mos.MAX_KM:.0f} km {len(g)}; "
             f"with a MOS forecast at some lead {len(m)} (none: {len(g) - len(m)})",
             "  games by lead available: " + ", ".join(f"lead {n} {int(m[f'mos{n}_mph'].notna().sum())}" for n in LEADS), ""]
    cols1 = ["sample", "games", "with_mos", "lead1", "lead2", "lead3", "close_n", "close_record", "close_win_pct",
             "close_win_ci", "close_roi_pct", "close_roi_ci", "close_p_one_sided"]
    cols2 = ["sample", "price_n", "price_record", "price_roi_pct", "open_n", "open_record", "open_win_pct",
             "open_move_mean", "obs_n", "obs_record", "obs_win_pct", "obs_win_ci"]
    with pd.option_context("display.width", 250, "display.max_columns", 40):
        lines += ["At the close (the primary):", tab[cols1].to_string(index=False), "",
                  "At nflverse's under price where it is -115 or better; at the SBR opener (2007-21); and the same "
                  "games on OBSERVED (game-book) wind at the close:", tab[cols2].to_string(index=False), "",
                  "MOS minus observed kickoff wind, mph (observed = game book, else calibrated ERA5):",
                  bias.to_string(index=False), "",
                  "Does 15 mph on MOS mean what 15 mph observed means? By season, lead 1: mean MOS minus observed "
                  "(l1_bias), share of games at 15+ on MOS and observed, and the share of MOS signals whose observed "
                  "wind reached 15:",
                  tab[["sample", "l1_bias", "l1_mos15_pct", "obs15_pct", "sig_obs15_pct"]].to_string(index=False)]
    both, fco, obo = sig[sig.obs_signal], sig[~sig.obs_signal], m[~m.mos_signal & m.obs_signal]
    pct = lambda s: f"{100 * s.under_win.sum() / max(len(s) - s.push.sum(), 1):.1f}%"
    fmt = lambda s: "{}-{}-{}".format(*record(s)) + f" ({pct(s)})"
    lines += ["", "Where the result sits (descriptive; these splits are not rules):",
              f"  MOS and observed both >= 15: {len(both)} games, {fmt(both)}",
              f"  MOS only: {len(fco)} games, {fmt(fco)}",
              f"  observed only: {len(obo)} games, {fmt(obo)}",
              f"  MOS signals by first lead: {sig.first_lead.value_counts().sort_index().to_dict()}",
              "", "Against Open-Meteo previous runs (step 3 of the issue):", *openmeteo_compare(d), "",
              f"Multiple testing: 1 variant for NFL (running total {VARIANTS_BEFORE} + the CFB replay + this = "
              f"{VARIANTS_BEFORE + 2}); Bonferroni bar p < {bar:.5f}. Pooled one-sided p = {pooled.close_p_one_sided}."]
    text = "\n".join(lines)
    (OUT / f"mos_replay{tag}.log").write_text(text + "\n")
    print(text)


if __name__ == "__main__":
    main()
