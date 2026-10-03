"""Idempotent close output application; no HTTP, authority or scheduling decisions.

A durable prepared record binds the exact before/after bytes for CSV and state.
After a crash, finish those same outputs; never append the rows a second time.
The persistent output lock is acquired only outside account admission's lock.
"""
import fcntl
import json
import os
from pathlib import Path
import tempfile

from ops.collector_guard import Blocked, atomic_json, digest


def _read(path):
    if path.is_symlink():
        raise Blocked('Close application symlink rejected')
    return path.read_text() if path.exists() else None


def _write(path, text):
    fd, name = tempfile.mkstemp(prefix=path.name+'.',dir=path.parent)
    try:
        with os.fdopen(fd,'w') as stream:
            stream.write(text);stream.flush();os.fsync(stream.fileno())
        os.replace(name,path)
        directory=os.open(path.parent,os.O_RDONLY)
        try:os.fsync(directory)
        finally:os.close(directory)
    finally:
        if os.path.exists(name):os.unlink(name)


def _paths(csv, state):
    csv,state=Path(csv),Path(state)
    if csv.parent!=state.parent or csv.name!='closes.csv' or state.name!='close_state.json':
        raise Blocked('Close outputs must share one directory')
    state.parent.mkdir(parents=True,exist_ok=True)
    return csv,state,state.parent/'close_apply_pending.json',state.parent/'close_apply.lock'


def _finish(csv,state,pending):
    raw=_read(pending)
    if raw is None:return
    try:
        txn=json.loads(raw)
        if (set(txn)!={'version','observation','before_csv','after_csv','before_state','after_state','phase','sha256'}
                or txn['version']!=1 or txn['phase'] not in {'prepared','complete'}):
            raise ValueError('Transaction schema')
        bound={k:v for k,v in txn.items() if k not in {'phase','sha256'}}
        if digest(json.dumps(bound,sort_keys=True).encode())!=txn['sha256']:
            raise ValueError('Transaction identity')
        current_csv,current_state=_read(csv),_read(state)
        if current_csv not in (txn['before_csv'],txn['after_csv']) or current_state not in (txn['before_state'],txn['after_state']):
            raise ValueError('Output conflicts with prepared observation')
        if current_state==txn['after_state'] and current_csv!=txn['after_csv']:
            raise ValueError('State committed before CSV; impossible application order')
        if txn['phase']=='complete':
            if current_csv!=txn['after_csv'] or current_state!=txn['after_state']:
                raise ValueError('Completed observation outputs changed')
            return
        if current_csv!=txn['after_csv']:
            if txn['after_csv'] is None:raise ValueError('Unexpected CSV removal')
            _write(csv,txn['after_csv'])
        if current_state!=txn['after_state']:_write(state,txn['after_state'])
        txn['phase']='complete';atomic_json(pending,txn)
    except (KeyError,ValueError,TypeError):
        raise Blocked('Close output transaction invalid; no automatic replacement') from None


def recover(csv,state):
    """Finish a prepared observation before reading selection/counters or paid HTTP."""
    csv,state,pending,lock=_paths(csv,state)
    if lock.is_symlink():raise Blocked('Close output lock symlink rejected')
    with lock.open('a+') as handle:
        fcntl.flock(handle,fcntl.LOCK_EX)
        _finish(csv,state,pending)


def seen(state, observation):
    return observation in state.get('applied_observations',[])


def apply(csv,state,observation,*,before_state,rows=None,slots=(),complete=(),max_tries=2):
    """Apply one conclusive response. `rows=None` preserves existing empty-feed handling.

    Rows are a DataFrame. Caller keeps its original columns/eligibility/matching.
    Counter changes and replay marker commit in the same desired state bytes.
    """
    csv,state,pending,lock=_paths(csv,state)
    if lock.is_symlink():raise Blocked('Close output lock symlink rejected')
    with lock.open('a+') as handle:
        fcntl.flock(handle,fcntl.LOCK_EX)
        _finish(csv,state,pending)
        old_csv,old_state=_read(csv),_read(state)
        current=json.loads(old_state) if old_state is not None else {'captured':[]}
        current.setdefault('tries',{})
        if seen(current,observation):return current
        if current!=before_state:raise Blocked('Close state changed since selection; restart from saved receipt')
        final=json.loads(json.dumps(current))
        after_csv=old_csv
        if rows is not None:
            after_csv=(old_csv or '')+rows.to_csv(index=False,header=old_csv is None)
            for kickoff in slots:
                final['tries'][kickoff]=final['tries'].get(kickoff,0)+1
                if kickoff in complete or final['tries'][kickoff]>=max_tries:
                    final['captured']=sorted(set(final['captured'])|{kickoff})
        final['applied_observations']=current.get('applied_observations',[])+[observation]
        txn=dict(version=1,observation=observation,before_csv=old_csv,after_csv=after_csv,
                 before_state=old_state,after_state=json.dumps(final,sort_keys=True))
        txn['sha256']=digest(json.dumps(txn,sort_keys=True).encode())
        txn['phase']='prepared';atomic_json(pending,txn)
        _finish(csv,state,pending)
        return final
