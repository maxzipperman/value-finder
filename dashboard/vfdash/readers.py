"""Reading files, and nothing else. Every file the dashboard looks at is opened here, read-only.

* No file whose name is or ends with ".env" is ever opened, nor a link to one (`refuse`).
* A missing, empty, cut-off or damaged file is never an error: each reader returns what it could read and
  a plain sentence saying what it couldn't.
* Ledgers only grow between rewrites, so `AppendOnlyCSV` reads each new line once and keeps the rest; a
  file that shrank, was replaced, or whose header changed is read again from the top.
"""
from __future__ import annotations

import csv
import io
import json
import os
import plistlib
import threading
from dataclasses import dataclass, field
from pathlib import Path


class Refused(Exception):
    """A path the dashboard must never open."""


class RefusedLink(Refused):
    """A link (or a path through a linked folder) that leads to a file the dashboard must never open."""


def _env_name(name: str) -> bool:
    name = name.lower()
    return name == ".env" or name.endswith(".env") or name.startswith(".env.")


def refuse(path) -> Path:
    p = Path(path)
    if _env_name(p.name):
        raise Refused(f"{p.name} is never opened")
    if _env_name(os.path.basename(os.path.realpath(p))):
        raise RefusedLink(f"{p.name} leads to a file that is never opened")
    return p


def _link_note(label: str) -> str:
    return f"{label} is a link to a file the dashboard never opens, so it is not read."


@dataclass
class Read:
    """What a reader got: `data` (None when nothing could be read), `note` (a plain sentence, "" when
    all went well), and `missing` (the file isn't there)."""
    data: object = None
    note: str = ""
    missing: bool = False
    mtime: float | None = None
    future: int = 0                                     # rows left out: logged later than now (runs.csv)


def _open_bytes(path: Path, start: int = 0, limit: int | None = None) -> bytes:
    with open(refuse(path), "rb") as f:
        if start:
            f.seek(start)
        return f.read() if limit is None else f.read(limit)


def read_bytes(path, label: str, tail: int | None = None) -> Read:
    """The file's bytes (the last `tail` bytes when given)."""
    p = Path(path)
    try:
        st = os.stat(refuse(p))
    except FileNotFoundError:
        return Read(note=f"{label} is missing.", missing=True)
    except RefusedLink:
        return Read(note=_link_note(label))
    except Refused:
        raise
    except OSError as e:
        return Read(note=f"{label} could not be opened ({e.strerror or type(e).__name__}).")
    try:
        start = max(0, st.st_size - tail) if tail else 0
        data = _open_bytes(p, start)
    except FileNotFoundError:
        return Read(note=f"{label} is missing.", missing=True)
    except RefusedLink:
        return Read(note=_link_note(label))
    except OSError as e:
        return Read(note=f"{label} could not be read ({e.strerror or type(e).__name__}).")
    return Read(data=data, mtime=st.st_mtime)


def read_text(path, label: str, tail: int | None = None) -> Read:
    r = read_bytes(path, label, tail)
    if r.data is None:
        return r
    text = r.data.decode("utf-8", errors="replace")
    note = f"{label} has characters that could not be read; they are shown as �." if "�" in text else ""
    if tail and len(r.data) >= tail:                    # started mid-file: drop the partial first line
        text = text.split("\n", 1)[1] if "\n" in text else ""
    return Read(data=text, note=note, mtime=r.mtime)


def read_json(path, label: str) -> Read:
    r = read_text(path, label)
    if r.data is None:
        return r
    if not r.data.strip():
        return Read(note=f"{label} is empty.", mtime=r.mtime)
    try:
        return Read(data=json.loads(r.data), mtime=r.mtime)
    except ValueError:
        return Read(note=f"{label} could not be read: it is not complete or not valid JSON.", mtime=r.mtime)


def read_plist(path, label: str) -> Read:
    r = read_bytes(path, label)
    if r.data is None:
        return r
    try:
        return Read(data=plistlib.loads(r.data), mtime=r.mtime)
    except Exception:                                   # noqa: BLE001 (any damage: say so)
        return Read(note=f"{label} could not be read as a launchd job file.", mtime=r.mtime)


def parse_csv_text(text: str) -> tuple[list[str], list[list[str]], int]:
    """(header, rows, damaged): complete rows only; a row with a different number of fields than the
    header is left out and counted."""
    reader = csv.reader(io.StringIO(text, newline=""))
    try:
        header = next(reader)
    except StopIteration:
        return [], [], 0
    except csv.Error:
        return [], [], 1
    rows, bad = [], 0
    width = len(header)
    try:
        for r in reader:
            if not r:
                continue
            if len(r) == width:
                rows.append(r)
            else:
                bad += 1
    except csv.Error:
        bad += 1
    return [h.strip() for h in header], rows, bad


