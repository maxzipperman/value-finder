"""Exact captured ancestors read-only; synthetic final1186 responses/temp runtimes only."""
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
from datetime import datetime,timedelta,timezone
import pytest
HERE=Path(__file__).parent
sys.path.insert(0,str(HERE))
import union,epoch,plan,f3a_missing
REAL=union.RUNTIME_BASE
BUNDLE=HERE.parent/'acquisition/football-archive-v4'


def deny(event,args):
    if event in ('socket.connect','socket.getaddrinfo'):raise RuntimeError('Offline tests only')
    if event=='open' and isinstance(args[0],(str,bytes)):
        p=Path(str(args[0]));flags=args[2] if len(args)>2 else 0
        if p.name in ('.env','player_week.parquet','pricing_cohort.json','game_outcomes.parquet') or '/data/forward/' in str(p):raise RuntimeError('No keys/outcomes/holdout')
        if str(p).startswith(str(REAL)) and isinstance(flags,int) and flags&(os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC):raise RuntimeError('No real runtime writes')
    if event in ('os.rename','os.remove','os.mkdir','os.rmdir') and any(isinstance(a,(str,bytes)) and str(a).startswith(str(REAL)) for a in args[:2]):raise RuntimeError('No real runtime mutation')
sys.addaudithook(deny)


def atomic(path,obj):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_bytes(json.dumps(obj,sort_keys=True,separators=(',',':'),ensure_ascii=False,default=str).encode()+b'\n')


def offline(cert,commit):
    p=cert['proposal'];line=f"APPROVED offline missing: proposal {cert['proposal_sha256']}, ledger {p['prior_ledger_sha256']}, request {p['request_id']}, response {p['response_sha256']}, commit {commit}"
    return {'status':'approved','execution_commit':commit,'proposal_sha256':cert['proposal_sha256'],'prior_ledger_sha256':p['prior_ledger_sha256'],
        'request_id':p['request_id'],'response_sha256':p['response_sha256'],'hub_go_ahead':{
        'comment_url':'https://github.com/maxzipperman/value-finder/pull/99#issuecomment-1','comment_body':line}}


