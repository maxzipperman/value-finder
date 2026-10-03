"""Exact halt reconciliation preparation/installation and untouched successor.

Prepare is read-only on runtime; writes only a new isolated proposal directory.
Install is hub-only, no GET to provider, no resend, requires live exact approval.
Successor uses identical committed seed/frame/protocol/selection; no randomness.
"""
import argparse
import copy
import fcntl
import hashlib
import json
from pathlib import Path
import sys
import os
import stat
import types


def canonical(v):return json.dumps(v,sort_keys=True,separators=(',',':'),default=str,allow_nan=False).encode()
def sha(raw):return hashlib.sha256(raw).hexdigest()


def regular(path):
    path=Path(path).absolute()
    if any(p.is_symlink() for p in (path,*path.parents)):raise ValueError('symlink source input')
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):raise ValueError('regular source input required')
        with os.fdopen(fd,'rb',closefd=False) as h:return h.read()
    finally:os.close(fd)


def captured(raw,path,name):
    module=types.ModuleType(name);module.__file__=str(path)
    exec(compile(raw,str(path),'exec'),module.__dict__)
    return module


def packet_builder(repo,expected=None):
    path=repo/'strategy-research/coverage-pilot-packet-v1/build.py'
    raw=regular(path)
    if expected is not None:
        if sha(raw)!=expected['packet_builder'] or sha(regular(Path(__file__)))!=expected['recovery_builder']:
            raise ValueError('reviewed recovery builder differs before execution')
    return captured(raw,path,'recovery_packet_builder')


def loader(repo, expected=None):
    repo=Path(repo).absolute();build=packet_builder(repo,expected)
    pilot=repo/'strategy-research/coverage-pilot-v1'
    bootstrap_raw=regular(pilot/'bootstrap.py')
    pin=expected['bootstrap'] if expected is not None else sha(bootstrap_raw)
    boot=build.pinned_module(bootstrap_raw,pilot/'bootstrap.py','recovery_bootstrap',pin)
    paths={n:pilot/(n+'.py') for n in boot.MODULES}
    paths.update(capture=repo/'strategy-research/football-metadata-v1/capture.py',history=repo/'strategy-research/football-metadata-v1/history.py',plan=repo/'strategy-research/nfl-props-archive-v1/plan.py',f2_gate=repo/'strategy-research/football_archive/f2_handoff.py',older_recovery=repo/'strategy-research/football_archive/older-recovery-v1/recovery.py')
    inventory={n:sha(regular(p)) for n,p in paths.items()};full=dict(inventory,packet_builder=sha(regular(repo/'strategy-research/coverage-pilot-packet-v1/build.py')),recovery_builder=sha(regular(Path(__file__))))
    if expected is not None and full!=expected:raise ValueError('reviewed recovery code differs')
    boot,load,source,bundle,paths=build.closure(repo,{'source_code_sha256':inventory})
    return build,boot,load,source,bundle,paths,full


def old_data(packet,boot,root):
    cert=json.loads(boot.regular(packet/'FREEZE.json'))
    if cert['root']!=root or sha(boot.canonical(cert['files']))!=root:raise ValueError('old packet root differs')
    data={n:boot.regular(packet/n) for n in boot.PACKET}
    if any(sha(v)!=cert['files'][n] for n,v in data.items()):raise ValueError('old frozen data differs')
    return data,cert


