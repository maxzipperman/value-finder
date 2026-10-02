from datetime import datetime, timedelta, time, tzinfo
from typing import Optional


def next_run(times: list[tuple[int, int]], now: datetime, tz: tzinfo) -> Optional[datetime]:
    """The first scheduled run strictly after `now`, from a list of daily (hour, minute) times."""
    if not times:
        return None
    
    # Convert now to the target timezone for accurate comparison
    now_in_tz = now.astimezone(tz)
    
    # Get today's date in the target timezone
    today = now_in_tz.date()
    
    # Check today and tomorrow
    for d in (today, today + timedelta(days=1)):
        # Sort times to ensure we find the earliest one first
        sorted_times = sorted(times)
        for h, m in sorted_times:
            t = datetime.combine(d, time(h, m), tzinfo=tz)
            # STRICTLY AFTER now
            if t > now_in_tz:
                return t
    
    return None
