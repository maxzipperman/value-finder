from datetime import datetime, time, timedelta

def next_run(times: list[tuple[int, int]], now: datetime, tz) -> datetime | None:
    """The first scheduled run strictly after `now`, from a list of daily (hour, minute) times."""
    if not times:
        return None

    # Normalize 'now' to the target timezone to ensure accurate comparison
    now_tz = now.astimezone(tz)

    today = now_tz.date()

    # Check today and tomorrow
    for days_offset in (0, 1):
        current_date = today + timedelta(days=days_offset)
        for h, m in sorted(times):
            # Construct the datetime in the target timezone
            candidate = datetime.combine(current_date, time(h, m), tzinfo=tz)

            # Check if strictly after 'now'
            if candidate > now_tz:
                return candidate

    return None
