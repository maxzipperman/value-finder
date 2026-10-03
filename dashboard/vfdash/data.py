"""Everything the dashboard reads, gathered into one snapshot that is rebuilt at most every 30 seconds.
Scorer previews are kept for 10 minutes. Reading never changes a file; see readers.py and commands.py."""
from __future__ import annotations

import json
import re
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone, tzinfo
from pathlib import Path

from . import commands, words
from .ledger import FUTURE_SLACK, Ledger
from .readers import AppendOnlyCSV, Read, read_csv, read_json, read_plist, read_text

UTC = timezone.utc
SNAPSHOT_SECONDS = 30
SCORER_SECONDS = 600
PROJECTS = commands.PROJECTS
SPORT_OF = {"nfl-weather": "NFL", "cfb-weather": "CFB"}                   # a short tag, as on the board
SPORT_IN_WORDS = {"nfl-weather": "NFL", "cfb-weather": "college football"}  # the sport in a sentence
QUOTA_FIELDS = ("utc", "remaining", "used", "last", "project", "status")     # never the key's fingerprint
DEFAULT_RUN_TIMES = [(7, 30), (11, 30), (15, 30), (19, 30)]
JOBS = [
    {"label": "com.nflweather.alerts", "name": "NFL alerts", "in_a_sentence": "NFL alerts", "project": "nfl-weather"},
    {"label": "com.cfbweather.alerts", "name": "College football alerts", "in_a_sentence": "college football alerts",
     "project": "cfb-weather"},
    {"label": "com.valuefinder.closecapture", "name": "Close capture", "in_a_sentence": "close capture",
     "log": "valuefinder-closecapture.log"},
    {"label": "com.valuefinder.ledgersync", "name": "Nightly ledger copy", "in_a_sentence": "nightly ledger copy",
     "log": "valuefinder-ledgersync.log"},
    {"label": "com.valuefinder.triggerpoll", "name": "Wind-trigger price collector", "in_a_sentence": "trigger collector", "log": "valuefinder-triggerpoll.log", "collector": True},
    {"label": "com.valuefinder.propslog", "name": "NFL props collector", "in_a_sentence": "props collector", "log": "valuefinder-propslog.log", "collector": True},
    {"label": "com.valuefinder.nbacollector", "name": "NBA collector", "in_a_sentence": "NBA collector", "log": "valuefinder-nbacollector.log", "collector": True},
]
MANIFEST = Path("sharp-markets") / "data" / "raw" / "_manifest" / "oddsapi_manifest.csv"


@dataclass
class Config:
    root: Path                      # the repo checkout to read (or a copy laid out like it)
    scorer_root: Path               # where the scorers and their Pythons live (default: root)
    home: Path                      # for ~/Library/LaunchAgents, ~/Library/Logs and ~/.cache/value-finder
    content: Path                   # dashboard/content
    tz: tzinfo
    port: int = 8787
    operations_root: Path | None = None

    @property
    def quota_file(self) -> Path:
        return self.home / ".cache" / "value-finder" / "odds_quota.json"

    def plist(self, label: str) -> Path:
        return self.home / "Library" / "LaunchAgents" / f"{label}.plist"

    def log(self, name: str) -> Path:
        return self.home / "Library" / "Logs" / name

    def forward(self, project: str) -> Path:
        return self.root / project / "data" / "forward"


def label(project: str, what: str, name: str) -> str:
    return f"the {SPORT_IN_WORDS.get(project, project)} {what} ({project}/data/forward/{name})"


