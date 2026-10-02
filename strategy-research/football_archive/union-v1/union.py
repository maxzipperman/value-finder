"""Read-only exact completed F2 union validator. No imports of paid executors/key loaders."""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
sys.dont_write_bytecode=True
import curves
import plan

SOURCE_ROOT=plan.SOURCE_ROOT
SOURCE_LEDGER_SHA='eb9e93e354babef2be73ddaa13ea6e2913c58eaaff706ed4e78aec1381636190'
PILOT_ROOT='cbe125474acf46becd3f7e01903675ece864adb683cdc73734bad7e1635dddcc'
PILOT_SHA='754c81b87bb22af671bcf8cc6d8dd02accd5123296ad43d0ce50a119adc49d77'
ORIGINAL_ROOT='059fc135b00bbbc36db208a8bb622d7444a43d42bb2607675d30671ad455f4e4'
STOPPED_SHA='fb9edfb65460c5f4fe84539ac2405b8e49d813dd5f9892bd32692bfbc86a4163'
PARTIAL_SHA='cc2f17d3289ac1dbebac6bcf5d828f4384f2ea4c9d88829c2d8510a014a57313'
SECOND_ROOT='4053703d09fdcedb6ce1608c8a5a0d09d3e702a6426891463163224e10af792e'
SECOND_STOPPED_SHA='dbf689aae12e74d1a839132e3ca606b504ed8bed97ea2fba4a59a3ce9a2482ca'
SECOND_PARTIAL_SHA='d10808cb0ba3962ff3abdef5d48c09cb53d3a95733e0b3b6c2bc605feccee3aa'
SECOND_AUTH_SHA='9adb99cc9b3439da75556ff031c96d2669850921b9a4a8c0bf1743cd2948086b'
SECOND_MISSING='cbacd1c8b9929a1386777465ca18148ea7feb7a88e6917542cca3a9ff4eba719'
SECOND_RESPONSE_SHA='ff1c10256fc992326336b0c9ecd3d75a555389d96e3fd4a46a58bf5159213e03'
CONTINUATION_ROOT='7485bc1230aeaf069a21e0a75ca9d93002c2e8abccdddaa706e45c5aa63aa467'
FIRST_COMMIT='20bcaa35d3d5b6f93d292062c2480e3edb82a83a'
CONTINUATION_COMMIT='3f29479fd8c9c5798ceb08b0c2d26d3c0e2706cb'
KNOWN_MISSING='850c02077a7ef01010d277ad63cff3a88847548a9a1a70424fa8252ccf632c9a'
KNOWN_RESPONSE_SHA='25923e8f5db247b52ed7b7ca2bdac5f938cbb0d7833e7aad90bdd0bd2dc917b6'
RUNTIME_BASE=Path.home()/'Library/Application Support/ValueFinder/football-acquisition-state'
HERE=Path(__file__).resolve().parent


def canonical(obj):return plan.canonical(obj)
def digest(data):return hashlib.sha256(data).hexdigest()
def read(path):return curves.read_bytes(path)
def sha(path):return digest(read(path))
def json_file(path):return json.loads(read(path))


def packet(folder, root):
    """Independently pinned complete file map; data only, never execute sibling code."""
    folder=Path(folder)
    if folder.is_symlink() or folder.parent.is_symlink():raise ValueError('Ordinary frozen directories required')
    captured={f'code/{p.name}':read(p) for p in folder.parent.glob('*.py')}
    for p in folder.iterdir():
        if p.is_symlink() or not p.is_file():raise ValueError('Regular immediate frozen files only')
        if p.name!='FREEZE.json':captured[p.name]=read(p)
    files={name:digest(data) for name,data in sorted(captured.items())}
    cert=json_file(folder/'FREEZE.json')
    if cert.get('root')!=root or cert.get('files')!=files or digest(canonical(files))!=root:
        raise ValueError('Pinned completed acquisition packet changed')
    return {name:json.loads(data) for name,data in captured.items() if name.endswith('.json') and not name.startswith('code/')}


def fixed_ledger(root,expected_sha=None):
    path=RUNTIME_BASE/root/'spending-ledger.json'
    if path.parent.is_symlink():raise ValueError('Fixed runtime cannot be a symlink')
    data=read(path)
    if expected_sha is not None and digest(data)!=expected_sha:raise ValueError('Pinned predecessor ledger changed')
    state=json.loads(data)
    if state['bundle_root_sha256']!=root or state['probe_credits']!=1687:raise ValueError('Ledger root/probe differs')
    if state['pending'] or state['stopped']:raise ValueError('Unresolved/stopped acquisition; no union certificate')
    return state,path,digest(data)


