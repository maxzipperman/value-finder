"""Score the pre-registered forward tests (PREREGISTRATION.md), one table per rule:

  MODEL_LEAN          model P(under) >= 55% / <= 45%. The entry is the earliest snapshot at least 24
                      hours before kickoff that has both a lean and a posted total (amendment 6).
  RULE_B              early wind under, priced at Pinnacle: the registered test. The entry is the
                      earliest pre-kickoff snapshot whose status was "SIGNAL". The 24-hour rule is the
                      lean's only: Rule B's window is about 11 to 82 hours (amendment 5, section 3).
  RULE_B (secondary)  the same gates at the backup price (the consensus line, when Pinnacle had no
                      quote). Reported separately; not part of the keep/drop decision (amendment 5).

What counts (amendments 2, 4 and 5): rows written under a registered rules version, logged before
kickoff, for games from Week 5 (Oct 8, 2026) through the 2027 season. Rows outside that are counted
by reason, never silently dropped; --list-excluded prints each one.

Each bet is settled, pending or void (amendment 6). It is void when its game kicked off more than 24
hours from the kickoff on its entry row, or when the schedule still shows no result 30 days after
that kickoff; a void bet is listed by reason and not graded. It is pending while it has no result.

The decisions (amendment 5, section 4, and amendment 6) are computed here and labelled. Horizons are
dates: "after Week 18" is after the last regular-season kickoff in the schedule. A decision is FINAL
once its horizon has passed and no bet that kicked off by then is pending. The first FINAL is written
down, and every later run prints that record; if a fresh computation on the same horizon would now
differ, it prints both and the recorded one stands. Before that the script prints an interim read,
which shows the numbers and decides nothing.

Who writes a decision down (amendment 6, section 3): a run on the live ledger (data/forward/ledger.csv),
on the real clock, reading the default schedule refreshed in the last 2 days, writes
data/forward/decisions.csv. A run with --now is a preview and records nothing. A run on another ledger
kept in data/forward/ (the rewrite's backup copy) neither reads nor writes a record. A copy of this
scorer in another folder (a worker's worktree) reads the live record but never writes it. A test
ledger kept anywhere else writes decisions.csv beside itself.

Each bet is graded at its ENTRY line and ENTRY price (profit in units, pushes return the stake), with
closing-line value against the final nflverse total. Amendment 3 adds a secondary CLV against
Pinnacle's total captured just before kickoff (data/forward/closes.csv). ROI is units won per bet
placed; a push counts as a bet. Wind triggers that never became a signal (no price, price too high,
outside the horizon) are counted, so coverage gaps can't quietly select winners.

    python scripts/fetch_data.py --skip-weather   # refresh schedule/lines/results
    python scripts/score_forward.py [--list-excluded]
"""
import argparse
import hashlib
import json
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
LEAN_LEAD = pd.Timedelta(hours=24)                    # the model lean's entry is at least 24 hours out
MOVED = pd.Timedelta(hours=24)                        # amendment 6: void if it kicked off further than this ...
NO_RESULT = pd.Timedelta(days=30)                     # ... or had no result this long after the entry's kickoff
VOID_MOVED = "the game kicked off more than 24 hours from the kickoff on its entry row"
VOID_NO_RESULT = "the schedule shows no result 30 days after that kickoff"
H26, H27 = "after Week 18 of 2026", "after the 2027 regular season"     # the decision horizons, by name
RECORD_COLS = ["rule", "horizon", "horizon_utc", "decided_utc", "n_bets", "verdict", "numbers", "ledger_rows_sha256"]
LIVE = ROOT / "data" / "forward"                      # the live folder: the alert jobs' ledger and its record
FRESH = pd.Timedelta(days=2)                          # a decision is recorded only from a schedule this fresh

