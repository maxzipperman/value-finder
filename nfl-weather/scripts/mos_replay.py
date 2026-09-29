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

Added for the full 2004-25 run (descriptive; the selection and grading above are unchanged):
grading at SBR's own close (2007-21), coverage by season and lead with the reason for every
missing forecast (output/tables/mos_coverage.csv, mos_no_forecast.csv), MOS against observed
wind by season and lead (mos_bias_by_season.csv), and the pooled result with the three era cuts
declared before the run, each also with standard errors grouped by game day (mos_replay_eras.csv).

Reads only the MOS cache (data/raw/mos/); fetches nothing.

    python scripts/mos_replay.py [--seasons 2023-2025]
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, timedelta
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
# The running count on main is 271 (STATUS.md, Sep 29, 2026), which already counts the CFB replay (PR 61).
# This replay adds 1, and one cut looked at after its results (the seasons outside 2007-21) adds 1, because
# every look is counted: 273, bar p < 0.05 / 273 = 0.000183 (hub decision, Sep 29, PR 65).
VARIANTS_BEFORE = 271
LEADS = mos.LEADS
MIN_BIAS_N = 20             # a lead with fewer games with both winds gets no bias row
# Era cuts, declared before the 2004-25 run (issue #40 brief, Sep 29): descriptive, 0 variants.
ERAS = (("2004-14", 2004, 2014), ("2015-25", 2015, 2025), ("last five, 2021-25", 2021, 2025))
OBSERVED_HISTORY = "57.2% in 682 observed-wind games since 1999 (STRATEGY.md)"
SAME_DAY_RHO = 0.1           # same-day correlation of line moves, paper-to-money study (#51)


def wilson(w, n, z=1.96):
    if n == 0:
        return np.nan, np.nan
    p = w / n
    c = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    m = (p + z * z / (2 * n)) / (1 + z * z / n)
    return m - c, m + c


def roi_from_rate(p):
    return p * (100 / abs(ENTRY_ODDS)) - (1 - p)


def attach_mos(g: pd.DataFrame, smap: pd.DataFrame, cache: dict | None = None) -> pd.DataFrame:
    """Per game: MOS wind at the kickoff instant, leads 1-3, from the nearest station with runs
    (rank 0, else 1, else 2). `cache` (station -> its runs) is filled as stations are read."""
    rows = []
    cache = {} if cache is None else cache
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
    d["sbr_close_push"] = d.total == d.sbr_total_close          # SBR's own close, 2007-21
    d["sbr_close_win"] = d.total < d.sbr_total_close
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
        row.update(grade(op, prefix="closeop_"))        # the nflverse close on the same games as the SBR opener
        row["open_move_mean"] = round(op.opener_move.mean(), 2) if len(op) else np.nan
        row.update(grade(sig[sig.sbr_total_close.notna()], "sbr_close_win", "sbr_close_push", prefix="sbrclose_"))
        # every game whose OBSERVED wind reached 15, among all games with a forecast: not the forecast signals
        obs = m[m.obs_signal]
        row.update(grade(obs, prefix="obs_"))
        row["obs_also_signal"] = int(obs.mos_signal.sum())
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


def matched_threshold(fc: pd.Series, obs: pd.Series) -> float:
    """The observed wind reached as often as the forecast reaches 15 mph, on games with both."""
    return float(obs.quantile(1 - (fc >= WIND).mean()))