def total_without_probe(state):
    if type(state['other_usage_reserved']) is not int or state['other_usage_reserved']<0:raise ValueError('Invalid cumulative debit')
    for a in state['attempts'].values():
        if (type(a['reserved_credits']) is not int or a['reserved_credits']<0 or type(a.get('billed_credits',0)) is not int
            or not 0<=a.get('billed_credits',0)<=a['reserved_credits']):raise ValueError('Invalid attempt debit')
    return state['other_usage_reserved']+sum(a['reserved_credits'] for a in state['attempts'].values())


def seed_link(seed,root,state,path,digest_value):
    if (seed['root']!=root or seed['ledger_path']!=str(path) or seed['ledger_sha256']!=digest_value
        or seed['probe_credits']!=1687 or seed['cumulative_debit_without_probe']!=total_without_probe(state)):
        raise ValueError('Exact ancestor seed differs')


def authenticated_comment(auth,authenticate):
    hub=auth['hub_go_ahead'];url=hub.get('comment_url','')
    if not re.fullmatch(r'https://github\.com/maxzipperman/value-finder/pull/99#issuecomment-[0-9]+',url):raise ValueError('Pinned hub comment required')
    if authenticate:
        cid=url.rsplit('-',1)[-1]
        comment=json.loads(subprocess.check_output(['gh','api',f'repos/maxzipperman/value-finder/issues/comments/{cid}'],text=True))
        if comment.get('html_url')!=url or comment.get('body')!=hub['comment_body'] or comment.get('user',{}).get('login')!='maxzipperman':
            raise ValueError('Authenticated approval changed')


def paid_approval(auth,m,policy,authenticate=False):
    # Completed acquisition proof: archived body/hash bound to completed ledger,
    # central registration and exact original implementation; never send authority.
    cost=m['new_credits'];commit=CONTINUATION_COMMIT;root=CONTINUATION_ROOT;hub=auth.get('hub_go_ahead',{})
    expected=f"APPROVED paid run: list {m['request_list_sha256']}, request-set {m['request_set_sha256']}, budget {cost} credits, commit {commit}"
    if (auth.get('status')!='approved' or auth.get('bundle_root_sha256')!=root or auth.get('execution_commit')!=commit
        or auth.get('priority')!=1 or auth.get('max_new_credits')!=23720 or not auth.get('human_authorization_evidence')
        or any(hub.get(k)!=v for k,v in {'status':'approved','bundle_root_sha256':root,'request_list_sha256':m['request_list_sha256'],
            'request_set_sha256':m['request_set_sha256'],'budget_credits':cost,'commit':commit}.items())):
        raise ValueError('Exact completed recovery-v2 approval differs')
    ceiling=auth.get('account_reconciliation',{}).get('max_baseline_used')
    if type(ceiling) is not int or ceiling<0:raise ValueError('Explicit historical account ceiling required')
    lines=hub.get('comment_body','').splitlines()
    if any(line not in lines for line in [expected,
        f'APPROVED account ceiling: max-baseline-used {ceiling}, root {root}',
        f"APPROVED exact missing policy: sha256 {digest(canonical(policy))}, max-missing 1186, root {root}"]):
        raise ValueError('Historical paid/account/policy approval lines differ')
    authenticated_comment(auth,False)  # Validate URL only. Exhausted paid bodies may change.


def offline_approval(auth,cert,commit,authenticate):
    p=cert['proposal'];expected=(f"APPROVED offline missing: proposal {cert['proposal_sha256']}, ledger {p['prior_ledger_sha256']}, "
        f"request {p['request_id']}, response {p['response_sha256']}, commit {commit}")
    if (auth.get('status')!='approved' or auth.get('execution_commit')!=commit
        or auth.get('proposal_sha256')!=cert['proposal_sha256'] or auth.get('prior_ledger_sha256')!=p['prior_ledger_sha256']
        or auth.get('request_id')!=p['request_id'] or auth.get('response_sha256')!=p['response_sha256']
        or auth.get('hub_go_ahead',{}).get('comment_body','').splitlines().count(expected)!=1):
        raise ValueError('Exact original-commit offline missing approval differs')
    authenticated_comment(auth,authenticate)