ap = argparse.ArgumentParser()
ap.add_argument("--ledger", default=str(LIVE / "ledger.csv"))
ap.add_argument("--games", default=str(RAW / "games.csv"))
ap.add_argument("--list-excluded", action="store_true", help="print every excluded row with its reason")
ap.add_argument("--now", help="score as of this UTC time: a preview for tests and rehearsals, which records no "
                              "decision; default: the clock")
ap.add_argument("--test-record", action="store_true",
                help="tests only: with --now, record final decisions beside a test ledger as if made at --now "
                     "(refused for any ledger in data/forward/)")
args = ap.parse_args()
CLOCK = pd.Timestamp.now(tz="UTC")
NOW = pd.Timestamp(args.now, tz="UTC") if args.now else CLOCK
ledger = Path(args.ledger)
if not ledger.exists():
    sys.exit("no ledger yet: run scripts/this_week.py or scripts/alerts.py first")
# Amendment 6, section 3: who writes a decision down, and where. A ledger inside a data/forward/ folder
# (this checkout's or another's) is a live ledger or a copy of one, never a test ledger.
FWD = next((q for q in ledger.resolve().parents if q.name == "forward" and q.parent.name == "data"), None)
IS_LIVE = ledger.resolve() == (LIVE / "ledger.csv").resolve()           # this checkout's live ledger
if args.test_record and (not args.now or FWD is not None):
    sys.exit("--test-record needs --now and a test ledger outside data/forward/")
if FWD is None:
    DECISIONS = ledger.parent / "decisions.csv"                         # a test ledger's own record
elif ledger.name == "ledger.csv" and ledger.resolve().parent == FWD:
    DECISIONS = FWD / "decisions.csv"                                   # a live ledger's record
else:
    DECISIONS = None                                                    # a copy, such as the rewrite's backup
schedule_file = Path(args.games)
refreshed = pd.Timestamp(schedule_file.stat().st_mtime, unit="s", tz="UTC")
if DECISIONS is None:
    NOT_RECORDED = "this ledger is kept in data/forward/ but is not the live ledger, so no record is read or written"
elif not IS_LIVE and FWD is not None:
    NOT_RECORDED = "this is another folder's live ledger, and only the scorer in that folder writes its record"
elif args.now and not args.test_record:
    NOT_RECORDED = "a run with --now is a preview"
elif IS_LIVE and schedule_file.resolve() != (RAW / "games.csv").resolve():
    NOT_RECORDED = "the live record is written only from the default schedule, data/raw/games.csv"
elif CLOCK - refreshed > FRESH:
    NOT_RECORDED = (f"the schedule was last refreshed {refreshed:%Y-%m-%d %H:%M} UTC, more than 2 days ago; refresh "
                    "it (every alert run does, or scripts/fetch_data.py --skip-weather) and run the scorer again")
else:
    NOT_RECORDED = ""


def eastern(day, time):
    """Kickoff in UTC from an Eastern date and time (nflverse's convention); NaT when either is blank."""
    day, time = pd.Series(day), pd.Series(time)
    ok = day.notna() & time.notna() & day.astype(str).str.strip().ne("") & time.astype(str).str.strip().ne("")
    t = pd.to_datetime(day.astype(str).where(ok) + " " + time.astype(str).where(ok), format="mixed", errors="coerce")
    return t.dt.tz_localize("America/New_York", ambiguous="NaT", nonexistent="NaT").dt.tz_convert("UTC")


L = pd.read_csv(ledger)
text = ledger.read_text().splitlines()
# the rows as written, for each decision's fingerprint
HEADER, LINES = text[0], [ln for ln in text[1:] if ln.strip()]
if len(LINES) != len(L):        # a row spread over several lines: fingerprint the rows as read instead
    LINES = (pd.read_csv(ledger, dtype=str, keep_default_na=False).to_csv(index=False, lineterminator="\n")
             .splitlines()[1:])
