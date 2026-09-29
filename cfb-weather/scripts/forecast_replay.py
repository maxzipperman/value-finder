"""Replay CFB Rule B on 2024 and 2025 with the forecasts that existed at bet time.

Every earlier CFB Rule B number used OBSERVED airport-station wind, which the rule
never sees: live, it fires on a forecast 1-3 days out. This replays it on Open-Meteo's
previous-runs archive (what the forecast said 1, 2 and 3 days before each game hour),
the same source and no-hindsight timing as nfl-weather (nflweather/fetch.py
fetch_previous_forecasts, nflweather/oddsapi.py decision_time, scripts/pinnacle_check.py).

* Games: FBS-involved, outdoor (not dome), venue coordinates and a known kickoff,
  2024 and 2025, with a closing total and a final score (data/processed/games.parquet).
* Forecast: wind_speed_10m_previous_day{1,2,3}, averaged over the kickoff hour and the
  next 3 (as cfbweather/weather.summarize does), put on the station scale with the
  frozen data/processed/calibration.json (fit 2016-23; not refit here).
* Timing: the lead-N forecast for the game window is public at decision_time =
  kickoff + 4h - N days + 7h release latency. A quote is only used if it existed at or
  after that moment. The one quote the rule uses is the closing total (known at
  kickoff), so every entry is at the close; cfbfastR has no prices, so the price is -110.
* Gates, exactly as cfbweather/board.rule_b_status: forecast >= 15 mph at lead 1, 2 or 3;
  under price -115 or better (-110 passes); expected value > 0 at that line and price
  from the frozen <= 2023 cohort of outdoor 15+ mph games.
* Also reported: CLV when entering at the opening total. The opener is posted BEFORE
  the forecast it's paired with, so that number overstates what was achievable; it is
  a diagnostic, not part of the record. Variants: 1.

Every response is cached under data/raw/openmeteo_prev/ before it is parsed; reruns
never re-fetch.

    python scripts/forecast_replay.py [--no-fetch]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd
from scipy import stats

from cfbweather.config import OUT, PROC, RAW, TABLES

PREV_URL = "https://previous-runs-api.open-meteo.com/v1/forecast"
LEADS = (1, 2, 3)
PREV_VARS = [f"wind_speed_10m_previous_day{n}" for n in LEADS]
CACHE = RAW / "openmeteo_prev"
SEASONS = (2024, 2025)
FORECAST_LATENCY_H = 7   # model initialization to published forecast (as nflweather/oddsapi.py)
GAME_WINDOW_H = 4        # forecast fields used: kickoff hour through kickoff + 4h
ENTRY_ODDS = -110        # cfbfastR has no prices
OBSERVED_EVIDENCE = "56.6% under vs the close in 990 observed-wind games, 2006-25 (STRATEGY.md)"
REHEARSAL = "21-10-1 at the opener, 2025 Week 5 on, with a perfect forecast (output/rehearsal_2025.log)"


def decision_time(kick_utc, lead_days):
    """Earliest moment the lead-N forecast for the whole game window was public (see nflweather/oddsapi.py)."""
    t = pd.Timestamp(kick_utc) + timedelta(hours=GAME_WINDOW_H) - timedelta(days=lead_days) \
        + timedelta(hours=FORECAST_LATENCY_H)
    return t.ceil("5min")


def eligible_games() -> pd.DataFrame:
    g = pd.read_parquet(PROC / "games.parquet")
    g = g[g.season.isin(SEASONS)]
    fbs = g.home_division.astype(str).str.lower().eq("fbs") | g.away_division.astype(str).str.lower().eq("fbs")
    return g[fbs & ~g.dome.astype(bool) & g.lat.notna() & g.lon.notna() & ~g.tbd.astype(bool)
             & g.total.notna() & g.close_total.notna()].copy()


def cache_path(lat, lon, kick_utc) -> Path:
    d0 = pd.Timestamp(kick_utc).strftime("%Y-%m-%d")
    d1 = (pd.Timestamp(kick_utc) + timedelta(hours=GAME_WINDOW_H)).strftime("%Y-%m-%d")
    return CACHE / f"{lat:.3f}_{lon:.3f}_{d0}_{d1}.json"


def fetch(games: pd.DataFrame, pause=1.0):
    from cfbweather.fetch import _get
    CACHE.mkdir(parents=True, exist_ok=True)
    todo = [r for r in games.itertuples() if not cache_path(r.lat, r.lon, r.start_utc).exists()]
    print(f"previous-run forecasts: {len(games)} games, {len(todo)} to fetch", flush=True)
    for i, r in enumerate(todo, 1):
        dest = cache_path(r.lat, r.lon, r.start_utc)
        d0, d1 = dest.stem.split("_")[2:4]
        resp = _get(PREV_URL, dict(latitude=round(r.lat, 3), longitude=round(r.lon, 3), start_date=d0, end_date=d1,
                                   hourly=",".join(PREV_VARS), wind_speed_unit="mph", timezone="UTC"))
        dest.write_text(resp.text)
        if i % 100 == 0:
            print(f"  {i}/{len(todo)}", flush=True)
        time.sleep(pause)


def summarize_prev(js: dict | None, kick_utc) -> dict:
    """Mean forecast wind over the kickoff hour and the next 3, per lead (NaN when that lead is missing)."""
    out = {f"fc{n}_raw": np.nan for n in LEADS}
    if not js or "hourly" not in js:
        return out
    h = pd.DataFrame(js["hourly"])
    h.index = pd.to_datetime(h.time)
    k0 = pd.Timestamp(kick_utc).tz_convert("UTC").tz_localize(None).floor("h")
    if k0 not in h.index:
        return out
    win = h.loc[k0:k0 + pd.Timedelta(hours=3)]
    for n in LEADS:
        col = f"wind_speed_10m_previous_day{n}"
        if col in h and pd.notna(h.at[k0, col]):
            out[f"fc{n}_raw"] = win[col].mean()
    return out


def replay(games: pd.DataFrame, cal: dict, resid_sorted: np.ndarray) -> pd.DataFrame:
    """One row per game: forecasts, triggers, the quote used and when it existed, and outcomes."""
    from cfbweather.board import RULE_B_LEAD, RULE_B_WIND
    from cfbweather.market import MIN_UNDER_ODDS, ev_under
    rows = []
    for r in games.itertuples():
        p = cache_path(r.lat, r.lon, r.start_utc)
        js = json.loads(p.read_text()) if p.exists() else None
        rows.append(dict(game_id=r.game_id, **summarize_prev(js, r.start_utc)))
    df = games.merge(pd.DataFrame(rows), on="game_id", how="left")
    for n in LEADS:
        df[f"fc{n}_wind"] = (cal["wind_intercept"] + cal["wind_slope"] * df[f"fc{n}_raw"]).clip(lower=0)
        df[f"fc{n}_available_utc"] = [decision_time(k, n) for k in df.start_utc]
    leads = [n for n in LEADS if RULE_B_LEAD[0] <= n <= RULE_B_LEAD[1]]
    trig = pd.DataFrame({n: df[f"fc{n}_wind"] >= RULE_B_WIND for n in leads})
    df["no_forecast"] = df[[f"fc{n}_raw" for n in leads]].isna().all(axis=1)
    df["fc_trigger"] = trig.any(axis=1)
    # the earliest snapshot that fires is the longest lead that triggers (the board keeps the earliest SIGNAL)
    df["first_lead"] = trig.apply(lambda t: max([n for n in leads if t[n]], default=np.nan), axis=1)
    df["quote"] = "close_total"
    df["quote_utc"] = df.start_utc                        # the closing total exists at kickoff
    df["forecast_available_utc"] = [decision_time(k, int(n)) if pd.notna(n) else pd.NaT
                                    for k, n in zip(df.start_utc, df.first_lead)]
    df["entry_odds"] = ENTRY_ODDS
    df["ev_under"] = ev_under(df.close_total, df.entry_odds, df.close_total, resid_sorted)
    gate = (df.entry_odds >= MIN_UNDER_ODDS) & (df.ev_under > 0)
    df["fc_signal"] = df.fc_trigger & gate
    df["obs_trigger"] = df.wx_wind >= RULE_B_WIND
    df["obs_signal"] = df.obs_trigger & gate
    df["push"] = df.total == df.close_total
    df["under_win"] = df.total < df.close_total
    win_profit = 100 / abs(ENTRY_ODDS)
    df["profit"] = np.where(df.push, 0.0, np.where(df.under_win, win_profit, -1.0))
    df["opener_clv"] = df.open_total - df.close_total    # diagnostic: the opener predates the forecast
    df["opener_push"] = df.total == df.open_total
    df["opener_win"] = df.total < df.open_total
    return df


def record(d: pd.DataFrame, win="under_win", push="push") -> tuple[int, int, int]:
    w, p = int(d[win].sum()), int(d[push].sum())
    return w, len(d) - w - p, p


def summary(df: pd.DataFrame) -> pd.DataFrame:
    be = abs(ENTRY_ODDS) / (abs(ENTRY_ODDS) + 100)
    out = []
    for label, d in [(str(s), df[df.season == s]) for s in SEASONS] + [("pooled", df)]:
        fc = d[~d.no_forecast]
        both = fc[fc.wx_wind.notna()]
        sig = d[d.fc_signal]
        w, l, p = record(sig)
        pv = stats.binomtest(w, w + l, be, alternative="greater").pvalue if w + l else np.nan
        op = sig[sig.open_total.notna()]
        ow, ol, opu = record(op, "opener_win", "opener_push")
        se = op.opener_clv.std(ddof=1) / np.sqrt(len(op)) if len(op) > 1 else np.nan
        obs = d[d.obs_signal]
        ob_w, ob_l, ob_p = record(obs)
        out.append(dict(
            sample=label, games=len(d), with_forecast=len(fc), no_forecast=int(d.no_forecast.sum()),
            fc_signals=len(sig), obs_signals=len(obs),
            fc_not_obs=int((both.fc_signal & ~both.obs_signal).sum()),
            obs_not_fc=int((~both.fc_signal & both.obs_signal).sum()),
            agreement=round(float((both.fc_signal == both.obs_signal).mean()), 4) if len(both) else np.nan,
            fc_record=f"{w}-{l}-{p}", fc_win_pct=round(100 * w / max(w + l, 1), 1),
            fc_roi_pct=round(100 * sig.profit.sum() / max(w + l, 1), 1), fc_p_one_sided=round(pv, 4),
            opener_n=len(op), opener_record=f"{ow}-{ol}-{opu}",
            opener_clv_mean=round(op.opener_clv.mean(), 2) if len(op) else np.nan,
            opener_clv_ci_lo=round(op.opener_clv.mean() - 1.96 * se, 2) if len(op) > 1 else np.nan,
            opener_clv_ci_hi=round(op.opener_clv.mean() + 1.96 * se, 2) if len(op) > 1 else np.nan,
            obs_record=f"{ob_w}-{ob_l}-{ob_p}", obs_win_pct=round(100 * ob_w / max(ob_w + ob_l, 1), 1)))
    return pd.DataFrame(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-fetch", action="store_true", help="use cached responses only")
    args = ap.parse_args()
    from cfbweather.board import PRICING_LAST_SEASON, RULE_B_WIND
    from cfbweather.market import cohort_residuals, load_games

    games = eligible_games()
    if not args.no_fetch:
        fetch(games)
    cal = json.loads((PROC / "calibration.json").read_text())
    hist = load_games(2006, PRICING_LAST_SEASON)
    resid = cohort_residuals(hist, (hist.outdoor == 1) & (hist.wx_wind >= RULE_B_WIND))
    df = replay(games, cal, resid)
    tab = summary(df)

    keep = ["game_id", "season", "week", "season_type", "start_utc", "home_team", "away_team", "venue", "lat", "lon",
            *[f"fc{n}_raw" for n in LEADS], *[f"fc{n}_wind" for n in LEADS],
            *[f"fc{n}_available_utc" for n in LEADS], "no_forecast", "fc_trigger", "first_lead",
            "forecast_available_utc", "quote", "quote_utc", "entry_odds", "ev_under", "fc_signal", "wx_wind",
            "obs_trigger", "obs_signal", "open_total", "close_total", "total", "under_win", "push", "profit",
            "opener_clv", "opener_win", "opener_push"]
    df[keep].to_parquet(PROC / "forecast_replay.parquet", index=False)
    TABLES.mkdir(parents=True, exist_ok=True)
    tab.to_csv(TABLES / "forecast_replay.csv", index=False)

    lines = ["CFB Rule B forecast replay, 2024-25 (forecasts that existed at bet time; entry at the close, -110)",
             f"  eligible games: {len(df)}; with a forecast: {int((~df.no_forecast).sum())}; "
             f"no forecast (own count): {int(df.no_forecast.sum())}", ""]
    with pd.option_context("display.width", 200, "display.max_columns", 40):
        lines.append(tab.to_string(index=False))
    fc = df[~df.no_forecast & df.wx_wind.notna()]
    for n in LEADS:
        e = (fc[f"fc{n}_wind"] - fc.wx_wind).dropna()
        lines.append(f"  lead {n}: forecast minus observed station wind, mean {e.mean():+.2f} mph, "
                     f"MAE {e.abs().mean():.2f}, corr {fc[f'fc{n}_wind'].corr(fc.wx_wind):.2f} (n={len(e)})")
    both, fco, obo = (df[df.fc_signal & df.obs_signal], df[df.fc_signal & ~df.obs_signal],
                      df[~df.fc_signal & df.obs_signal])
    fmt = lambda d: "{}-{}-{}".format(*record(d)) + f" ({100 * d.under_win.sum() / max(len(d) - d.push.sum(), 1):.1f}%)"
    lines += ["", "Where the edge sits (descriptive; these splits are not rules):",
              f"  forecast and observed both fire: {len(both)} games, {fmt(both)}",
              f"  forecast only (the wind didn't arrive): {len(fco)} games, {fmt(fco)}",
              f"  observed only (the forecast missed it): {len(obo)} games, {fmt(obo)}",
              f"  forecast signals by first lead: {df[df.fc_signal].first_lead.value_counts().sort_index().to_dict()}"]
    r25 = df[(df.season == 2025) & (df.week >= 5) | (df.season == 2025) & (df.season_type != "regular")]
    s25 = r25[r25.fc_signal & r25.open_total.notna()]
    w, l, p = record(s25, "opener_win", "opener_push")
    lines += ["", "Comparisons:",
              f"  observed-wind evidence: {OBSERVED_EVIDENCE}",
              f"  2025 dress rehearsal: {REHEARSAL}",
              f"  this replay, same window and entry (2025 Week 5 on, at the opener): {w}-{l}-{p} "
              f"(the opener predates the forecast, so this overstates what was achievable)",
              "  quotes: every entry is the closing total, which exists at kickoff, after each lead's forecast was public",
              "  variants added: 1 (running total 135)"]
    text = "\n".join(lines)
    (OUT / "forecast_replay.log").write_text(text + "\n")
    print(text)


if __name__ == "__main__":
    main()
