"""Trusted v2 data-only verification of specific immutable partial ancestors.

No execution/import of paid v1 modules. Historical paid approval is exhausted;
its pinned archive identity, registration and run manifest are evidence only.
Offline approvals authenticate at their ORIGINAL implementation commits.
"""
import hashlib
import json
from pathlib import Path
import epoch
import plan

FIRST_ROOT='059fc135b00bbbc36db208a8bb622d7444a43d42bb2607675d30671ad455f4e4'
SECOND_ROOT='4053703d09fdcedb6ce1608c8a5a0d09d3e702a6426891463163224e10af792e'
FIRST_POST='cc2f17d3289ac1dbebac6bcf5d828f4384f2ea4c9d88829c2d8510a014a57313'
FIRST_STOP='fb9edfb65460c5f4fe84539ac2405b8e49d813dd5f9892bd32692bfbc86a4163'
FIRST_COMMIT='20bcaa35d3d5b6f93d292062c2480e3edb82a83a'
HISTORICAL_AUTH='9adb99cc9b3439da75556ff031c96d2669850921b9a4a8c0bf1743cd2948086b'


def digest(obj):return hashlib.sha256(plan.canonical(obj)).hexdigest()


def frozen(packet,root):
    import missing
    packet=Path(packet)
    if packet.is_symlink() or packet.parent.is_symlink():raise ValueError('Regular frozen packet required')
    paths={f'code/{p.name}':p for p in packet.parent.glob('*.py')}
    for p in packet.iterdir():
        if p.is_symlink() or not p.is_file():raise ValueError('Regular frozen files required')
        if p.name!='FREEZE.json':paths[p.name]=p
    files={name:hashlib.sha256(missing.regular_bytes(p)).hexdigest() for name,p in sorted(paths.items())}
    cert=json.loads(missing.regular_bytes(packet/'FREEZE.json'))
    if cert!={'root':root,'files':files} or digest(files)!=root:raise ValueError('Historical frozen bytes changed')
    return packet


def first_certificate():
    packet=frozen(Path(__file__).parent.parent/'recovery-v1/F2-continuation',SECOND_ROOT)
    return json.loads((packet/'missing-certificate.json').read_text())


def terminal(state,cert,root,prior):
    p=cert['proposal'];rid=p['request_id'];a=state['attempts'][rid]
    if (state['bundle_root_sha256']!=root or state['status']!='event_epoch_partial_reconciled'
        or state['pending'] or state['stopped'] or p['original_root']!=root or p['prior_ledger_sha256']!=prior
        or digest(p)!=cert['proposal_sha256'] or state['missing_resolution']['proposal_sha256']!=cert['proposal_sha256']
        or a['status']!='missing' or a['reserved_credits']!=20 or a['billed_credits']!=0
        or a['response_sha256']!=p['response_sha256'] or a['receipt_sha256']!=p['receipt_sha256']):
        raise ValueError('Explicit partial certificate differs')


def offline(cert,commit,bundle,authenticate):
    p=cert['proposal'];folder=epoch.ROOT_BASE/p['original_root']
    if plan.sha(folder/'recovery'/('original-ledger-'+p['prior_ledger_sha256']+'.json'))!=p['prior_ledger_sha256']:
        raise ValueError('Exact stopped bytes missing/changed')
    auth=json.loads((folder/('missing-approval-'+cert['proposal_sha256']+'.json')).read_text())
    line=(f"APPROVED offline missing: proposal {cert['proposal_sha256']}, ledger {p['prior_ledger_sha256']}, "
          f"request {p['request_id']}, response {p['response_sha256']}, commit {commit}")
    if (auth.get('status')!='approved' or auth.get('execution_commit')!=commit
        or auth.get('proposal_sha256')!=cert['proposal_sha256'] or auth.get('prior_ledger_sha256')!=p['prior_ledger_sha256']
        or auth.get('request_id')!=p['request_id'] or auth.get('response_sha256')!=p['response_sha256']
        or auth.get('hub_go_ahead',{}).get('comment_body','').splitlines().count(line)!=1):
        raise ValueError('Original-commit offline approval differs')
    import re
    if not re.fullmatch(r'https://github\.com/maxzipperman/value-finder/pull/99#issuecomment-[0-9]+',auth['hub_go_ahead'].get('comment_url','')):
        raise ValueError('Offline approval URL invalid')
    if authenticate:epoch.source_executor(bundle).verify_live_hub_comment(auth)
    return auth


