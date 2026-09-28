"""Score CFB Rule B signals at the entry line and price; CLV against the last
logged quote before kickoff (cfbfastR has no 2026 closing lines). Amendment 1 adds a secondary
CLV against the total captured just before kickoff (data/forward/closes.csv).

    python scripts/score_forward.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd

from cfbweather.build import schedules
from cfbweather.config import ROOT
from cfbweather.market import american_to_profit

path = ROOT / "data" / "forward" / "ledger.csv"
if not path.exists():
    sys.exit("no ledger yet: run scripts/alerts.py")
L = pd.read_csv(path)
L["snapshot_utc"], L["start_utc"] = pd.to_datetime(L.snapshot_utc, utc=True), pd.to_datetime(L.start_utc, utc=True)
L = L[L.start_utc >= pd.Timestamp("2026-10-01", tz="UTC")]
s = schedules()[["game_id", "home_points", "away_points"]]
s["total"] = s.home_points + s.away_points
close = L[L.snapshot_utc < L.start_utc].dropna(subset=["mkt_total"]).sort_values("snapshot_utc").drop_duplicates("game_id", keep="last")
bets = L[L.rule_b == "SIGNAL"].sort_values("snapshot_utc").drop_duplicates("game_id")
bets = bets.merge(close[["game_id", "mkt_total"]].rename(columns={"mkt_total": "close_total"}), on="game_id", how="left")
bets = bets.merge(s[["game_id", "total"]], on="game_id", how="left")
# Amendment 1: the close captured just before kickoff (scripts/capture_close.py), secondary only
closes = ROOT / "data" / "forward" / "closes.csv"
if closes.exists():
    cap = pd.read_csv(closes).dropna(subset=["close_total"]).drop_duplicates("game_id", keep="last")
    bets = bets.merge(cap[["game_id", "close_total"]].rename(columns={"close_total": "cap_close"}),
                      on="game_id", how="left")
else:
    bets["cap_close"] = np.nan
done = bets[bets.total.notna()].copy()
print(f"RULE_B: {len(bets)} signals, {len(done)} settled")
if len(done):
    win, push = done.total < done.mkt_total, done.total == done.mkt_total
    done["profit"] = np.where(push, 0, np.where(win, american_to_profit(done.mkt_under), -1.0))
    done["clv_pts"] = done.mkt_total - done.close_total
    se = done.clv_pts.std(ddof=1) / np.sqrt(len(done)) if len(done) > 1 else np.nan
    print(f"  record {int(win.sum())}-{int((~win & ~push).sum())}-{int(push.sum())}, units {done.profit.sum():+.2f}; "
          f"mean CLV {done.clv_pts.mean():+.2f} (95% CI {done.clv_pts.mean() - 1.96 * se:+.2f} to {done.clv_pts.mean() + 1.96 * se:+.2f})")
    done["clv_cap"] = done.mkt_total - done.cap_close
    c = done.clv_cap.dropna()
    if len(c):
        cse = c.std(ddof=1) / np.sqrt(len(c)) if len(c) > 1 else np.nan
        print(f"  secondary (amendment 1): mean CLV vs captured close {c.mean():+.2f} "
              f"(95% CI {c.mean() - 1.96 * cse:+.2f} to {c.mean() + 1.96 * cse:+.2f}); "
              f"{len(done) - len(c)} of {len(done)} without a captured close")
    else:
        print(f"  secondary (amendment 1): no captured closes for these {len(done)} bets")
    print(done[["game_id", "kick_et", "away_team", "home_team", "mkt_total", "mkt_under", "close_total", "total", "clv_pts", "profit"]].to_string(index=False))
