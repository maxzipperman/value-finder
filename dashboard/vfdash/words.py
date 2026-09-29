"""Times and plain words. Every time the page shows is formatted here, in the Mac's local time, except
kickoffs, which are shown in Eastern time as the ledgers give them."""
from __future__ import annotations

import os
import re
from datetime import date, datetime, time, timedelta, timezone, tzinfo
from zoneinfo import ZoneInfo

UTC = timezone.utc
EASTERN = ZoneInfo("America/New_York")
DAY_START, DAY_END = time(7, 30), time(23, 30)      # the alert jobs' working day (health checks)
MINUS = "−"


def local_zone() -> tzinfo:
    """The Mac's own time zone by name (so daylight-saving changes land right), else the offset in force."""
    try:
        return ZoneInfo(os.path.realpath("/etc/localtime").split("/zoneinfo/", 1)[1])
    except Exception:                                   # noqa: BLE001 (no zone link: use the current offset)
        return datetime.now().astimezone().tzinfo or UTC


# ---------------------------------------------------------------- reading times

_UTC_FORMATS = ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%MZ", "%Y-%m-%dT%H%MZ", "%Y-%m-%d %H:%MZ", "%Y-%m-%d %H:%M:%SZ",
                "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M")


def parse_utc(text) -> datetime | None:
    """A UTC time as the jobs write them ("2026-09-29T14:30:07Z", "2026-09-29T0002Z",
    "2026-10-02 00:00:00+00:00", ...), as an aware datetime; None when blank or not a time."""
    if text is None:
        return None
    s = str(text).strip()
    if not s:
        return None
    for fmt in _UTC_FORMATS:
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=UTC)
        except ValueError:
            pass
    try:
        t = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None
    return t.replace(tzinfo=UTC) if t.tzinfo is None else t.astimezone(UTC)


def eastern_kickoff(day: str, clock: str) -> datetime | None:
    """NFL kickoff in UTC from the ledger's Eastern gameday ("2026-10-04") and gametime ("13:00")."""
    try:
        d = datetime.strptime(f"{day.strip()} {clock.strip()}", "%Y-%m-%d %H:%M")
    except (ValueError, AttributeError):
        return None
    return d.replace(tzinfo=EASTERN).astimezone(UTC)


_KICK_ET = re.compile(r"^\s*(?:[A-Za-z]{3}\s+)?(\d{1,2})-(\d{1,2})\s+(\d{1,2}):(\d{2})\s*$")


def cfb_kickoff(start_utc: str, kick_et: str, logged: datetime | None) -> datetime | None:
    """CFB kickoff in UTC: start_utc when the row has it; older rows have only kick_et
    ("Thu 10-01 20:00", Eastern, no year), whose year is taken from when the row was logged."""
    t = parse_utc(start_utc)
    if t is not None:
        return t
    m = _KICK_ET.match(kick_et or "")
    if not m or logged is None:
        return None
    month, day, hh, mm = map(int, m.groups())
    year = logged.astimezone(EASTERN).year
    if month < logged.astimezone(EASTERN).month - 6:     # a January bowl logged in December
        year += 1
    try:
        return datetime(year, month, day, hh, mm, tzinfo=EASTERN).astimezone(UTC)
    except ValueError:
        return None


# ---------------------------------------------------------------- writing times

def clock(dt: datetime, tz: tzinfo) -> str:
    """7:30 AM"""
    t = dt.astimezone(tz)
    return f"{t.hour % 12 or 12}:{t.minute:02d} {'AM' if t.hour < 12 else 'PM'}"


def day_label(dt: datetime, tz: tzinfo) -> str:
    """Tue Sep 29"""
    t = dt.astimezone(tz)
    return f"{t:%a} {t:%b} {t.day}"


def when(dt: datetime | None, tz: tzinfo, now: datetime | None = None) -> str:
    """A local time: "7:30 AM" today, else "Mon Sep 28, 7:30 PM"."""
    if dt is None:
        return "not recorded"
    if now is not None and dt.astimezone(tz).date() == now.astimezone(tz).date():
        return clock(dt, tz)
    return f"{day_label(dt, tz)}, {clock(dt, tz)}"


def when_full(dt: datetime | None, tz: tzinfo) -> str:
    """Always with the day: "Tue Sep 29, 7:30 AM"."""
    return "not recorded" if dt is None else f"{day_label(dt, tz)}, {clock(dt, tz)}"