def read_runs(path: Path, what: str, now: datetime | None = None, tz: tzinfo = UTC) -> Read:
    """An alert job's runs.csv. Without its run_utc and status columns it can't be read (a damaged or foreign
    file, not an empty record); a row whose run time can't be read is left out and counted. With `now`, a row
    logged later than now is left out until its time comes (it would hide a job that stopped), counted and named;
    `future` on the result says how many."""
    r = read_csv(path, what)
    if r.data is None:
        return r
    header, rows = r.data
    missing = [c for c in RUNS_REQUIRED if c not in header]
    if missing:
        return Read(note=f"{cap(what)} {words.missing_columns(missing)}, so it can't be read.", mtime=r.mtime)
    timed = [row for row in rows if words.parse_utc(row.get("run_utc")) is not None]
    if rows and not timed:
        return Read(note=f"No row of {what} has a run time (run_utc) that can be read, so the dashboard can't "
                         "tell when that job last ran.", mtime=r.mtime)
    notes = [r.note] if r.note else []
    if len(timed) < len(rows):
        n = len(rows) - len(timed)
        notes.append(f"{words.count(n, 'row')} of {what} {'has' if n == 1 else 'have'} a run time (run_utc) that "
                     f"can't be read; {'it is' if n == 1 else 'they are'} left out.")
    later = sorted(t for t in (words.parse_utc(row.get("run_utc")) for row in timed)
                   if now is not None and t > now + FUTURE_SLACK)
    if later:
        timed = [row for row in timed if words.parse_utc(row.get("run_utc")) <= now + FUTURE_SLACK]
        n = len(later)
        named = "; ".join(words.when_full(t, tz) for t in later[:3]) + (f"; and {n - 3:,} more" if n > 3 else "")
        notes.append(f"{words.count(n, 'row')} of {what} {'is' if n == 1 else 'are'} logged later than now: {named}. "
                     f"{'It is' if n == 1 else 'They are'} left out until then.")
    return Read(data=(header, timed), note=" ".join(notes), mtime=r.mtime, future=len(later))


@dataclass
class Launchctl:
    listed: dict | None = None      # label -> {"pid": int|None, "status": int|None}; None when unreadable
    printed: dict = field(default_factory=dict)   # label -> {"state", "runs", "last exit code"}
    note: str = ""


@dataclass
class Scored:
    project: str
    status: str                     # ok, failed, timed_out, missing, skipped, waiting, not_document
    text: str = ""                  # the printed report: the document's "text" (or what a failed run printed)
    error: str = ""
    ran_at: datetime | None = None
    seconds: float = 0.0
    doc: dict | None = None         # the scorer's --json document, with anything like a key blanked


def scrub_all(x):
    """Every string in a document, blanked of anything that looks like a key (words.scrub)."""
    if isinstance(x, str):
        return words.scrub(x)
    if isinstance(x, list):
        return [scrub_all(v) for v in x]
    if isinstance(x, dict):
        return {str(k): scrub_all(v) for k, v in x.items()}
    return x


DOCUMENT_BYTES = 20_000_000       # a scorer's document is well under 1 MB for a season; anything this big is not one
# The tests each scorer's document always holds (the scorers print every one, with or without bets)
TEST_IDS = {"nfl-weather": ("RULE_B", "RULE_B_SECONDARY", "MODEL_LEAN"), "cfb-weather": ("RULE_B", "RULE_HT")}


def read_document(stdout: str, test_ids=()) -> dict | None:
    """A scorer's --json document, or None when what it printed is not one: a single JSON object with the printed
    report as text and a list of tests, each with its id, counts and bets, among them every id in `test_ids` (the
    scorer's own). Something too big, nested too deeply to read, of the wrong shape, or without its tests is not a
    document."""
    if not isinstance(stdout, str) or len(stdout) > DOCUMENT_BYTES:
        return None
    try:
        doc = json.loads(stdout)
        if not (isinstance(doc, dict) and isinstance(doc.get("text"), str) and isinstance(doc.get("tests"), list)):
            return None
        for t in doc["tests"]:
            if not (isinstance(t, dict) and isinstance(t.get("id"), str) and isinstance(t.get("counts"), dict)
                    and isinstance(t.get("bets"), list) and all(isinstance(b, dict) for b in t["bets"])):
                return None
        if not set(test_ids) <= {t["id"] for t in doc["tests"]}:
            return None
        return scrub_all(doc)
    except (TypeError, ValueError, RecursionError):
        return None


