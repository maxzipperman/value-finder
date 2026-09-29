"""Score the pre-registered forward tests (PREREGISTRATION.md), one table per rule:

  MODEL_LEAN          model P(under) >= 55% / <= 45%, earliest snapshot >= 24h before kickoff
  RULE_B              early wind under, priced at Pinnacle: the registered test. The entry is the
                      earliest pre-kickoff snapshot whose status was "SIGNAL".
  RULE_B (secondary)  the same gates at the backup price (the consensus line, when Pinnacle had no
                      quote). Reported separately; not part of the keep/drop decision (amendment 5).

What counts (amendments 2, 4 and 5): rows written under a registered rules version, logged before
kickoff, for games from Week 5 (Oct 8, 2026) through the 2027 season. Rows outside that are counted
and listed by reason, never silently dropped.

Each bet is graded at its ENTRY line and ENTRY price (profit in units, pushes return the stake), with
closing-line value against the final nflverse total. Amendment 3 adds a secondary CLV against
Pinnacle's total captured just before kickoff (data/forward/closes.csv). ROI is units won per bet
placed; a push counts as a bet. Wind triggers that never became a signal (no price, price too high,
outside the horizon) are counted, so coverage gaps can't quietly select winners.

    python scripts/fetch_data.py --skip-weather   # refresh schedule/lines/results
    python scripts/score_forward.py
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd

from nflweather.board import PRIMARY_SRC, REGISTERED_VERSIONS
from nflweather.config import RAW, ROOT
from nflweather.market import american_to_profit, cost_of_waiting

FIRST_KICK = pd.Timestamp("2026-10-08", tz="UTC")     # amendment 2: Week 5 onward
TEST_SEASONS = (2026, 2027)                           # amendment 4: the two seasons are pooled
BREAK_EVEN = 110 / 210                                # -110
ENOUGH = 40

ap = argparse.ArgumentParser()
ap.add_argument("--ledger", default=str(ROOT / "data" / "forward" / "ledger.csv"))
ap.add_argument("--games", default=str(RAW / "games.csv"))
args = ap.parse_args()
ledger = Path(args.ledger)
if not ledger.exists():
    sys.exit("no ledger yet: run scripts/this_week.py or scripts/alerts.py first")
L = pd.read_csv(ledger)
L["snapshot_utc"] = pd.to_datetime(L.snapshot_utc, utc=True)
for c in ("lean", "rule_b", "rules_version", "line_src"):
    L[c] = L[c].fillna("").astype(str) if c in L else ""
G = pd.read_csv(args.games)
G["kick_utc"] = pd.to_datetime(G.gameday + " " + G.gametime).dt.tz_localize("America/New_York").dt.tz_convert("UTC")
if "season" not in G:      # a season runs from September into February
    d = pd.to_datetime(G.gameday)
    G["season"] = np.where(d.dt.month >= 8, d.dt.year, d.dt.year - 1)
for c in ("week", "game_type"):
    if c not in G:
        G[c] = np.nan
g = G[["game_id", "total", "total_line", "kick_utc", "result", "season", "week"]].rename(
    columns={"total_line": "close_total"})
L = L.merge(g, on="game_id", how="left")
# Amendment 3: the Pinnacle close captured just before kickoff (scripts/capture_close.py), secondary only
closes = ledger.parent / "closes.csv"
cap = pd.read_csv(closes) if closes.exists() else pd.DataFrame(columns=["game_id", "book", "close_total"])
cap = (cap[cap.book.eq("pinnacle")].dropna(subset=["close_total"]).drop_duplicates("game_id", keep="last")
       [["game_id", "close_total"]].rename(columns={"close_total": "cap_close"}))
L = L.merge(cap, on="game_id", how="left")

# What counts. Every excluded row is counted by its first failing reason.
why = np.select([~L.rules_version.isin(REGISTERED_VERSIONS), L.kick_utc.isna(), L.kick_utc < FIRST_KICK,
                 ~L.season.isin(TEST_SEASONS), L.snapshot_utc >= L.kick_utc],
                ["unregistered rules version", "game not in the schedule", "before Week 5 (Oct 8, 2026)",
                 "after the 2027 season", "logged at or after kickoff"], "")
print(f"ledger rows: {len(L)}; in the test: {int((why == '').sum())}")
for reason, n in pd.Series(why[why != ""]).value_counts().items():
    print(f"  excluded, {reason}: {n}")
L = L[why == ""]


def season_complete(season):
    """True once every regular-season game of `season` in the schedule has a result."""
    s = G[(G.season == season) & (G.game_type.astype(str) == "REG")]
    return len(s) > 0 and bool(s.result.notna().all())


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
    cap = pd.to_numeric(bets.cap_close, errors="coerce")
    clv_cap = np.where(under, entry - cap, cap - entry)
    beat = np.where(under, bets.total < bets.close_total, bets.total > bets.close_total)   # vs the close
    tie = bets.total == bets.close_total
    return bets.assign(win=win, push=push, profit=profit, clv_pts=clv, clv_cap=clv_cap, priced=has_price,
                       beat_close=beat, tie_close=tie)


def mean_ci(x):
    x = pd.Series(x).dropna()
    if not len(x):
        return np.nan, np.nan, np.nan, 0
    se = x.std(ddof=1) / np.sqrt(len(x)) if len(x) > 1 else np.nan
    return x.mean(), x.mean() - 1.96 * se, x.mean() + 1.96 * se, len(x)


def report(name, bets):
    settled = bets[bets.result.notna()]
    print(f"\n{name}: {len(bets)} signals, {len(settled)} settled")
    if settled.empty:
        return settled
    w, p = int(settled.win.sum()), int(settled.push.sum())
    m, lo, hi, n = mean_ci(settled.clv_pts)
    print(f"  record at entry line {w}-{len(settled) - w - p}-{p}   units {settled.profit.sum():+.2f} "
          f"(ROI {100 * settled.profit.sum() / len(settled):+.1f}% per bet placed; "
          f"{int((~settled.priced).sum())} graded at an assumed -110)")
    print(f"  mean CLV {m:+.2f} pts  (95% CI {lo:+.2f} to {hi:+.2f}; {n} of {len(settled)} bets have a primary close)")
    cm, clo, chi, cn = mean_ci(settled.clv_cap)
    if cn:
        print(f"  secondary (amendment 3): mean CLV vs captured Pinnacle close {cm:+.2f} pts "
              f"(95% CI {clo:+.2f} to {chi:+.2f}); {len(settled) - cn} of {len(settled)} without a captured close")
    else:
        print(f"  secondary (amendment 3): no captured closes for these {len(settled)} bets")
    print(settled[["game_id", "side", "line_src", "total_line", "close_total", "total", "clv_pts", "profit"]]
          .to_string(index=False))
    return settled


def decide(name, settled, final, split, split_name):
    """The registered keep/drop test. `split` labels each bet's half (or season); CLV must be positive
    in every part. An interim read prints the same numbers and decides nothing."""
    if settled is None or settled.empty:
        print(f"  decision ({name}): nothing settled yet")
        return None
    m, lo, hi, n = mean_ci(settled.clv_pts)
    graded = settled[~settled.tie_close]
    rate = graded.beat_close.mean() if len(graded) else np.nan
    parts = settled.assign(part=split).groupby("part").clv_pts.mean()
    both = len(parts) >= 2 and bool((parts > 0).all())
    keep = bool(m > 0 and lo > 0 and rate >= BREAK_EVEN and both)
    drop = bool(m <= 0 or hi < 0.25)
    verdict = "KEEP" if keep else "DROP" if drop else "INCONCLUSIVE (carry forward unchanged)"
    print(f"  decision ({name}), {'FINAL' if final else 'INTERIM read, decides nothing'}: {verdict}")
    print(f"    mean CLV {m:+.2f} (95% CI {lo:+.2f} to {hi:+.2f}, n={n}); win rate vs the close "
          f"{100 * rate:.1f}% (needs {100 * BREAK_EVEN:.1f}%); mean CLV by {split_name}: "
          f"{ {str(k): round(float(v), 2) for k, v in parts.items()} }")
    return verdict if final else None


def halves(df):
    return np.where(pd.to_numeric(df.week, errors="coerce") <= 11, "Weeks 5-11", "Weeks 12-18")


pre = L[L.snapshot_utc < L.kick_utc]

# MODEL_LEAN: the original pre-registration, on its original horizon
lean = pre[pre.lean.str.len().gt(0) & (pre.snapshot_utc <= pre.kick_utc - pd.Timedelta(hours=24))]
lean = lean.sort_values("snapshot_utc").drop_duplicates("game_id")
lean = grade(lean.assign(side=np.where(lean.lean.str.startswith("UNDER"), "UNDER", "OVER")), "side")
done = report("MODEL_LEAN", lean)
if len(done):
    decide("model lean: after Week 18 and 40 leans, whichever is later", done[done.season == 2026],
           season_complete(2026) and len(done) >= ENOUGH, halves(done[done.season == 2026]), "half")

# RULE_B: amendment 1, gated by amendment 2, priced by amendment 5
sig = pre[pre.rule_b.isin(["SIGNAL", "SIGNAL_SECONDARY"])]
primary = sig[sig.rule_b.eq("SIGNAL") & sig.line_src.eq(PRIMARY_SRC)]
rb = grade(primary.sort_values("snapshot_utc").drop_duplicates("game_id").assign(side="UNDER"), "side")
done = report("RULE_B (wind under)", rb)
if len(done):
    in_one = len(done) >= ENOUGH and done.season.nunique() == 1     # 40 signals inside one season
    final = len(done) >= ENOUGH or season_complete(2027)
    decide("Rule B: once, after the 2027 season or at 40 signals", done, final,
           halves(done) if in_one else done.season.astype(int).values, "half" if in_one else "season")

second = sig[~sig.game_id.isin(rb.game_id)]
second = grade(second.sort_values("snapshot_utc").drop_duplicates("game_id").assign(side="UNDER"), "side")
if len(second):
    report("RULE_B, secondary price (not part of the decision)", second)
else:
    print("\nRULE_B, secondary price (not part of the decision): 0 signals")

trig = pre[pre.rule_b.isin(["no_price", "price_too_high", "negative_ev", "outside_horizon", "SIGNAL",
                            "SIGNAL_SECONDARY"])]
if len(trig):
    print("\nWind triggers by final status (a game counts once, at its best status):")
    order = {"SIGNAL": 0, "SIGNAL_SECONDARY": 1, "negative_ev": 2, "price_too_high": 3, "no_price": 4,
             "outside_horizon": 5}
    best = trig.assign(o=trig.rule_b.map(order)).sort_values("o").drop_duplicates("game_id")
    print(best.rule_b.value_counts().to_string())
# Cost of waiting (issue #5): paper fills from scripts/log_fill.py vs the alert-time quote
fills_path = ledger.parent / "fills.csv"
if fills_path.exists():
    fills = pd.read_csv(fills_path, dtype={"game_id": str}).drop_duplicates(["game_id", "rule"], keep="last")
    entries = rb[["game_id", "total_line", "under_odds"]].rename(
        columns={"total_line": "entry_line", "under_odds": "entry_price"}).assign(rule="rule_b")
    wc = cost_of_waiting(entries, fills)
    if len(wc):
        print(f"\nCost of waiting, RULE_B: {len(wc)} paper fills; vs the alert-time quote the fill gained "
              f"{wc.pts_gained.mean():+.2f} pts and {wc.profit_gained.mean():+.3f} units of payout per unit staked")
print("\nDecision horizons. Rule B (amendments 4 and 5): once, after the 2027 season, on 2026 Weeks 5+ and 2027 "
      "pooled, or at 40 signals if sooner. Model lean: after Week 18 of 2026 and 40 leans, whichever is later.")
print("Variants under forward test: 2 (MODEL_LEAN, RULE_B).")