def kickoff_et(dt: datetime | None) -> str:
    """Kickoff in Eastern time: "Sun Oct 4, 1:00 PM ET"."""
    if dt is None:
        return "kickoff not known"
    return f"{day_label(dt, EASTERN)}, {clock(dt, EASTERN)} ET"


def iso_z(dt: datetime | None) -> str | None:
    return None if dt is None else dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def ago(dt: datetime, now: datetime) -> str:
    """"3 hours ago", "25 minutes ago", "2 days ago"."""
    s = (now - dt).total_seconds()
    if s < 90:
        return "just now"
    if s < 90 * 60:
        return f"{round(s / 60)} minutes ago"
    if s < 36 * 3600:
        h = round(s / 3600)
        return f"{h} hour{'s' if h != 1 else ''} ago"
    d = round(s / 86400)
    return f"{d} day{'s' if d != 1 else ''} ago"


def working_hours_between(start: datetime, end: datetime, tz: tzinfo) -> float:
    """Hours between `start` and `end` that fall inside the jobs' working day, 7:30 AM to 11:30 PM local.
    Overnight hours don't count, so a quiet night is not an outage."""
    if end <= start:
        return 0.0
    if (end - start) > timedelta(days=40):
        return float("inf")
    total = 0.0
    d = start.astimezone(tz).date() - timedelta(days=1)
    last = end.astimezone(tz).date()
    while d <= last:
        a = datetime.combine(d, DAY_START, tzinfo=tz)
        b = datetime.combine(d, DAY_END, tzinfo=tz)
        lo, hi = max(a, start), min(b, end)
        if hi > lo:
            total += (hi - lo).total_seconds() / 3600
        d += timedelta(days=1)
    return total


def next_run(times: list[tuple[int, int]], now: datetime, tz: tzinfo) -> datetime | None:
    """The first scheduled run strictly after `now`, from a list of daily (hour, minute) times."""
    if not times:
        return None
    today = now.astimezone(tz).date()
    for d in (today, today + timedelta(days=1)):
        for h, m in sorted(times):
            t = datetime.combine(d, time(h, m), tzinfo=tz)
            if t > now:
                return t
    return None


def days_to(kick: datetime | None, now: datetime, tz: tzinfo) -> int | None:
    """Calendar days from today (local) to the kickoff's Eastern date, the way the rules count lead days."""
    if kick is None:
        return None
    return (kick.astimezone(EASTERN).date() - now.astimezone(tz).date()).days


# ---------------------------------------------------------------- numbers

def num(text) -> float | None:
    try:
        v = float(str(text).strip())
    except (TypeError, ValueError):
        return None
    return None if v != v else v                        # NaN is blank


def odds(text) -> str:
    """American odds as shown: "−108", "+105"; "" when blank."""
    v = num(text)
    if v is None:
        return ""
    v = round(v)
    return f"{MINUS}{abs(v)}" if v < 0 else f"+{v}"


def total(text) -> str:
    v = num(text)
    return "" if v is None else f"{v:.1f}"


def pct(text, signed=False, digits=0) -> str:
    v = num(text)
    if v is None:
        return ""
    s = f"{abs(v) * 100:.{digits}f}%"
    if signed:
        return (MINUS if v < 0 else "+") + s
    return (MINUS if v < 0 else "") + s


def whole(text, unit="") -> str:
    v = num(text)
    return "" if v is None else f"{round(v)}{unit}"


def count(n: int, one: str, many: str | None = None) -> str:
    return f"{n:,} {one if n == 1 else (many or one + 's')}"


# ---------------------------------------------------------------- statuses in plain words

BOOKS = {"pinnacle": "Pinnacle", "nflverse": "the consensus line (nflverse)", "draftkings": "DraftKings",
         "fanduel": "FanDuel", "betmgm": "BetMGM", "lowvig": "LowVig", "betonlineag": "BetOnline",
         "betrivers": "BetRivers", "espnbet": "ESPN BET", "bovada": "Bovada", "hardrockbet": "Hard Rock",
         "caesars": "Caesars", "williamhill_us": "Caesars", "fanatics": "Fanatics", "espn": "ESPN",
         "mybookieag": "MyBookie", "betus": "BetUS", "ballybet": "Bally Bet", "fliff": "Fliff"}


