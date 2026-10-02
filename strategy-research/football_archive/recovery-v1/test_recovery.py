"""Offline exact 404 transition tests. Never mutate the real global runtime or use a paid key."""
import copy
from datetime import datetime, timedelta, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
sys.dont_write_bytecode=True
import pytest
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import epoch,missing,plan
BUNDLE=HERE.parent/'acquisition/football-archive-v4'
REAL_RUNTIME=epoch.ROOT_BASE


def deny(event,args):
    if event in ('socket.connect','socket.getaddrinfo'):raise RuntimeError('Offline tests prohibit network')
    if event=='open' and isinstance(args[0],(str,bytes)):
        path=Path(str(args[0]));flags=args[2] if len(args)>2 else 0
        if path.name in ('.env','player_week.parquet','pricing_cohort.json','game_outcomes.parquet') or '/data/forward/' in str(path):
            raise RuntimeError('Tests prohibit credentials/outcomes/holdout')
        if str(path).startswith(str(REAL_RUNTIME)) and isinstance(flags,int) and flags&(os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC):
            raise RuntimeError('Tests may not write actual runtime')
    if event in ('os.rename','os.remove','os.mkdir','os.rmdir') and any(isinstance(a,(str,bytes)) and str(a).startswith(str(REAL_RUNTIME)) for a in args[:2]):
        raise RuntimeError('Tests may not mutate actual runtime')


sys.addaudithook(deny)


def offline_auth(cert):
    line=(f"APPROVED offline missing: proposal {cert['proposal_sha256']}, ledger {missing.STOPPED_SHA}, "
        f"request {missing.REQUEST}, response {missing.CACHE_SHA}, commit {'b'*40}")
    return {'status':'approved','proposal_sha256':cert['proposal_sha256'],'prior_ledger_sha256':missing.STOPPED_SHA,
        'request_id':missing.REQUEST,'response_sha256':missing.CACHE_SHA,'execution_commit':'b'*40,
        'hub_go_ahead':{'comment_url':'https://github.com/maxzipperman/value-finder/pull/99#issuecomment-1','comment_body':line}}


def paid_auth(root,m):
    body=(f"APPROVED paid run: list {m['request_list_sha256']}, request-set {m['request_set_sha256']}, "
        f"budget {m['new_credits']} credits, commit {'b'*40}\nAPPROVED account ceiling: max-baseline-used 200000, root {root}")
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
        self.adapters={'https':HTTPAdapter(max_retries=0)}
        self.used=93829;self.remaining=4906171;self.calls=[];self.mode=mode
    def get(self,url,params=None,**kwargs):
        assert kwargs['allow_redirects'] is False
        self.calls.append((url,params))
        if url.endswith('/sports'):return Response('[]',{'x-requests-last':'0','x-requests-used':str(self.used),'x-requests-remaining':str(self.remaining)})
        if self.mode=='timeout':
            import requests
            raise requests.Timeout('synthetic timeout')
        self.used+=20;self.remaining-=20
        headers={'x-requests-last':'20','x-requests-used':str(self.used),'x-requests-remaining':str(self.remaining)}
        at=plan.ts(params['date']);stamp=at-timedelta(minutes=5)
        body={'timestamp':plan.iso(stamp),'previous_timestamp':plan.iso(stamp-timedelta(minutes=5)),
            'next_timestamp':plan.iso(stamp+timedelta(minutes=5)),
            'data':{'id':url.split('/')[-2],'sport_key':plan.NFL,'bookmakers':[]}}
        if self.mode=='billing':headers.pop('x-requests-last')
        if self.mode=='overcharge':headers['x-requests-last']='21'
        if self.mode=='reset':headers.update({'x-requests-used':'0','x-requests-remaining':'5000000'})
        if self.mode=='lag':body['timestamp']=plan.iso(at-timedelta(hours=1))
        if self.mode=='external':headers['x-requests-used']=str(self.used+101)
        return Response(json.dumps(body),headers,int(self.mode) if self.mode in ('403','404','429') else 200)
    def close(self):pass


