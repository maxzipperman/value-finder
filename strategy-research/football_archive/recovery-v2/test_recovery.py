"""Offline adversarial tests, real captured evidence read-only, fake keys/transport only."""
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
import epoch,missing,plan,policy,ancestry
BUNDLE=HERE.parent/'acquisition/football-archive-v4'
REAL_RUNTIME=epoch.ROOT_BASE


def deny(event,args):
    if event in ('socket.connect','socket.getaddrinfo'):raise RuntimeError('Offline only')
    if event=='open' and isinstance(args[0],(str,bytes)):
        path=Path(str(args[0]));flags=args[2] if len(args)>2 else 0
        if path.name in ('.env','player_week.parquet','pricing_cohort.json','game_outcomes.parquet') or '/data/forward/' in str(path):raise RuntimeError('No secrets/outcomes')
        if str(path).startswith(str(REAL_RUNTIME)) and isinstance(flags,int) and flags&(os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC):raise RuntimeError('No actual runtime write')
    if event in ('os.rename','os.remove','os.mkdir','os.rmdir') and any(isinstance(a,(str,bytes)) and str(a).startswith(str(REAL_RUNTIME)) for a in args[:2]):raise RuntimeError('No actual runtime mutation')
sys.addaudithook(deny)


def offline_auth(cert):
    p=cert['proposal'];commit='b'*40
    line=f"APPROVED offline missing: proposal {cert['proposal_sha256']}, ledger {p['prior_ledger_sha256']}, request {p['request_id']}, response {p['response_sha256']}, commit {commit}"
    return {'status':'approved','proposal_sha256':cert['proposal_sha256'],'prior_ledger_sha256':p['prior_ledger_sha256'],
        'request_id':p['request_id'],'response_sha256':p['response_sha256'],'execution_commit':commit,
        'hub_go_ahead':{'comment_url':'https://github.com/maxzipperman/value-finder/pull/99#issuecomment-1','comment_body':line}}


def paid_auth(root,m,packet):
    body=(f"APPROVED paid run: list {m['request_list_sha256']}, request-set {m['request_set_sha256']}, budget {m['new_credits']} credits, commit {'b'*40}\nAPPROVED account ceiling: max-baseline-used 200000, root {root}")
    obj=json.loads((packet/'exact-missing-policy.json').read_text());body+='\n'+policy.approval_line(obj,root)
    return {'status':'approved','bundle_root_sha256':root,'priority':1,'max_new_credits':m['new_credits'],
        'human_authorization_evidence':'SYNTHETIC ONLY','execution_commit':'b'*40,
        'hub_go_ahead':{'status':'approved','bundle_root_sha256':root,'request_set_sha256':m['request_set_sha256'],
            'request_list_sha256':m['request_list_sha256'],'budget_credits':m['new_credits'],'commit':'b'*40,
            'comment_url':'https://github.com/maxzipperman/value-finder/pull/99#issuecomment-1','comment_body':body},
        'account_reconciliation':{'status':'approved','bundle_root_sha256':root,'baseline_mode':'capture_first_free_check',
            'reason':'Synthetic only','owner_note':'Synthetic only','max_baseline_used':200000,
            'billing_period_utc':datetime.now(timezone.utc).strftime('%Y-%m')}}


class Response:
    def __init__(self,body,headers,status=200):self.text,self.headers,self.status_code=body,headers,status