L["_row"] = np.arange(len(L))
L["snapshot_utc"] = pd.to_datetime(L.snapshot_utc, utc=True)
for c in ("lean", "rule_b", "rules_version", "line_src"):
    L[c] = L[c].fillna("").astype(str) if c in L else ""
# the kickoff the entry row was logged against (amendment 6, reading 1)
L["row_kick"] = (eastern(L.gameday, L.gametime) if {"gameday", "gametime"} <= set(L)
                 else pd.Series(pd.NaT, index=L.index, dtype="datetime64[ns, UTC]"))
G = pd.read_csv(args.games)
G["kick_utc"] = eastern(G.gameday, G.gametime)
if "season" not in G:      # a season runs from September into February
    d = pd.to_datetime(G.gameday)
    G["season"] = np.where(d.dt.month >= 8, d.dt.year, d.dt.year - 1)
for c in ("week", "game_type"):
    if c not in G:
        G[c] = np.nan
g = G[["game_id", "total", "total_line", "kick_utc", "result", "season", "week", "game_type"]].rename(
    columns={"total_line": "close_total"}).assign(in_schedule=True)
L = L.merge(g, on="game_id", how="left")
L["in_schedule"] = L.in_schedule.eq(True)
# Amendment 3: the Pinnacle close captured just before kickoff (scripts/capture_close.py), secondary only
closes = ledger.parent / "closes.csv"
cap = pd.read_csv(closes) if closes.exists() else pd.DataFrame(columns=["game_id", "book", "close_total"])
cap = (cap[cap.book.eq("pinnacle")].dropna(subset=["close_total"]).drop_duplicates("game_id", keep="last")
       [["game_id", "close_total"]].rename(columns={"close_total": "cap_close"}))
L = L.merge(cap, on="game_id", how="left")

# What counts. Every excluded row is counted by its first failing reason.
why = np.select([~L.rules_version.isin(REGISTERED_VERSIONS), ~L.in_schedule, L.kick_utc.isna(),
                 L.kick_utc < FIRST_KICK, ~L.season.isin(TEST_SEASONS), L.snapshot_utc >= L.kick_utc],
                ["unregistered rules version", "game not in the schedule", "no kickoff time in the schedule",
                 "before Week 5 (Oct 8, 2026)", "after the 2027 season", "logged at or after kickoff"], "")
print(f"ledger rows: {len(L)}; in the test: {int((why == '').sum())}")
for reason, n in pd.Series(why[why != ""]).value_counts().items():
    print(f"  excluded, {reason}: {n}")
if args.list_excluded and (why != "").any():
    print(L.assign(excluded=why)[why != ""][["snapshot_utc", "game_id", "rules_version", "lean", "rule_b", "excluded"]]
          .to_string(index=False))
L = L[why == ""]


def regular_season(season):
    return G[(G.season == season) & (G.game_type.astype(str) == "REG")]


def horizon_of(season):
    """Amendment 6, reading 4: "after Week 18" is after the season's last regular-season kickoff in the
    schedule. None while the schedule doesn't have that season."""
    k = regular_season(season).kick_utc.max()
    return None if pd.isna(k) else k


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
    bets = bets.assign(win=win, push=push, profit=profit, clv_pts=clv, clv_cap=clv_cap, priced=has_price,
                       beat_close=beat, tie_close=tie)
    # Amendment 6, readings 1 and 2: void (moved or never scored), pending (no result yet), or settled
    moved = (bets.kick_utc - bets.row_kick).abs() > MOVED
    stale = bets.result.isna() & (NOW >= bets.row_kick.fillna(bets.kick_utc) + NO_RESULT)
    void = np.select([moved, stale], [VOID_MOVED, VOID_NO_RESULT], "")
    return bets.assign(void=void, status=np.where(void != "", "void",
                                                  np.where(bets.result.notna(), "settled", "pending")))


