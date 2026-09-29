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
counts, whatever its season label; amendment 4). "Before kickoff" is before the earlier of the kickoff
on the row and the kickoff in the schedule (amendment 4, reading 11). Rows outside that are counted by
reason, never silently dropped; --list-excluded prints each one. ROI is units won per bet placed; a push
counts as a bet. A game is graded only once the schedule marks it completed.

Listings (amendment 4, reading 10): a game's rows are grouped by the kickoff on each row, so a game that
is postponed and signals again is two listings. Each listing has its own entry (and, for Rule B, its own
later-quote close).

Each bet is settled, pending or void (amendment 4). It is void when its game kicked off more than 24
hours from the kickoff on its entry row, when another listing of the same game is the one graded, or
when the schedule still shows no score 30 days after that kickoff; a void bet is listed by reason and not
graded. It is pending while it has no score.

The decisions are computed here and labelled. A decision is FINAL once its horizon has passed and no
bet that kicked off by then is pending. A Rule B decision with fewer than 20 bets that have a primary
close is INCONCLUSIVE (amendment 4, reading 12). The first FINAL is written down, and every later run
prints that record; if a fresh computation on the same horizon would now differ, it prints both and the
recorded one stands. Before that the script prints an interim read, which shows the numbers and decides
nothing.

Rule B's 95% interval of mean CLV (amendment 5, reading 1) is the wider of two, over the n signals with a primary
close and their plain mean m: the plain half-width t(0.975, n - 1) x sd / sqrt(n), and the grouped half-width
t(0.975, G - 1) x sqrt((G / (G - 1)) x sum over days of (sum of that day's CLV - m)^2 / n^2), the signals grouped
by the Eastern calendar date of their game's actual kickoff (the schedule's; the entry row's when the schedule
gives none; G days). The interval is m plus or minus the larger. With fewer than 2 game days (or 2 signals) there
is no interval and the decision is INCONCLUSIVE. The scorer prints which of the two is the wider, and both; the
record keeps the interval, both half-widths and G. Rule HT is graded on results and doesn't change.

Who writes a decision down (amendment 4, section 3): a run on the live ledger (data/forward/ledger.csv),
on the real clock, reading the default cfbfastR schedule whose current-season file was refreshed in the
last 2 days, writes data/forward/decisions.csv. The scorer is live only when its data/forward folder,
with links resolved, is inside its own project folder. A run with --now is a preview: it records
nothing, and shows a recorded decision only if it was made by the preview's date. A run on another
ledger kept in data/forward/ (the rewrite's backup copy) neither reads nor writes a record. A copy of
this scorer in another folder (a worker's worktree) reads the live record but never writes it. A test
ledger kept anywhere else writes decisions.csv beside itself (a --now run on it only with --test-record,
which exists for tests). A lost live record is restored from its copy on the ledgers branch, never
decided again: while the file is missing, every run on the live ledger reads the copy, a real run restores
the file from it, and any other run prints the copy's decisions as recorded. A copy that is there but
damaged stops recording, as a damaged file does. One run at a time writes, under a file lock, and a
damaged record (a half-written line, a line without its 10 fields, numbers a later run can't print, a time
with no time zone) stops recording without stopping the scores.

Amendment 5, reading 3: in a damaged record, every decision whose line can still be read on its own is
printed as recorded, never as a fresh FINAL. A decision that a decisions.csv still in place is missing, while
its copy on the ledgers branch holds it, is restored from the copy by a real run (and read from the copy by
any other run), never decided again; the restore appends the copy's own line, byte for byte. The nightly copy
(ops/sync_ledgers.sh) never publishes a file that has lost a line of the published copy, so the copy keeps every
decision it ever held: the one case left is a decision recorded since the last nightly copy that published the
file and lost before the next one (normally the same day; longer while a changed published line holds the file
back, until the hub puts it right). A copy that can't be read stops recording whether or not the file is
there, and each decision on a line of it that can still be read is printed from it as recorded; nothing is
restored from a damaged copy, and the hub replaces a damaged published copy by hand with a commit to the ledgers
branch. A blank line, or a line of only spaces, in the file or its copy is not a record and is not damage: it is
skipped when read and never copied by a restore.

    python scripts/score_forward.py [--ledger PATH] [--schedule PATH] [--list-excluded]
"""
import argparse
import csv
import fcntl
import hashlib
import io
import json
import re
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd
from scipy import stats

from cfbweather.board import HT_FIRST_KICK, REGISTERED_VERSIONS, TEST_SEASONS, season_of
from cfbweather.config import RAW, ROOT
from cfbweather.market import american_to_profit, cost_of_waiting

FIRST_KICK = pd.Timestamp("2026-10-01", tz="UTC")
REG_END_2026 = pd.Timestamp("2026-12-13T08:00:00Z")   # the 2026 regular season ends with Army-Navy, Dec 12
TEST_END = pd.Timestamp("2028-02-01T00:00:00Z")       # after the 2027 season's title game (January 2028)
ENOUGH = 40
MIN_CLOSES = 20                                       # amendment 4, reading 12: a CLV decision needs 20 closes
MOVED = pd.Timedelta(hours=24)                        # amendment 4: void if it kicked off further than this ...
NO_RESULT = pd.Timedelta(days=30)                     # ... or had no score this long after the entry's kickoff
VOID_MOVED = "the game kicked off more than 24 hours from the kickoff on its entry row"
VOID_OTHER = "another listing of this game is the one graded"
VOID_NO_RESULT = "the schedule shows no result 30 days after that kickoff"
RB_HORIZON = "after 40 signals or the 2026 regular season, whichever is later"
HT_HORIZON = "once, after the 2027 season's title game"
NOT_KEPT = ("NOT KEPT (no money goes on the rule; it stays on paper for 2027 only by a dated amendment before "
            "2027 Week 0)")
# Amendment 4, reading 3: every decision has a fixed id, stored in its own column, and the record is looked up
# by that id, never by label text. No decisions.csv has been written yet (no decision has been recorded), so a
# file without the decision_id column can't exist and nothing needs migrating.
RB_ID, HT_ID = "CFB_RULE_B", "CFB_RULE_HT"
RECORD_COLS = ["decision_id", "rule", "horizon", "horizon_utc", "decided_utc", "n_bets", "verdict", "numbers",
               "ledger_rows", "ledger_rows_sha256"]
LIVE = ROOT / "data" / "forward"                      # the live folder: the alert jobs' ledger and its record
FRESH = pd.Timedelta(days=2)                          # a decision is recorded only from a schedule this fresh
PUBLISHED = f"origin/ledgers:{ROOT.name}/decisions.csv"   # the nightly copy of the record (ops/sync_ledgers.sh)

ap = argparse.ArgumentParser()
ap.add_argument("--ledger", default=str(LIVE / "ledger.csv"))
ap.add_argument("--schedule", help="CSV with game_id, home_points, away_points, and start_utc or start_date for the "
                                   "moved-game check (default: cfbfastR schedules)")
ap.add_argument("--list-excluded", action="store_true", help="print every excluded row with its reason")
ap.add_argument("--now", help="score as of this UTC time: a preview for tests and rehearsals, which records no "
                              "decision; default: the clock")
ap.add_argument("--test-record", action="store_true",
                help="tests only: with --now, record final decisions beside a test ledger as if made at --now "
                     "(refused for any ledger in data/forward/)")
args = ap.parse_args()
CLOCK = pd.Timestamp.now(tz="UTC")
NOW = pd.Timestamp(args.now, tz="UTC") if args.now else CLOCK
path = Path(args.ledger)
if not path.exists():
    sys.exit("no ledger yet: run scripts/alerts.py")
# Amendment 4, section 3: who writes a decision down, and where. A ledger inside a data/forward/ folder
# (this checkout's or another's) is a live ledger or a copy of one, never a test ledger. This scorer is live
# only when its own data/forward folder, with links resolved, is inside its own project folder.
FWD = next((q for q in path.resolve().parents if q.name == "forward" and q.parent.name == "data"), None)
LIVE_INSIDE = LIVE.resolve().is_relative_to(ROOT.resolve())
ON_LIVE = path.resolve() == (LIVE / "ledger.csv").resolve()
IS_LIVE = LIVE_INSIDE and ON_LIVE                                       # this checkout's live ledger
if args.test_record and (not args.now or FWD is not None):
    sys.exit("--test-record needs --now and a test ledger outside data/forward/")
if FWD is None:
    DECISIONS = path.parent / "decisions.csv"                           # a test ledger's own record
elif path.name == "ledger.csv" and path.resolve().parent == FWD:
    DECISIONS = FWD / "decisions.csv"                                   # a live ledger's record
else:
    DECISIONS = None                                                    # a copy, such as the rewrite's backup
# Freshness: only the current season's schedule file counts (every alert run refreshes that one)
CURRENT = RAW / "cfbfastr" / f"schedules_{season_of(CLOCK)}.parquet"
fresh_file = Path(args.schedule) if args.schedule else CURRENT
refreshed = (pd.Timestamp(fresh_file.stat().st_mtime, unit="s", tz="UTC") if fresh_file.exists()
             else pd.Timestamp(0, tz="UTC"))
if DECISIONS is None:
    NOT_RECORDED = "this ledger is kept in data/forward/ but is not the live ledger, so no record is read or written"
elif ON_LIVE and not LIVE_INSIDE:
    NOT_RECORDED = ("this scorer's data/forward folder is a link to a folder outside its own project, so only the "
                    "scorer in that folder writes its record")
elif not IS_LIVE and FWD is not None:
    NOT_RECORDED = "this is another folder's live ledger, and only the scorer in that folder writes its record"
elif args.now and not args.test_record:
    NOT_RECORDED = "a run with --now is a preview"
elif IS_LIVE and args.schedule:
    NOT_RECORDED = "the live record is written only from the default schedule (cfbfastR)"
elif not fresh_file.exists():
    NOT_RECORDED = (f"the current season's schedule, {fresh_file.name}, is missing; refresh it (every alert run does, "
                    "or scripts/fetch_data.py) and run the scorer again")
elif CLOCK - refreshed > FRESH:
    what = "the schedule" if args.schedule else f"the current season's schedule, {fresh_file.name},"
    NOT_RECORDED = (f"{what} was last refreshed {refreshed:%Y-%m-%d %H:%M} UTC, more than 2 days ago; refresh it "
                    "(every alert run does, or scripts/fetch_data.py) and run the scorer again")
else:
    NOT_RECORDED = ""


# ---------------------------------------------------------------- the decision record (amendment 4, reading 3)
# What a recorded decision must hold for a later run to print it (null where there is no number, as for an
# interval on one bet). A Rule B record made at the end of the test with fewer than 40 holds only its count.
# Amendment 5: ci_low and ci_high are the registered interval, the mean plus or minus the wider of plain_half_width
# and grouped_half_width (the latter over game_days game days). No decision has been recorded yet, so no record
# without these keys exists.
NEEDS = {RB_ID: (("n_bets",), ()),
         RB_ID + " at its horizon": (("n_bets", "n_clv", "game_days"),
                                     ("mean_clv", "ci_low", "ci_high", "plain_half_width", "grouped_half_width")),
         HT_ID: (("n_bets", "wins", "losses", "pushes"), ("units", "roi", "avg_break_even", "p_one_sided"))}


def is_number(v, none_ok=False):
    return (v is None and none_ok) or (isinstance(v, (int, float)) and not isinstance(v, bool))


def check_row(r):
    """One recorded decision, or ValueError saying what is damaged in it."""
    if r.decision_id not in (RB_ID, HT_ID):
        raise ValueError(f"an unknown decision id {r.decision_id!r}")
    for t in (r.horizon_utc, r.decided_utc):
        if pd.isna(pd.Timestamp(t)):
            raise ValueError(f"a blank time ({t!r})")
        if pd.Timestamp(t).tzinfo is None:              # amendment 5, reading 3: it can't be read as a UTC time
            raise ValueError(f"a time with no time zone ({t!r}), which can't be read as a UTC time")
    int(r.n_bets)
    known = (("KEEP", NOT_KEPT) if r.decision_id == RB_ID else ("PROMOTE", "DROP", "STAY ON PAPER"))
    if not (r.verdict in known or (r.decision_id == RB_ID and r.verdict.startswith("INCONCLUSIVE"))):
        raise ValueError(f"an unknown verdict {r.verdict!r}")
    nums = json.loads(r.numbers)
    if not isinstance(nums, dict):
        raise ValueError(f"{r.decision_id}'s numbers are not a set of named numbers")
    counts, numbers = NEEDS[r.decision_id + (" at its horizon" if r.decision_id == RB_ID and "horizon" in nums
                                             else "")]
    missing = [k for k in counts + numbers if k not in nums]
    if missing:
        raise ValueError(f"{r.decision_id}'s numbers have no {', '.join(missing)}")
    bad = ([k for k in counts if not is_number(nums[k])] + [k for k in numbers if not is_number(nums[k], True)]
           + ([] if isinstance(nums.get("horizon", ""), str) else ["horizon"]))
    if bad:
        raise ValueError(f"{r.decision_id}'s numbers have a damaged {', '.join(bad)}")
    [int(p) for p in r.ledger_rows.split()]
    if not re.fullmatch(r"[0-9a-f]{64}", r.ledger_rows_sha256):
        raise ValueError(f"{r.decision_id}'s fingerprint is not 64 hexadecimal characters")


def record_lines(data):
    """Amendment 5, reading 3: a record's lines, as bytes without their line breaks, in order. A blank line, or a line
    of only spaces (before a CRLF line's carriage return), is not a record and is not damage: it is left out here,
    so it is skipped when the file or its copy is read, never counted as a decision and never copied by a restore.
    Whatever follows the last line break (nothing, in a file that can be read) is left out too."""
    return [p for p in data.split(b"\n")[:-1] if not re.fullmatch(rb" *\r?", p)]


def parse_record(data):
    """The decision record from a file's bytes: (rows, "") or (None, why it can't be read). The file must end with
    a complete line, its first line must be the record's header, every line must have exactly its 10 fields, and
    each row must be one of this scorer's decisions, with valid times, the numbers a later run prints, row
    positions and a full fingerprint. A half-written line (wherever it was cut), a missing header or column, an
    empty file or a damaged number makes it unreadable. Blank lines are skipped (record_lines)."""
    try:
        text = data.decode("utf-8")
        if not text.endswith("\n"):             # a cut last line, or an empty file: never append to it
            raise ValueError("the file is empty" if not text else "its last line is not complete (no line break)")
        text = b"".join(p + b"\n" for p in record_lines(data)).decode("utf-8")
        if not text:
            raise ValueError("the file holds only blank lines")
        lines = [f for f in csv.reader(io.StringIO(text, newline=""), strict=True) if f]
        if not lines or lines[0] != RECORD_COLS:
            raise ValueError("its first line is not the record's header")
        for i, fields in enumerate(lines[1:], start=1):
            if len(fields) != len(RECORD_COLS):
                raise ValueError(f"record {i} has {len(fields)} fields, not {len(RECORD_COLS)}")
        d = pd.DataFrame(lines[1:], columns=RECORD_COLS)
        for r in d.itertuples():
            check_row(r)
    except Exception as e:                                              # noqa: BLE001 (any damage: report it)
        return None, f"{type(e).__name__}: {(str(e).splitlines() or [''])[0]}"
    return d, ""


def readable_records(data):
    """Amendment 5, reading 3: the decisions in a damaged record that can still be read. Each line is taken on
    its own, and it can be read when it has exactly the record's 10 fields, in the record's order, and passes
    every check a recorded decision must pass (check_row). The first line holding a decision id is the one kept,
    as `recorded` reads a whole file."""
    keep = []
    for line in re.split(r"\r?\n", data.decode("utf-8", errors="replace")):
        try:
            fields = next(csv.reader([line], strict=True), [])
            if len(fields) != len(RECORD_COLS) or fields == RECORD_COLS:
                continue
            check_row(next(pd.DataFrame([fields], columns=RECORD_COLS).itertuples()))
        except Exception:                                               # noqa: BLE001 (this line can't be read)
            continue
        keep.append(fields)
    return pd.DataFrame(keep, columns=RECORD_COLS).drop_duplicates("decision_id")


def published_copy():
    """The record as ops/sync_ledgers.sh last copied it to the ledgers branch: read-only, without a fetch. None
    when git can't show it (no ledgers branch, or no file in it): that is no copy. A copy that git shows is
    returned as it is, even empty, so that a damaged copy is seen as damaged."""
    try:
        r = subprocess.run(["git", "-C", str(ROOT), "show", PUBLISHED], capture_output=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout if r.returncode == 0 else None


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


RECORD, RESTORED, FROM_COPY, DAMAGED = None, set(), {}, False     # FROM_COPY: decision id -> why it came from the copy
HISTORY = f"git log origin/ledgers -- {ROOT.name}/decisions.csv"   # where a readable earlier copy can be found


def plural(k, word="decision"):
    return f"{k} recorded {word}{'s' if k != 1 else ''}"


def copy_lines(readable):
    """What a damaged copy still shows, for the line that says it is damaged."""
    k = len(readable)
    return (f" {plural(k)} in the copy can still be read ({', '.join(readable.decision_id)})." if k else
            " No recorded decision in the copy can still be read.")


def lines_held(data, ids):
    """Amendment 5, reading 3: a readable copy's own record lines for these decision ids, byte for byte and in the
    copy's order. A restore appends them as they are, so the file again holds every line of the published copy, and
    the nightly copy (which never publishes a file that has lost a published line) publishes it again. Blank lines
    are never copied (record_lines)."""
    pieces = record_lines(data)[1:]             # after the header, blank lines left out
    return b"".join(p + b"\n" for p in pieces if (next(csv.reader([p.decode("utf-8")]), None) or [""])[0] in ids)


if DECISIONS is not None:
    # A lost live record is restored from its nightly copy before anything is decided, so it is never decided
    # again. Every run on a live ledger reads the copy; only a run that may record restores from it, and any other
    # run prints the copy's decisions as recorded.
    copy = published_copy() if FWD is not None else None
    held, copy_broken = parse_record(copy) if copy is not None else (None, "")
    if copy_broken:
        # Amendment 4, section 3: a copy that can't be read stops recording, as a damaged file does, whether or not
        # the file is there. Amendment 5, reading 3: each decision on a line of it that can still be read is held,
        # so it is printed from the copy as recorded and never decided again; nothing is restored from a damaged copy.
        held = readable_records(copy)
    if FWD is not None and not DECISIONS.exists():
        if copy_broken:
            RECORD, FROM_COPY = held, dict.fromkeys(held.decision_id, "the file is missing, and the copy is damaged; "
                                                                      "this line of it can still be read")
            print(f"Decision record: data/forward/decisions.csv is missing, and its copy on the ledgers branch "
                  f"({PUBLISHED}) is unreadable ({copy_broken}). Nothing will be recorded until the file is restored "
                  f"from a readable copy in that branch's history ({HISTORY}) and the copy can be read again: the hub "
                  "replaces a damaged published copy by hand with a commit to the ledgers branch, and recording "
                  "resumes once the copy can be read. The scores below are printed as usual."
                  + copy_lines(held) + (" They are printed below as recorded." if len(held) else ""))
            NOT_RECORDED = ("the decision record is missing and its copy on the ledgers branch is unreadable; nothing "
                            f"will be recorded until the file is restored from a readable copy ({HISTORY}) and the "
                            "copy can be read again")
        elif held is not None and len(held):
            if IS_LIVE and not NOT_RECORDED:
                with record_lock():
                    if not DECISIONS.exists():            # the copy's own lines, blank lines left out
                        DECISIONS.write_bytes(b"".join(p + b"\n" for p in record_lines(copy)))
                        RESTORED = set(held.decision_id)
                if RESTORED:
                    print(f"Decision record: data/forward/decisions.csv was missing; restored {plural(len(held))} "
                          f"from its copy on the ledgers branch ({PUBLISHED}). A lost record is never decided again.")
            else:
                RECORD, FROM_COPY = held, dict.fromkeys(held.decision_id, "the file is missing")
                print(f"Decision record: data/forward/decisions.csv is missing; its copy on the ledgers branch "
                      f"({PUBLISHED}) holds {plural(len(held))}, printed below as recorded. This run doesn't restore "
                      f"the file ({NOT_RECORDED}); the next run that may record restores it.")
    if DECISIONS.exists() and not FROM_COPY:
        data = DECISIONS.read_bytes()
        RECORD, broken = parse_record(data)
        if broken:
            # Amendment 5, reading 3: the decisions that can still be read are printed as recorded, never as a
            # fresh FINAL, and nothing is recorded until the file is repaired
            DAMAGED, RECORD = True, readable_records(data)
            print(f"Decision record: {DECISIONS.name} is unreadable ({broken}). Nothing will be recorded until it is "
                  "repaired or restored from the ledgers branch; the scores below are printed as usual. "
                  + (f"{plural(len(RECORD))} in it can still be read ({', '.join(RECORD.decision_id)}) and "
                     f"{'are' if len(RECORD) != 1 else 'is'} printed below as recorded."
                     if len(RECORD) else "No recorded decision in it can still be read."))
            NOT_RECORDED = ("the decision record is unreadable; nothing will be recorded until it is repaired or "
                            "restored from the ledgers branch")
        if copy_broken:
            # Amendment 4, section 3, and amendment 5, reading 3: the file is there, but its copy can't be read, so
            # nothing is recorded until the copy can be read again, and the copy's readable decisions are held
            print(f"Decision record: its copy on the ledgers branch ({PUBLISHED}) is unreadable ({copy_broken}). "
                  "Nothing will be recorded until the copy can be read again: the hub replaces a damaged published "
                  "copy by hand with a commit to the ledgers branch, and recording resumes once the copy can be "
                  "read. The scorer never restores from a damaged copy; if the file "
                  f"has lost a decision, restore it by hand from a readable copy in the branch's history ({HISTORY})."
                  + copy_lines(held))
            NOT_RECORDED = (("the decision record and its copy on the ledgers branch are unreadable; nothing will be "
                             "recorded until the file is repaired and the copy can be read again") if DAMAGED else
                            ("its copy on the ledgers branch is unreadable; the hub replaces a damaged published copy "
                             "by hand with a commit to the ledgers branch, and recording resumes once the copy can be "
                             "read"))
        # Amendment 5, reading 3: a decision the file is missing while its copy holds it is restored from the copy,
        # never decided again. A run that may record appends it to the file; any other run prints it from the copy.
        lost = held[~held.decision_id.isin(RECORD.decision_id)] if held is not None else None
        if lost is not None and len(lost) and IS_LIVE and not NOT_RECORDED:
            with record_lock():             # read again under the lock: another run may have written meanwhile
                now_held, now_broken = parse_record(DECISIONS.read_bytes())
                if now_broken:
                    NOT_RECORDED = ("the decision record became unreadable during this run; nothing will be recorded "
                                    "until it is repaired or restored from the ledgers branch")
                else:
                    add = lost[~lost.decision_id.isin(now_held.decision_id)]
                    with open(DECISIONS, "ab") as fh:         # the copy's own lines, byte for byte
                        fh.write(lines_held(copy, set(add.decision_id)))
                    RESTORED, RECORD, lost = set(add.decision_id), pd.concat([now_held, add], ignore_index=True), None
            if RESTORED:
                print(f"Decision record: data/forward/decisions.csv was missing {plural(len(RESTORED))} that its copy "
                      f"on the ledgers branch ({PUBLISHED}) holds ({', '.join(sorted(RESTORED))}); restored from the "
                      "copy. A lost record is never decided again.")
        if lost is not None and len(lost):          # a run that may not record: print them from the copy
            RECORD = pd.concat([RECORD, lost], ignore_index=True)
            FROM_COPY = dict.fromkeys(lost.decision_id, ("the file is damaged" if DAMAGED else "the file is missing it")
                                      + ("; the copy is damaged, and this line of it can still be read"
                                         if copy_broken else ""))
            them = "them" if len(lost) != 1 else "it"
            print(f"Decision record: data/forward/decisions.csv {'is damaged and ' if DAMAGED else ''}doesn't hold "
                  f"{plural(len(lost))} that its copy on the ledgers branch ({PUBLISHED}) holds "
                  f"({', '.join(lost.decision_id)}), printed below as recorded. This run doesn't restore {them} "
                  f"({NOT_RECORDED}); " + (
                      f"a damaged copy is never restored from: restore {them} by hand, from this copy's readable "
                      f"line{'s' if len(lost) != 1 else ''} or a readable copy in the branch's history ({HISTORY}), "
                      f"before the hub replaces the damaged copy by hand, after which the copy no longer holds {them}."
                      if copy_broken else
                      f"{them} will be restored once the file is repaired." if DAMAGED else
                      f"the next run that may record restores {them}."))
    if RECORD is not None and args.now:        # a preview shows only the decisions made by its date
        RECORD = RECORD.loc[np.array([pd.Timestamp(t) <= NOW for t in RECORD.decided_utc], dtype=bool)]


def origin(did):
    """Where a recorded decision was read from, for the line that prints it."""
    return ("; restored from the ledgers branch" if did in RESTORED else
            f"; read from its copy on the ledgers branch ({FROM_COPY[did]})" if did in FROM_COPY else
            "; the file is damaged, and this record can still be read" if DAMAGED else "")


def recorded(did):
    """The decision already written down under this id, or None."""
    if RECORD is None:
        return None
    d = RECORD[RECORD.decision_id.eq(did)]
    return None if d.empty else d.iloc[0]


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
if kick is None:
    print("the schedule has no kickoff times (start_utc or start_date): the check for moved games is off")
if "completed" in S:        # the feed scores a game that was never played 0-0: grade completed games only
    played = S.completed.astype(str).str.lower().isin(["true", "1", "1.0"])
    print(f"schedule rows with a score but not marked completed (not graded): "
          f"{int((~played & s.total.notna()).sum())}")
    s.loc[~played.values, "total"] = np.nan
s = s.drop_duplicates("game_id")
L = L.merge(s[["game_id", "sched_kick"]], on="game_id", how="left")
# Amendment 4, reading 11: "before kickoff" is before the earlier of the row's kickoff and the schedule's
L["kick_first"] = L[["start_utc", "sched_kick"]].min(axis=1)

# What counts. Every excluded row is counted by its first failing reason.
why = np.select([~L.rules_version.isin(REGISTERED_VERSIONS), L.start_utc.isna(), L.start_utc < FIRST_KICK,
                 ~L.season.isin(TEST_SEASONS) | (L.start_utc >= TEST_END), L.snapshot_utc >= L.kick_first],
                ["unregistered rules version", "no kickoff time in the row", "before Oct 1, 2026",
                 "after the 2027 season", "logged at or after kickoff"], "")
print(f"ledger rows: {len(L)}; in the test: {int((why == '').sum())}")
for reason, n in pd.Series(why[why != ""]).value_counts().items():
    print(f"  excluded, {reason}: {n}")
if args.list_excluded and (why != "").any():
    print(L.assign(excluded=why)[why != ""][["snapshot_utc", "game_id", "rules_version", "rule_b", "excluded"]]
          .to_string(index=False))
L = L[why == ""]


def listings(rows):
    """Amendment 4, reading 10: a game's rows grouped by the kickoff on each row. In order of that kickoff, a row
    more than 24 hours after the first kickoff of the current listing starts a new one, so the kickoffs of one
    listing are all within 24 hours of each other. A postponed game that signals again is two listings."""
    rows = rows.sort_values(["game_id", "start_utc", "snapshot_utc"], kind="stable")
    ids, prev, first, n = [], object(), None, 0
    for gid, k in zip(rows.game_id, rows.start_utc):
        if gid != prev:
            prev, first, n = gid, k, 0
        elif k - first > MOVED:
            first, n = k, n + 1
        ids.append(n)
    return rows.assign(listing=ids)


L = listings(L)


def interim(name, when, tests):
    print(f"  decision ({name}): INTERIM read, decides nothing. {when}")
    print("    as the numbers stand: " + "; ".join(f"{k} ({'met' if bool(v) else 'not met'})" for k, v in tests.items()))


def mean_ci(x):
    """Mean +/- 1.96 standard errors: the interval of the secondary CLV (amendment 2), which decides nothing. Rule
    B's registered CLV interval is `interval` below."""
    x = pd.Series(x).dropna()
    if not len(x):
        return np.nan, np.nan, np.nan, 0
    se = x.std(ddof=1) / np.sqrt(len(x)) if len(x) > 1 else np.nan
    return x.mean(), x.mean() - 1.96 * se, x.mean() + 1.96 * se, len(x)


def game_day(bets):
    """Amendment 5, reading 1: each bet's game day, the calendar date of its game's actual kickoff (the
    schedule's; the entry row's when the schedule gives none) in Eastern time."""
    kick = bets.sched_kick.fillna(bets.start_utc)
    return kick.dt.tz_convert("America/New_York").dt.strftime("%Y-%m-%d")


def interval(clv, day):
    """Amendment 5, reading 1: the registered 95% interval of mean CLV, the wider of two. Over the n signals that
    have a CLV (a primary close), m is their plain mean.
      plain half-width    t x s / sqrt(n), s their sample standard deviation, t the 97.5th percentile of Student's t
                          on n - 1 degrees of freedom;
      grouped half-width  t x the grouped standard error, t on G - 1 degrees of freedom: the signals grouped by game
                          day, G days, s_g the sum over day g's signals of (CLV - m), the variance of the mean
                          (G / (G - 1)) x sum(s_g^2) / n^2.
    The registered interval is m plus or minus the larger of the two. With fewer than 2 game days or fewer than 2
    signals there is none (nan bounds). Returns a dict: m, lo, hi, n, G, plain (half-width) and grouped (half-width)."""
    d = pd.DataFrame({"clv": pd.to_numeric(pd.Series(clv).to_numpy(), errors="coerce"),
                      "day": pd.Series(day).to_numpy()}).dropna(subset=["clv"])
    n, G = len(d), int(d.day.nunique(dropna=False))
    m = d.clv.mean() if n else np.nan
    iv = dict(m=m, lo=np.nan, hi=np.nan, n=n, G=G, plain=np.nan, grouped=np.nan)
    if n < 2:
        return iv
    iv["plain"] = stats.t.ppf(0.975, n - 1) * d.clv.std(ddof=1) / np.sqrt(n)
    if G < 2:
        return iv
    s = (d.clv - m).groupby(d.day, dropna=False).sum()
    iv["grouped"] = stats.t.ppf(0.975, G - 1) * np.sqrt(G / (G - 1) * (s ** 2).sum() / n ** 2)
    half = max(iv["plain"], iv["grouped"])
    return iv | dict(lo=m - half, hi=m + half)


def interval_text(m, lo, hi, n, G, plain, grouped):
    """The registered interval, which of the two it is, and both."""
    if n < 2:
        return "no interval on one signal" if n else "no interval"
    if G < 2:
        return "no interval: the signals with a primary close kicked off on 1 game day"
    g, p = f"grouped {m - grouped:+.2f} to {m + grouped:+.2f}", f"plain {m - plain:+.2f} to {m + plain:+.2f}"
    which = (f"the two are equally wide, over {G} game days ({g}; {p})" if np.isclose(grouped, plain, rtol=1e-9) else
             f"the wider is the grouped one, over {G} game days ({g}; {p})" if grouped > plain else
             f"the wider is the plain one ({p}; {g}, over {G} game days)")
    return f"95% CI {lo:+.2f} to {hi:+.2f}; {which}"


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
    """Amendment 4: void (moved more than a day, another listing of the game is the one graded, or no score 30
    days on), pending (no score yet), or settled. One listing per game is graded: the one whose kickoff is nearest
    the game's actual kickoff, the later listing on a tie, and the latest listing when the schedule has no
    kickoff for the game."""
    bets = bets.merge(s[["game_id", "total"]], on="game_id", how="left")
    moved = (bets.sched_kick - bets.start_utc).abs() > MOVED
    dist = (bets.sched_kick - bets.start_utc).abs().fillna(pd.Timedelta(0))
    chosen = bets.assign(_d=dist).sort_values(["_d", "listing"], ascending=[True, False]).drop_duplicates("game_id")
    other = ~bets.index.isin(chosen.index)
    stale = bets.total.isna() & (NOW >= bets.start_utc + NO_RESULT)
    void = np.select([moved, other, stale], [VOID_MOVED, VOID_OTHER, VOID_NO_RESULT], "")
    return bets.assign(void=void, status=np.where(void != "", "void",
                                                  np.where(bets.total.notna(), "settled", "pending")))


def header(bets):
    void = bets[bets.status.eq("void")]
    print(f"{int(bets.status.eq('settled').sum())} settled, {int(bets.status.eq('pending').sum())} pending, "
          f"{len(void)} void (not graded)")
    for reason, v in void.groupby("void", sort=False):
        print(f"  void, {reason}: {len(v)} ({', '.join(v.game_id.astype(str))})")


def fingerprint(positions):
    """Amendment 4, reading 3: sha256 of the ledger's header line and then each row that entered the decision,
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
    the first row after the header: the entry rows, and for Rule B the later quotes used as closes) and their
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


def reprint(rec, show, fresh_verdict, fresh_nums, n_fresh, fresh_text=None):
    """A decision already recorded: print it, and a fresh computation beside it when that now differs."""
    show(rec.verdict, json.loads(rec.numbers))
    print(f"    recorded in decisions.csv on {rec.decided_utc}, horizon {rec.horizon_utc}; "
          f"ledger rows sha256 {rec.ledger_rows_sha256[:16]}" + origin(rec.decision_id))
    check_fingerprint(rec)
    if not n_fresh:
        print("    a fresh computation on the same horizon now has no settled bets. The recorded decision stands.")
    elif fresh_text is not None:           # a record with no numbers but a count: say what the count is now
        if json.dumps(fresh_nums) != json.dumps(json.loads(rec.numbers)):
            print(f"    {fresh_text} The recorded decision stands.")
    elif fresh_verdict != rec.verdict or json.dumps(fresh_nums) != json.dumps(json.loads(rec.numbers)):
        print(f"    a fresh computation on the same horizon now gives: {fresh_verdict}, on {n_fresh} bets:")
        show(fresh_verdict, fresh_nums, fresh=True)
        print("    The recorded decision stands.")


def f(v):
    return None if pd.isna(v) else float(v)


last = L.dropna(subset=["mkt_total"])
quotes = last[is_price(last.mkt_under)]                             # amendment 4: a total with a valid under price
last = quotes.sort_values("snapshot_utc", kind="stable").drop_duplicates(["game_id", "listing"], keep="last")
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
bets = (L[L.rule_b == "SIGNAL"].sort_values("snapshot_utc", kind="stable")
        .drop_duplicates(["game_id", "listing"]))                   # each listing's earliest signal
# Amendment 4: the primary close is the last quote of the same listing logged after the entry row, else the
# captured close
later = quotes.merge(bets[["game_id", "listing", "snapshot_utc"]].rename(columns={"snapshot_utc": "entry_utc"}),
                     on=["game_id", "listing"])
later = (later[later.snapshot_utc > later.entry_utc].sort_values("snapshot_utc", kind="stable")
         .drop_duplicates(["game_id", "listing"], keep="last"))
bets = bets.merge(later[["game_id", "listing", "mkt_total", "snapshot_utc", "line_src", "_row"]].rename(
    columns={"mkt_total": "close_total", "snapshot_utc": "close_utc", "line_src": "close_src", "_row": "close_row"}),
    on=["game_id", "listing"], how="left")
use_cap = bets.close_total.isna() & bets.game_id.map(cap).notna()
bets["close_from"] = np.where(bets.close_total.notna(), "later quote", np.where(use_cap, "captured close", "none"))
bets.loc[use_cap, "close_total"] = bets.game_id.map(cap)[use_cap]
bets["close_src"] = np.where(use_cap, "captured close (" + bets.game_id.map(cap_src).fillna("").astype(str) + ")",
                             bets.close_src.fillna("none").astype(str))
bets = settle(bets)
done = bets[bets.status.eq("settled")].copy()
win, push = done.total < done.mkt_total, done.total == done.mkt_total
done["profit"] = np.where(push, 0, np.where(win, american_to_profit(done.mkt_under), -1.0))
done["clv_pts"] = done.mkt_total - done.close_total
print(f"\nRULE_B: {len(bets)} signals, ", end="")
header(bets)
if len(done):
    iv = interval(done.clv_pts, game_day(done))
    m, lo, n = iv["m"], iv["lo"], iv["n"]
    print(f"  record {int(win.sum())}-{int((~win & ~push).sum())}-{int(push.sum())}, units {done.profit.sum():+.2f} "
          f"(ROI {100 * done.profit.sum() / len(done):+.1f}% per bet placed); mean CLV {m:+.2f}; {n} of {len(done)} "
          f"bets have a primary close; {interval_text(**iv)}")
    src = done.close_from.value_counts()
    stale = int(((done.start_utc - done.close_utc) > pd.Timedelta(hours=6)).sum())
    print(f"  primary close: {src.get('later quote', 0)} from a later logged quote, {src.get('captured close', 0)} "
          f"from the captured close, {src.get('none', 0)} with none (counted, left out of the CLV); {stale} of the "
          f"later quotes were logged more than 6 hours before kickoff")
    secondary(done, "bets")


# The decision (amendment 3, section 4, and amendment 4): after 40 signals or the end of the 2026
# regular season, whichever is later, on the signals that kicked off by then. Later signals never enter it.
def rb_numbers(dec):
    """KEEP or NOT KEPT on the registered test; INCONCLUSIVE with fewer than 20 primary closes (reading 12), or
    with fewer than 2 game days (amendment 5, reading 1). The interval is the wider of the plain one and the one
    grouped by game day; the record keeps both half-widths and the number of game days."""
    iv = interval(dec.clv_pts, game_day(dec))
    m, lo, n, G = iv["m"], iv["lo"], iv["n"], iv["G"]
    nums = dict(n_bets=len(dec), mean_clv=f(m), ci_low=f(lo), ci_high=f(iv["hi"]), n_clv=int(n), game_days=G,
                plain_half_width=f(iv["plain"]), grouped_half_width=f(iv["grouped"]))
    if n < MIN_CLOSES:
        return f"INCONCLUSIVE (only {n} of the {len(dec)} signals have a primary close, fewer than {MIN_CLOSES})", nums
    if G < 2:
        return (f"INCONCLUSIVE (the {n} signals that have a primary close kicked off on 1 game day, so there is no "
                "interval)"), nums
    return ("KEEP" if (m > 0 and lo > 0) else NOT_KEPT), nums


def rb_show(verdict, nums, fresh=False):
    if "horizon" not in nums:              # the test ended with fewer than 40
        print(f"  decision (Rule B), FINAL: {verdict}. The test ended with {nums['n_bets']} settled signals, "
              f"fewer than {ENOUGH}.")
        return
    m, lo, hi, ph, gh = (np.nan if nums[k] is None else nums[k]
                         for k in ("mean_clv", "ci_low", "ci_high", "plain_half_width", "grouped_half_width"))
    lead = ("    " if fresh else
            "  decision (Rule B: after 40 signals or the 2026 regular season, whichever is later), FINAL: ")
    ci = interval_text(m, lo, hi, nums["n_clv"], nums["game_days"], ph, gh)
    print(f"{lead}{verdict}, on the {nums['n_bets']} signals that kicked off by {nums['horizon']}: "
          f"mean CLV {m:+.2f}, n={nums['n_clv']}; {ci}")
    if nums["n_bets"] > nums["n_clv"]:
        print(f"    {nums['n_bets'] - nums['n_clv']} of the {nums['n_bets']} signals have no primary close (left out of "
              "the CLV)")


def label(h):
    return ("2026-12-12, the end of the regular season (Army-Navy)" if h == REG_END_2026
            else f"{h:%Y-%m-%d %H:%M} UTC, the 40th signal's kickoff")


def entered(dec):
    """The ledger rows behind a Rule B decision: each entry, and each later quote used as its close."""
    return list(dec._row) + list(dec.close_row.dropna().astype(int))


rec = recorded(RB_ID)
if len(done) or rec is not None:           # a recorded decision prints even when nothing is settled now
    by_kick = done.sort_values("start_utc")
    pending = bets[bets.status.eq("pending")]
    horizon = max(by_kick.start_utc.iloc[ENOUGH - 1], REG_END_2026) if len(done) >= ENOUGH else None
    if rec is not None:
        h = pd.Timestamp(rec.horizon_utc)
        dec = by_kick[by_kick.start_utc <= h]
        verdict, nums = rb_numbers(dec)
        if "horizon" in json.loads(rec.numbers):
            reprint(rec, rb_show, verdict, nums | {"horizon": label(h)}, len(dec))
        else:                              # recorded at the end of the test with fewer than 40: a fresh count
            reprint(rec, rb_show, rec.verdict, {"n_bets": len(dec)}, len(dec),
                    fresh_text=f"a fresh count on the same horizon now finds {len(dec)} settled signals, not "
                               f"{json.loads(rec.numbers)['n_bets']}.")
    elif horizon is not None and NOW > horizon and not (pending.start_utc <= horizon).any():
        dec = by_kick[by_kick.start_utc <= horizon]
        verdict, nums = rb_numbers(dec)
        nums["horizon"] = label(horizon)
        rb_show(verdict, nums)
        if nums["n_clv"] < MIN_CLOSES:
            print(f"    only {nums['n_clv']} signals have a primary close; a verdict needs at least {MIN_CLOSES} "
                  "(amendment 4, reading 12)")
        elif nums["game_days"] < 2:
            print("    the signals with a primary close kicked off on 1 game day, so there is no interval; a verdict "
                  "needs at least 2 game days (amendment 5, reading 1)")
        write_down(RB_ID, "Rule B", RB_HORIZON, horizon, verdict, nums, entered(dec))
    elif horizon is None and NOW >= TEST_END and not (pending.start_utc < TEST_END).any():
        rb_show("INCONCLUSIVE", {"n_bets": len(done)})
        write_down(RB_ID, "Rule B", RB_HORIZON, TEST_END, "INCONCLUSIVE", {"n_bets": len(done)}, entered(done))
    else:
        waiting = int((pending.start_utc <= horizon).sum()) if horizon is not None else len(pending)
        when = (f"Its horizon has passed: {label(horizon)}. The decision waits for {waiting} pending "
                f"signal{'s' if waiting != 1 else ''}." if horizon is not None and NOW > horizon
                else "The decision comes after 40 signals or the 2026 regular season, whichever is later.")
        interim("Rule B", when, {"mean CLV > 0": m > 0, "95% interval above zero": lo > 0,
                                 f"{ENOUGH} settled signals": len(done) >= ENOUGH,
                                 f"at least {MIN_CLOSES} with a primary close": n >= MIN_CLOSES})
        if len(done) > n:
            print(f"    {len(done) - n} of the {len(done)} settled signals have no primary close (left out of the CLV)")
if len(done):
    print(done[["game_id", "kick_et", "away_team", "home_team", "line_src", "mkt_total", "mkt_under", "close_src",
                "close_total", "total", "clv_pts", "profit"]].to_string(index=False))
    print("  by price source:", done.line_src.value_counts().to_dict())
    print("  close from:", {k: int(v) for k, v in done.close_src.value_counts(sort=False).items()})


# ---------------------------------------------------------------- Rule HT (amendment 1)
ht = last[(last.start_utc >= HT_FIRST_KICK)] if "rule_ht" in last else last.iloc[0:0]
ht = settle(ht[ht.rule_ht == "SIGNAL"]) if len(ht) else ht.assign(status="", void="", total=np.nan)
ht_done = ht[ht.status.eq("settled")].copy()
win, push = ht_done.total < ht_done.mkt_total, ht_done.total == ht_done.mkt_total
ht_done["profit"] = np.where(push, 0, np.where(win, american_to_profit(ht_done.mkt_under), -1.0))
ht_done["result"] = np.where(push, "P", np.where(win, "W", "L"))
print(f"\nRULE_HT: {len(ht)} signals at the last quote before kickoff, ", end="")
header(ht)


def ht_numbers(d):
    if not len(d):
        return None, dict(n_bets=0)
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
if len(ht_done):
    be = np.nan if nums["avg_break_even"] is None else nums["avg_break_even"]
    p = np.nan if nums["p_one_sided"] is None else nums["p_one_sided"]
    w, n = nums["wins"], nums["wins"] + nums["losses"]
    print(f"  record {w}-{n - w}-{nums['pushes']} ({100 * w / max(n, 1):.1f}%), units {nums['units']:+.2f}, "
          f"ROI {100 * nums['roi']:+.1f}% per bet placed; average break-even {100 * be:.1f}%, one-sided p {p:.3f} "
          f"(exact, against each bet's own break-even; pushes are left out of the exact test and count in ROI)")
    secondary(ht_done, "bets")
# The decision (amendments 1, 3 and 4): once, after the 2027 season's title game. "At or below
# break-even" is read at the prices taken: the bets, together, won nothing.
rec = recorded(HT_ID)
if len(ht_done) or rec is not None:        # a recorded decision prints even when nothing is settled now
    ht_pending = ht[ht.status.eq("pending")]
    if rec is not None:
        fresh, fresh_nums = ht_numbers(ht_done[ht_done.start_utc < pd.Timestamp(rec.horizon_utc)])
        reprint(rec, ht_show, fresh, fresh_nums, fresh_nums["n_bets"])
    elif NOW >= TEST_END and not (ht_pending.start_utc < TEST_END).any():
        ht_show(verdict, nums)
        write_down(HT_ID, "Rule HT", HT_HORIZON, TEST_END, verdict, nums, ht_done._row)
    else:
        waiting = int((ht_pending.start_utc < TEST_END).sum())
        when = (f"The title game has passed; the decision waits for {waiting} pending signal"
                f"{'s' if waiting != 1 else ''}." if NOW >= TEST_END else
                "The decision comes once, after the 2027 season's title game (January 2028).")
        interim("Rule HT", when, {"one-sided p < 0.05": p < 0.05, "ROI > 0": nums["roi"] > 0})
if len(ht_done):
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
        e = e.assign(v=e.status.eq("void")).sort_values("v", kind="stable").drop_duplicates("game_id")  # graded listing
        entries = e[["game_id", "mkt_total", "mkt_under"]].rename(
            columns={"mkt_total": "entry_line", "mkt_under": "entry_price"}).assign(rule=rule)
        wc = cost_of_waiting(entries, fills)
        if len(wc):
            print(f"\nCost of waiting, {rule.upper()}: {len(wc)} paper fills; vs the rule's quote the fill gained "
                  f"{wc.pts_gained.mean():+.2f} pts and {wc.profit_gained.mean():+.3f} units of payout per unit staked")
if NOT_RECORDED:
    print(f"\nDecision record: none written by this run: {NOT_RECORDED}.")
else:
    print("\nDecision record: the first final decision is written to " + (
        "data/forward/decisions.csv (the live record)." if IS_LIVE else "decisions.csv beside this test ledger."))
print("Variants under forward test: 2 (RULE_B, RULE_HT).")
