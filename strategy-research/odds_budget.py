"""Odds API credit budget for every current and possible use in this repo (no API calls, no downloads).

Turns the Odds API cost rules into credits per use, using kickoff times and wind from the processed
datasets, then checks what fits each plan in one month. The rules and plan prices come from the
official docs; strategy-research/odds-api-credits.md lists the sources and explains every row.

  live /odds                        markets x regions per call (a bookmakers= list of <=10 books = 1 region)
  live /events/{id}/odds            markets returned x regions, per game
  historical /odds                  10 x markets x regions per snapshot; one call = every game of the sport
  historical /events/{id}/odds      10 x markets returned x regions, per game, per snapshot (props,
                                    alternates, periods, team totals; history from 2023-05-03)

Inputs (read-only)
  nfl-weather/data/processed/games.parquet, calibration.json   kickoffs, observed wind, Open-Meteo forecasts
  cfb-weather/data/processed/games.parquet                     kickoffs (start_utc), observed station wind
  NBA figures are copied from sharp-markets/docs/PLAN.md (no NBA schedule in this repo).

The 2026 schedules are incomplete (no postseason, many CFB kickoffs TBD), so 2026 backfill counts use
2025 as a stand-in. The CFB file has no 2020-22 bowls, so those seasons get 2025's postseason count added.

Outputs: output/odds_api_budget.csv (use cases), odds_api_plans.csv (plan fit), odds_api_counts.csv (games and
         snapshots per season), odds_api_live_months.csv (live credits by month), all under output/
Run from the repo root:  nfl-weather/.venv/bin/python strategy-research/odds_budget.py [--no-save]
The 5M-month plan across all sports (odds_5m.py) runs at the end and writes output/odds_5m_*.csv.
"""
import argparse
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = Path(__file__).resolve().parent / "output"
NFL = ROOT / "nfl-weather/data/processed"
CFB = ROOT / "cfb-weather/data/processed"

PLANS = {"Free": (500, 0), "20K": (20_000, 30), "100K": (100_000, 59), "5M": (5_000_000, 119),
         "15M": (15_000_000, 249)}
HIST = 10                        # historical multiplier
H, D = pd.Timedelta(hours=1), pd.Timedelta(days=1)
M5 = pd.Timedelta(minutes=5)
SEASONS = range(2020, 2027)      # featured-market history starts 2020-06-06
PROPS = range(2023, 2027)        # additional markets start 2023-05-03


def nfl_games():
    g = pd.read_parquet(NFL / "games.parquet")
    g = g[g.season.between(2020, 2026)].copy()
    et = pd.to_datetime(g.gameday + " " + g.gametime.fillna("13:00"))
    g["kick"] = et.dt.tz_localize("America/New_York").dt.tz_convert("UTC")
    cal = json.loads((NFL / "calibration.json").read_text())
    fc = g[["fc1_wind", "fc3_wind"]].max(axis=1) * cal["wind_slope"] + cal["wind_intercept"]
    g["fc_wind"] = fc.where(g[["fc1_wind", "fc3_wind"]].notna().any(axis=1))
    g["outdoor"] = g.wx_src.isin(["gamebook", "era5"])
    g["post"] = g.game_type != "REG"
    return g


def cfb_games():
    c = pd.read_parquet(CFB / "games.parquet")
    c = c[c.season.between(2020, 2026) & ((c.home_division == "fbs") | (c.away_division == "fbs"))].copy()
    c["kick"] = c.start_utc
    c["outdoor"] = c.wx_src == "station"
    c["post"] = c.season_type == "postseason"
    return c


def grid(kicks, lookback, step, at=None):
    """Snapshot times on a `step` grid (or daily at hour `at`, UTC) inside any [kick - lookback, kick],
    plus each kickoff itself (the close)."""
    pts = set()
    for k in pd.Series(kicks).dropna().unique():
        k = pd.Timestamp(k)
        if at is None:
            pts.update(pd.date_range((k - lookback).ceil(step), k.floor(step), freq=step))
        else:
            first = (k - lookback).normalize() + pd.Timedelta(hours=at)
            pts.update(t for t in pd.date_range(first, k, freq=D) if t >= k - lookback)
        pts.add(k)
    return pts