class Session:
    def __init__(self,mode='ok'):
        from requests.adapters import HTTPAdapter
        self.adapters={'https':HTTPAdapter(max_retries=0)};self.used=96149;self.remaining=4903851;self.calls=[];self.mode=mode
    def get(self,url,params=None,**kwargs):
        assert kwargs['allow_redirects'] is False
        self.calls.append((url,params))
        if url.endswith('/sports'):return Response('[]',{'x-requests-last':'0','x-requests-used':str(self.used),'x-requests-remaining':str(self.remaining)})
        if self.mode=='timeout':
            import requests
            raise requests.Timeout('synthetic')
        missing_response=self.mode.startswith('missing')
        if not missing_response:self.used+=20;self.remaining-=20
        h={'x-requests-last':'0' if missing_response else '20','x-requests-used':str(self.used),'x-requests-remaining':str(self.remaining)}
        at=plan.ts(params['date']);stamp=at-timedelta(minutes=5)
        body={'timestamp':plan.iso(stamp),'previous_timestamp':plan.iso(stamp-timedelta(minutes=5)),
            'next_timestamp':plan.iso(stamp+timedelta(minutes=5)),'data':{'id':url.split('/')[-2],'sport_key':plan.NFL,'bookmakers':[]}}
        status=200
        if missing_response:body={'error_code':'EVENT_NOT_FOUND'};status=404
        if self.mode in ('billing','missing-counters'):h.pop('x-requests-last')
        if self.mode=='overcharge':h['x-requests-last']='21'
        if self.mode in ('reset','missing-reset'):h.update({'x-requests-used':'0','x-requests-remaining':'5000000'})
        if self.mode=='lag':body['timestamp']=plan.iso(at-timedelta(hours=1))
        if self.mode in ('external','missing-external'):h['x-requests-used']=str(self.used+101)
        if self.mode=='missing-code':body['error_code']='OTHER'
        if self.mode=='missing-billing':h['x-requests-last']='1'
        if self.mode=='missing-keyecho':body['message']=params['apiKey']
        if self.mode=='missing-floor':h['x-requests-remaining']='531629'
        if self.mode=='missing-lag':h['x-requests-used']=str(self.used-101)
        if self.mode in ('403','404','429'):status=int(self.mode)
        return Response(json.dumps(body),h,status)
    def close(self):pass


