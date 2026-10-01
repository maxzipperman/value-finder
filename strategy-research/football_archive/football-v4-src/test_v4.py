"""Portable offline checks. All writes are to temporary copies; synthetic keys only."""
import copy
from datetime import datetime,timedelta,timezone
import hashlib
import json
from pathlib import Path
import socket
import sys

sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import pytest
import builder,validator,executor,price_eligibility as eligibility,coverage_report


def deny_network(event,args):
    if event in ('socket.connect','socket.getaddrinfo'):raise RuntimeError('Test network disabled')
    if event=='open' and isinstance(args[0],(str,bytes)):
        name=str(args[0])
        if Path(name).name=='.env' or '/data/forward/' in name:raise RuntimeError('Test credential/holdout read disabled')
sys.addaudithook(deny_network)


def policy(root,mode='explicit'):
    return {'status':'approved','bundle_root_sha256':root,'baseline_mode':mode,'used':1687,'remaining':4998313,
            'reason':'synthetic known baseline','owner_note':'SYNTHETIC TEST ONLY; no real permission','pre_run_other_usage_budget_debit':0,'max_baseline_used':1700,'billing_period_utc':datetime.now(timezone.utc).strftime('%Y-%m')}


@pytest.fixture(autouse=True)
def isolated_runtime(tmp_path,monkeypatch):
    monkeypatch.setattr(executor,'RUNTIME_BASE',tmp_path/'global-state')


def approved(root,manifest):
    commit='b'*40;cap=manifest['new_credits_by_priority']['1']
    body=(f"APPROVED paid run: list {manifest['request_list_sha256']}, request-set {manifest['request_set_sha256']}, "
          f"budget {cap} credits, commit {commit}")
    return {'status':'approved','bundle_root_sha256':root,'priority':1,'max_new_credits':cap,
            'human_authorization_evidence':'SYNTHETIC OWNER ONLY','execution_commit':commit,'account_reconciliation':policy(root),
            'hub_go_ahead':{'status':'approved','bundle_root_sha256':root,'request_set_sha256':manifest['request_set_sha256'],
                'request_list_sha256':manifest['request_list_sha256'],'budget_credits':cap,'commit':commit,
                'comment_url':'https://github.com/maxzipperman/value-finder/pull/99#issuecomment-1','comment_body':body}}


@pytest.fixture
def cfg():return json.loads((HERE/'protocol.json').read_text())


def quote_context(actual=None,kick='2023-10-01T17:00:00Z',returned='2023-10-01T16:50:00Z',requested='2023-10-01T16:55:00Z'):
    obs={'provider_id':'p','canonical_game_id':'g','provider_kickoff_utc':kick,'returned_utc':returned,
         'source_cache_key':'cache','source_body_sha256':'bodyhash','team_keys':['nfl:A','nfl:B']}
    oid=eligibility.observation_id(obs)
    q={'canonical_game_id':'g','provider_game_id':'p','book':'pinnacle','market':'totals','side':'Under','line':44.5,'decimal_price':1.91,
       'requested_utc':requested,'returned_utc':returned,'market_last_update':returned,'bookmaker_last_update':None,
       'provider_kickoff_utc':kick,'observation_id':oid,'source_body_sha256':'bodyhash','source_cache_key':'cache','request_id':'r'}
    qid=eligibility.identity(q);q['quote_id']=qid
    catalog={'games':{'g':{'provider_ids':['p'],'scheduled_utc':'2023-10-01T17:00:00Z','team_keys':['nfl:A','nfl:B']}},
             'observations':{oid:obs},'quotes':{qid:q},'actual_play':{},'close_request_ids':{'g':{'r'}}}
    if actual:catalog['actual_play']['g']={'canonical_game_id':'g','utc':actual,'source_id':'independent_first_play','independent':True}
    return {'quote_id':qid},catalog


def test_probe_and_budget_arithmetic():
    m=json.loads((HERE/'request-manifest.json').read_text());p=json.loads((HERE/'probe-spending-ledger.json').read_text())
    assert sum(a['counted_credits'] for a in p['attempts'])==1687
    assert m['request_count']==5052 and sum(r['max_new_credits']>0 for r in m['requests'])==5028
    assert m['new_credits_by_priority']=={'1':82830,'2':68010}
    assert m['new_credits_after_probe_reuse']+1687==152527
    summary=json.loads((HERE/'alternate-close-summary.json').read_text())
    assert summary['affected_games']==54 and summary['distinct_alternate_slots']==50
    assert summary['already_requested_distinct_alternate_slots']==22 and summary['affected_games_with_existing_alternate_slot']==25
    assert summary['new_slots']==28 and summary['additional_credits']==840


def test_joint_root_and_exact_invariants():
    cert=json.loads((HERE/'FREEZE.json').read_text());result=validator.verify(HERE,cert['bundle_root_sha256'],check_cache=True)
    assert result['execution_sources_bound'] and result['all_observed_opportunities_retained']
    with pytest.raises(ValueError,match='root'):validator.verify(HERE,'0'*64)


@pytest.mark.parametrize('field',['protocol.json','executor.py','archive_markets/http.py','request-manifest.json'])
def test_root_detects_modified_file(tmp_path,field):
    # Integrity check precedes metadata imports, so a minimal test certificate is enough.
    p=tmp_path/field;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('original')
    expected={field:executor.sha(p)};executor.atomic(tmp_path/'FREEZE.json',{'file_sha256':expected,'bundle_root_sha256':hashlib.sha256(validator.canonical(expected)).hexdigest()})
    p.write_text('changed')
    with pytest.raises(ValueError,match='bytes changed'):validator.verify(tmp_path)


def test_after_first_play_entry_rejected(cfg):
    row,cat=quote_context(actual='2023-10-01T16:52:00Z')
    g=eligibility.evaluate(cfg,row,cat)
    assert not g['eligible'] and not g['actual_play_certified']
    assert g['snapshot_pre_actual_play'] and 'decision_not_before_actual_play' in g['reasons']


@pytest.mark.parametrize('actual,expected',[('2023-10-01T16:55:00Z',False),('2023-10-01T16:55:01Z',True)])
def test_actual_play_boundary(cfg,actual,expected):
    row,cat=quote_context(actual=actual);assert eligibility.evaluate(cfg,row,cat)['eligible']==expected


