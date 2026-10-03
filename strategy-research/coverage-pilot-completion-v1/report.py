"""One frozen outcome-blind coverage look. No provider client, keys or runtime writes.

Verify requires hub-supplied exact terminal pins; finalize additionally requires
live explicit final-look authority. All mutable reads are under the shared lock.
"""
import argparse
from collections import Counter, defaultdict
import copy
import fcntl
from fractions import Fraction
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import types

ROOT='f490e0daaec2d7721d0298da1abbfbce47a7de13124a412641d5edb33addb380'
OUTPUT_BASE=Path('/Users/maxzipperman/.codex/.chatgpt-projects/g-p-6abd9b86b9548191a07ce7f1180bc80a/research-lab/acquisition/coverage-pilot-once/final-existing-frame-v1')


def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False,default=str).encode()
def digest(raw):return hashlib.sha256(raw).hexdigest()
def identity(value):return digest(canonical(value))


def regular(path):
    path=Path(path).absolute()
    if any(p.is_symlink() for p in (path,*path.parents)):raise ValueError('symlink input/output forbidden')
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):raise ValueError('regular evidence required')
        with os.fdopen(fd,'rb',closefd=False) as h:return h.read()
    finally:os.close(fd)


def output_path(path,mode):
    path=Path(path).absolute()
    if path.parent!=OUTPUT_BASE or path.name!=('receipt-verification.json' if mode=='verify' else 'final-record.json'):
        raise ValueError('output outside fixed artifact directory/name')
    if any(p.is_symlink() for p in (path,*path.parents)):raise ValueError('symlink output forbidden')
    return path


def captured_closure(repo,packet,root):
    if root!=ROOT:raise ValueError('only exact merged successor root supported')
    cert=json.loads(regular(packet/'FREEZE.json'))
    if cert['root']!=root or identity(cert['files'])!=root:raise ValueError('external packet root differs')
    path=repo/'strategy-research/coverage-pilot-v1/bootstrap.py';raw=regular(path)
    if digest(raw)!=cert['files']['code/bootstrap.py']:raise ValueError('bootstrap changed before execution')
    boot=types.ModuleType('coverage_completion_bootstrap');boot.__file__=str(path)
    exec(compile(raw,str(path),'exec'),boot.__dict__)
    bundle=repo/'strategy-research/football_archive/acquisition/football-archive-v4'
    runner,base,data,source,load=boot.verified(packet,root,bundle)
    summary=runner.packet(data,source)
    if summary['selected_denominator']!=430 or summary['full_denominator']!=6790 or summary['requests']!=729 or summary['max_new_credits']!=36810:raise ValueError('original draw/scope differs')
    return data,source,load


def terminal_state(state,rows,pin,root,runtime,marker,initialization):
    if (state.get('status')!='pilot_complete' or state.get('pending') or state.get('stopped')
            or state.get('bundle_root_sha256')!=root or state.get('pilot_plan_sha256')!=root
            or state.get('authorization_sha256')!=pin['authorization_sha256']
            or initialization!={'bundle_root_sha256':root,'probe_credits':1687}
            or marker!={'bundle_root_sha256':root,'authorization_sha256':pin['authorization_sha256'],'runtime_path':str(runtime.absolute())}
            or state.get('probe_credits')!=1687 or state.get('slice_cap')!=sum(r['max_new_credits'] for r in rows)):
        raise ValueError('nonterminal or mismatched completion identity')
    if type(pin['billed']) is not int or type(pin['reserved']) is not int:raise ValueError('exact integer completion debit required')
    by_id={r['request_id']:r for r in rows}
    if len(by_id)!=len(rows) or set(state['attempts'])!=set(by_id):raise ValueError('missing/duplicate/extra completion request')
    for rid,a in state['attempts'].items():
        if a.get('status') not in ('completed','missing') or a.get('send_started') is not True or a.get('reserved_credits')!=by_id[rid]['max_new_credits'] or type(a.get('billed_credits')) is not int or not 0<=a['billed_credits']<=a['reserved_credits']:
            raise ValueError('nonterminal or changed reservation')
    billed=sum(a['billed_credits'] for a in state['attempts'].values());reserved=sum(a['reserved_credits'] for a in state['attempts'].values())
    if (billed,reserved)!=(pin['billed'],pin['reserved']):raise ValueError('completion charge/reservation pins differ')
    if state['predecessor_snapshot']!=pin['predecessor_snapshot_sha256']:raise ValueError('completion predecessor differs')
    return dict(billed=billed,reserved=reserved)


