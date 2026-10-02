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
CONTINUATION_ROOT='4053703d09fdcedb6ce1608c8a5a0d09d3e702a6426891463163224e10af792e'
CONTINUATION_COMMIT='20bcaa35d3d5b6f93d292062c2480e3edb82a83a'
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


def paid_approval(auth,m,policy,authenticate):
    cost=m['new_credits'];commit=CONTINUATION_COMMIT;root=CONTINUATION_ROOT;hub=auth.get('hub_go_ahead',{})
    expected=f"APPROVED paid run: list {m['request_list_sha256']}, request-set {m['request_set_sha256']}, budget {cost} credits, commit {commit}"
    if (auth.get('status')!='approved' or auth.get('bundle_root_sha256')!=root or auth.get('execution_commit')!=commit
        or auth.get('priority')!=1 or auth.get('max_new_credits')!=26140 or not auth.get('human_authorization_evidence')
        or any(hub.get(k)!=v for k,v in {'status':'approved','bundle_root_sha256':root,'request_list_sha256':m['request_list_sha256'],
            'request_set_sha256':m['request_set_sha256'],'budget_credits':cost,'commit':commit}.items())):
        raise ValueError('Exact continuation approval differs')
    ceiling=auth.get('account_reconciliation',{}).get('max_baseline_used')
    if type(ceiling) is not int or ceiling<0:raise ValueError('Explicit previous stage account ceiling required')
    lines=hub.get('comment_body','').splitlines()
    if any(line not in lines for line in [expected,
        f'APPROVED account ceiling: max-baseline-used {ceiling}, root {root}',
        f"APPROVED provider-only missing policy: sha256 {digest(canonical(policy))}, max-missing 63, root {root}"]):
        raise ValueError('Continuation paid/account/policy approval lines differ')
    authenticated_comment(auth,authenticate)


def offline_approval(auth,cert,authenticate):
    p=cert['proposal'];expected=(f"APPROVED offline missing: proposal {cert['proposal_sha256']}, ledger {STOPPED_SHA}, "
        f"request {KNOWN_MISSING}, response {KNOWN_RESPONSE_SHA}, commit {CONTINUATION_COMMIT}")
    if (auth.get('status')!='approved' or auth.get('execution_commit')!=CONTINUATION_COMMIT
        or auth.get('proposal_sha256')!=cert['proposal_sha256'] or auth.get('prior_ledger_sha256')!=STOPPED_SHA
        or auth.get('request_id')!=KNOWN_MISSING or auth.get('response_sha256')!=KNOWN_RESPONSE_SHA
        or expected not in auth.get('hub_go_ahead',{}).get('comment_body','').splitlines()):raise ValueError('Exact offline missing approval differs')
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
    if kind=='known_offline_missing':
        if (attempt['missing_resolution_proposal_sha256']!=cert['proposal_sha256']
            or attempt['response_sha256']!=KNOWN_RESPONSE_SHA or attempt['receipt_sha256']!=cert['proposal']['receipt_sha256']):
            raise ValueError('Exact initial missing certificate differs')
    elif kind=='prospective_provider_only_missing':
        psha=digest(canonical(policy))
        if (attempt.get('missing_policy_sha256')!=psha or receipt.get('missing_policy_sha256')!=psha
            or receipt['request_id'] not in policy['eligible_request_ids']):raise ValueError('Prospective missing outside exact policy')
    else:raise ValueError('Unapproved missing category')


