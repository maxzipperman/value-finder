"""Score the pre-registered forward test (PREREGISTRATION.md) against closing
totals and results from the refreshed nflverse schedule.

    python scripts/fetch_data.py --skip-weather   # refresh schedule/lines
    python scripts/score_forward.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd

from nflweather.config import RAW, ROOT
from nflweather.market import record

ledger = ROOT / "data" / "forward" / "ledger.csv"
if not ledger.exists():
    sys.exit("no ledger yet: run scripts/this_week.py first")
L = pd.read_csv(ledger, parse_dates=["snapshot_utc"])
g = pd.read_csv(RAW / "games.csv")[["game_id", "total", "total_line", "gameday", "gametime", "result"]]
g = g.rename(columns={"total_line": "close_total"})
g["kick_utc"] = pd.to_datetime(g.gameday + " " + g.gametime).dt.tz_localize("America/New_York").dt.tz_convert("UTC")

L = L.merge(g[["game_id", "total", "close_total", "kick_utc", "result"]], on="game_id", how="left")
L = L[L.result.notna() & L.lean.fillna("").str.len().gt(0)]
L = L[L.snapshot_utc <= L.kick_utc - pd.Timedelta(hours=24)]
first = L.sort_values("snapshot_utc").drop_duplicates("game_id")   # earliest qualifying snapshot
if first.empty:
    sys.exit("no settled leans yet")
under = first.lean.str.startswith("UNDER")
first["clv_pts"] = np.where(under, first.total_line - first.close_total, first.close_total - first.total_line)
win = np.where(under, first.total < first.close_total, first.total > first.close_total)
loss = np.where(under, first.total > first.close_total, first.total < first.close_total)
rec = record(win, loss)
se = first.clv_pts.std(ddof=1) / np.sqrt(len(first)) if len(first) > 1 else np.nan
print(f"leans settled: {len(first)}   variants examined: 1 (pre-registered)")
print(f"mean CLV: {first.clv_pts.mean():+.2f} pts  (95% CI {first.clv_pts.mean() - 1.96 * se:+.2f} to {first.clv_pts.mean() + 1.96 * se:+.2f})")
print(f"vs close: {rec['wins']}-{rec['bets'] - rec['wins']}  ({100 * rec['win_pct']:.1f}%, ROI at -110 {100 * rec['roi_110']:+.1f}%)")
print(first[["game_id", "lean", "total_line", "close_total", "total", "clv_pts"]].to_string(index=False))
