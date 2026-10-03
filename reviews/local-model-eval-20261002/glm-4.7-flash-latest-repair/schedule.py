from datetime import datetime, time, timedelta
from typing import List, Tuple, Optional, Union

def next_run(times: List[Tuple[int, int]], now: datetime, tz: Union[datetime.tzinfo, None]) -> Optional[datetime]:
    """The first scheduled run strictly after `now`, from a list of daily (hour, minute) times."""
    if not times:
        return None
    
    # Normalize 'now' to the target timezone to ensure accurate comparison
    now_tz = now.astimezone(tz)
    today = now_tz.date()
    
    # Iterate through today and tomorrow
    for days_offset in range(2):
        current_date = today + timedelta(days=days_offset)
        
        # Sort times to ensure we find the earliest valid slot for the day
        for h, m in sorted(times):
            candidate = datetime.combine(current_date, time(h, m), tzinfo=tz)
            
            # Strictly after 'now' (considering timezone)
            if candidate > now_tz:
                return candidate
                
    return None
