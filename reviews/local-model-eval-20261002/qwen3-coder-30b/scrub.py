import re

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
    return text
