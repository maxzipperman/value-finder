"""Exact one-attempt offline missing proposal/transition. No send or key-loading path."""
import argparse
import copy
import fcntl
import hashlib
import json
import os
import stat
from pathlib import Path
import sys
sys.dont_write_bytecode = True
import epoch
import plan

ORIGINAL_ROOT = '059fc135b00bbbc36db208a8bb622d7444a43d42bb2607675d30671ad455f4e4'
STOPPED_SHA = 'fb9edfb65460c5f4fe84539ac2405b8e49d813dd5f9892bd32692bfbc86a4163'
REQUEST = '850c02077a7ef01010d277ad63cff3a88847548a9a1a70424fa8252ccf632c9a'
CACHE_SHA = '25923e8f5db247b52ed7b7ca2bdac5f938cbb0d7833e7aad90bdd0bd2dc917b6'



def regular_bytes(path):
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):raise ValueError('Regular evidence only')
        with os.fdopen(fd,'rb',closefd=False) as handle:return handle.read()
    finally:os.close(fd)


def cached_record(path, expected):
    data=regular_bytes(path)
    if hashlib.sha256(data).hexdigest()!=expected:raise ValueError('Pinned cached bytes changed')
    import pyarrow as pa
    import pyarrow.parquet as pq
    records=pq.read_table(pa.BufferReader(data)).to_pylist()
    if len(records)!=1:raise ValueError('Expected one cache record')
    return records[0]

def original(packet=None):
    packet = packet or Path(__file__).parent.parent / 'execution-v1/F2'
    # Verify v1 entirely from trusted recovery code BEFORE compiling it.
    paths = {f'code/{p.name}': p for p in packet.parent.glob('*.py')}
    if packet.is_symlink() or packet.parent.is_symlink(): raise ValueError('No symlink source')
    for p in packet.iterdir():
        if p.is_symlink() or not p.is_file(): raise ValueError('Regular original packet only')
        if p.name != 'FREEZE.json': paths[p.name] = p
    if any(p.is_symlink() or not p.is_file() for p in paths.values()): raise ValueError('Regular original code only')
    captured = {name: regular_bytes(p) for name,p in paths.items()}
    files = {name:hashlib.sha256(data).hexdigest() for name,data in sorted(captured.items())}
    cert = json.loads(regular_bytes(packet/'FREEZE.json'))
    if cert['root'] != ORIGINAL_ROOT or cert['files'] != files or hashlib.sha256(plan.canonical(files)).hexdigest()!=ORIGINAL_ROOT:
        raise ValueError('Original paid F2 bytes changed')
    import types
    old = types.ModuleType('immutable_original_f2'); old.__file__ = str(packet.parent/'epoch.py')
    exec(compile(captured['code/epoch.py'],old.__file__,'exec'),old.__dict__)
    m, rows = old.verify_packet(packet, ORIGINAL_ROOT)
    old.verify_source_plan(packet, packet.parent.parent/'acquisition/football-archive-v4', m, rows)
    return old, m, rows


