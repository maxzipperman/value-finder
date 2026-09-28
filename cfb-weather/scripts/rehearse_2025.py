"""Dress rehearsal: replay the 2025 season from Week 5 through this season's Rule B and Rule HT
code, ledger format and scorer, as if it were live. It tests the plumbing and shows the workload;
it is not evidence for either rule and adds no variants.

How the replay is built (no downloads, no API calls):
* Four snapshots per FBS game with a closing total: 72h, 48h, 24h and 2h before kickoff. The first
  two quote cfbfastR's OPENING total, the last two its CLOSING total, so Rule B entries (earliest
  SIGNAL) get a real open-to-close CLV and Rule HT (last quote) enters at the close.
* Prices are -110 both ways (cfbfastR has no prices).
* Wind: the observed station wind stands in for the forecast, i.e. a perfect forecast. That flatters
  Rule B; a real forecast replay needs Open-Meteo, which runs on the Mac.
* Statuses come from board.rule_b_status, board.rule_ht_status and board.ht_threshold(2025).
* Dates move forward 53 weeks (same weekday) so the unmodified scorer's 2026 windows apply:
  2025 Week 6 (Oct 3) lands after Rule HT's start (2026-10-07 00:00 UTC).

Outputs: output/tables/rehearsal_2025.csv (ledger), output/rehearsal_2025.log (console)
    python scripts/rehearse_2025.py
"""
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd

from cfbweather import board
from cfbweather.config import OUT, PROC, ROOT
from cfbweather.market import cohort_residuals, ev_under, load_games

SHIFT = pd.Timedelta(weeks=53)
g = pd.read_parquet(PROC / "games.parquet")
g = g[(g.season == 2025) & ((g.home_division == "fbs") | (g.away_division == "fbs")) & g.close_total.notna()
      & g.home_points.notna() & ((g.week >= 5) | (g.season_type == "postseason"))].copy()
g["open_total"] = g.open_total.fillna(g.close_total)
threshold = board.ht_threshold(2025)

hist = load_games(2006, board.PRICING_LAST_SEASON)
resid = cohort_residuals(hist, (hist.outdoor == 1) & (hist.wx_wind >= board.RULE_B_WIND))

rows = []
for hours, lead, col in ((72, 3, "open_total"), (48, 2, "open_total"), (24, 1, "close_total"), (2, 0, "close_total")):
    s = g.copy()
    s["wx_src"] = np.where(s.dome.fillna(False).astype(bool), "indoor",
                           np.where(s.wx_src.eq("station") & s.wx_wind.notna(), "forecast", "no_forecast"))
    s["lead_days"] = lead
    s["line_src"] = "cfbfastR " + col.split("_")[0]
    s["mkt_total"], s["mkt_under"], s["mkt_over"] = s[col], -110.0, -110.0
    s["ev_under"] = ev_under(s.mkt_total, s.mkt_under, s.mkt_total, resid)
    s["rule_b"] = s.apply(board.rule_b_status, axis=1)
    s["ht_threshold"] = threshold
    s["rule_ht"] = s.apply(board.rule_ht_status, axis=1)
    s["snapshot_utc"] = s.start_utc - pd.Timedelta(hours=hours)
    rows.append(s)
S = pd.concat(rows, ignore_index=True)
S["start_s"] = S.start_utc + SHIFT
S["rule_ht"] = np.where(S.start_s >= board.HT_FIRST_KICK, S.rule_ht, "before_window")

led = S.assign(snapshot_utc=(S.snapshot_utc + SHIFT).dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
               rules_version=board.RULES_VERSION, venue=S.venue_name,
               kick_et=S.start_s.dt.tz_convert("America/New_York").dt.strftime("%a %m-%d %H:%M"),
               best_under=np.nan, best_under_book="", start_utc=S.start_s.dt.strftime("%Y-%m-%dT%H:%M:%SZ"))
led = led[["snapshot_utc", "rules_version"] + board.COLS + ["start_utc"]]
sched = g[["game_id", "home_points", "away_points"]]

with tempfile.TemporaryDirectory() as tmp:
    led.to_csv(Path(tmp) / "ledger.csv", index=False)
    sched.to_csv(Path(tmp) / "sched.csv", index=False)
    out = subprocess.run([sys.executable, str(ROOT / "scripts" / "score_forward.py"), "--ledger",
                          str(Path(tmp) / "ledger.csv"), "--schedule", str(Path(tmp) / "sched.csv")],
                         capture_output=True, text=True, check=True).stdout

(OUT / "tables").mkdir(parents=True, exist_ok=True)
led.to_csv(OUT / "tables" / "rehearsal_2025.csv", index=False)
order = {"SIGNAL": 0, "negative_ev": 1, "price_too_high": 2, "no_price": 3, "outside_horizon": 4}
rb = S[S.rule_b.isin(order)].assign(o=lambda d: d.rule_b.map(order)).sort_values("o").drop_duplicates("game_id")
last = S.sort_values("snapshot_utc").drop_duplicates("game_id", keep="last")
wlab = lambda d: np.where(d.season_type == "postseason", "bowls", d.week.astype(int).astype(str))  # noqa: E731
order_w = [str(w) for w in sorted(g[g.season_type != "postseason"].week.unique())] + ["bowls"]
wk = pd.DataFrame({"games": g.groupby(wlab(g)).size(),
                   "rule_b_signals": rb[rb.rule_b == "SIGNAL"].pipe(lambda d: d.groupby(wlab(d)).size()),
                   "rule_ht_signals": last[last.rule_ht == "SIGNAL"].pipe(lambda d: d.groupby(wlab(d)).size())}
                  ).reindex(order_w).fillna(0).astype(int)
print("CFB dress rehearsal: 2025 from Week 5 through this season's Rule B and Rule HT code and scorer")
print(f"  {len(g)} FBS games with a closing total; {len(led)} ledger rows (4 per game); "
      f"Rule HT threshold for 2025 = {threshold:.2f}")
print(f"  Rule B snapshot statuses: {S.rule_b.value_counts().to_dict()}")
print(f"  Rule HT at the last quote: {last.rule_ht.value_counts().to_dict()}")
print("\nPer week (2025 week numbers):\n" + wk.T.to_string())
print("\nScorer output (Rule B entry = the opening total, CLV to the close; Rule HT at the close):\n" + out)