@pytest.fixture
def prepared(tmp_path,monkeypatch):
    base=epoch.source_executor(BUNDLE)
    monkeypatch.setattr(epoch,'ROOT_BASE',tmp_path/'state')
    monkeypatch.setattr(base,'RUNTIME_BASE',epoch.ROOT_BASE)
    monkeypatch.setattr(base,'checkout_commit',lambda _: 'b'*40)
    monkeypatch.setattr(epoch,'source_executor',lambda _:base)
    monkeypatch.setattr(epoch,'checkout_clean',lambda _:None)
    # Byte-copy original prior ledger; relocate only reviewed ancestor pointers.
    original_prior=REAL_RUNTIME/plan.SOURCE_ROOT/'spending-ledger.json'
    prior=epoch.ROOT_BASE/plan.SOURCE_ROOT/'spending-ledger.json'
    prior.parent.mkdir(parents=True);shutil.copyfile(original_prior,prior)
    monkeypatch.setattr(epoch,'SEED_HASH',plan.sha(prior))
    pilot=json.loads((REAL_RUNTIME/epoch.PILOT_ROOT/'spending-ledger.json').read_text())
    pilot['predecessor_seed']['ledger_path']=str(prior)
    pilot_path=epoch.ROOT_BASE/epoch.PILOT_ROOT/'spending-ledger.json';base.atomic(pilot_path,pilot)
    shutil.copytree(REAL_RUNTIME/epoch.PILOT_ROOT/'receipts',pilot_path.parent/'receipts')
    monkeypatch.setattr(epoch,'PILOT_LEDGER_SHA',plan.sha(pilot_path))
    spec=importlib.util.spec_from_file_location('immutable_test_pilot',HERE.parent/'followups/epoch.py')
    oldpilot=importlib.util.module_from_spec(spec);spec.loader.exec_module(oldpilot)
    spec=importlib.util.spec_from_file_location('immutable_test_coverage',HERE.parent/'followups/pilot_coverage.py')
    cov=importlib.util.module_from_spec(spec);spec.loader.exec_module(cov);cov.epoch=oldpilot
    cov_report=cov.report(HERE.parent/'followups/F2-pilot',epoch.PILOT_ROOT,BUNDLE,pilot_path)
    monkeypatch.setattr(epoch,'PILOT_COVERAGE_SHA',hashlib.sha256(plan.canonical(cov_report)+b'\n').hexdigest())
    original_helper=missing.original
    def original():
        old,m,rows=original_helper()
        old.ROOT_BASE=epoch.ROOT_BASE;old.SEED_HASH=epoch.SEED_HASH
        old.pilot_gate=epoch.pilot_gate
        return old,m,rows
    monkeypatch.setattr(missing,'original',original)
    stopped=json.loads((REAL_RUNTIME/missing.ORIGINAL_ROOT/'spending-ledger.json').read_text())
    stopped['predecessor_seed'].update(ledger_path=str(pilot_path),ledger_sha256=plan.sha(pilot_path))
    path=epoch.ROOT_BASE/missing.ORIGINAL_ROOT/'spending-ledger.json';base.atomic(path,stopped)
    monkeypatch.setattr(missing,'STOPPED_SHA',plan.sha(path))
    shutil.copytree(REAL_RUNTIME/missing.ORIGINAL_ROOT/'receipts',path.parent/'receipts')
    actual_cert=json.loads((HERE/'F2-continuation/missing-certificate.json').read_text())
    cache_from=Path(actual_cert['proposal']['response_path'])
    cache_to=path.parent/'data/raw'/cache_from.relative_to(REAL_RUNTIME/missing.ORIGINAL_ROOT/'data/raw')
    cache_to.parent.mkdir(parents=True);shutil.copyfile(cache_from,cache_to)
    cert,post,receipt,rows=missing.preview(BUNDLE)
    packet=tmp_path/'packet';shutil.copytree(HERE/'F2-continuation',packet)
    m=json.loads((packet/'manifest.json').read_text())
    for row in rows:
        attempt=post['attempts'].get(row['request_id'])
        if attempt:row.update(max_new_credits=0,cache_source=attempt['response_path'],cache_sha256=attempt['response_sha256'])
    m=plan.write_packet(packet,m,rows,json.loads((packet/'opportunities.json').read_text()))
    base.atomic(packet/'missing-certificate.json',cert)
    seed=json.loads((packet/'seed.json').read_text());seed.update(ledger_path=str(path),ledger_sha256=cert['post_ledger_sha256'])
    base.atomic(packet/'seed.json',seed)
    cache_info=json.loads((packet/'cache-reconciliation.json').read_text())
    cache_info['raw_roots'].append(str(path.parent/'data/raw'));cache_info['request_set_sha256']=m['request_set_sha256']
    base.atomic(packet/'cache-reconciliation.json',cache_info)
    root=epoch.freeze(packet)
    auth_path=tmp_path/'offline-approval.json';base.atomic(auth_path,offline_auth(cert))
    monkeypatch.setattr(epoch,'partial_certificate',lambda:cert)
    return packet,root,cert,post,receipt,path,auth_path,base,m


def apply(prepared,checkpoint=lambda _:None):
    packet,root,cert,post,receipt,path,auth_path,base,m=prepared
    return missing.transition(BUNDLE,packet/'missing-certificate.json',auth_path,fake_auth=True,checkpoint=checkpoint)