@pytest.fixture(scope='module')
def snapshot(tmp_path_factory):
    base=tmp_path_factory.mktemp('union-snapshot')
    packets={}
    for name,root in [('execution-v1/F2',union.ORIGINAL_ROOT),('followups/F2-pilot',union.PILOT_ROOT),
        ('recovery-v1/F2-continuation',union.SECOND_ROOT),('recovery-v2/F2-second-continuation',union.CONTINUATION_ROOT)]:
        packets[name]=union.packet(HERE.parent/name,root)
    states={};paths={};pins={}
    roots=[union.SOURCE_ROOT,union.PILOT_ROOT,union.ORIGINAL_ROOT,union.SECOND_ROOT]
    for root in roots:
        st=union.json_file(REAL/root/'spending-ledger.json')
        if st.get('predecessor_seed'):
            previous=st['predecessor_seed']['root'];st['predecessor_seed'].update(ledger_path=str(paths[previous]),ledger_sha256=pins[previous])
        path=base/root/'spending-ledger.json';atomic(path,st);states[root]=st;paths[root]=path;pins[root]=union.sha(path)
        shutil.copyfile(REAL/root/'INITIALIZED.json',path.parent/'INITIALIZED.json')
        atomic(base/'registrations'/(root+'.json'),{'bundle_root_sha256':root,'authorization_sha256':st['authorization_sha256'],'runtime_path':str(path.parent.resolve())})
        if root!=union.SOURCE_ROOT:shutil.copytree(REAL/root/'receipts',path.parent/'receipts')
    c1=packets['recovery-v1/F2-continuation']['missing-certificate.json']
    c1['post_ledger_sha256']=pins[union.ORIGINAL_ROOT]
    packets['recovery-v1/F2-continuation']['seed.json']=states[union.SECOND_ROOT]['predecessor_seed']
    for root in (union.ORIGINAL_ROOT,union.SECOND_ROOT):shutil.copytree(REAL/root/'recovery',paths[root].parent/'recovery')
    atomic(paths[union.ORIGINAL_ROOT].parent/('missing-approval-'+c1['proposal_sha256']+'.json'),offline(c1,union.FIRST_COMMIT))
    oldrun=union.json_file(REAL/union.SECOND_ROOT/'run-manifest.json')
    oldrun.update(seed=states[union.SECOND_ROOT]['predecessor_seed'],missing_certificate=c1)
    atomic(paths[union.SECOND_ROOT].parent/'run-manifest.json',oldrun)
    c2=packets['recovery-v2/F2-second-continuation']['missing-certificate.json']
    c2['proposal']['historical_run_manifest_sha256']=union.sha(paths[union.SECOND_ROOT].parent/'run-manifest.json')
    c2['proposal_sha256']=union.digest(union.canonical(c2['proposal']))
    st=states[union.SECOND_ROOT];st['missing_resolution']['proposal_sha256']=c2['proposal_sha256']
    st['attempts'][union.SECOND_MISSING]['missing_resolution_proposal_sha256']=c2['proposal_sha256']
    atomic(paths[union.SECOND_ROOT],st);pins[union.SECOND_ROOT]=union.sha(paths[union.SECOND_ROOT]);c2['post_ledger_sha256']=pins[union.SECOND_ROOT]
    atomic(paths[union.SECOND_ROOT].parent/('missing-approval-'+c2['proposal_sha256']+'.json'),offline(c2,union.CONTINUATION_COMMIT))
    for root in (union.SECOND_ROOT,):atomic(base/'registrations'/(root+'.json'),{'bundle_root_sha256':root,'authorization_sha256':states[root]['authorization_sha256'],'runtime_path':str(paths[root].parent.resolve())})
    final=packets['recovery-v2/F2-second-continuation'];seed=final['seed.json']
    seed.update(ledger_path=str(paths[union.SECOND_ROOT]),ledger_sha256=pins[union.SECOND_ROOT])
    auth=union.json_file(Path('/private/tmp/value-finder-f2-second-continuation-authorization.json'))
    state={'bundle_root_sha256':union.CONTINUATION_ROOT,'authorization_sha256':union.digest(union.canonical(auth)),
        'probe_credits':1687,'status':'event_epoch_complete','pending':None,'stopped':None,'predecessor_seed':seed,
        'slice_cap':23720,'other_usage_reserved':union.total_without_probe(st),'attempts':{},'cache_reuse':{},'accepted_missing_reuse':{},
        'provider_used':119869,'provider_remaining':4880131}
    oldpolicy=packets['recovery-v1/F2-continuation']['provider-only-missing-policy.json']
    for owner in roots[1:]:
        for rid,a in states[owner]['attempts'].items():
            if a['status']=='completed':state['cache_reuse'][rid]=a['response_sha256']
            else:state['accepted_missing_reuse'][rid]=(c1['proposal_sha256'] if owner==union.ORIGINAL_ROOT else c2['proposal_sha256'] if rid==union.SECOND_MISSING else union.digest(union.canonical(oldpolicy)))
    import pyarrow as pa
    import pyarrow.parquet as pq
    used=96149
    for row in final['requests.json']:
        if not row['max_new_credits']:continue
        used+=20;at=plan.ts(row['requested_utc']);stamp=at-timedelta(minutes=5)
        body={'timestamp':plan.iso(stamp),'previous_timestamp':plan.iso(stamp-timedelta(minutes=5)),'next_timestamp':plan.iso(stamp+timedelta(minutes=5)),
            'data':{'id':row['event_id'],'sport_key':plan.NFL,'bookmakers':[]}}
        headers={'x-requests-last':'20','x-requests-used':str(used),'x-requests-remaining':str(5000000-used)}
        record={'cache_key':row['cache_key'],'sport':row['sport'],'source':row['source'],'url':plan.BASE+row['path'],
            'params_json':json.dumps(row['params']),'http_status':200,'body':json.dumps(body),'headers_json':json.dumps(headers),'fetched_at':datetime(2026,10,2,tzinfo=timezone.utc)}
        cache=base/union.CONTINUATION_ROOT/'data/raw'/row['sport']/row['source']/row['requested_utc'][:10]/(row['cache_key']+'.parquet')
        cache.parent.mkdir(parents=True,exist_ok=True);pq.write_table(pa.Table.from_pylist([record]),cache)
        receipt=base/union.CONTINUATION_ROOT/'receipts'/(row['request_id']+'.json')
        atomic(receipt,{'request_id':row['request_id'],'cache_key':row['cache_key'],'record_sha256':union.sha(cache),'record':record,'headers':headers})
        state['attempts'][row['request_id']]={'status':'completed','cache_key':row['cache_key'],'send_started':True,'reserved_credits':20,'billed_credits':20,
            'response_path':str(cache),'response_sha256':union.sha(cache),'receipt_sha256':union.sha(receipt)}
    atomic(base/union.CONTINUATION_ROOT/'spending-ledger.json',state)
    atomic(base/union.CONTINUATION_ROOT/'INITIALIZED.json',{'bundle_root_sha256':union.CONTINUATION_ROOT,'probe_credits':1687})
    atomic(base/'registrations'/(union.CONTINUATION_ROOT+'.json'),{'bundle_root_sha256':union.CONTINUATION_ROOT,'authorization_sha256':state['authorization_sha256'],'runtime_path':str((base/union.CONTINUATION_ROOT).resolve())})
    atomic(base/union.CONTINUATION_ROOT/'run-manifest.json',{'epoch_root':union.CONTINUATION_ROOT,'commit':union.CONTINUATION_COMMIT,'seed':seed,
        'missing_certificate':c2,'exact_missing_policy':final['exact-missing-policy.json'],'frozen_source_root':union.SOURCE_ROOT,'request_set_sha256':final['manifest.json']['request_set_sha256']})
    return base,packets,pins,auth