def verify_first(bundle,authenticate=True):
    cert=first_certificate();path=epoch.ROOT_BASE/FIRST_ROOT/'spending-ledger.json'
    if plan.sha(path)!=FIRST_POST or cert['post_ledger_sha256']!=FIRST_POST:raise ValueError('First partial pin differs')
    terminal(json.loads(path.read_text()),cert,FIRST_ROOT,FIRST_STOP)
    offline(cert,FIRST_COMMIT,bundle,authenticate)
    return cert


def historical(state):
    folder=epoch.ROOT_BASE/SECOND_ROOT
    registration=json.loads((epoch.ROOT_BASE/'registrations'/f'{SECOND_ROOT}.json').read_text())
    if (state['authorization_sha256']!=HISTORICAL_AUTH or registration!={'bundle_root_sha256':SECOND_ROOT,
        'authorization_sha256':HISTORICAL_AUTH,'runtime_path':str(folder.resolve())}):
        raise ValueError('Historical authorization/registration pin differs')
    manifest=json.loads((folder/'run-manifest.json').read_text())
    packet=frozen(Path(__file__).parent.parent/'recovery-v1/F2-continuation',SECOND_ROOT)
    m=json.loads((packet/'manifest.json').read_text())
    oldpolicy=json.loads((packet/'provider-only-missing-policy.json').read_text())
    if (manifest['epoch_root']!=SECOND_ROOT or manifest['commit']!=FIRST_COMMIT
        or manifest['seed']!=state['predecessor_seed'] or manifest['missing_certificate']!=first_certificate()
        or manifest['provider_only_missing_policy']!=oldpolicy or manifest['request_set_sha256']!=m['request_set_sha256']):
        raise ValueError('Historical run manifest differs')
    # No live paid-comment authentication: exhausted approvals never authorize new sends.
    return oldpolicy


def verify_second(cert,bundle,*,expected_commit,authenticate=True):
    import missing
    path=epoch.ROOT_BASE/SECOND_ROOT/'spending-ledger.json'
    if plan.sha(path)!=cert['post_ledger_sha256']:raise ValueError('Second partial pin differs')
    state=json.loads(path.read_text());terminal(state,cert,SECOND_ROOT,missing.STOPPED_SHA)
    historical(state)
    if cert['proposal']['historical_run_manifest_sha256']!=plan.sha(path.parent/'run-manifest.json'):
        raise ValueError('Historical run manifest bytes changed')
    offline(cert,expected_commit,bundle,authenticate)
    return state


def seed_state(seed,rows,seen=None):
    seen=set() if seen is None else seen
    root=seed['root'];path=Path(seed['ledger_path'])
    pins={epoch.PRIOR_ROOT:epoch.SEED_HASH,epoch.PILOT_ROOT:epoch.PILOT_LEDGER_SHA,FIRST_ROOT:FIRST_POST,
          SECOND_ROOT:epoch.partial_certificate()['post_ledger_sha256']} if root==SECOND_ROOT else {epoch.PRIOR_ROOT:epoch.SEED_HASH,epoch.PILOT_ROOT:epoch.PILOT_LEDGER_SHA,FIRST_ROOT:FIRST_POST}
    if root in seen or root not in pins or seed['ledger_sha256']!=pins[root] or path.resolve()!=epoch.ROOT_BASE/root/'spending-ledger.json' or plan.sha(path)!=pins[root]:
        raise ValueError('Unreviewed/cyclic/changed ancestor')
    seen.add(root);state=json.loads(path.read_text())
    if state['bundle_root_sha256']!=root or state['pending'] or state['stopped'] or state['probe_credits']!=1687:
        raise ValueError('Unresolved ancestor')
    if root==FIRST_ROOT:terminal(state,first_certificate(),root,FIRST_STOP)
    elif root==SECOND_ROOT:
        import missing
        terminal(state,epoch.partial_certificate(),root,missing.STOPPED_SHA)
    elif state['status'] not in ('recent_complete_stopped_before_older','event_epoch_complete'):raise ValueError('Incomplete ancestor')
    if any(a['status'] not in ('completed','missing') or type(a['reserved_credits']) is not int or a['reserved_credits']<0
        or type(a.get('billed_credits',0)) is not int or not 0<=a.get('billed_credits',0)<=a['reserved_credits'] for a in state['attempts'].values()):raise ValueError('Ancestor debit/attempt invalid')
    if type(state['other_usage_reserved']) is not int or state['other_usage_reserved']<0:raise ValueError('Ancestor debit invalid')
    debit=state['other_usage_reserved']+sum(a['reserved_credits'] for a in state['attempts'].values())
    if seed['cumulative_debit_without_probe']!=debit or seed['probe_credits']!=1687:raise ValueError('Ancestor debit decreased')
    if {r['request_id'] for r in rows if r['max_new_credits']} & set(state['attempts']):raise ValueError('Ancestor request cannot be repurchased')
    if root!=epoch.PRIOR_ROOT:
        wanted={SECOND_ROOT:FIRST_ROOT,FIRST_ROOT:epoch.PILOT_ROOT,epoch.PILOT_ROOT:epoch.PRIOR_ROOT}[root]
        if state['predecessor_seed']['root']!=wanted:raise ValueError('Exact ancestry order differs')
        if state['other_usage_reserved']<seed_state(state['predecessor_seed'],rows,seen):raise ValueError('Ancestor debit decreased')
    return debit


