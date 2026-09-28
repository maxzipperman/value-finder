"""Odds API credit budget for every current and possible use in this repo (no API calls, no downloads).

Turns the Odds API cost rules into credits per use case, using kickoff times and wind from the
processed datasets, then checks which uses fit each plan in one month. The rules and plan prices
come from the official docs; strategy-research/odds-api-credits.md lists the sources.

  live /odds                        markets x regions per call (a bookmakers= list of <=10 books = 1 region)
  historical /odds                  10 x markets x regions per snapshot; one call = every game of the sport
  historical /events                1 per call (0 if empty)
  historical /events/{id}/odds      10 x markets returned x regions, per game, per snapshot (props,
                                    alternates, periods, team totals; history from 2023-05-03)

Inputs (read-only)
  nfl-weather/data/processed/games.parquet, calibration.json   kickoffs, observed wind, Open-Meteo forecasts
  cfb-weather/data/processed/games.parquet                     kickoffs (start_utc), observed station wind
  NBA figures are copied from sharp-markets/docs/PLAN.md (no NBA schedule in this repo).

Outputs: output/odds_api_budget.csv (use cases), output/odds_api_plans.csv (plan fit), output/odds_api_counts.csv
Run from the repo root:  nfl-weather/.venv/bin/python strategy-research/odds_budget.py [--no-save]
"""
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = Path(__file__).resolve().parent / "output"
NFL = ROOT / "nfl-weather/data/processed"
CFB = ROOT / "cfb-weather/data/processed"

PLANS = {"Free": (500, 0), "20K": (20_000, 30), "100K": (100_000, 59), "5M": (5_000_000, 119),
         "15M": (15_000_000, 249)}
HIST = 10            # historical multiplier
H = pd.Timedelta(hours=1)
M5 = pd.Timedelta(minutes=5)


def nfl_games():
    g = pd.read_parquet(NFL / "games.parquet")
    g = g[g.season.between(2020, 2026)].copy()
    et = pd.to_datetime(g.gameday + " " + g.gametime.fillna("13:00"))
    g["kick"] = et.dt.tz_localize("America/New_York").dt.tz_convert("UTC")
    cal = json.loads((NFL / "calibration.json").read_text())
    fc = g[["fc1_wind", "fc3_wind"]].max(axis=1) * cal["wind_slope"] + cal["wind_intercept"]
    g["fc_wind"] = fc.where(g[["fc1_wind", "fc3_wind"]].notna().any(axis=1))
    g["outdoor"] = g.wx_src.isin(["gamebook", "era5"])
    return g


def cfb_games():
    c = pd.read_parquet(CFB / "games.parquet")
    c = c[c.season.between(2020, 2026) & ((c.home_division == "fbs") | (c.away_division == "fbs"))].copy()
    c["kick"] = c.start_utc
    c["outdoor"] = c.wx_src == "station"
    return c