def book(name: str) -> str:
    name = (name or "").strip()
    return BOOKS.get(name.lower(), name)


RULE_B_WORDS = {
    "SIGNAL": "Signal",
    "SIGNAL_SECONDARY": "Signal at the backup price",
    "no_trigger": "No wind trigger",
    "outside_horizon": "Wind trigger, outside the 1 to 3 day window",
    "no_price": "Wind trigger, no price",
    "price_too_high": "Wind trigger, price too high",
    "negative_ev": "Wind trigger, expected value below zero",
    "not_outdoor": "Not an outdoor game",
    "no_venue": "Venue location not known",
    "time_tbd": "Kickoff time not set",
    "no_forecast": "No forecast yet",
    "missing": "No forecast yet",
}
RULE_HT_WORDS = {
    "SIGNAL": "Signal",
    "no_price": "No price",
    "below_threshold": "Total below the line",
    "price_too_high": "Price too high",
    "before_window": "Before the test starts (Week 6)",
}
LEAN_WORDS = {"UNDER lean": "Leans under", "OVER lean": "Leans over", "": "No lean"}


def status_words(rule: str, value: str, wx_src: str = "", threshold: str = "") -> str:
    v = (value or "").strip()
    if rule == "lean":
        return LEAN_WORDS.get(v, f"Logged as “{v}”")
    if not v:
        return "Not logged on this row"
    if rule == "rule_b":
        if v == "not_outdoor" and wx_src == "open_roof":
            return "Open roof, not counted"
        if v == "not_outdoor" and wx_src == "missing":
            return "No forecast yet"
        if v == "not_outdoor" and wx_src == "indoor":
            return "Indoors"
        return RULE_B_WORDS.get(v, f"Logged as “{v}”")
    if rule == "rule_ht":
        if v == "below_threshold" and num(threshold) is not None:
            return f"Total below {num(threshold):.1f}"
        return RULE_HT_WORDS.get(v, f"Logged as “{v}”")
    return v


def is_signal(rule: str, value: str) -> bool:
    """Rule B at either price and Rule HT count as signals, as in runs.csv; the model lean is a watch."""
    v = (value or "").strip()
    return (rule == "rule_b" and v in ("SIGNAL", "SIGNAL_SECONDARY")) or (rule == "rule_ht" and v == "SIGNAL")


def alert_words(key: str) -> str:
    """An alert key from alert_state.json in plain words."""
    k = (key or "").strip()
    fixed = {"ruleb": "Rule B signal", "ruleb_secondary": "Rule B signal at the backup price",
             "ht": "Rule HT signal", "edge": "Model edge watch", "coldvis": "Cold visitor watch",
             "leanUNDER": "Model lean watch: under", "leanOVER": "Model lean watch: over"}
    if k in fixed:
        return fixed[k]
    if k.startswith("ruleb_") or k.startswith("watch_"):
        return f"Wind watch, no bet ({RULE_B_WORDS.get(k.split('_', 1)[1], k.split('_', 1)[1]).lower()})"
    if k.startswith("lag"):
        return f"Line lag watch (wind {k[3:]} mph)" if k[3:].isdigit() else "Line lag watch"
    return f"Alert “{k}”"


SECRET = re.compile(r"(?i)\b(api[_-]?key|apikey|key|token|secret|password|authorization)(\s*[:=]\s*|%3d)([^\s&;,'\"()<>]+)")


def scrub(text: str) -> str:
    """Blank anything that looks like a key before it is shown (the jobs already do this; this is a second
    lock on the door)."""
    return SECRET.sub(lambda m: f"{m.group(1)}{m.group(2)}***", str(text or ""))


def strip_markdown(text: str) -> str:
    """Markdown to plain words: links to their text, no bold, italics or code marks."""
    s = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text or "")
    s = s.replace("**", "").replace("`", "")
    s = re.sub(r"(?<![\w*])\*(?!\s)([^*]+?)\*(?![\w*])", r"\1", s)
    return " ".join(s.split())


def first_sentence(text: str) -> str:
    s = strip_markdown(text).strip()
    m = re.search(r"(?<=[.?])\s+(?=[A-Z(\"“])", s)
    return s[:m.start()].strip() if m else s


def is_date(d: date | None) -> bool:
    return isinstance(d, date)