def preview(bundle):
    old,m,rows=original()
    base=epoch.source_executor(bundle)
    old.pilot_gate(bundle)
    ledger=epoch.ROOT_BASE/ORIGINAL_ROOT/'spending-ledger.json'
    if plan.sha(ledger)!=STOPPED_SHA: raise ValueError('Exact stopped ledger pin differs')
    state=json.loads(ledger.read_text())
    row=next(r for r in rows if r['request_id']==REQUEST)
    a=state['attempts'][REQUEST]
    if (state['bundle_root_sha256']!=ORIGINAL_ROOT or state['pending']!=REQUEST or not state['stopped']
        or state['status']!='halted' or a['status']!='pending' or not a.get('send_started')
        or a['reserved_credits']!=20 or a['cache_key']!=row['cache_key'] or a['observed_http_status']!=404
        or a['observed_billing_headers']!={'x-requests-last':'0','x-requests-used':'93829','x-requests-remaining':'4906171'}
        or len(state['attempts'])!=418 or sum(x['reserved_credits'] for x in state['attempts'].values())!=8360
        or sum(x.get('billed_credits',0) for x in state['attempts'].values())!=8340):
        raise ValueError('Stopped reservation/send/billing/allowlist differs')
    if any(x['status']!='completed' for rid,x in state['attempts'].items() if rid!=REQUEST): raise ValueError('Another unresolved attempt')
    old.seed_state(state['predecessor_seed'], rows)
    _,read_record,*_=base.vendor_imports(bundle,ledger.parent)
    hits=list((ledger.parent/'data/raw'/row['sport']/row['source']).glob('*/'+row['cache_key']+'.parquet'))
    if len(hits)!=1 or plan.sha(hits[0])!=CACHE_SHA: raise ValueError('Exact 404 cache pin differs')
    record=cached_record(hits[0],CACHE_SHA); validate_missing(row,record)
    for done in rows:
        attempt=state['attempts'].get(done['request_id'])
        if not attempt or attempt['status']!='completed':continue
        receipt_path=ledger.parent/'receipts'/(done['request_id']+'.json')
        if plan.sha(receipt_path)!=attempt['receipt_sha256']:raise ValueError('Completed receipt changed')
        record_done=cached_record(Path(attempt['response_path']),attempt['response_sha256'])
        epoch.event_valid(done,record_done,base,json.loads((bundle/'protocol.json').read_text()))
        evidence=json.loads(regular_bytes(receipt_path))
        if evidence['record_sha256']!=attempt['response_sha256'] or evidence['request_id']!=done['request_id'] or evidence['cache_key']!=done['cache_key']:
            raise ValueError('Completed receipt identity differs')
    receipt={'request_id':REQUEST,'cache_key':row['cache_key'],'record_sha256':CACHE_SHA,
        'headers':json.loads(record['headers_json']),'record':record,'status':'missing',
        'reason':'hub-approved exact cached 404; no resend; full reservation retained'}
    receipt_sha=hashlib.sha256(base.canonical(receipt)+b'\n').hexdigest()
    proposal={'schema':'f2-one-404-v1','original_root':ORIGINAL_ROOT,'prior_ledger_sha256':STOPPED_SHA,
        'request_id':REQUEST,'cache_key':row['cache_key'],'response_path':str(hits[0].resolve()),
        'response_sha256':CACHE_SHA,'receipt_sha256':receipt_sha,'reserved_credits':20,'billed_credits':0,
        'request_list_sha256':m['request_list_sha256'],'request_set_sha256':m['request_set_sha256']}
    proposal_sha=hashlib.sha256(plan.canonical(proposal)).hexdigest()
    result=copy.deepcopy(state)
    result['attempts'][REQUEST].update(status='missing',billed_credits=0,response_path=proposal['response_path'],
        response_sha256=CACHE_SHA,receipt_sha256=receipt_sha,missing_resolution_proposal_sha256=proposal_sha)
    result['pending']=None;result['stopped']=None;result['status']='event_epoch_partial_reconciled'
    result['missing_resolution']={'proposal_sha256':proposal_sha,'prior_ledger_sha256':STOPPED_SHA,
        'request_id':REQUEST,'response_sha256':CACHE_SHA,'receipt_sha256':receipt_sha,
        'reason':'one approved terminal missing; reservations retained; continuation requires separate paid approval'}
    certificate={'proposal':proposal,'proposal_sha256':proposal_sha,'post_ledger_sha256':hashlib.sha256(base.canonical(result)+b'\n').hexdigest()}
    return certificate,result,receipt,rows


def validate_missing(row, record):
    if (record['cache_key']!=row['cache_key'] or record['sport']!=row['sport'] or record['source']!=row['source']
        or record['url']!=plan.BASE+row['path'] or json.loads(record['params_json'])!=row['params']
        or record['http_status']!=404):
        raise ValueError('404 identity/status differs')
    if not isinstance(json.loads(record['body']),dict) or json.loads(record['body']).get('error_code')!='EVENT_NOT_FOUND':
        raise ValueError('Exact missing error body differs')
    headers=json.loads(record['headers_json'])
    if any(headers.get(k)!=v for k,v in {'x-requests-last':'0','x-requests-used':'93829','x-requests-remaining':'4906171'}.items()):
        raise ValueError('404 billing differs')


def validate_approval(auth,certificate,base,commit=None):
    p=certificate['proposal'];line=(f"APPROVED offline missing: proposal {certificate['proposal_sha256']}, ledger {p['prior_ledger_sha256']}, "
        f"request {REQUEST}, response {CACHE_SHA}, commit {auth.get('execution_commit','')}")
    if (auth.get('status')!='approved' or auth.get('proposal_sha256')!=certificate['proposal_sha256']
        or auth.get('prior_ledger_sha256')!=STOPPED_SHA or auth.get('request_id')!=REQUEST or auth.get('response_sha256')!=CACHE_SHA
        or auth.get('hub_go_ahead',{}).get('comment_body','').splitlines().count(line)!=1
        or (commit is not None and auth.get('execution_commit')!=commit)):
        raise ValueError('Exact authenticated offline missing approval required')
    import re
    if (not re.fullmatch('[a-f0-9]{40}',auth.get('execution_commit',''))
        or not re.fullmatch(r'https://github\.com/maxzipperman/value-finder/pull/99#issuecomment-[0-9]+',auth['hub_go_ahead'].get('comment_url',''))):
        raise ValueError('Offline approval commit/comment invalid')


