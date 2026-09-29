"""Run records and forecast provenance for the scheduled jobs. Copied to cfb-weather (cfbweather/runlog.py); keep the two in sync.

"Log, don't drop" (CLAUDE.md): every alert run appends one row to data/forward/runs.csv, whether it
finished or failed, so a run that logged no games still leaves a record. Each forecast a run used is
kept in data/forward/forecasts/ under the hash of its contents, and the ledger row carries that hash and
the time the file was fetched, so an old row can be traced to the exact forecast behind it.
"""
from __future__ import annotations

import csv
import gzip
import hashlib
import re
from pathlib import Path

import pandas as pd

RUN_COLS = ["run_utc", "job", "rules_version", "status", "games", "signals", "priced", "unmapped", "error"]
SECRET = re.compile(r"(?i)\b(api_?key|key|token|secret|password)=[^&\s'\")]+")


def scrub(text) -> str:
    """`text` on one line with any key in it blanked. Request URLs carry the Odds API key as
    `apiKey=...`, and an error message can quote the URL; run records are pushed to GitHub and
    notifications go through ntfy, so neither may hold a key."""
    return SECRET.sub(lambda m: f"{m.group(1)}=***", " ".join(str(text).split()))


def record_run(path, job, rules_version, status, games=0, signals=0, priced=0, unmapped="", error=""):
    """Append one run to runs.csv. `status` is "ok" or "failed"; `unmapped` lists odds-feed team names
    that matched no scheduled team (their games arrive unpriced); `error` is the exception, shortened."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    new = not path.exists()
    with path.open("a", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(RUN_COLS)
        w.writerow([pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%dT%H:%M:%SZ"), job, rules_version, status, games,
                    signals, priced, unmapped, scrub(error)[:300]])


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
