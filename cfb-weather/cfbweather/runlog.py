"""Run records and forecast provenance for the scheduled jobs. Copied from nfl-weather (nflweather/runlog.py); keep the two in sync.

"Log, don't drop" (CLAUDE.md): every alert run appends one row to data/forward/runs.csv, whether it
finished or failed, so a run that logged no games still leaves a record. Each forecast a run used is
kept in data/forward/forecasts/ under the hash of its contents, and the ledger row carries that hash and
the time the file was fetched, so an old row can be traced to the exact forecast behind it.
ops/RUN_RECORDS.md explains the records for the owner.
"""
from __future__ import annotations

import csv
import gzip
import hashlib
import io
import json
import os
import re
import shutil
from pathlib import Path

import pandas as pd

# rule_priced (added Sep 29, 2026) is the number of games priced at the rule's own book(s), so a run with
# the Odds API down no longer looks like a normal run. New columns only ever go on the end.
RUN_COLS = ["run_utc", "job", "rules_version", "status", "games", "signals", "priced", "unmapped", "error",
            "rule_priced"]

# What a secret can look like in an error message. The value stops at whitespace and at the punctuation
# that ends a value in a URL, a list or a dict (& ; , quotes brackets braces < > %), so the text after it
# survives. A name counts only where a word or a part of a name starts (ODDS_API_KEY, x-api-key, oddsApiKey,
# ?apiKey%3D), so words like "monkey", "keyword" or "KeyError" are left alone.
_VALUE = r"[^\s&;,'\"()\[\]{}<>%]+"
SECRET = re.compile(r"""
    (?: \b | (?<=[_-]) | (?<=%[0-9a-f]{2}) | (?-i:(?<=[a-z0-9])(?=[A-Z])) )    # where a name part starts
    (?P<name> api[_-]?key | key | token | secret | password | passwd | authorization )
    (?P<mid>
        ["']? \s* (?: [:=] | %3[ad] ) \s*                # name: value, name = value, "name": , name%3D
        (?: (?: bearer | basic | token ) \s+ )?         # Authorization: Bearer <value>
        ["'<\[(]*                                        # an opening quote or bracket before the value
    )
    (?P<value>""" + _VALUE + ")", re.IGNORECASE | re.VERBOSE)
BEARER = re.compile(r"\b(?P<name>bearer\s+)(?P<value>" + _VALUE + ")", re.IGNORECASE)


def scrub(text) -> str:
    """`text` on one line with any key in it blanked (the value becomes ***). Request URLs carry the Odds
    API key as `apiKey=...`, and an error message can quote the URL, a header or the request's parameters;
    run records are pushed to GitHub and notifications go through ntfy, so neither may hold a key."""
    text = " ".join(str(text).split())
    text = SECRET.sub(lambda m: f"{m['name']}{m['mid']}***", text)
    return BEARER.sub(lambda m: f"{m['name']}***", text)


