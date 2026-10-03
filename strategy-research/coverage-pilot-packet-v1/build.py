"""Deterministic read-only-history packet assembly. No RNG, keys, HTTP or sends.

Hub supplies an exclusive externally pinned seed record after protocol agreement.
Only new output-directory files are written; live acquisition state is read-only.
"""
import argparse
import fcntl
import hashlib
import stat
import types
import json
import os
import subprocess
from pathlib import Path


def canonical(v):
    return json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()


def sha(raw):return hashlib.sha256(raw).hexdigest()



def regular(path):
    path=Path(path).absolute()
    if any(p.is_symlink() for p in (path,*path.parents)):raise ValueError('symlink source input')
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):raise ValueError('regular source input required')
        with os.fdopen(fd,'rb',closefd=False) as handle:return handle.read()
    finally:os.close(fd)


def captured_module(raw,path,name):
    result=types.ModuleType(name);result.__file__=str(path)
    exec(compile(raw,str(path),'exec'),result.__dict__)
    return result


def pinned_module(raw,path,name,expected):
    if sha(raw)!=expected:raise ValueError('reviewed bootstrap/capture hash differs')
    return captured_module(raw,path,name)

def validate_output(repo, output):
    """New directory inside an isolated Git root only; run before any seed/history."""
    repo=Path(repo);output=Path(output)
    if '..' in repo.parts or '..' in output.parts:raise ValueError('parent traversal forbidden')
    repo=repo.absolute()
    if not output.is_absolute():output=repo/output
    output=output.absolute()
    for path in (repo,output):
        if any(p.is_symlink() for p in (path,*path.parents)):raise ValueError('symlink output/repository ancestor')
    live=Path.home()/'code/value-finder'
    runtime=Path.home()/'Library/Application Support/ValueFinder/football-acquisition-state'
    for path in (repo,output):
        if any(path==denied or denied in path.parents for denied in (live,runtime)):
            raise ValueError('live checkout/runtime output forbidden')
    if output==repo or repo not in output.parents:raise ValueError('output must be strictly inside isolated repository')
    if output.exists():raise ValueError('output must be a new directory')
    top=Path(subprocess.check_output(['git','rev-parse','--show-toplevel'],cwd=repo,text=True).strip()).absolute()
    if top!=repo:raise ValueError('explicit isolated Git root required')
    return repo,output

def closure(repo,protocol):
    pilot=repo/'strategy-research/coverage-pilot-v1';meta=repo/'strategy-research/football-metadata-v1'
    boot_path=pilot/'bootstrap.py'
    boot_raw=regular(boot_path)
    boot=pinned_module(boot_raw,boot_path,'packet_bootstrap',protocol['source_code_sha256']['bootstrap'])
    paths={n:pilot/(n+'.py') for n in boot.MODULES}
    paths.update(capture=meta/'capture.py',history=meta/'history.py',plan=repo/'strategy-research/nfl-props-archive-v1/plan.py',f2_gate=repo/'strategy-research/football_archive/f2_handoff.py',older_recovery=repo/'strategy-research/football_archive/older-recovery-v1/recovery.py')
    raw={n:(boot_raw if n=='bootstrap' else regular(path)) for n,path in paths.items()}
    if {n:sha(b) for n,b in raw.items()}!=protocol['source_code_sha256']:raise ValueError('reviewed code closure changed')
    bundle=repo/'strategy-research/football_archive/acquisition/football-archive-v4'
    cert=json.loads(regular(bundle/'FREEZE.json'))
    if sha(boot.canonical(cert['file_sha256']))!=boot.SOURCE_ROOT or cert['bundle_root_sha256']!=boot.SOURCE_ROOT:raise ValueError('immutable root differs')
    source={n:regular(bundle/n) for n in cert['file_sha256']}
    if {n:sha(b) for n,b in source.items()}!=cert['file_sha256']:raise ValueError('immutable source differs')
    capture=pinned_module(raw['capture'],paths['capture'],'packet_capture',protocol['source_code_sha256']['capture'])
    mods=dict(raw)
    for n,b in source.items():
        if n.endswith('.py'):
            key=(n[:-12] if n.endswith('/__init__.py') else n[:-3]).replace('/','.')
            if key in mods:raise ValueError('module collision')
            mods[key]=b;paths[key]=bundle/n
    return boot,capture.closed_modules(mods,paths),source,bundle,paths


