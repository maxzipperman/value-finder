"""Score the pre-registered forward tests (PREREGISTRATION.md), one table per rule:

  MODEL_LEAN          model P(under) >= 55% / <= 45%. The entry is the earliest snapshot at least 24
                      hours before kickoff that has both a lean and a posted total (amendment 6).
  RULE_B              early wind under, priced at Pinnacle: the registered test. The entry is the
                      earliest pre-kickoff snapshot whose status was "SIGNAL". The 24-hour rule is the
                      lean's only: Rule B's window is about 11 to 82 hours (amendment 5, section 3).
  RULE_B (secondary)  the same gates at the backup price (the consensus line, when Pinnacle had no
                      quote). Reported separately; not part of the keep/drop decision (amendment 5).

What counts (amendments 2, 4 and 5): rows written under a registered rules version, logged before
kickoff, for games from Week 5 (Oct 8, 2026) through the 2027 season. "Before kickoff" is before the
earlier of the kickoff on the row and the kickoff in the schedule (amendment 6, reading 10). Rows outside
that are counted by reason, never silently dropped; --list-excluded prints each one.

Listings (amendment 6, reading 9): a game's rows are grouped by the kickoff on each row, so a game that is
postponed and signals again is two listings. Each listing has its own entry.

Each bet is settled, pending or void (amendment 6). It is void when its game kicked off more than 24
hours from the kickoff on its entry row, when another listing of the same game is the one nearest the
game's actual kickoff, or when the schedule still shows no result 30 days after that kickoff; a void bet
is listed by reason and not graded. It is pending while it has no result.

The decisions (amendment 5, section 4, and amendment 6) are computed here and labelled. Horizons are
dates: "after Week 18" is after the last regular-season kickoff in the schedule. A decision is FINAL
once its horizon has passed and no bet that kicked off by then is pending. A decision with fewer than 20
bets that have a primary close is INCONCLUSIVE (amendment 6, reading 11). The first FINAL is written
down, and every later run prints that record; if a fresh computation on the same horizon would now
differ, it prints both and the recorded one stands. Before that the script prints an interim read,
which shows the numbers and decides nothing.

Who writes a decision down (amendment 6, section 3): a run on the live ledger (data/forward/ledger.csv),
on the real clock, reading the default schedule refreshed in the last 2 days, writes
data/forward/decisions.csv. The scorer is live only when its data/forward folder, with links resolved, is
inside its own project folder. A run with --now is a preview: it records nothing, and shows a recorded
decision only if it was made by the preview's date. A run on another ledger kept in data/forward/ (the
rewrite's backup copy) neither reads nor writes a record. A copy of this scorer in another folder (a
worker's worktree) reads the live record but never writes it. A test ledger kept anywhere else writes
decisions.csv beside itself (a --now run on it only with --test-record, which exists for tests). A lost
live record is restored from its copy on the ledgers branch, never decided again. One run at a time writes, under a file lock, and a
damaged record stops recording without stopping the scores.

Each bet is graded at its ENTRY line and ENTRY price (profit in units, pushes return the stake), with
closing-line value against the final nflverse total. Amendment 3 adds a secondary CLV against
Pinnacle's total captured just before kickoff (data/forward/closes.csv). ROI is units won per bet
placed; a push counts as a bet. Wind triggers that never became a signal (no price, price too high,
outside the horizon) are counted, so coverage gaps can't quietly select winners.

    python scripts/fetch_data.py --skip-weather   # refresh schedule/lines/results
    python scripts/score_forward.py [--list-excluded]
"""
import argparse
import fcntl
import hashlib
import io
import json
import subprocess
import sys
from contextlib import contextmanager
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
MIN_CLOSES = 20                                       # amendment 6, reading 11: a CLV decision needs 20 closes
LEAN_LEAD = pd.Timedelta(hours=24)                    # the model lean's entry is at least 24 hours out
MOVED = pd.Timedelta(hours=24)                        # amendment 6: void if it kicked off further than this ...
NO_RESULT = pd.Timedelta(days=30)                     # ... or had no result this long after the entry's kickoff
VOID_MOVED = "the game kicked off more than 24 hours from the kickoff on its entry row"
VOID_OTHER = "another listing of this game is nearer its actual kickoff"
VOID_NO_RESULT = "the schedule shows no result 30 days after that kickoff"
H26, H27 = "after Week 18 of 2026", "after the 2027 regular season"     # the decision horizons, by name
# Amendment 6, reading 3: every decision has a fixed id, stored in its own column, and the record is looked up
# by that id, never by label text. No decisions.csv has been written yet (no decision has been recorded), so a
# file without the decision_id column can't exist and nothing needs migrating.
DECISION_ID = {("Rule B", H26): "RULE_B:2026", ("Rule B", H27): "RULE_B:2026-27",
               ("model lean", H26): "MODEL_LEAN:2026", ("model lean", H27): "MODEL_LEAN:2026-27"}
