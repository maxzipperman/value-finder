from datetime import datetime, time, timedelta
from datetime import tzinfo

def next_run(times: list[tuple[int, int]], now: datetime, tz: tzinfo) -> datetime | None:
    """The first scheduled run strictly after `now`, from a list of daily (hour, minute) times."""
    if not times:
        return None
    today = now.astimezone(tz).date()
    for d in (today, today + timedelta(days=1)):
        for h, m in sorted(times):
            t = datetime.combine(d, time(h, m), tzinfo=tz)
            if t > now:  # Changed from >= to > to ensure strictly after
                return t
    return None