def validate(authorization, *, authenticate=False):
    """Only this pinned completed union; never generic partial/stopped acceptance."""
    tree=HERE.parent
    original=packet(tree/'execution-v1/F2',ORIGINAL_ROOT)
    pilot_packet=packet(tree/'followups/F2-pilot',PILOT_ROOT)
    recovery=packet(tree/'recovery-v1/F2-continuation',CONTINUATION_ROOT)
    rows=original['requests.json'];ops=original['opportunities.json'];m=recovery['manifest.json'];cr=recovery['requests.json']
    if len(rows)!=1773 or len(ops)!=1774 or original['manifest.json']['books']!=m['books'] or len(m['books'])!=10:
        raise ValueError('Exact full-union denominator differs')
    if recovery['opportunities.json']!=ops:raise ValueError('Continuation dropped/changed opportunities')
    if {r['request_id'] for r in rows}!={r['request_id'] for r in cr}:raise ValueError('Continuation slot union differs')
    no_cache={'max_new_credits','cache_source','cache_sha256'}
    for r,c in zip(rows,cr):
        if {k:v for k,v in r.items() if k not in no_cache}!={k:v for k,v in c.items() if k not in no_cache}:
            raise ValueError('Original request scope/identity changed')
    policy=recovery['provider-only-missing-policy.json'];cert=recovery['missing-certificate.json']
    if policy!=expected_policy(cr,ops) or digest(canonical(policy))!=m['provider_only_missing_policy_sha256']:raise ValueError('Pinned prospective policy differs')
    if cert['post_ledger_sha256']!=PARTIAL_SHA or cert['proposal_sha256']!=digest(canonical(cert['proposal'])):
        raise ValueError('Exact partial certificate differs')
    state,path,ledger_sha=fixed_ledger(CONTINUATION_ROOT)
    if state['status']!='event_epoch_complete':raise ValueError('Continuation not complete; F3a remains blocked')
    partial,partial_path,partial_sha=fixed_ledger(ORIGINAL_ROOT,PARTIAL_SHA)
    if partial['status']!='event_epoch_partial_reconciled' or partial['missing_resolution']['proposal_sha256']!=cert['proposal_sha256']:
        raise ValueError('Exact terminal partial certificate missing')
    pilot,pilot_path,pilot_sha=fixed_ledger(PILOT_ROOT,PILOT_SHA)
    first,first_path,first_sha=fixed_ledger(SOURCE_ROOT,SOURCE_LEDGER_SHA)
    if pilot['status']!='event_epoch_complete' or first['status']!='recent_complete_stopped_before_older':raise ValueError('Original ancestors incomplete')
    if any(a['status'] not in ('completed','missing') for a in first['attempts'].values()):raise ValueError('Unresolved original F1 ancestor')
    seed_link(pilot['predecessor_seed'],SOURCE_ROOT,first,first_path,first_sha)
    seed_link(partial['predecessor_seed'],PILOT_ROOT,pilot,pilot_path,pilot_sha)
    seed_link(state['predecessor_seed'],ORIGINAL_ROOT,partial,partial_path,partial_sha)
    if state['predecessor_seed']!=recovery['seed.json']:raise ValueError('Continuation changed frozen partial seed')
    for later,earlier in [(pilot,first),(partial,pilot),(state,partial)]:
        if later['other_usage_reserved']<total_without_probe(earlier):raise ValueError('Ancestor cumulative debit reduced')
    backup=partial_path.parent/'recovery'/('original-ledger-'+STOPPED_SHA+'.json')
    if sha(backup)!=STOPPED_SHA:raise ValueError('Exact stopped bytes missing/changed')
    offline_path=partial_path.parent/('missing-approval-'+cert['proposal_sha256']+'.json')
    offline=json_file(offline_path);offline_approval(offline,cert,authenticate)
    paid_approval(authorization,m,policy,authenticate)
    auth_sha=digest(canonical(authorization))
    marker=json_file(RUNTIME_BASE/'registrations'/(CONTINUATION_ROOT+'.json'))
    if marker!={'bundle_root_sha256':CONTINUATION_ROOT,'authorization_sha256':auth_sha,'runtime_path':str(path.parent.resolve())} or state['authorization_sha256']!=auth_sha:
        raise ValueError('Completed continuation authorization/registration differs')
    run=json_file(path.parent/'run-manifest.json')
    if (run['epoch_root']!=CONTINUATION_ROOT or run['commit']!=CONTINUATION_COMMIT or run['seed']!=recovery['seed.json']
        or run['missing_certificate']!=cert or run['provider_only_missing_policy']!=policy or run['frozen_source_root']!=SOURCE_ROOT):
        raise ValueError('Completed run manifest differs')
    new={r['request_id'] for r in cr if r['max_new_credits']}
    reused={r['request_id']:r['cache_sha256'] for r in cr if not r['max_new_credits'] and r['request_id']!=KNOWN_MISSING}
    if (len(new)!=1307 or set(state['attempts'])!=new or state['cache_reuse']!=reused
        or state.get('accepted_missing_reuse')!={KNOWN_MISSING:cert['proposal_sha256']}
        or state['slice_cap']!=26140 or sum(a['reserved_credits'] for a in state['attempts'].values())!=26140):
        raise ValueError('Completed continuation allowlist/reuse/cap differs')
    pilot_ids={r['request_id'] for r in pilot_packet['requests.json']}
    old_ids={r['request_id'] for r in rows if r['max_new_credits']} - new
    if len(old_ids)!=418 or set(partial['attempts'])!=old_ids or set(pilot['attempts'])!=pilot_ids or len(pilot_ids)!=48:
        raise ValueError('417 plus one initial missing /48 pilot ancestor union differs')
    if set(first['attempts']) & {r['request_id'] for r in rows}:raise ValueError('Unexpected original F1 identity overlap')
    if set(partial['cache_reuse'])-pilot_ids:raise ValueError('Unknown partial pilot reuse')
    bundle=tree/'acquisition/football-archive-v4'
    proto=curves.protocol_from(bundle,original['manifest.json'])
    responses={};evidence=[];missing_counts={'known_offline_missing':0,'prospective_provider_only_missing':0}
    for row in rows:
        rid=row['request_id']
        if rid in new:owner,owner_root=state,CONTINUATION_ROOT
        elif rid in old_ids:owner,owner_root=partial,ORIGINAL_ROOT
        elif rid in pilot_ids:owner,owner_root=pilot,PILOT_ROOT
        else:raise ValueError('Slot has no unique paid ancestor')
        attempt=owner['attempts'][rid]
        if attempt['status'] not in ('completed','missing') or attempt['reserved_credits']!=20:raise ValueError('Nonterminal/unreserved union attempt')
        record,receipt,ev=record_for(row,attempt,owner_root)
        if attempt['status']=='missing':
            kind='known_offline_missing' if rid==KNOWN_MISSING and owner_root==ORIGINAL_ROOT else 'prospective_provider_only_missing'
            if kind=='prospective_provider_only_missing' and owner_root!=CONTINUATION_ROOT:raise ValueError('Unexpected ancestor missing')
            missing_response(record,attempt,receipt,kind,cert,policy);missing_counts[kind]+=1
            responses[rid]={'body':None,'reason':kind};ev['missing_category']=kind
        else:
            body,reason=curves.response_body(row,record,proto)
            if reason:raise ValueError('Claimed completed response violates original envelope: '+reason)
            responses[rid]={'body':body,'reason':None}
        evidence.append(ev)
    if missing_counts['known_offline_missing']!=1 or missing_counts['prospective_provider_only_missing']>63:
        raise ValueError('Terminal missing counts outside exact certificates')
    total=1687+total_without_probe(state)
    for cap in ('first_tranche_cumulative_credits','day_one_cumulative_ceiling','broader_cumulative_ceiling'):
        if total>proto['budgets'][cap]:raise ValueError('Completed union cumulative cap exceeded')
    if state['provider_remaining']<proto['budgets']['account_reserve_floor']:raise ValueError('Completed union reserve floor breached')
    report=curves.summarize(original['manifest.json'],rows,ops,responses,proto)
    report.update({'schema':'completed-f2-union-v1','acquisition_complete':True,'root':CONTINUATION_ROOT,
        'ledger_sha256':ledger_sha,'missing_categories':missing_counts,'response_evidence':evidence,
        'accounting':{'continuation_reserved':26140,'continuation_billed':sum(a['billed_credits'] for a in state['attempts'].values()),
            'original_partial_reserved':8360,'original_partial_billed':8340,'pilot_reserved':960,
            'cumulative_reserved':total,'provider_used':state['provider_used'],'provider_remaining':state['provider_remaining']},
        'approval_authenticated_live':authenticate})
    certificate={'schema':'completed-f2-union-certificate-v1','continuation_root':CONTINUATION_ROOT,'continuation_commit':CONTINUATION_COMMIT,
        'continuation_ledger_sha256':ledger_sha,'partial_ledger_sha256':partial_sha,'pilot_ledger_sha256':pilot_sha,'source_ledger_sha256':first_sha,
        'stopped_backup_sha256':STOPPED_SHA,'offline_approval_sha256':sha(offline_path),'continuation_approval_sha256':auth_sha,
        'missing_certificate_sha256':digest(canonical(cert)),'prospective_policy_sha256':digest(canonical(policy)),
        'response_evidence_sha256':digest(canonical(evidence)),'coverage_sha256':digest(canonical({k:v for k,v in report.items() if k!='approval_authenticated_live'})+b'\n'),
        'missing_categories':missing_counts,'cumulative_debit_without_probe':total_without_probe(state),
        'opportunity_count':1774,'request_slots':1773,'books':original['manifest.json']['books'],
        'market_keys':['alternate_spreads','alternate_totals'],'scope_seasons':[2023,2024,2025],
        'actual_play_certified':False,'strategy_grading_enabled':False,'outcomes_joined':False,'purchase_authorized':False}
    for p,expected in [(path,ledger_sha),(partial_path,partial_sha),(pilot_path,pilot_sha),(first_path,first_sha)]:
        if sha(p)!=expected:raise ValueError('Union changed during read; no certificate')
    packet(tree/'execution-v1/F2',ORIGINAL_ROOT);packet(tree/'recovery-v1/F2-continuation',CONTINUATION_ROOT)
    return certificate,report


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--continuation-authorization',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True);p.add_argument('--certificate-out',type=Path,required=True)
    p.add_argument('--authenticate',action='store_true');a=p.parse_args()
    cert,report=validate(json_file(a.continuation_authorization),authenticate=a.authenticate)
    for path,obj in [(a.out,report),(a.certificate_out,cert)]:
        path.parent.mkdir(parents=True,exist_ok=True)
        with path.open('xb') as handle:handle.write(canonical(obj)+b'\n');handle.flush();os.fsync(handle.fileno())
    print(json.dumps({'certificate':cert,'denominators':report['denominators'],'missing':report['missing_categories'],'paired_by_season':report['paired_by_season']},indent=2))