def bias_by_season(d: pd.DataFrame) -> pd.DataFrame:
    """MOS minus observed kickoff wind (mph) by season and lead, and how often each reaches 15 mph.

    matched_obs_mph: the observed wind reached as often as MOS reaches 15 (by frequency)."""
    out = []
    for season, s0 in [(str(x), d[d.season == x]) for x in sorted(d.season.unique())] + [("all", d)]:
        for n in LEADS:
            col = f"mos{n}_mph"
            s = s0[s0[col].notna() & s0.wx_wind.notna()]
            if len(s) < MIN_BIAS_N:
                continue
            e = s[col] - s.wx_wind
            out.append(dict(season=season, lead=n, n=len(s), mean_error=round(e.mean(), 2), mae=round(e.abs().mean(), 2),
                            rmse=round(float(np.sqrt((e ** 2).mean())), 2), corr=round(s[col].corr(s.wx_wind), 3),
                            mos_ge15_pct=round(100 * (s[col] >= WIND).mean(), 2),
                            obs_ge15_pct=round(100 * (s.wx_wind >= WIND).mean(), 2),
                            matched_obs_mph=round(matched_threshold(s[col], s.wx_wind), 2)))
    return pd.DataFrame(out)


def grouped(d: pd.DataFrame, win="under_win", push="push") -> dict:
    """Win rate over decided bets with its standard error grouped by game day (the kickoff's Eastern
    date; CR1 cluster-robust), because signals on the same day are not independent. Also the design
    effect, interval and p-value that a same-day correlation of SAME_DAY_RHO would give at these day sizes."""
    s = d[~d[push].astype(bool)]
    n = len(s)
    if n < 2:
        return dict(days=0, per_day=np.nan, grouped_ci="", grouped_p=np.nan, deff=np.nan, deff_rho=np.nan,
                    rho_ci="", rho_p=np.nan)
    y = s[win].astype(float).to_numpy()
    p = y.mean()
    day = pd.Series([mos.kick_date(k) for k in s.start_utc], index=s.index)
    sums = pd.Series(y - p, index=s.index).groupby(day).sum()
    G = len(sums)
    se = float(np.sqrt(G / (G - 1) * (sums ** 2).sum() / n ** 2))
    se_bin = float(np.sqrt(p * (1 - p) / n))
    size = day.value_counts()
    m_w = float((size ** 2).sum() / size.sum())       # the average day size a bet sits in
    deff_rho = 1 + (m_w - 1) * SAME_DAY_RHO
    se_rho = se_bin * np.sqrt(deff_rho)
    return dict(days=G, per_day=round(n / G, 2),
                grouped_ci=f"{100 * (p - 1.96 * se):.1f}-{100 * (p + 1.96 * se):.1f}",
                grouped_roi_ci=f"{100 * roi_from_rate(p - 1.96 * se):+.1f} to {100 * roi_from_rate(p + 1.96 * se):+.1f}",
                grouped_p=round(float(stats.norm.sf((p - BREAK_EVEN) / se)), 4) if se > 0 else np.nan,
                deff=round((se / se_bin) ** 2, 2), deff_rho=round(deff_rho, 2),
                rho_ci=f"{100 * (p - 1.96 * se_rho):.1f}-{100 * (p + 1.96 * se_rho):.1f}",
                rho_p=round(float(stats.norm.sf((p - BREAK_EVEN) / se_rho)), 4))


def era_table(d: pd.DataFrame, eras=ERAS) -> pd.DataFrame:
    """The pooled result and the declared era cuts: close, grouped by game day, SBR opener (with the nflverse
    close on the same games) and SBR close, and observed wind >= 15 in the same pool of games.

    Each era is clipped to the seasons in `d` (a --seasons run); an era with none of them is left out,
    and a clipped one says so in its label, so a partial run never prints an era it didn't cover."""
    m = d[d.has_mos]
    first, last = int(d.season.min()), int(d.season.max())
    out = []
    for label, a, b in (("pooled", first, last),) + tuple(eras):
        a2, b2 = max(a, first), min(b, last)
        if a2 > b2:
            continue
        if (a2, b2) != (a, b):
            label = f"{label}, only {a2}-{b2} run"
        s = m[m.season.between(a2, b2)]
        sig = s[s.mos_signal]
        row = dict(sample=label, seasons=f"{a2}-{b2}", games=len(s), per_season=round(len(sig) / (b2 - a2 + 1), 1))
        row.update(grade(sig, prefix="close_"))
        row.update(grouped(sig))
        op = sig[sig.total_open.notna()]
        row.update(grade(op, "opener_win", "opener_push", prefix="open_"))
        row.update(grade(op, prefix="closeop_"))
        row.update(grade(sig[sig.sbr_total_close.notna()], "sbr_close_win", "sbr_close_push", prefix="sbrclose_"))
        obs = s[s.obs_signal & s.wx_wind.notna()]
        row.update(grade(obs, prefix="obs_"))
        row["obs_also_signal"] = int(obs.mos_signal.sum())
        out.append(row)
    return pd.DataFrame(out)