def grid_union(kicks, lookback, step):
    """Distinct snapshot times on a `step` grid inside any [kick - lookback, kick], plus each kickoff (the close)."""
    pts = set()
    for k in pd.Series(kicks).dropna().unique():
        k = pd.Timestamp(k)
        t = (k - lookback).ceil(step)
        pts.update(pd.date_range(t, k.floor(step), freq=step))
        pts.add(k)
    return len(pts)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-save", action="store_true", help="print only; don't rewrite output/*.csv")
    save = not ap.parse_args().no_save
    nfl, cfb = nfl_games(), cfb_games()
    S = range(2020, 2026)
    S3 = range(2023, 2026)          # props/alternates/periods exist from 2023-05-03
    counts = []
    for name, d in (("NFL", nfl), ("CFB", cfb)):
        for s in [*S, 2026]:
            x = d[d.season == s]
            counts.append({
                "sport": name, "season": s, "games": len(x), "kickoffs": x.kick.nunique(),
                "hourly_7d_snaps": grid_union(x.kick, 168 * H, H),
                "windy12_obs": int((x.outdoor & (x.wx_wind >= 12)).sum()),
                "windy15_obs": int((x.outdoor & (x.wx_wind >= 15)).sum()),
                "windy12_fc": int((x.outdoor & (x.fc_wind >= 12)).sum()) if "fc_wind" in x else 0,
            })
    cnt = pd.DataFrame(counts)

    def tot(sport, col, seasons):
        return int(cnt[(cnt.sport == sport) & cnt.season.isin(list(seasons))][col].sum())

    # 5-min windows, 72h before each windy kickoff (union per sport). NFL uses the calibrated forecast
    # (2024-25 only have forecasts); CFB has no forecast column, so observed wind stands in for it.
    nfl_w = nfl[nfl.season.isin([2024, 2025]) & nfl.outdoor & (nfl.fc_wind >= 12)]
    cfb_w = cfb[cfb.season.isin([2024, 2025]) & cfb.outdoor & (cfb.wx_wind >= 12)]
    snaps5_nfl = sum(grid_union(nfl_w[nfl_w.season == s].kick, 72 * H, M5) for s in (2024, 2025))
    snaps5_cfb = sum(grid_union(cfb_w[cfb_w.season == s].kick, 72 * H, M5) for s in (2024, 2025))

    # Live: the alerts run 4x/day; a close capture adds one call per distinct kickoff. Month = October 2025.
    oct_ = lambda d: d[(d.kick >= "2025-10-01") & (d.kick < "2025-11-01")].kick.nunique()  # noqa: E731
    nfl_oct_k, cfb_oct_k = oct_(nfl), oct_(cfb)

    g3n, g3c = tot("NFL", "games", S3), tot("CFB", "games", S3)
    w12n, w12c = tot("NFL", "windy12_obs", S3), tot("CFB", "windy12_obs", S3)
    hn, hc = tot("NFL", "hourly_7d_snaps", S), tot("CFB", "hourly_7d_snaps", S)
    hn25, hc25 = tot("NFL", "hourly_7d_snaps", [2025]), tot("CFB", "hourly_7d_snaps", [2025])
    kn3, kc3 = tot("NFL", "kickoffs", S3), tot("CFB", "kickoffs", S3)
    kn, kc = tot("NFL", "kickoffs", S), tot("CFB", "kickoffs", S)
    h26 = tot("NFL", "hourly_7d_snaps", [2026]) + tot("CFB", "hourly_7d_snaps", [2026])
    g26n = tot("NFL", "games", [2026])

    rows = [
        # id, kind, use, issue, formula, credits, value (1-5)
        ("L1", "live/mo", "NFL alerts: live Pinnacle totals", "Rule B", "1 mkt x 1 book group x 4 runs x 31 days", 4 * 31, 5),
        ("L2", "live/mo", "CFB alerts: live Pinnacle+DK totals", "Rule B", "1 x 1 x 4 runs x 31 days", 4 * 31, 5),
        ("L3", "live/mo", "Close capture: one live totals call per kickoff slot (Oct 2025 slots)", "Rule B",
         f"1 x ({nfl_oct_k} NFL + {cfb_oct_k} CFB kickoff slots)", nfl_oct_k + cfb_oct_k, 4),
        ("L4", "live/mo", "NBA forward collector (PLAN s7): 5-min h2h ticks + 1-min final 2h", "H1/H2 (#9)",
         "1 x (~144 ticks + 150-260) x ~27 game days (estimate)", 27 * (144 + 205), 2),
        ("B1", "backfill", "NFL Pinnacle totals at forecast times, 2024-25 (existing backfill_plan)", "#6, Rule B",
         "10 x 1 mkt x 1 group x 826 snapshots", 8_260, 4),
        ("B2", "backfill", "5-min totals, 72h before windy kickoffs (NFL fc>=12, CFB obs>=12), 2024-25", "#6 forecast timing",
         f"10 x 1 x 1 x ({snaps5_nfl:,} NFL + {snaps5_cfb:,} CFB snapshots)", HIST * (snaps5_nfl + snaps5_cfb), 3),
        ("B3", "backfill", "Hourly multi-book featured lines, 7 days pre-kickoff, NFL+CFB 2020-25", "#8, #5, #4",
         f"10 x 3 mkts x 1 group (10 books) x ({hn:,} NFL + {hc:,} CFB snapshots)", HIST * 3 * (hn + hc), 5),
        ("B3a", "alt", "Lean version of B3: multi-book featured closes only, NFL+CFB 2020-25", "#8",
         f"10 x 3 x 1 group x ({kn} NFL + {kc:,} CFB kickoff slots)", HIST * 3 * (kn + kc), 4),
        ("B4", "backfill", "Exchange group (Kalshi, Polymarket, Novig, ProphetX), hourly, 2025", "#8, #9",
         f"10 x 3 x 1 group x ({hn25:,} + {hc25:,} snapshots)", HIST * 3 * (hn25 + hc25), 3),
        ("B5", "backfill", "Alternate spreads+totals, NFL 2023-25, 2 snapshots (T-24h, close)", "#8 teasers, key numbers",
         f"10 x 2 mkts x 1 group x 2 snaps x {g3n} games", HIST * 2 * 2 * g3n, 4),
        ("B6", "backfill", "Alternate spreads+totals, CFB 2023-25, 2 snapshots", "#8",
         f"10 x 2 x 1 x 2 x {g3c:,} games", HIST * 2 * 2 * g3c, 2),
        ("B7", "backfill", "Player props, NFL 2023-25, 4 markets x 4 snapshots", "#10, weather props",
         f"10 x 4 mkts x 1 group x 4 snaps x {g3n} games", HIST * 4 * 4 * g3n, 3),
        ("B8", "backfill", "Player props, CFB 2023-25, 4 markets x 4 snapshots (upper bound; empty is free)", "#10, weather props",
         f"10 x 4 x 1 x 4 x {g3c:,} games", HIST * 4 * 4 * g3c, 2),
        ("B9", "backfill", "1H totals + team totals, windy NFL games 2023-25 + equal calm controls, every 2h over 72h", "#6 derivative lag",
         f"10 x 2 mkts x 1 group x 36 snaps x ({w12n} windy + {w12n} calm)", HIST * 2 * 36 * 2 * w12n, 3),
        ("B10", "backfill", "Same for CFB 2023-25", "#6 derivative lag",
         f"10 x 2 x 1 x 36 x ({w12c} + {w12c})", HIST * 2 * 36 * 2 * w12c, 3),
        ("B11", "backfill", "Historical events lookups for event IDs (one per kickoff slot)", "B5-B10",
         f"1 x ({kn3} NFL + {kc3:,} CFB kickoff slots)", kn3 + kc3, None),
        ("B12", "backfill", "NBA sample week, schedule A (PLAN.md)", "H1/H2",
         "10 x 1 mkt x 1 group x 754 snapshots", 7_540, 3),
        ("B13", "backfill", "NBA 2025-26 full season, schedule D: 5-min open to tip (PLAN.md)", "H1/H2",
         "10 x 1 x 1 x 49,398 snapshots", 493_980, 2),
        ("B14", "backfill", "NBA Pinnacle closes 2021-26 for the H3 Kaggle test (PLAN.md)", "H3",
         "10 x 1 x 1 x ~3,955 tip times", 39_550, 2),
        ("O1", "later", "2026 out-of-sample add-on after the seasons: B3 + B5 + B7 for 2026 (schedules so far)", "all",
         f"30 x {h26:,} snapshots + (40 + 160) x {g26n} NFL games", 30 * h26 + 200 * g26n, 3),
    ]
    b = pd.DataFrame(rows, columns=["id", "kind", "use", "issue", "arithmetic", "credits", "value"])
    if save:
        b.to_csv(OUT / "odds_api_budget.csv", index=False)
        cnt.to_csv(OUT / "odds_api_counts.csv", index=False)

    live = int(b[b.kind == "live/mo"].credits.sum())
    alerts = int(b[b.id.isin(["L1", "L2", "L3"])].credits.sum())
    fill = b[b.kind == "backfill"].sort_values(["value", "credits"], ascending=[False, True], na_position="first")
    plans = []
    for p, (cr, usd) in PLANS.items():
        room, fits = cr - alerts, []                     # the alerts run in the same month
        for r in fill.itertuples():
            if p != "Free" and r.credits <= room:        # historical endpoints are paid-only
                room -= r.credits
                fits.append(r.id)
        plans.append({"plan": p, "credits": cr, "usd": usd,
                      "usd_per_1k": round(usd / cr * 1000, 4) if usd else 0.0,
                      "alerts_fit": alerts <= cr, "all_live_fit": live <= cr,
                      "backfills_that_fit": " ".join(fits), "credits_used": cr - room,
                      "value_points_fit": int(fill[fill.id.isin(fits)].value.sum())})
    pl = pd.DataFrame(plans)
    if save:
        pl.to_csv(OUT / "odds_api_plans.csv", index=False)

    pd.set_option("display.width", 250, "display.max_colwidth", 120)
    print(cnt.to_string(index=False), "\n")
    print(f"5-min snapshots: NFL {snaps5_nfl:,} ({len(nfl_w)} windy games), CFB {snaps5_cfb:,} ({len(cfb_w)} windy games)")
    print(f"Oct 2025 kickoff slots: NFL {nfl_oct_k}, CFB {cfb_oct_k}\n")
    print(b[["id", "use", "arithmetic", "credits", "value"]].to_string(index=False), "\n")
    print(f"Backfill total: {int(fill.credits.sum()):,}   Live per month: {live:,} (alerts + close capture {alerts})\n")
    print(pl.to_string(index=False))


if __name__ == "__main__":
    main()