def test_delayed_execution_crosses_play(cfg):
    row,cat=quote_context(actual='2023-10-01T16:57:00Z');row['execution_utc']='2023-10-01T16:58:00Z'
    g=eligibility.evaluate(cfg,row,cat);assert 'execution_not_before_actual_play' in g['reasons'] and not g['actual_play_certified']


def test_missing_actual_preserves_scheduled_proxy(cfg):
    row,cat=quote_context();g=eligibility.evaluate(cfg,row,cat,'close')
    assert g['eligible'] and g['status']=='scheduled_pregame_eligible' and not g['actual_play_certified']


def test_later_actual_start_cannot_admit_scheduled_late_decision(cfg):
    row,cat=quote_context(actual='2023-10-01T17:30:00Z',requested='2023-10-01T17:05:00Z',returned='2023-10-01T17:00:00Z')
    g=eligibility.evaluate(cfg,row,cat);assert not g['eligible'] and not g['actual_play_certified'] and not g['scheduled_pregame_eligible']
    assert 'not_in_scheduled_pregame_window' in g['reasons']


def test_conflict_without_actual_is_diagnostic(cfg):
    row,cat=quote_context(kick='2023-10-01T17:10:00Z');g=eligibility.evaluate(cfg,row,cat,'close')
    assert not g['eligible'] and 'unresolved_material_kickoff_conflict' in g['reasons']


@pytest.mark.parametrize('field,value',[('provider_kickoff_utc','2023-10-02T17:00:00Z'),('provider_game_id','invented'),('side','NoSuchSide'),('canonical_game_id','other')])
def test_caller_cannot_replace_bound_fields(cfg,field,value):
    row,cat=quote_context();row[field]=value
    assert eligibility.evaluate(cfg,row,cat)['reasons']==['quote_source_field_mismatch']


@pytest.mark.parametrize('side',['NoSuchSide','home','away'])
def test_source_market_side_validated(cfg,side):
    row,cat=quote_context();cat['quotes'][row['quote_id']]['side']=side
    assert 'invalid_market_side_or_event_teams' in eligibility.evaluate(cfg,row,cat)['reasons']


def test_unbound_quote_and_schedule(cfg):
    row,cat=quote_context();assert not eligibility.evaluate(cfg,{'quote_id':'invented'},cat)['eligible']
    cat['observations'].clear();assert 'unbound_schedule_observation' in eligibility.evaluate(cfg,row,cat)['reasons']


def test_simultaneous_conflicting_exact_listing_quarantined(cfg):
    row,cat=quote_context();old=next(iter(cat['observations'].values()));other=dict(old,provider_kickoff_utc='2023-10-01T23:00:00Z')
    cat['observations'][eligibility.observation_id(other)]=other
    assert 'conflicting_asof_exact_listing' in eligibility.evaluate(cfg,row,cat)['reasons']


def test_other_provider_id_does_not_choose_quoted_listing(cfg):
    row,cat=quote_context();old=next(iter(cat['observations'].values()));other=dict(old,provider_id='alphabetically_later',provider_kickoff_utc='2023-10-01T23:00:00Z')
    cat['observations'][eligibility.observation_id(other)]=other
    assert eligibility.evaluate(cfg,row,cat)['eligible']


def test_future_schedule_observation_ignored(cfg):
    row,cat=quote_context();old=next(iter(cat['observations'].values()));other=dict(old,returned_utc='2023-10-01T16:56:00Z',provider_kickoff_utc='2023-10-02T17:00:00Z')
    cat['observations'][eligibility.observation_id(other)]=other
    assert eligibility.evaluate(cfg,row,cat)['eligible']


@pytest.mark.parametrize('age,reason',[(901,'quote_stale_at_snapshot'),(-1,'future_quote_timestamp')])
def test_quote_age_origins(cfg,age,reason):
    row,cat=quote_context();q=cat['quotes'][row['quote_id']]
    q['market_last_update']=(eligibility.timestamp(q['returned_utc'])-timedelta(seconds=age)).isoformat()
    assert reason in eligibility.evaluate(cfg,row,cat)['reasons']


def test_snapshot_gap_reported_without_loosening(cfg):
    row,cat=quote_context(returned='2023-10-01T16:49:00Z')
    g=eligibility.evaluate(cfg,row,cat,'close');assert g['eligible'] and g['metrics']['provider_gap_over_five_minutes']


def test_missing_quote_time_not_imputed(cfg):
    row,cat=quote_context();cat['quotes'][row['quote_id']]['market_last_update']=None
    assert 'missing_quote_timestamp' in eligibility.evaluate(cfg,row,cat)['reasons']


def test_neutral_swapped_side_joins_team(cfg):
    row,cat=quote_context();q=cat['quotes'][row['quote_id']];q['market']='spreads';q['side']='nfl:A'
    obs=next(iter(cat['observations'].values()));obs['team_keys'].reverse();newid=eligibility.observation_id(obs)
    cat['observations']={newid:obs};q['observation_id']=newid
    assert eligibility.evaluate(cfg,row,cat)['eligible']


def test_paper_void_retained(cfg):
    row,cat=quote_context(actual='2023-10-02T17:00:01Z')
    g=eligibility.evaluate(cfg,row,cat);assert g['paper_listing_status']=='postponed_over_24h_void' and g['eligible']


def test_close_ranking_does_not_follow_prices(cfg):
    row1,cat1=quote_context(returned='2023-10-01T16:45:00Z',requested='2023-10-01T16:50:00Z')
    row2,cat2=quote_context();cat=copy.deepcopy(cat1);cat['quotes'].update(cat2['quotes']);cat['observations'].update(cat2['observations'])
    old=cat['quotes'][row1['quote_id']];new=cat['quotes'][row2['quote_id']]
    old['decimal_price']=10.0;old['line']=99.0;new['decimal_price']=1.01;new['line']=1.0
    assert eligibility.select_close(cfg,[row1,row2],cat)['primary']['row']==row2
    old['decimal_price']=1.01;new['decimal_price']=10.0
    assert eligibility.select_close(cfg,[row2,row1],cat)['primary']['row']==row2


def test_missing_close_not_substituted(cfg):
    row,cat=quote_context(kick='2023-10-01T18:00:00Z')
    result=eligibility.select_close(cfg,[row],cat);assert result['primary'] is None and len(result['diagnostics'])==1
    assert not eligibility.primary_reference_pair({'book':'draftkings'},{'book':'draftkings'})


