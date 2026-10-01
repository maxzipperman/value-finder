"""What the grader reads from the repo's documents at run time: the count and the bar, and the book note.

The count and the bar (PREREGISTRATION_PROPS.md, sections 2.9 and 4). The registration's header field "Count and
bar at registration" is the bar the Act condition uses; the brief for this grader adds "with the count and bar taken
from STATUS.md at run time and printed". Both are read and printed:
  * STATUS.md: the running count is the largest N in any "0.05 / N" there (the count only rises, and each step of
    it is written as "p < ... (0.05 / N)").
  * the header field: the italic placeholder "(the hub fills this in ...)" and the "As of writing, for
    illustration: ... add theirs." sentence are set aside, and every "0.05 / N" left on the line is read, whether
    or not the placeholder is still there. None left: unfilled (placeholder present) or unreadable. One N: filled.
    More than one: ambiguous, and the largest is taken.
The stricter applies: the larger count, so the smaller bar (p < 0.05 / count). The count adds nothing for this
grader: it implements the one variant already in the running count.

The book note (section 8). "The resulting book, with the two coverage figures, is recorded after the F3a pull, and
before any F3a row is joined to an outcome, in a dated note (section 8)." `noted_book` reads section 8, HTML
comments and the italic placeholder set aside, and returns the book of its dated entries: an entry (a paragraph or
list item) that carries a date (YYYY-MM-DD) and says "the book is Pinnacle" or "the book is DraftKings". Other
mentions of a book's name (the coverage figures, "Pinnacle lists ...") don't count. Dated entries naming both books
name none. `markets props-grade` joins nothing to an outcome unless the hub passes --book-recorded with the book the
rule picks, section 8 records that same book, and the registration file is committed unchanged.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parents[5]
STATUS = REPO / "STATUS.md"
PREREG = REPO / "nfl-weather" / "PREREGISTRATION_PROPS.md"
PREREG_REL = "nfl-weather/PREREGISTRATION_PROPS.md"
_BAR = re.compile(r"0\.05\s*/\s*(\d[\d,]*)")
FIELD = "**Count and bar at registration:**"
PLACEHOLDER = "(the hub fills this in"
_PLACEHOLDER = re.compile(r"\*?\(the hub fills this in.*?\)\*?", re.S)
_ILLUSTRATION = re.compile(r"As of writing, for illustration:.*?add theirs\.", re.S)
_DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
_BOOK_IS = re.compile(r"\bthe book is\W{0,4}(pinnacle|draft\s*kings)\b", re.I)
BOOK_NAMES = {"pinnacle": "Pinnacle", "draftkings": "DraftKings"}


def _counts(text: str) -> list[int]:
    return [int(m.replace(",", "")) for m in _BAR.findall(text)]


@dataclass
class Bar:
    status_count: int | None
    header: str                   # "unfilled", "filled", "ambiguous", "missing" or "unreadable"
    header_count: int | None      # the largest N read from the header field
    count: int | None             # the one used: the larger of the two
    header_counts: tuple = ()     # every N read from the header field

    @property
    def alpha(self) -> float | None:
        return None if self.count is None else 0.05 / self.count

    def lines(self) -> list[str]:
        s = (f"STATUS.md at run time: running count {self.status_count} (the largest \"0.05 / N\" in it), bar "
             f"p < {0.05 / self.status_count:.6f}" if self.status_count else
             "STATUS.md at run time: no running count found (no \"0.05 / N\" in it)")
        h = {"unfilled": "unfilled (it still holds the hub's placeholder; its illustration figures are ignored)",
             "missing": "not found in the registration file",
             "unreadable": "filled, but no \"0.05 / N\" on it could be read",
             "ambiguous": f"filled, but not unambiguously: it reads {', '.join(map(str, self.header_counts))}; the "
                          f"largest, {self.header_count}, is set against STATUS.md's",
             "filled": f"{self.header_count}, bar p < {0.05 / self.header_count:.6f}" if self.header_count else ""}
        used = (f"Used, the stricter (the larger count): {self.count}, bar p < 0.05 / {self.count} = {self.alpha:.6f}"
                if self.count else "Used: none could be read, so section 2.9's condition 1 cannot be met")
        return [s, f"Registration header, \"Count and bar at registration\": {h[self.header]}", used,
                "Variants already run but not yet in STATUS.md are not visible to this grader; the hub adds them to "
                "the header field. This grader adds no variant: it implements the 1 already in the running count."]


def header_counts(line: str) -> tuple[str, list[int]]:
    """(state, counts) for the header field's line: see the module docstring."""
    rest = line.split(FIELD, 1)[1]
    placeholder = PLACEHOLDER in rest
    rest = _ILLUSTRATION.sub("", _PLACEHOLDER.sub("", rest))
    counts = sorted(set(_counts(rest)))
    if not counts:
        return ("unfilled" if placeholder else "unreadable"), []
    return ("filled" if len(counts) == 1 else "ambiguous"), counts


def bar(status: Path = STATUS, prereg: Path = PREREG) -> Bar:
    sc = max(_counts(status.read_text()), default=None) if status.exists() else None
    header, hcs = "missing", []
    if prereg.exists():
        line = next((ln for ln in prereg.read_text().splitlines() if FIELD in ln), None)
        if line is not None:
            header, hcs = header_counts(line)
    hc = max(hcs, default=None)
    used = max([c for c in (sc, hc) if c], default=None)
    return Bar(sc, header, hc, used, tuple(hcs))


def section8(prereg: Path = PREREG) -> str:
    """Section 8's text, without its heading and without the italic placeholder paragraph."""
    if not prereg.exists():
        return ""
    text = prereg.read_text()
    m = re.search(r"^## 8\. Dated notes\s*$(.*?)(?=^## |\Z)", text, flags=re.M | re.S)
    if not m:
        return ""
    body = [ln for ln in m.group(1).splitlines() if not ln.strip().startswith("*(After the F3a pull")]
    return "\n".join(body).strip()


def noted_book(prereg: Path = PREREG) -> tuple[str | None, str]:
    """(the book section 8's dated entries record, "") or (None, why there is none); see the module docstring."""
    text = re.sub(r"<!--.*?-->", "", section8(prereg), flags=re.S)
    blocks = [b for b in re.split(r"\n\s*\n|\n(?=\s*[-*] )", text) if b.strip()]
    if not blocks:
        return None, "it holds only the placeholder"
    named = set()
    for b in blocks:
        books = {re.sub(r"\s", "", x.lower()) for x in _BOOK_IS.findall(b)}
        if books and _DATE.search(b):
            named |= books
    if not named:
        return None, "it has no dated entry (YYYY-MM-DD) saying \"the book is Pinnacle\" or \"the book is DraftKings\""
    if len(named) > 1:
        return None, "its dated entries name both books"
    return named.pop(), ""
