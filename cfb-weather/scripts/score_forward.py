"""Score the pre-registered CFB forward tests (STRATEGY.md, PREREGISTRATION.md):

  RULE_B   wind under: earliest SIGNAL snapshot, graded at its entry line and price; CLV
           against the last logged quote before kickoff (cfbfastR has no 2026 closing lines).
           Amendment 2 adds a secondary CLV against the close captured just before kickoff.
  RULE_HT  high-total under (amendment 1), from 2026 Week 6: each game's LAST logged quote
           before kickoff, if that quote is a SIGNAL. Graded on win rate and ROI at that
           price; the promotion test is one-sided vs the break-even of the prices taken.

    python scripts/score_forward.py [--ledger PATH] [--schedule PATH]
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd

from scipy import stats

from cfbweather.board import HT_FIRST_KICK
from cfbweather.config import ROOT
from cfbweather.market import american_to_profit, cost_of_waiting

ap = argparse.ArgumentParser()
ap.add_argument("--ledger", default=str(ROOT / "data" / "forward" / "ledger.csv"))
ap.add_argument("--schedule", help="CSV with game_id, home_points, away_points (default: cfbfastR schedules)")
args = ap.parse_args()
path = Path(args.ledger)
if not path.exists():
    sys.exit("no ledger yet: run scripts/alerts.py")
L = pd.read_csv(path)
L["snapshot_utc"], L["start_utc"] = pd.to_datetime(L.snapshot_utc, utc=True), pd.to_datetime(L.start_utc, utc=True)
L = L[L.start_utc >= pd.Timestamp("2026-10-01", tz="UTC")]
if args.schedule:
    s = pd.read_csv(args.schedule)
else:
    from cfbweather.build import schedules
    s = schedules()
s = s[["game_id", "home_points", "away_points"]].copy()
s["game_id"] = pd.to_numeric(s.game_id)
s["total"] = s.home_points + s.away_points
close = L[L.snapshot_utc < L.start_utc].dropna(subset=["mkt_total"]).sort_values("snapshot_utc").drop_duplicates("game_id", keep="last")
# Amendment 2: the close captured 2-20 minutes before kickoff (scripts/capture_close.py). Secondary and
# descriptive only; missing closes are counted, never imputed.
cap_path = path.parent / "closes.csv"
cap = (pd.read_csv(cap_path).dropna(subset=["close_total"]).drop_duplicates("game_id", keep="last")
       if cap_path.exists() else pd.DataFrame(columns=["game_id", "close_total"]))
cap = pd.Series(cap.close_total.values, index=pd.to_numeric(cap.game_id), dtype=float)


def secondary(df, label):
    clv = (df.mkt_total - df.game_id.map(cap)).dropna()
    if not len(clv):
        print(f"  secondary (amendment 2): no captured closes for these {len(df)} {label}")
        return
    se = clv.std(ddof=1) / np.sqrt(len(clv)) if len(clv) > 1 else np.nan
    print(f"  secondary (amendment 2): mean CLV vs the captured close {clv.mean():+.2f} "
          f"(95% CI {clv.mean() - 1.96 * se:+.2f} to {clv.mean() + 1.96 * se:+.2f}); "
          f"{len(df) - len(clv)} of {len(df)} {label} without a captured close")


bets = L[L.rule_b == "SIGNAL"].sort_values("snapshot_utc").drop_duplicates("game_id")
bets = bets.merge(close[["game_id", "mkt_total"]].rename(columns={"mkt_total": "close_total"}), on="game_id", how="left")
bets = bets.merge(s[["game_id", "total"]], on="game_id", how="left")
done = bets[bets.total.notna()].copy()
print(f"RULE_B: {len(bets)} signals, {len(done)} settled")
if len(done):
    win, push = done.total < done.mkt_total, done.total == done.mkt_total
    done["profit"] = np.where(push, 0, np.where(win, american_to_profit(done.mkt_under), -1.0))
    done["clv_pts"] = done.mkt_total - done.close_total
    se = done.clv_pts.std(ddof=1) / np.sqrt(len(done)) if len(done) > 1 else np.nan
    print(f"  record {int(win.sum())}-{int((~win & ~push).sum())}-{int(push.sum())}, units {done.profit.sum():+.2f}; "
          f"mean CLV {done.clv_pts.mean():+.2f} (95% CI {done.clv_pts.mean() - 1.96 * se:+.2f} to {done.clv_pts.mean() + 1.96 * se:+.2f})")
    secondary(done, "bets")
    print(done[["game_id", "kick_et", "away_team", "home_team", "mkt_total", "mkt_under", "close_total", "total", "clv_pts", "profit"]].to_string(index=False))


# ---------------------------------------------------------------- Rule HT (amendment 1)
ht = close[(close.start_utc >= HT_FIRST_KICK)] if "rule_ht" in close else close.iloc[0:0]
ht = ht[ht.rule_ht == "SIGNAL"].merge(s[["game_id", "total"]], on="game_id", how="left") if len(ht) else ht
ht_done = ht[ht.total.notna()].copy() if len(ht) else ht
print(f"\nRULE_HT: {len(ht)} signals at the last quote before kickoff, {len(ht_done)} settled")
if len(ht_done):
    win, push = ht_done.total < ht_done.mkt_total, ht_done.total == ht_done.mkt_total
    ht_done["profit"] = np.where(push, 0, np.where(win, american_to_profit(ht_done.mkt_under), -1.0))
    w, n = int(win.sum()), int((~push).sum())
    be = float(np.mean(1 / (1 + american_to_profit(ht_done.mkt_under[~push]))))   # break-even of the prices taken
    p = stats.binomtest(w, n, be, alternative="greater").pvalue if n else np.nan
    print(f"  record {w}-{n - w}-{int(push.sum())} ({100 * w / max(n, 1):.1f}%), units {ht_done.profit.sum():+.2f}, "
          f"ROI {100 * ht_done.profit.sum() / len(ht_done):+.1f}%; break-even {100 * be:.1f}%, one-sided p {p:.3f}")
    secondary(ht_done, "bets")
    print(ht_done[["game_id", "kick_et", "away_team", "home_team", "mkt_total", "mkt_under", "ht_threshold", "total",
                   "profit"]].to_string(index=False))

# ---------------------------------------------------------------- cost of waiting (issue #5)
fills_path = path.parent / "fills.csv"
if fills_path.exists():
    fills = pd.read_csv(fills_path).drop_duplicates(["game_id", "rule"], keep="last")
    fills["game_id"] = pd.to_numeric(fills.game_id)
    for rule, e in (("rule_b", bets), ("rule_ht", ht)):
        if not len(e):
            continue
        entries = e[["game_id", "mkt_total", "mkt_under"]].rename(
            columns={"mkt_total": "entry_line", "mkt_under": "entry_price"}).assign(rule=rule)
        wc = cost_of_waiting(entries, fills)
        if len(wc):
            print(f"\nCost of waiting, {rule.upper()}: {len(wc)} paper fills; vs the rule's quote the fill gained "
                  f"{wc.pts_gained.mean():+.2f} pts and {wc.profit_gained.mean():+.3f} units of payout per unit staked")