def test_grid_midnight_and_dst():
    assert builder.close_time('2023-10-02T00:03:30Z')=='2023-10-01T23:55:00Z'
    m=json.loads((HERE/'request-manifest.json').read_text());slots=[r for r in m['requests'] if 'MOS_original_evening_slot_diagnostic' in r['purposes']]
    assert sum(r['requested_utc'][11:16]=='02:30' for r in slots)==341
    assert sum(r['requested_utc'][11:16]=='03:30' for r in slots)==324


def ledger_inputs(cfg):
    m=json.loads((HERE/'request-manifest.json').read_text());probe=json.loads((HERE/'probe-spending-ledger.json').read_text())
    root='a'*64;auth=approved(root,m)
    return m,probe,root,auth


def test_lock_and_durable_reservation(cfg,tmp_path):
    m,p,r,a=ledger_inputs(cfg);l=executor.Ledger(tmp_path,cfg,m,r,a,p)
    try:
        with pytest.raises(BlockingIOError):executor.Ledger(tmp_path,cfg,m,r,a,p)
        row=next(r for r in m['requests'] if r['priority']==1 and r['max_new_credits'])
        l.reserve(row);disk=json.loads(l.path.read_text());assert disk['pending']==row['request_id'] and disk['attempts'][row['request_id']]['reserved_credits']==30
    finally:l.close()
    with pytest.raises(executor.Halt,match='Pending'):executor.Ledger(tmp_path,cfg,m,r,a,p)


def test_older_and_modified_allowlist_rejected(cfg,tmp_path):
    m,p,r,a=ledger_inputs(cfg);l=executor.Ledger(tmp_path,cfg,m,r,a,p)
    try:
        older=next(row for row in m['requests'] if row['priority']==2 and row['max_new_credits'])
        with pytest.raises(executor.Halt,match='allowlist'):l.reserve(older)
        row=copy.deepcopy(next(row for row in m['requests'] if row['priority']==1 and row['max_new_credits']));row['params']['markets']='totals'
        with pytest.raises(executor.Halt,match='allowlist'):l.reserve(row)
    finally:l.close()


@pytest.mark.parametrize('field,value',[('first_tranche_cumulative_credits',1716),('day_one_cumulative_ceiling',1716),('broader_cumulative_ceiling',1716)])
def test_all_cumulative_caps_enforced(cfg,tmp_path,field,value):
    m,p,r,a=ledger_inputs(cfg);cfg['budgets'][field]=value;l=executor.Ledger(tmp_path,cfg,m,r,a,p)
    try:
        row=next(x for x in m['requests'] if x['priority']==1 and x['max_new_credits'])
        with pytest.raises(executor.Halt,match='Cumulative'):l.reserve(row)
    finally:l.close()


def test_reserve_floor(cfg,tmp_path):
    m,p,r,a=ledger_inputs(cfg);l=executor.Ledger(tmp_path,cfg,m,r,a,p)
    try:
        l.state['provider_remaining']=cfg['budgets']['account_reserve_floor']+29
        l.state['epoch']['remaining_lowwater']=l.state['provider_remaining']
        row=next(x for x in m['requests'] if x['priority']==1 and x['max_new_credits'])
        with pytest.raises(executor.Halt,match='reserve'):l.reserve(row)
    finally:l.close()


@pytest.mark.parametrize('used,left',[(0,5000000),(1800,4998200),(1687,None)])
def test_monthly_reset_external_usage_and_unreadable_balance_halt(cfg,tmp_path,used,left):
    m,p,r,a=ledger_inputs(cfg);l=executor.Ledger(tmp_path,cfg,m,r,a,p)
    try:
        with pytest.raises(executor.Halt):l.account(used,left)
        assert l.state['probe_credits']==1687
    finally:l.close()


def test_deleted_ledger_does_not_reset(cfg,tmp_path):
    m,p,r,a=ledger_inputs(cfg);l=executor.Ledger(tmp_path,cfg,m,r,a,p);l.close();(tmp_path/'spending-ledger.json').unlink()
    with pytest.raises(executor.Halt,match='missing'):executor.Ledger(tmp_path,cfg,m,r,a,p)


class FakeResponse:
    def __init__(self,body,headers,status=200):self.text=body;self.headers=headers;self.status_code=status


class FakeSession:
    def __init__(self,body,mode='ok'):
        from requests.adapters import HTTPAdapter
        self.adapters={'https':HTTPAdapter(max_retries=0)};self.body=body;self.mode=mode;self.calls=[];self.used=1687;self.remaining=4998313
    def get(self,url,params=None,**kwargs):
        assert kwargs['allow_redirects'] is False
        self.calls.append(url)
        if url.endswith('/sports'):return FakeResponse('[]',{'x-requests-last':'0','x-requests-used':str(self.used),'x-requests-remaining':str(self.remaining)})
        if self.mode=='timeout':
            import requests
            raise requests.Timeout('synthetic timeout; no real key')
        self.used+=30;self.remaining-=30
        headers={'x-requests-last':'30','x-requests-used':str(self.used),'x-requests-remaining':str(self.remaining)}
        if self.mode=='overcharge':headers['x-requests-last']='31';headers['x-requests-used']=str(self.used+1);headers['x-requests-remaining']=str(self.remaining-1)
        if self.mode=='reset':headers['x-requests-used']='30';headers['x-requests-remaining']='4999970'
        if self.mode=='bad_billing':headers.pop('x-requests-last')
        if self.mode in ('other_usage','other_usage_excess'):headers['x-requests-used']=str(self.used+(101 if self.mode=='other_usage_excess' else 1));headers['x-requests-remaining']=str(self.remaining-(101 if self.mode=='other_usage_excess' else 1))
        body=self.body
        if self.mode=='echo':body=body.replace('"data":', '"echo":"SYNTHETIC_KEY_ONLY", "data":')
        if self.mode=='future':
            d=json.loads(body);d['timestamp']='2099-01-01T00:00:00Z';body=json.dumps(d)
        if self.mode=='lag':
            d=json.loads(body);d['timestamp']=builder.iso(builder.ts(d['timestamp'])-timedelta(minutes=20));body=json.dumps(d)
        return FakeResponse(body,headers,500 if self.mode=='http500' else 404 if self.mode=='http404' else 200)
    def close(self):pass


