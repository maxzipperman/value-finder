from datetime import datetime, timezone
UTC=timezone.utc
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