@pytest.fixture
def prepared(snapshot,tmp_path,monkeypatch):
    base,packets,pins,auth=snapshot
    shutil.copytree(base,tmp_path/'state')
    # Snapshot's evidence paths remain read-only; per-test ledger/receipt mutations target its private copy.
    target=tmp_path/'state';newpackets=copy.deepcopy(packets);newstates={}
    previous=None
    for root in [union.SOURCE_ROOT,union.PILOT_ROOT,union.ORIGINAL_ROOT,union.SECOND_ROOT,union.CONTINUATION_ROOT]:
        path=target/root/'spending-ledger.json';st=union.json_file(path)
        if previous:
            st['predecessor_seed'].update(ledger_path=str(target/previous/'spending-ledger.json'),ledger_sha256=union.sha(target/previous/'spending-ledger.json'))
        if root==union.ORIGINAL_ROOT:newpackets['recovery-v1/F2-continuation']['missing-certificate.json']['post_ledger_sha256']=None
        atomic(path,st);newstates[root]=st;previous=root
    # Recertify relocated fixture references with the same original commit semantics.
    c1=newpackets['recovery-v1/F2-continuation']['missing-certificate.json'];c1['post_ledger_sha256']=union.sha(target/union.ORIGINAL_ROOT/'spending-ledger.json')
    st=newstates[union.SECOND_ROOT];newpackets['recovery-v1/F2-continuation']['seed.json']=st['predecessor_seed']
    run=union.json_file(target/union.SECOND_ROOT/'run-manifest.json');run.update(seed=st['predecessor_seed'],missing_certificate=c1);atomic(target/union.SECOND_ROOT/'run-manifest.json',run)
    c2=newpackets['recovery-v2/F2-second-continuation']['missing-certificate.json']
    c2['proposal']['historical_run_manifest_sha256']=union.sha(target/union.SECOND_ROOT/'run-manifest.json');c2['proposal_sha256']=union.digest(union.canonical(c2['proposal']))
    st['missing_resolution']['proposal_sha256']=c2['proposal_sha256'];st['attempts'][union.SECOND_MISSING]['missing_resolution_proposal_sha256']=c2['proposal_sha256'];atomic(target/union.SECOND_ROOT/'spending-ledger.json',st)
    c2['post_ledger_sha256']=union.sha(target/union.SECOND_ROOT/'spending-ledger.json')
    atomic(target/union.ORIGINAL_ROOT/('missing-approval-'+c1['proposal_sha256']+'.json'),offline(c1,union.FIRST_COMMIT))
    atomic(target/union.SECOND_ROOT/('missing-approval-'+c2['proposal_sha256']+'.json'),offline(c2,union.CONTINUATION_COMMIT))
    final=newpackets['recovery-v2/F2-second-continuation'];final['seed.json']=newstates[union.CONTINUATION_ROOT]['predecessor_seed']
    final['seed.json']['ledger_sha256']=c2['post_ledger_sha256']
    st=newstates[union.CONTINUATION_ROOT];st['accepted_missing_reuse'][union.SECOND_MISSING]=c2['proposal_sha256'];atomic(target/union.CONTINUATION_ROOT/'spending-ledger.json',st)
    run=union.json_file(target/union.CONTINUATION_ROOT/'run-manifest.json');run.update(seed=final['seed.json'],missing_certificate=c2);atomic(target/union.CONTINUATION_ROOT/'run-manifest.json',run)
    for root in (union.SOURCE_ROOT,union.PILOT_ROOT,union.ORIGINAL_ROOT,union.SECOND_ROOT,union.CONTINUATION_ROOT):
        obj=union.json_file(target/'registrations'/(root+'.json'));obj['runtime_path']=str((target/root).resolve());atomic(target/'registrations'/(root+'.json'),obj)
    monkeypatch.setattr(union,'RUNTIME_BASE',target)
    monkeypatch.setattr(epoch,'ROOT_BASE',target)
    for name,root in [('SOURCE_LEDGER_SHA',union.SOURCE_ROOT),('PILOT_SHA',union.PILOT_ROOT),('PARTIAL_SHA',union.ORIGINAL_ROOT),('SECOND_PARTIAL_SHA',union.SECOND_ROOT)]:
        monkeypatch.setattr(union,name,union.sha(target/root/'spending-ledger.json'))
    reader=union.packet
    monkeypatch.setattr(union,'packet',lambda folder,root:copy.deepcopy(newpackets[str(Path(folder).relative_to(HERE.parent))]))
    return target,newpackets,auth