@pytest.fixture
def prepared(tmp_path,monkeypatch):
    base=epoch.source_executor(BUNDLE)
    monkeypatch.setattr(epoch,'ROOT_BASE',tmp_path/'state');monkeypatch.setattr(base,'RUNTIME_BASE',epoch.ROOT_BASE)
    monkeypatch.setattr(base,'checkout_commit',lambda _:'b'*40);monkeypatch.setattr(epoch,'source_executor',lambda _:base)
    monkeypatch.setattr(epoch,'checkout_clean',lambda _:None)
    cert1=ancestry.first_certificate()
    # Keep cache data read-only at captured paths. Only pointers and corresponding test hashes change.
    roots=[epoch.PRIOR_ROOT,epoch.PILOT_ROOT,ancestry.FIRST_ROOT,ancestry.SECOND_ROOT]
    paths={};states={}
    for root in roots:
        state=json.loads((REAL_RUNTIME/root/'spending-ledger.json').read_text())
        if state.get('predecessor_seed'):
            prior=state['predecessor_seed']['root'];state['predecessor_seed'].update(ledger_path=str(paths[prior]),ledger_sha256=plan.sha(paths[prior]))
        path=epoch.ROOT_BASE/root/'spending-ledger.json';base.atomic(path,state);paths[root]=path;states[root]=state
        if (REAL_RUNTIME/root/'receipts').exists():shutil.copytree(REAL_RUNTIME/root/'receipts',path.parent/'receipts')
    monkeypatch.setattr(epoch,'SEED_HASH',plan.sha(paths[epoch.PRIOR_ROOT]));monkeypatch.setattr(epoch,'PILOT_LEDGER_SHA',plan.sha(paths[epoch.PILOT_ROOT]))
    cert1['post_ledger_sha256']=plan.sha(paths[ancestry.FIRST_ROOT]);monkeypatch.setattr(ancestry,'FIRST_POST',cert1['post_ledger_sha256'])
    monkeypatch.setattr(ancestry,'first_certificate',lambda:cert1)
    first=paths[ancestry.FIRST_ROOT].parent
    shutil.copytree(REAL_RUNTIME/ancestry.FIRST_ROOT/'recovery',first/'recovery')
    shutil.copyfile(REAL_RUNTIME/ancestry.FIRST_ROOT/('missing-approval-'+cert1['proposal_sha256']+'.json'),first/('missing-approval-'+cert1['proposal_sha256']+'.json'))
    second=paths[ancestry.SECOND_ROOT].parent
    run=json.loads((REAL_RUNTIME/ancestry.SECOND_ROOT/'run-manifest.json').read_text());run.update(seed=states[ancestry.SECOND_ROOT]['predecessor_seed'],missing_certificate=cert1)
    base.atomic(second/'run-manifest.json',run)
    base.atomic(epoch.ROOT_BASE/'registrations'/f'{ancestry.SECOND_ROOT}.json',{'bundle_root_sha256':ancestry.SECOND_ROOT,'authorization_sha256':ancestry.HISTORICAL_AUTH,'runtime_path':str(second.resolve())})
    src=Path(json.loads((HERE/'F2-second-continuation/missing-certificate.json').read_text())['proposal']['response_path'])
    dest=second/'data/raw'/src.relative_to(REAL_RUNTIME/ancestry.SECOND_ROOT/'data/raw');dest.parent.mkdir(parents=True);shutil.copyfile(src,dest)
    monkeypatch.setattr(missing,'STOPPED_SHA',plan.sha(paths[ancestry.SECOND_ROOT]))
    # pilot gate separately covered by immutable pilot tests; this fixture changes its ledger pointer.
    monkeypatch.setattr(epoch,'pilot_gate',lambda _: {'remainder_gate_passed':True})
    cert,post,receipt,rows=missing.preview(BUNDLE)
    packet=tmp_path/'packet';shutil.copytree(HERE/'F2-second-continuation',packet)
    for row in rows:
        a=post['attempts'].get(row['request_id'])
        if a:row.update(max_new_credits=0,cache_source=a['response_path'],cache_sha256=a['response_sha256'])
    m=json.loads((packet/'manifest.json').read_text());m=plan.write_packet(packet,m,rows,json.loads((packet/'opportunities.json').read_text()))
    base.atomic(packet/'missing-certificate.json',cert)
    seed=json.loads((packet/'seed.json').read_text());seed.update(ledger_path=str(paths[ancestry.SECOND_ROOT]),ledger_sha256=cert['post_ledger_sha256'])
    base.atomic(packet/'seed.json',seed)
    info=json.loads((packet/'cache-reconciliation.json').read_text())
    actual_roots=set(info['raw_roots']);discover=epoch.known_raw_roots
    monkeypatch.setattr(epoch,'known_raw_roots',lambda own_root=None:sorted(actual_roots|set(discover(own_root))))
    info['raw_roots']=epoch.known_raw_roots();info['request_set_sha256']=m['request_set_sha256'];base.atomic(packet/'cache-reconciliation.json',info)
    root=epoch.freeze(packet);auth=tmp_path/'offline.json';base.atomic(auth,offline_auth(cert))
    monkeypatch.setattr(epoch,'partial_certificate',lambda:cert)
    return packet,root,cert,post,receipt,paths[ancestry.SECOND_ROOT],auth,base,m


def apply(p,checkpoint=lambda _:None):return missing.transition(BUNDLE,p[0]/'missing-certificate.json',p[6],fake_auth=True,checkpoint=checkpoint)


def run(p,session,checkpoint=lambda _:None,key='SYNTHETIC_KEY_ONLY'):
    return epoch.run(p[0],p[1],BUNDLE,paid_auth(p[1],p[8],p[0]),key=key,fake_session=session,checkpoint=checkpoint)


