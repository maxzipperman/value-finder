import json
from collections import defaultdict
from pathlib import Path
C = Path(__file__).resolve().parents[3] / "strategy-research" / "data" / "heat"
venue_rows = json.loads((C / "soccer_venue_rows.json").read_text())
team_rows = json.loads((C / "soccer_team_rows.json").read_text())
# venues actually used by each league-season (from the team rows), to drop the K1-2025 / J1-2025 shared-window duplicates
used = defaultdict(set)
for t in team_rows:
    for vid in t["venues"]:
        used[(t["sport"], t["season"])].add(vid)
agg = defaultdict(lambda: defaultdict(float))
for r in venue_rows:
    k = (r["sport"], r["season"])
    if r["venue_id"] not in used[k]:
        continue
    a = agg[k]
    a["venues"] += 1
    a["venue_days"] += r.get("days", 0)
    for f in ("hi19>=85", "hi19>=90", "hi19>=95", "himax>=90", "hi16>=90"):
        a[f] += r.get(f, 0)
print(f"{'league':26s} {'season':6s} {'open venues':>11s} {'venue-days':>10s} {'HI19>=85':>8s} {'HI19>=90':>8s} {'HI19>=95':>8s} {'HImax>=90':>9s} {'HI16>=90':>8s} {'1/wk matches HI19>=90':>21s}")
tot = defaultdict(float)
for k in sorted(agg):
    a = agg[k]
    print(f"{k[0]:26s} {k[1]:6s} {a['venues']:11.0f} {a['venue_days']:10.0f} {a['hi19>=85']:8.0f} {a['hi19>=90']:8.0f} {a['hi19>=95']:8.0f} {a['himax>=90']:9.0f} {a['hi16>=90']:8.0f} {a['hi19>=90']/7:21.1f}")
    for f in a: tot[f] += a[f]
print(f"{'TOTAL':33s} {tot['venues']:11.0f} {tot['venue_days']:10.0f} {tot['hi19>=85']:8.0f} {tot['hi19>=90']:8.0f} {tot['hi19>=95']:8.0f} {tot['himax>=90']:9.0f} {tot['hi16>=90']:8.0f} {tot['hi19>=90']/7:21.1f}")
# Top teams by expected qualifying home matches
print("\nTop 15 team-seasons by E[qualifying home matches, HI19>=90]:")
for t in sorted(team_rows, key=lambda t: -t["exp_matches_hi19_90"])[:15]:
    print(f"  {t['sport']:26s} {t['season']} {t['team']:28s} venues={list(t['venues'])} E={t['exp_matches_hi19_90']:.1f} (hi19>=90 days {t.get('hi19>=90',0)} of {t['open_days']})")
print("\nUnresolved team-days:", [(t['sport'], t['season'], t['team'], t['unresolved_days']) for t in team_rows if t['unresolved_days']])