def record_for(row,attempt,root):
    import pyarrow as pa
    import pyarrow.parquet as pq
    receipt_path=RUNTIME_BASE/root/'receipts'/(row['request_id']+'.json')
    data=read(Path(attempt['response_path']));receipt_data=read(receipt_path)
    if digest(data)!=attempt['response_sha256'] or digest(receipt_data)!=attempt['receipt_sha256']:raise ValueError('Cache/receipt changed')
    receipt=json.loads(receipt_data);records=pq.read_table(pa.BufferReader(data)).to_pylist()
    if (len(records)!=1 or receipt['request_id']!=row['request_id'] or receipt['cache_key']!=row['cache_key']
        or receipt['record_sha256']!=digest(data) or receipt['record']!=json.loads(json.dumps(records[0],default=str))):
        raise ValueError('Durable receipt/cache record differs')
    record=records[0]
    if (record['cache_key']!=row['cache_key'] or record['sport']!=row['sport'] or record['source']!=row['source']
        or record['url']!=plan.BASE+row['path'] or json.loads(record['params_json'])!=row['params']):raise ValueError('Cached request identity differs')
    headers=json.loads(record['headers_json'])
    if any(not str(headers.get(k,'')).isdigit() for k in ('x-requests-last','x-requests-used','x-requests-remaining')):
        raise ValueError('Missing/invalid cached billing')
    if int(headers['x-requests-last'])!=attempt['billed_credits']:raise ValueError('Receipt bill differs from ledger')
    return record,receipt,{'request_id':row['request_id'],'root':root,'status':attempt['status'],
        'response_sha256':digest(data),'receipt_sha256':digest(receipt_data),'reserved_credits':attempt['reserved_credits'],
        'billed_credits':attempt['billed_credits']}


def expected_policy(rows,ops):
    by_id={o['opportunity_id']:o for o in ops}
    eligible=sorted(r['request_id'] for r in rows if r['max_new_credits'] and r['opportunities']
        and all(by_id[oid]['identity_type']=='provider-only' and by_id[oid]['status']=='planned' for oid in r['opportunities']))
    if len(eligible)!=63 or KNOWN_MISSING in eligible:raise ValueError('Exact 63 unsent provider-only IDs differ')
    return {'schema':'provider-only-zero-billed-event-not-found-v1','scope':'F2 continuation only','original_root':ORIGINAL_ROOT,
        'eligible_request_ids':eligible,'max_missing':63,'maximum_missing_reserved_credits':1260,'source_provider_only_opportunity_bound':64,
        'http_status':404,'error_code':'EVENT_NOT_FOUND','required_last_credits':0,'preserve_full_reservation':True,'no_resend':True,
        'canonical_404_halts':True,'opportunity_and_book_denominators_preserved':True}


def missing_response(record,attempt,receipt,kind,cert,policy):
    try:body=json.loads(record['body'])
    except (ValueError,TypeError):raise ValueError('Malformed missing response') from None
    if (record['http_status']!=404 or not isinstance(body,dict) or body.get('error_code')!='EVENT_NOT_FOUND'
        or int(json.loads(record['headers_json'])['x-requests-last'])!=0
        or attempt['reserved_credits']!=20 or attempt['billed_credits']!=0 or receipt.get('status')!='missing'):
        raise ValueError('Unreviewed terminal missing evidence')
    if kind in ('initial_offline_missing','canonical_offline_missing'):
        p=cert['proposal']
        if (receipt['request_id']!=p['request_id'] or attempt.get('missing_resolution_proposal_sha256')!=cert['proposal_sha256']
            or attempt['response_sha256']!=p['response_sha256'] or attempt['receipt_sha256']!=p['receipt_sha256']):
            raise ValueError('Exact offline missing certificate differs')
    elif kind in ('historical_provider_only_missing','prospective_exact_slot_missing'):
        psha=digest(canonical(policy))
        if (attempt.get('missing_policy_sha256')!=psha or receipt.get('missing_policy_sha256')!=psha
            or receipt['request_id'] not in policy['eligible_request_ids']):raise ValueError('Missing outside exact policy')
    else:raise ValueError('Unapproved missing category')