def test_real_preview_immutable():
    path=REAL_RUNTIME/missing.ORIGINAL_ROOT/'spending-ledger.json';before=plan.sha(path)
    cert,post,receipt,rows=missing.preview(BUNDLE)
    assert len(post['attempts'])==121 and post['attempts'][missing.REQUEST]['reserved_credits']==20
    assert sum(a['status']=='missing' for a in post['attempts'].values())==5
    assert sum(r['max_new_credits']>0 and r['request_id'] not in post['attempts'] for r in rows)==1186
    assert plan.sha(path)==before


def test_transition_exact_preservation(prepared):
    before=json.loads(prepared[5].read_text());result=apply(prepared);after=json.loads(prepared[5].read_text())
    assert result['reserved']==2420 and result['billed']==2320 and result['paid_calls']==0
    for rid,a in before['attempts'].items():
        if rid!=missing.REQUEST:assert after['attempts'][rid]==a
    for key in before:
        if key not in ('attempts','pending','stopped','status'):assert after[key]==before[key]
    with pytest.raises(ValueError):apply(prepared)


@pytest.mark.parametrize('field',['status','proposal_sha256','prior_ledger_sha256','request_id','response_sha256','execution_commit'])
def test_bad_offline_approval(prepared,field):
    auth=json.loads(prepared[6].read_text());auth[field]='wrong';prepared[7].atomic(prepared[6],auth)
    with pytest.raises(ValueError):apply(prepared)
    assert plan.sha(prepared[5])==missing.STOPPED_SHA


@pytest.mark.parametrize('point',['after_original_backup','after_approval','after_missing_receipt','after_missing_transition'])
def test_transition_crash(prepared,point):
    def crash(at):
        if at==point:raise RuntimeError('crash')
    with pytest.raises(RuntimeError):apply(prepared,crash)
    state=json.loads(prepared[5].read_text());assert sum(a['reserved_credits'] for a in state['attempts'].values())==2420
    assert plan.sha(prepared[5].parent/'recovery'/('original-ledger-'+missing.STOPPED_SHA+'.json'))==missing.STOPPED_SHA
    if point!='after_missing_transition':apply(prepared)
    else:
        with pytest.raises(ValueError):apply(prepared)


def test_no_transition_no_key(prepared):
    session=Session();reads=[]
    with pytest.raises(Exception):run(prepared,session,key=lambda:reads.append(1))
    assert not reads and not session.calls


@pytest.mark.parametrize('mode',['ok','missing'])
def test_full_exact_1186_preserves_581_valid_6_missing(prepared,mode):
    apply(prepared);session=Session(mode);result=run(prepared,session)
    assert len(session.calls)==1187 and result['new_reserved']==23720 and result['cumulative_reserved']==121676
    assert result['new_billed']==(23720 if mode=='ok' else 0)
    state=json.loads((prepared[7].runtime_path(prepared[1])/'spending-ledger.json').read_text())
    assert len(state['cache_reuse'])==581 and len(state['accepted_missing_reuse'])==6
    if mode=='missing':assert sum(a['status']=='missing' for a in state['attempts'].values())==1186
    old={r['request_id'] for r in json.loads((prepared[0]/'requests.json').read_text()) if not r['max_new_credits']}
    assert not old & set(state['attempts'])
    assert state['status']=='event_epoch_complete'
    rid=next(iter(state['attempts']));(prepared[7].runtime_path(prepared[1])/'receipts'/f'{rid}.json').unlink()
    reads=[];again=Session()
    with pytest.raises(Exception):run(prepared,again,key=lambda:reads.append(1))
    assert not reads and not again.calls


@pytest.mark.parametrize('mode',['timeout','billing','overcharge','reset','lag','external','403','404','429','missing-code','missing-billing','missing-counters','missing-reset','missing-external','missing-keyecho','missing-floor','missing-lag'])
def test_adverse_halts_and_restart_never_sends(prepared,mode):
    apply(prepared);session=Session(mode)
    with pytest.raises(Exception):run(prepared,session)
    assert len(session.calls)==2
    again=Session();reads=[]
    with pytest.raises(Exception):run(prepared,again,key=lambda:reads.append(1))
    assert not reads and not again.calls