@pytest.fixture
def tiny_bundle(cfg,tmp_path,monkeypatch):
    import shutil
    b=tmp_path/'bundle';b.mkdir();shutil.copytree(HERE/'archive_markets',b/'archive_markets')
    m=json.loads((HERE/'request-manifest.json').read_text());r=copy.deepcopy(next(r for r in m['requests'] if r['priority']==1 and r['max_new_credits']))
    r['canonical_game_ids']=['g'];m.update(requests=[r],new_credits_by_priority={'1':30,'2':0},new_credits_after_probe_reuse=30,request_count=1)
    for name,v in [('protocol.json',cfg),('request-manifest.json',m),('probe-spending-ledger.json',json.loads((HERE/'probe-spending-ledger.json').read_text())),
       ('runtime-lock.json',executor.current_runtime()),('FREEZE.json',{'file_sha256':{}}),('provider-observations.json',[]),
       ('canonical-games.json',[{'canonical_game_id':'g','provider_ids':['p'],'sport':r['sport'],'season':2023,'scheduled_utc':builder.iso(builder.ts(r['requested_utc'])+timedelta(minutes=10)),
                               'team_keys':['nfl:A','nfl:B'],'first_observed_lead_hours':72}]),
       ('aliases.json',[{'sport':r['sport'],'provider_name':n,'canonical_team_key':k} for n,k in [('Team A','nfl:A'),('Team B','nfl:B')]]),
       ('close-candidates.json',[{'canonical_game_id':'g','request_id':r['request_id']}]),('alternate-close-summary.json',{'affected_games':1,'distinct_alternate_slots':1}),('opportunity-registry.json',[])]:executor.atomic(b/name,v)
    # Isolate dynamic wrapper tests from full-bundle static validation, which is tested independently.
    monkeypatch.setattr(validator,'verify',lambda *a,**k:{'test_fixture':True})
    at=builder.ts(r['requested_utc']);snap=at-timedelta(minutes=5)
    body=json.dumps({'timestamp':builder.iso(snap),'previous_timestamp':builder.iso(snap-timedelta(minutes=5)),'next_timestamp':builder.iso(snap+timedelta(minutes=5)),
        'data':[{'id':'p','commence_time':builder.iso(at+timedelta(minutes=10)),'home_team':'Team A','away_team':'Team B',
                 'bookmakers':[{'key':'pinnacle','last_update':builder.iso(snap),'markets':[{'key':'totals','last_update':builder.iso(snap),
                            'outcomes':[{'name':'Under','point':44.5,'price':1.91}]}]}]}]})
    root='a'*64;auth=approved(root,m)
    monkeypatch.setattr(executor,'checkout_commit',lambda _:auth['execution_commit'])
    return b,root,auth,executor.runtime_path(root),body


def test_wrapper_completion_and_resume(tiny_bundle):
    b,r,a,run,body=tiny_bundle;fake=FakeSession(body)
    result=executor.run(b,r,a,run,key='SYNTHETIC_KEY_ONLY',fake_session=fake)
    assert result['reserved_new_credits']==30 and result['counted_probe_and_new']==1717 and len(fake.calls)==2
    resumed=FakeSession(body);resumed.used=1717;resumed.remaining=4998283
    result=executor.run(b,r,a,run,key='SYNTHETIC_KEY_ONLY',fake_session=resumed)
    assert len(resumed.calls)==1 and result['reserved_new_credits']==30
    report=json.loads((run/'coverage-report.json').read_text());assert report['outcomes_joined'] is False and report['all_recent_requests_completed']


@pytest.mark.parametrize('point',['after_reservation','after_transport','after_response_durability','after_receipt_durability'])
def test_power_loss_never_automatically_resends(tiny_bundle,point):
    b,r,a,run,body=tiny_bundle;fake=FakeSession(body)
    class PowerLoss(BaseException):pass
    def checkpoint(here):
        if point==here:raise PowerLoss()
    with pytest.raises(PowerLoss):executor.run(b,r,a,run,key='SYNTHETIC_KEY_ONLY',fake_session=fake,checkpoint=checkpoint)
    second=FakeSession(body)
    with pytest.raises(executor.Halt,match='Pending'):executor.run(b,r,a,run,key='SYNTHETIC_KEY_ONLY',fake_session=second)
    assert not second.calls
    ledger=json.loads((run/'spending-ledger.json').read_text());assert sum(x['reserved_credits'] for x in ledger['attempts'].values())==30


@pytest.mark.parametrize('mode',['timeout','http500','bad_billing','other_usage_excess','echo','future','overcharge','reset'])
def test_transport_failure_halts_without_retry(tiny_bundle,mode):
    b,r,a,run,body=tiny_bundle;fake=FakeSession(body,mode)
    with pytest.raises(executor.Halt):executor.run(b,r,a,run,key='SYNTHETIC_KEY_ONLY',fake_session=fake)
    assert len(fake.calls)==2  # One free check, one attempted paid request; never retry.
    ledger=json.loads((run/'spending-ledger.json').read_text());assert ledger['pending'] and ledger['stopped']
    assert all('SYNTHETIC_KEY_ONLY' not in p.read_text(errors='ignore') for p in run.rglob('*') if p.is_file() and p.suffix in ('.json','.csv'))


def test_guard_blocks_unreserved_and_outside_allowlist(cfg,tmp_path):
    m,p,r,a=ledger_inputs(cfg);l=executor.Ledger(tmp_path,cfg,m,r,a,p);fake=FakeSession('{}');guard=executor.GuardedSession(fake,l,m['requests'])
    try:
        with pytest.raises(executor.Halt):guard.get('https://api.the-odds-api.com/v4/historical/sports/americanfootball_nfl/odds',params={})
        assert not fake.calls
    finally:l.close()


def test_guard_prohibits_adapter_retry(cfg,tmp_path):
    from requests.adapters import HTTPAdapter
    m,p,r,a=ledger_inputs(cfg);l=executor.Ledger(tmp_path,cfg,m,r,a,p);fake=FakeSession('{}');fake.adapters['https']=HTTPAdapter(max_retries=1)
    try:
        with pytest.raises(executor.Halt,match='retries'):executor.GuardedSession(fake,l,m['requests'])
    finally:l.close()


