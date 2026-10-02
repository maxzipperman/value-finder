"""LOCAL-BECAUSE: hardware: bounded owner-authorized local-model log triage.

Read two explicit run-record files. Own only a separate runtime directory.
No model tools, raw-error disclosure, source writes, repairs or external APIs.
"""
from __future__ import annotations
import argparse
import csv
import fcntl
import hashlib
import io
import json
import os
from pathlib import Path
import re
import tempfile
import subprocess
from datetime import datetime, timezone
import urllib.request

PROJECTS = ('nfl-weather', 'cfb-weather')
MODEL = 'qwen3.6:35b'
DIGEST = 'a7eb95c53bcf96b4bdd008d0fab4a5dac88047d9c1a7a9ab88ed453423fbd87c'
MAX_BYTES = 8 * 1024 * 1024
STEPS = ('building the board', 'saving the ledger', 'reading the alert state',
         'building the alerts', 'sending the alerts', 'saving the alert state')
CHECKS = {'building the board': 'connectivity', 'saving the ledger': 'disk_permissions',
          'reading the alert state': 'state_readability', 'building the alerts': 'code_review',
          'sending the alerts': 'notification_delivery', 'saving the alert state': 'disk_permissions',
          'run_note': 'state_readability', 'price_gap': 'cached_quota', 'unknown': 'source_review'}
CHECK_TEXT = {'connectivity': 'Check connectivity and the existing job log; do not rerun data requests.',
              'disk_permissions': 'Inspect available disk space and file permissions without changing them.',
              'state_readability': 'Inspect the alert-state warning and preserved backup; do not reset state.',
              'code_review': 'Review the alert-building exception in an isolated checkout.',
              'notification_delivery': 'Inspect the recorded delivery error; do not send a test notification.',
              'cached_quota': 'Inspect cached quota and price coverage; do not request fresh odds.',
              'source_review': 'Inspect this run record locally; keep any raw error and credentials private.'}

class SourceError(Exception):
    pass

def stamp(value):
    if not isinstance(value, str): raise ValueError('invalid timestamp')
    d = datetime.fromisoformat(value.strip().replace('Z', '+00:00'))
    if d.utcoffset() is None: raise ValueError('naive timestamp')
    return d.astimezone(timezone.utc)

def identity(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True).encode()).hexdigest()

def classify(error):
    text = str(error).lower()
    step = next((s for s in STEPS if text.startswith('while ' + s)), 'unknown')
    # Only fixed enums leave this function. No free-form log text is retained.
    kinds = [('timeout', r'timed?\s*out|timeout'), ('disk', r'no space|disk full'),
             ('permission', r'permission denied|permissionerror'),
             ('network', r'connection|network|dns|unreachable'),
             ('format', r'jsondecodeerror|valueerror|malformed|corrupt'),
             ('code', r'typeerror|attributeerror|keyerror|nameerror')]
    kind = next((k for k, pattern in kinds if re.search(pattern, text)), 'unspecified')
    return step, kind

def read_records(root, project, now):
    path = root / project / 'data/forward/runs.csv'
    if path.resolve() != path: raise SourceError('source_symlink')
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(fd, 'rb') as f:
            before = os.fstat(f.fileno());raw = f.read(MAX_BYTES + 1);after = os.fstat(f.fileno())
        if before.st_size != after.st_size or before.st_mtime_ns != after.st_mtime_ns:
            raise SourceError('source_changing')
        if len(raw) > MAX_BYTES: raise SourceError('source_too_large')
        if not raw.endswith(b'\n'): raise SourceError('source_incomplete')
        reader = csv.DictReader(io.StringIO(raw.decode('utf-8-sig')), strict=True)
        names = reader.fieldnames or []
        if len(names) != len(set(names)) or not {'run_utc','status','error'} <= set(names):
            raise SourceError('source_schema')
        records = []
        for number, row in enumerate(reader, 2):
            if number > 50002: raise SourceError('source_too_many_rows')
            if None in row or any(v is None for v in row.values()): raise SourceError('source_row_shape')
            try: t = stamp(row['run_utc'])
            except (ValueError, TypeError): raise SourceError('source_timestamp')
            status = row['status'].strip().lower()
            if status not in ('ok','failed'): raise SourceError('source_status')
            if t > now: raise SourceError('source_future_timestamp')
            step, kind = classify(row['error'])
            def number_or_none(name):
                v = row.get(name, '').strip()
                return int(v) if v.isascii() and v.isdecimal() else None
            records.append(dict(time=t, row=number, status=status, step=step, kind=kind,
                                note=bool(row['error'].strip()), games=number_or_none('games'),
                                priced=number_or_none('rule_priced')))
        if not records: raise SourceError('source_empty')
        return sorted(records, key=lambda r: (r['time'], r['row']))
    except SourceError: raise
    except FileNotFoundError: raise SourceError('source_missing')
    except (OSError, UnicodeError, csv.Error, ValueError): raise SourceError('source_unreadable')

