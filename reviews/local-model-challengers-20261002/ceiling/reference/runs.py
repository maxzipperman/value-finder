from times import instant

def reconcile(rows,asof):
    at=instant(asof); unique={}; stamps={}
    for row in rows:
        if not isinstance(row,dict):
            continue
        try:
            if any(not isinstance(row[k],str) or not row[k] for k in ('run_id','job')):
                continue
            if type(row['attempt']) is not int or row['attempt']<=0 or type(row['downloaded_rows']) is not int or row['downloaded_rows']<0:
                continue
            status=row['status']
            if not isinstance(status,str) or status not in ('ok','partial','failed','pending') or (status in ('failed','pending') and row['downloaded_rows']!=0):
                continue
            observed=instant(row['observed_at'])
            if observed>at:
                continue
            identity=row['run_id']
            if identity not in stamps or observed>stamps[identity]:
                unique[identity]=row;stamps[identity]=observed
        except (KeyError,ValueError,TypeError,OverflowError):
            continue
    picked={}; ranks={}
    for identity,row in unique.items():
        key=row['job']; stamp=stamps[identity]; rank=(row['attempt'],stamp,identity); old=ranks.get(key)
        if old is None or rank[0]>old[0] or (rank[0]==old[0] and (rank[1]>old[1] or (rank[1]==old[1] and rank[2]<old[2]))):
            picked[key]=row;ranks[key]=rank
    return picked
