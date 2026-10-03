from datetime import datetime, timezone

def instant(value):
    try:
        if isinstance(value,str):
            value=datetime.fromisoformat(value)
        if not isinstance(value,datetime) or value.tzinfo is None or value.utcoffset() is None:
            raise ValueError('aware timestamp required')
        return value.astimezone(timezone.utc)
    except (ValueError,TypeError,OverflowError) as exc:
        raise ValueError('invalid timestamp') from exc