def missing_policy(rows):
    ids=[r['request_id'] for r in rows]
    props=[r['request_id'] for r in rows if r['source']=='oddsapi/hist_event_odds']
    cap=lambda n:max(1,(n+19)//20) if n else 0
    return dict(snapshot_lag_ids=ids,event_not_found_ids=props,max_missing=dict(snapshot_lag=cap(len(ids)),event_not_found=cap(len(props))))


def selected_union(frame,selected,slotmap,originals,history,load,books):
    """history is metadata projected only AFTER authenticated complete global proof."""
    plan=load('plan');mapping=load('mapping');utc=load('timing').utc
    games={g['game_id']:g for g in frame};oldmap={g['game_id']:g for g in slotmap}
    oldrows={r['request_id']:r for r in originals};attempts={};cells={}
    for h in history:
        rid=h['request_id']
        if rid in attempts:raise ValueError('ambiguous duplicate historical request ID')
        attempts[rid]=h
        if h.get('source')!='oddsapi/hist_event_odds':continue
        params=h['params']
        if params.get('dateFormat','iso')!='iso' or params.get('oddsFormat','decimal')!='decimal' or set(params)-{'date','dateFormat','oddsFormat','bookmakers','markets'}:raise ValueError('incompatible historical query')
        for b in params['bookmakers'].split(','):
            for m in params['markets'].split(','):
                key=mapping.cell(h['sport'],h['event_id'],params['date'],b,m)
                if key in cells:raise ValueError('ambiguous historical market cell')
                cells[key]=h
    requests={};mappings=[]
    for gid in selected['selected']:
        g=games[gid];sport=g['stratum'].split('/')[1]
        item=dict(game_id=gid,request_ids=[],reason=None)
        if g['stratum'].startswith('older/'):
            slots=oldmap[gid]['slots']
            item['metadata_disposition']=mapping.older_metadata_disposition(g,slots)
            if item['metadata_disposition']['classification']=='failure':
                item['reason']='metadata_ineligible';mappings.append(item);continue
            ids=[slots[s]['request_id'] for s in ('EARLY','CLOSE')]
            item.update(reused_request_ids=[],reused_evidence=[])
            for rid in ids:
                if rid in attempts:
                    h=attempts[rid]
                    if not h.get('claim'):raise ValueError('raw-less designated older attempt; retain exclusion, stop for frozen zero disposition')
                    item['reused_request_ids'].append(rid);item['reused_evidence'].append(h['claim'])
                else:
                    r=oldrows[rid]
                    if r['priority']!=2 or not r['max_new_credits']:raise ValueError('not an untouched original paid older ID')
                    requests[rid]=dict(r,url=plan.BASE+r['path']);item['request_ids'].append(rid)
        else:
            item['reused_slots']=[]
            ops=[];cellhistory=[]
            for op in g['source_opportunities']:
                ops.append(dict(op,season=g['season'],sport=sport,books=books))
                for b in books:
                    for m in mapping.MARKETS:
                        h=cells.get(mapping.cell(sport,op['event_id'],op['requested_utc'],b,m))
                        if h:
                            if not h.get('claim'):raise ValueError('reused props cell has no terminal receipt/raw proof')
                            cellhistory.append(dict(cell=mapping.cell(sport,op['event_id'],op['requested_utc'],b,m),status=h['status']))
                            # Single-cell rectangles make partial reuse explicit and nonoverlapping.
                            item['reused_slots'].append(dict(sport=sport,event_id=op['event_id'],requested_utc=op['requested_utc'],books=[b],markets=[m],evidence=[h['claim']]))
            result=mapping.props_union(ops,cellhistory,plan.make_request)
            if result['blocked']:raise ValueError('unresolved props cells')
            for r in result['requests']:
                if r['request_id'] in requests and requests[r['request_id']]!=r:raise ValueError('request collision')
                requests[r['request_id']]=r;item['request_ids'].append(r['request_id'])
        item['request_ids']=sorted(set(item['request_ids']))
        if not item['request_ids']:item['reason']='all_designated_cells_receipt_authenticated'
        mappings.append(item)
    rows=[requests[k] for k in sorted(requests)]
    load('overlap').check_internal(rows,mappings)
    return rows,mappings



def frozen_probe_history(context,load):
    """Expose immutable zero-credit old slots with separate authenticated claims."""
    capture=load('capture');source=context['files'];result=[]
    manifest=source['request-manifest.json'];ledger=source['probe-spending-ledger.json']
    attempts={a['request_id']:a for a in json.loads(ledger)['attempts']}
    root=json.loads(context['freeze'])['bundle_root_sha256']
    for row in json.loads(manifest)['requests']:
        if row['priority']!=2 or row['max_new_credits']!=0:continue
        rid=row['request_id']
        if rid not in attempts:raise ValueError('frozen reuse lacks probe attempt')
        claim=dict(kind='frozen_probe',source_bundle_root=root,request_id=rid,cache_source=row['cache_source'],cache_sha256=row['cache_sha256'],request_manifest_sha256=capture.digest(manifest),probe_ledger_sha256=capture.digest(ledger),probe_attempt_sha256=capture.identity(attempts[rid]))
        rec=load('evidence').frozen_probe_record(claim,context)
        result.append(dict(rec,request_id=rid,status='completed',claim=claim))
    return result

def authenticated_history(root_base,snapshot,capture):
    import pyarrow as pa
    import pyarrow.parquet as pq
    result=[]
    for root,pin in sorted(snapshot['ledgers'].items()):
        folder=root_base/root;ledger=folder/'spending-ledger.json'
        if capture.sha(ledger)!=pin:raise ValueError('historical ledger changed')
        for rid,a in sorted(capture.read(ledger)['attempts'].items()):
            h=dict(request_id=rid,status=a['status'])
            if a.get('response_path'):
                raw=capture.regular(a['response_path']);receipt=capture.regular(folder/'receipts'/(rid+'.json'))
                if capture.digest(raw)!=a['response_sha256'] or capture.digest(receipt)!=a['receipt_sha256']:raise ValueError('historical evidence changed')
                recs=pq.read_table(pa.BufferReader(raw),columns=['sport','source','url','params_json']).to_pylist()
                if len(recs)!=1:raise ValueError('single historical record required')
                rec=recs[0];params=json.loads(rec.pop('params_json'));rec['params']=params
                if capture.identity({k:rec[k] for k in ('source','url','params')})!=rid:raise ValueError('historical request identity differs')
                if rec['source']=='oddsapi/hist_event_odds':rec['event_id']=rec['url'].split('/events/')[1].removesuffix('/odds')
                h.update(rec,claim=dict(root=root,request_id=rid,response_sha256=a['response_sha256'],receipt_sha256=a['receipt_sha256']))
            result.append(h)
    return result


def assemble(args):
    repo,args.output=validate_output(args.repo,args.output)
    protocol_raw=regular(args.protocol);protocol=json.loads(protocol_raw)
    if sha(protocol_raw)!=args.protocol_sha256:raise ValueError('external protocol file pin differs')
    if protocol['execution_status']!='reviewed_for_execution':raise ValueError('predraw protocol review still pending')
    boot,load,source,bundle,paths=closure(repo,protocol);capture=load('capture');planner=load('planner')
    names={'frame.json':'frame.json','slot-map.json':'requested-slot-map.json','classifier-contract.json':'PRIMARY-CONTRACT.json','certainty-source-proof.json':'source-proof.json'}
    data={n:boot.regular(args.certainty/original) for n,original in names.items()}
    if {n:sha(b) for n,b in data.items()}!=protocol['final_input_sha256']:raise ValueError('final input pins differ')
    data['protocol.json']=protocol_raw;data['draw.json']=boot.regular(args.seed_record)
    record=json.loads(data['draw.json'])
    if planner.digest(record)!=args.seed_record_sha256:raise ValueError('external once-only seed commitment differs')
    frame=json.loads(data['frame.json']);fc=planner.digest(planner.frame_rows(frame));pc=planner.digest(protocol)
    if fc!=protocol['frame_canonical_sha256']:raise ValueError('canonical frame differs')
    selected=planner.select(frame,record,protocol['sample_sizes'],committed_frame=fc,committed_protocol=pc,committed_seed_record=args.seed_record_sha256,protocol=protocol)
    if protocol['execution_status']!='reviewed_for_execution':raise ValueError('predraw protocol review still pending')
    base=load('executor');root_base=base.RUNTIME_BASE
    # Existing lock opened read-only: no live-state directory/file creation.
    with (root_base/'followup-purchase.lock').open('rb') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        snapshot={'ledgers':{p.parent.name:capture.sha(p) for p in root_base.glob('*/spending-ledger.json')},'registrations':{p.stem:capture.sha(p) for p in (root_base/'registrations').glob('*.json')}}
        bindings=json.loads(boot.regular(args.historical_bindings))
        def verify(ledgers,markers):return load('baseline').verify_base(ledgers,markers,snapshot,source['request-manifest.json'],bindings)
        snap,carry=load('evidence').global_union(root_base,snapshot,{},verify)
        history=authenticated_history(root_base,snap,capture)
        context={'freeze':boot.regular(bundle/'FREEZE.json'),'files':source}
        history.extend(frozen_probe_history(context,load))
        rows,mappings=selected_union(frame,selected,json.loads(data['slot-map.json']),json.loads(source['request-manifest.json'])['requests'],history,load,protocol['candidate_books'])
        load('evidence').authenticate_reuse(root_base,snap,mappings,frozen_source=context)
        cap=sum(r['max_new_credits'] for r in rows)
        if not rows or cap+carry['conservative_debit']>250000:raise ValueError('empty paid list or cumulative ceiling exceeded')
        rawroots=sorted({str((root_base/r/'data/raw').absolute()) for r in snap['ledgers']}|{str((Path.home()/'code/value-finder/sharp-markets/data/raw').absolute()),str((args.probe_bundle/'data/raw').absolute())})
        for item in json.loads(source['input-provenance.json'])['raw_probe_sources']:
            suffix=item['path'].removeprefix('local://football-probe-v1/')
            if suffix==item['path'] or capture.sha(args.probe_bundle/suffix)!=item['sha256']:raise ValueError('probe provenance differs')
        inventory={}
        for rawroot in rawroots:
            for sport in ('americanfootball_nfl','americanfootball_ncaaf'):
                for src in ('oddsapi/hist_odds','oddsapi/hist_event_odds','oddsapi/hist_event_markets'):
                    for path in (Path(rawroot)/sport/src).glob('*/*.parquet'):
                        if '2020-01-01'<=path.parent.name<'2026-02-10':inventory[str(path)]=capture.sha(path)
        cacheplan=dict(raw_roots=rawroots,probe_bundle_root=str(args.probe_bundle.resolve()),inventory_sha256=capture.identity(inventory))
        load('overlap').check(rows,rawroots,expected_inventory_sha256=cacheplan['inventory_sha256'])
        baseline=dict(base_snapshot=snap,expected_global_snapshot=snap,historical_bindings=bindings,pilot_bindings={})
        objects={'selected.json':selected,'requests.json':rows,'mappings.json':mappings,'policy.json':missing_policy(rows),'baseline.json':baseline,'overlap.json':cacheplan}
        objects['manifest.json']=dict(frame_sha256=fc,protocol_sha256=pc,seed_record_sha256=args.seed_record_sha256,request_count=len(rows),max_new_credits=cap,request_list_sha256=sha(canonical(rows)),request_set_sha256=capture.identity(rows))
        data.update({n:canonical(v) for n,v in objects.items()})
        # Match bootstrap.verified's exact logical file set, including every dependency.
        files={n:sha(b) for n,b in data.items()}
        files.update({'code/'+n+'.py':protocol['source_code_sha256'][n] for n in boot.MODULES|{'capture','history','plan','f2_gate','older_recovery'}})
        files['policy/older-PROTOCOL.md']=capture.sha(repo/'strategy-research/football_archive/older-recovery-v1/PROTOCOL.md')
        files['policy/PRIMARY-CONTRACT.json']=capture.sha(repo/'strategy-research/coverage-pilot-v1/PRIMARY-CONTRACT.json')
        files['source/FREEZE.json']=capture.sha(bundle/'FREEZE.json');root=sha(boot.canonical(files))
        validate_output(repo,args.output)
        args.output.mkdir(mode=0o700)  # exclusive new directory, never overwrite/rebuild silently
        for name,raw in data.items():
            with (args.output/name).open('xb') as handle:handle.write(raw);handle.flush();os.fsync(handle.fileno())
        load('evidence').write_once(args.output/'FREEZE.json',dict(root=root,files=files))
        runner,_,packet,shared,_=boot.verified(args.output,root,bundle)
        result=runner.packet(packet,shared)
        # Reauthenticate history after assembly; no state/receipt mutation accepted.
        load('evidence').global_union(root_base,snapshot,{},verify)
        return dict(result,root=root,carried_credits=carry['conservative_debit'],seed_record_sha256=args.seed_record_sha256,paid_authority=False)


if __name__=='__main__':
    p=argparse.ArgumentParser()
    for name in ('repo','protocol','certainty','seed-record','historical-bindings','probe-bundle','output'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--protocol-sha256',required=True);p.add_argument('--seed-record-sha256',required=True)
    print(json.dumps(assemble(p.parse_args()),sort_keys=True))