def test_actual_preview_exact_remaining_and_no_mutation():
    before=plan.sha(REAL_RUNTIME/missing.ORIGINAL_ROOT/'spending-ledger.json')
    cert,post,receipt,rows=missing.preview(BUNDLE)
    assert cert['proposal_sha256']=='8e8bb95f87b7b51e04eca912e1a30db44578f2746d33b5ccc3ad796a435aeb30'
    assert post['attempts'][missing.REQUEST]['reserved_credits']==20 and post['attempts'][missing.REQUEST]['billed_credits']==0
    assert len(post['attempts'])==418 and sum(r['max_new_credits']>0 and r['request_id'] not in post['attempts'] for r in rows)==1307
    assert plan.sha(REAL_RUNTIME/missing.ORIGINAL_ROOT/'spending-ledger.json')==before


def test_terminal_transition_preserves_every_attempt_and_debit(prepared):
    before=json.loads(prepared[5].read_text());result=apply(prepared);after=json.loads(prepared[5].read_text())
    assert result['reserved']==8360 and result['billed']==8340 and result['paid_calls']==0
    for rid,a in before['attempts'].items():
        if rid!=missing.REQUEST:assert after['attempts'][rid]==a
    for field in ('cache_reuse','epoch','other_usage_reserved','accounts','probe_credits','slice_cap'):
        assert after[field]==before[field]
    assert plan.sha(prepared[5])==prepared[2]['post_ledger_sha256']
    with pytest.raises(ValueError):apply(prepared) # terminal transition never resets/reapplies


@pytest.mark.parametrize('field',['status','proposal_sha256','prior_ledger_sha256','request_id','response_sha256','execution_commit'])
def test_offline_approval_exact_fields(prepared,field):
    auth=json.loads(prepared[6].read_text());auth[field]='wrong';prepared[7].atomic(prepared[6],auth)
    before=plan.sha(prepared[5])
    with pytest.raises(ValueError):apply(prepared)
    assert before==plan.sha(prepared[5])


def test_stop_before_offline_acceptance_blocks_key(prepared):
    packet,root,cert,post,receipt,path,auth_path,base,m=prepared;reads=[];session=Session()
    with pytest.raises(Exception):epoch.run(packet,root,BUNDLE,paid_auth(root,m),key=lambda:reads.append(1),fake_session=session)
    assert not reads and not session.calls and plan.sha(path)==missing.STOPPED_SHA


@pytest.mark.parametrize('point',['after_missing_receipt','after_missing_transition'])
def test_offline_transition_crash_never_sends_or_reduces_debit(prepared,point):
    def crash(at):
        if at==point:raise RuntimeError('synthetic offline crash')
    with pytest.raises(RuntimeError):apply(prepared,crash)
    state=json.loads(prepared[5].read_text())
    assert sum(a['reserved_credits'] for a in state['attempts'].values())==8360
    if point=='after_missing_receipt':
        assert state['pending']==missing.REQUEST
        assert (prepared[5].parent/'receipts'/f'{missing.REQUEST}.json').exists()
        apply(prepared) # explicit second offline acceptance, no paid path
    else:
        assert state['pending'] is None
        with pytest.raises(ValueError):apply(prepared)


def test_full_exact_continuation_no_ancestor_send(prepared):
    apply(prepared)
    packet,root,cert,post,receipt,path,auth_path,base,m=prepared
    session=Session();result=epoch.run(packet,root,BUNDLE,paid_auth(root,m),key='SYNTHETIC_KEY_ONLY',fake_session=session)
    assert len(session.calls)==1308 and result['new_reserved']==result['new_billed']==26140
    assert result['cumulative_reserved']==121676
    sent={(url,tuple(sorted({k:v for k,v in params.items() if k!='apiKey'}.items()))) for url,params in session.calls[1:]}
    _,_,oldrows=missing.original()
    for r in oldrows:
        if r['request_id'] in post['attempts'] or not r['max_new_credits']:
            assert (plan.BASE+r['path'],tuple(sorted(r['params'].items()))) not in sent
    state=json.loads((base.runtime_path(root)/'spending-ledger.json').read_text())
    assert len(state['cache_reuse'])==465 and len(state['accepted_missing_reuse'])==1


@pytest.mark.parametrize('mode',['timeout','billing','overcharge','reset','lag','external','403','404','429'])
def test_continuation_adverse_transport_stops_once(prepared,mode):
    apply(prepared)
    packet,root,cert,post,receipt,path,auth_path,base,m=prepared
    first=Session(mode)
    with pytest.raises(Exception):epoch.run(packet,root,BUNDLE,paid_auth(root,m),key='SYNTHETIC_KEY_ONLY',fake_session=first)
    assert len(first.calls)==2
    second=Session();reads=[]
    with pytest.raises(Exception):epoch.run(packet,root,BUNDLE,paid_auth(root,m),key=lambda:reads.append(1),fake_session=second)
    assert not reads and not second.calls
