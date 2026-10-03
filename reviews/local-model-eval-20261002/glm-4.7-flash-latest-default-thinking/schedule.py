from datetime import datetime, time, timedelta, tzinfo

def next_run(times: list[tuple[int, int]], now: datetime, tz: tzinfo) -> datetime | None:
    """The first scheduled run strictly after `now`, from a list of daily (hour, minute) times."""
    if not times:
        return None

    # Normalize 'now' to the target timezone to ensure accurate comparison
    target_now = now.astimezone(tz)
    today = target_now.date()

    # Sort times to ensure we return the earliest valid candidate
    sorted_times = sorted(times)

    # Check the schedule for today and tomorrow
    for day_offset in (0, 1):
        candidate_date = today + timedelta(days=day_offset)
        for hour, minute in sorted_times:
            run_time = datetime.combine(candidate_date, time(hour, minute), tzinfo=tz)
            if run_time > target_now:
                return run_time

    return None