def prepare(args):
    # Confinement before runtime reads/writes.
    build=packet_builder(args.repo)
    repo,out=build.validate_output(args.repo,args.output)
    build,boot,load,source,bundle,paths,inventory=loader(repo)
    capture=load('capture');q=load('quarantine');base=load('executor');root=q.ROOT
    data,oldcert=old_data(args.old_packet,boot,root);rows=json.loads(data['requests.json']);policy=json.loads(data['policy.json'])
    runtime=base.RUNTIME_BASE/root;ledger=runtime/'spending-ledger.json';before=capture.regular(ledger)
    if sha(before)!=q.BEFORE:raise ValueError('halted ledger differs')
    state=json.loads(before);row=next(r for r in rows if r['request_id']==q.RID)
    expected=runtime/'data/raw'/row['sport']/row['source']/row['requested_utc'][:10]/(row['cache_key']+'.parquet')
    raw=capture.regular(expected)
    if sha(raw)!=q.RAW:raise ValueError('exact cached response differs')
    import pyarrow as pa
    import pyarrow.parquet as pq
    records=pq.read_table(pa.BufferReader(raw)).to_pylist()
    if len(records)!=1:raise ValueError('single saved response required')
    other=copy.deepcopy(state);other['attempts'].pop(q.RID)
    load('evidence').captured_receipts(runtime,rows,other,policy)
    after,receipt=q.transition(state,row,records[0],policy,base,json.loads(source['protocol.json']),expected)
    untouched=[r for r in rows if r['request_id'] not in state['attempts']]
    if len(untouched)!=729 or sum(r['max_new_credits'] for r in untouched)!=36810:raise ValueError('untouched scope differs')
    oldmap=json.loads(data['mappings.json']);affected=[m['game_id'] for m in oldmap if q.RID in m['request_ids']]
    marker=base.RUNTIME_BASE/'registrations'/(root+'.json');init=runtime/'INITIALIZED.json'
    cert=dict(version=1,source_root=root,quarantined_request_id=q.RID,before_ledger_sha256=sha(before),after_ledger_sha256=sha(base.canonical(after)+b'\n'),receipt_sha256=sha(receipt),cache_sha256=q.RAW,cache_path=str(expected),runtime_path=str(runtime),marker_sha256=capture.sha(marker),initialization_sha256=capture.sha(init),attempted_ids=sorted(state['attempts']),untouched_ids=sorted(r['request_id'] for r in untouched),untouched_count=729,untouched_cap=36810,scope_sha256=capture.identity(untouched),affected_selected_game_ids=affected,selected_denominator=430,seed_record_sha256=capture.identity(json.loads(data['draw.json'])),frame_sha256=sha(data['frame.json']),original_request_list_sha256=sha(data['requests.json']),original_policy_sha256=sha(data['policy.json']),billed_before=180,observed_pending_bill=30,billed_after=210,reservations_retained=270,carried_conservative_debit=170576,usable_quote=False,no_resend=True,next_purchase_authorized=False,code_inventory=inventory)
    if capture.sha(ledger)!=q.BEFORE:raise ValueError('ledger changed during preparation')
    out.mkdir(mode=0o700)
    for name,raw in {'certificate.json':canonical(cert),'before-ledger.json':before,'after-ledger.json':base.canonical(after)+b'\n','untouched-requests.json':canonical(untouched)}.items():
        import os
        with (out/name).open('xb') as h:h.write(raw);h.flush();os.fsync(h.fileno())
    base.durable_directory(out)
    # write_once's canonical encoding matches base for metadata, verify exact hashes.
    if capture.sha(out/'after-ledger.json')!=cert['after_ledger_sha256'] or capture.sha(out/'before-ledger.json')!=q.BEFORE:raise ValueError('proposal encoding changed')
    return dict(certificate_path=str(out/'certificate.json'),certificate_sha256=capture.sha(out/'certificate.json'),after_ledger_sha256=cert['after_ledger_sha256'],untouched_count=729,untouched_cap=36810,paid_calls=0,runtime_modified=False)