def read_csv(path, label: str, tail: int | None = None) -> Read:
    """A small CSV read whole: data = (header, rows as dicts). A last line with no line end is taken as
    still being written and left out, with a note."""
    r = read_text(path, label)
    if r.data is None:
        return r
    text = r.data
    if not text.strip():
        return Read(note=f"{label} is empty.", mtime=r.mtime)
    notes = [r.note] if r.note else []
    if not text.endswith("\n"):
        cut = text.rfind("\n")
        if cut < 0:
            return Read(note=f"{label} has only a partly written first line.", mtime=r.mtime)
        text = text[:cut + 1]
        notes.append(f"The last line of {label} is incomplete (still being written, or cut off); it is left out.")
    header, rows, bad = parse_csv_text(text)
    if not header:
        return Read(note=f"{label} could not be read as a table.", mtime=r.mtime)
    if bad:
        notes.append(f"{bad:,} line{'s' if bad != 1 else ''} of {label} could not be read and "
                     f"{'are' if bad != 1 else 'is'} left out.")
    out = [dict(zip(header, row, strict=True)) for row in rows]
    return Read(data=(header, out), note=" ".join(notes), mtime=r.mtime)


@dataclass
class AppendOnlyCSV:
    """A CSV that grows at the end. `refresh()` reads only what was added since the last call. Each
    complete row goes through `pick(header)` -> a function that turns a row into what is kept."""
    path: Path
    label: str
    pick: object                                    # callable(header) -> callable(row) -> kept value
    rows: list = field(default_factory=list)
    header: list = field(default_factory=list)
    note: str = ""
    missing: bool = False
    readable: bool = False
    mtime: float | None = None
    damaged: int = 0
    _key: tuple | None = None
    _offset: int = 0
    _head: bytes = b""
    _seen_tail: bytes = b""
    _fn: object = None
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def refresh(self) -> "AppendOnlyCSV":
        with self._lock:
            self._refresh()
        return self

    def _reset(self):
        self.rows, self.header, self._offset, self._head, self._fn, self.damaged = [], [], 0, b"", None, 0
        self._seen_tail = b""

    def _unchanged(self, p: Path, size: int) -> bool:
        """The part already read is still there: same header and the same bytes just before the offset."""
        if not self._head or size < self._offset:
            return False
        if _open_bytes(p, 0, len(self._head)) != self._head:
            return False
        n = len(self._seen_tail)
        return not n or _open_bytes(p, self._offset - n, n) == self._seen_tail

    def _refresh(self):
        p = self.path
        try:
            st = os.stat(refuse(p))
        except FileNotFoundError:
            self._reset()
            self.missing, self.readable, self.note, self._key = True, False, f"{self.label} is missing.", None
            return
        except RefusedLink:
            self._reset()
            self.missing, self.readable, self.note, self._key = False, False, _link_note(self.label), None
            return
        except OSError as e:
            self._reset()
            self.missing, self.readable, self._key = False, False, None
            self.note = f"{self.label} could not be opened ({e.strerror or type(e).__name__})."
            return
        self.missing, self.mtime = False, st.st_mtime
        key = (st.st_dev, st.st_ino)
        try:
            if not (key == self._key and self._unchanged(p, st.st_size)):
                self._reset()
                self._key = key
            data = _open_bytes(p, self._offset)
        except RefusedLink:
            self._reset()
            self.readable, self._key, self.note = False, None, _link_note(self.label)
            return
        except OSError as e:
            self._reset()
            self.readable, self._key = False, None
            self.note = f"{self.label} could not be read ({e.strerror or type(e).__name__})."
            return
        notes = []
        if self._offset == 0:
            if not data.strip():
                self.readable, self.note = False, f"{self.label} is empty."
                self._key = None
                return
            end = data.find(b"\n")
            if end < 0:
                self.readable, self.note = False, f"{self.label} has only a partly written first line."
                self._key = None
                return
            head = data[:end + 1]
            try:
                self.header = [h.strip() for h in next(csv.reader([head.decode("utf-8", errors="replace")]))]
            except (csv.Error, StopIteration):
                self.readable, self.note = False, f"{self.label} could not be read as a table."
                self._key = None
                return
            self._head, self._offset, data = head, len(head), data[end + 1:]
            self._fn = self.pick(self.header)
        cut = data.rfind(b"\n")
        complete, rest = (data[:cut + 1], data[cut + 1:]) if cut >= 0 else (b"", data)
        if rest.strip():
            notes.append(f"The last line of {self.label} is incomplete (still being written, or cut off); "
                         "it is left out for now.")
        if complete:
            text = complete.decode("utf-8", errors="replace")
            width, fn, keep = len(self.header), self._fn, self.rows.append
            try:
                for row in csv.reader(io.StringIO(text, newline="")):
                    if not row:
                        continue
                    if len(row) != width:
                        self.damaged += 1
                        continue
                    keep(fn(row))
            except csv.Error:
                self.damaged += 1
            self._offset += len(complete)
            self._seen_tail = complete[-256:]
        if self.damaged:
            notes.append(f"{self.damaged:,} line{'s' if self.damaged != 1 else ''} of {self.label} could not be "
                         f"read and {'are' if self.damaged != 1 else 'is'} left out.")
        self.readable, self.note = True, " ".join(notes)