def counter_replay(base,state,rows,records,policy,protocol,receipts):
    """Replay frozen counter primitive without save/init/network or runtime mutation."""
    epoch=state['epoch']
    if not epoch or epoch['start_billed']!=0 or epoch.get('first_provider_observation_verified') is not True:raise ValueError('unexpected counter epoch')
    simulated=object.__new__(base.Ledger);simulated.state=copy.deepcopy(state);simulated.protocol=protocol;simulated.save=lambda:None
    simulated.state['epoch']={k:epoch[k] for k in ('start_used','start_remaining','start_billed','prebaseline_other_debit','first_provider_observation_verified')}
    simulated.state['epoch'].update(used_highwater=epoch['start_used'],remaining_lowwater=epoch['start_remaining'],external_peak=0)
    simulated.state['other_usage_reserved']=epoch['prebaseline_other_debit']
    # The sole completed continuation has one initial free-account observation.
    if len(state['accounts'])!=1 or state.get('free_account_attempt',{}).get('status')!='completed':raise ValueError('unexpected free-account history')
    account=state['accounts'][0]
    if (account['used'],account['remaining'])!=(state['free_account_attempt']['used'],state['free_account_attempt']['remaining']):raise ValueError('free-account counter binding differs')
    simulated.measure_counters(account['used'],account['remaining'],0)
    own=0
    for row in rows:
        result=receipts.classify(row,records[row['request_id']],policy);own+=result['bill']
        simulated.measure_counters(result['used'],result['remaining'],own)
    for key in ('epoch','provider_used','provider_remaining','other_usage_reserved'):
        if simulated.state[key]!=state[key]:raise ValueError('counter epoch replay differs')
    return dict(billed=own,used=state['provider_used'],remaining=state['provider_remaining'],epoch=state['epoch'],conservative_debit=state['other_usage_reserved']+1687+simulated.reserved())


def saved_record(folder,rid,attempt,capture):
    import pyarrow as pa
    import pyarrow.parquet as pq
    raw=capture.regular(attempt['response_path']);proof_raw=capture.regular(folder/'receipts'/(rid+'.json'))
    if capture.digest(raw)!=attempt['response_sha256'] or capture.digest(proof_raw)!=attempt['receipt_sha256']:raise ValueError('receipt/raw changed during projection')
    proof=json.loads(proof_raw);records=pq.read_table(pa.BufferReader(raw)).to_pylist()
    if len(records)!=1 or proof['request_id']!=rid or proof['response_sha256']!=attempt['response_sha256'] or canonical(proof['record'])!=canonical(records[0]):raise ValueError('single exact saved receipt required')
    return records[0]


