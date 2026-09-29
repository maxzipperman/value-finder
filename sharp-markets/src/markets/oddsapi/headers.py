"""`markets odds5m headers`: how the Odds API's balance header (x-requests-remaining) behaved in one pull's latest run,
read from the manifest alone. It makes no network request and needs no --confirm.

Nobody knows yet whether the real header is live, runs a few answers late, or is refreshed in steps. A header that
runs late makes an honest run look as if the account fell further than the run counted, which is what the alarm
watches for, so the alarm's margin (--alarm-margin) has to be wider than the header's lateness. This stage measures
the lateness on a run already made (the probe's one-credit sweeps first) and advises the margin for the next pull.

The run is the rows of the manifest after the key check that came last before the pull's last row, up to the next key
check (every pull of that command). Each answer is counted as the run counted it: what it reported, or its upper bound
when it didn't say. A charged answer whose reported balance is not below the reading before it "showed no fall"; the
longest stretch of answers in a row from such an answer until the balance next fell measures the header's lateness,
in answers. So does a reading that rose because it was out of date (a copy of the balance kept behind the live one),
by the answers' worth of charges it hides. The lateness is the larger of the two, in this run or in the run just
before it, whose last answers a late header can still hide at this run's key check. A rise by more than the smallest
default margin (5,000) is credits added, and the account is measured again from it, as a run does.
"""
from __future__ import annotations

import csv
import math
from collections import Counter
from pathlib import Path

from .bulk import DEFAULT_MARGIN

VERDICTS = {
    "live": "The balance header is live: every charge shows in the answer that made it.",
    "late": "The balance header runs late by up to {n:,} answers.",
    "steps": "The balance header is refreshed in steps, about every {n:,} answers.",
    "fell": ("The balance fell by {n:,} credits more than the run counted: something else spent on this key, or the API "
             "charged more than it reported."),
    "none": "There is no run of that pull in the manifest.",
}


def _int(value) -> int | None:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _runs(rows: list[dict], pull: str) -> list[tuple[dict, list[dict]]]:
    """(key-check row, the rows after it up to the next key check) for the run that holds the pull's last row, then for
    the last run before it that bought anything (a `balance` check buys nothing); [] when the pull has no run."""
    last = max((i for i, r in enumerate(rows) if r.get("pull") == pull), default=None)
    checks = [i for i, r in enumerate(rows) if r.get("pull") == "account" and (last is None or i < last)]
    if last is None or not checks:
        return []
    end = next((i for i in range(last, len(rows)) if rows[i].get("pull") == "account"), len(rows))
    out = [(rows[checks[-1]], rows[checks[-1] + 1:end])]
    for a, b in zip(checks[-2::-1], checks[:0:-1]):          # key checks before it, latest first, with the next one
        if b > a + 1:
            return out + [(rows[a], rows[a + 1:b])]
    return out


def _measure(key: dict, run: list[dict]) -> dict | None:
    """Replays one run's readings the way the run did (a rise above 5,000 starts it again), and measures the header."""
    start = _int(key.get("remaining"))
    if start is None or not run:
        return None
    prev = lowest = low_all = base = start
    counted = charged = no_fall = falls = readings = longest = top = 0
    stretch, rises = None, Counter()
    for i, r in enumerate(run):
        cost = _int(r.get("credits_last"))
        cost = _int(r.get("expected_credits")) or 0 if cost is None else cost
        counted, top = counted + cost, max(top, cost)
        left = _int(r.get("remaining"))
        if left is None:
            continue
        readings += 1
        if left > prev:
            rises[left - prev] += 1
        if left - prev > DEFAULT_MARGIN:          # credits added: measured again from here, as a run does
            base, lowest, prev, stretch = left + counted, left, left, None
            continue
        fell = left < prev
        charged += cost > 0
        no_fall += cost > 0 and not fell
        falls += fell
        stretch = None if fell else i if stretch is None and cost > 0 else stretch
        if stretch is not None:
            longest = max(longest, i - stretch + 1)
        lowest, low_all, prev = min(lowest, left), min(low_all, left), left
    stale = max((size for size in rises if size <= DEFAULT_MARGIN), default=0)     # an out-of-date reading's rise
    return {"start": start, "requests": len(run), "counted": counted, "top": top, "lowest": low_all,
            "charged": charged, "no_fall": no_fall, "falls": falls, "readings": readings, "stretch": longest,
            "rises": dict(sorted(rises.items())), "unexplained": (base - lowest) - counted,
            "lateness": max(longest, math.ceil(stale * len(run) / counted) if stale and counted else 0)}


