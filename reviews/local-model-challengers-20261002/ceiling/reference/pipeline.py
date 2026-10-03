from times import instant
from quotes import select
from runs import reconcile

def snapshot(quote_rows,run_rows,event,asof):
    at=instant(asof)
    if not isinstance(event,str) or not event:
        raise ValueError('invalid event')
    quotes=select(quote_rows,event,at); runs=reconcile(run_rows,at)
    return {'quotes':quotes,'runs':runs,'successful_rows':sum(row['downloaded_rows'] for row in runs.values() if row['status'] in ('ok','partial')),'failures':sorted(job for job,row in runs.items() if row['status']=='failed'),'partial_jobs':sorted(job for job,row in runs.items() if row['status']=='partial'),'unknown_jobs':sorted(job for job,row in runs.items() if row['status']=='pending')}