def transition(bundle, certificate_path, approval_path, *, fake_auth=False, checkpoint=lambda _:None):
    """Hub-only mutation; default CLI never calls this without --confirm-offline."""
    bundle=Path(bundle);certificate=json.loads(Path(certificate_path).read_text());auth=json.loads(Path(approval_path).read_text())
    base=epoch.source_executor(bundle)
    epoch.checkout_clean(Path(certificate_path).parent)
    root=json.loads((Path(certificate_path).parent/'FREEZE.json').read_text())['root']
    epoch.verify_packet(Path(certificate_path).parent,root)
    base.execution_context(Path(__file__).parent,ORIGINAL_ROOT,epoch.ROOT_BASE/ORIGINAL_ROOT)
    validate_approval(auth,certificate,base,base.checkout_commit(Path(__file__).parent))
    if not fake_auth: base.verify_live_hub_comment(auth)
    folder=epoch.ROOT_BASE/ORIGINAL_ROOT
    with (epoch.ROOT_BASE/'followup-purchase.lock').open('a') as global_lock, (folder/'acquisition.lock').open('a') as local_lock:
        fcntl.flock(global_lock,fcntl.LOCK_EX|fcntl.LOCK_NB);fcntl.flock(local_lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        current,state,receipt,_=preview(bundle)
        if current!=certificate: raise ValueError('Frozen transition certificate differs from exact evidence')
        proposal_sha=certificate['proposal_sha256']
        # Preserve the exact stopped bytes before any approval/receipt/ledger write.
        backup=folder/'recovery'/('original-ledger-'+STOPPED_SHA+'.json')
        stopped_bytes=regular_bytes(folder/'spending-ledger.json')
        if hashlib.sha256(stopped_bytes).hexdigest()!=STOPPED_SHA:raise ValueError('Stopped bytes changed')
        if backup.exists():
            if plan.sha(backup)!=STOPPED_SHA:raise ValueError('Original ledger backup conflicts')
        else:
            backup.parent.mkdir(parents=True,exist_ok=True)
            temporary=backup.with_suffix('.json.tmp')
            with temporary.open('xb') as handle:
                handle.write(stopped_bytes);handle.flush();os.fsync(handle.fileno())
            os.replace(temporary,backup);base.durable_directory(backup.parent)
        checkpoint('after_original_backup')
        approval_out=folder/('missing-approval-'+proposal_sha+'.json')
        receipt_out=folder/'receipts'/f'{REQUEST}.json'
        for path,obj in [(approval_out,auth),(receipt_out,receipt)]:
            expected=hashlib.sha256(base.canonical(obj)+b'\n').hexdigest()
            if path.exists() and plan.sha(path)!=expected: raise ValueError('Existing recovery evidence conflicts')
            if not path.exists():base.atomic(path,obj)
            checkpoint('after_approval' if path==approval_out else 'after_missing_receipt')
        if plan.sha(folder/'spending-ledger.json')!=STOPPED_SHA:raise ValueError('Stopped ledger changed before transition')
        base.atomic(folder/'spending-ledger.json',state)
        checkpoint('after_missing_transition')
        if plan.sha(folder/'spending-ledger.json')!=certificate['post_ledger_sha256']:raise ValueError('Post ledger differs')
        return {'status':state['status'],'ledger_sha256':certificate['post_ledger_sha256'],'reserved':8360,'billed':8340,'paid_calls':0}


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--bundle',type=Path,required=True)
    parser.add_argument('--certificate',type=Path,required=True);parser.add_argument('--approval',type=Path)
    parser.add_argument('--confirm-offline',action='store_true');args=parser.parse_args()
    if not args.confirm_offline:
        c,_,_,_=preview(args.bundle)
        if c!=json.loads(args.certificate.read_text()):raise SystemExit('Frozen offline proposal differs')
        print(json.dumps({'offline':True,'proposal':c,'paid_calls':0},indent=2))
    else:
        if not args.approval:raise SystemExit('Exact authenticated approval required')
        print(json.dumps(transition(args.bundle,args.certificate,args.approval),indent=2))