def missing_record(row,record):
    import policy
    base=epoch.source_executor(Path(__file__).parent.parent/'acquisition/football-archive-v4')
    # Trusted evidence validator; exact missing eligibility checked separately by root/certificate/policy.
    original=dict(row,max_new_credits=row['max_credits'])
    return policy.valid(original,record,{'eligible_request_ids':[row['request_id']]},base)


def records(state,rows,bundle,allow_pending=None):
    import missing
    base=epoch.source_executor(bundle);byid={r['request_id']:r for r in rows};proofs={}
    folder=epoch.ROOT_BASE/state['bundle_root_sha256']
    oldpolicy=historical(state) if state['bundle_root_sha256']==SECOND_ROOT else None
    cert1=first_certificate();cert2=epoch.partial_certificate() if state['bundle_root_sha256']==SECOND_ROOT and state['status']=='event_epoch_partial_reconciled' else None
    for rid,a in state['attempts'].items():
        if rid==allow_pending:continue
        if rid not in byid:raise ValueError('Attempt outside original request universe')
        row=byid[rid];receipt_path=folder/'receipts'/f'{rid}.json'
        if plan.sha(receipt_path)!=a['receipt_sha256']:raise ValueError('Ancestor receipt changed')
        evidence=json.loads(missing.regular_bytes(receipt_path));record=missing.cached_record(Path(a['response_path']),a['response_sha256'])
        if (a['cache_key']!=row['cache_key'] or a['reserved_credits']!=20 or not a.get('send_started')
            or evidence['request_id']!=rid or evidence['cache_key']!=row['cache_key'] or evidence['record_sha256']!=a['response_sha256']
            or base.canonical(evidence['record'])!=base.canonical(record) or evidence['headers']!=json.loads(record['headers_json'])):raise ValueError('Ancestor receipt binding differs')
        if a['status']=='completed':
            epoch.event_valid(row,record,base,json.loads((bundle/'protocol.json').read_text()))
            if base.integer(evidence['headers']['x-requests-last'])!=a['billed_credits']:raise ValueError('Ancestor billing differs')
            proof=a['receipt_sha256']
        elif a['status']=='missing':
            missing_record(row,record)
            if a['billed_credits']!=0 or evidence.get('status')!='missing':raise ValueError('Missing debit/status differs')
            if state['bundle_root_sha256']==FIRST_ROOT:
                if rid!=cert1['proposal']['request_id'] or a['response_sha256']!=cert1['proposal']['response_sha256']:raise ValueError('First missing differs')
                proof=cert1['proposal_sha256']
            elif cert2 and rid==cert2['proposal']['request_id']:
                if a['response_sha256']!=cert2['proposal']['response_sha256']:raise ValueError('Second missing differs')
                proof=cert2['proposal_sha256']
            elif oldpolicy and rid in oldpolicy['eligible_request_ids'] and a.get('missing_policy_sha256')==digest(oldpolicy) and evidence.get('missing_policy_sha256')==digest(oldpolicy):proof=digest(oldpolicy)
            else:raise ValueError('Unreviewed ancestor missing')
        else:raise ValueError('Unresolved ancestor attempt')
        proofs[rid]={**a,'proof_sha256':proof}
    return proofs


def reuse(seed,rows,bundle):
    proofs={};seen=set()
    while seed['root']!=epoch.PRIOR_ROOT:
        if seed['root'] in seen:raise ValueError('Cyclic reuse')
        seen.add(seed['root']);state=json.loads(Path(seed['ledger_path']).read_text())
        got=records(state,rows,bundle)
        if proofs.keys() & got.keys():raise ValueError('Duplicate ancestor acquisition')
        proofs.update(got);seed=state['predecessor_seed']
    for row in rows:
        a=proofs.get(row['request_id'])
        if a and (row['max_new_credits'] or row['cache_source']!=a['response_path'] or row['cache_sha256']!=a['response_sha256']):raise ValueError('Exact ancestor reuse differs')
        if not row['max_new_credits'] and not a:raise ValueError('Reuse has no ancestor receipt')
    return proofs