def authenticate(data,source,load,pin):
    capture=load('capture');base=load('executor');evidence=load('evidence');baseline=load('baseline');root_base=base.RUNTIME_BASE
    if pin['version']!=1 or pin['root']!=ROOT or pin['adapter_sha256']!=digest(regular(Path(__file__))):raise ValueError('completion adapter/root pin differs')
    runtime=root_base/ROOT;ledger=runtime/'spending-ledger.json';marker=root_base/'registrations'/(ROOT+'.json');init=runtime/'INITIALIZED.json'
    actual={n:capture.sha(p) for n,p in {'ledger_sha256':ledger,'marker_sha256':marker,'initialization_sha256':init}.items()}
    if any(pin[n]!=v for n,v in actual.items()):raise ValueError('exact completion files changed')
    state=capture.read(ledger);rows=json.loads(data['requests.json']);policy=json.loads(data['policy.json']);bindings=json.loads(data['baseline.json']);maps=json.loads(data['mappings.json'])
    terminal=terminal_state(state,rows,pin,ROOT,runtime,capture.read(marker),capture.read(init))
    if state['predecessor_snapshot']!=identity(bindings['expected_global_snapshot']):raise ValueError('frozen predecessor differs')
    proof=evidence.captured_receipts(runtime,rows,state,policy)
    if proof['untouched_ids'] or proof['reserved']!=36810:raise ValueError('incomplete receipt union')
    current_binding=dict(actual,rows=rows,policy=policy,predecessor_snapshot=state['predecessor_snapshot'],authorization_sha256=state['authorization_sha256'],plan_sha256=ROOT)
    pilots=dict(bindings['pilot_bindings'],**{ROOT:current_binding})
    def check_base(ledgers,markers):return baseline.verify_base(ledgers,markers,bindings['base_snapshot'],source['request-manifest.json'],bindings['historical_bindings'])
    snapshot,carry=evidence.global_union(root_base,bindings['base_snapshot'],pilots,check_base)
    if snapshot!=pin['global_snapshot']:raise ValueError('completion global inventory pin differs')
    evidence.authenticate_reuse(root_base,snapshot,maps,frozen_source={'freeze':data['source/FREEZE.json'],'files':source})
    projected={};pins={}
    def add(rid,record,status,claim):
        if rid in projected:
            if canonical(projected[rid])!=canonical(dict(record=record,status=status,claim=claim)):raise ValueError('ambiguous duplicate receipt provenance')
            return
        projected[rid]=dict(record=record,status=status,claim=claim);pins[rid]=claim
    for row in rows:
        rid=row['request_id'];a=state['attempts'][rid]
        add(rid,saved_record(runtime,rid,a,capture),a['status'],dict(root=ROOT,request_id=rid,response_sha256=a['response_sha256'],receipt_sha256=a['receipt_sha256']))
    for item in maps:
        claims=list(item.get('reused_evidence',[]))
        for slot in item.get('reused_slots',[]):claims.extend(slot['evidence'])
        for claim in claims:
            rid=claim['request_id']
            if claim.get('kind')=='frozen_probe':
                evidence.frozen_probe_record(claim,{'freeze':data['source/FREEZE.json'],'files':source})
                import pyarrow as pa
                import pyarrow.parquet as pq
                recs=pq.read_table(pa.BufferReader(source[claim['cache_source']])).to_pylist()
                if len(recs)!=1:raise ValueError('ambiguous probe record')
                add(rid,recs[0],'completed',claim)
            else:
                folder=root_base/claim['root'];a=capture.read(folder/'spending-ledger.json')['attempts'][rid]
                add(rid,saved_record(folder,rid,a,capture),a['status'],claim)
    if pins!=pin['request_evidence']:raise ValueError('exact designated raw/receipt pin union differs')
    counters=counter_replay(base,state,rows,{rid:r['record'] for rid,r in projected.items()},policy,json.loads(source['protocol.json']),load('receipts'))
    if counters!=pin['counter_reconciliation'] or counters['conservative_debit']!=carry['conservative_debit']:raise ValueError('counter/carry pins differ')
    # Recheck all exact mutable pin inventories after projecting raw bytes.
    if any(capture.sha(p)!=actual[n] for n,p in {'ledger_sha256':ledger,'marker_sha256':marker,'initialization_sha256':init}.items()):raise ValueError('completion changed during read')
    again,againcarry=evidence.global_union(root_base,bindings['base_snapshot'],pilots,check_base)
    if again!=snapshot or againcarry!=carry:raise ValueError('global history changed during read')
    return projected,dict(terminal=terminal,counters=counters,global_snapshot=snapshot,request_evidence_sha256=identity(pins),next_purchase_authorized=False)


def record_body(entry):
    return json.loads(entry['record']['body'])