def install(args):
    # Only hub invokes --confirm-offline; no paid API/client imported or invoked.
    cert=json.loads(regular(args.certificate))
    if sha(canonical(cert))!=args.certificate_sha256:raise ValueError('external certificate differs')
    build,boot,load,source,bundle,paths,inventory=loader(args.repo,cert['code_inventory'])
    capture=load('capture');q=load('quarantine');base=load('executor')
    approval=json.loads(boot.regular(args.approval));binding=dict(certificate=cert,certificate_sha256=args.certificate_sha256,approval=approval)
    q.verify_approval(binding)
    runtime=base.RUNTIME_BASE/q.ROOT;ledger=runtime/'spending-ledger.json'
    with (base.RUNTIME_BASE/'followup-purchase.lock').open('rb') as shared,(runtime/'acquisition.lock').open('rb') as local:
        fcntl.flock(shared,fcntl.LOCK_EX|fcntl.LOCK_NB);fcntl.flock(local,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if capture.sha(ledger)!=q.BEFORE or capture.sha(base.RUNTIME_BASE/'registrations'/(q.ROOT+'.json'))!=cert['marker_sha256'] or capture.sha(runtime/'INITIALIZED.json')!=cert['initialization_sha256']:raise ValueError('exact installed prestate differs')
        data,_=old_data(args.old_packet,boot,q.ROOT);rows=json.loads(data['requests.json']);state=capture.read(ledger);row=next(r for r in rows if r['request_id']==q.RID)
        raw=capture.regular(cert['cache_path'])
        if sha(raw)!=q.RAW:raise ValueError('quarantine cache changed')
        import pyarrow as pa
        import pyarrow.parquet as pq
        records=pq.read_table(pa.BufferReader(raw)).to_pylist()
        if len(records)!=1:raise ValueError('single saved response required')
        rec=records[0]
        other=copy.deepcopy(state);other['attempts'].pop(q.RID)
        load('evidence').captured_receipts(runtime,rows,other,json.loads(data['policy.json']))
        after,receipt=q.transition(state,row,rec,json.loads(data['policy.json']),base,json.loads(source['protocol.json']),cert['cache_path'])
        if sha(base.canonical(after)+b'\n')!=cert['after_ledger_sha256'] or sha(receipt)!=cert['receipt_sha256']:raise ValueError('approved transition changed')
        q.verify_approval(binding)  # last authority check before mutations
        backup=runtime/'quarantine-before-ledger.json'
        if backup.exists():
            if capture.sha(backup)!=q.BEFORE:raise ValueError('backup differs')
        else:base.atomic(backup,state)
        saved=runtime/'receipts'/(q.RID+'.json')
        if saved.exists():
            if capture.sha(saved)!=cert['receipt_sha256']:raise ValueError('existing quarantine receipt differs')
        else:base.atomic(saved,json.loads(receipt))
        base.atomic(ledger,after)
        q.verify_partial(runtime,rows,after,json.loads(data['policy.json']),cert)
        return dict(status='pilot_partial_reconciled',billed=210,reserved=270,untouched=729,paid_calls=0)


def successor(args):
    cert=json.loads(regular(args.certificate))
    if sha(canonical(cert))!=args.certificate_sha256:raise ValueError('certificate changed')
    build=packet_builder(args.repo,cert['code_inventory'])
    repo,out=build.validate_output(args.repo,args.output)
    build,boot,load,source,bundle,paths,inventory=loader(repo,cert['code_inventory']);capture=load('capture');q=load('quarantine');base=load('executor')
    data,oldcert=old_data(args.old_packet,boot,q.ROOT);rows=json.loads(data['requests.json']);policy=json.loads(data['policy.json']);oldbaseline=json.loads(data['baseline.json']);cache=json.loads(data['overlap.json'])
    approval=json.loads(boot.regular(args.approval));binding=dict(certificate=cert,certificate_sha256=args.certificate_sha256,approval=approval)
    q.verify_approval(binding)
    runtime=base.RUNTIME_BASE/q.ROOT;state=capture.read(runtime/'spending-ledger.json');q.verify_partial(runtime,rows,state,policy,cert)
    # Old exact base seven stores plus one reviewed certified partial. No hiding roots.
    pilots={q.ROOT:dict(ledger_sha256=cert['after_ledger_sha256'],marker_sha256=cert['marker_sha256'],initialization_sha256=cert['initialization_sha256'],rows=rows,policy=policy,predecessor_snapshot=capture.identity(oldbaseline['expected_global_snapshot']),authorization_sha256=state['authorization_sha256'],plan_sha256=q.ROOT,reconciliation=binding)}
    def baseline(ledgers,markers):return load('baseline').verify_base(ledgers,markers,oldbaseline['base_snapshot'],source['request-manifest.json'],oldbaseline['historical_bindings'])
    with (base.RUNTIME_BASE/'followup-purchase.lock').open('rb') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        snapshot,carry=load('evidence').global_union(base.RUNTIME_BASE,oldbaseline['base_snapshot'],pilots,baseline)
        attempts=state['attempts'];new=[r for r in rows if r['request_id'] not in attempts]
        if capture.identity(new)!=cert['scope_sha256'] or len(new)!=729 or sum(r['max_new_credits'] for r in new)!=36810:raise ValueError('same-draw residual differs')
        by_id={r['request_id']:r for r in rows};maps=json.loads(data['mappings.json'])
        for item in maps:
            old=list(item['request_ids']);item['request_ids']=[r for r in old if r not in attempts]
            for rid in old:
                if rid not in attempts:continue
                r=by_id[rid];a=attempts[rid];claim=dict(root=q.ROOT,request_id=rid,receipt_sha256=a['receipt_sha256'],response_sha256=a['response_sha256'])
                if r['source']=='oddsapi/hist_odds':item.setdefault('reused_request_ids',[]).append(rid);item.setdefault('reused_evidence',[]).append(claim)
                else:item.setdefault('reused_slots',[]).append(dict(sport=r['sport'],event_id=r['event_id'],requested_utc=r['requested_utc'],books=r['params']['bookmakers'].split(','),markets=r['params']['markets'].split(','),evidence=[claim]))
            if q.RID in old:item['coverage_disposition']=dict(classification='failure',reason='certified_quarantined_response',request_ids=[q.RID])
            item['reason']=None if item['request_ids'] else 'all_designated_cells_receipt_authenticated'
        load('overlap').check_internal(new,maps);load('evidence').authenticate_reuse(base.RUNTIME_BASE,snapshot,maps,frozen_source={'freeze':boot.regular(bundle/'FREEZE.json'),'files':source})
        rawroots=sorted(set(cache['raw_roots'])|{str((runtime/'data/raw').absolute())});inv={}
        for root in rawroots:
            for sport in ('americanfootball_nfl','americanfootball_ncaaf'):
                for src in ('oddsapi/hist_odds','oddsapi/hist_event_odds','oddsapi/hist_event_markets'):
                    for p in (Path(root)/sport/src).glob('*/*.parquet'):
                        if '2020-01-01'<=p.parent.name<'2026-02-10':inv[str(p)]=capture.sha(p)
        cache.update(raw_roots=rawroots,inventory_sha256=capture.identity(inv));load('overlap').check(new,rawroots,expected_inventory_sha256=cache['inventory_sha256'])
        # Response-only acquisition amendment. Seed/frame/protocol/selected files unchanged.
        newpolicy=build.missing_policy(new);newpolicy['quote_policy']={'decimal_one':'retain_raw_non_executable'}
        data.update({'requests.json':canonical(new),'mappings.json':canonical(maps),'policy.json':canonical(newpolicy),'overlap.json':canonical(cache),'baseline.json':canonical(dict(base_snapshot=oldbaseline['base_snapshot'],expected_global_snapshot=snapshot,historical_bindings=oldbaseline['historical_bindings'],pilot_bindings=pilots))})
        manifest=json.loads(data['manifest.json']);manifest.update(request_count=729,max_new_credits=36810,request_list_sha256=sha(data['requests.json']),request_set_sha256=capture.identity(new),response_policy_amendment='retain_literal_decimal_one_as_non_executable_only',predecessor_root=q.ROOT,reconciliation_certificate_sha256=args.certificate_sha256)
        data['manifest.json']=canonical(manifest)
        files={n:sha(v) for n,v in data.items()};files.update({'code/'+n+'.py':capture.sha(p) for n,p in paths.items() if n in boot.MODULES|{'capture','history','plan','f2_gate','older_recovery'}})
        files['policy/older-PROTOCOL.md']=capture.sha(repo/'strategy-research/football_archive/older-recovery-v1/PROTOCOL.md');files['policy/PRIMARY-CONTRACT.json']=capture.sha(repo/'strategy-research/coverage-pilot-v1/PRIMARY-CONTRACT.json');files['source/FREEZE.json']=capture.sha(bundle/'FREEZE.json');root=sha(boot.canonical(files))
        build.validate_output(repo,out)
        q.verify_partial(runtime,rows,capture.read(runtime/'spending-ledger.json'),policy,cert)
        again,againcarry=load('evidence').global_union(base.RUNTIME_BASE,oldbaseline['base_snapshot'],pilots,baseline)
        if again!=snapshot or againcarry!=carry:raise ValueError('history changed during assembly')
        out.mkdir(mode=0o700)
        for n,raw in data.items():
            with (out/n).open('xb') as h:h.write(raw);h.flush();os.fsync(h.fileno())
        load('evidence').write_once(out/'FREEZE.json',dict(root=root,files=files))
        base.durable_directory(out)
        runner,_,packet,shared,_=boot.verified(out,root,bundle);result=runner.packet(packet,shared)
        return dict(result,root=root,carried_debit=carry['conservative_debit'],same_seed=True,quarantined_selected_game_failure=True,paid_calls=0)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=('prepare','install','successor'))
    p.add_argument('--repo',type=Path,required=True);p.add_argument('--old-packet',type=Path,required=True);p.add_argument('--output',type=Path)
    p.add_argument('--certificate',type=Path);p.add_argument('--certificate-sha256');p.add_argument('--approval',type=Path);p.add_argument('--confirm-offline',action='store_true')
    a=p.parse_args()
    if a.mode=='install' and not a.confirm_offline:p.error('hub-only explicit offline installation required')
    print(json.dumps({'prepare':prepare,'install':install,'successor':successor}[a.mode](a),sort_keys=True))