def analyze(rows: list[dict], pull: str = "P0", per_call: int = 30) -> dict:
    """The measures and the one verdict for `pull`'s latest run in the manifest `rows`."""
    runs = _runs(rows, pull)
    m = _measure(*runs[0]) if runs else None
    if m is None:
        return {"verdict": VERDICTS["none"], "kind": "none"}
    before = (_measure(*runs[1]) if len(runs) > 1 else None) or {"lateness": 0, "top": 0}
    lateness = max(m["lateness"], before["lateness"])
    # what a late header can hide: this run's last answers, and at its key check the run before's; plus 1% (at least
    # 200) for other uses of the key
    if m["unexplained"] > max(200, m["counted"] // 100) + lateness * max(m["top"], before["top"]):
        kind, n = "fell", m["unexplained"]
    elif lateness == 0:
        kind, n = "live", 0
    elif 2 * m["no_fall"] > m["charged"]:
        kind, n = "steps", max(round(m["readings"] / max(1, m["falls"])), lateness + 1)
    else:
        kind, n = "late", lateness
    return {**m, "kind": kind, "verdict": VERDICTS[kind].format(n=n).replace(" 1 answers", " 1 answer"),
            "key_check": runs[0][0].get("logged_at", ""), "pulls": sorted({r.get("pull", "") for r in runs[0][1]}),
            "lateness": lateness, "lateness_this_run": m["lateness"], "per_call": per_call,
            "advised": max(DEFAULT_MARGIN, 2 * lateness * per_call)}


def stage_headers(manifest: Path, pull: str | None, per_call: int = 30) -> int:
    """Prints the analysis of `pull`'s latest run (P0 by default); exit status 0, or 1 when the manifest can't be read."""
    pull = "P0" if pull in (None, "", "all") else pull
    try:
        with Path(manifest).open(newline="") as f:
            rows = list(csv.DictReader(f))
    except FileNotFoundError:
        rows = []
    except (OSError, csv.Error, UnicodeDecodeError) as e:
        print(f"headers: the manifest could not be read ({getattr(e, 'strerror', None) or e}): {manifest}")
        return 1
    a = analyze(rows, pull, per_call)
    if a["kind"] != "none":
        rises = ", ".join(f"+{size:,}" + (f" x {k:,}" if k > 1 else "") + (" (credits added)" * (size > DEFAULT_MARGIN))
                          for size, k in a["rises"].items())
        print(f"headers, {pull}: the run after the key check at {a['key_check']} (pulls {', '.join(a['pulls'])})\n"
              f"  requests: {a['requests']:,} answers; the run counted {a['counted']:,} credits for them\n"
              f"  the balance: {a['start']:,} at the key check, lowest {a['lowest']:,}: a fall of "
              f"{a['start'] - a['lowest']:,}\n"
              f"  charged answers that showed no fall in the balance: {a['no_fall']:,} of {a['charged']:,}; the "
              f"longest stretch in a row: {a['stretch']:,} answers\n"
              f"  rises in the balance: {sum(a['rises'].values()):,}{': ' + rises if rises else ''}\n"
              f"  the header's lateness: {a['lateness']:,} answers (the longer of that stretch and the answers' worth "
              "of charges hidden by the largest out-of-date rise, in this run or the paid run before it; "
              f"{a['lateness_this_run']:,} in this run)")
    print(a["verdict"])
    if a["kind"] != "none":
        print(f"Smallest --alarm-margin advised for a pull whose calls cost up to {per_call} credits: "
              f"{a['advised']:,} (the larger of {DEFAULT_MARGIN:,} and 2 x {a['lateness']:,} answers x {per_call})")
    return 0
