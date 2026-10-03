import math
from times import instant

def probability(value):
    if isinstance(value,bool) or not isinstance(value,(int,float,str)):
        raise ValueError('invalid odds')
    try:
        v=float(value)
    except (ValueError,TypeError,OverflowError) as exc:
        raise ValueError('invalid odds') from exc
    if not math.isfinite(v) or abs(v)<100:
        raise ValueError('invalid odds')
    return 100/(v+100) if v>0 else (-v)/((-v)+100)

def select(rows,event,asof):
    at=instant(asof)
    if not isinstance(event,str) or not event:
        raise ValueError('invalid event')
    picked={}; ranks={}
    for row in rows:
        if not isinstance(row,dict):
            continue
        try:
            if any(not isinstance(row[k],str) or not row[k] for k in ('id','book','event')) or row['event']!=event:
                continue
            observed=instant(row['observed_at']); expiry=instant(row['expires_at']); update=instant(row['last_update'])
            p=probability(row['odds'])
            if not (observed<=at<expiry and update<=observed):
                continue
            key=row['book']; rank=(observed,row['id'])
            old=ranks.get(key)
            if old is None or observed>old[0] or (observed==old[0] and row['id']<old[1]):
                ranks[key]=rank; picked[key]={'row':row,'probability':p}
        except (KeyError,ValueError,TypeError,OverflowError):
            continue
    return picked