def test_full_five_root_union_and_missing_denominators(prepared):
    target,packets,auth=prepared;cert,report=union.validate(auth)
    assert cert['request_slots']==1773 and cert['opportunity_count']==1774
    assert report['denominators']['book_market_cells']==35480
    assert sum(c['counts']['denominator'] for c in report['book_market_coverage'])==35480
    assert {c['identity_type'] for c in report['book_market_coverage']}=={'canonical','provider-only'}
    assert cert['missing_categories']=={'initial_offline_missing':1,'historical_provider_only_missing':4,'canonical_offline_missing':1,'prospective_exact_slot_missing':0}
    assert report['accounting']['cumulative_reserved']==121676 and len(report['response_evidence'])==1773
    assert cert['continuation_commit']==union.CONTINUATION_COMMIT
    assert not cert['outcomes_joined'] and not cert['purchase_authorized']


@pytest.mark.parametrize('fault',['pending','stopped','not-complete','first-backup','second-backup','first-commit','second-commit','old-registration','new-registration','old-run','new-run','receipt','cache','debit','reuse','missing-reuse','wrong-hash','duplicate'])
def test_union_rejects_missing_changed_evidence(prepared,fault):
    target,packets,auth=prepared;path=target/union.CONTINUATION_ROOT/'spending-ledger.json';state=union.json_file(path)
    if fault in ('pending','stopped'):state[fault]='SYNTHETIC'
    if fault=='not-complete':state['status']='in_progress'
    if fault=='debit':state['other_usage_reserved']-=1
    if fault=='reuse':state['cache_reuse'].pop(next(iter(state['cache_reuse'])))
    if fault=='missing-reuse':state['accepted_missing_reuse'].pop(union.SECOND_MISSING)
    if fault=='duplicate':state['attempts'][union.SECOND_MISSING]=copy.deepcopy(next(iter(state['attempts'].values())))
    atomic(path,state)
    if fault in ('first-backup','second-backup'):
        root=union.ORIGINAL_ROOT if fault=='first-backup' else union.SECOND_ROOT
        next((target/root/'recovery').glob('original-ledger-*.json')).unlink()
    if fault in ('first-commit','second-commit'):
        root=union.ORIGINAL_ROOT if fault=='first-commit' else union.SECOND_ROOT
        cert=packets['recovery-v1/F2-continuation' if fault=='first-commit' else 'recovery-v2/F2-second-continuation']['missing-certificate.json']
        ap=target/root/('missing-approval-'+cert['proposal_sha256']+'.json');obj=union.json_file(ap);obj['execution_commit']='f'*40;atomic(ap,obj)
    if fault in ('old-registration','new-registration'):(target/'registrations'/((union.SECOND_ROOT if fault=='old-registration' else union.CONTINUATION_ROOT)+'.json')).unlink()
    if fault in ('old-run','new-run'):(target/(union.SECOND_ROOT if fault=='old-run' else union.CONTINUATION_ROOT)/'run-manifest.json').unlink()
    if fault=='receipt':next((target/union.CONTINUATION_ROOT/'receipts').glob('*.json')).unlink()
    if fault=='cache':
        rid=next(iter(state['attempts']));a=state['attempts'][rid];a['response_sha256']='a'*64;atomic(path,state)
    with pytest.raises(Exception):union.validate(auth,expected_ledger_sha256='0'*64 if fault=='wrong-hash' else None)