def classify_selected(data,source,load,projection):
    classifier=load('classifier');plan=load('plan');timing=load('timing')
    frame={g['game_id']:g for g in json.loads(data['frame.json'])};selected=json.loads(data['selected.json'])['selected'];maps=json.loads(data['mappings.json']);protocol=json.loads(data['protocol.json']);slotmap={g['game_id']:g for g in json.loads(data['slot-map.json'])}
    observations=json.loads(source['provider-observations.json']);canonical_games={g['canonical_game_id']:g for g in json.loads(source['canonical-games.json'])}
    if len(selected)!=len(set(selected)) or {m['game_id'] for m in maps}!=set(selected) or len(maps)!=len(selected):raise ValueError('selected mapping denominator incomplete')
    results={};details={}
    for item in maps:
        gid=item['game_id'];g=frame[gid]
        forced=[item[k] for k in ('metadata_disposition','coverage_disposition') if item.get(k,{}).get('classification')=='failure']
        if forced:
            results[gid]=False;details[gid]=dict(success=False,forced_dispositions=forced,timing_basis='scheduled_proxy',actual_play_certified=False,grading_enabled=False);continue
        args=dict(execution=None,candidate_books=protocol['candidate_books'],independent_kickoff=canonical_games[gid]['scheduled_utc'])
        slots={}
        if g['stratum'].startswith('older/'):
            declared=slotmap[gid]['slots']
            for role,label in [('EARLY','EARLY_18_54'),('CLOSE','CLOSE_T10')]:
                s=declared[role];rid=s['request_id'];entry=projection[rid]
                if entry['status']=='missing':slots[role]=dict(pairs=set(),reasons=['terminal_missing']);continue
                if role=='EARLY':binding=classifier.bind_asof(observations,gid,s['requested_utc'])
                else:
                    b=s['binding'];binding=dict(status='bound',event_id=s['provider_id'],provider_kickoff_utc=b['provider_kickoff_utc'],binding_observed_utc=b['returned_utc'],home_team=b['home_team'],away_team=b['away_team'])
                slots[role]=classifier.slot_pairs(record_body(entry),requested=s['requested_utc'],binding=binding,slot=label,markets=['totals'],**dict(args,execution=s['requested_utc'],candidate_books=protocol['candidate_books']+['pinnacle']))
            result=classifier.older_totals_feasibility(slots['EARLY'],slots['CLOSE'],protocol['candidate_books'])
        else:
            assigned={rid:projection[rid] for rid in item['request_ids']}
            for reuse in item.get('reused_slots',[]):
                for claim in reuse['evidence']:assigned[claim['request_id']]=projection[claim['request_id']]
            for op in g['source_opportunities']:
                binding=classifier.bind_asof(observations,gid,op['requested_utc']);pairs=set();reasons=[];matched=[]
                for rid,entry in assigned.items():
                    rec=entry['record'];params=json.loads(rec['params_json'])
                    if timing.utc(params['date'])!=timing.utc(op['requested_utc']):continue
                    if rec['sport']!=g['stratum'].split('/')[1] or not rec['url'].endswith('/events/'+op['event_id']+'/odds'):raise ValueError('slot receipt identity mismatch')
                    matched.append(rid)
                    if entry['status']=='missing':reasons.append('terminal_missing');continue
                    part=classifier.slot_pairs(record_body(entry),requested=op['requested_utc'],binding=binding,slot=op['slot'],markets=protocol['primary_markets'],**dict(args,execution=op['requested_utc']))
                    pairs.update(part['pairs']);reasons.extend(part['reasons'])
                if not matched:raise ValueError('missing designated props receipt')
                slots[op['slot']]=dict(pairs=pairs,reasons=sorted(set(reasons)))
            result=classifier.props_feasibility(slots['T24'],slots['CLOSE_T10'])
        results[gid]=result['success'];details[gid]=dict(result,slot_reasons={k:v['reasons'] for k,v in slots.items()},pair_counts={k:len(v['pairs']) for k,v in slots.items()})
    if set(results)!=set(selected):raise ValueError('selected final denominator changed')
    return results,details