def check_partial(state,path,certificate,root,stopped_sha,post_sha,request,response,commit,authenticate):
    p=certificate['proposal']
    if (sha(path)!=post_sha or certificate['post_ledger_sha256']!=post_sha
        or certificate['proposal_sha256']!=digest(canonical(p)) or p['original_root']!=root
        or p['prior_ledger_sha256']!=stopped_sha or p['request_id']!=request or p['response_sha256']!=response
        or p['reserved_credits']!=20 or p['billed_credits']!=0
        or state['status']!='event_epoch_partial_reconciled'
        or state['missing_resolution']['proposal_sha256']!=certificate['proposal_sha256']):
        raise ValueError('Precise partial transition certificate differs')
    if sha(path.parent/'recovery'/('original-ledger-'+stopped_sha+'.json'))!=stopped_sha:
        raise ValueError('Exact stopped backup missing/changed')
    auth_path=path.parent/('missing-approval-'+certificate['proposal_sha256']+'.json')
    offline_approval(json_file(auth_path),certificate,commit,authenticate)
    return sha(auth_path)


def registration(root,state,auth_sha):
    path=RUNTIME_BASE/root
    if (state['authorization_sha256']!=auth_sha or json_file(RUNTIME_BASE/'registrations'/(root+'.json'))!={
        'bundle_root_sha256':root,'authorization_sha256':auth_sha,'runtime_path':str(path.resolve())}):
        raise ValueError('Historical authorization/registration differs')