def test_all_24_probe_bodies_offline_replayed(cfg,tmp_path):
    from archive_markets.cache import read_record
    m=json.loads((HERE/'request-manifest.json').read_text());rows=[r for r in m['requests'] if r['max_new_credits']==0]
    cat=coverage_report.make_catalog(HERE);aliases={(a['sport'],a['provider_name']):a['canonical_team_key'] for a in json.loads((HERE/'aliases.json').read_text())}
    for row in rows:
        record=read_record(HERE/row['cache_source']);executor.validate_response(row,record,cfg)
        events,ids=coverage_report.normalize_response(cat,row,record,aliases)
        assert events and ids
        for qid in ids:eligibility.evaluate(cfg,{'quote_id':qid},cat)
    assert len(rows)==24


def test_arbitrary_daily_quote_cannot_become_close(cfg):
    row,cat=quote_context();cat['close_request_ids']={'g':{'different_request'}}
    assert 'not_a_frozen_close_candidate' in eligibility.evaluate(cfg,row,cat,'close')['reasons']


def test_runtime_lock_blocks_before_key_read(tiny_bundle):
    b,r,a,run,body=tiny_bundle
    executor.atomic(b/'runtime-lock.json',{'python':'different','distributions':{}})
    reads=[];fake=FakeSession(body)
    with pytest.raises(executor.Halt,match='runtime'):
        executor.run(b,r,a,run,key=lambda:reads.append(True),fake_session=fake)
    assert not reads and not fake.calls


def test_wrong_root_blocks_before_key_read(tmp_path):
    reads=[];fake=FakeSession('{}')
    with pytest.raises(ValueError,match='root'):
        executor.run(HERE,'0'*64,{},executor.runtime_path('0'*64),key=lambda:reads.append(True),fake_session=fake)
    assert not reads and not fake.calls


def test_receipt_or_cache_change_never_rebuys(tiny_bundle):
    b,r,a,run,body=tiny_bundle;fake=FakeSession(body)
    executor.run(b,r,a,run,key='SYNTHETIC_KEY_ONLY',fake_session=fake)
    ledger=json.loads((run/'spending-ledger.json').read_text());receipt=next((run/'receipts').glob('*.json'));receipt.write_text('{}')
    resumed=FakeSession(body);resumed.used=1717;resumed.remaining=4998283
    with pytest.raises(executor.Halt,match='evidence'):
        executor.run(b,r,a,run,key='SYNTHETIC_KEY_ONLY',fake_session=resumed)
    assert len(resumed.calls)==1  # At most free account check, no paid repurchase.


def test_completion_crash_resumes_without_paid_send(tiny_bundle):
    b,r,a,run,body=tiny_bundle;fake=FakeSession(body)
    class PowerLoss(BaseException):pass
    def checkpoint(here):
        if here=='after_completion':raise PowerLoss()
    with pytest.raises(PowerLoss):executor.run(b,r,a,run,key='SYNTHETIC_KEY_ONLY',fake_session=fake,checkpoint=checkpoint)
    resumed=FakeSession(body);resumed.used=1717;resumed.remaining=4998283
    executor.run(b,r,a,run,key='SYNTHETIC_KEY_ONLY',fake_session=resumed)
    assert len(resumed.calls)==1


def test_independent_actual_evidence_must_bind_game(cfg):
    row,cat=quote_context(actual='2023-10-01T17:00:00Z');cat['actual_play']['g']['canonical_game_id']='another_game'
    assert 'unbound_actual_play_evidence' in eligibility.evaluate(cfg,row,cat)['reasons']


def test_intended_missing_instruments_survive_coverage(tiny_bundle):
    b,r,a,run,body=tiny_bundle;executor.run(b,r,a,run,key='SYNTHETIC_KEY_ONLY',fake_session=FakeSession(body))
    report=json.loads((run/'coverage-report.json').read_text())
    assert len(report['intended_slot_book_market_accounting'])==30
    assert sum(x['status']=='missing_quote' for x in report['intended_slot_book_market_accounting'])==29
    assert report['intended_decision_pair_accounting']
    assert any(x['pair_status']=='missing_or_ineligible_entry' for x in report['intended_decision_pair_accounting'])


@pytest.mark.parametrize('probe_index',range(24))
def test_each_cached_probe_body_through_spending_wrapper(tiny_bundle,probe_index):
    """Replay actual sanitized bodies with synthetic current billing; never a live request."""
    from archive_markets.cache import read_record
    b,root,auth,runtime,_=tiny_bundle
    full=json.loads((HERE/'request-manifest.json').read_text())
    probe=copy.deepcopy([r for r in full['requests'] if r['max_new_credits']==0][probe_index])
    record=read_record(HERE/probe['cache_source'])
    probe.update(priority=1,max_new_credits=30,cache_source=None,cache_sha256=None,canonical_game_ids=['g'])
    small=json.loads((b/'request-manifest.json').read_text());small['requests']=[probe];executor.atomic(b/'request-manifest.json',small)
    executor.atomic(b/'close-candidates.json',[{'canonical_game_id':'g','request_id':probe['request_id']}])
    # Static all-season restrictions are tested on the full bundle; this fixture isolates transport/accounting.
    fake=FakeSession(record['body'])
    result=executor.run(b,root,auth,runtime,key='SYNTHETIC_KEY_ONLY',fake_session=fake)
    assert len(fake.calls)==2 and result['reserved_new_credits']==30
    state=json.loads((runtime/'spending-ledger.json').read_text())
    assert state['status']=='recent_complete_stopped_before_older' and state['pending'] is None


def test_fresh_reset_baseline_adopted_without_local_budget_reset(cfg,tmp_path):
    m,p,r,a=ledger_inputs(cfg);rec=policy(r,'capture_first_free_check');rec.pop('pre_run_other_usage_budget_debit')
    l=executor.Ledger(tmp_path,cfg,m,r,a,p,reconciliation=rec)
    try:
        assert l.state['epoch'] is None
        l.account(0,5000000)
        assert l.state['probe_credits']==1687 and l.state['epoch']['start_used']==0
    finally:l.close()


def test_pre_run_usage_is_reserved_conservatively(cfg,tmp_path):
    m,p,r,a=ledger_inputs(cfg);rec=policy(r,'capture_first_free_check');rec.pop('pre_run_other_usage_budget_debit')
    l=executor.Ledger(tmp_path,cfg,m,r,a,p,reconciliation=rec)
    try:
        l.account(1700,4998300)
        assert l.state['other_usage_reserved']==1700 and l.state['probe_credits']==1687
    finally:l.close()


