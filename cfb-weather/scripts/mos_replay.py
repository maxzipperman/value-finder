"""Replay CFB Rule B on GFS MOS forecasts as they were issued, 2006-25 (issue #40).

Every earlier long-run CFB Rule B number used the wind OBSERVED at the nearest airport. The
live rule bets on a FORECAST 1-3 days out, and the Open-Meteo replay (scripts/forecast_replay.py)
covers only 2024-25. The NWS's GFS MOS archive at the Iowa Environmental Mesonet has every run,
with its run time, back to 2000, so this replays the rule on forecasts that existed at bet time
for every season with closing totals.

* Games: FBS-involved, outdoor, venue coordinates, known kickoff, a closing total and a final
  score (scripts/mos_stations.eligible), at a venue with a GFS MOS station within 40 km
  (data/processed/mos_station_map.csv; the next-nearest is used when the nearest has no run).
* Forecast: MOS wind (knots -> mph) averaged over the kickoff hour and the next three, each hour
  interpolated between the 3-hourly MOS steps (cfbweather/mos.py says exactly how).
* Timing: lead L uses the last MOS run on date (kickoff's Eastern date - L), counted the way the
  live rule counts it; the run was published before that day's last alert run, so nothing uses
  information from after the bet. GFS MOS reaches 72 hours, so lead 3 rarely covers the window.
* Trigger (the primary, 1 variant): MOS wind >= 15 mph at any available lead 1-3. No calibration:
  MOS is already a station forecast. The threshold isn't tuned; the MOS-vs-observed bias table
  shows whether 15 mph on MOS means what 15 mph observed means.
* Entry: the consensus closing total (cfbfastR) at an assumed -110. Also graded at the opening
  total where one exists (cfbfastR's, else the median CFBD opener); the opener is usually posted
  before the forecast that fires, so it flatters the result, and the close understates it.
* Next to it: the same games on observed wind (the evidence STRATEGY.md cites), and for 2024-25
  the Open-Meteo replay (data/processed/forecast_replay.parquet).

Reads only the MOS cache (data/raw/mos/, filled by scripts/mos_fetch.py); fetches nothing.

    python scripts/mos_replay.py [--seasons 2023-2025]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np
import pandas as pd
from scipy import stats

from cfbweather import mos
from cfbweather.config import OUT, PROC, TABLES

WIND = 15.0                  # board.RULE_B_WIND; checked in tests/test_mos.py
ENTRY_ODDS = -110
BREAK_EVEN = 110 / 210
VARIANTS_BEFORE = 200        # STATUS.md running total on Sep 29, 2026; this adds 1 (NFL's replay adds another)
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
    """ROI per bet at -110 for a win rate p over decided bets (pushes excluded)."""
    return p * (100 / abs(ENTRY_ODDS)) - (1 - p)


def openers(g: pd.DataFrame) -> pd.Series:
    """cfbfastR's consensus opening total, else the median CFBD opener across providers."""
    c = pd.read_parquet(PROC / "cfbd_lines.parquet", columns=["game_id", "total_open"])
    c = c.dropna().groupby("game_id").total_open.median()
    return g.open_total.fillna(g.game_id.map(c))


def obs_icao(d: pd.DataFrame, smap: pd.DataFrame) -> pd.Series:
    """ICAO id of the station each game's observed wind came from (games.parquet wx_station is a
    Meteostat id). Uses Meteostat's station list when it's on disk, else the map's nearest station."""
    try:
        from mos_stations import meteostat_icao
        ids = meteostat_icao()
        return d.wx_station.map(ids).fillna("")
    except OSError:
        return d.venue_id.map(smap[smap["rank"] == 0].set_index("venue_id").obs_icao).fillna("")


def attach_mos(g: pd.DataFrame, smap: pd.DataFrame) -> pd.DataFrame:
    """Per game: MOS wind at leads 1-3 from the nearest station with runs (rank 0, else 1, else 2)."""
    rows = []
    cache = {}
    ranks = smap.sort_values("rank").groupby("venue_id")[["icao", "km", "rank"]].apply(
        lambda d: list(d.itertuples(index=False, name=None))).to_dict()
    for r in g.itertuples():
        out = dict(game_id=r.game_id, mos_station="", mos_km=np.nan, mos_rank=np.nan)
        for n in LEADS:
            out[f"mos{n}_mph"] = np.nan
            out[f"mos{n}_runtime"] = pd.NaT
        for icao, km, rank in ranks.get(r.venue_id, []):
            if icao not in cache:
                cache[icao] = mos.load_station(icao)
            sel = mos.select_runs(cache[icao], r.start_utc)
            if all(v is None for v in sel.values()):
                continue
            out.update(mos_station=icao, mos_km=km, mos_rank=rank)
            for n, v in sel.items():
                if v is not None:
                    out[f"mos{n}_mph"] = v["wind_mph"]
                    out[f"mos{n}_runtime"] = v["runtime"]
                    out[f"mos{n}_bet_by_utc"] = v["bet_by_utc"]
            break
        rows.append(out)
    return g.merge(pd.DataFrame(rows), on="game_id", how="left")