def coverage(g_all: pd.DataFrame, d: pd.DataFrame, smap: pd.DataFrame, cache: dict, how="kickoff") -> pd.DataFrame:
    """Per eligible game and lead: "forecast", or why there is none.

    "no station within 40 km"; "empty answer" (every station within 40 km that was asked answered
    with no runs or no wind for that season); "not downloaded" (no station asked); or, at a
    station with runs that season, mos.lead_status's reason ("no run that day", "run ends before
    the window", "gap or no wind"). `detail` names each station tried and what it held."""
    ranks = smap.sort_values("rank").groupby("stadium_key").icao.apply(list).to_dict()
    used = d.set_index("game_id")
    answers = {}

    def answer(icao, kd):
        sts = pd.Timestamp(kd - pd.Timedelta(days=max(LEADS)))
        ets = pd.Timestamp(kd - pd.Timedelta(days=min(LEADS))) + pd.Timedelta(hours=18)
        p = mos.cached_cover(icao, sts, ets)
        if p is None:
            return "not downloaded"
        if p not in answers:
            answers[p] = mos.file_status(p)
        return answers[p]

    asked_memo = {}

    def asked(icao, day):
        """Whether a cached answer covers the runs of this date (00Z to 18Z)."""
        if (icao, day) not in asked_memo:
            asked_memo[icao, day] = mos.cached_cover(icao, pd.Timestamp(day), pd.Timestamp(day) + pd.Timedelta(hours=18)) \
                is not None
        return asked_memo[icao, day]

    rows = []
    for r in g_all.itertuples():
        base = dict(game_id=r.game_id, season=r.season)
        stations = ranks.get(r.stadium_key, [])
        if not stations:
            rows += [dict(base, lead=n, status="no station within 40 km", detail="") for n in LEADS]
            continue
        u = used.loc[r.game_id]
        if u.mos_station:
            runs = cache[u.mos_station]
            for n in LEADS:
                if pd.notna(u[f"mos{n}_mph"]):
                    st = "forecast"
                elif not asked(u.mos_station, mos.kick_date(r.start_utc) - timedelta(days=n)):
                    st = "not downloaded"     # e.g. a station borrowed from the other sport's download
                else:
                    st = mos.lead_status(runs, r.start_utc, n, how)
                rows.append(dict(base, lead=n, status=st, detail=u.mos_station))
            continue
        kd = mos.kick_date(r.start_utc)
        held = [(icao, answer(icao, kd)) for icao in stations]
        detail = "; ".join(f"{i} {a}" for i, a in held)
        with_runs = [i for i, a in held if a == "ok"]
        for n in LEADS:
            if with_runs:
                if with_runs[0] not in cache:
                    cache[with_runs[0]] = mos.load_station(with_runs[0])
                st = mos.lead_status(cache[with_runs[0]], r.start_utc, n, how)
            elif any(a in ("no runs", "no wind", "unreadable") for _, a in held):
                st = "empty answer"
            else:
                st = "not downloaded"
            rows.append(dict(base, lead=n, status=st, detail=detail))
    return pd.DataFrame(rows)


COVERAGE_ORDER = ["forecast", "no station within 40 km", "empty answer", "not downloaded", "no run that day",
                  "run ends before the window", "gap or no wind"]


