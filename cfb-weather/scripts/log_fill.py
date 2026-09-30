"""Paper-log the price you actually got after an alert (issue #5). score_forward.py compares
each fill with the alert-time quote, so the ledger measures the cost of waiting.

    python scripts/log_fill.py GAME_ID --rule rule_b --line 44.5 --price -108 [--book fanduel] [--at 2026-10-11T15:05Z]
                               [--max-stake 100] [--note "limit shown at the bet slip"]

Appends to data/forward/fills.csv. Rules: rule_b, rule_ht.

--max-stake (issue #76): the largest stake, in dollars, the book would have accepted on this bet. The
point of the column is to record whether a book would take at least the owner's $25 to $50 a bet, so
enter what the bet slip or the book allowed, and leave it out when it isn't known. --note is a short
free-text remark. Both are optional, logging only, and never touch the scorer's grading. They are the
last two columns of fills.csv (max_stake, note); a row logged without them leaves them blank. An older
fills.csv without the two columns is widened in place the first time a fill is added: every old cell
is kept as it was, byte for byte, and each old row gains two empty cells.
"""
import argparse
import csv
import io
import math
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

from cfbweather.config import ROOT

OLD_COLUMNS = ["fill_utc", "game_id", "rule", "line", "price", "book"]
NEW_COLUMNS = ["max_stake", "note"]
COLUMNS = OLD_COLUMNS + NEW_COLUMNS


def split_records(text):
    """Split CSV text into records, each with its own line ending, exactly as written. A line end inside a
    quoted cell does not end a record. Nothing is re-quoted or re-encoded."""
    out, start, quoted, i, n = [], 0, False, 0, len(text)
    while i < n:
        ch = text[i]
        if ch == '"':
            quoted = not quoted
        elif ch in "\r\n" and not quoted:
            if ch == "\r" and text[i + 1:i + 2] == "\n":
                i += 1
            out.append(text[start:i + 1])
            start = i + 1
        i += 1
    if start < n:
        out.append(text[start:])
    return out


def body_and_end(record):
    body = record.rstrip("\r\n")
    return body, record[len(body):]


def n_fields(body):
    return len(next(csv.reader([body]))) if body else 0


def widen(text):
    """The text of an old fills.csv with two empty cells added to the header and to every row that has the six
    old cells. Every existing cell is left byte for byte. Raises ValueError for a header that is not the old or
    the new one, or a row with more cells than the new header."""
    records = split_records(text)
    if not records:
        return text
    head, _ = body_and_end(records[0])
    if next(csv.reader([head])) != OLD_COLUMNS:
        raise ValueError("the header is not the six-column fills header")
    out = []
    for k, rec in enumerate(records):
        body, end = body_and_end(rec)
        if k == 0:
            out.append(body + "," + ",".join(NEW_COLUMNS) + (end or "\n"))
            continue
        if not body.strip():
            out.append(rec)
            continue
        n = n_fields(body)
        if n > len(OLD_COLUMNS):
            raise ValueError(f"row {k + 1} has {n} cells, more than the header's {len(OLD_COLUMNS)}")
        out.append(body + "," * (len(COLUMNS) - n) + end)
    return "".join(out)


def money(x):
    """A dollar figure as a plain number: no exponent, no trailing zeros."""
    return f"{x:.6f}".rstrip("0").rstrip(".")


def append_fill(path, row, max_stake=None, note=""):
    """Append one fill (a dict of the six original fields) to fills.csv at `path`, widening an old file in
    place first. Returns the row written."""
    path = Path(path)
    if max_stake is not None and (not math.isfinite(max_stake) or max_stake <= 0):
        raise ValueError("--max-stake must be a positive number of dollars")
    note = " ".join(str(note or "").split())
    cells = [row[c] for c in OLD_COLUMNS] + ["" if max_stake is None else money(max_stake), note]
    path.parent.mkdir(parents=True, exist_ok=True)
    text = path.read_bytes().decode("utf-8") if path.exists() else ""
    if not text.strip():
        text = ""
    eol = "\r\n" if text.split("\n", 1)[0].endswith("\r") else "\n"
    if text:
        header = next(csv.reader([body_and_end(split_records(text)[0])[0]]))
        if header == OLD_COLUMNS:
            text = widen(text)
        elif header != COLUMNS:
            raise ValueError(f"{path.name} has an unexpected header {header}; nothing was written")
        if not text.endswith(("\n", "\r")):
            text += eol
    else:
        text = ",".join(COLUMNS) + eol
    buf = io.StringIO()
    csv.writer(buf, lineterminator=eol).writerow(
        [str(float(c)) if k in (3, 4) else c for k, c in enumerate(cells)])
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write((text + buf.getvalue()).encode("utf-8"))
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise
    return cells


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("game_id")
    ap.add_argument("--rule", required=True, choices="rule_b,rule_ht".split(","))
    ap.add_argument("--line", type=float, required=True, help="the total you got")
    ap.add_argument("--price", type=float, required=True, help="American odds you got on the under")
    ap.add_argument("--book", default="")
    ap.add_argument("--at", default=None, help="fill time, UTC (default: now)")
    ap.add_argument("--max-stake", type=float, default=None, metavar="DOLLARS",
                    help="the largest stake, in dollars, the book would have accepted; the point is to record "
                         "whether a book would take at least your $25 to $50 a bet (optional; leave out if unknown)")
    ap.add_argument("--note", default="", help="a short note (optional)")
    ap.add_argument("--fills", default=str(ROOT / "data" / "forward" / "fills.csv"))
    a = ap.parse_args(argv)

    at = pd.Timestamp(a.at) if a.at else pd.Timestamp.now(tz="UTC")
    at = at.tz_localize("UTC") if at.tzinfo is None else at.tz_convert("UTC")
    row = dict(fill_utc=at.strftime("%Y-%m-%dT%H:%M:%SZ"), game_id=a.game_id, rule=a.rule, line=a.line,
               price=a.price, book=a.book)
    try:
        append_fill(a.fills, row, a.max_stake, a.note)
    except ValueError as e:
        sys.exit(f"log_fill: {e}")
    size = f", book would take up to ${money(a.max_stake)}" if a.max_stake is not None else ""
    print(f"logged {a.rule} {a.game_id}: under {a.line} at {a.price:+.0f} {a.book}{size}".rstrip())


if __name__ == "__main__":
    main()
