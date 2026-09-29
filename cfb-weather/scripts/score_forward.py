"""Score the pre-registered CFB forward tests (STRATEGY.md, PREREGISTRATION.md):

  RULE_B   wind under: earliest pre-kickoff SIGNAL snapshot, graded at its entry line and price; CLV
           against the last logged quote before kickoff (cfbfastR has no 2026 closing lines).
           Amendment 2 adds a secondary CLV against the close captured just before kickoff.
  RULE_HT  high-total under (amendment 1), from 2026 Week 6: each game's LAST logged quote
           before kickoff, if that quote is a SIGNAL. Graded on win rate and ROI at that
           price; the promotion test is one-sided against the break-even of the prices taken.

What counts (amendment 3): rows written under a registered rules version, logged before kickoff, for
games from Oct 1, 2026 through the 2027 season's title game. Rows outside that are counted by reason,
never silently dropped; --list-excluded prints each one. ROI is units won per bet placed; a push
counts as a bet. A game is graded only once the schedule marks it completed.

The decisions are computed here and labelled. A FINAL decision is made once, on the bets that kicked
off by its horizon, so a later run prints the same numbers. Before the horizon the script prints an
interim read, which shows the numbers and decides nothing.

    python scripts/score_forward.py [--ledger PATH] [--schedule PATH] [--list-excluded]
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd

from cfbweather.board import HT_FIRST_KICK, REGISTERED_VERSIONS, TEST_SEASONS, season_of
from cfbweather.config import ROOT
from cfbweather.market import american_to_profit, cost_of_waiting

FIRST_KICK = pd.Timestamp("2026-10-01", tz="UTC")
REG_END_2026 = pd.Timestamp("2026-12-13T08:00:00Z")   # the 2026 regular season ends with Army-Navy, Dec 12
TEST_END = pd.Timestamp("2028-02-01T00:00:00Z")       # after the 2027 season's title game (January 2028)
PENDING = pd.Timedelta(days=7)      # a game with no score a week after its kickoff was not played
ENOUGH = 40

ap = argparse.ArgumentParser()
ap.add_argument("--ledger", default=str(ROOT / "data" / "forward" / "ledger.csv"))
ap.add_argument("--schedule", help="CSV with game_id, home_points, away_points (default: cfbfastR schedules)")
ap.add_argument("--list-excluded", action="store_true", help="print every excluded row with its reason")
ap.add_argument("--now", help="score as of this UTC time (tests and rehearsals); default: the clock")
args = ap.parse_args()
NOW = pd.Timestamp(args.now, tz="UTC") if args.now else pd.Timestamp.now(tz="UTC")
path = Path(args.ledger)
if not path.exists():
    sys.exit("no ledger yet: run scripts/alerts.py")
L = pd.read_csv(path)
L["snapshot_utc"], L["start_utc"] = pd.to_datetime(L.snapshot_utc, utc=True), pd.to_datetime(L.start_utc, utc=True)
L["rules_version"] = L.rules_version.fillna("").astype(str) if "rules_version" in L else ""
L["season"] = L.start_utc.map(season_of)
if args.schedule:
    S = pd.read_csv(args.schedule)
else:
    from cfbweather.build import schedules
    S = schedules()
s = S[["game_id", "home_points", "away_points"]].copy()
s["game_id"] = pd.to_numeric(s.game_id)
s["total"] = s.home_points + s.away_points
if "completed" in S:        # the feed scores a game that was never played 0-0: grade completed games only
    played = S.completed.astype(str).str.lower().isin(["true", "1", "1.0"])
    print(f"schedule rows with a score but not marked completed (not graded): "
          f"{int((~played & s.total.notna()).sum())}")
    s.loc[~played.values, "total"] = np.nan

# What counts. Every excluded row is counted by its first failing reason.
why = np.select([~L.rules_version.isin(REGISTERED_VERSIONS), L.start_utc.isna(), L.start_utc < FIRST_KICK,
                 ~L.season.isin(TEST_SEASONS), L.snapshot_utc >= L.start_utc],
                ["unregistered rules version", "no kickoff time in the row", "before Oct 1, 2026",
                 "after the 2027 season", "logged at or after kickoff"], "")
print(f"ledger rows: {len(L)}; in the test: {int((why == '').sum())}")
for reason, n in pd.Series(why[why != ""]).value_counts().items():
    print(f"  excluded, {reason}: {n}")
if args.list_excluded and (why != "").any():
    print(L.assign(excluded=why)[why != ""][["snapshot_utc", "game_id", "rules_version", "rule_b", "excluded"]]
          .to_string(index=False))
L = L[why == ""]


def interim(name, when, tests):
    print(f"  decision ({name}): INTERIM read, decides nothing. The decision comes {when}.")
    print("    as the numbers stand: " + "; ".join(f"{k} ({'met' if bool(v) else 'not met'})" for k, v in tests.items()))


def mean_ci(x):
    x = pd.Series(x).dropna()
    if not len(x):
        return np.nan, np.nan, np.nan, 0
    se = x.std(ddof=1) / np.sqrt(len(x)) if len(x) > 1 else np.nan
    return x.mean(), x.mean() - 1.96 * se, x.mean() + 1.96 * se, len(x)


def tail_at_least(wins, probs):
    """P(W >= wins) when bet i wins with probability probs[i]: the exact test against each bet's own
    break-even. With one price for every bet it is the ordinary binomial test."""
    dist = np.array([1.0])
    for p in probs:
        dist = np.convolve(dist, [1 - p, p])
    return float(dist[int(wins):].sum())


last = L.dropna(subset=["mkt_total"]).sort_values("snapshot_utc").drop_duplicates("game_id", keep="last")
# Amendment 2: the close captured 2-20 minutes before kickoff (scripts/capture_close.py). Secondary and
# descriptive only; missing closes are counted, never imputed.
cap_path = path.parent / "closes.csv"
cap = (pd.read_csv(cap_path).dropna(subset=["close_total"]).drop_duplicates("game_id", keep="last")
       if cap_path.exists() else pd.DataFrame(columns=["game_id", "close_total"]))
cap = pd.Series(cap.close_total.values, index=pd.to_numeric(cap.game_id), dtype=float)


def secondary(df, label):
    m, lo, hi, n = mean_ci(df.mkt_total - df.game_id.map(cap))
    if not n:
        print(f"  secondary (amendment 2): no captured closes for these {len(df)} {label}")
        return
    print(f"  secondary (amendment 2): mean CLV vs the captured close {m:+.2f} "
          f"(95% CI {lo:+.2f} to {hi:+.2f}); {len(df) - n} of {len(df)} {label} without a captured close")


# ---------------------------------------------------------------- Rule B
bets = L[L.rule_b == "SIGNAL"].sort_values("snapshot_utc").drop_duplicates("game_id")
bets = bets.merge(last[["game_id", "mkt_total", "snapshot_utc"]].rename(
    columns={"mkt_total": "close_total", "snapshot_utc": "close_utc"}), on="game_id", how="left")
bets = bets.merge(s[["game_id", "total"]], on="game_id", how="left")
done = bets[bets.total.notna()].copy()
print(f"\nRULE_B: {len(bets)} signals, {len(done)} settled")
if len(done):
    win, push = done.total < done.mkt_total, done.total == done.mkt_total
    done["profit"] = np.where(push, 0, np.where(win, american_to_profit(done.mkt_under), -1.0))
    done["clv_pts"] = done.mkt_total - done.close_total
    m, lo, hi, n = mean_ci(done.clv_pts)
    print(f"  record {int(win.sum())}-{int((~win & ~push).sum())}-{int(push.sum())}, units {done.profit.sum():+.2f} "
          f"(ROI {100 * done.profit.sum() / len(done):+.1f}% per bet placed); "
          f"mean CLV {m:+.2f} (95% CI {lo:+.2f} to {hi:+.2f}; {n} of {len(done)} bets have a primary close)")
    own = int((done.close_utc == done.snapshot_utc).sum())
    stale = int(((done.start_utc - done.close_utc) > pd.Timedelta(hours=6)).sum())
    print(f"  primary close: {own} of {len(done)} are the entry row itself (CLV 0 by construction); "
          f"{stale} were logged more than 6 hours before kickoff")
    secondary(done, "bets")
    # The decision (amendment 3, section 4): after 40 signals or the end of the 2026 regular season,
    # whichever is later, on the signals that kicked off by then. Later signals never enter it.
    by_kick = done.sort_values("start_utc")
    horizon = max(by_kick.start_utc.iloc[ENOUGH - 1], REG_END_2026) if len(done) >= ENOUGH else None
    pending = bets[bets.total.isna() & (bets.start_utc > NOW - PENDING)]      # kicked off, not yet scored
    if horizon is not None and not (pending.start_utc <= horizon).any() and NOW > horizon:
        dec = by_kick[by_kick.start_utc <= horizon]
        m, lo, hi, n = mean_ci(dec.clv_pts)
        print(f"  decision (Rule B: after 40 signals or the 2026 regular season, whichever is later), FINAL: "
              f"{'KEEP' if (m > 0 and lo > 0) else 'DO NOT KEEP'}, on the {len(dec)} signals that kicked off by "
              f"{horizon:%Y-%m-%d}: mean CLV {m:+.2f} (95% CI {lo:+.2f} to {hi:+.2f}, n={n})")
    elif NOW >= TEST_END:
        print(f"  decision (Rule B), FINAL: INCONCLUSIVE. The test ended with {len(done)} settled signals, "
              f"fewer than {ENOUGH}.")
    else:
        interim("Rule B", "after 40 signals or the 2026 regular season, whichever is later",
                {"mean CLV > 0": m > 0, "95% interval above zero": lo > 0,
                 f"{ENOUGH} settled signals": len(done) >= ENOUGH})
    print(done[["game_id", "kick_et", "away_team", "home_team", "line_src", "mkt_total", "mkt_under", "close_total",
                "total", "clv_pts", "profit"]].to_string(index=False))
    print("  by price source:", done.line_src.value_counts().to_dict())


# ---------------------------------------------------------------- Rule HT (amendment 1)
ht = last[(last.start_utc >= HT_FIRST_KICK)] if "rule_ht" in last else last.iloc[0:0]
ht = ht[ht.rule_ht == "SIGNAL"].merge(s[["game_id", "total"]], on="game_id", how="left") if len(ht) else ht
ht_done = ht[ht.total.notna()].copy() if len(ht) else ht
print(f"\nRULE_HT: {len(ht)} signals at the last quote before kickoff, {len(ht_done)} settled")
if len(ht_done):
    win, push = ht_done.total < ht_done.mkt_total, ht_done.total == ht_done.mkt_total
    ht_done["profit"] = np.where(push, 0, np.where(win, american_to_profit(ht_done.mkt_under), -1.0))
    w, n = int(win.sum()), int((~push).sum())
    each = np.asarray(1 / (1 + american_to_profit(ht_done.mkt_under[~push])), float)   # each bet's own break-even
    be = float(np.mean(each)) if n else np.nan
    p = tail_at_least(w, each) if n else np.nan
    roi = ht_done.profit.sum() / len(ht_done)
    print(f"  record {w}-{n - w}-{int(push.sum())} ({100 * w / max(n, 1):.1f}%), units {ht_done.profit.sum():+.2f}, "
          f"ROI {100 * roi:+.1f}% per bet placed; average break-even {100 * be:.1f}%, one-sided p {p:.3f} "
          f"(exact, against each bet's own break-even)")
    secondary(ht_done, "bets")
    # The decision (amendments 1 and 3): once, after the 2027 season's title game. "At or below
    # break-even" is read at the prices taken: the bets, together, won nothing.
    promote, drop = bool(p < 0.05 and roi > 0), bool(roi <= 0)
    if NOW >= TEST_END:
        print(f"  decision (Rule HT: once, after the 2027 season), FINAL: "
              f"{'PROMOTE' if promote else 'DROP' if drop else 'STAY ON PAPER'} "
              f"(promote needs one-sided p < 0.05 and ROI > 0; drop when ROI is zero or below)")
    else:
        interim("Rule HT", "once, after the 2027 season's title game (January 2028)",
                {"one-sided p < 0.05": p < 0.05, "ROI > 0": roi > 0})
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
print("\nVariants under forward test: 2 (RULE_B, RULE_HT).")