def mean_ci(x):
    x = pd.Series(x).dropna()
    if not len(x):
        return np.nan, np.nan, np.nan, 0
    se = x.std(ddof=1) / np.sqrt(len(x)) if len(x) > 1 else np.nan
    return x.mean(), x.mean() - 1.96 * se, x.mean() + 1.96 * se, len(x)


def report(name, bets):
    settled = bets[bets.status.eq("settled")]
    n_pend, void = int(bets.status.eq("pending").sum()), bets[bets.status.eq("void")]
    print(f"\n{name}: {len(bets)} signals, {len(settled)} settled, {n_pend} pending, {len(void)} void (not graded)")
    for reason, v in void.groupby("void", sort=False):
        print(f"  void, {reason}: {len(v)} ({', '.join(v.game_id.astype(str))})")
    if settled.empty:
        return settled
    w, p = int(settled.win.sum()), int(settled.push.sum())
    m, lo, hi, _ = mean_ci(settled.clv_pts)
    print(f"  record at entry line {w}-{len(settled) - w - p}-{p}   units {settled.profit.sum():+.2f} "
          f"(ROI {100 * settled.profit.sum() / len(settled):+.1f}% per bet placed; "
          f"{int((~settled.priced).sum())} graded at an assumed -110)")
    print(f"  mean CLV {m:+.2f} pts  (95% CI {lo:+.2f} to {hi:+.2f}; {int(settled.close_total.notna().sum())} of "
          f"{len(settled)} bets have a primary close)")
    cm, clo, chi, cn = mean_ci(settled.clv_cap)
    if cn:
        print(f"  secondary (amendment 3): mean CLV vs captured Pinnacle close {cm:+.2f} pts "
              f"(95% CI {clo:+.2f} to {chi:+.2f}); {len(settled) - cn} of {len(settled)} without a captured close")
    else:
        print(f"  secondary (amendment 3): no captured closes for these {len(settled)} bets")
    print(settled[["game_id", "side", "line_src", "total_line", "close_total", "total", "clv_pts", "profit"]]
          .to_string(index=False))
    return settled


# ---------------------------------------------------------------- the decisions
def assess(bets, split, split_name, final_label, enough=True):
    """The registered keep/drop test on `bets`, as numbers and a verdict. `split` labels each bet's half
    (or season); CLV must be positive in every part. Keep and drop both met is a DROP."""
    m, lo, hi, n = mean_ci(bets.clv_pts)
    graded = bets[bets.close_total.notna() & ~bets.tie_close]     # no close, or a tie with it: left out
    rate = graded.beat_close.mean() if len(graded) else np.nan
    parts = bets.assign(part=split).groupby("part").clv_pts.mean()
    f = lambda v: None if pd.isna(v) else float(v)                # noqa: E731
    nums = dict(n_bets=len(bets), mean_clv=f(m), ci_low=f(lo), ci_high=f(hi), n_clv=int(n), win_rate_vs_close=f(rate),
                beat_close=int(graded.beat_close.sum()), with_close=len(graded), ties=int(bets.tie_close.sum()),
                split=split_name, by_part={str(k): float(v) for k, v in parts.items()})
    keep, drop = criteria(nums)
    verdict = (final_label[1] if not enough else "DROP" if drop else
               "KEEP" if all(keep.values()) else final_label[0])
    return verdict, nums


def criteria(nums):
    """The keep tests and the drop test, from a decision's numbers."""
    m, lo, hi, rate = (np.nan if nums[k] is None else nums[k] for k in ("mean_clv", "ci_low", "ci_high",
                                                                         "win_rate_vs_close"))
    parts = nums["by_part"]
    plural = {"half": "halves", "season": "seasons"}[nums["split"]]
    keep = {"mean CLV > 0": m > 0, "95% interval above zero": lo > 0,
            f"win rate vs the close at least {100 * BREAK_EVEN:.1f}%": rate >= BREAK_EVEN,
            f"mean CLV positive in both {plural}": len(parts) >= 2 and all(v > 0 for v in parts.values())}
    return keep, bool(m <= 0 or hi < 0.25)