def test_bounded_shared_usage_completes_and_manifest_records_evidence(tiny_bundle):
    b,r,a,run,body=tiny_bundle;fake=FakeSession(body,'other_usage')
    result=executor.run(b,r,a,run,key='SYNTHETIC_KEY_ONLY',fake_session=fake)
    state=json.loads((run/'spending-ledger.json').read_text());assert state['other_usage_reserved']==1 and state['pending'] is None
    manifest=json.loads((run/'run-manifest.json').read_text())
    assert manifest['reconciliation_sha256'] and manifest['interpreter_path']==sys.executable


def test_counter_lag_and_catchup_not_double_counted(cfg,tmp_path):
    m,p,r,a=ledger_inputs(cfg);l=executor.Ledger(tmp_path,cfg,m,r,a,p)
    try:
        l.measure_counters(1687,4998313,30)  # One own bill hidden in stale headers.
        assert l.state['other_usage_reserved']==0
        l.measure_counters(1722,4998278,30)  # Catch-up + five external credits.
        assert l.state['other_usage_reserved']==5
        l.measure_counters(1752,4998248,60)  # Same external five, next own bill.
        assert l.state['other_usage_reserved']==5
        with pytest.raises(executor.Halt,match='lag'):l.measure_counters(1752,4998248,180)
    finally:l.close()


def test_explicit_account_only_recovery_preserves_attempt_budget(cfg,tmp_path):
    m,p,r,a=ledger_inputs(cfg);l=executor.Ledger(tmp_path,cfg,m,r,a,p);l.halt('synthetic account reset');l.close()
    rec=policy(r,'capture_first_free_check');rec['account_only_recovery']=True;rec['owner_note']='SYNTHETIC APPROVED RECOVERY';rec['prior_ledger_sha256']=executor.sha(tmp_path/'spending-ledger.json')
    l=executor.Ledger(tmp_path,cfg,m,r,a,p,reconciliation=rec)
    try:
        l.account(0,5000000);assert l.state['probe_credits']==1687 and l.state['stopped'] is None
    finally:l.close()


def test_pending_cannot_be_cleared_by_account_only_recovery(cfg,tmp_path):
    m,p,r,a=ledger_inputs(cfg);l=executor.Ledger(tmp_path,cfg,m,r,a,p)
    row=next(x for x in m['requests'] if x['priority']==1 and x['max_new_credits']);l.reserve(row);l.close()
    rec=policy(r,'capture_first_free_check');rec['account_only_recovery']=True
    with pytest.raises(executor.Halt,match='Pending'):executor.Ledger(tmp_path,cfg,m,r,a,p,reconciliation=rec)


def test_draft_authorization_and_reconciliation_block_before_key(tiny_bundle):
    b,r,a,run,body=tiny_bundle;a['status']='draft';reads=[];fake=FakeSession(body)
    with pytest.raises(executor.Halt,match='authorization'):executor.run(b,r,a,run,key=lambda:reads.append(True),fake_session=fake)
    assert not reads and not fake.calls


def test_offline_saved_response_reconciliation_never_sends(tiny_bundle):
    b,r,a,run,body=tiny_bundle;fake=FakeSession(body)
    class Crash(BaseException):pass
    def checkpoint(point):
        if point=='after_response_durability':raise Crash()
    with pytest.raises(Crash):executor.run(b,r,a,run,key='SYNTHETIC_KEY_ONLY',fake_session=fake,checkpoint=checkpoint)
    state=json.loads((run/'spending-ledger.json').read_text());rid=state['pending'];cached=next((run/'data/raw').glob('*/*/*/*/*.parquet'))
    rec=policy(r,'capture_first_free_check');rec['pending_response_resolution']={'request_id':rid,'response_sha256':executor.sha(cached),'owner_note':'SYNTHETIC inspected cached response'}
    result=executor.reconcile_cached_response(b,r,a,rec,run)
    state=json.loads((run/'spending-ledger.json').read_text());assert state['pending'] is None and state['attempts'][rid]['reserved_credits']==30
    assert result['new_API_calls']==0 and len(fake.calls)==2


@pytest.mark.parametrize('change',['missing','wrong_root','wrong_list','draft'])
def test_hub_exact_list_required_before_key(tiny_bundle,change):
    b,r,a,run,body=tiny_bundle
    if change=='missing':a.pop('hub_go_ahead')
    elif change=='wrong_root':a['hub_go_ahead']['bundle_root_sha256']='0'*64
    elif change=='wrong_list':a['hub_go_ahead']['request_set_sha256']='0'*64
    else:a['hub_go_ahead']['status']='draft'
    reads=[];fake=FakeSession(body)
    with pytest.raises(executor.Halt,match='Hub go-ahead'):
        executor.run(b,r,a,run,key=lambda:reads.append(True),fake_session=fake)
    assert not reads and not fake.calls


@pytest.mark.parametrize('used_delta,remaining_delta,own',[(130,130,30),(30,130,30),(130,30,30),(0,0,100)])
def test_counter_margin_boundaries(cfg,tmp_path,used_delta,remaining_delta,own):
    m,p,r,a=ledger_inputs(cfg);l=executor.Ledger(tmp_path,cfg,m,r,a,p)
    try:
        l.measure_counters(1687+used_delta,4998313-remaining_delta,own)
        assert l.state['other_usage_reserved']==max(0,used_delta-own,remaining_delta-own)
        with pytest.raises(executor.Halt):
            if own==100:l.measure_counters(1687,4998313,101)
            else:l.measure_counters(1687+used_delta+101,4998313-remaining_delta-101,own)
    finally:l.close()


def test_exact_manifest_cache_handoff(tiny_bundle):
    import cache_handoff
    from archive_markets.oddsapi.bulk import Call, BulkClient, cached_bodies
    b,r,a,run,body=tiny_bundle;fake=FakeSession(body)
    executor.run(b,r,a,run,key='SYNTHETIC_KEY_ONLY',fake_session=fake)
    handoff=cache_handoff.build_handoff(b,r,run)
    calls=cache_handoff.as_calls(handoff,Call);cache=cache_handoff.ReadOnlyCache(handoff,run/'data/raw')
    client=BulkClient(cache,max_credits=0,session=fake,api_key='SYNTHETIC_KEY_ONLY')
    try:
        records=list(cached_bodies(client,calls))
        assert len(records)==1 and records[0][2]==json.loads(body) and len(fake.calls)==2
        with pytest.raises(RuntimeError,match='Read-only'):cache.get_or_fetch()
    finally:client.session.close()


