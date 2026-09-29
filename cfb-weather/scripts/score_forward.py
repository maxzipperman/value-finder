"""Score the pre-registered CFB forward tests (STRATEGY.md, PREREGISTRATION.md):

  RULE_B   wind under: earliest pre-kickoff SIGNAL snapshot, graded at its entry line and price. CLV
           against the primary close (amendment 4): the last logged quote before kickoff that is later
           than the entry row; else the close captured by amendment 2; else none (counted, left out
           of the CLV). cfbfastR has no 2026 closing lines. Amendment 2 adds a secondary CLV against
           the captured close for every bet.
  RULE_HT  high-total under (amendment 1), from 2026 Week 6: each game's LAST logged quote before
           kickoff, if that quote is a SIGNAL. A quote is a posted total with a valid under price
           (amendment 4). Graded on win rate and ROI at that price; the promotion test is one-sided
           against the break-even of the prices taken, with pushes left out of it.

What counts (amendment 3): rows written under a registered rules version, logged before kickoff, for
games from Oct 1, 2026 through the 2027 season's title game (a game dated from Feb 1, 2028 never
counts, whatever its season label; amendment 4). Rows outside that are counted by reason, never
silently dropped; --list-excluded prints each one. ROI is units won per bet placed; a push counts
as a bet. A game is graded only once the schedule marks it completed.

Each bet is settled, pending or void (amendment 4). It is void when its game kicked off more than 24
hours from the kickoff on its entry row, or when the schedule still shows no score 30 days after that
kickoff; a void bet is listed by reason and not graded. It is pending while it has no score.

The decisions are computed here and labelled. A decision is FINAL once its horizon has passed and no
bet that kicked off by then is pending. The first FINAL is written to decisions.csv beside the ledger,
and every later run prints that record; if a fresh computation on the same horizon would now differ,
it prints both and the recorded one stands. Before that the script prints an interim read, which
shows the numbers and decides nothing.

    python scripts/score_forward.py [--ledger PATH] [--schedule PATH] [--list-excluded]
"""
import argparse
import hashlib
import json
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
ENOUGH = 40
MOVED = pd.Timedelta(hours=24)                        # amendment 4: void if it kicked off further than this ...
NO_RESULT = pd.Timedelta(days=30)                     # ... or had no score this long after the entry's kickoff
VOID_MOVED = "the game kicked off more than 24 hours from the kickoff on its entry row"
VOID_NO_RESULT = "the schedule shows no result 30 days after that kickoff"
RB_HORIZON = "after 40 signals or the 2026 regular season, whichever is later"
HT_HORIZON = "once, after the 2027 season's title game"
NOT_KEPT = ("NOT KEPT (no money goes on the rule; it stays on paper for 2027 only by a dated amendment before "
            "2027 Week 0)")
RECORD_COLS = ["rule", "horizon", "horizon_utc", "decided_utc", "n_bets", "verdict", "numbers", "ledger_rows_sha256"]

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
DECISIONS = path.parent / "decisions.csv"       # beside the ledger scored: a test ledger never writes to data/forward/
L = pd.read_csv(path)
text = path.read_text().splitlines()
# the rows as written, for each decision's fingerprint
HEADER, LINES = text[0], [ln for ln in text[1:] if ln.strip()]
if len(LINES) != len(L):        # a row spread over several lines: fingerprint the rows as read instead
    LINES = (pd.read_csv(path, dtype=str, keep_default_na=False).to_csv(index=False, lineterminator="\n")
             .splitlines()[1:])
L["_row"] = np.arange(len(L))
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
# the schedule's kickoff, to compare with the entry row's (amendment 4); a schedule without one can't show a move
kick = next((c for c in ("start_utc", "start_date") if c in S), None)
s["sched_kick"] = (pd.to_datetime(S[kick], utc=True, errors="coerce") if kick
                   else pd.Series(pd.NaT, index=s.index, dtype="datetime64[ns, UTC]"))