@dataclass
class Snap:
    built: datetime
    ledgers: dict
    runs: dict = field(default_factory=dict)
    closes: dict = field(default_factory=dict)
    alert_state: dict = field(default_factory=dict)
    alerts_log: dict = field(default_factory=dict)
    decisions: dict = field(default_factory=dict)
    fills: dict = field(default_factory=dict)
    quota: dict | None = None
    quota_note: str = ""
    plists: dict = field(default_factory=dict)
    launchctl: Launchctl = field(default_factory=Launchctl)
    logs: dict = field(default_factory=dict)
    operations: dict = field(default_factory=dict)
    status_text: str | None = None
    status_note: str = ""
    evidence: Read = field(default_factory=Read)
    tests_content: Read = field(default_factory=Read)
    manifest: dict | None = None
    manifest_note: str = ""
    unreadable: list = field(default_factory=list)        # expected files that couldn't be read (health: warn)
    warnings: list = field(default_factory=list)          # other things health warns about (rows logged later
                                                          # than now)
    notes: list = field(default_factory=list)             # other things worth saying


cap = words.cap
RUNS_REQUIRED = ("run_utc", "status")           # without these a runs.csv row says nothing


# ---------------------------------------------------------------- launchd

def schedule_of(plist: dict) -> dict:
    """Only the schedule: calendar times, an interval, keep-alive. Nothing else in a job file is kept."""
    cal = plist.get("StartCalendarInterval")
    cal = [cal] if isinstance(cal, dict) else cal if isinstance(cal, list) else []
    times = []
    for c in cal:
        if isinstance(c, dict) and isinstance(c.get("Hour"), int):
            times.append((int(c["Hour"]), int(c.get("Minute", 0) if isinstance(c.get("Minute", 0), int) else 0)))
    interval = plist.get("StartInterval")
    return {"times": sorted(times), "interval": interval if isinstance(interval, int) else None,
            "keep_alive": bool(plist.get("KeepAlive")), "run_at_load": bool(plist.get("RunAtLoad"))}


def schedule_words(s: dict | None, tz_note: str = "") -> str:
    if not s:
        return "Schedule not known"
    parts = []
    if s["times"]:
        clocks = [words.clock(datetime(2000, 1, 1, h, m, tzinfo=UTC), UTC) for h, m in s["times"]]
        n = len(clocks)
        joined = clocks[0] if n == 1 else ", ".join(clocks[:-1]) + " and " + clocks[-1]
        parts.append(f"Every day at {joined}" if n == 1 else f"{['', 'Once', 'Twice', 'Three times', 'Four times'][n] if n <= 4 else f'{n} times'} a day: {joined}")
    if s["interval"]:
        m = s["interval"] / 60
        parts.append(f"Every {m:g} minutes" if m >= 1 else f"Every {s['interval']} seconds")
    if s["keep_alive"]:
        parts.append("Kept running")
    return "; ".join(parts) or "No schedule in its job file"


def parse_launchctl_list(text: str) -> dict:
    out = {}
    for ln in text.splitlines():
        parts = ln.split()
        if len(parts) >= 3 and parts[2] in commands.JOB_LABELS:
            pid = int(parts[0]) if parts[0].lstrip("-").isdigit() else None
            status = int(parts[1]) if parts[1].lstrip("-").isdigit() else None
            out[parts[2]] = {"pid": pid, "status": status}
    return out


PRINT_KEYS = ("state", "runs", "last exit code")


def parse_launchctl_print(text: str) -> dict:
    """Only the job's state, run count and last exit code; everything else it prints is ignored."""
    out = {}
    for ln in text.splitlines():
        m = re.match(r"^\t?([a-z ]+?) = (.+)$", ln)
        if m and m.group(1) in PRINT_KEYS and m.group(1) not in out:
            out[m.group(1)] = m.group(2).strip()[:60]
    return out


# ---------------------------------------------------------------- the manifest of Thursday's pull