def per_season(d, fn):
    """fn(season games) -> count, for 2020-26. 2026 uses 2025; seasons missing their postseason
    (CFB 2020-22) get 2025's postseason-only count added."""
    out = {}
    post25 = fn(d[(d.season == 2025) & d.post])
    for s in SEASONS:
        x = d[d.season == (2025 if s == 2026 else s)]
        out[s] = fn(x) + (post25 if s < 2026 and not x.post.any() else 0)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-save", action="store_true", help="print only; don't rewrite output/*.csv")
    save = not ap.parse_args().no_save
    nfl, cfb = nfl_games(), cfb_games()

    counts = []
    for name, d in (("NFL", nfl), ("CFB", cfb)):
        games = per_season(d, len)
        slots = per_season(d, lambda x: x.kick.nunique())
        daily = per_season(d, lambda x: len(grid(x.kick, 7 * D, None, at=16)))
        hourly = per_season(d, lambda x: len(grid(x.kick, 7 * D, H)))
        w12 = per_season(d, lambda x: int((x.outdoor & (x.wx_wind >= 12)).sum()))
        for s in SEASONS:
            counts.append({"sport": name, "season": s, "stand_in": "2025" if s == 2026 else "",
                           "games": games[s], "kickoff_slots": slots[s], "daily_plus_close_snaps": daily[s],
                           "hourly_7d_snaps": hourly[s], "windy12_obs": w12[s]})
    cnt = pd.DataFrame(counts)

    def tot(col, seasons, sport=None):
        x = cnt[cnt.season.isin(list(seasons)) & ((cnt.sport == sport) if sport else True)]
        return int(x[col].sum())

    # 5-min windows 72h before windy kickoffs, 2024-25 (NFL: calibrated forecast >= 12; CFB has no
    # forecast column, so observed wind stands in). Counted net of the hourly X1 snapshots.
    b2 = b2_net = 0
    for d, windy in ((nfl, lambda x: x.fc_wind >= 12), (cfb, lambda x: x.wx_wind >= 12)):
        for s in (2024, 2025):
            x = d[d.season == s]
            five = grid(x[x.outdoor & windy(x)].kick, 72 * H, M5)
            b2 += len(five)
            b2_net += len(five - grid(x.kick, 7 * D, H))

    # October 2026 live: every day is active for both sports. Close capture = one call per kickoff slot.
    # NFL slots come from the 2026 schedule; CFB kickoffs are mostly TBD, so use Oct 2025's rate per
    # Saturday (Oct 2026 has 5 Saturdays, Oct 2025 had 4) plus Oct 2025's other-day slots.
    nfl_oct = nfl[(nfl.kick >= "2026-10-01") & (nfl.kick < "2026-11-01")].kick.nunique()
    c25 = cfb[(cfb.kick >= "2025-10-01") & (cfb.kick < "2025-11-01")]
    sat = c25.kick.dt.tz_convert("America/New_York").dt.dayofweek == 5
    cfb_sat, cfb_wk = c25[sat].kick.nunique(), c25[~sat].kick.nunique()
    cfb_oct = round(cfb_sat / 4 * 5 + cfb_wk)
    nfl_nov = int(((nfl.kick >= "2025-11-01") & (nfl.kick < "2025-12-01")).sum())

    # Live credits by month, 2025-26 as the stand-in season: 4 runs a day on every day with a game in the
    # next 8 days (the boards return early otherwise) + one close-capture call per kickoff slot.
    live_rows = []
    for m in pd.period_range("2025-08", "2026-02", freq="M"):
        row = {"month": str(m + 12)}                     # shown as the matching 2026-27 month
        for name, d in (("nfl", nfl), ("cfb", cfb)):
            days = pd.date_range(m.start_time, m.end_time.normalize(), freq=D, tz="America/Los_Angeles")
            k = d.kick.dt.tz_convert("America/Los_Angeles").dt.normalize()
            active = sum(((k >= day) & (k <= day + 8 * D)).any() for day in days)
            row[f"{name}_alert_runs"] = 4 * active
            row[f"{name}_close_slots"] = d[k.dt.tz_localize(None).dt.to_period("M") == m].kick.nunique()
        row["alerts"] = row["nfl_alert_runs"] + row["cfb_alert_runs"]
        row["alerts_plus_close"] = row["alerts"] + row["nfl_close_slots"] + row["cfb_close_slots"]
        live_rows.append(row)
    live_months = pd.DataFrame(live_rows)

    g_props = tot("games", PROPS, "NFL")
    w12_props = tot("windy12_obs", PROPS, "NFL")
    daily = tot("daily_plus_close_snaps", SEASONS)
    hourly = tot("hourly_7d_snaps", SEASONS)
    h25 = tot("hourly_7d_snaps", [2025])
    g3c = tot("games", range(2023, 2026), "CFB")
    w12n, w12c = tot("windy12_obs", range(2023, 2026), "NFL"), tot("windy12_obs", range(2023, 2026), "CFB")
    pilot_probe = 1_000

    rows = [
        # id, stage, use, serves, arithmetic, credits, value (1-5)
        ("L1", "live, per month", "NFL alerts: live Pinnacle totals", "Rule B",
         "1 market x 1 book group x 4 runs x 31 days", 4 * 31, 5),
        ("L2", "live, per month", "CFB alerts: live Pinnacle/DraftKings totals", "Rule B",
         "1 x 1 x 4 runs x 31 days", 4 * 31, 5),
        ("L3", "live, per month", "Close capture: one totals call per kickoff slot, Oct 2026", "Rule B, #4",
         f"1 x ({nfl_oct} NFL + ~{cfb_oct} CFB slots)", nfl_oct + cfb_oct, 5),
        ("L4", "if B12 passes", "NBA forward collector (PLAN.md s7), per month", "H1/H2",
         "1 x (144 to 288 five-min ticks + 0 to 205 one-min) x 27 game days", "3,888-14,175", 2),
        ("L5", "optional, per month", "Live logger: hourly multi-book featured lines, both sports, "
         "+ NFL props, alternates, 1H and team totals", "#8, #10, #6",
         f"3 x 24 x 30 x 2 sports + {nfl_nov} NFL games x (4 props + 4 x 2 snaps)",
         3 * 24 * 30 * 2 + nfl_nov * (4 + 8), 3),
        ("P0", "Oct pilot", "Probes: billing multiplier, Pinnacle props/alternates/periods, "
         "LowVig and exchange history starts, one test week per new puller", "all", "capped", pilot_probe, 4),
        ("B1", "Oct pilot", "NFL Pinnacle totals at the forecast decision times, 2024-25 (existing backfill_plan)",
         "Rule B replay, #6", "10 x 1 market x 1 group x 826 snapshots", 8_260, 3),
        ("B12", "Oct pilot", "NBA sample week, schedule A (PLAN.md)", "H1/H2 gate",
         "10 x 1 x 1 x 754 snapshots", 7_540, 4),
        ("M1", "main month", "Multi-book featured lines, daily 16:00 UTC for 7 days pre-kickoff + every close, "
         "NFL+CFB 2020-26", "#8, #4, #5, CFB Pinnacle closes",
         f"10 x 3 markets x 1 group (10 books) x {daily:,} snapshots", HIST * 3 * daily, 4),
        ("M2", "main month", "Alternate spreads+totals, NFL 2023-26, at T-24h and close", "#8",
         f"10 x 2 markets x 1 group x 2 snaps x {g_props:,} games", HIST * 2 * 2 * g_props, 3),
        ("M3", "main month", "Player props (4 markets), NFL 2023-26, at the close", "#10",
         f"10 x 4 x 1 x 1 snap x {g_props:,} games", HIST * 4 * g_props, 3),
        ("M4", "dropped (pre-check failed)", "1H totals + team totals, windy NFL games (obs >= 12 mph) "
         "+ as many calm controls, 2023-26, at T-24h and close", "#6 derivative markets",
         f"10 x 2 x 1 x 2 snaps x ({w12_props} windy + {w12_props} calm)", HIST * 2 * 2 * 2 * w12_props, 1),
        ("M6", "main month if #21 is in the data-use plan", "Kicker props (kicking points, field goals made), NFL "
         "2023-26, at the close", "#21", f"10 x 2 x 1 x 1 snap x {g_props:,} games", HIST * 2 * g_props, 3),
        ("M5", "main month if H3 proceeds", "NBA Pinnacle closes 2021-26 for the H3 Kaggle test (PLAN.md)", "H3",
         "10 x 1 x 1 x ~3,955 tip times", 39_550, 2),
        ("N1", "if B12 passes", "NBA 2025-26 full season, schedule D: 5-min from market open to tip (PLAN.md)",
         "H1/H2", "10 x 1 x 1 x 49,398 snapshots, less B12's 754 and M5's 791 already cached",
         HIST * (49_398 - 754 - 791), 2),
        ("X1", "deferred", "Hourly multi-book featured lines, 7 days pre-kickoff, NFL+CFB 2020-26", "#8",
         f"10 x 3 x 1 x {hourly:,} snapshots", HIST * 3 * hourly, 3),
        ("X2", "deferred", "5-min totals for 72h before windy kickoffs, 2024-25, net of X1",
         "#6 forecast-run timing", f"10 x 1 x 1 x {b2_net:,} snapshots ({b2:,} before netting)", HIST * b2_net, 1),
        ("X3", "dropped", "Exchange book group (Kalshi, Polymarket, Novig, ProphetX), hourly, 2025", "#8, #9",
         f"10 x 3 x 1 x {h25:,} snapshots", HIST * 3 * h25, 1),
        ("X4", "dropped", "Alternate spreads+totals, CFB 2023-25", "#8",
         f"10 x 2 x 1 x 2 x {g3c:,} games", HIST * 2 * 2 * g3c, 1),
        ("X5", "dropped", "Player props, CFB 2023-25, 4 markets x 4 snapshots (upper bound)", "#10",
         f"10 x 4 x 1 x 4 x {g3c:,} games", HIST * 4 * 4 * g3c, 1),
        ("X6", "replaced by M3", "Player props, NFL 2023-25, 4 markets x 4 snapshots", "#10",
         "10 x 4 x 1 x 4 x 855 games", HIST * 4 * 4 * 855, 2),
        ("X7", "replaced by M4", "1H totals + team totals every 2h over 72h, windy + calm, NFL and CFB 2023-25",
         "#6", f"10 x 2 x 1 x 37 x 2 x ({w12n} NFL + {w12c} CFB)", HIST * 2 * 37 * 2 * (w12n + w12c), 1),
    ]
    b = pd.DataFrame(rows, columns=["id", "stage", "use", "serves", "arithmetic", "credits", "value"])

    num = lambda i: int(b.set_index("id").credits[i])  # noqa: E731
    live_oct = num("L1") + num("L2") + num("L3")
    pilot = num("P0") + num("B1") + num("B12")
    main_core = sum(num(i) for i in ("M1", "M2", "M3"))
    main_all = main_core + num("M5")                 # M4 dropped: prechecks.py found no wind effect on the split
    plans = []
    for p, (cr, usd) in PLANS.items():
        plans.append({
            "plan": p, "credits": cr, "usd": usd, "usd_per_1k": round(usd / cr * 1000, 4) if usd else 0.0,
            "live_oct_2026": live_oct <= cr,
            "pilot_plus_live": (pilot + live_oct <= cr) and p != "Free",
            "main_core_M1_M3": main_core <= cr and p != "Free",
            "main_all_M1_M3_M5": main_all <= cr and p != "Free",
            "main_plus_N1_X1": main_all + num("N1") + num("X1") <= cr and p != "Free",
        })
    pl = pd.DataFrame(plans)
    if save:
        b.to_csv(OUT / "odds_api_budget.csv", index=False)
        cnt.to_csv(OUT / "odds_api_counts.csv", index=False)
        pl.to_csv(OUT / "odds_api_plans.csv", index=False)
        live_months.to_csv(OUT / "odds_api_live_months.csv", index=False)

    pd.set_option("display.width", 250, "display.max_colwidth", 110)
    print(cnt.to_string(index=False), "\n")
    print(f"Oct 2026 kickoff slots: NFL {nfl_oct}; CFB ~{cfb_oct} (Oct 2025: {cfb_sat} on 4 Saturdays, {cfb_wk} other days)")
    print(f"NFL games in Nov 2025: {nfl_nov}\n")
    print(b[["id", "stage", "use", "arithmetic", "credits", "value"]].to_string(index=False), "\n")
    print(f"Live, Oct 2026 (L1-L3): {live_oct:,}   Oct pilot (P0+B1+B12): {pilot:,}   with live: {pilot + live_oct:,}")
    print(f"Main month core (M1-M3): {main_core:,}   with M5: {main_all:,}   "
          f"+ N1 + X1: {main_all + num('N1') + num('X1'):,}\n")
    print(pl.to_string(index=False), "\n")
    print("Live credits by month (2025-26 schedule relabelled as 2026-27):")
    print(live_months.to_string(index=False))

    import odds_5m                     # the 5M month across every sport (owner decision, Sep 28)
    odds_5m.main(save)


if __name__ == "__main__":
    main()