def bound_record(data,load,classifications):
    frame=json.loads(data['frame.json']);protocol=json.loads(data['protocol.json']);selected=json.loads(data['selected.json'])['selected']
    if set(classifications)!=set(selected) or any(type(v) is not bool for v in classifications.values()):raise ValueError('nonterminal/incomplete classifications')
    groups=defaultdict(Counter);by_id={g['game_id']:g for g in frame}
    for g in frame:groups[g['stratum']][g['classification']]+=1
    if set(groups)!=set(protocol['sample_sizes']) or len(groups)!=12:raise ValueError('fixed stratum denominator changed')
    observed=Counter(by_id[g]['stratum'] for g,v in classifications.items() if v)
    samples=Counter(by_id[g]['stratum'] for g in selected)
    reports=[]
    for key,c in sorted(groups.items()):
        if samples[key]!=protocol['sample_sizes'][key]:raise ValueError('sample allocation changed')
        older=key.startswith('older/')
        r=load('bounds').stratum(known_successes=c['success'],known_failures=c['failure'],unknown=c['unknown'],sample=samples[key],observed=observed[key],phase='existing',projected_new_credits=(60 if older else 122)*c['unknown'],utility_floor=Fraction(protocol['older_utility_floor'] if older else protocol['props_utility_floor']),cost_ceiling=protocol['older_cost_ceiling'] if older else protocol['props_cost_ceiling'])
        reports.append(dict(r,stratum=key,sample=samples[key],observed=observed[key],known_failures=c['failure'],projected_new_credits=(60 if older else 122)*c['unknown'],cost_basis='frozen_conservative_gross_initially_unknown_60_122'))
    return load('certainty').json_ready(dict(strata=reports,pooled=load('bounds').pooled_report(reports),incremental_purchase_planning='requires_separately_reviewed_residual_allowlist_no_automatic_release'))


def final_authority(auth,pin,verification_pin,*,completion_pin=None,fetch=None):
    url=auth['comment_url'];body=auth['comment_body']
    expected=f"APPROVED final coverage look: root {ROOT}, completion {completion_pin or identity(pin)}, verification {verification_pin}, adapter {pin['adapter_sha256']}"
    if (not re.fullmatch(r'https://github\.com/maxzipperman/value-finder/pull/[0-9]+#issuecomment-[0-9]+',url) or body.splitlines().count(expected)!=1 or re.search(r'\b(HALTED|EXHAUSTED|REVOKED|NOT APPROVED|NOT READY)\b',body,re.I)):raise ValueError('exact active final-look authority required')
    live=fetch(url.rsplit('-',1)[-1]) if fetch else json.loads(subprocess.check_output(['gh','api','repos/maxzipperman/value-finder/issues/comments/'+url.rsplit('-',1)[-1]],text=True))
    if live.get('html_url')!=url or live.get('body')!=body or live.get('user',{}).get('login')!='maxzipperman':raise ValueError('final-look authority changed')