def manifest_picker(header):
    pos = {h: i for i, h in enumerate(header)}
    idx = [pos.get(c, -1) for c in ("pull", "credits_last", "expected_credits", "remaining", "logged_at",
                                   "http_status")]

    def pick(row):
        row.append("")
        return tuple(row[i] for i in idx)
    return pick


def summarize_manifest(rows) -> dict:
    pulls: dict[str, dict] = {}
    last = ""
    for pull, billed, expected, remaining, logged, _status in rows:
        p = pulls.setdefault(pull or "(no name)", {"pull": pull or "(no name)", "requests": 0, "billed": 0,
                                                   "upper": 0, "lowest": None, "unreadable": 0})
        p["requests"] += 1
        e = words.num(expected)
        b = words.num(billed)
        if b is None:
            p["unreadable"] += 1 if e else 0
            b = e or 0
        p["billed"] += int(round(b))
        p["upper"] += int(round(e or 0))
        r = words.num(remaining)
        if r is not None:
            p["lowest"] = int(r) if p["lowest"] is None else min(p["lowest"], int(r))
        if logged > last:
            last = logged
    return {"pulls": list(pulls.values()), "last_logged": last}


# ---------------------------------------------------------------- the store

class Store:
    def __init__(self, cfg: Config, clock=None, runner=None):
        self.cfg = cfg
        self.clock = clock or (lambda: datetime.now(UTC))
        self.allowed = commands.Allowed(cfg.scorer_root, cfg.root)
        self.runner = runner or (lambda cmd, cwd, timeout: commands.run(cmd, cwd, self.allowed, timeout))
        self.ledgers = {s: Ledger(s, cfg.root) for s in ("nfl", "cfb")}
        self.manifest = AppendOnlyCSV(cfg.root / MANIFEST, f"the pull's request log ({MANIFEST})", manifest_picker)
        self.lock = threading.RLock()
        self._snap: Snap | None = None
        self._snap_at: float | None = None
        self._derived: dict = {}
        self._scores: dict[str, Scored] = {}
        self._score_locks = {p: threading.Lock() for p in PROJECTS}

    # ------------------------------------------------------------ commands
    def _run(self, cmd, cwd, timeout):
        if not self.allowed.check(cmd, cwd):              # the same check commands.run makes, before any runner
            raise PermissionError(f"not an allowed command: {cmd!r}")
        return self.runner(cmd, cwd, timeout)

    # ------------------------------------------------------------ the snapshot
    def snapshot(self) -> Snap:
        with self.lock:
            now = self.clock()
            if self._snap is None or self._snap_at is None or abs(now.timestamp() - self._snap_at) >= SNAPSHOT_SECONDS:
                self._snap = self._build(now)
                self._snap_at = now.timestamp()
                self._derived = {}
            return self._snap

    def derived(self, key, fn):
        """fn(), worked out once per key from the current snapshot and kept until the snapshot is rebuilt."""
        with self.lock:
            self.snapshot()
            if key not in self._derived:
                self._derived[key] = fn()
            return self._derived[key]

    def _expect(self, snap: Snap, r: Read, what: str):
        if r.data is None:
            snap.unreadable.append(cap(r.note or f"{what} could not be read."))
        elif r.note:
            snap.notes.append(cap(r.note))

    def _optional(self, snap: Snap, r: Read):
        if r.note and not r.missing:
            snap.notes.append(cap(r.note))

    def _build(self, now: datetime) -> Snap:
        cfg = self.cfg
        snap = Snap(built=now, ledgers=self.ledgers)
        for L in self.ledgers.values():
            try:
                L.refresh(now)
            except Exception as e:                        # noqa: BLE001 (never an error page)
                snap.unreadable.append(f"{cap(L.csv.label)} could not be read ({type(e).__name__}).")
                continue
            if not L.readable:
                snap.unreadable.append(cap(L.note))
            elif L.note:
                snap.notes.append(cap(L.note))
            if L.future:
                snap.notes.append(L.future_note(cfg.tz))
                snap.warnings.append(L.future_problem())
        for p in PROJECTS:
            fwd = cfg.forward(p)
            snap.runs[p] = read_runs(fwd / "runs.csv", label(p, "run record", "runs.csv"), now, cfg.tz)
            self._expect(snap, snap.runs[p], label(p, "run record", "runs.csv"))
            n = snap.runs[p].future
            if n:
                snap.warnings.append(f"The {SPORT_IN_WORDS[p]} run record has {words.count(n, 'row')} logged later "
                                     f"than now, {'which is' if n == 1 else 'which are'} left out; check the Mac's "
                                     "clock.")
            snap.alert_state[p] = read_json(fwd / "alert_state.json", label(p, "alert record", "alert_state.json"))
            if snap.alert_state[p].data is not None and not isinstance(snap.alert_state[p].data, dict):
                snap.alert_state[p] = Read(note=label(p, "alert record", "alert_state.json") + " is not in the "
                                           "form the alert jobs write.")
            self._expect(snap, snap.alert_state[p], label(p, "alert record", "alert_state.json"))
            for key, name, what in (("closes", "closes.csv", "closing-line record"), ("decisions", "decisions.csv",
                                    "decision record"), ("fills", "fills.csv", "paper-fill record")):
                r = read_csv(fwd / name, label(p, what, name))
                getattr(snap, key)[p] = r
                self._optional(snap, r)
            snap.alerts_log[p] = read_text(fwd / "alerts.log", label(p, "alert log", "alerts.log"), tail=512_000)
            self._optional(snap, snap.alerts_log[p])
        # credits (only whitelisted fields; the key's fingerprint is never kept)
        q = read_json(cfg.quota_file, "the credit balance file (~/.cache/value-finder/odds_quota.json)")
        if isinstance(q.data, dict):
            snap.quota = {k: q.data.get(k) for k in QUOTA_FIELDS if k in q.data}
            for k in ("remaining", "used", "last"):
                v = snap.quota.get(k)
                snap.quota[k] = int(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None
        else:
            why = q.note if q.data is None else "The credit balance file is not in the form the jobs write."
            snap.quota_note = cap(why or "The credit balance file could not be read.")
            snap.unreadable.append(snap.quota_note)
        # launchd job files (schedule only)
        for job in JOBS:
            lbl = job["label"]
            r = read_plist(cfg.plist(lbl), f"the launchd file for the {job['in_a_sentence']} job "
                                           f"(~/Library/LaunchAgents/{lbl}.plist)")
            snap.plists[lbl] = schedule_of(r.data) if isinstance(r.data, dict) else None
            if r.data is None and not job.get("collector"):
                snap.unreadable.append(cap(r.note))
            if "log" in job:
                lr = read_text(cfg.log(job["log"]), f"the {job['in_a_sentence']} log", tail=4096)
                last = next((ln for ln in reversed((lr.data or "").splitlines()) if ln.strip()), "")
                snap.logs[lbl] = {"mtime": lr.mtime, "last_line": words.scrub(last)[:200], "note": lr.note}
        snap.launchctl = self._launchctl()
        if snap.launchctl.listed is None:
            snap.unreadable.append(snap.launchctl.note)
        from . import operations
        snap.operations = operations.build(cfg, now)
        # STATUS.md, content
        st = read_text((cfg.operations_root or cfg.root) / "STATUS.md", "the status page (STATUS.md)")
        snap.status_text, snap.status_note = st.data, cap(st.note)
        self._expect(snap, st, "the status page (STATUS.md)")
        snap.evidence = read_json(cfg.content / "evidence.json", "the evidence list (dashboard/content/evidence.json)")
        self._expect(snap, snap.evidence, "the evidence list")
        snap.tests_content = read_json(cfg.content / "forward_tests.json",
                                       "the file of forward-test descriptions (dashboard/content/forward_tests.json)")
        self._expect(snap, snap.tests_content, "the forward-test descriptions")
        # Thursday's pull
        self.manifest.refresh()
        if self.manifest.readable:
            snap.manifest = summarize_manifest(self.manifest.rows)
            snap.manifest_note = cap(self.manifest.note)
        elif not self.manifest.missing:
            snap.manifest_note = cap(self.manifest.note)
        return snap

    def _launchctl(self) -> Launchctl:
        out = Launchctl()
        try:
            r = self._run(commands.launchctl_list_command(), None, commands.LAUNCHCTL_TIMEOUT)
        except PermissionError:
            raise
        except Exception as e:                            # noqa: BLE001
            out.note = f"Could not ask launchd about the scheduled jobs ({type(e).__name__})."
            return out
        if not r.ok:
            out.note = "Could not ask launchd about the scheduled jobs" + (
                " (it took too long)." if r.timed_out else ".")
            return out
        out.listed = parse_launchctl_list(r.stdout)
        for lbl in commands.JOB_LABELS:
            if lbl not in out.listed:
                continue
            try:
                p = self._run(commands.launchctl_print_command(lbl), None, commands.LAUNCHCTL_TIMEOUT)
            except PermissionError:
                raise
            except Exception:                             # noqa: BLE001
                continue
            if p.ok:
                out.printed[lbl] = parse_launchctl_print(p.stdout)
        return out

    # ------------------------------------------------------------ the scorers
    def scorer(self, project: str, wait: bool = True) -> Scored:
        """The scorer's preview, at most 10 minutes old. With wait=False it never blocks: it returns what it
        has (possibly nothing yet) and refreshes in the background."""
        have = self._scores.get(project)
        now = self.clock()
        fresh = have is not None and have.ran_at is not None and (now - have.ran_at) < timedelta(seconds=SCORER_SECONDS)
        if fresh:
            return have
        if not wait:
            if not self._score_locks[project].locked():
                threading.Thread(target=self._score, args=(project,), daemon=True).start()
            return have or Scored(project, "waiting")
        return self._score(project)

    def _score(self, project: str) -> Scored:
        with self._score_locks[project]:
            have = self._scores.get(project)
            now = self.clock()
            if have is not None and have.ran_at is not None and (now - have.ran_at) < timedelta(seconds=SCORER_SECONDS):
                return have
            cmd, cwd = commands.scorer_command(self.cfg.scorer_root, self.cfg.root, project, now)
            would_create = commands.folders_a_scorer_would_create(self.cfg.scorer_root, project)
            if would_create:
                res = Scored(project, "skipped", error=", ".join(would_create), ran_at=now)
                self._scores[project] = res
                return res
            try:
                r = self._run(cmd, cwd, commands.SCORER_TIMEOUT)
            except PermissionError:
                raise
            except Exception as e:                        # noqa: BLE001
                res = Scored(project, "failed", error=f"{type(e).__name__}", ran_at=now)
            else:
                doc = read_document(r.stdout, TEST_IDS.get(project, ())) if r.ok else None
                # as printed, except that anything like a key is blanked (and, when it is not the document, only
                # its last 200,000 characters: a failed run's report is a few thousand)
                out = doc["text"] if doc is not None else words.scrub((r.stdout or "")[-200_000:])
                if r.missing:
                    res = Scored(project, "missing", ran_at=now)
                elif r.timed_out:
                    res = Scored(project, "timed_out", text=out, ran_at=now, seconds=r.seconds)
                elif not r.ok:
                    res = Scored(project, "failed", text=out, error=words.scrub(r.stderr)[-2000:], ran_at=now,
                                 seconds=r.seconds)
                elif doc is None:
                    res = Scored(project, "not_document", error=out[-1200:], ran_at=now, seconds=r.seconds)
                else:
                    res = Scored(project, "ok", text=out, ran_at=now, seconds=r.seconds, doc=doc)
            self._scores[project] = res
            return res

    def warm(self):
        """Start both scorer previews in the background (server start-up)."""
        for p in PROJECTS:
            self.scorer(p, wait=False)
