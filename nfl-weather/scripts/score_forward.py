"""Score the pre-registered forward tests (PREREGISTRATION.md), one table per rule:

  MODEL_LEAN  model P(under) >= 55% / <= 45%, earliest snapshot >= 24h before kickoff
  RULE_B      early wind under: earliest snapshot whose board status was "SIGNAL"

Each bet is graded at its ENTRY line and ENTRY price (profit in units, pushes return
the stake), with closing-line value measured against the final nflverse total.
Wind triggers that never became a signal (no price, price too high, outside the
horizon) are counted, so coverage gaps can't quietly select winners.

    python scripts/fetch_data.py --skip-weather   # refresh schedule/lines/results
    python scripts/score_forward.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd

from nflweather.config import RAW, ROOT
from nflweather.market import american_to_profit

import argparse

ap = argparse.ArgumentParser()
ap.add_argument("--ledger", default=str(ROOT / "data" / "forward" / "ledger.csv"))
ap.add_argument("--games", default=str(RAW / "games.csv"))
args = ap.parse_args()
ledger = Path(args.ledger)
if not ledger.exists():
    sys.exit("no ledger yet: run scripts/this_week.py or scripts/alerts.py first")
L = pd.read_csv(ledger)
L["snapshot_utc"] = pd.to_datetime(L.snapshot_utc, utc=True)
for c in ("lean", "rule_b", "rules_version"):
    L[c] = L[c].fillna("").astype(str) if c in L else ""
g = pd.read_csv(args.games)[["game_id", "total", "total_line", "gameday", "gametime", "result"]]
g = g.rename(columns={"total_line": "close_total"})
g["kick_utc"] = pd.to_datetime(g.gameday + " " + g.gametime).dt.tz_localize("America/New_York").dt.tz_convert("UTC")
L = L.merge(g[["game_id", "total", "close_total", "kick_utc", "result"]], on="game_id", how="left")
# Amendment 2: evaluation starts with Week 5 (Oct 8, 2026); pre-amendment rows are excluded
L = L[(L.rules_version != "") & (L.kick_utc >= pd.Timestamp("2026-10-08", tz="UTC"))]


def grade(bets, side_col):
    """Outcome at the entry line and price."""
    under = bets[side_col] == "UNDER"
    entry = bets.total_line
    win = np.where(under, bets.total < entry, bets.total > entry)
    push = bets.total == entry
    odds = np.where(under, bets.under_odds, bets.over_odds)
    has_price = ~pd.isna(odds)
    profit = np.where(push, 0.0, np.where(win, american_to_profit(np.where(has_price, odds, -110)), -1.0))
    clv = np.where(under, entry - bets.close_total, bets.close_total - entry)
    return bets.assign(win=win, push=push, profit=profit, clv_pts=clv, priced=has_price)


def report(name, bets):
    settled = bets[bets.result.notna()]
    print(f"\n{name}: {len(bets)} signals, {len(settled)} settled")
    if settled.empty:
        return
    w, p = int(settled.win.sum()), int(settled.push.sum())
    l = len(settled) - w - p
    se = settled.clv_pts.std(ddof=1) / np.sqrt(len(settled)) if len(settled) > 1 else np.nan
    m = settled.clv_pts.mean()
    print(f"  record at entry line {w}-{l}-{p}   units {settled.profit.sum():+.2f} "
          f"(ROI {100 * settled.profit.sum() / max(len(settled) - p, 1):+.1f}%; {int((~settled.priced).sum())} graded at an assumed -110)")
    print(f"  mean CLV {m:+.2f} pts  (95% CI {m - 1.96 * se:+.2f} to {m + 1.96 * se:+.2f})")
    print(settled[["game_id", "side", "total_line", "close_total", "total", "clv_pts", "profit"]].to_string(index=False))


# MODEL_LEAN: original pre-registration
lean = L[L.lean.str.len().gt(0) & (L.snapshot_utc <= L.kick_utc - pd.Timedelta(hours=24))]
lean = lean.sort_values("snapshot_utc").drop_duplicates("game_id")
lean = grade(lean.assign(side=np.where(lean.lean.str.startswith("UNDER"), "UNDER", "OVER")), "side")
report("MODEL_LEAN", lean)

# RULE_B: amendment 1, gated by amendment 2
rb = L[L.rule_b.eq("SIGNAL")].sort_values("snapshot_utc").drop_duplicates("game_id")
rb = grade(rb.assign(side="UNDER"), "side")
report("RULE_B (wind under)", rb)

trig = L[L.rule_b.isin(["no_price", "price_too_high", "negative_ev", "outside_horizon", "SIGNAL"])]
if len(trig):
    print("\nWind triggers by final status (a game counts once, at its best status):")
    order = {"SIGNAL": 0, "negative_ev": 1, "price_too_high": 2, "no_price": 3, "outside_horizon": 4}
    best = trig.assign(o=trig.rule_b.map(order)).sort_values("o").drop_duplicates("game_id")
    print(best.rule_b.value_counts().to_string())
print("\nVariants under forward test: 2 (MODEL_LEAN, RULE_B).")