def run(args):
    pin_raw=regular(args.completion_binding);pin=json.loads(pin_raw)
    if digest(pin_raw)!=args.completion_sha256 or pin['root']!=ROOT:raise ValueError('external completion bytes differ')
    # Source authority is checked before executing any sibling/local dependency.
    if digest(regular(Path(__file__)))!=pin['adapter_sha256']:raise ValueError('reviewed adapter source differs')
    out=output_path(args.output,args.mode);repo=Path(args.repo).absolute();packet=Path(args.packet).absolute()
    data,source,load=captured_closure(repo,packet,ROOT);base=load('executor');capture=load('capture');evidence=load('evidence')
    if base.current_runtime()!=json.loads(source['runtime-lock.json']):raise ValueError('reviewed runtime/environment differs')
    fingerprint=dict(root=ROOT,completion_sha256=args.completion_sha256,adapter_sha256=pin['adapter_sha256'],packet_files_sha256=identity({n:digest(v) for n,v in data.items()}))
    with (base.RUNTIME_BASE/'followup-purchase.lock').open('rb') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        auth=None;verified=None
        if args.mode=='finalize':
            auth_raw=regular(args.final_authorization)
            if digest(auth_raw)!=args.final_authorization_sha256:raise ValueError('external final authority bytes differ')
            auth=json.loads(auth_raw);final_authority(auth,pin,args.verified_sha256,completion_pin=args.completion_sha256)
            verified_raw=regular(args.verified_receipts)
            if digest(verified_raw)!=args.verified_sha256:raise ValueError('confirmed verification changed')
            verified=json.loads(verified_raw)
            if verified.get('fingerprint')!=fingerprint or verified.get('status')!='receipts_verified':raise ValueError('different/unverified receipt report')
        projection,proof=authenticate(data,source,load,pin)
        if args.mode=='verify':result=dict(status='receipts_verified',fingerprint=fingerprint,proof=proof,final_look_run=False)
        else:
            if proof!=verified['proof']:raise ValueError('receipt proof changed after verification')
            if out.exists():
                saved_raw=regular(out)
                if not args.existing_final_sha256 or digest(saved_raw)!=args.existing_final_sha256:raise ValueError('existing final record needs external saved artifact pin; no second look')
                saved=json.loads(saved_raw)
                if saved.get('fingerprint')!=fingerprint or saved.get('verification_sha256')!=args.verified_sha256 or saved.get('proof')!=proof or saved.get('record_sha256')!=identity(saved.get('record')):raise ValueError('one-look record changed; no recomputation')
                final_authority(auth,pin,args.verified_sha256,completion_pin=args.completion_sha256)
                now,shared,_=captured_closure(repo,packet,ROOT)
                if now!=data or shared!=source:raise ValueError('source changed before saved-record reuse')
                return saved
            classifications,details=classify_selected(data,source,load,projection);bounds=bound_record(data,load,classifications)
            manifest=json.loads(data['manifest.json']);selected=json.loads(data['selected.json'])['selected'];mappings=json.loads(data['mappings.json'])
            record=evidence.final_record(frame_sha256=manifest['frame_sha256'],protocol_sha256=manifest['protocol_sha256'],draw_sha256=manifest['seed_record_sha256'],evidence_sha256=identity(dict(fingerprint=fingerprint,proof=proof)),selected_ids=selected,classifications=classifications,saved_bounds=bounds,mappings=mappings)
            result=dict(fingerprint=fingerprint,verification_sha256=args.verified_sha256,proof=proof,record=record,record_sha256=identity(record),details=details,timing_basis='scheduled_proxy',actual_play_certified=False,grading_enabled=False,next_purchase_authorized=False)
        # Final boundary: source, authority and mutable evidence still identical.
        now,shared,_=captured_closure(repo,packet,ROOT)
        if now!=data or shared!=source:raise ValueError('source changed during read')
        _,again=authenticate(data,source,load,pin)
        if again!=proof:raise ValueError('receipt evidence changed before save')
        if auth:final_authority(auth,pin,args.verified_sha256,completion_pin=args.completion_sha256)
        output_path(out,args.mode)
        if out.exists():
            old=json.loads(regular(out))
            if old!=result:raise ValueError('existing artifact differs; no overwrite')
            return old
        out.parent.mkdir(parents=True,exist_ok=True);output_path(out,args.mode)
        evidence.write_once(out,result)
        return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['verify','finalize']);p.add_argument('--repo',type=Path,required=True);p.add_argument('--packet',type=Path,required=True);p.add_argument('--root',required=True);p.add_argument('--completion-binding',type=Path,required=True);p.add_argument('--completion-sha256',required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--verified-receipts',type=Path);p.add_argument('--verified-sha256');p.add_argument('--final-authorization',type=Path);p.add_argument('--final-authorization-sha256');p.add_argument('--existing-final-sha256');a=p.parse_args()
    if a.root!=ROOT:p.error('only frozen merged successor supported')
    if a.mode=='finalize' and not all((a.verified_receipts,a.verified_sha256,a.final_authorization,a.final_authorization_sha256)):p.error('explicit hub-confirmed verification and final-look authorization required')
    print(json.dumps({'status':'saved','artifact':str(a.output),'artifact_sha256':identity(run(a))},sort_keys=True))
