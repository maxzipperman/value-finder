"""Price the trims of the 5M plan by reusing odds_budget.py / odds_5m.py arithmetic (read-only)."""
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "strategy-research"))
import odds_budget as ob  # noqa: E402
import odds_5m as o5      # noqa: E402

HIST, PER_SNAP = o5.HIST, o5.PER_SNAP   # 10, 30
nfl, cfb = ob.nfl_games(), ob.cfb_games()
fb = o5.football_counts()
p, s, c = o5.plan()
print("=== odds_5m.plan() reproduced ===")
print(p[["id", "credits", "value", "dropped", "in_plan"]].to_string(index=False))
inplan = p[p.in_plan].credits.sum()
print(f"in-plan total {inplan:,}   (doc says 4,175,930)")
print("counts:", c)

# ---------------------------------------------------------------- per-season football counts
for name in ("NFL", "CFB"):
    print(name, "daily", fb[name]["daily"], "\n    hourly", fb[name]["hourly"], "\n    games", fb[name]["games"])

# ---------------------------------------------------------------- overlap: are daily snapshots a subset of hourly?
print("\n=== daily-subset-of-hourly check (F1 vs F4 double count) ===")
overlap_total = 0
for name, d in (("NFL", nfl), ("CFB", cfb)):
    for sn in ob.SEASONS:
        x = d[d.season == (2025 if sn == 2026 else sn)]
        daily = ob.grid(x.kick, 7 * ob.D, None, at=16)
        hourly = ob.grid(x.kick, 7 * ob.D, ob.H)
        not_in = len(daily - hourly)
        overlap_total += len(daily & hourly)
        if not_in:
            print(f"  {name} {sn}: {not_in} daily points NOT in hourly")
print(f"  daily snapshots that the hourly grid already contains: {overlap_total:,} of {c['daily_fb']:,}")
print(f"  F4 gross {PER_SNAP * c['hourly_fb']:,}; net of F1's cached snapshots {PER_SNAP * (c['hourly_fb'] - overlap_total):,}")

# ---------------------------------------------------------------- F3 trims
nfl_p = c["nfl_p"]
print("\n=== F3 trims (NFL props, 2023-26 games =", nfl_p, ") ===")
f3 = {
    "F3 as planned: 6 mkts x 4 snaps": HIST * 6 * 4 * nfl_p,
    "F3 at 2 snaps (T-24h, close): 6 x 2": HIST * 6 * 2 * nfl_p,
    "F3 close only: 6 x 1": HIST * 6 * 1 * nfl_p,
    "  of which yardage 4 mkts close only (= M3)": HIST * 4 * nfl_p,
    "  of which kicking 2 mkts close only, all games (= M6)": HIST * 2 * nfl_p,
}
for k, v in f3.items():
    print(f"  {k:60} {v:>9,}")

# windy/cold outdoor NFL games 2023-25 (observed) and forecast-based
g = nfl[nfl.season.between(2023, 2025)].copy()
obs = g.outdoor & ((g.wx_wind >= 15) | (g.wx_temp <= 32))
fc_temp = g.fc1_temp if "fc1_temp" in g else pd.Series(float("nan"), index=g.index)
fcst = g.outdoor & ((g.fc_wind >= 15) | (fc_temp <= 32))
print("  outdoor games 2023-25:", int(g.outdoor.sum()), "of", len(g))
print("  observed wx_wind>=15 or wx_temp<=32, outdoor, by season:",
      g[obs].groupby("season").size().to_dict(), "total", int(obs.sum()))
print("  forecast (calibrated fc_wind>=15 or fc1_temp<=32), outdoor, by season:",
      g[fcst].groupby("season").size().to_dict(), "total", int(fcst.sum()),
      "| fc_wind non-null:", int(g.fc_wind.notna().sum()), "fc1_temp non-null:", int(fc_temp.notna().sum()))
print("  wind-only (>=15 obs):", int((g.outdoor & (g.wx_wind >= 15)).sum()),
      " cold-only (<=32 obs):", int((g.outdoor & (g.wx_temp <= 32)).sum()))
