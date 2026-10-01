"""What the grader reads from the repo's documents at run time: the count and the bar, and the book note.

The count and the bar (PREREGISTRATION_PROPS.md, sections 2.9 and 4). The registration's header field "Count and
bar at registration" is the bar the Act condition uses; the brief for this grader adds "with the count and bar taken
from STATUS.md at run time and printed". Both are read and printed:
  * STATUS.md: the running count is the largest N in any "0.05 / N" there (the count only rises, and each step of
    it is written as "p < ... (0.05 / N)").
  * the header field: unfilled while it still holds the "(the hub fills this in" placeholder (its "for
    illustration" figures are then ignored); when filled, the largest N in a "0.05 / N" on that line.
The stricter applies: the larger count, so the smaller bar (p < 0.05 / count). The count adds nothing for this
grader: it implements the one variant already in the running count.

The book note (section 8). "The resulting book, with the two coverage figures, is recorded after the F3a pull, and
before any F3a row is joined to an outcome, in a dated note (section 8)." `book_noted` reads section 8 and says
whether a note other than the placeholder is there and which books it names. `markets props-grade` joins nothing to
an outcome unless the hub passes --book-recorded with the book the rule picks AND section 8 names that book.
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
BOOK_NAMES = {"pinnacle": "Pinnacle", "draftkings": "DraftKings"}


def _counts(text: str) -> list[int]:
    return [int(m.replace(",", "")) for m in _BAR.findall(text)]


@dataclass
class Bar:
    status_count: int | None
    header: str                   # "unfilled", "filled", "missing" or "unreadable"
    header_count: int | None
    count: int | None             # the one used: the larger of the two

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
             "filled": f"{self.header_count}, bar p < {0.05 / self.header_count:.6f}" if self.header_count else ""}
        used = (f"Used, the stricter (the larger count): {self.count}, bar p < 0.05 / {self.count} = {self.alpha:.6f}"
                if self.count else "Used: none could be read, so section 2.9's condition 1 cannot be met")
        return [s, f"Registration header, \"Count and bar at registration\": {h[self.header]}", used,
                "Variants already run but not yet in STATUS.md are not visible to this grader; the hub adds them to "
                "the header field. This grader adds no variant: it implements the 1 already in the running count."]


def bar(status: Path = STATUS, prereg: Path = PREREG) -> Bar:
    sc = max(_counts(status.read_text()), default=None) if status.exists() else None
    header, hc = "missing", None
    if prereg.exists():
        line = next((ln for ln in prereg.read_text().splitlines() if FIELD in ln), None)
        if line is not None:
            if PLACEHOLDER in line:
                header = "unfilled"
            else:
                hc = max(_counts(line.split(FIELD, 1)[1]), default=None)
                header = "filled" if hc else "unreadable"
    used = max([c for c in (sc, hc) if c], default=None)
    return Bar(sc, header, hc, used)


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


def book_noted(prereg: Path = PREREG) -> set[str]:
    """The books section 8's note names (by key: pinnacle, draftkings); empty while only the placeholder is there."""
    note = section8(prereg).lower().replace(" ", "")
    return {k for k in BOOK_NAMES if k in note}