def detect(root, project, now):
    try: rows = read_records(root, project, now)
    except SourceError as e:
        return dict(project=project, status='source_problem', step='unknown', kind=str(e),
                    run_utc=None, row=None, streak=1, check='source_review')
    latest = rows[-1]
    # This worker classifies recorded problems; the dashboard owns stale-job monitoring.
    if latest['status'] == 'failed':
        streak = 0
        for r in reversed(rows):
            if (r['status'],r['step'],r['kind']) != ('failed',latest['step'],latest['kind']): break
            streak += 1
        step,kind,status = latest['step'],latest['kind'],'failed'
        episode = rows[-streak]['time'].isoformat()
    elif latest['note']:
        step,kind,status,streak = 'run_note',latest['kind'],'warning',1
        episode = latest['time'].isoformat()
    else:
        gaps = 0
        for r in reversed(rows):
            if r['status'] != 'ok' or r['note'] or not r['games'] or r['priced'] != 0: break
            gaps += 1
        if gaps < 2: return None
        step,kind,status,streak = 'price_gap','missing_rule_prices','warning',gaps
        episode = rows[-gaps]['time'].isoformat()
    return dict(project=project, status=status, step=step, kind=kind,
                run_utc=latest['time'].isoformat(), row=latest['row'], streak=streak,
                episode_utc=episode, check=CHECKS[step])

def event_key(event):
    # One notice for first problem, one escalation to repeated failures, then quiet.
    return identity({k:event[k] for k in ('project','status','step','kind')} |
                    {'repeated': event['streak'] >= 2, 'episode':event.get('episode_utc')})

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs): raise ValueError('redirect forbidden')

def local_request(endpoint, payload=None):
    if endpoint not in ('tags','ps','chat'): raise ValueError('endpoint forbidden')
    request = urllib.request.Request('http://127.0.0.1:11434/api/' + endpoint,
        data=None if payload is None else json.dumps(payload).encode(),
        headers={'Content-Type':'application/json'})
    # Ignore proxy environment; never follow redirects away from loopback.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    with opener.open(request, timeout=60) as response:
        data = response.read(131073)
        if len(data) > 131072: raise ValueError('oversized response')
        return json.loads(data)

def memory_headroom():
    """Conservative Mac-only heuristic; not a precise available-byte estimate."""
    result = subprocess.run(['/usr/bin/memory_pressure','-Q'],capture_output=True,text=True,
                            timeout=5,check=True)
    match = re.search(r'System-wide memory free percentage:\s*(\d+)%',result.stdout)
    if not match: raise ValueError('memory_status_unknown')
    percent = int(match[1])
    if not 0 <= percent <= 100: raise ValueError('memory_status_unknown')
    return percent

def explain(events, request=local_request):
    resident = request('ps')
    if not isinstance(resident,dict) or not isinstance(resident.get('models'),list): raise ValueError('model_state_unknown')
    if resident['models']: raise ValueError('model_busy')
    if memory_headroom() < 45: raise ValueError('memory_headroom_low')
    inventory = request('tags')
    if not isinstance(inventory,dict) or not isinstance(inventory.get('models'),list): raise ValueError('model_inventory_unknown')
    tags = inventory['models']
    if not any(m.get('name') == MODEL and m.get('digest') == DIGEST for m in tags):
        raise ValueError('model_not_verified')
    facts = [dict(event_id=e['event_id'], project=e['project'], status=e['status'],
                  step=e['step'], classified_error=e['kind'], streak=e['streak'],
                  required_check=e['check']) for e in events]
    schema = {'type':'object','properties':{'explanations':{'type':'array','items':{
        'type':'object','properties':{'event_id':{'type':'string'},'summary':{'type':'string'},
                                    'check':{'type':'string','enum':list(CHECK_TEXT)}},
        'required':['event_id','summary','check'],'additionalProperties':False}}},
        'required':['explanations'],'additionalProperties':False}
    body = dict(model=MODEL, stream=False, think=False, keep_alive=0, format=schema,
        options=dict(temperature=0, num_ctx=8192, num_predict=700), messages=[
        dict(role='system',content='Explain only supplied operational facts in one short sentence per event. '
             'Error categories are tentative classifications, not established root causes. Do not claim repairs, '
             'data loss, successful runs or spending. Copy required_check exactly. No commands, URLs or tools. '
             'Never suggest rerunning jobs, obtaining new data, editing rules or resetting state.'),
        dict(role='user',content=json.dumps(facts))])
    result = request('chat', body)
    if result.get('done_reason') == 'length': raise ValueError('model_unfinished')
    value = json.loads(result['message']['content'])
    if not isinstance(value,dict) or set(value) != {'explanations'}: raise ValueError('model_schema')
    explanations = value['explanations'];expected = {e['event_id']:e for e in events};out = {}
    if not isinstance(explanations,list) or len(explanations) != len(events): raise ValueError('model_event_count')
    for item in explanations:
        if not isinstance(item,dict) or set(item) != {'event_id','summary','check'}: raise ValueError('model_schema')
        eid = item['event_id'];summary = item['summary']
        if not isinstance(eid,str) or eid not in expected or eid in out: raise ValueError('model_event_id')
        if item['check'] != expected[eid]['check']: raise ValueError('model_check')
        if not isinstance(summary,str) or not 1 <= len(summary) <= 300 or any(ord(c)<32 for c in summary) or '://' in summary:
            raise ValueError('model_summary')
        out[eid] = summary
    return out