for lab, n in (("observed", int(obs.sum())), ("forecast", int(fcst.sum()))):
    print(f"  kicking 2 mkts, close only, {lab} windy/cold 2023-25 ({n} games): {HIST * 2 * n:,} credits")
# add 2026 stand-in? task says 2023-25 only

# ---------------------------------------------------------------- F5 / F6
cfb_p = c["cfb_p"]
print("\n=== F5/F6 (CFB 2023-26 games =", cfb_p, ") ===")
print(f"  F5 as planned 3 mkts x 2 snaps: {HIST * 3 * 2 * cfb_p:,}")
print(f"  F5 team_totals only, close only: {HIST * 1 * 1 * cfb_p:,}")
print(f"  F6 as planned 4 mkts x close: {HIST * 4 * cfb_p:,}")

# ---------------------------------------------------------------- F2 breakdown
print("\n=== F2 breakdown ===")
print(f"  F2 as planned 3 mkts x 3 snaps: {HIST * 3 * 3 * nfl_p:,}")
print(f"  team_totals share (1 mkt x 3 snaps): {HIST * 1 * 3 * nfl_p:,}")
print(f"  alternates at 2 snaps (= M2): {HIST * 2 * 2 * nfl_p:,}")

# ---------------------------------------------------------------- F4 variants
print("\n=== F4 variants ===")
def hourly_counts(d, lookback, seasons):
    out = {}
    for sn in seasons:
        x = d[d.season == (2025 if sn == 2026 else sn)]
        post25 = d[(d.season == 2025) & d.post]
        pts = ob.grid(x.kick, lookback, ob.H)
        if sn < 2026 and not x.post.any():
            pts |= ob.grid(post25.kick, lookback, ob.H)
        out[sn] = pts
    return out

def daily_pts(d, seasons):
    out = {}
    for sn in seasons:
        x = d[d.season == (2025 if sn == 2026 else sn)]
        post25 = d[(d.season == 2025) & d.post]
        pts = ob.grid(x.kick, 7 * ob.D, None, at=16)
        if sn < 2026 and not x.post.any():
            pts |= ob.grid(post25.kick, 7 * ob.D, None, at=16)
        out[sn] = pts
    return out

h7 = {"NFL": hourly_counts(nfl, 7 * ob.D, ob.SEASONS), "CFB": hourly_counts(cfb, 7 * ob.D, ob.SEASONS)}
h48 = {"NFL": hourly_counts(nfl, 48 * ob.H, ob.SEASONS), "CFB": hourly_counts(cfb, 48 * ob.H, ob.SEASONS)}
dl = {"NFL": daily_pts(nfl, ob.SEASONS), "CFB": daily_pts(cfb, ob.SEASONS)}

def tot(dd, sports, seasons):
    return sum(len(dd[sp][sn]) for sp in sports for sn in seasons)

def net(hh, sports, seasons):
    return sum(len(hh[sp][sn] - dl[sp][sn]) for sp in sports for sn in seasons)

ALL, S3 = list(ob.SEASONS), [2023, 2024, 2025]
rows = [
    ("F4 as planned: hourly 7d, both sports, 2020-26", tot(h7, ["NFL", "CFB"], ALL), net(h7, ["NFL", "CFB"], ALL)),
    ("hourly 7d, NFL only, 2020-26", tot(h7, ["NFL"], ALL), net(h7, ["NFL"], ALL)),
    ("hourly, final 48h only, both sports, 2020-26", tot(h48, ["NFL", "CFB"], ALL), net(h48, ["NFL", "CFB"], ALL)),
    ("hourly, final 48h only, NFL only, 2020-26", tot(h48, ["NFL"], ALL), net(h48, ["NFL"], ALL)),
    ("hourly 7d, both sports, 2023-25 only", tot(h7, ["NFL", "CFB"], S3), net(h7, ["NFL", "CFB"], S3)),
    ("hourly 7d, NFL only, 2023-25 only", tot(h7, ["NFL"], S3), net(h7, ["NFL"], S3)),
    ("hourly, final 48h, NFL only, 2023-25 only", tot(h48, ["NFL"], S3), net(h48, ["NFL"], S3)),
]
print(f"  {'variant':55} {'snaps':>8} {'gross cr':>11} {'snaps net of F1':>16} {'net cr':>11}")
for lab, n, nn in rows:
    print(f"  {lab:55} {n:>8,} {PER_SNAP * n:>11,} {nn:>16,} {PER_SNAP * nn:>11,}")
