"""Prospective F3a fake-transport integration against a complete synthetic five-root union."""
import copy
import json
from pathlib import Path
import sys
from datetime import datetime,timedelta,timezone
import pytest
HERE=Path(__file__).parent
sys.path.insert(0,str(HERE))
from test_union import snapshot,prepared,atomic,BUNDLE
import union,epoch,plan,f3a_missing as policy


class Response:
    def __init__(self,body,headers,status=200):self.text,self.headers,self.status_code=body,headers,status


class Session:
    def __init__(self,mode='ok'):
        from requests.adapters import HTTPAdapter
        self.adapters={'https':HTTPAdapter(max_retries=0)};self.used=119869;self.remaining=4880131;self.calls=[];self.mode=mode
    def get(self,url,params=None,**kwargs):
        assert kwargs['allow_redirects'] is False
        self.calls.append((url,params))
        if url.endswith('/sports'):return Response('[]',{'x-requests-last':'0','x-requests-used':str(self.used),'x-requests-remaining':str(self.remaining)})
        if self.mode=='timeout':
            import requests
            raise requests.Timeout('SYNTHETIC')
        absent=self.mode.startswith('missing')
        if not absent:self.used+=60;self.remaining-=60
        h={'x-requests-last':'0' if absent else '60','x-requests-used':str(self.used),'x-requests-remaining':str(self.remaining)}
        at=plan.ts(params['date']);stamp=at-timedelta(minutes=5)
        body={'timestamp':plan.iso(stamp),'previous_timestamp':plan.iso(stamp-timedelta(minutes=5)),
            'next_timestamp':plan.iso(stamp+timedelta(minutes=5)),'data':{'id':url.split('/')[-2],'sport_key':plan.NFL,'bookmakers':[]}}
        status=200
        if absent:body={'error_code':'EVENT_NOT_FOUND'};status=404
        if self.mode in ('billing','missing-counters'):h.pop('x-requests-last')
        if self.mode=='overcharge':h['x-requests-last']='61'
        if self.mode in ('reset','missing-reset'):h.update({'x-requests-used':'0','x-requests-remaining':'5000000'})
        if self.mode=='lag':body['timestamp']=plan.iso(at-timedelta(hours=1))
        if self.mode in ('external','missing-external'):h['x-requests-used']=str(self.used+101)
        if self.mode=='missing-code':body['error_code']='OTHER'
        if self.mode=='missing-billing':h['x-requests-last']='1'
        if self.mode=='missing-keyecho':body['message']=params['apiKey']
        if self.mode=='missing-floor':h['x-requests-remaining']='531629'
        if self.mode=='missing-lag':h['x-requests-used']=str(self.used-101)
        if self.mode in ('403','404','429'):status=int(self.mode)
        if self.mode=='identity':body['data']['id']='OTHER'
        return Response(json.dumps(body),h,status)
    def close(self):pass


def authorization(root,m,obj):
    commit='b'*40
    body=(f"APPROVED paid run: list {m['request_list_sha256']}, request-set {m['request_set_sha256']}, budget {m['new_credits']} credits, commit {commit}\n"
        f"APPROVED account ceiling: max-baseline-used 200000, root {root}\n"+policy.approval_line(obj,root))
    return {'status':'approved','bundle_root_sha256':root,'priority':1,'max_new_credits':m['new_credits'],
        'human_authorization_evidence':'SYNTHETIC ONLY','execution_commit':commit,
        'hub_go_ahead':{'status':'approved','bundle_root_sha256':root,'request_set_sha256':m['request_set_sha256'],'request_list_sha256':m['request_list_sha256'],
            'budget_credits':m['new_credits'],'commit':commit,'comment_url':'https://github.com/maxzipperman/value-finder/pull/99#issuecomment-1','comment_body':body},
        'account_reconciliation':{'status':'approved','bundle_root_sha256':root,'baseline_mode':'capture_first_free_check','reason':'SYNTHETIC','owner_note':'SYNTHETIC',
            'max_baseline_used':200000,'billing_period_utc':datetime.now(timezone.utc).strftime('%Y-%m')}}


@pytest.fixture
def driver(prepared,tmp_path,monkeypatch):
    import shutil
    target,pk,auth=prepared;cert,coverage=union.validate(auth)
    base=epoch.source_executor(BUNDLE);monkeypatch.setattr(base,'RUNTIME_BASE',target)
    monkeypatch.setattr(base,'checkout_commit',lambda _:'b'*40);monkeypatch.setattr(epoch,'source_executor',lambda _:base)
    monkeypatch.setattr(epoch,'checkout_clean',lambda _:None);monkeypatch.setattr(epoch,'union_certificate',lambda:cert)
    packet=tmp_path/'packet';shutil.copytree(HERE/'F3a',packet)
    m=json.loads((packet/'manifest.json').read_text());rows=json.loads((packet/'requests.json').read_text());ops=json.loads((packet/'opportunities.json').read_text())
    m['stage']='F3a-from-F2-union';m['f2_union_certificate_sha256']=union.digest(plan.canonical(cert));m=plan.write_packet(packet,m,rows,ops)
    seed={'root':union.CONTINUATION_ROOT,'ledger_path':str(target/union.CONTINUATION_ROOT/'spending-ledger.json'),
        'ledger_sha256':cert['continuation_ledger_sha256'],'probe_credits':1687,'cumulative_debit_without_probe':cert['cumulative_debit_without_probe']}
    for name,obj in [('seed.json',seed),('union-certificate.json',cert),('union-coverage.json',coverage),('continuation-authorization.json',auth),
        ('cache-reconciliation.json',{'status':'reconciled','raw_roots':epoch.known_raw_roots(),'request_set_sha256':m['request_set_sha256'],'reused':[],
            'paid_count':570,'new_credits':34200})]:atomic(packet/name,obj)
    root=epoch.freeze(packet);obj=policy.load(packet,m,rows)
    return packet,root,base,m,authorization(root,m,obj),cert