def replay(g: pd.DataFrame) -> pd.DataFrame:
    d = g.copy()
    have = [f"mos{n}_mph" for n in LEADS]
    d["has_mos"] = d[have].notna().any(axis=1)
    trig = pd.DataFrame({n: d[f"mos{n}_mph"] >= WIND for n in LEADS})
    d["mos_signal"] = trig.any(axis=1)
    d["first_lead"] = trig.apply(lambda t: max([n for n in LEADS if t[n]], default=np.nan), axis=1)
    d["mos_max_mph"] = d[have].max(axis=1)
    d["obs_signal"] = d.wx_wind >= WIND
    d["push"] = d.total == d.close_total
    d["under_win"] = d.total < d.close_total
    d["profit"] = np.where(d.push, 0.0, np.where(d.under_win, 100 / abs(ENTRY_ODDS), -1.0))
    d["opener"] = openers(d)
    d["opener_push"] = d.total == d.opener
    d["opener_win"] = d.total < d.opener
    d["opener_move"] = d.close_total - d.opener
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
    seasons = sorted(d.season.unique())
    for label, s in [(str(x), d[d.season == x]) for x in seasons] + [("pooled", d)]:
        m = s[s.has_mos]
        sig = m[m.mos_signal]
        row = dict(sample=label, games=len(s), with_mos=len(m), **{f"lead{n}": int(m[f"mos{n}_mph"].notna().sum())
                                                                    for n in LEADS})
        row.update(grade(sig, prefix="close_"))
        op = sig[sig.opener.notna()]
        row.update(grade(op, "opener_win", "opener_push", prefix="open_"))
        row["open_move_mean"] = round(op.opener_move.mean(), 2) if len(op) else np.nan
        obs = m[m.obs_signal & m.wx_wind.notna()]
        row.update(grade(obs, prefix="obs_"))
        b = m[m.mos1_mph.notna() & m.wx_wind.notna()]
        row.update(l1_bias=round((b.mos1_mph - b.wx_wind).mean(), 2) if len(b) else np.nan,
                   l1_mos15_pct=round(100 * (b.mos1_mph >= WIND).mean(), 1) if len(b) else np.nan,
                   obs15_pct=round(100 * (b.wx_wind >= WIND).mean(), 1) if len(b) else np.nan,
                   sig_obs15_pct=round(100 * (sig.wx_wind >= WIND).mean(), 1) if len(sig) else np.nan)
        out.append(row)
    return pd.DataFrame(out)


def bias_table(d: pd.DataFrame) -> pd.DataFrame:
    """MOS minus observed station wind (mph), by lead, on every game with both."""
    out = []
    for n in LEADS:
        col = f"mos{n}_mph"
        for label, s in (("all", d), ("same airport", d[d.same_as_obs]), ("different airport", d[~d.same_as_obs])):
            s = s[s[col].notna() & s.wx_wind.notna()]
            if len(s) < MIN_BIAS_N:
                continue
            e = s[col] - s.wx_wind
            out.append(dict(lead=n, stations=label, n=len(s), mean_error=round(e.mean(), 2),
                            mae=round(e.abs().mean(), 2), rmse=round(float(np.sqrt((e ** 2).mean())), 2),
                            corr=round(s[col].corr(s.wx_wind), 3),
                            mos_ge15_pct=round(100 * (s[col] >= WIND).mean(), 2),
                            obs_ge15_pct=round(100 * (s.wx_wind >= WIND).mean(), 2),
                            mos_mean=round(s[col].mean(), 2), obs_mean=round(s.wx_wind.mean(), 2)))
    return pd.DataFrame(out)