@pytest.mark.parametrize('change',['incomplete','outcomes_joined','response_changed'])
def test_cache_handoff_refuses_unverified_inputs(tiny_bundle,change):
    import cache_handoff
    b,r,a,run,body=tiny_bundle
    executor.run(b,r,a,run,key='SYNTHETIC_KEY_ONLY',fake_session=FakeSession(body))
    if change=='incomplete':
        p=run/'spending-ledger.json';v=json.loads(p.read_text());v['status']='running';executor.atomic(p,v)
    elif change=='outcomes_joined':
        p=run/'coverage-report.json';v=json.loads(p.read_text());v['outcomes_joined']=True;executor.atomic(p,v)
    else:
        p=next((run/'data/raw').rglob('*.parquet'));p.write_bytes(p.read_bytes()+b'changed')
    with pytest.raises(ValueError):cache_handoff.build_handoff(b,r,run)


def test_recovery_replaces_stale_floor_before_budget_check(cfg,tmp_path):
    m,p,r,a=ledger_inputs(cfg);rec=policy(r);floor=cfg['budgets']['account_reserve_floor']
    rec['remaining']=floor+50
    l=executor.Ledger(tmp_path,cfg,m,r,a,p,reconciliation=rec)
    try:
        with pytest.raises(executor.Halt):l.account(1747,floor-10)
        l.halt('synthetic reserve floor stop');old=l.state['other_usage_reserved']
    finally:l.close()
    recovery=policy(r);recovery.update(used=0,remaining=5000000,account_only_recovery=True,prior_ledger_sha256=executor.sha(tmp_path/'spending-ledger.json'))
    l=executor.Ledger(tmp_path,cfg,m,r,a,p,reconciliation=recovery)
    try:
        assert l.state['provider_remaining']==5000000 and l.state['other_usage_reserved']==old and l.state['probe_credits']==1687
        l.budget_check(30)
    finally:l.close()


def test_fresh_checkout_shares_ledger_without_rebuy(tiny_bundle,tmp_path):
    import shutil
    b,r,a,run,body=tiny_bundle
    executor.run(b,r,a,run,key='SYNTHETIC_KEY_ONLY',fake_session=FakeSession(body))
    second=tmp_path/'fresh-checkout';shutil.copytree(b,second)
    f2=FakeSession(body);f2.used=1717;f2.remaining=4998283
    executor.run(second,r,a,run,key='SYNTHETIC_KEY_ONLY',fake_session=f2)
    assert len(f2.calls)==1 and f2.calls[0].endswith('/sports')


def test_alternate_runtime_refused_before_key(tiny_bundle,tmp_path):
    b,r,a,run,body=tiny_bundle;reads=[];fake=FakeSession(body)
    with pytest.raises(executor.Halt,match='fixed root-keyed'):
        executor.run(b,r,a,tmp_path/'other-checkout',key=lambda:reads.append(True),fake_session=fake)
    assert not reads and not fake.calls


def test_deleted_runtime_folder_refused_by_global_marker(tiny_bundle):
    import shutil
    b,r,a,run,body=tiny_bundle
    executor.run(b,r,a,run,key='SYNTHETIC_KEY_ONLY',fake_session=FakeSession(body));shutil.rmtree(run)
    reads=[];fake=FakeSession(body)
    with pytest.raises(executor.Halt,match='Registered runtime ledger missing'):
        executor.run(b,r,a,run,key=lambda:reads.append(True),fake_session=fake)
    assert not reads and not fake.calls


def test_deleted_entire_store_cannot_adopt_spent_balance(tiny_bundle):
    import shutil
    b,r,a,run,body=tiny_bundle;a['account_reconciliation']=policy(r,'capture_first_free_check')
    executor.run(b,r,a,run,key='SYNTHETIC_KEY_ONLY',fake_session=FakeSession(body));shutil.rmtree(executor.RUNTIME_BASE)
    fake=FakeSession(body);fake.used=1717;fake.remaining=4998283
    with pytest.raises(executor.Halt,match='max_baseline_used'):
        executor.run(b,r,a,run,key='SYNTHETIC_KEY_ONLY',fake_session=fake)
    assert len(fake.calls)==1 and fake.calls[0].endswith('/sports')


def test_live_checkout_and_git_runtime_refused(tiny_bundle,monkeypatch,tmp_path):
    b,r,a,run,body=tiny_bundle;reads=[];fake=FakeSession(body)
    monkeypatch.setattr(executor,'LIVE_CHECKOUT',b)
    with pytest.raises(executor.Halt,match='live checkout'):
        executor.run(b,r,a,run,key=lambda:reads.append(True),fake_session=fake)
    assert not reads and not fake.calls
    git=tmp_path/'repo';(git/'.git').mkdir(parents=True);monkeypatch.setattr(executor,'RUNTIME_BASE',git/'state')
    with pytest.raises(executor.Halt,match='outside every git'):executor.runtime_path(r)


@pytest.mark.parametrize('field,value',[('request_list_sha256','0'*64),('budget_credits',999999999),('commit','not-a-commit'),('comment_url','https://example.com/comment'),('comment_body','x')])
def test_strict_hub_approval_fields_refused_before_key(tiny_bundle,field,value):
    b,r,a,run,body=tiny_bundle;a['hub_go_ahead'][field]=value;reads=[];fake=FakeSession(body)
    with pytest.raises(executor.Halt,match='Hub go-ahead'):
        executor.run(b,r,a,run,key=lambda:reads.append(True),fake_session=fake)
    assert not reads and not fake.calls


def test_new_checkout_commit_invalidates_paid_approval(tiny_bundle,monkeypatch):
    b,r,a,run,body=tiny_bundle;monkeypatch.setattr(executor,'checkout_commit',lambda _:'c'*40)
    reads=[];fake=FakeSession(body)
    with pytest.raises(executor.Halt,match='current commit'):
        executor.run(b,r,a,run,key=lambda:reads.append(True),fake_session=fake)
    assert not reads and not fake.calls


@pytest.mark.parametrize('horizon',['entry','close'])
def test_actual_play_is_only_an_additional_exclusion(cfg,horizon):
    row,cat=quote_context();before=eligibility.evaluate(cfg,row,cat,horizon)
    assert before['eligible']
    cat['actual_play']['g']={'canonical_game_id':'g','utc':'2023-10-01T16:49:00Z','source_id':'independent','independent':True}
    assert not eligibility.evaluate(cfg,row,cat,horizon)['eligible']
    # Late decision/snapshot remains rejected even when actual play was much later.
    row,cat=quote_context(actual='2023-10-01T17:30:00Z',requested='2023-10-01T17:05:00Z',returned='2023-10-01T17:00:00Z')
    assert not eligibility.evaluate(cfg,row,cat,horizon)['eligible']