def record_run(path, job, rules_version, status, games=0, signals=0, priced=0, unmapped="", error="",
               rule_priced=0):
    """Append one run to runs.csv. `status` is "ok" or "failed"; `priced` counts games with any posted
    total, `rule_priced` those priced at the rule's own book(s); `unmapped` lists odds-feed team names
    that matched no scheduled team (their games arrive unpriced); `error` is the exception, shortened, or
    a note on an "ok" run. A runs.csv from before a column was added is widened once (widen_runs)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    cols = widen_runs(path)
    row = dict(run_utc=pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%dT%H:%M:%SZ"), job=job,
               rules_version=rules_version, status=status, games=games, signals=signals, priced=priced,
               unmapped=unmapped, error=scrub(error)[:300], rule_priced=rule_priced)
    with path.open("a", newline="") as f:
        w = csv.writer(f)
        if cols is None:
            w.writerow(RUN_COLS)
        w.writerow([row.get(c, "") for c in cols or RUN_COLS])


def widen_runs(path) -> list[str] | None:
    """The columns of the runs.csv at `path` (None when there is no file or it is empty), after adding any
    of RUN_COLS it lacks. The file is then rewritten once: the header gains the new names, and each old
    line keeps every character it had and gains one empty field per new column at its end. The new file
    is written beside the old one, with its permissions, and replaces it in a single step, so a crash
    leaves the old file."""
    path = Path(path)
    if not path.exists():
        return None
    with path.open(newline="") as f:
        text = f.read()
    lines = text.split("\n")
    tail = lines.pop()                                  # "" when the file ends with a line end
    lines = [ln + "\n" for ln in lines] + ([tail] if tail else [])
    if not lines:
        return None
    header = next(csv.reader([lines[0]]))
    missing = [c for c in RUN_COLS if c not in header]
    if not missing:
        return header
    eol = lines[0][len(lines[0].rstrip("\r\n")):] or "\r\n"
    records = list(csv.reader(io.StringIO(text, newline="")))
    if len(records) == len(lines):                     # one record per line, as record_run writes them
        out = []
        for i, line in enumerate(lines):
            body = line.rstrip("\r\n")
            end = line[len(body):] or eol              # a last line with no line end gets one
            extra = "," + ",".join(missing) if i == 0 else "," * len(missing)
            out.append(body + (extra if body else "") + end)
        new = "".join(out)
    else:                                              # a record spans lines (hand-edited): rewrite through csv
        buf = io.StringIO()
        csv.writer(buf, lineterminator=eol).writerows([header + missing]
                                                      + [r + [""] * len(missing) for r in records[1:] if r])
        new = buf.getvalue()
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("w", newline="") as f:
        f.write(new)
    shutil.copymode(path, tmp)                          # the new file keeps the old one's permissions
    os.replace(tmp, path)
    return header + missing


def read_alert_state(path, keep_copy=True) -> tuple[dict, str, str]:
    """(state, note, kept) from the alert job's alert_state.json: {game: {"sent": [alert keys], ...}}. A
    missing file is an empty state. A file that can't be read as that (damaged by a crash or a bad hand
    edit) is kept beside it as alert_state.corrupt-<UTC time>.json, whose name is `kept`, and the run
    starts from an empty state; `note` says so, for the run record. Both are "" otherwise. Alerts already
    sent may then be sent again. With `keep_copy` False (dry runs) nothing is written and `kept` is "". A
    file that can't be opened at all raises: it is never replaced without a copy."""
    path = Path(path)
    if not path.exists():
        return {}, "", ""
    try:
        state = json.loads(path.read_text())
        if not (isinstance(state, dict) and all(isinstance(s, dict) and isinstance(s.get("sent", []), list)
                                                for s in state.values())):
            raise ValueError("not a list of sent alerts per game")
        return state, "", ""
    except ValueError as e:                            # includes a JSON syntax error and a bad encoding
        why = f"{type(e).__name__}: {e}"
    if not keep_copy:
        return {}, f"{path.name} could not be read ({why}); this dry run started from an empty state", ""
    copy = path.with_name(f"{path.stem}.corrupt-{pd.Timestamp.now(tz='UTC'):%Y%m%dT%H%M%SZ}{path.suffix}")
    shutil.copy2(path, copy)
    return {}, (f"{path.name} could not be read ({why}); kept as {copy.name}; started from an empty state, "
                f"so alerts sent before may be sent again"), copy.name


def write_alert_state(path, state) -> None:
    """Write the alert state through a temp file and one rename, so a crash can't leave it half-written."""
    path = Path(path)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(state, indent=1))
    os.replace(tmp, path)


def keep_forecast(src, archive_dir=None):
    """(hash, fetched_utc) of the forecast file `src`, or ("", "") when it is missing. With
    `archive_dir`, the file is also stored there under its content hash (identical forecasts once)."""
    src = Path(src)
    if not str(src) or not src.is_file():
        return "", ""
    raw = src.read_bytes()
    h = hashlib.sha256(raw).hexdigest()[:16]
    dest = Path(archive_dir) / f"{h}.json.gz" if archive_dir else None
    if dest is not None and not dest.exists():
        dest.parent.mkdir(parents=True, exist_ok=True)
        with gzip.open(dest, "wb") as f:
            f.write(raw)
    fetched = pd.Timestamp(src.stat().st_mtime, unit="s", tz="UTC").strftime("%Y-%m-%dT%H:%M:%SZ")
    return h, fetched