def run(d,session,checkpoint=lambda _:None,key='SYNTHETIC_F3A_KEY_ONLY'):
    return epoch.run(d[0],d[1],BUNDLE,d[4],key=key,fake_session=session,checkpoint=checkpoint)


@pytest.mark.parametrize('mode',['ok','missing'])
def test_full570_f3a_valid_or_missing_preserves_34200_and_union(driver,mode):
    session=Session(mode);result=run(driver,session)
    assert len(session.calls)==571 and result['new_reserved']==34200 and result['cumulative_reserved']==155876
    assert result['new_billed']==(34200 if mode=='ok' else 0)
    state=json.loads((driver[2].runtime_path(driver[1])/'spending-ledger.json').read_text())
    assert state['status']=='event_epoch_complete' and len(state['attempts'])==570
    if mode=='missing':
        assert all(a['status']=='missing' and a['reserved_credits']==60 and a['billed_credits']==0 for a in state['attempts'].values())
    rid=next(iter(state['attempts']));(driver[2].runtime_path(driver[1])/'receipts'/f'{rid}.json').unlink()
    reads=[];again=Session()
    with pytest.raises(Exception):run(driver,again,key=lambda:reads.append(1))
    assert not reads and not again.calls


@pytest.mark.parametrize('mode',['timeout','billing','overcharge','reset','lag','external','403','404','429','identity',
    'missing-code','missing-billing','missing-counters','missing-reset','missing-external','missing-keyecho','missing-floor','missing-lag'])
def test_f3a_adverse_halts_no_resend(driver,mode):
    first=Session(mode)
    with pytest.raises(Exception):run(driver,first)
    assert len(first.calls)==2
    again=Session();reads=[]
    with pytest.raises(Exception):run(driver,again,key=lambda:reads.append(1))
    assert not reads and not again.calls


@pytest.mark.parametrize('point',['after_reservation','after_send_started','after_cache_durability','after_receipt_durability','after_terminal_ledger'])
def test_f3a_durable_crash_no_resend(driver,point):
    first=Session('missing')
    def crash(at):
        if at==point:raise RuntimeError('SYNTHETIC crash')
    with pytest.raises(RuntimeError):run(driver,first,crash)
    state=json.loads((driver[2].runtime_path(driver[1])/'spending-ledger.json').read_text())
    assert sum(a['reserved_credits'] for a in state['attempts'].values())==60
    again=Session();reads=[]
    with pytest.raises(Exception):run(driver,again,key=lambda:reads.append(1))
    assert not reads and not again.calls


@pytest.mark.parametrize('fault',['candidate','union-hash','policy-line','ancestor-stop','new-store','overlap','global-stop'])
def test_f3a_prekey_guards(driver,fault):
    packet,root,base,m,auth,cert=driver
    if fault=='candidate':
        m['stage']='candidate';atomic(packet/'manifest.json',m);root=epoch.freeze(packet)
    if fault=='union-hash':
        c=json.loads((packet/'union-certificate.json').read_text());c['continuation_ledger_sha256']='0'*64;atomic(packet/'union-certificate.json',c);root=epoch.freeze(packet)
    if fault=='policy-line':auth['hub_go_ahead']['comment_body']='\n'.join(line for line in auth['hub_go_ahead']['comment_body'].splitlines() if not line.startswith('APPROVED F3a'))
    if fault=='ancestor-stop':
        path=epoch.ROOT_BASE/union.CONTINUATION_ROOT/'spending-ledger.json';st=json.loads(path.read_text());st['stopped']='SYNTHETIC';atomic(path,st)
    if fault=='new-store':(epoch.ROOT_BASE/('e'*64)/'data/raw').mkdir(parents=True)
    if fault=='overlap':
        row=json.loads((packet/'requests.json').read_text())[0]
        raw=epoch.ROOT_BASE/union.CONTINUATION_ROOT/'data/raw'/row['sport']/row['source']/'2025-01-01';raw.mkdir(parents=True,exist_ok=True)
        (raw/(row['cache_key']+'.parquet')).write_bytes(b'SYNTHETIC exact key')
    if fault=='global-stop':atomic(epoch.ROOT_BASE/('f'*64)/'spending-ledger.json',{'pending':'OTHER','stopped':'OTHER'})
    reads=[];session=Session()
    with pytest.raises(Exception):epoch.run(packet,root,BUNDLE,auth,key=lambda:reads.append(1),fake_session=session)
    assert not reads and not session.calls
