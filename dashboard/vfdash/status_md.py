"""What the dashboard takes from STATUS.md: the "Waiting on you" items and the running count of variants."""
from __future__ import annotations

import re
from datetime import date, datetime, tzinfo

from . import words

ITEM = re.compile(r"^(\d+)\.\s+\*\*(.+?)\*\*(.*)$")
MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov",
                                      "dec"], start=1)}
DUE = re.compile(r"\bdue\b[\s:,-]*(?:by\s+|on\s+)?(?:(?:mon|tue|wed|thu|fri|sat|sun)[a-z]*\.?,?\s+)?"
                 r"(?:(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+(\d{1,2})(?:,?\s+(\d{4}))?"
                 r"|(\d{4})-(\d{2})-(\d{2}))", re.IGNORECASE)


def section(text: str, heading: str) -> str:
    """The body of the "## heading" section, up to the next heading of the same or higher level."""
    lines = text.splitlines()
    out, inside = [], False
    for ln in lines:
        if re.match(r"^##\s+", ln):
            if inside:
                break
            inside = ln.strip("# ").strip().lower() == heading.lower()
            continue
        if inside:
            out.append(ln)
    return "\n".join(out)


def due_date(text: str, today: date) -> date | None:
    """The date after "due" in an item's text, if there is one."""
    m = DUE.search(words.strip_markdown(text))
    if not m:
        return None
    try:
        if m.group(4):
            return date(int(m.group(4)), int(m.group(5)), int(m.group(6)))
        month, day = MONTHS[m.group(1).lower()[:3]], int(m.group(2))
        year = int(m.group(3)) if m.group(3) else today.year
        d = date(year, month, day)
        if not m.group(3) and (today - d).days > 183:      # "due Jan 5" written in December
            d = date(year + 1, month, day)
        return d
    except (ValueError, KeyError):
        return None


def waiting_items(text: str, now: datetime, tz: tzinfo) -> list[dict]:
    """Each numbered item of "## Waiting on you", in order: its bold title, the first sentence of its text,
    and a due date only when its text says "due" followed by a date."""
    body = section(text, "Waiting on you")
    items, cur = [], None
    for ln in body.splitlines():
        m = ITEM.match(ln)
        if m:
            cur = {"n": int(m.group(1)), "title": m.group(2), "text": [m.group(3)]}
            items.append(cur)
        elif cur is not None:
            cur["text"].append(ln)
    today = now.astimezone(tz).date()
    out = []
    for it in items:
        rest = "\n".join(it["text"]).strip()
        full = f"**{it['title']}**{rest}"
        due = due_date(full, today)
        level = None
        if due is not None:
            days = (due - today).days
            level = "fail" if days < 0 else "warn" if days <= 3 else "ok"
        line = rest.split("\n", 1)[0] if rest.split("\n", 1)[0].strip() else rest
        first = words.first_sentence(line)
        if first.startswith("(") and first.rstrip(".").endswith(")"):     # a parenthetical: take the next sentence
            after = words.strip_markdown(line)[len(first):].strip()
            first = words.first_sentence(after) or first
        out.append({"n": it["n"], "title": words.strip_markdown(it["title"]).rstrip().rstrip(".").rstrip(),
                    "first_sentence": first or "The item has no text after its title.",
                    "due": None if due is None else f"Due {due:%a} {due:%b} {due.day}",
                    "due_iso": None if due is None else due.isoformat(), "due_level": level})
    return out


def variants(text: str) -> int | None:
    """The largest explicit cumulative total in the Variants bullet or later committed-variant setup."""
    totals = []
    for ln in text.splitlines():
        if re.match(r"^\s*[-*]\s+\*\*Variants:?\*\*", ln):
            nums = re.findall(r"\*\*\s*(\d[\d,]*)\s*\*\*", ln)
            if nums:
                totals.append(int(nums[-1].replace(",", "")))
        elif "committed variants" in ln:
            # Later setup entries explicitly state their cumulative total, outside the older bullet.
            m = re.search(r"=\s*\*\*(\d[\d,]*)\*\*", ln)
            if m:
                totals.append(int(m[1].replace(",", "")))
    return max(totals) if totals else None


def bar(n: int | None) -> str | None:
    """The multiple-testing bar for a new result: 0.05 split over the variants tried."""
    return None if not n else f"{0.05 / n:.3g}"