def validate(authorization, *, expected_ledger_sha256=None, authenticate=False):
    """Data-only five-root union API. Downstream freezes returned certificate and
    passes its exact completion hash; no paid modules, key loaders or runtime writes.
    Only the two pinned partials are allowed, at their ORIGINAL implementation commits.
    """
    tree=HERE.parent
    original=packet(tree/'execution-v1/F2',ORIGINAL_ROOT)
    pilot_packet=packet(tree/'followups/F2-pilot',PILOT_ROOT)
    old=packet(tree/'recovery-v1/F2-continuation',SECOND_ROOT)
    final=packet(tree/'recovery-v2/F2-second-continuation',CONTINUATION_ROOT)
    rows=original['requests.json'];ops=original['opportunities.json'];m=final['manifest.json'];fr=final['requests.json'];cr=old['requests.json']
    if len(rows)!=1773 or len(ops)!=1774 or len(m['books'])!=10 or original['manifest.json']['books']!=m['books']:
        raise ValueError('Full original union denominator differs')
    fields={'max_new_credits','cache_source','cache_sha256'}
    for pk in (old,final):
        if pk['opportunities.json']!=ops or len(pk['requests.json'])!=len(rows):raise ValueError('Opportunity/slot universe changed')
        for want,got in zip(rows,pk['requests.json']):
            if {k:v for k,v in want.items() if k not in fields}!={k:v for k,v in got.items() if k not in fields}:raise ValueError('Original identity/slot changed')
    oldpolicy=old['provider-only-missing-policy.json'];policy=final['exact-missing-policy.json']
    cert1=old['missing-certificate.json'];cert2=final['missing-certificate.json']
    if oldpolicy!=expected_policy(cr,ops) or digest(canonical(oldpolicy))!=old['manifest.json']['provider_only_missing_policy_sha256']:
        raise ValueError('Original63-ID missing policy differs')
    # New reviewed policy is pinned by the immutable final packet; derive its exact
    # finite eligible list again and forbid an identity-class/runtime broad predicate.
    new={r['request_id'] for r in fr if r['max_new_credits']}
    if (len(new)!=1186 or policy['eligible_request_ids']!=sorted(new) or policy['max_missing']!=1186
        or policy['maximum_missing_reserved_credits']!=23720 or digest(canonical(policy))!=m['exact_missing_policy_sha256']):
        raise ValueError('Exact1186-ID policy differs')
    state,path,ledger_sha=fixed_ledger(CONTINUATION_ROOT,expected_ledger_sha256)
    if state['status']!='event_epoch_complete':raise ValueError('Final recovery-v2 incomplete; union/F3a blocked')
    second,second_path,second_sha=fixed_ledger(SECOND_ROOT,SECOND_PARTIAL_SHA)
    partial,partial_path,partial_sha=fixed_ledger(ORIGINAL_ROOT,PARTIAL_SHA)
    pilot,pilot_path,pilot_sha=fixed_ledger(PILOT_ROOT,PILOT_SHA)
    first,first_path,first_sha=fixed_ledger(SOURCE_ROOT,SOURCE_LEDGER_SHA)
    if pilot['status']!='event_epoch_complete' or first['status']!='recent_complete_stopped_before_older':
        raise ValueError('Source/pilot incomplete')
    roots=[SOURCE_ROOT,PILOT_ROOT,ORIGINAL_ROOT,SECOND_ROOT,CONTINUATION_ROOT]
    chain=[first,pilot,partial,second,state];paths=[first_path,pilot_path,partial_path,second_path,path]
    hashes=[first_sha,pilot_sha,partial_sha,second_sha,ledger_sha]
    for i in range(1,5):
        seed_link(chain[i]['predecessor_seed'],roots[i-1],chain[i-1],paths[i-1],hashes[i-1])
        if chain[i]['other_usage_reserved']<total_without_probe(chain[i-1]):raise ValueError('Ancestor debit decreased')
    if state['predecessor_seed']!=final['seed.json'] or second['predecessor_seed']!=old['seed.json']:
        raise ValueError('Frozen partial predecessor seed changed')
    offline1=check_partial(partial,partial_path,cert1,ORIGINAL_ROOT,STOPPED_SHA,PARTIAL_SHA,KNOWN_MISSING,KNOWN_RESPONSE_SHA,FIRST_COMMIT,authenticate)
    offline2=check_partial(second,second_path,cert2,SECOND_ROOT,SECOND_STOPPED_SHA,SECOND_PARTIAL_SHA,SECOND_MISSING,SECOND_RESPONSE_SHA,CONTINUATION_COMMIT,authenticate)
    registration(SECOND_ROOT,second,SECOND_AUTH_SHA)
    oldrun=json_file(second_path.parent/'run-manifest.json')
    if (oldrun['epoch_root']!=SECOND_ROOT or oldrun['commit']!=FIRST_COMMIT or oldrun['seed']!=old['seed.json']
        or oldrun['missing_certificate']!=cert1 or oldrun['provider_only_missing_policy']!=oldpolicy
        or oldrun['request_set_sha256']!=old['manifest.json']['request_set_sha256']
        or cert2['proposal']['historical_authorization_sha256']!=SECOND_AUTH_SHA
        or cert2['proposal']['historical_run_manifest_sha256']!=sha(second_path.parent/'run-manifest.json')):
        raise ValueError('Historical stopped-run proof differs')
    paid_approval(authorization,m,policy)
    auth_sha=digest(canonical(authorization));registration(CONTINUATION_ROOT,state,auth_sha)
    run=json_file(path.parent/'run-manifest.json')
    if (run['epoch_root']!=CONTINUATION_ROOT or run['commit']!=CONTINUATION_COMMIT or run['seed']!=final['seed.json']
        or run['missing_certificate']!=cert2 or run['exact_missing_policy']!=policy or run['frozen_source_root']!=SOURCE_ROOT
        or run['request_set_sha256']!=m['request_set_sha256']):
        raise ValueError('Final completed run manifest differs')
    byid={r['request_id']:r for r in rows}
    sets=[set(pilot['attempts']),set(partial['attempts']),set(second['attempts']),set(state['attempts'])]
    if [len(x) for x in sets]!=[48,418,121,1186] or set(state['attempts'])!=new:
        raise ValueError('Exact acquisition partition counts differ')
    acquired=set()
    for ids in sets:
        if acquired & ids:raise ValueError('Duplicate ancestor acquisition')
        acquired.update(ids)
    if acquired!=set(byid):raise ValueError('Incomplete original request-slot union')
    if set(partial['attempts'])!={r['request_id'] for r in rows if r['max_new_credits']} - {r['request_id'] for r in cr if r['max_new_credits']}:
        raise ValueError('First partial allowlist differs')
    if set(second['attempts'])!={r['request_id'] for r in cr if r['max_new_credits']} -new:
        raise ValueError('Second partial allowlist differs')
    reused={r['request_id']:r['cache_sha256'] for r in fr if not r['max_new_credits']}
    expected_valid={};expected_missing={};owners={}
    for st,rt in zip(chain[1:],roots[1:]):
        for rid,a in st['attempts'].items():owners[rid]=(st,rt)
    bundle=tree/'acquisition/football-archive-v4';proto=curves.protocol_from(bundle,original['manifest.json'])
    responses={};evidence=[];missing_counts={k:0 for k in ('initial_offline_missing','historical_provider_only_missing','canonical_offline_missing','prospective_exact_slot_missing')}
    for row in rows:
        rid=row['request_id'];owner,rt=owners[rid];a=owner['attempts'][rid]
        if a['status'] not in ('completed','missing') or a['reserved_credits']!=20 or not a.get('send_started'):
            raise ValueError('Unresolved/unreserved union attempt')
        record,receipt,ev=record_for(row,a,rt)
        if rt!=CONTINUATION_ROOT:
            if reused.get(rid)!=a['response_sha256']:raise ValueError('Frozen reused evidence differs')
        if a['status']=='missing':
            if rt==ORIGINAL_ROOT:kind='initial_offline_missing';c,p=cert1,None
            elif rt==SECOND_ROOT and rid==SECOND_MISSING:kind='canonical_offline_missing';c,p=cert2,None
            elif rt==SECOND_ROOT:kind='historical_provider_only_missing';c,p=None,oldpolicy
            elif rt==CONTINUATION_ROOT:kind='prospective_exact_slot_missing';c,p=None,policy
            else:raise ValueError('Unexpected pilot missing')
            missing_response(record,a,receipt,kind,c,p);missing_counts[kind]+=1
            responses[rid]={'body':None,'reason':kind};ev['missing_category']=kind
            if rt!=CONTINUATION_ROOT:expected_missing[rid]=(c['proposal_sha256'] if c else digest(canonical(p)))
        else:
            body,reason=curves.response_body(row,record,proto)
            if reason:raise ValueError('Completed envelope invalid: '+reason)
            responses[rid]={'body':body,'reason':None}
            if rt!=CONTINUATION_ROOT:expected_valid[rid]=a['response_sha256']
        ev['identity_classes']=sorted({o['identity_type'] for o in ops if o.get('request_id')==rid})
        evidence.append(ev)
    if (missing_counts['initial_offline_missing']!=1 or missing_counts['canonical_offline_missing']!=1
        or missing_counts['historical_provider_only_missing']!=4 or missing_counts['prospective_exact_slot_missing']>1186
        or len(expected_valid)!=581 or len(expected_missing)!=6 or state['cache_reuse']!=expected_valid
        or state.get('accepted_missing_reuse')!=expected_missing or state['slice_cap']!=23720
        or sum(a['reserved_credits'] for a in state['attempts'].values())!=23720):
        raise ValueError('Missing/reuse/cap accounting differs')
    # Earlier stopped epochs retain only reuse visited before their precise stop.
    prior_proofs={}
    for st,rt in zip(chain[1:],roots[1:]):
        valid={rid:a['response_sha256'] for rid,a in prior_proofs.items() if a['status']=='completed'}
        if any(valid.get(rid)!=h for rid,h in st['cache_reuse'].items()):raise ValueError('Historical reused proof differs')
        if rt!=CONTINUATION_ROOT:prior_proofs.update(st['attempts'])
    if sum(a['status']=='completed' for a in partial['attempts'].values())!=417 or sum(a['status']=='completed' for a in second['attempts'].values())!=116:
        raise ValueError('Historical valid partitions differ')
    total=1687+total_without_probe(state)
    for cap in ('first_tranche_cumulative_credits','day_one_cumulative_ceiling','broader_cumulative_ceiling'):
        if total>proto['budgets'][cap]:raise ValueError('Cumulative cap exceeded')
    if type(state['provider_remaining']) is not int or state['provider_remaining']<proto['budgets']['account_reserve_floor']:
        raise ValueError('Completed reserve floor breached')
    report=curves.summarize(original['manifest.json'],rows,ops,responses,proto)
    report.update({'schema':'completed-f2-union-v2','acquisition_complete':True,'root':CONTINUATION_ROOT,
        'ledger_sha256':ledger_sha,'missing_categories':missing_counts,'response_evidence':evidence,
        'accounting':{'continuation_reserved':23720,'continuation_billed':sum(a['billed_credits'] for a in state['attempts'].values()),
            'original_partial_reserved':8360,'original_partial_billed':8340,'second_partial_reserved':2420,
            'second_partial_billed':2320,'pilot_reserved':960,'cumulative_reserved':total,
            'provider_used':state['provider_used'],'provider_remaining':state['provider_remaining']},
        'offline_approvals_authenticated_live':authenticate})
    certificate={'schema':'completed-f2-union-certificate-v2','continuation_root':CONTINUATION_ROOT,'continuation_commit':CONTINUATION_COMMIT,
        'continuation_ledger_sha256':ledger_sha,'partial_ledger_sha256':partial_sha,'second_partial_ledger_sha256':second_sha,
        'pilot_ledger_sha256':pilot_sha,'source_ledger_sha256':first_sha,'stopped_backup_sha256':STOPPED_SHA,
        'second_stopped_backup_sha256':SECOND_STOPPED_SHA,'offline_approval_sha256':offline1,'second_offline_approval_sha256':offline2,
        'continuation_approval_sha256':auth_sha,'historical_continuation_approval_sha256':SECOND_AUTH_SHA,
        'missing_certificate_sha256':digest(canonical(cert1)),'second_missing_certificate_sha256':digest(canonical(cert2)),
        'historical_policy_sha256':digest(canonical(oldpolicy)),'prospective_policy_sha256':digest(canonical(policy)),
        'response_evidence_sha256':digest(canonical(evidence)),
        'coverage_sha256':digest(canonical({k:v for k,v in report.items() if k!='offline_approvals_authenticated_live'})+bytes([10])),
        'missing_categories':missing_counts,'cumulative_debit_without_probe':total_without_probe(state),
        'opportunity_count':1774,'request_slots':1773,'books':original['manifest.json']['books'],
        'market_keys':['alternate_spreads','alternate_totals'],'scope_seasons':[2023,2024,2025],
        'actual_play_certified':False,'strategy_grading_enabled':False,'outcomes_joined':False,'purchase_authorized':False}
    for pp,expected in zip(paths,hashes):
        if sha(pp)!=expected:raise ValueError('Union changed during read')
    packet(tree/'execution-v1/F2',ORIGINAL_ROOT);packet(tree/'recovery-v1/F2-continuation',SECOND_ROOT)
    packet(tree/'recovery-v2/F2-second-continuation',CONTINUATION_ROOT)
    return certificate,report


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--continuation-authorization',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True);p.add_argument('--certificate-out',type=Path,required=True)
    p.add_argument('--authenticate',action='store_true');p.add_argument('--expected-ledger-sha256');a=p.parse_args()
    cert,report=validate(json_file(a.continuation_authorization),expected_ledger_sha256=a.expected_ledger_sha256,authenticate=a.authenticate)
    for path,obj in [(a.out,report),(a.certificate_out,cert)]:
        path.parent.mkdir(parents=True,exist_ok=True)
        with path.open('xb') as handle:handle.write(canonical(obj)+b'\n');handle.flush();os.fsync(handle.fileno())
    print(json.dumps({'certificate':cert,'denominators':report['denominators'],'missing':report['missing_categories'],'paired_by_season':report['paired_by_season']},indent=2))