RECORD_COLS = ["decision_id", "rule", "horizon", "horizon_utc", "decided_utc", "n_bets", "verdict", "numbers",
               "ledger_rows", "ledger_rows_sha256"]
LIVE = ROOT / "data" / "forward"                      # the live folder: the alert jobs' ledger and its record
FRESH = pd.Timedelta(days=2)                          # a decision is recorded only from a schedule this fresh
PUBLISHED = f"origin/ledgers:{ROOT.name}/decisions.csv"   # the nightly copy of the record (ops/sync_ledgers.sh)

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
# (this checkout's or another's) is a live ledger or a copy of one, never a test ledger. This scorer is live
# only when its own data/forward folder, with links resolved, is inside its own project folder.
FWD = next((q for q in ledger.resolve().parents if q.name == "forward" and q.parent.name == "data"), None)
LIVE_INSIDE = LIVE.resolve().is_relative_to(ROOT.resolve())
ON_LIVE = ledger.resolve() == (LIVE / "ledger.csv").resolve()
IS_LIVE = LIVE_INSIDE and ON_LIVE                                       # this checkout's live ledger
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
elif ON_LIVE and not LIVE_INSIDE:
    NOT_RECORDED = ("this scorer's data/forward folder is a link to a folder outside its own project, so only the "
                    "scorer in that folder writes its record")
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


# ---------------------------------------------------------------- the decision record (amendment 6, reading 3)
def parse_record(data):
    """The decision record from a file's bytes: (rows, "") or (None, why it can't be read). A half-written line,
    a missing header or column, an empty file or a damaged number makes it unreadable."""
    def when(x):
        t = pd.Timestamp(x)
        if pd.isna(t):
            raise ValueError(f"a blank time ({x!r})")
        return t
    try:
        d = pd.read_csv(io.BytesIO(data), dtype=str, keep_default_na=False)
        missing = [c for c in RECORD_COLS if c not in d.columns]
        if missing:
            raise ValueError("no column " + ", ".join(missing))
        for r in d.itertuples():
            if not r.decision_id:
                raise ValueError("a row with no decision id")
            json.loads(r.numbers)
            when(r.horizon_utc), when(r.decided_utc)
            [int(p) for p in r.ledger_rows.split()]
    except Exception as e:                                              # noqa: BLE001 (any damage: report it)
        return None, f"{type(e).__name__}: {(str(e).splitlines() or [''])[0]}"
    return d, ""