if "completed" in S:        # the feed scores a game that was never played 0-0: grade completed games only
    played = S.completed.astype(str).str.lower().isin(["true", "1", "1.0"])
    print(f"schedule rows with a score but not marked completed (not graded): "
          f"{int((~played & s.total.notna()).sum())}")
    s.loc[~played.values, "total"] = np.nan

# What counts. Every excluded row is counted by its first failing reason.
why = np.select([~L.rules_version.isin(REGISTERED_VERSIONS), L.start_utc.isna(), L.start_utc < FIRST_KICK,
                 ~L.season.isin(TEST_SEASONS) | (L.start_utc >= TEST_END), L.snapshot_utc >= L.start_utc],
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
    print(f"  decision ({name}): INTERIM read, decides nothing. {when}")
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


def is_price(odds):
    """Amendment 3: a price must be a price, at or beyond 100 either side of zero."""
    o = pd.to_numeric(pd.Series(odds), errors="coerce").to_numpy(float)
    return np.isfinite(o) & (np.abs(o) >= 100)


def settle(bets):
    """Amendment 4: void (moved more than a day, or no score 30 days on), pending (no score yet), or settled."""
    bets = bets.merge(s[["game_id", "total", "sched_kick"]], on="game_id", how="left")
    moved = (bets.sched_kick - bets.start_utc).abs() > MOVED
    stale = bets.total.isna() & (NOW >= bets.start_utc + NO_RESULT)
    void = np.select([moved, stale], [VOID_MOVED, VOID_NO_RESULT], "")
    return bets.assign(void=void, status=np.where(void != "", "void",
                                                  np.where(bets.total.notna(), "settled", "pending")))


def header(bets):
    void = bets[bets.status.eq("void")]
    print(f"{int(bets.status.eq('settled').sum())} settled, {int(bets.status.eq('pending').sum())} pending, "
          f"{len(void)} void (not graded)")
    for reason, v in void.groupby("void", sort=False):
        print(f"  void, {reason}: {len(v)} ({', '.join(v.game_id.astype(str))})")


def recorded(rule):
    """The decision already written down for this rule (amendment 4, section 3), or None."""
    if not DECISIONS.exists():
        return None
    d = pd.read_csv(DECISIONS, dtype=str, keep_default_na=False)
    d = d[d.rule.eq(rule)]
    return None if d.empty else d.iloc[0]


def write_down(rule, horizon, horizon_utc, verdict, nums, rows):
    """Append a decision the first time it is FINAL, with a sha256 of the ledger's header and the entry
    rows that entered it, exactly as written."""
    lines = [HEADER] + [LINES[i] for i in sorted(rows)]
    rec = dict(rule=rule, horizon=horizon, horizon_utc=f"{horizon_utc:%Y-%m-%dT%H:%M:%SZ}",
               decided_utc=f"{NOW:%Y-%m-%dT%H:%M:%SZ}", n_bets=nums["n_bets"], verdict=verdict,
               numbers=json.dumps(nums),
               ledger_rows_sha256=hashlib.sha256(("\n".join(lines) + "\n").encode()).hexdigest())
    pd.DataFrame([rec], columns=RECORD_COLS).to_csv(DECISIONS, mode="a", header=not DECISIONS.exists(), index=False)
    print(f"    recorded in decisions.csv on {rec['decided_utc']}, horizon {rec['horizon_utc']}; "
          f"ledger rows sha256 {rec['ledger_rows_sha256'][:16]}")


def reprint(rec, show, fresh_verdict, fresh_nums, n_fresh):
    """A decision already recorded: print it, and a fresh computation beside it when that now differs."""
    show(rec.verdict, json.loads(rec.numbers))
    print(f"    recorded in decisions.csv on {rec.decided_utc}, horizon {rec.horizon_utc}; "
          f"ledger rows sha256 {rec.ledger_rows_sha256[:16]}")
    if fresh_verdict != rec.verdict or json.dumps(fresh_nums) != json.dumps(json.loads(rec.numbers)):
        print(f"    a fresh computation on the same horizon now gives: {fresh_verdict}, on {n_fresh} bets:")
        show(fresh_verdict, fresh_nums, fresh=True)
        print("    The recorded decision stands.")


def f(v):
    return None if pd.isna(v) else float(v)


last = L.dropna(subset=["mkt_total"])
quotes = last[is_price(last.mkt_under)]                             # amendment 4: a total with a valid under price
last = quotes.sort_values("snapshot_utc").drop_duplicates("game_id", keep="last")
# Amendment 2: the close captured 2-20 minutes before kickoff (scripts/capture_close.py). Secondary and
# descriptive, and Rule B's primary close when no later quote was logged (amendment 4).
cap_path = path.parent / "closes.csv"
cap = (pd.read_csv(cap_path).dropna(subset=["close_total"]).drop_duplicates("game_id", keep="last")
       if cap_path.exists() else pd.DataFrame(columns=["game_id", "close_total", "line_src"]))
cap_src = pd.Series(cap["line_src"].fillna("").astype(str).values if "line_src" in cap else "",
                    index=pd.to_numeric(cap.game_id), dtype=str)
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
# Amendment 4: the primary close is the last quote logged after the entry row, else the captured close
later = quotes.merge(bets[["game_id", "snapshot_utc"]].rename(columns={"snapshot_utc": "entry_utc"}), on="game_id")
later = later[later.snapshot_utc > later.entry_utc].sort_values("snapshot_utc").drop_duplicates("game_id", keep="last")
bets = bets.merge(later[["game_id", "mkt_total", "snapshot_utc", "line_src"]].rename(
    columns={"mkt_total": "close_total", "snapshot_utc": "close_utc", "line_src": "close_src"}),
    on="game_id", how="left")
use_cap = bets.close_total.isna() & bets.game_id.map(cap).notna()
bets["close_from"] = np.where(bets.close_total.notna(), "later quote", np.where(use_cap, "captured close", "none"))
bets.loc[use_cap, "close_total"] = bets.game_id.map(cap)[use_cap]
bets["close_src"] = np.where(use_cap, "captured close (" + bets.game_id.map(cap_src).fillna("").astype(str) + ")",
                             bets.close_src.fillna("none").astype(str))
bets = settle(bets)
done = bets[bets.status.eq("settled")].copy()
print(f"\nRULE_B: {len(bets)} signals, ", end="")
header(bets)
if len(done):
    win, push = done.total < done.mkt_total, done.total == done.mkt_total
    done["profit"] = np.where(push, 0, np.where(win, american_to_profit(done.mkt_under), -1.0))
    done["clv_pts"] = done.mkt_total - done.close_total
    m, lo, hi, n = mean_ci(done.clv_pts)
    print(f"  record {int(win.sum())}-{int((~win & ~push).sum())}-{int(push.sum())}, units {done.profit.sum():+.2f} "
          f"(ROI {100 * done.profit.sum() / len(done):+.1f}% per bet placed); "
          f"mean CLV {m:+.2f} (95% CI {lo:+.2f} to {hi:+.2f}; {n} of {len(done)} bets have a primary close)")
    src = done.close_from.value_counts()
    stale = int(((done.start_utc - done.close_utc) > pd.Timedelta(hours=6)).sum())
    print(f"  primary close: {src.get('later quote', 0)} from a later logged quote, {src.get('captured close', 0)} "
          f"from the captured close, {src.get('none', 0)} with none (counted, left out of the CLV); {stale} of the "
          f"later quotes were logged more than 6 hours before kickoff")
    secondary(done, "bets")

    # The decision (amendment 3, section 4, and amendment 4): after 40 signals or the end of the 2026
    # regular season, whichever is later, on the signals that kicked off by then. Later signals never enter it.
    def rb_numbers(dec):
        m, lo, hi, n = mean_ci(dec.clv_pts)
        return ("KEEP" if (m > 0 and lo > 0) else NOT_KEPT), dict(n_bets=len(dec), mean_clv=f(m), ci_low=f(lo),
                                                                 ci_high=f(hi), n_clv=int(n))

    def rb_show(verdict, nums, fresh=False):
        if "horizon" not in nums:              # the test ended with fewer than 40
            print(f"  decision (Rule B), FINAL: {verdict}. The test ended with {nums['n_bets']} settled signals, "
                  f"fewer than {ENOUGH}.")
            return
        m, lo, hi = (np.nan if nums[k] is None else nums[k] for k in ("mean_clv", "ci_low", "ci_high"))
        lead = ("    " if fresh else
                "  decision (Rule B: after 40 signals or the 2026 regular season, whichever is later), FINAL: ")
        print(f"{lead}{verdict}, on the {nums['n_bets']} signals that kicked off by {nums['horizon']}: "
              f"mean CLV {m:+.2f} (95% CI {lo:+.2f} to {hi:+.2f}, n={nums['n_clv']})")

    def label(h):
        return ("2026-12-12, the end of the regular season (Army-Navy)" if h == REG_END_2026
                else f"{h:%Y-%m-%d %H:%M} UTC, the 40th signal's kickoff")

    by_kick = done.sort_values("start_utc")
    pending = bets[bets.status.eq("pending")]
    horizon = max(by_kick.start_utc.iloc[ENOUGH - 1], REG_END_2026) if len(done) >= ENOUGH else None
    rec = recorded("Rule B")
    if rec is not None:
        h = pd.Timestamp(rec.horizon_utc)
        dec = by_kick[by_kick.start_utc <= h]
        verdict, nums = rb_numbers(dec)
        nums = (nums | {"horizon": label(h)}) if "horizon" in json.loads(rec.numbers) else {"n_bets": len(dec)}
        verdict = verdict if "horizon" in nums else "INCONCLUSIVE"
        reprint(rec, rb_show, verdict, nums, len(dec))
    elif horizon is not None and NOW > horizon and not (pending.start_utc <= horizon).any():
        dec = by_kick[by_kick.start_utc <= horizon]
        verdict, nums = rb_numbers(dec)
        nums["horizon"] = label(horizon)
        rb_show(verdict, nums)
        write_down("Rule B", RB_HORIZON, horizon, verdict, nums, dec._row)
    elif horizon is None and NOW >= TEST_END and not (pending.start_utc < TEST_END).any():
        rb_show("INCONCLUSIVE", {"n_bets": len(done)})
        write_down("Rule B", RB_HORIZON, TEST_END, "INCONCLUSIVE", {"n_bets": len(done)}, done._row)
    else:
        waiting = int((pending.start_utc <= horizon).sum()) if horizon is not None else len(pending)
        when = (f"Its horizon has passed: {label(horizon)}. The decision waits for {waiting} pending "
                f"signal{'s' if waiting != 1 else ''}." if horizon is not None and NOW > horizon
                else "The decision comes after 40 signals or the 2026 regular season, whichever is later.")
        interim("Rule B", when, {"mean CLV > 0": m > 0, "95% interval above zero": lo > 0,
                                 f"{ENOUGH} settled signals": len(done) >= ENOUGH})
    print(done[["game_id", "kick_et", "away_team", "home_team", "line_src", "mkt_total", "mkt_under", "close_src",
                "close_total", "total", "clv_pts", "profit"]].to_string(index=False))
    print("  by price source:", done.line_src.value_counts().to_dict())
    print("  close from:", {k: int(v) for k, v in done.close_src.value_counts(sort=False).items()})


# ---------------------------------------------------------------- Rule HT (amendment 1)
ht = last[(last.start_utc >= HT_FIRST_KICK)] if "rule_ht" in last else last.iloc[0:0]
ht = settle(ht[ht.rule_ht == "SIGNAL"]) if len(ht) else ht.assign(status="", void="", total=np.nan)
ht_done = ht[ht.status.eq("settled")].copy()
print(f"\nRULE_HT: {len(ht)} signals at the last quote before kickoff, ", end="")
header(ht)
if len(ht_done):
    win, push = ht_done.total < ht_done.mkt_total, ht_done.total == ht_done.mkt_total
    ht_done["profit"] = np.where(push, 0, np.where(win, american_to_profit(ht_done.mkt_under), -1.0))
    ht_done["result"] = np.where(push, "P", np.where(win, "W", "L"))

    def ht_numbers(d):
        w, n = int(d.result.eq("W").sum()), int(d.result.ne("P").sum())
        each = np.asarray(1 / (1 + american_to_profit(d.mkt_under[d.result.ne("P")])), float)   # own break-evens
        units = float(d.profit.sum())
        nums = dict(n_bets=len(d), wins=w, losses=n - w, pushes=int(d.result.eq("P").sum()), units=units,
                    roi=units / len(d), avg_break_even=f(np.mean(each)) if n else None,
                    p_one_sided=tail_at_least(w, each) if n else None)
        promote = bool(nums["p_one_sided"] is not None and nums["p_one_sided"] < 0.05 and nums["roi"] > 0)
        return ("PROMOTE" if promote else "DROP" if nums["roi"] <= 0 else "STAY ON PAPER"), nums

    def ht_show(verdict, nums, fresh=False):
        p = np.nan if nums["p_one_sided"] is None else nums["p_one_sided"]
        if not fresh:
            print(f"  decision (Rule HT: once, after the 2027 season), FINAL: {verdict} "
                  f"(promote needs one-sided p < 0.05 and ROI > 0; drop when ROI is zero or below)")
        print(f"    on {nums['n_bets']} bets: record {nums['wins']}-{nums['losses']}-{nums['pushes']}, units "
              f"{nums['units']:+.2f}, ROI {100 * nums['roi']:+.1f}%, one-sided p {p:.3f}")

    verdict, nums = ht_numbers(ht_done)
    be = np.nan if nums["avg_break_even"] is None else nums["avg_break_even"]
    p = np.nan if nums["p_one_sided"] is None else nums["p_one_sided"]
    w, n = nums["wins"], nums["wins"] + nums["losses"]
    print(f"  record {w}-{n - w}-{nums['pushes']} ({100 * w / max(n, 1):.1f}%), units {nums['units']:+.2f}, "
          f"ROI {100 * nums['roi']:+.1f}% per bet placed; average break-even {100 * be:.1f}%, one-sided p {p:.3f} "
          f"(exact, against each bet's own break-even; pushes are left out of the exact test and count in ROI)")
    secondary(ht_done, "bets")
    # The decision (amendments 1, 3 and 4): once, after the 2027 season's title game. "At or below
    # break-even" is read at the prices taken: the bets, together, won nothing.
    rec = recorded("Rule HT")
    ht_pending = ht[ht.status.eq("pending")]
    if rec is not None:
        verdict, nums = ht_numbers(ht_done[ht_done.start_utc < pd.Timestamp(rec.horizon_utc)])
        reprint(rec, ht_show, verdict, nums, nums["n_bets"])
    elif NOW >= TEST_END and not (ht_pending.start_utc < TEST_END).any():
        ht_show(verdict, nums)
        write_down("Rule HT", HT_HORIZON, TEST_END, verdict, nums, ht_done._row)
    else:
        waiting = int((ht_pending.start_utc < TEST_END).sum())
        when = (f"The title game has passed; the decision waits for {waiting} pending signal"
                f"{'s' if waiting != 1 else ''}." if NOW >= TEST_END else
                "The decision comes once, after the 2027 season's title game (January 2028).")
        interim("Rule HT", when, {"one-sided p < 0.05": p < 0.05, "ROI > 0": nums["roi"] > 0})
    print(ht_done[["game_id", "kick_et", "away_team", "home_team", "line_src", "mkt_total", "mkt_under",
                   "ht_threshold", "total", "profit"]].to_string(index=False))
    # Amendment 3, section 2, and amendment 4: reported by price source. The decision uses every bet.
    by = [f"{src} {len(d)} ({int(d.result.eq('W').sum())}-{int(d.result.eq('L').sum())}-{int(d.result.eq('P').sum())}, "
          f"units {d.profit.sum():+.2f})" for src, d in ht_done.groupby("line_src", sort=False)]
    print("  by price source: " + "; ".join(by))

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
