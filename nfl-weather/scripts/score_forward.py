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

The 95% interval of mean CLV (amendment 7, reading 1) is the wider of two, over the n bets with a primary close
and their plain mean m: the plain half-width t(0.975, n - 1) x sd / sqrt(n), and the grouped half-width
t(0.975, G - 1) x sqrt((G / (G - 1)) x sum over days of (sum of that day's CLV - m)^2 / n^2), the bets grouped by
the Eastern calendar date of their game's actual kickoff (G days). The interval is m plus or minus the larger.
With fewer than 2 game days (or 2 bets) there is no interval and the decision is INCONCLUSIVE. The scorer prints
which of the two is the wider, and both; the record keeps the interval, both half-widths and G.

Who writes a decision down (amendment 6, section 3): a run on the live ledger (data/forward/ledger.csv),
on the real clock, reading the default schedule refreshed in the last 2 days, writes
data/forward/decisions.csv. The scorer is live only when its data/forward folder, with links resolved, is
inside its own project folder. A run with --now is a preview: it records nothing, and shows a recorded
decision only if it was made by the preview's date. A run on another ledger kept in data/forward/ (the
rewrite's backup copy) neither reads nor writes a record. A copy of this scorer in another folder (a
worker's worktree) reads the live record but never writes it. A test ledger kept anywhere else writes
decisions.csv beside itself (a --now run on it only with --test-record, which exists for tests). A lost
live record is restored from its copy on the ledgers branch, never decided again: while the file is
missing, every run on the live ledger reads the copy, a real run restores the file from it, and any other
run prints the copy's decisions as recorded. A copy that is there but damaged stops recording, as a
damaged file does. One run at a time writes, under a file lock, and a damaged record (a half-written
line, a line without its 10 fields, numbers a later run can't print, a time with no time zone) stops
recording without stopping the scores.

Amendment 7, reading 3: in a damaged record, every decision whose line can still be read on its own is
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

Each bet is graded at its ENTRY line and ENTRY price (profit in units, pushes return the stake), with
closing-line value against the final nflverse total. Amendment 3 adds a secondary CLV against
Pinnacle's total captured just before kickoff (data/forward/closes.csv). Amendment 8, section 1: a bet
uses a captured close only when it was captured 2 to 20 minutes (both inclusive, amendment 3's window as
scripts/capture_close.py applies it) before the kickoff of the listing graded, the earlier of the kickoff
on the listing's last row logged before kickoff and the kickoff in the schedule; among such captures of
the game, the last in the file is taken. A game with a captured close outside that window has none for
this listing: it is counted as missing, the scorer prints how many and which, and --list-excluded prints
each refused capture. A capture of the game outside the window when another inside it is used is set
aside: the scorer says how many when there are any, and --list-excluded prints each. The test's end is
judged on the schedule's kickoff and season, as before (amendment 8, section 2). ROI is units won per
bet placed; a push counts as a bet. Wind triggers that never became a signal (no price, price too high,
outside the horizon) are counted, so coverage gaps can't quietly select winners.

    python scripts/fetch_data.py --skip-weather   # refresh schedule/lines/results
    python scripts/score_forward.py [--list-excluded]
    python scripts/score_forward.py --now 2026-10-20T17:00:00 --json   # the dashboard's read: one JSON document

--json prints one JSON document and nothing else: the report above as text, byte for byte, and each test's counts,
numbers, decision and bets, each number the one the report prints. It changes nothing about what is graded, decided
or recorded; with --now it is a preview, and records nothing.
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
ap.add_argument("--json", action="store_true",
                help="print one JSON document instead of the report: the report itself as text, and each test's "
                     "counts, numbers, decision and bets. What is graded, decided and recorded doesn't change")
args = ap.parse_args()
# --json: the report is printed into a buffer, exactly as it would be printed, and handed over inside one document
# at the end (json_document). Nothing else about the run changes: the same rows count, the same bets are graded, and
# a decision is recorded, or not, by the same rules.
REPORT = io.StringIO() if args.json else None
if REPORT is not None:
    STDOUT, sys.stdout = sys.stdout, REPORT
JSON = {"excluded": {}, "rows": {}, "tests": {}, "decisions": {}, "written": {}}    # filled as the report prints
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
# What a recorded decision must hold for a later run to print it: its counts, its numbers (null when there is
# none, as for an interval on one bet) and how its bets were split. Amendment 7: ci_low and ci_high are the
# registered interval, the mean plus or minus the wider of plain_half_width and grouped_half_width (the latter over
# game_days game days). No decision has been recorded yet, so no record without these keys exists.
COUNTS = ("n_bets", "n_clv", "beat_close", "vs_close_no_tie", "ties", "game_days")
NUMBERS = ("mean_clv", "ci_low", "ci_high", "plain_half_width", "grouped_half_width", "win_rate_vs_close")


def is_number(v, none_ok=False):
    return (v is None and none_ok) or (isinstance(v, (int, float)) and not isinstance(v, bool))


def check_row(r):
    """One recorded decision, or ValueError saying what is damaged in it."""
    if r.decision_id not in DECISION_ID.values():
        raise ValueError(f"an unknown decision id {r.decision_id!r}")
    for t in (r.horizon_utc, r.decided_utc):
        if pd.isna(pd.Timestamp(t)):
            raise ValueError(f"a blank time ({t!r})")
        if pd.Timestamp(t).tzinfo is None:              # amendment 7, reading 3: it can't be read as a UTC time
            raise ValueError(f"a time with no time zone ({t!r}), which can't be read as a UTC time")
    int(r.n_bets)
    if not (r.verdict in ("KEEP", "DROP") or r.verdict.startswith("INCONCLUSIVE")):
        raise ValueError(f"an unknown verdict {r.verdict!r}")
    nums = json.loads(r.numbers)
    if not isinstance(nums, dict):
        raise ValueError(f"{r.decision_id}'s numbers are not a set of named numbers")
    missing = [k for k in COUNTS + NUMBERS + ("split", "by_part") if k not in nums]
    if missing:
        raise ValueError(f"{r.decision_id}'s numbers have no {', '.join(missing)}")
    bad = ([k for k in COUNTS if not is_number(nums[k])] + [k for k in NUMBERS if not is_number(nums[k], True)]
           + ([] if nums["split"] in ("half", "season") else ["split"])
           + ([] if isinstance(nums["by_part"], dict) and all(map(is_number, nums["by_part"].values()))
              else ["by_part"]))
    if bad:
        raise ValueError(f"{r.decision_id}'s numbers have a damaged {', '.join(bad)}")
    [int(p) for p in r.ledger_rows.split()]
    if not re.fullmatch(r"[0-9a-f]{64}", r.ledger_rows_sha256):
        raise ValueError(f"{r.decision_id}'s fingerprint is not 64 hexadecimal characters")


def record_lines(data):
    """Amendment 7, reading 3: a record's lines, as bytes without their line breaks, in order. A blank line, or a line
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
    """Amendment 7, reading 3: the decisions in a damaged record that can still be read. Each line is taken on
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
    """Amendment 7, reading 3: a readable copy's own record lines for these decision ids, byte for byte and in the
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
        # Amendment 6, section 3: a copy that can't be read stops recording, as a damaged file does, whether or not
        # the file is there. Amendment 7, reading 3: each decision on a line of it that can still be read is held,
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
            # Amendment 7, reading 3: the decisions that can still be read are printed as recorded, never as a
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
            # Amendment 6, section 3, and amendment 7, reading 3: the file is there, but its copy can't be read, so
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
        # Amendment 7, reading 3: a decision the file is missing while its copy holds it is restored from the copy,
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
# Amendment 3: the Pinnacle close captured just before kickoff (scripts/capture_close.py), secondary only. Amendment
# 8, section 1: a capture is a listing's close only when it was captured inside that window before the listing's
# kickoff (with_captured, below).
CAP_WINDOW = (pd.Timedelta(minutes=2), pd.Timedelta(minutes=20))   # amendment 3; capture_close.py's WINDOW, inclusive
CAP_REFUSED = "close captured outside the window for this listing (2 to 20 minutes before its kickoff)"
CAP_ASIDE = "capture set aside: outside the window for this listing; another capture inside it is used"
closes = ledger.parent / "closes.csv"
cap = pd.read_csv(closes, dtype={"game_id": str}) if closes.exists() else pd.DataFrame(
    columns=["game_id", "kick_utc", "capture_utc", "book", "close_total"])
cap = cap.reindex(columns=list(dict.fromkeys(["game_id", "kick_utc", "capture_utc", "book", "close_total"]
                                             + list(cap.columns))))
cap = cap.assign(_order=np.arange(len(cap)))                       # file order: the last is taken
cap = cap[cap.book.eq("pinnacle")].dropna(subset=["close_total"])
cap["close_total"] = pd.to_numeric(cap.close_total, errors="coerce")
cap["cap_utc"] = pd.to_datetime(cap.capture_utc.astype(object), utc=True, errors="coerce", format="mixed")

# What counts. Every excluded row is counted by its first failing reason.
why = np.select([~L.rules_version.isin(REGISTERED_VERSIONS), ~L.in_schedule, L.kick_utc.isna(),
                 L.kick_utc < FIRST_KICK, ~L.season.isin(TEST_SEASONS), L.snapshot_utc >= L.kick_first],
                ["unregistered rules version", "game not in the schedule", "no kickoff time in the schedule",
                 "before Week 5 (Oct 8, 2026)", "after the 2027 season", "logged at or after kickoff"], "")
print(f"ledger rows: {len(L)}; in the test: {int((why == '').sum())}")
JSON["rows"] = {"ledger": len(L), "in_test": int((why == "").sum())}
for reason, n in pd.Series(why[why != ""]).value_counts().items():
    print(f"  excluded, {reason}: {n}")
    JSON["excluded"][reason] = int(n)
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
# Amendment 8, section 1: the kickoff of each listing, for its captured close: the `kick_first` (the earlier of the
# row's kickoff and the schedule's) of the listing's last row logged before kickoff. Every row left in L was logged
# before its own `kick_first` (`why`, above), so that row was logged before the schedule's kickoff, and the bound is
# never later than it.
LISTING_KICK = (L.sort_values(["snapshot_utc", "_row"], kind="stable")
                .drop_duplicates(["game_id", "listing"], keep="last").set_index(["game_id", "listing"]).kick_first)


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


def with_captured(b):
    """Amendment 8, section 1: each bet's captured Pinnacle close, from its own listing. A capture counts only when
    its capture time is 2 to 20 minutes (both inclusive) before the kickoff of the bet's listing (LISTING_KICK: the
    earlier of the kickoff on the listing's last row logged before kickoff and the schedule's; amendment 6, reading
    10); among those, the last in closes.csv is taken. Adds cap_kick (that kickoff) and cap_close (blank when none);
    cap_refused: the game has a captured Pinnacle close, but none in that window for this listing, so this bet has
    none (counted as missing); and cap_aside: how many of the game's Pinnacle captures outside the window were set
    aside when one inside it is used."""
    b = b.assign(cap_kick=LISTING_KICK.reindex(pd.MultiIndex.from_frame(b[["game_id", "listing"]])).set_axis(b.index))
    k = b[["game_id", "cap_kick"]].rename_axis("_b").reset_index()
    m = k.merge(cap[["game_id", "cap_utc", "close_total", "_order"]], on="game_id")
    lead = m.cap_kick - m.cap_utc
    inside = (lead >= CAP_WINDOW[0]) & (lead <= CAP_WINDOW[1])
    aside = (~inside).groupby(m._b).sum()
    m = m[inside].sort_values("_order", kind="stable").drop_duplicates("_b", keep="last").set_index("_b")
    out = b.assign(cap_close=m.close_total.reindex(b.index).astype(float))
    return out.assign(cap_refused=out.cap_close.isna() & out.game_id.isin(cap.game_id),
                      cap_aside=np.where(out.cap_close.notna(), aside.reindex(b.index).fillna(0), 0).astype(int))


def outside(r, label):
    """The Pinnacle captures of these bets' games outside the window for their listing, one line each
    (--list-excluded)."""
    c = r[["game_id", "row_kick", "cap_kick"]].merge(cap, on="game_id")
    lead = c.cap_kick - c.cap_utc
    c = c[~((lead >= CAP_WINDOW[0]) & (lead <= CAP_WINDOW[1]))]
    print(c.assign(excluded=label).rename(columns={
        "row_kick": "row_kickoff", "cap_kick": "listing_kickoff", "kick_utc": "captured_for"})[
        ["game_id", "row_kickoff", "listing_kickoff", "capture_utc", "captured_for", "close_total", "excluded"]]
        .to_string(index=False))


def grade(bets, side_col):
    """Outcome at the entry line and price."""
    bets = with_captured(bets)
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
    """Mean +/- 1.96 standard errors: the interval of the secondary CLV (amendment 3), which decides nothing. The
    registered CLV interval is `interval` below."""
    x = pd.Series(x).dropna()
    if not len(x):
        return np.nan, np.nan, np.nan, 0
    se = x.std(ddof=1) / np.sqrt(len(x)) if len(x) > 1 else np.nan
    return x.mean(), x.mean() - 1.96 * se, x.mean() + 1.96 * se, len(x)


def game_day(bets):
    """Amendment 7, reading 1: each bet's game day, the calendar date of its game's actual kickoff (the schedule's)
    in Eastern time."""
    kick = bets.kick_utc.fillna(bets.row_kick)
    return kick.dt.tz_convert("America/New_York").dt.strftime("%Y-%m-%d")


def interval(clv, day):
    """Amendment 7, reading 1: the registered 95% interval of mean CLV, the wider of two. Over the n bets that have a
    CLV (a primary close), m is their plain mean.
      plain half-width    t x s / sqrt(n), s their sample standard deviation, t the 97.5th percentile of Student's t
                          on n - 1 degrees of freedom;
      grouped half-width  t x the grouped standard error, t on G - 1 degrees of freedom: the bets grouped by game
                          day, G days, s_g the sum over day g's bets of (CLV - m), the variance of the mean
                          (G / (G - 1)) x sum(s_g^2) / n^2.
    The registered interval is m plus or minus the larger of the two. With fewer than 2 game days or fewer than 2 bets
    there is none (nan bounds). Returns a dict: m, lo, hi, n, G, plain (half-width) and grouped (half-width)."""
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
        return "no interval on one bet" if n else "no interval"
    if G < 2:
        return "no interval: the bets with a primary close kicked off on 1 game day"
    g, p = f"grouped {m - grouped:+.2f} to {m + grouped:+.2f}", f"plain {m - plain:+.2f} to {m + plain:+.2f}"
    which = (f"the two are equally wide, over {G} game days ({g}; {p})" if np.isclose(grouped, plain, rtol=1e-9) else
             f"the wider is the grouped one, over {G} game days ({g}; {p})" if grouped > plain else
             f"the wider is the plain one ({p}; {g}, over {G} game days)")
    return f"95% CI {lo:+.2f} to {hi:+.2f}; {which}"


def report(name, bets):
    settled = bets[bets.status.eq("settled")]
    n_pend, void = int(bets.status.eq("pending").sum()), bets[bets.status.eq("void")]
    print(f"\n{name}: {len(bets)} signals, {len(settled)} settled, {n_pend} pending, {len(void)} void (not graded)")
    for reason, v in void.groupby("void", sort=False):
        print(f"  void, {reason}: {len(v)} ({', '.join(v.game_id.astype(str))})")
    JSON["tests"][name] = {"bets": bets}                  # --json: the numbers this table prints, as it prints them
    if settled.empty:
        return settled
    w, p = int(settled.win.sum()), int(settled.push.sum())
    iv = interval(settled.clv_pts, game_day(settled))
    JSON["tests"][name] |= {"won": w, "pushed": p, "iv": iv}
    print(f"  record at entry line {w}-{len(settled) - w - p}-{p}   units {settled.profit.sum():+.2f} "
          f"(ROI {100 * settled.profit.sum() / len(settled):+.1f}% per bet placed; "
          f"{int((~settled.priced).sum())} graded at an assumed -110)")
    print(f"  mean CLV {iv['m']:+.2f} pts; {int(settled.close_total.notna().sum())} of {len(settled)} bets have a "
          f"primary close; {interval_text(**iv)}")
    cm, clo, chi, cn = mean_ci(settled.clv_cap)
    JSON["tests"][name]["secondary"] = (cm, clo, chi, cn)
    if cn:
        print(f"  secondary (amendment 3): mean CLV vs captured Pinnacle close {cm:+.2f} pts "
              f"(95% CI {clo:+.2f} to {chi:+.2f}); {len(settled) - cn} of {len(settled)} without a captured close")
    else:
        print(f"  secondary (amendment 3): no captured closes for these {len(settled)} bets")
    r = settled[settled.cap_refused]              # amendment 8, section 1: counted and named, never dropped
    if len(r):
        print(f"  captured Pinnacle close refused for {len(r)} of these {len(settled)} bets: {CAP_REFUSED}; counted "
              f"as missing ({', '.join(r.game_id.astype(str))})")
        if args.list_excluded:
            outside(r, CAP_REFUSED)
    a = settled[settled.cap_aside > 0]            # outside the window, while another capture inside it is used
    if len(a):
        print(f"  Pinnacle captures set aside for {len(a)} of these {len(settled)} bets: {int(a.cap_aside.sum())} "
              f"outside the window for the listing, while another inside it is used "
              f"({', '.join(a.game_id.astype(str))})")
        if args.list_excluded:
            outside(a, CAP_ASIDE)
    print(settled[["game_id", "side", "line_src", "total_line", "close_total", "total", "clv_pts", "profit"]]
          .to_string(index=False))
    return settled


# ---------------------------------------------------------------- the decisions
def assess(bets, split, split_name, final_label, enough=True):
    """The registered keep/drop test on `bets`, as numbers and a verdict. `split` labels each bet's half
    (or season); CLV must be positive in every part. Keep and drop both met is a DROP. With fewer than 20
    bets that have a primary close the result is inconclusive (amendment 6, reading 11). The interval is the wider
    of the plain one and the one grouped by game day, and with fewer than 2 game days there is none and the result
    is inconclusive (amendment 7, reading 1); the record keeps both half-widths and the number of game days."""
    iv = interval(bets.clv_pts, game_day(bets))
    n, G = iv["n"], iv["G"]
    has = bets.close_total.notna()
    graded = bets[has & ~bets.tie_close]                           # no close, or a tie with it: left out
    rate = graded.beat_close.mean() if len(graded) else np.nan
    parts = bets.assign(part=split).groupby("part").clv_pts.mean()
    f = lambda v: None if pd.isna(v) else float(v)                # noqa: E731
    nums = dict(n_bets=len(bets), mean_clv=f(iv["m"]), ci_low=f(iv["lo"]), ci_high=f(iv["hi"]), n_clv=int(n),
                win_rate_vs_close=f(rate), beat_close=int(graded.beat_close.sum()), vs_close_no_tie=len(graded),
                ties=int((has & bets.tie_close).sum()), split=split_name,
                by_part={str(k): float(v) for k, v in parts.items()}, game_days=G,
                plain_half_width=f(iv["plain"]), grouped_half_width=f(iv["grouped"]))
    keep, drop = criteria(nums)
    head, tail = final_label[0].split(" (", 1)
    verdict = (final_label[1] if not enough else
               f"{head} (only {n} of the {len(bets)} bets have a primary close, fewer than {MIN_CLOSES}; {tail}"
               if n < MIN_CLOSES else
               f"{head} (the {n} bets that have a primary close kicked off on 1 game day, so there is no interval; "
               f"{tail}" if G < 2 else
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
    m, lo, hi, n, rate, ph, gh = (np.nan if nums[k] is None else nums[k] for k in (
        "mean_clv", "ci_low", "ci_high", "n_clv", "win_rate_vs_close", "plain_half_width", "grouped_half_width"))
    keep, drop = criteria(nums)
    ci = interval_text(m, lo, hi, n, nums["game_days"], ph, gh)
    print(f"    mean CLV {m:+.2f}, n={n}; {ci}")
    print(f"    win rate vs the close {100 * rate:.1f}% ({nums['beat_close']} of the {nums['vs_close_no_tie']} bets "
          f"that have a primary close and didn't tie it; {nums['ties']} ties left out); mean CLV by "
          f"{nums['split']}: { {k: round(v, 2) for k, v in nums['by_part'].items()} }")
    if nums["n_bets"] > n:
        print(f"    {nums['n_bets'] - n} of the {nums['n_bets']} bets have no primary close (left out of the CLV and "
              "the win rate)")
    if n < MIN_CLOSES:
        print(f"    only {n} bets have a primary close; a verdict needs at least {MIN_CLOSES} (amendment 6, reading 11)")
    elif nums["game_days"] < 2:
        print("    the bets with a primary close kicked off on 1 game day, so there is no interval; a verdict needs at "
              "least 2 game days (amendment 7, reading 1)")
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
    JSON["written"][did] = False
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
    JSON["written"][did] = True
    print(f"    recorded in decisions.csv on {rec['decided_utc']}, horizon {rec['horizon_utc']}; "
          f"ledger rows sha256 {rec['ledger_rows_sha256'][:16]}")


def json_mark():
    """--json: where the report has got to, so a decision's own lines can be handed over as printed."""
    return REPORT.tell() if REPORT is not None else 0


def json_decision(rule, did, name, status, verdict, start, rec=None):
    """--json: one decision as printed: interim, final (and whether this run wrote it down) or recorded."""
    if REPORT is None:
        return
    d = {"id": did, "name": name, "status": status, "verdict": verdict, "text": REPORT.getvalue()[start:]}
    if rec is not None:
        # a recorded number that is NaN or infinite (json.dumps writes it; JSON has no such value) is null here
        numbers = json.loads(rec.numbers, parse_constant=lambda _: None)
        d["recorded"] = {"verdict": rec.verdict, "decided_utc": rec.decided_utc, "horizon_utc": rec.horizon_utc,
                         "n_bets": int(rec.n_bets), "numbers": numbers, "from": origin(did)[2:] or None}
    if status == "final":
        d["written"] = JSON["written"].get(did, False)
    JSON["decisions"].setdefault(rule, []).append(d)


def decision(did, rule, horizon, name, h_utc, bets_by, split_by, split_name, pending, when, labels,
             enough=lambda b: True):
    """One registered decision. Prints the recorded one if it exists (and a fresh computation on the same
    horizon beside it when that now differs); otherwise FINAL, written down by a run that may record, once
    the horizon has passed and no bet that kicked off by then is pending; otherwise an interim read.
    Returns the verdict or None."""
    start = json_mark()
    rec = recorded(did)
    if rec is not None:
        h = pd.Timestamp(rec.horizon_utc)
        bets = bets_by(h)
        fresh, nums = assess(bets, split_by(bets), split_name, labels, enough(bets))
        print(f"  decision ({name}), FINAL: {rec.verdict}")
        show(json.loads(rec.numbers))
        print(f"    recorded in decisions.csv on {rec.decided_utc}, horizon {rec.horizon_utc}; "
              f"ledger rows sha256 {rec.ledger_rows_sha256[:16]}" + origin(did))
        check_fingerprint(rec)
        if not len(bets):
            print("    a fresh computation on the same horizon now has no settled bets. The recorded decision stands.")
        elif fresh != rec.verdict or json.dumps(nums) != json.dumps(json.loads(rec.numbers)):
            print(f"    a fresh computation on the same horizon now gives: {fresh}, on {len(bets)} bets:")
            show(nums)
            print("    The recorded decision stands.")
        json_decision(rule, did, name, "recorded", rec.verdict, start, rec)
        return rec.verdict
    bets = bets_by(h_utc)
    verdict, nums = assess(bets, split_by(bets), split_name, labels, enough(bets))
    waiting = 0 if h_utc is None else int((pending.kick_utc <= h_utc).sum())
    if h_utc is not None and NOW > h_utc and not waiting:
        print(f"  decision ({name}), FINAL: {verdict}")
        show(nums)
        write_down(did, rule, horizon, h_utc, verdict, nums, bets._row)
        json_decision(rule, did, name, "final", verdict, start)
        return verdict
    print(f"  decision ({name}): INTERIM read, decides nothing. {when(waiting)}")
    show(nums)
    json_decision(rule, did, name, "interim", None, start)
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
      "with a primary close, and the first final one is written down. Its 95% interval of mean CLV is the wider of "
      "the plain one and the one grouped by game day, and it needs at least 2 game days (amendment 7).")
if NOT_RECORDED:
    print(f"Decision record: none written by this run: {NOT_RECORDED}.")
else:
    print("Decision record: the first final decision is written to " + (
        "data/forward/decisions.csv (the live record)." if IS_LIVE else "decisions.csv beside this test ledger."))
print("Variants under forward test: 2 (MODEL_LEAN, RULE_B).")


# ---------------------------------------------------------------- --json: the same report, machine-readable
# Every number below is one the report above printed (or, for a single bet, one its table printed), taken from the
# same variables; nothing is graded or decided here. A number that doesn't exist (no interval on one bet) is null.
def json_num(v):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    return v if np.isfinite(v) else None


def json_time(t):
    return None if t is None or pd.isna(t) else pd.Timestamp(t).tz_convert("UTC").strftime("%Y-%m-%dT%H:%M:%SZ")


def json_text(v):
    return None if v is None or (isinstance(v, float) and np.isnan(v)) or str(v) == "" else str(v)


def json_bet(b):
    """One bet: its game, its entry row (line, price and where the price came from), its close, its outcome and the
    units at the price taken. The close, the closing-line value, the final total and the units are given once the bet
    is settled, as the report's table gives them."""
    settled, under = b["status"] == "settled", b["side"] == "UNDER"
    outcome = (b["status"] if b["status"] in ("pending", "void") else
               "push" if b["push"] else "won" if b["win"] else "lost")
    kick = b["kick_utc"] if pd.notna(b["kick_utc"]) else b["row_kick"]
    has_close = settled and pd.notna(b["close_total"])
    return {"game_id": str(b["game_id"]), "away_team": json_text(b.get("away_team")),
            "home_team": json_text(b.get("home_team")), "kickoff_utc": json_time(kick),
            "entry_row_kickoff_utc": json_time(b["row_kick"]), "side": b["side"],
            "logged_utc": json_time(b["snapshot_utc"]), "entry_line": json_num(b["total_line"]),
            "entry_price": json_num(b["under_odds"] if under else b["over_odds"]),
            "price_assumed": not bool(b["priced"]), "price_source": json_text(b["line_src"]),
            "close_line": json_num(b["close_total"]) if has_close else None,
            "close_source": "nflverse schedule" if has_close else None,
            "clv": json_num(b["clv_pts"]) if settled else None,
            "captured_close": json_num(b["cap_close"]) if settled else None,
            "clv_captured": json_num(b["clv_cap"]) if settled else None,
            "final_total": json_num(b["total"]) if settled else None, "outcome": outcome,
            "void_reason": json_text(b["void"]), "units": json_num(b["profit"]) if settled else None,
            "ledger_row": int(b["_row"]) + 1, "listing": int(b["listing"])}


def json_test(tid, name, printed, rule, decides):
    """One test as its table printed it: counts, record, units, return per bet placed, mean CLV, the registered
    interval (both half-widths and the game days), the secondary CLV, the decision as printed, and its bets."""
    t = JSON["tests"].get(printed, {})
    bets = t.get("bets", pd.DataFrame(columns=["status", "void"]))
    settled = bets[bets.status.eq("settled")]
    void = bets[bets.status.eq("void")]
    out = {"id": tid, "name": name, "printed_as": printed, "decides": decides,
           "counts": {"signals": len(bets), "settled": len(settled), "pending": int(bets.status.eq("pending").sum()),
                      "void": len(void)},
           "void_reasons": {str(k): len(v) for k, v in void.groupby("void", sort=False)},
           "record": None, "units": None, "roi_percent": None, "graded_at_assumed_price": None, "mean_clv": None,
           "n_clv": None, "interval": None, "secondary_clv": None,
           "decisions": JSON["decisions"].get(rule, []) if rule else [],
           "bets": [json_bet(b) for b in bets.sort_values("snapshot_utc", kind="stable").to_dict("records")]
           if len(bets) else []}
    if "iv" in t:
        w, p, iv = t["won"], t["pushed"], t["iv"]
        units = settled.profit.sum()
        cm, clo, chi, cn = t["secondary"]
        out |= {"record": {"won": w, "lost": len(settled) - w - p, "pushed": p}, "units": json_num(units),
                "roi_percent": json_num(100 * units / len(settled)),
                "graded_at_assumed_price": int((~settled.priced).sum()),
                "mean_clv": json_num(iv["m"]), "n_clv": int(settled.close_total.notna().sum()),
                "interval": {"low": json_num(iv["lo"]), "high": json_num(iv["hi"]), "n": int(iv["n"]),
                             "game_days": int(iv["G"]), "plain_half_width": json_num(iv["plain"]),
                             "grouped_half_width": json_num(iv["grouped"])},
                "secondary_clv": {"mean": json_num(cm), "low": json_num(clo), "high": json_num(chi), "n": int(cn),
                                  "without": len(settled) - int(cn)}}
    return out


def json_document():
    return {"scorer": ROOT.name, "generated_utc": json_time(CLOCK), "now": json_time(NOW), "preview": bool(args.now),
            "ledger": str(ledger), "text": REPORT.getvalue(), "rows": JSON["rows"], "excluded": JSON["excluded"],
            "decision_record": {"written_by_this_run": any(JSON["written"].values()),
                                "why_not": NOT_RECORDED or None},
            "tests": [json_test("RULE_B", "Rule B, wind under, at the registered price (Pinnacle)",
                                "RULE_B (wind under)", "Rule B", True),
                      json_test("RULE_B_SECONDARY", "Rule B, wind under, at the backup price (not part of the decision)",
                                "RULE_B, secondary price (not part of the decision)", None, False),
                      json_test("MODEL_LEAN", "Model lean", "MODEL_LEAN", "model lean", True)]}


if REPORT is not None:
    sys.stdout = STDOUT
    print(json.dumps(json_document(), allow_nan=False, default=lambda o: o.item() if hasattr(o, "item") else str(o)))