def show(nums):
    m, lo, hi, n, rate = (np.nan if nums[k] is None else nums[k]
                          for k in ("mean_clv", "ci_low", "ci_high", "n_clv", "win_rate_vs_close"))
    keep, drop = criteria(nums)
    ci = f"95% CI {lo:+.2f} to {hi:+.2f}" if n > 1 else "no interval on one bet"
    print(f"    mean CLV {m:+.2f} ({ci}, n={n}); win rate vs the close {100 * rate:.1f}% "
          f"({nums['beat_close']} of {nums['with_close']} with a close, {nums['ties']} ties), ties left out; "
          f"mean CLV by {nums['split']}: { {k: round(v, 2) for k, v in nums['by_part'].items()} }")
    print("    keep needs: " + "; ".join(f"{k} ({'met' if bool(v) else 'not met'})" for k, v in keep.items())
          + f". Drop if mean CLV <= 0 or the interval's upper bound is below +0.25 ({'met' if drop else 'not met'}).")


def recorded(rule, horizon):
    """The decision already written down for this rule and horizon (amendment 6, reading 3), or None."""
    if DECISIONS is None or not DECISIONS.exists():
        return None
    d = pd.read_csv(DECISIONS, dtype=str, keep_default_na=False)
    d = d[d.rule.eq(rule) & d.horizon.eq(horizon)]
    return None if d.empty else d.iloc[0]


def write_down(rule, horizon, horizon_utc, verdict, nums, rows):
    """Append a decision the first time it is FINAL, with a sha256 of the ledger's header and the entry
    rows that entered it, exactly as written (the closes come from the schedule). A run that may not
    record (a --now preview, a stale schedule, a copy of the ledger in data/forward/) says why instead."""
    if NOT_RECORDED:
        print(f"    not recorded: {NOT_RECORDED}.")
        return
    lines = [HEADER] + [LINES[i] for i in sorted(rows)]
    rec = dict(rule=rule, horizon=horizon, horizon_utc=f"{horizon_utc:%Y-%m-%dT%H:%M:%SZ}",
               decided_utc=f"{NOW:%Y-%m-%dT%H:%M:%SZ}", n_bets=nums["n_bets"], verdict=verdict,
               numbers=json.dumps(nums),
               ledger_rows_sha256=hashlib.sha256(("\n".join(lines) + "\n").encode()).hexdigest())
    pd.DataFrame([rec], columns=RECORD_COLS).to_csv(DECISIONS, mode="a", header=not DECISIONS.exists(), index=False)
    print(f"    recorded in decisions.csv on {rec['decided_utc']}, horizon {rec['horizon_utc']}; "
          f"ledger rows sha256 {rec['ledger_rows_sha256'][:16]}")


def decision(rule, horizon, name, h_utc, bets_by, split_by, split_name, pending, when, labels, enough=lambda b: True):
    """One registered decision. Prints the recorded one if it exists (and a fresh computation on the same
    horizon beside it when that now differs); otherwise FINAL, written down by a run that may record, once
    the horizon has passed and no bet that kicked off by then is pending; otherwise an interim read.
    Returns the verdict or None."""
    rec = recorded(rule, horizon)
    if rec is not None:
        h = pd.Timestamp(rec.horizon_utc)
        bets = bets_by(h)
        fresh, nums = assess(bets, split_by(bets), split_name, labels, enough(bets))
        print(f"  decision ({name}), FINAL: {rec.verdict}")
        show(json.loads(rec.numbers))
        print(f"    recorded in decisions.csv on {rec.decided_utc}, horizon {rec.horizon_utc}; "
              f"ledger rows sha256 {rec.ledger_rows_sha256[:16]}")
        if not len(bets):
            print("    a fresh computation on the same horizon now has no settled bets. The recorded decision stands.")
        elif fresh != rec.verdict or json.dumps(nums) != json.dumps(json.loads(rec.numbers)):
            print(f"    a fresh computation on the same horizon now gives: {fresh}, on {len(bets)} bets:")
            show(nums)
            print("    The recorded decision stands.")
        return rec.verdict
    bets = bets_by(h_utc)
    verdict, nums = assess(bets, split_by(bets), split_name, labels, enough(bets))
    waiting = 0 if h_utc is None else int((pending.kick_utc <= h_utc).sum())
    if h_utc is not None and NOW > h_utc and not waiting:
        print(f"  decision ({name}), FINAL: {verdict}")
        show(nums)
        write_down(rule, horizon, h_utc, verdict, nums, bets._row)
        return verdict
    print(f"  decision ({name}): INTERIM read, decides nothing. {when(waiting)}")
    show(nums)
    return None


