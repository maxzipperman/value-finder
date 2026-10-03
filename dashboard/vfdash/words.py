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
    "time_tbd": "Would signal, but no kickoff time is set (not eligible yet)",
}
LEAN_WORDS = {"UNDER lean": "Leans under", "OVER lean": "Leans over", "": "No lean"}
# The lean model is run only for an outdoor NFL game with a forecast (wx_src "era5"); on any other game the job
# logs a blank lean, which says the model wasn't run, not that it found nothing.
LEAN_NOT_RUN = {"indoor": "Not an outdoor game", "open_roof": "Open roof, not counted", "missing": "No forecast yet"}


def status_words(rule: str, value: str, wx_src: str = "", threshold: str = "") -> str:
    v = (value or "").strip()
    if rule == "lean":
        if not v and (wx_src or "").strip() in LEAN_NOT_RUN:
            return LEAN_NOT_RUN[wx_src.strip()]
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


# The badge a rule's status gets on the page. One colour is kept for signals and used for nothing else: a filled
# "Signal" badge, and the same colour outlined for a signal at the NFL's backup price (the consensus line, logged
# apart and not part of the decision). A watch gets a quiet outlined badge in the neutral colour, so it can never be
# mistaken for a signal: the NFL model lean, and a wind trigger that did not become a signal (no price, a price too
# high, a value not above zero, or outside the 1 to 3 day window; the alert job sends a watch for these).
WATCH_RULE_B = ("no_price", "price_too_high", "negative_ev", "outside_horizon")
BADGE_WORDS = {"signal": "Signal", "backup": "Signal, backup price", "watch": "Watch"}


def badge(rule: str, value: str) -> str:
    """"signal", "backup", "watch" or "" for one rule's status on a row."""
    v = (value or "").strip()
    if rule == "rule_b":
        return ("signal" if v == "SIGNAL" else "backup" if v == "SIGNAL_SECONDARY" else
                "watch" if v in WATCH_RULE_B else "")
    if rule == "rule_ht":
        return "signal" if v == "SIGNAL" else ""
    if rule == "lean":
        return "watch" if v in ("UNDER lean", "OVER lean") else ""
    return ""


def strongest(badges) -> str:
    """The badge a row shows beside its game: a signal before a backup-price signal before a watch."""
    for b in ("signal", "backup", "watch"):
        if b in badges:
            return b
    return ""


def until(kick: datetime | None, now: datetime) -> str:
    """How long until kickoff, in words: "in 2 days, 5 hours", "in 3 hours, 10 minutes", "in 25 minutes"."""
    if kick is None:
        return ""
    s = int((kick - now).total_seconds())
    if s <= 0:
        return "kicked off"
    d, h, m = s // 86400, s % 86400 // 3600, s % 3600 // 60
    unit = lambda n, w: f"{n} {w}{'s' if n != 1 else ''}"                       # noqa: E731
    if d:
        return "in " + unit(d, "day") + (f", {unit(h, 'hour')}" if h else "")
    if h:
        return "in " + unit(h, "hour") + (f", {unit(m, 'minute')}" if m else "")
    return "in " + unit(max(m, 1), "minute")


def signed(v, digits=2) -> str:
    """"+1.40", "−0.35" (a true minus sign), "0.00"; "" when blank."""
    x = num(v)
    if x is None:
        return ""
    s = f"{abs(x):.{digits}f}"
    if float(s) == 0:
        return s
    return (MINUS if x < 0 else "+") + s


def p_value(p: float | None) -> str:
    """A p-value as the page writes it: "0.39", "0.0499", "0.000312", "below 0.000001"."""
    if p is None:
        return ""
    if p < 1e-6:
        return "below 0.000001"
    return f"{p:.3g}" if p < 0.1 else f"{p:.2f}"


def alert_words(key: str) -> str:
    """An alert key from alert_state.json in plain words."""
    k = (key or "").strip()
    fixed = {"ruleb": "Rule B signal", "ruleb_secondary": "Rule B signal at the backup price",
             "ht": "Rule HT signal", "ht_time_tbd": "Rule HT: not eligible, no kickoff time set",
             "edge": "Model edge watch", "coldvis": "Cold visitor watch",
             "leanUNDER": "Model lean watch: under", "leanOVER": "Model lean watch: over"}
    if k in fixed:
        return fixed[k]
    if k.startswith("ruleb_") or k.startswith("watch_"):
        return f"Wind watch, no bet ({RULE_B_WORDS.get(k.split('_', 1)[1], k.split('_', 1)[1]).lower()})"
    if k.startswith("lag"):
        return f"Line lag watch (wind {k[3:]} mph)" if k[3:].isdigit() else "Line lag watch"
    return f"Alert “{k}”"


# What a secret can look like. SECRET, BEARER and _VALUE are copied exactly from the jobs' own scrub
# (nfl-weather/nflweather/runlog.py, the same in cfb-weather), and a test checks the copies stay the same:
# the value stops at whitespace and at the punctuation that ends a value in a URL, a list or a dict, and a
# name counts only where a word or a part of a name starts (ODDS_API_KEY, x-api-key, oddsApiKey, ?apiKey%3D),
# so words like "monkey", "keyword" or "KeyError" are left alone.
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
# The names of the projects' secret settings (their .env files hold these): whatever follows one is blanked,
# even where SECRET would not see a key (NTFY_TOPIC=..., "NTFY_TOPIC": "...", NTFY_TOPIC => ...).
ENV_NAMES = ("ODDS_API_KEY", "CFBD_API_KEY", "KAGGLE_KEY", "NTFY_TOPIC")
ENV_VALUE = re.compile(r"\b(?P<name>" + "|".join(ENV_NAMES) + r")(?P<mid>[\"']?\s*(?:=>|[:=]|%3[ad])\s*[\"'<\[(]*)"
                       r"(?P<value>" + _VALUE + ")", re.IGNORECASE)


def scrub(text: str) -> str:
    """Blank anything that looks like a key before it is shown (the value becomes ***). The jobs already do
    this to what they record; this is a second lock on the door, for everything else the page shows (logs,
    a scorer's error output). Unlike the jobs' copy it keeps line breaks, since some of what it shows has
    several lines."""
    def blank(m, mid=True):                             # a value already blanked ("apiKey=***`") is left as it is
        return m[0] if m["value"].startswith("***") else f"{m['name']}{m['mid'] if mid else ''}***"
    text = str(text or "")
    text = ENV_VALUE.sub(blank, text)
    text = SECRET.sub(blank, text)
    return BEARER.sub(lambda m: blank(m, mid=False), text)


def missing_columns(names: list[str]) -> str:
    """"is missing its run_utc column", "is missing its gameday and gametime columns"."""
    joined = names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]
    return f"is missing its {joined} column{'s' if len(names) > 1 else ''}"


def cap(s: str) -> str:
    """The first letter in capitals, unless the sentence starts with a file path (ops/RUN_RECORDS.md)."""
    if not s or re.match(r"^[\w.~-]+/", s):
        return s
    return s[:1].upper() + s[1:]


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