@pytest.mark.parametrize('point',['after_reservation','after_send_started','after_cache_durability','after_receipt_durability'])
def test_send_crash_unresolved_no_resend(prepared,point):
    apply(prepared);session=Session('missing')
    def crash(at):
        if at==point:raise RuntimeError('crash')
    with pytest.raises(RuntimeError):run(prepared,session,crash)
    again=Session();reads=[]
    with pytest.raises(Exception):run(prepared,again,key=lambda:reads.append(1))
    assert not reads and not again.calls


@pytest.mark.parametrize('fault',['first-backup','first-approval-commit','second-backup','receipt','registration','debit','global-stop','policy-line'])
def test_missing_ancestor_or_approval_evidence_prekey(prepared,fault):
    apply(prepared);base=prepared[7];first=epoch.ROOT_BASE/ancestry.FIRST_ROOT
    if fault=='first-backup':next((first/'recovery').glob('original-ledger-*.json')).unlink()
    if fault=='first-approval-commit':
        path=next(first.glob('missing-approval-*.json'));obj=json.loads(path.read_text());obj['execution_commit']='b'*40;base.atomic(path,obj)
    if fault=='second-backup':next((prepared[5].parent/'recovery').glob('original-ledger-*.json')).unlink()
    if fault=='receipt':next((prepared[5].parent/'receipts').glob('*.json')).unlink()
    if fault=='registration':(epoch.ROOT_BASE/'registrations'/f'{ancestry.SECOND_ROOT}.json').unlink()
    if fault=='debit':
        obj=json.loads(prepared[5].read_text());obj['other_usage_reserved']-=1;base.atomic(prepared[5],obj)
    if fault=='global-stop':base.atomic(epoch.ROOT_BASE/('e'*64)/'spending-ledger.json',{'pending':'OTHER','stopped':'OTHER'})
    reads=[];session=Session();auth=paid_auth(prepared[1],prepared[8],prepared[0])
    if fault=='policy-line':auth['hub_go_ahead']['comment_body']='\n'.join(x for x in auth['hub_go_ahead']['comment_body'].splitlines() if not x.startswith('APPROVED exact'))
    with pytest.raises(Exception):epoch.run(prepared[0],prepared[1],BUNDLE,auth,key=lambda:reads.append(1),fake_session=session)
    assert not reads and not session.calls


def test_exact_policy_canonical_provider_only_and_identity():
    packet=HERE/'F2-second-continuation';rows=json.loads((packet/'requests.json').read_text());ops=json.loads((packet/'opportunities.json').read_text());obj=policy.expected(rows,ops)
    assert len(obj['eligible_request_ids'])==1186 and missing.REQUEST not in obj['eligible_request_ids']
    kinds={o['identity_type'] for o in ops if o.get('request_id') in obj['eligible_request_ids']};assert kinds=={'canonical','provider-only'}
    row=next(r for r in rows if r['max_new_credits']);base=epoch.source_executor(BUNDLE)
    rec={'cache_key':row['cache_key'],'sport':row['sport'],'source':row['source'],'url':plan.BASE+row['path'],'params_json':json.dumps(row['params']),'http_status':404,'body':'{"error_code":"EVENT_NOT_FOUND"}','headers_json':'{"x-requests-last":"0","x-requests-used":"96149","x-requests-remaining":"4903851"}'}
    policy.valid(row,rec,obj,base)
    for field in ('cache_key','sport','source','url','params_json','http_status','body','headers_json'):
        bad=dict(rec);bad[field]='WRONG'
        with pytest.raises(Exception):policy.valid(row,bad,obj,base)