print("  per-season hourly 7d NFL:", {k: len(v) for k, v in h7['NFL'].items()})
print("  per-season hourly 7d CFB:", {k: len(v) for k, v in h7['CFB'].items()})
print("  per-season hourly 48h NFL:", {k: len(v) for k, v in h48['NFL'].items()})
print("  per-season hourly 48h CFB:", {k: len(v) for k, v in h48['CFB'].items()})

# ---------------------------------------------------------------- B1 / S1 from the season-structure estimates
print("\n=== B1 (MLB) variants, from odds_5m.SPORTS estimates ===")
mlb = s[s.sport == "MLB"].set_index("season")
print(mlb[["games", "days", "slots", "snapshots", "sealed"]].to_string())
def b1(seasons, col):
    return PER_SNAP * int(mlb.loc[seasons, col].sum())
print(f"  B1 as planned (2020-26 daily+close): {b1(list(mlb.index), 'snapshots'):,}")
print(f"  B1 2024-25 daily+close: {b1(['2024', '2025'], 'snapshots'):,}")
print(f"  B1 2024-25 close only: {b1(['2024', '2025'], 'slots'):,}")
print(f"  B1 2024-26 close only (test sample + sealed confirm): {b1(['2024', '2025', '2026'], 'slots'):,}")
print(f"  B1 2024-26 daily+close: {b1(['2024', '2025', '2026'], 'snapshots'):,}")
print(f"  B1 2026 close only alone: {b1(['2026'], 'slots'):,}")

print("\n=== S1 (soccer) variants ===")
soc = s[s.sport.isin(o5.SOCCER_WHY)].copy()
print(soc.groupby("sport", sort=False)[["games", "snapshots", "slots"]].sum().to_string())
def sel(sports, seasons_pred, col):
    x = soc[soc.sport.isin(sports) & soc.season.apply(seasons_pred)]
    return int(x[col].sum()), x
three = ["MLS", "Liga MX", "Brasileirao"]
allsoc = list(o5.SOCCER_WHY)
y2425 = lambda lab: lab.startswith("2024") or lab.startswith("2025")
y2426 = lambda lab: lab.startswith("2024") or lab.startswith("2025") or lab.startswith("2026")
for lab, sports, pred, col in [
    ("S1 as planned (all, all seasons, daily+close)", allsoc, lambda l: True, "snapshots"),
    ("S1 all leagues+tournaments, 2024-25, daily+close", allsoc, y2425, "snapshots"),
    ("S1 all leagues+tournaments, 2024-25, close only", allsoc, y2425, "slots"),
    ("S1 MLS+LigaMX+Bras, 2024-25, daily+close", three, y2425, "snapshots"),
    ("S1 MLS+LigaMX+Bras, 2024-25, close only", three, y2425, "slots"),
    ("S1 MLS+LigaMX+Bras, 2024-26, close only (incl. sealed 2026)", three, y2426, "slots"),
    ("S1 World Cup 2026 only, close only (sealed)", ["World Cups"], lambda l: l.startswith("2026"), "slots"),
    ("S1 all, 2024-26, close only", allsoc, y2426, "slots"),
    ("S1 all, 2024-26, daily+close", allsoc, y2426, "snapshots"),
]:
    n, x = sel(sports, pred, col)
    print(f"  {lab:62} {n:>7,} snaps -> {PER_SNAP * n:>9,} credits  [{', '.join(sorted(set(x.sport)))}]")