def halves(df):
    return np.where(pd.to_numeric(df.week, errors="coerce") <= 11, "Weeks 5-11", "Weeks 12-18")


def horizon_decision(what, unit, bets):
    """Amendment 5, section 4, and amendment 6. With 40 in the 2026 regular season, the decision is made
    after Week 18 of 2026 on those bets, split by half; a keep or a drop then is the decision. Otherwise,
    or when 2026 is inconclusive, it is made once, after the 2027 regular season, on every bet that kicked
    off by then, split by season. Bets after a horizon never enter it. A decision recorded on the pooled
    horizon with none recorded for 2026 is the decision: a 2026 result that lands later can't add one."""
    done, pending = bets[bets.status.eq("settled")], bets[bets.status.eq("pending")]
    h26, h27 = horizon_of(2026), horizon_of(2027)
    reg26 = done[(done.season == 2026) & done.game_type.astype(str).eq("REG")]
    # 2026 bets still waiting for a result can bring 2026 to 40: its decision then waits for them
    wait26 = pending[(pending.season == 2026) & pending.game_type.astype(str).eq("REG")]

    def ahead(label, h, waiting):
        if h is not None and NOW > h:
            return f"{label} is over; the decision waits for {waiting} pending {unit if waiting != 1 else unit[:-1]}."
        return f"The decision comes {label.replace('Week', 'after Week', 1)}" + (
            f" (the last regular-season kickoff, {h:%Y-%m-%d %H:%M} UTC)." if h is not None else ".")

    rule = what
    if recorded(rule, H27) is not None and recorded(rule, H26) is None:
        name = f"{what}: once, after the 2027 regular season, both seasons pooled"
    elif recorded(rule, H26) is not None or len(reg26) + len(wait26) >= ENOUGH:
        verdict = decision(rule, H26, f"{what}: 40 {unit} in 2026, decided after Week 18 of 2026", h26,
                           lambda h: reg26 if h is None else reg26[reg26.kick_utc <= h], halves, "half", pending,
                           lambda k: ahead("Week 18 of 2026", h26, k),
                           ("INCONCLUSIVE (carried into 2027 unchanged)", None))
        if verdict is None or verdict in ("KEEP", "DROP"):
            if verdict:
                print(f"    Later {unit} are logged and reported, and decide nothing (amendment 6).")
            return
        name = f"{what}: inconclusive in 2026, decided once more after the 2027 regular season, both seasons pooled"
    else:
        name = f"{what}: once, after the 2027 regular season, both seasons pooled"

    def ahead27(k):
        text = ahead("Week 18 of 2027", h27, k)
        if (h26 is None or NOW <= h26) and recorded(rule, H26) is None:
            text = text.rstrip(".") + f", or after Week 18 of 2026 with 40 {unit} in the 2026 regular season."
        return text
    decision(rule, H27, name, h27, lambda h: done if h is None else done[done.kick_utc <= h],
             lambda b: b.season.astype(int).values, "season", pending, ahead27,
             ("INCONCLUSIVE (carry forward unchanged)",
              f"INCONCLUSIVE (fewer than {ENOUGH} {unit} by the end of the 2027 regular season)"),
             enough=lambda b: what != "model lean" or len(b) >= ENOUGH)