def test_historical_second_original_commit_explicit_for_downstream(prepared,monkeypatch):
    apply(prepared);base=prepared[7];monkeypatch.setattr(base,'checkout_commit',lambda _:'c'*40)
    observed=[];monkeypatch.setattr(base,'verify_live_hub_comment',lambda auth:observed.append(auth['execution_commit']))
    ancestry.verify_first(BUNDLE,authenticate=True)
    ancestry.verify_second(prepared[2],BUNDLE,expected_commit='b'*40,authenticate=True)
    assert observed==[ancestry.FIRST_COMMIT,'b'*40]
    with pytest.raises(ValueError):ancestry.verify_second(prepared[2],BUNDLE,expected_commit='c'*40,authenticate=False)


def test_missing_after_terminal_commit_crash_still_halts_no_resend(prepared):
    apply(prepared);session=Session('missing')
    def crash(at):
        if at=='after_terminal_ledger':raise RuntimeError('crash')
    with pytest.raises(RuntimeError):run(prepared,session,crash)
    state=json.loads((prepared[7].runtime_path(prepared[1])/'spending-ledger.json').read_text())
    assert len(state['attempts'])==1 and next(iter(state['attempts'].values()))['status']=='missing'
    assert state['stopped']
    reads=[];again=Session()
    with pytest.raises(Exception):run(prepared,again,key=lambda:reads.append(1))
    assert not reads and not again.calls


@pytest.mark.parametrize('kind',['global','isolated','known-store-overlap'])
def test_new_store_inventory_and_exact_overlap_before_key(prepared,monkeypatch,kind):
    apply(prepared);packet,root,*_=prepared
    row=next(r for r in json.loads((packet/'requests.json').read_text()) if r['max_new_credits'])
    if kind=='global':raw=epoch.ROOT_BASE/('f'*64)/'data/raw'
    elif kind=='isolated':
        project=packet.parent/'isolated-checkouts';monkeypatch.setattr(epoch,'PROJECT',project)
        raw=project/'later-worker/sharp-markets/data/raw'
    else:raw=Path(json.loads((packet/'cache-reconciliation.json').read_text())['raw_roots'][0])
    # Never write a real store in the overlap test; freeze a temporary known store instead.
    if kind=='known-store-overlap':
        raw=packet.parent/'temporary-known/data/raw';raw.mkdir(parents=True)
        discover=epoch.known_raw_roots;monkeypatch.setattr(epoch,'known_raw_roots',lambda own_root=None:sorted(set(discover(own_root))|{str(raw.resolve())}))
        info=json.loads((packet/'cache-reconciliation.json').read_text());info['raw_roots']=epoch.known_raw_roots(root);prepared[7].atomic(packet/'cache-reconciliation.json',info)
        root=epoch.freeze(packet)
    hit=raw/row['sport']/row['source']/'2024-01-01'/(row['cache_key']+'.parquet');hit.parent.mkdir(parents=True);hit.write_bytes(b'SYNTHETIC exact-key overlap only')
    reads=[];session=Session()
    with pytest.raises(Exception):epoch.run(packet,root,BUNDLE,paid_auth(root,prepared[8],packet),key=lambda:reads.append(1),fake_session=session)
    assert not reads and not session.calls


def test_inventory_excludes_own_output_but_keeps_other_roots(tmp_path,monkeypatch):
    monkeypatch.setattr(epoch,'ROOT_BASE',tmp_path)
    own='1'*64;other='2'*64
    for root in (own,other):(tmp_path/root/'data/raw').mkdir(parents=True)
    roots=epoch.known_raw_roots(own)
    assert str(tmp_path/own/'data/raw') not in roots and str(tmp_path/other/'data/raw') in roots



def test_cross_checkout_without_raw_store_is_inventory_portable(tmp_path,monkeypatch):
    before=epoch.known_raw_roots()
    checkout=tmp_path/'another-executing-checkout';checkout.mkdir()
    monkeypatch.setattr(epoch,'REPO',checkout)
    assert epoch.known_raw_roots()==before
    raw=checkout/'sharp-markets/data/raw';raw.mkdir(parents=True)
    assert str(raw.resolve()) in epoch.known_raw_roots()
    assert epoch.known_raw_roots()!=before