def missing_policy(root,auth,runtime,reason,response=None):
    state=json.loads((runtime/'spending-ledger.json').read_text());rid=state['pending'];prior=executor.sha(runtime/'spending-ledger.json')
    resolution={'request_id':rid,'reason':reason,'owner_note':'SYNTHETIC accepted missing only',
        'hub_go_ahead':{'status':'approved','commit':auth['execution_commit'],'comment_url':'https://github.com/maxzipperman/value-finder/pull/99#issuecomment-2',
            'comment_body':f"APPROVED missing response: root {root}, request {rid}, ledger {prior}, commit {auth['execution_commit']}, reason {reason}"}}
    if response is not None:resolution['response_sha256']=executor.sha(response)
    else:resolution['attempt_sha256']=hashlib.sha256(executor.canonical(state['attempts'][rid])).hexdigest()
    return {'status':'approved','bundle_root_sha256':root,'prior_ledger_sha256':prior,'missing_response_resolution':resolution}


@pytest.mark.parametrize('mode,reason',[('http500','http_5xx'),('http404','http_404'),('lag','snapshot_lag')])
def test_approved_missing_can_continue_without_resend(tiny_bundle,mode,reason):
    import cache_handoff
    b,r,a,run,body=tiny_bundle;fake=FakeSession(body,mode)
    with pytest.raises(executor.Halt):executor.run(b,r,a,run,key='SYNTHETIC_KEY_ONLY',fake_session=fake)
    cached=list((run/'data/raw').rglob('*.parquet'));rec=missing_policy(r,a,run,reason,cached[0] if cached else None)
    executor.accept_as_missing(b,r,a,rec,run)
    state=json.loads((run/'spending-ledger.json').read_text());rid=rec['missing_response_resolution']['request_id']
    assert state['attempts'][rid]['status']=='missing' and state['attempts'][rid]['reserved_credits']==30
    recovery=policy(r,'capture_first_free_check');recovery.update(max_baseline_used=1717,account_only_recovery=True,prior_ledger_sha256=executor.sha(run/'spending-ledger.json'))
    resume=FakeSession(body);resume.used=1717;resume.remaining=4998283
    executor.run(b,r,a,run,key='SYNTHETIC_KEY_ONLY',fake_session=resume,reconciliation=recovery)
    assert len(resume.calls)==1 and resume.calls[0].endswith('/sports')
    coverage=json.loads((run/'coverage-report.json').read_text())
    assert coverage['all_recent_requests_completed'] and coverage['accepted_missing_requests'][0]['reason']==reason
    assert all(x['status']=='missing_quote' for x in coverage['intended_slot_book_market_accounting'])
    handoff=cache_handoff.build_handoff(b,r,run)
    assert handoff['entries'][0]['status']=='accepted_missing' and handoff['entries'][0]['response_path'] is None


@pytest.mark.parametrize('change',['draft','wrong_ledger','wrong_request','wrong_comment','wrong_source'])
def test_missing_response_requires_exact_hub_approval(tiny_bundle,change):
    b,r,a,run,body=tiny_bundle
    with pytest.raises(executor.Halt):executor.run(b,r,a,run,key='SYNTHETIC_KEY_ONLY',fake_session=FakeSession(body,'lag'))
    saved=next((run/'data/raw').rglob('*.parquet'));rec=missing_policy(r,a,run,'snapshot_lag',saved)
    if change=='draft':rec['status']='draft'
    elif change=='wrong_ledger':rec['prior_ledger_sha256']='0'*64
    elif change=='wrong_request':rec['missing_response_resolution']['request_id']='wrong'
    elif change=='wrong_comment':rec['missing_response_resolution']['hub_go_ahead']['comment_body']='x'
    else:rec['missing_response_resolution']['response_sha256']='0'*64
    with pytest.raises(executor.Halt):executor.accept_as_missing(b,r,a,rec,run)
    assert json.loads((run/'spending-ledger.json').read_text())['pending'] is not None


@pytest.mark.parametrize('change',['missing_ceiling','negative_ceiling','old_period'])
def test_reconciliation_policy_refused_before_key(tiny_bundle,change):
    b,r,a,run,body=tiny_bundle;rec=a['account_reconciliation']
    if change=='missing_ceiling':rec.pop('max_baseline_used')
    elif change=='negative_ceiling':rec['max_baseline_used']=-1
    else:rec['billing_period_utc']='2000-01'
    reads=[];fake=FakeSession(body)
    with pytest.raises(executor.Halt,match='reconciliation'):
        executor.run(b,r,a,run,key=lambda:reads.append(True),fake_session=fake)
    assert not reads and not fake.calls


@pytest.mark.parametrize('mode',['timeout','overcharge','bad_billing','future'])
def test_unknown_failures_and_overcharges_cannot_be_accepted_missing(tiny_bundle,mode):
    b,r,a,run,body=tiny_bundle
    with pytest.raises(executor.Halt):executor.run(b,r,a,run,key='SYNTHETIC_KEY_ONLY',fake_session=FakeSession(body,mode))
    saved=list((run/'data/raw').rglob('*.parquet'))
    rec=missing_policy(r,a,run,'snapshot_lag' if saved else 'http_5xx',saved[0] if saved else None)
    with pytest.raises(executor.Halt):executor.accept_as_missing(b,r,a,rec,run)
    assert json.loads((run/'spending-ledger.json').read_text())['pending'] is not None


@pytest.mark.parametrize('change',['url','body','author'])
def test_live_hub_evidence_must_match_github(tiny_bundle,monkeypatch,change):
    b,r,a,run,body=tiny_bundle;hub=a['hub_go_ahead']
    comment={'html_url':hub['comment_url'],'body':hub['comment_body'],'user':{'login':'maxzipperman'}}
    if change=='url':comment['html_url']='https://example.com'
    elif change=='body':comment['body']='reviewing, not approved'
    else:comment['user']['login']='another-account'
    monkeypatch.setattr(executor.subprocess,'check_output',lambda *args,**kwargs:json.dumps(comment))
    with pytest.raises(executor.Halt,match='GitHub'):executor.verify_live_hub_comment(a)