def coverage_table(cov: pd.DataFrame) -> pd.DataFrame:
    """Eligible games per season and lead by status (a forecast, or why none), plus "any" lead: a
    forecast at some lead, else the game's lead-1 reason."""
    fc = cov[cov.status == "forecast"].game_id.unique()
    anyl = cov.sort_values("lead").drop_duplicates("game_id").copy()
    anyl.loc[anyl.game_id.isin(fc), "status"] = "forecast"
    c = pd.concat([cov.assign(lead=cov.lead.astype(str)), anyl.assign(lead="any")])
    c = pd.concat([c.assign(season=c.season.astype(str)), c.assign(season="all")])
    t = c.groupby(["season", "lead"]).status.value_counts().unstack(fill_value=0)
    t = t[[k for k in COVERAGE_ORDER if k in t.columns]]
    t.insert(0, "games", t.sum(axis=1))
    return t.reset_index()


def signals_per_season(d: pd.DataFrame) -> pd.DataFrame:
    """MOS signals per season, all and from Oct 1 on. Counts only."""
    sig = d[d.has_mos & d.mos_signal]
    kd = pd.Series([mos.kick_date(k) for k in sig.start_utc], index=sig.index)
    from_oct = pd.Series([k >= date(s, 10, 1) for k, s in zip(kd, sig.season)], index=sig.index, dtype=bool)
    t = pd.DataFrame(dict(signals=sig.groupby("season").size(), from_oct1=sig[from_oct].groupby("season").size()))
    return t.reindex(sorted(d.season.unique())).fillna(0).astype(int)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seasons", help="e.g. 2023-2025 (default 2004-2025)")
    args = ap.parse_args()
    from mos_fetch import eligible_games, parse_seasons
    seasons = parse_seasons(args.seasons)
    g_all = eligible_games(seasons)
    smap = pd.read_csv(PROC / "mos_station_map.csv")
    n_all = len(g_all)
    g = g_all[g_all.stadium_key.isin(smap.stadium_key)].copy()
    cache = {}
    d = replay(attach_mos(g, smap, cache))
    tab, bias = season_table(d), bias_table(d[d.has_mos])
    bseason = bias_by_season(d[d.has_mos])
    eras = era_table(d)
    cov = coverage(g_all, d, smap, cache)
    ctab = coverage_table(cov)
    per_season = signals_per_season(d)

    keep = ["game_id", "season", "week", "gameday", "gametime", "start_utc", "away_team", "home_team", "stadium_key",
            "mos_station", "mos_km", "mos_rank", *[c for n in LEADS for c in (f"mos{n}_mph", f"mos{n}_runtime")],
            "has_mos", "mos_signal", "first_lead", "wx_src", "wx_wind", "obs_signal", "total_line", "under_odds",
            "price_ok", "total_open", "opener_move", "sbr_total_close", "total", "under_win", "push", "opener_win",
            "opener_push", "sbr_close_win", "sbr_close_push"]
    tag = "" if seasons == (2004, 2025) else f"_{seasons[0]}_{seasons[1]}"
    d[keep].to_parquet(PROC / f"mos_replay{tag}.parquet", index=False)
    TABLES.mkdir(parents=True, exist_ok=True)
    tab.to_csv(TABLES / f"mos_replay_seasons{tag}.csv", index=False)
    bias.to_csv(TABLES / f"mos_bias{tag}.csv", index=False)
    bseason.to_csv(TABLES / f"mos_bias_by_season{tag}.csv", index=False)
    eras.to_csv(TABLES / f"mos_replay_eras{tag}.csv", index=False)
    ctab.to_csv(TABLES / f"mos_coverage{tag}.csv", index=False)
    none = cov[~cov.game_id.isin(cov[cov.status == "forecast"].game_id) & (cov.lead == 1)]
    nf = g_all[["game_id", "season", "week", "gameday", "gametime", "away_team", "home_team", "stadium_key",
                "stadium"]].merge(none[["game_id", "status", "detail"]], on="game_id").rename(columns={"status": "why"})
    nf.to_csv(TABLES / f"mos_no_forecast{tag}.csv", index=False)

    m = d[d.has_mos]
    sig = m[m.mos_signal]
    pooled = tab[tab["sample"] == "pooled"].iloc[0]
    bar = 0.05 / (VARIANTS_BEFORE + 2)
    lines = [f"NFL Rule B replay on GFS MOS forecasts as issued, {seasons[0]}-{seasons[1]} "
             f"(trigger: MOS wind at kickoff >= {WIND:.0f} mph at lead 1-3; entry at the close, -110)",
             f"  eligible outdoor games {n_all}; at a stadium with a MOS station within {mos.MAX_KM:.0f} km {len(g)}; "
             f"with a MOS forecast at some lead {len(m)} (none: {len(g) - len(m)})",
             "  games by lead available: " + ", ".join(f"lead {n} {int(m[f'mos{n}_mph'].notna().sum())}" for n in LEADS),
             f"  forecast station: nearest {int((m.mos_rank == 0).sum())}, next-nearest {int((m.mos_rank == 1).sum())}, "
             f"third-nearest {int((m.mos_rank == 2).sum())}", ""]
    cols1 = ["sample", "games", "with_mos", "lead1", "lead2", "lead3", "close_n", "close_record", "close_win_pct",
             "close_win_ci", "close_roi_pct", "close_roi_ci", "close_p_one_sided"]
    cols2 = ["sample", "price_n", "price_record", "price_roi_pct", "open_n", "open_record", "open_win_pct",
             "open_move_mean", "closeop_record", "closeop_win_pct", "sbrclose_n", "sbrclose_record", "sbrclose_win_pct",
             "obs_n", "obs_also_signal", "obs_record", "obs_win_pct", "obs_win_ci"]
    anyl = ctab[ctab.lead == "any"].drop(columns="lead")
    wide = ctab[ctab.lead != "any"].pivot(index="season", columns="lead", values="forecast").add_prefix("lead")
    cov_view = anyl.set_index("season").join(wide).reset_index()
    cov_view = cov_view[["season", "games", "lead1", "lead2", "lead3"] + [c for c in anyl.columns if c not in ("season", "games")]]
    cov_view = cov_view.rename(columns={"forecast": "any_lead"})
    cov_view = cov_view.set_index("season").loc[[s for s in cov_view.season if s != "all"] + ["all"]].reset_index()
    ecols = ["sample", "seasons", "per_season", "close_n", "close_record", "close_win_pct", "close_win_ci", "close_roi_pct",
             "close_p_one_sided", "days", "grouped_ci", "grouped_p", "deff"]
    ecols2 = ["sample", "open_n", "open_record", "open_win_pct", "open_win_ci", "closeop_record", "closeop_win_pct",
              "sbrclose_n", "sbrclose_record", "sbrclose_win_pct", "obs_n", "obs_also_signal", "obs_record",
              "obs_win_pct", "obs_win_ci"]
    with pd.option_context("display.width", 250, "display.max_columns", 40):
        lines += ["Coverage (step 2): eligible games per season with a MOS forecast at lead 1, 2, 3 and at any lead; "
                  "games with none at any lead, by why (their lead-1 reason):",
                  cov_view.to_string(index=False), "",
                  "Coverage by lead, all seasons (why a lead has no forecast):",
                  ctab[ctab.season == "all"].drop(columns="season").to_string(index=False), "",
                  "Games with no forecast at any lead, by what each station within 40 km held:",
                  nf.groupby(["why", "detail"]).size().rename("games").reset_index().to_string(index=False), "",
                  "At the close (the primary):", tab[cols1].to_string(index=False), "",
                  "At nflverse's under price where it is -115 or better; at the SBR opener, with the nflverse close on "
                  "those same games (closeop_), and at the SBR close (2007-21); and, at the close, every game whose "
                  "OBSERVED (game-book) wind reached 15 in the same pool of games with a forecast (obs_: not the "
                  "forecast signals; obs_also_signal of them are also forecast signals):",
                  tab[cols2].to_string(index=False), "",
                  "Pooled and the declared era cuts (descriptive, 0 variants), with the interval and p-value also "
                  "computed with standard errors grouped by game day (the kickoff's Eastern date):",
                  eras[ecols].to_string(index=False), "",
                  eras[ecols2].to_string(index=False), "",
                  f"If same-day results correlated at {SAME_DAY_RHO}, as same-day line moves do (paper-to-money study, "
                  "#51): design effect, 95% interval and one-sided p:",
                  *[f"  {r.sample}: {r.deff_rho}, {r.rho_ci}%, p = {r.rho_p}" for r in eras.itertuples()], "",
                  "MOS minus observed kickoff wind, mph (observed = game book, else calibrated ERA5):",
                  bias.to_string(index=False), "",
                  "By season and lead (matched_obs_mph: the observed wind reached as often as MOS reaches 15 mph):",
                  bseason.to_string(index=False), "",
                  "Does 15 mph on MOS mean what 15 mph observed means? By season, lead 1: mean MOS minus observed "
                  "(l1_bias), share of games at 15+ on MOS and observed, and the share of MOS signals whose observed "
                  "wind reached 15:",
                  tab[["sample", "l1_bias", "l1_mos15_pct", "obs15_pct", "sig_obs15_pct"]].to_string(index=False)]
    both, fco, obo = sig[sig.obs_signal], sig[~sig.obs_signal], m[~m.mos_signal & m.obs_signal]
    pct = lambda s: f"{100 * s.under_win.sum() / max(len(s) - s.push.sum(), 1):.1f}%"
    fmt = lambda s: "{}-{}-{}".format(*record(s)) + f" ({pct(s)})"
    either = m[m.wx_wind.notna()]
    (wb, lb, _), (wm, lm, _) = record(both), record(fco)
    lines += ["", "Where the result sits (descriptive; these splits are not rules):",
              f"  MOS and observed both >= 15: {len(both)} games, {fmt(both)}",
              f"  MOS only: {len(fco)} games, {fmt(fco)}",
              f"  observed only: {len(obo)} games, {fmt(obo)}",
              f"  gap between both-fired and MOS-only, Fisher exact two-sided p = "
              f"{stats.fisher_exact([[wb, lb], [wm, lm]]).pvalue:.3f}",
              f"  MOS signals by first lead: {sig.first_lead.value_counts().sort_index().to_dict()}",
              f"  the rule (any lead) fires on {100 * m.mos_signal.mean():.2f}% of {len(m)} games; the observed wind "
              f"reaches 15 on {100 * m.obs_signal.mean():.2f}%; the observed threshold reached as often as the rule "
              f"fires: {float(either.wx_wind.quantile(1 - either.mos_signal.mean())):.2f} mph (n={len(either)})",
              "", "Signals per season (all, and from Oct 1 on):",
              per_season.T.to_string(), f"  mean {per_season.signals.mean():.1f}, median {per_season.signals.median():.0f}, "
              f"range {per_season.signals.min()}-{per_season.signals.max()}",
              "", "Against Open-Meteo previous runs (step 3 of the issue):", *openmeteo_compare(d), "",
              f"Multiple testing: 1 variant for the NFL, plus 1 for a cut looked at after the results (the seasons "
              f"outside 2007-21; every look is counted); with the CFB replay already inside main's running count of "
              f"{VARIANTS_BEFORE}, this makes {VARIANTS_BEFORE + 2}. Bonferroni bar p < {bar:.6f}. Pooled one-sided p = "
              f"{pooled.close_p_one_sided}. The era cuts above are descriptive and add none.",
              f"Observed-wind history for comparison: {OBSERVED_HISTORY}."]
    text = "\n".join(lines)
    (OUT / f"mos_replay{tag}.log").write_text(text + "\n")
    print(text)


if __name__ == "__main__":
    main()