def test_authenticates_both_offline_at_original_commits_only(prepared,monkeypatch):
    auth=prepared[2];seen=[]
    def comment(obj,authenticate):
        if authenticate:seen.append(obj['execution_commit'])
    monkeypatch.setattr(union,'authenticated_comment',comment)
    union.validate(auth,authenticate=True)
    assert seen==[union.FIRST_COMMIT,union.CONTINUATION_COMMIT]



def test_all1186_prospective_missings_keep_full_denominators(prepared):
    target,pk,auth=prepared;path=target/union.CONTINUATION_ROOT/'spending-ledger.json';state=union.json_file(path)
    policy=pk['recovery-v2/F2-second-continuation']['exact-missing-policy.json'];psha=union.digest(union.canonical(policy))
    import pyarrow as pa
    import pyarrow.parquet as pq
    for rid,a in state['attempts'].items():
        rp=target/union.CONTINUATION_ROOT/'receipts'/(rid+'.json');receipt=union.json_file(rp);record=receipt['record']
        record.update(http_status=404,body=json.dumps({'error_code':'EVENT_NOT_FOUND'}),
            headers_json=json.dumps({'x-requests-last':'0','x-requests-used':'96149','x-requests-remaining':'4903851'}))
        cache=target/union.CONTINUATION_ROOT/'data/raw'/'synthetic-missing'/(rid+'.parquet');cache.parent.mkdir(parents=True,exist_ok=True)
        pq.write_table(pa.Table.from_pylist([record]),cache)
        receipt.update(record=record,record_sha256=union.sha(cache),headers=json.loads(record['headers_json']),status='missing',missing_policy_sha256=psha,
            reason='exact requested slot absent; reservation retained')
        atomic(rp,receipt)
        a.update(status='missing',billed_credits=0,response_path=str(cache),response_sha256=union.sha(cache),receipt_sha256=union.sha(rp),missing_policy_sha256=psha)
    state.update(provider_used=96149,provider_remaining=4903851);atomic(path,state)
    cert,report=union.validate(auth)
    assert cert['missing_categories']['prospective_exact_slot_missing']==1186
    assert report['response_coverage']['valid']==581 and report['denominators']['request_slots']==1773
    assert sum(c['counts']['denominator'] for c in report['book_market_coverage'])==35480
    assert report['accounting']['continuation_billed']==0 and report['accounting']['cumulative_reserved']==121676



@pytest.mark.parametrize('index',range(5))
@pytest.mark.parametrize('kind',['registration-omitted','registration-tampered','initialization-omitted','initialization-tampered'])
def test_all_five_roots_require_original_markers(prepared,index,kind):
    target,pk,auth=prepared
    root=[union.SOURCE_ROOT,union.PILOT_ROOT,union.ORIGINAL_ROOT,union.SECOND_ROOT,union.CONTINUATION_ROOT][index]
    path=target/'registrations'/(root+'.json') if kind.startswith('registration') else target/root/'INITIALIZED.json'
    if kind.endswith('omitted'):path.unlink()
    else:
        obj=union.json_file(path)
        if kind.startswith('registration'):obj['authorization_sha256']='0'*64
        else:obj['probe_credits']=0
        atomic(path,obj)
    with pytest.raises((ValueError,OSError)):union.validate(auth)