def verify_downstream_union(final_ledger_path, *, certificate_path=None,
        first_transition_commit=FIRST_COMMIT, second_transition_commit=CONTINUATION_COMMIT,
        authenticate=True):
    """Whole-chain thin wrapper for consumers of a completely captured/pinned module.
    Historical authorization and certificate are captured from that frozen packet;
    a copied downstream certificate must match those exact authenticated bytes.
    """
    pinned=globals().get('PINNED_PACKET')
    if pinned is None:raise ValueError('Use complete verified dependency loader before downstream validation')
    expected=pinned['union-certificate.json']
    if expected.get('schema')!='completed-f2-union-certificate-v2':raise ValueError('Final complete five-root certificate required')
    path=Path(final_ledger_path)
    if path.resolve()!=RUNTIME_BASE/CONTINUATION_ROOT/'spending-ledger.json':
        raise ValueError('Only fixed final recovery-v2 ledger allowed')
    if first_transition_commit!=FIRST_COMMIT or second_transition_commit!=CONTINUATION_COMMIT:
        raise ValueError('Original reviewed transition commits required')
    if certificate_path is not None and json_file(Path(certificate_path))!=expected:
        raise ValueError('Downstream certificate differs from captured frozen certificate')
    got,report=validate(pinned['continuation-authorization.json'],
        expected_ledger_sha256=expected['continuation_ledger_sha256'],authenticate=authenticate)
    if got!=expected:raise ValueError('Full union differs from exact captured certificate')
    return got,report