# ---------------------------------------------------------------- N1
print("\n=== N1 ===")
print(f"  N1 as planned: 10 x (49,398 - 754 - 791) = {HIST * (49_398 - 754 - 791):,}")
print(f"  N1 schedule D with nothing cached (5M month replaced the pilot; M5 not in plan): {HIST * 49_398:,}")
print(f"  sample week, schedule A: 10 x 754 = {HIST * 754:,}")
print(f"  full 2025-26 at schedule A: 10 x 16,990 = {HIST * 16_990:,} (sample week's 754 snaps are inside it; "
      f"extra after the week = {HIST * (16_990 - 754):,})")

# ---------------------------------------------------------------- 2026 games that will exist in October 2026
print("\n=== 2026 season: how much exists to pull during an Oct 1-31, 2026 month ===")
for name, d, plan_daily, plan_hourly, plan_games in (("NFL", nfl, 296, 3870, 285), ("CFB", cfb, 522, 3851, 934)):
    x = d[d.season == 2026]
    for cutoff in ("2026-10-04", "2026-11-01"):
        y = x[x.kick.notna() & (x.kick < pd.Timestamp(cutoff, tz="UTC"))]
        print(f"  {name} 2026 kickoffs before {cutoff}: {len(y)} games (plan assumed {plan_games}); "
              f"daily+close snaps {len(ob.grid(y.kick, 7 * ob.D, None, at=16))} (plan {plan_daily}); "
              f"hourly snaps {len(ob.grid(y.kick, 7 * ob.D, ob.H))} (plan {plan_hourly})")
    print(f"  {name} 2026 rows with a kickoff time: {int(x.kick.notna().sum())} of {len(x)}")

# ---------------------------------------------------------------- lean / medium plans
print("\n=== plan totals ===")
F1 = HIST * 3 * c["daily_fb"]
F2 = HIST * 3 * 3 * nfl_p
lean = {
    "F1 as is": F1, "F2 as is": F2, "F3 close only (6 mkts)": HIST * 6 * nfl_p,
    "N1 -> sample week A": 7_540,
    "B1 2024-25 close only": b1(['2024', '2025'], 'slots'),
    "S1 MLS+LigaMX+Bras 2024-25 close only": PER_SNAP * sel(three, y2425, "slots")[0],
}
lean_sealed = dict(lean)
lean_sealed["B1 2024-25 close only"] = b1(['2024', '2025', '2026'], 'slots')
lean_sealed["S1 MLS+LigaMX+Bras 2024-25 close only"] = PER_SNAP * sel(three, y2426, "slots")[0]
lean_sealed["S1 World Cup 2026 close only"] = PER_SNAP * sel(["World Cups"], lambda l: l.startswith("2026"), "slots")[0]
medium = {
    "F1 as is": F1, "F2 as is": F2, "F3 at 2 snaps": HIST * 6 * 2 * nfl_p,
    "F5 team_totals close only": HIST * cfb_p,
    "N1 -> sample week + full 2025-26 at schedule A": HIST * 16_990,
    "B1 2024-26 daily+close": b1(['2024', '2025', '2026'], 'snapshots'),
    "S1 all leagues 2024-26 daily+close": PER_SNAP * sel(allsoc, y2426, "snapshots")[0],
    "F4 hourly NFL only 2020-26 (net of F1 cache)": PER_SNAP * net(h7, ["NFL"], ALL),
}
for lab, dd in (("LEAN (2024-25 test sample only)", lean), ("LEAN + sealed 2026 close-only", lean_sealed), ("MEDIUM", medium)):
    t = sum(dd.values())
    print(f"\n  {lab}: history {t:,}")
    for k, v in dd.items():
        print(f"     {k:52} {v:>9,}")
    for res in (300_000, 531_630):
        print(f"     + reserve {res:,} = {t + res:,}; unallocated of 5M = {5_000_000 - t - res:,}; "
              f"vs 4.18M plan saves {4_175_930 - t:,}")