pre = L[L.snapshot_utc < L.kick_utc]

# MODEL_LEAN: the original pre-registration, on its original horizon. Amendment 6, reading 5: the entry
# is the earliest snapshot at least 24 hours out that has both a lean and a posted total.
lean = pre[pre.lean.str.len().gt(0) & pd.to_numeric(pre.total_line, errors="coerce").notna()
           & (pre.snapshot_utc <= pre.kick_utc - LEAN_LEAD)]
lean = lean.sort_values("snapshot_utc").drop_duplicates("game_id")
lean = grade(lean.assign(side=np.where(lean.lean.str.startswith("UNDER"), "UNDER", "OVER")), "side")
done = report("MODEL_LEAN", lean)
if len(done) or recorded("model lean", H26) is not None or recorded("model lean", H27) is not None:
    horizon_decision("model lean", "leans", lean)

# RULE_B: amendment 1, gated by amendment 2, priced by amendment 5
sig = pre[pre.rule_b.isin(["SIGNAL", "SIGNAL_SECONDARY"])]
primary = sig[sig.rule_b.eq("SIGNAL") & sig.line_src.eq(PRIMARY_SRC)]
rb = grade(primary.sort_values("snapshot_utc").drop_duplicates("game_id").assign(side="UNDER"), "side")
done = report("RULE_B (wind under)", rb)
if len(done) or recorded("Rule B", H26) is not None or recorded("Rule B", H27) is not None:
    horizon_decision("Rule B", "signals", rb)

second = sig[~sig.game_id.isin(rb.game_id)]
second = grade(second.sort_values("snapshot_utc").drop_duplicates("game_id").assign(side="UNDER"), "side")
if len(second):
    report("RULE_B, secondary price (not part of the decision)", second)
else:
    print("\nRULE_B, secondary price (not part of the decision): 0 signals")

trig = pre[pre.rule_b.isin(["no_price", "price_too_high", "negative_ev", "outside_horizon", "SIGNAL",
                            "SIGNAL_SECONDARY"])]
if len(trig):
    print("\nWind triggers (a game counts once, at the best status it reached):")
    order = {"SIGNAL": 0, "SIGNAL_SECONDARY": 1, "negative_ev": 2, "price_too_high": 3, "no_price": 4,
             "outside_horizon": 5}
    # the same primary/secondary split as the tables above: a signal priced anywhere but Pinnacle is secondary
    status = np.where(trig.rule_b.eq("SIGNAL") & ~trig.line_src.eq(PRIMARY_SRC), "SIGNAL_SECONDARY", trig.rule_b)
    best = trig.assign(status=status, o=pd.Series(status, index=trig.index).map(order)).sort_values("o")
    print(best.drop_duplicates("game_id").status.value_counts().to_string())
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
print("\nDecision horizons (amendment 5, section 4, and amendment 6), for Rule B and the model lean alike: with "
      "40 in the 2026 regular season, after Week 18 of 2026 (its last regular-season kickoff) on those bets, where "
      "a keep or a drop is the decision and an inconclusive result is decided once more after the 2027 regular "
      "season on both seasons pooled; otherwise once, after the 2027 regular season, on both seasons pooled. A "
      "decision waits for every bet that kicked off by its horizon to settle or be void, and the first final one "
      "is written down.")
if NOT_RECORDED:
    print(f"Decision record: none written by this run: {NOT_RECORDED}.")
else:
    print("Decision record: the first final decision is written to " + (
        "data/forward/decisions.csv (the live record)." if IS_LIVE else "decisions.csv beside this test ledger."))
print("Variants under forward test: 2 (MODEL_LEAN, RULE_B).")