def openmeteo_compare(d: pd.DataFrame) -> list[str]:
    p = PROC / "forecast_replay.parquet"
    if not p.exists():
        return ["  (no data/processed/forecast_replay.parquet)"]
    f = pd.read_parquet(p, columns=["game_id", "fc1_wind", "fc2_wind", "fc3_wind", "fc_signal", "first_lead"])
    f = f.rename(columns={"first_lead": "om_first_lead"})
    m = d.merge(f, on="game_id", how="inner")
    lines = [f"  games in both replays (2024-25): {len(m)}"]
    for n in LEADS:
        s = m[m[f"mos{n}_mph"].notna() & m[f"fc{n}_wind"].notna()]
        if not len(s):
            lines.append(f"  lead {n}: no games with both")
            continue
        e = s[f"mos{n}_mph"] - s[f"fc{n}_wind"]
        eo = s[f"fc{n}_wind"] - s.wx_wind
        em = s[f"mos{n}_mph"] - s.wx_wind
        lines.append(f"  lead {n} (n={len(s)}): MOS minus Open-Meteo (station scale) {e.mean():+.2f} mph, "
                     f"corr {s[f'mos{n}_mph'].corr(s[f'fc{n}_wind']):.2f}; vs observed: MOS MAE {em.abs().mean():.2f}, "
                     f"Open-Meteo MAE {eo.abs().mean():.2f}")
    both = m[m.has_mos]
    om_sig, mos_sig = both.fc_signal.astype(bool), both.mos_signal.astype(bool)
    fmt = lambda s: "{}-{}-{}".format(*record(s))
    lines += [f"  signals on the same {len(both)} games: MOS {int(mos_sig.sum())} ({fmt(both[mos_sig])}), "
              f"Open-Meteo {int(om_sig.sum())} ({fmt(both[om_sig])}), both {int((mos_sig & om_sig).sum())}",
              f"  Open-Meteo signals that fired only at lead 3 (which GFS MOS rarely reaches): "
              f"{int((om_sig & (both.fc1_wind < WIND) & (both.fc2_wind < WIND)).sum())} of {int(om_sig.sum())}"]
    return lines


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seasons", help="e.g. 2023-2025 (default 2006-2025)")
    args = ap.parse_args()
    from mos_fetch import parse_seasons
    from mos_stations import eligible
    seasons = parse_seasons(args.seasons)

    g = pd.read_parquet(PROC / "games.parquet")
    g = g[eligible(g) & g.season.between(*seasons)].copy()
    smap = pd.read_csv(PROC / "mos_station_map.csv")
    n_all = len(g)
    g = g[g.venue_id.isin(smap.venue_id)].copy()
    d = replay(attach_mos(g, smap))
    d["obs_icao"] = obs_icao(d, smap)
    d["same_as_obs"] = d.mos_station.ne("") & d.mos_station.eq(d.obs_icao)
    tab = season_table(d)
    bias = bias_table(d[d.has_mos])

    keep = ["game_id", "season", "week", "season_type", "start_utc", "home_team", "away_team", "venue_id", "venue",
            "mos_station", "mos_km", "mos_rank", "same_as_obs",
            *[c for n in LEADS for c in (f"mos{n}_mph", f"mos{n}_runtime")], "has_mos", "mos_max_mph", "mos_signal",
            "first_lead", "wx_station", "obs_icao", "wx_wind", "obs_signal", "close_total", "opener", "opener_move", "total",
            "under_win", "push", "profit", "opener_win", "opener_push"]
    tag = "" if seasons == (2006, 2025) else f"_{seasons[0]}_{seasons[1]}"
    d[keep].to_parquet(PROC / f"mos_replay{tag}.parquet", index=False)
    TABLES.mkdir(parents=True, exist_ok=True)
    tab.to_csv(TABLES / f"mos_replay_seasons{tag}.csv", index=False)
    bias.to_csv(TABLES / f"mos_bias{tag}.csv", index=False)

    m = d[d.has_mos]
    sig = m[m.mos_signal]
    pooled = tab[tab["sample"] == "pooled"].iloc[0]
    bar = 0.05 / (VARIANTS_BEFORE + 2)
    lines = [f"CFB Rule B replay on GFS MOS forecasts as issued, {seasons[0]}-{seasons[1]} "
             f"(trigger: MOS wind >= {WIND:.0f} mph at lead 1-3; entry at the close, -110)",
             f"  eligible games {n_all}; at a venue with a MOS station within {mos.MAX_KM:.0f} km {len(g)}; "
             f"with a MOS forecast at some lead {len(m)} (none: {len(g) - len(m)})",
             f"  games by lead available: " + ", ".join(f"lead {n} {int(m[f'mos{n}_mph'].notna().sum())}" for n in LEADS),
             f"  forecast station: nearest {int((m.mos_rank == 0).sum())}, next-nearest {int((m.mos_rank > 0).sum())}; "
             f"same airport as the observed wind {int(m.same_as_obs.sum())}", ""]
    cols1 = ["sample", "games", "with_mos", "lead1", "lead2", "lead3", "close_n", "close_record", "close_win_pct",
             "close_win_ci", "close_roi_pct", "close_roi_ci", "close_p_one_sided"]
    cols2 = ["sample", "open_n", "open_record", "open_win_pct", "open_win_ci", "open_roi_pct", "open_move_mean",
             "obs_n", "obs_record", "obs_win_pct", "obs_win_ci", "obs_roi_pct"]
    with pd.option_context("display.width", 250, "display.max_columns", 40):
        lines += ["At the close (the primary):", tab[cols1].to_string(index=False), "",
                  "At the opener (where one exists), and the same games on OBSERVED wind at the close:",
                  tab[cols2].to_string(index=False), "",
                  "MOS minus observed station wind, mph (observed = the 4-hour kickoff mean the backtests use):",
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
              f"  MOS only (the wind didn't arrive): {len(fco)} games, {fmt(fco)}",
              f"  observed only (MOS missed it): {len(obo)} games, {fmt(obo)}",
              f"  MOS signals by first lead: {sig.first_lead.value_counts().sort_index().to_dict()}",
              "", "Against Open-Meteo, 2024-25 (step 3 of the issue):", *openmeteo_compare(d), "",
              f"Multiple testing: 1 variant for CFB (running total {VARIANTS_BEFORE} + this + the NFL replay = "
              f"{VARIANTS_BEFORE + 2}); Bonferroni bar p < {bar:.5f}. Pooled one-sided p = {pooled.close_p_one_sided}."]
    text = "\n".join(lines)
    (OUT / f"mos_replay{tag}.log").write_text(text + "\n")
    print(text)


if __name__ == "__main__":
    main()