def atomic_json(path, value):
    fd, name = tempfile.mkstemp(prefix=path.name+'.',dir=path.parent)
    tmp = Path(name)
    try:
        with os.fdopen(fd,'w') as f:
            json.dump(value,f,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
        os.replace(tmp,path)
    finally:
        tmp.unlink(missing_ok=True)

def run(root, runtime, now=None, inference=explain):
    root = Path(root).resolve(strict=True);runtime = Path(runtime).absolute()
    if runtime.resolve() != runtime or runtime.is_relative_to(root): raise ValueError('runtime must be outside source root without symlinks')
    runtime.mkdir(parents=True,exist_ok=True,mode=0o700)
    now = now or datetime.now(timezone.utc)
    if now.utcoffset() is None: raise ValueError('now must be aware')
    lock_fd = os.open(runtime/'worker.lock',os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW,0o600)
    with os.fdopen(lock_fd,'r+') as lock:
        try: fcntl.flock(lock,fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError: return dict(status='quiet',reason='already_running')
        state_path = runtime/'state.json'
        if state_path.is_symlink(): raise ValueError('state symlink forbidden')
        state = json.loads(state_path.read_text()) if state_path.exists() else {'version':1,'active':{}}
        if not isinstance(state,dict) or set(state) != {'version','active'} or type(state['version']) is not int or state['version'] != 1 or not isinstance(state['active'],dict):
            raise ValueError('invalid state; preserve it for review')
        if not set(state['active']) <= set(PROJECTS) or any(not isinstance(v,str) or not re.fullmatch('[0-9a-f]{64}',v) for v in state['active'].values()):
            raise ValueError('invalid state entries; preserve them for review')
        active = {};new = [];recovered = []
        for project in PROJECTS:
            event = detect(root,project,now)
            if event is not None:
                key = event_key(event);active[project] = key
                if state['active'].get(project) != key:
                    event['event_id'] = key;new.append(event)
            elif project in state['active']: recovered.append(project)
        if not new and not recovered: return dict(status='quiet',reason='healthy_or_unchanged')
        # Stable identity provides report replay after a state-write crash.
        report_id = identity({'active':active,'recovered':recovered,'previous':state['active']})
        reports = runtime/'reports';reports.mkdir(exist_ok=True,mode=0o700)
        if reports.resolve() != reports: raise ValueError('reports symlink forbidden')
        report_path = reports/(report_id + '.json')
        if report_path.is_symlink(): raise ValueError('report symlink forbidden')
        if not report_path.exists():
            summaries = {};model_status = 'not_needed'
            infer_events = [e for e in new if e['status'] != 'source_problem']
            if infer_events:
                try: summaries = inference(infer_events);model_status = 'local_model'
                except Exception: model_status = 'deterministic_fallback'
            report = dict(report_id=report_id,created_utc=now.astimezone(timezone.utc).isoformat(),
                          model_status=model_status,model=MODEL if model_status=='local_model' else None,
                          recovered=recovered,events=[])
            for event in new:
                report['events'].append(event | dict(
                    source=str(root/event['project']/'data/forward/runs.csv'),
                    verified_fact=f"{event['project']}: {event['status']}; step {event['step']}; {event['streak']} matching recorded problem(s).",
                    next_check=CHECK_TEXT[event['check']],
                    ai_draft=summaries.get(event['event_id'])))
            atomic_json(report_path,report)
        atomic_json(state_path,{'version':1,'active':active})
        return dict(status='report',report=str(report_path),report_id=report_id,
                    new_problems=len(new),recovered=recovered)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root',type=Path,required=True)
    parser.add_argument('--runtime',type=Path,required=True)
    args = parser.parse_args()
    try: print(json.dumps(run(args.source_root,args.runtime)))
    except Exception:
        # Do not print raw exceptions: their text may contain private values.
        print(json.dumps({'status':'worker_error','reason':'state_or_runtime_error; preserve files for review'}))
        raise SystemExit(1)