def published_copy():
    """The record as ops/sync_ledgers.sh last copied it to the ledgers branch: read-only, without a fetch. A
    failure to read it counts as no copy."""
    try:
        r = subprocess.run(["git", "-C", str(ROOT), "show", PUBLISHED], capture_output=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout if r.returncode == 0 and r.stdout.strip() else None


@contextmanager
def record_lock():
    """One run at a time reads the record for writing and appends to it."""
    with open(DECISIONS.parent / ".decisions.lock", "a") as fh:
        try:
            fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("    waiting for another run to finish with the decision record", flush=True)
            fcntl.flock(fh, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


RECORD, RESTORED = None, False
if DECISIONS is not None:
    # A lost live record is restored from its nightly copy before anything is decided, so it is never decided again.
    if IS_LIVE and not NOT_RECORDED and not DECISIONS.exists():
        copy = published_copy()
        held = parse_record(copy)[0] if copy is not None else None
        if held is not None and len(held):
            with record_lock():
                if not DECISIONS.exists():
                    DECISIONS.write_bytes(copy)
                    RESTORED = True
            if RESTORED:
                print(f"Decision record: data/forward/decisions.csv was missing; restored {len(held)} recorded "
                      f"decision{'s' if len(held) != 1 else ''} from its copy on the ledgers branch ({PUBLISHED}). "
                      "A lost record is never decided again.")
    if DECISIONS.exists():
        RECORD, broken = parse_record(DECISIONS.read_bytes())
        if broken:
            print(f"Decision record: {DECISIONS.name} is unreadable ({broken}). Nothing will be recorded until it is "
                  "repaired or restored from the ledgers branch; the scores below are printed as usual.")
            NOT_RECORDED = ("the decision record is unreadable; nothing will be recorded until it is repaired or "
                            "restored from the ledgers branch")
        elif args.now:        # a preview shows only the decisions made by its date
            RECORD = RECORD.loc[np.array([pd.Timestamp(t) <= NOW for t in RECORD.decided_utc], dtype=bool)]


def recorded(did):
    """The decision already written down under this id, or None."""
    if RECORD is None:
        return None
    d = RECORD[RECORD.decision_id.eq(did)]
    return None if d.empty else d.iloc[0]


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
# Amendment 6, reading 10: "before kickoff" is before the earlier of the row's kickoff and the schedule's
L["kick_first"] = L[["row_kick", "kick_utc"]].min(axis=1)
# Amendment 3: the Pinnacle close captured just before kickoff (scripts/capture_close.py), secondary only
closes = ledger.parent / "closes.csv"
cap = pd.read_csv(closes) if closes.exists() else pd.DataFrame(columns=["game_id", "book", "close_total"])
cap = (cap[cap.book.eq("pinnacle")].dropna(subset=["close_total"]).drop_duplicates("game_id", keep="last")
       [["game_id", "close_total"]].rename(columns={"close_total": "cap_close"}))
L = L.merge(cap, on="game_id", how="left")

# What counts. Every excluded row is counted by its first failing reason.
why = np.select([~L.rules_version.isin(REGISTERED_VERSIONS), ~L.in_schedule, L.kick_utc.isna(),
                 L.kick_utc < FIRST_KICK, ~L.season.isin(TEST_SEASONS), L.snapshot_utc >= L.kick_first],
                ["unregistered rules version", "game not in the schedule", "no kickoff time in the schedule",
                 "before Week 5 (Oct 8, 2026)", "after the 2027 season", "logged at or after kickoff"], "")
print(f"ledger rows: {len(L)}; in the test: {int((why == '').sum())}")
for reason, n in pd.Series(why[why != ""]).value_counts().items():
    print(f"  excluded, {reason}: {n}")
if args.list_excluded and (why != "").any():
    print(L.assign(excluded=why)[why != ""][["snapshot_utc", "game_id", "rules_version", "lean", "rule_b", "excluded"]]
          .to_string(index=False))
L = L[why == ""]


def listings(rows):
    """Amendment 6, reading 9: a game's rows grouped by the kickoff on each row. In order of that kickoff, a row
    more than 24 hours after the first kickoff of the current listing starts a new one, so the kickoffs of one
    listing are all within 24 hours of each other. A postponed game that signals again is two listings."""
    rows = rows.assign(_lk=rows.row_kick.fillna(rows.kick_utc)).sort_values(["game_id", "_lk", "snapshot_utc"],
                                                                            kind="stable")
    ids, prev, first, n = [], object(), None, 0
    for gid, k in zip(rows.game_id, rows._lk):
        if gid != prev:
            prev, first, n = gid, k, 0
        elif pd.notna(k) and pd.notna(first) and k - first > MOVED:
            first, n = k, n + 1
        ids.append(n)
    return rows.assign(listing=ids).drop(columns="_lk")


L = listings(L)


def entries(rows):
    """Each listing's entry: its earliest row."""
    return rows.sort_values("snapshot_utc", kind="stable").drop_duplicates(["game_id", "listing"])


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
    # Amendment 6, readings 1, 2 and 9: void (moved, another listing of the game is the one graded, or never
    # scored), pending (no result yet), or settled. One listing per game is graded: the one whose kickoff is
    # nearest the game's actual kickoff (the later listing on a tie).
    moved = (bets.kick_utc - bets.row_kick).abs() > MOVED
    dist = (bets.kick_utc - bets.row_kick.fillna(bets.kick_utc)).abs()
    chosen = bets.assign(_d=dist).sort_values(["_d", "listing"], ascending=[True, False]).drop_duplicates("game_id")
    other = ~bets.index.isin(chosen.index)
    stale = bets.result.isna() & (NOW >= bets.row_kick.fillna(bets.kick_utc) + NO_RESULT)
    void = np.select([moved, other, stale], [VOID_MOVED, VOID_OTHER, VOID_NO_RESULT], "")
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
    (or season); CLV must be positive in every part. Keep and drop both met is a DROP. With fewer than 20
    bets that have a primary close the result is inconclusive (amendment 6, reading 11)."""
    m, lo, hi, n = mean_ci(bets.clv_pts)
    has = bets.close_total.notna()
    graded = bets[has & ~bets.tie_close]                           # no close, or a tie with it: left out
    rate = graded.beat_close.mean() if len(graded) else np.nan
    parts = bets.assign(part=split).groupby("part").clv_pts.mean()
    f = lambda v: None if pd.isna(v) else float(v)                # noqa: E731
    nums = dict(n_bets=len(bets), mean_clv=f(m), ci_low=f(lo), ci_high=f(hi), n_clv=int(n), win_rate_vs_close=f(rate),
                beat_close=int(graded.beat_close.sum()), vs_close_no_tie=len(graded),
                ties=int((has & bets.tie_close).sum()), split=split_name,
                by_part={str(k): float(v) for k, v in parts.items()})
    keep, drop = criteria(nums)
    head, tail = final_label[0].split(" (", 1)
    verdict = (final_label[1] if not enough else
               f"{head} (only {n} of the {len(bets)} bets have a primary close, fewer than {MIN_CLOSES}; {tail}"
               if n < MIN_CLOSES else
               "DROP" if drop else "KEEP" if all(keep.values()) else final_label[0])
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
    print(f"    mean CLV {m:+.2f} ({ci}, n={n}); win rate vs the close {100 * rate:.1f}% ({nums['beat_close']} of "
          f"the {nums['vs_close_no_tie']} bets that have a primary close and didn't tie it; {nums['ties']} ties left "
          f"out); mean CLV by {nums['split']}: { {k: round(v, 2) for k, v in nums['by_part'].items()} }")
    if nums["n_bets"] > n:
        print(f"    {nums['n_bets'] - n} of the {nums['n_bets']} bets have no primary close (left out of the CLV and "
              "the win rate)")
    if n < MIN_CLOSES:
        print(f"    only {n} bets have a primary close; a verdict needs at least {MIN_CLOSES} (amendment 6, reading 11)")
    print("    keep needs: " + "; ".join(f"{k} ({'met' if bool(v) else 'not met'})" for k, v in keep.items())
          + f". Drop if mean CLV <= 0 or the interval's upper bound is below +0.25 ({'met' if drop else 'not met'}).")


def fingerprint(positions):
    """Amendment 6, reading 3: sha256 of the ledger's header line and then each row that entered the decision,
    exactly as written, in ledger order, each followed by a newline. None when a row is missing."""
    if any(p < 1 or p > len(LINES) for p in positions):
        return None
    return hashlib.sha256(("\n".join([HEADER] + [LINES[p - 1] for p in positions]) + "\n").encode()).hexdigest()


def check_fingerprint(rec):
    """Recompute a recorded decision's fingerprint from the rows it lists; warn if they changed since."""
    now = fingerprint([int(p) for p in rec.ledger_rows.split()])
    if now != rec.ledger_rows_sha256:
        print("    warning: the ledger's header or the rows behind this recorded decision have changed since it was "
              f"recorded (their fingerprint is now {now[:16] if now else 'incomplete: rows are missing'}). The "
              "recorded decision still stands.")


def write_down(did, rule, horizon, horizon_utc, verdict, nums, rows):
    """Append a decision the first time it is FINAL, with the positions of the ledger rows that entered it (1 is
    the first row after the header; the entry rows, since the closes come from the schedule) and their
    fingerprint. Under the file lock the record is read again first, so two runs at once write one row. A run
    that may not record (a --now preview, a stale schedule, a copy of the ledger in data/forward/, an unreadable
    record) says why instead."""
    if NOT_RECORDED:
        print(f"    not recorded: {NOT_RECORDED}.")
        return
    positions = sorted({int(r) + 1 for r in rows})
    rec = dict(decision_id=did, rule=rule, horizon=horizon, horizon_utc=f"{horizon_utc:%Y-%m-%dT%H:%M:%SZ}",
               decided_utc=f"{NOW:%Y-%m-%dT%H:%M:%SZ}", n_bets=nums["n_bets"], verdict=verdict,
               numbers=json.dumps(nums), ledger_rows=" ".join(map(str, positions)),
               ledger_rows_sha256=fingerprint(positions))
    with record_lock():
        now_held, broken = parse_record(DECISIONS.read_bytes()) if DECISIONS.exists() else (None, "")
        if broken:
            print(f"    not recorded: the decision record is unreadable ({broken}); nothing will be recorded until it "
                  "is repaired or restored from the ledgers branch.")
            return
        if now_held is not None and now_held.decision_id.eq(did).any():
            first = now_held[now_held.decision_id.eq(did)].iloc[0]
            print(f"    not recorded: this decision was already recorded on {first.decided_utc} ({first.verdict}), "
                  "and that record stands.")
            return
        pd.DataFrame([rec], columns=RECORD_COLS).to_csv(DECISIONS, mode="a", header=not DECISIONS.exists(),
                                                        index=False)
    print(f"    recorded in decisions.csv on {rec['decided_utc']}, horizon {rec['horizon_utc']}; "
          f"ledger rows sha256 {rec['ledger_rows_sha256'][:16]}")


def decision(did, rule, horizon, name, h_utc, bets_by, split_by, split_name, pending, when, labels,
             enough=lambda b: True):
    """One registered decision. Prints the recorded one if it exists (and a fresh computation on the same
    horizon beside it when that now differs); otherwise FINAL, written down by a run that may record, once
    the horizon has passed and no bet that kicked off by then is pending; otherwise an interim read.
    Returns the verdict or None."""
    rec = recorded(did)
    if rec is not None:
        h = pd.Timestamp(rec.horizon_utc)
        bets = bets_by(h)
        fresh, nums = assess(bets, split_by(bets), split_name, labels, enough(bets))
        print(f"  decision ({name}), FINAL: {rec.verdict}")
        show(json.loads(rec.numbers))
        print(f"    recorded in decisions.csv on {rec.decided_utc}, horizon {rec.horizon_utc}; "
              f"ledger rows sha256 {rec.ledger_rows_sha256[:16]}" + ("; restored from the ledgers branch" if RESTORED
                                                                       else ""))
        check_fingerprint(rec)
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
        write_down(did, rule, horizon, h_utc, verdict, nums, bets._row)
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
    id26, id27 = DECISION_ID[(what, H26)], DECISION_ID[(what, H27)]
    reg26 = done[(done.season == 2026) & done.game_type.astype(str).eq("REG")]
    # 2026 bets still waiting for a result can bring 2026 to 40: its decision then waits for them
    wait26 = pending[(pending.season == 2026) & pending.game_type.astype(str).eq("REG")]

    def ahead(label, h, waiting):
        if h is not None and NOW > h:
            return f"{label} is over; the decision waits for {waiting} pending {unit if waiting != 1 else unit[:-1]}."
        return f"The decision comes {label.replace('Week', 'after Week', 1)}" + (
            f" (the last regular-season kickoff, {h:%Y-%m-%d %H:%M} UTC)." if h is not None else ".")

    rule = what
    if recorded(id27) is not None and recorded(id26) is None:
        name = f"{what}: once, after the 2027 regular season, both seasons pooled"
    elif recorded(id26) is not None or len(reg26) + len(wait26) >= ENOUGH:
        verdict = decision(id26, rule, H26, f"{what}: 40 {unit} in 2026, decided after Week 18 of 2026", h26,
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
        if (h26 is None or NOW <= h26) and recorded(id26) is None:
            text = text.rstrip(".") + f", or after Week 18 of 2026 with 40 {unit} in the 2026 regular season."
        return text
    decision(id27, rule, H27, name, h27, lambda h: done if h is None else done[done.kick_utc <= h],
             lambda b: b.season.astype(int).values, "season", pending, ahead27,
             ("INCONCLUSIVE (carry forward unchanged)",
              f"INCONCLUSIVE (fewer than {ENOUGH} {unit} by the end of the 2027 regular season)"),
             enough=lambda b: what != "model lean" or len(b) >= ENOUGH)


def any_recorded(what):
    return recorded(DECISION_ID[(what, H26)]) is not None or recorded(DECISION_ID[(what, H27)]) is not None


pre = L                     # every row that counts was logged before the earlier kickoff (reading 10)

# MODEL_LEAN: the original pre-registration, on its original horizon. Amendment 6, reading 5: the entry
# is the earliest snapshot at least 24 hours out that has both a lean and a posted total.
lean = pre[pre.lean.str.len().gt(0) & pd.to_numeric(pre.total_line, errors="coerce").notna()
           & (pre.snapshot_utc <= pre.kick_first - LEAN_LEAD)]
lean = entries(lean)
lean = grade(lean.assign(side=np.where(lean.lean.str.startswith("UNDER"), "UNDER", "OVER")), "side")
done = report("MODEL_LEAN", lean)
if len(done) or any_recorded("model lean"):
    horizon_decision("model lean", "leans", lean)

# RULE_B: amendment 1, gated by amendment 2, priced by amendment 5
sig = pre[pre.rule_b.isin(["SIGNAL", "SIGNAL_SECONDARY"])]
primary = sig[sig.rule_b.eq("SIGNAL") & sig.line_src.eq(PRIMARY_SRC)]
rb = grade(entries(primary).assign(side="UNDER"), "side")
done = report("RULE_B (wind under)", rb)
if len(done) or any_recorded("Rule B"):
    horizon_decision("Rule B", "signals", rb)

second = sig[~sig.game_id.isin(rb.game_id)]
second = grade(entries(second).assign(side="UNDER"), "side")
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
    one = rb.assign(v=rb.status.eq("void")).sort_values("v", kind="stable").drop_duplicates("game_id")  # graded listing
    entries_ = one[["game_id", "total_line", "under_odds"]].rename(
        columns={"total_line": "entry_line", "under_odds": "entry_price"}).assign(rule="rule_b")
    wc = cost_of_waiting(entries_, fills)
    if len(wc):
        print(f"\nCost of waiting, RULE_B: {len(wc)} paper fills; vs the alert-time quote the fill gained "
              f"{wc.pts_gained.mean():+.2f} pts and {wc.profit_gained.mean():+.3f} units of payout per unit staked")
print("\nDecision horizons (amendment 5, section 4, and amendment 6), for Rule B and the model lean alike: with "
      "40 in the 2026 regular season, after Week 18 of 2026 (its last regular-season kickoff) on those bets, where "
      "a keep or a drop is the decision and an inconclusive result is decided once more after the 2027 regular "
      "season on both seasons pooled; otherwise once, after the 2027 regular season, on both seasons pooled. A "
      "decision waits for every bet that kicked off by its horizon to settle or be void, needs at least 20 bets "
      "with a primary close, and the first final one is written down.")
if NOT_RECORDED:
    print(f"Decision record: none written by this run: {NOT_RECORDED}.")
else:
    print("Decision record: the first final decision is written to " + (
        "data/forward/decisions.csv (the live record)." if IS_LIVE else "decisions.csv beside this test ledger."))
print("Variants under forward test: 2 (MODEL_LEAN, RULE_B).")
