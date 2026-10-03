"""Synthetic contracts only; no native quotes/account files/authority/transport."""
import copy
import dataclasses
import json
from pathlib import Path
import sys
import pytest
sys.path.insert(0,str(Path(__file__).parent))
import prospective as P
sys.path.insert(0,str(Path(__file__).parents[1]/'execution-v1'))
import stage
import successor151 as S
from test_successor151 import lineage
REPO=Path(__file__).resolve().parents[3]

@pytest.fixture
def rows():return stage.source()[1]

@pytest.fixture
def plan():
    return P.Plan('a'*64,'b'*40,P.LIST_SHA,P.SET_SHA,P.PROSPECTIVE_PROTOCOL_SHA,P.LINEAGE_SHA,'c'*64)

def test_protocol_is_exact_one_field_unadopted_amendment():
    raw=(REPO/'strategy-research/football_archive/acquisition/football-archive-v4/protocol.json').read_bytes()
    before=raw;original=json.loads(raw);result=P.prospective_protocol(raw)
    expected=copy.deepcopy(original);expected['budgets']['first_tranche_cumulative_credits']=400000
    assert result['protocol']==expected and raw==before
    assert result['protocol_sha256']==P.PROSPECTIVE_PROTOCOL_SHA
    assert not result['adopted'] and not result['paid_execution_enabled']
    with pytest.raises(ValueError):P.prospective_protocol(raw+b' ')

def test_all754_contracts_bind_existing_ids_explicit10_and_one_plan(plan,rows):
    contracts=P.exact_requests(plan,rows)
    assert len(contracts)==754 and sum(r.maximum_credits for r in contracts)==7540
    assert {c.request_id for c in contracts}=={r['request_id'] for r in rows}
    assert all(c.plan_root==plan.root and c.maximum_credits==10 for c in contracts)
    assert all('apiKey' not in c.public_params_json for c in contracts)

@pytest.mark.parametrize('field,value',[('request_id','0'*64),('path','/sports/basketball_nba/odds'),('max_new_credits',1),('max_credits',True),('retry_allowance',1),('sealed',True)])
def test_request_changes_cannot_be_recast_as_live_cost(plan,rows,field,value):
    row=copy.deepcopy(rows[0]);row[field]=value
    with pytest.raises(ValueError):P.historical_request(plan,row)

@pytest.mark.parametrize('field',['csv_sha256','request_set_sha256','prospective_protocol_sha256','lineage_pins_sha256'])
def test_plan_content_substitution_rejected(plan,field):
    with pytest.raises(ValueError):dataclasses.replace(plan,**{field:'0'*64}).validate()

def test_whole_set_subset_duplicate_or_price_selected_rows_rejected(plan,rows):
    for altered in (rows[:753],rows[:-1]+[rows[0]],list(reversed(rows))):
        with pytest.raises(ValueError):P.exact_requests(plan,altered)

def receipt(request,replayed=False):
    return dict(request_id=request.request_id,plan_identity_sha256=request.plan_identity_sha256,status=200,
                headers={'x-requests-last':'10','x-requests-used':'100010','x-requests-remaining':'4899990'},
                body='{"data":[]}',observed_utc='2026-10-03T20:00:00Z',replayed=replayed)

def test_replay_preserves_original_clock_and_bill_without_new_send(plan,rows):
    req=P.historical_request(plan,rows[0]);r=receipt(req,True)
    before=copy.deepcopy(r);out=P.validate_account_receipt(r,req)
    assert out==before and r==before and out is not r
    assert out['observed_utc']=='2026-10-03T20:00:00Z' and out['headers']['x-requests-last']=='10'

@pytest.mark.parametrize('change',['different_request','different_plan','missing_header','overbill','redirect','naive_time','bad_replay'])
def test_bad_account_receipt_remains_uncertain(plan,rows,change):
    req=P.historical_request(plan,rows[0]);r=receipt(req)
    if change=='different_request':r['request_id']='0'*64
    elif change=='different_plan':r['plan_identity_sha256']='0'*64
    elif change=='missing_header':r['headers'].pop('x-requests-last')
    elif change=='overbill':r['headers']['x-requests-last']='11'
    elif change=='redirect':r['status']=302
    elif change=='naive_time':r['observed_utc']='2026-10-03T20:00:00'
    elif change=='bad_replay':r['replayed']='yes'
    with pytest.raises(ValueError):P.validate_account_receipt(r,req)

@pytest.fixture
def active(plan,rows):
    row=rows[0];req=P.historical_request(plan,row);account=receipt(req)
    record=dict(cache_key=row['cache_key'],http_status=200,url=req.url,sport='nba',source='oddsapi_hist',
                params_json=json.dumps(row['params']),body=account['body'],headers_json=json.dumps(account['headers']))
    saved=dict(request_id=row['request_id'],cache_key=row['cache_key'],record_sha256='d'*64,
               body_sha256=P.sha(record['body'].encode()),headers=account['headers'],record=record)
    raw=P.canonical(saved)
    state=dict(bundle_root_sha256=plan.root,authorization_sha256=plan.authorization_sha256,slice_cap=7540,
               probe_credits=1687,other_usage_reserved=272899,pending=None,stopped=None,status='running',
               attempts={row['request_id']:dict(status='completed',reserved_credits=10,receipt_sha256=P.sha(raw),cache_key=row['cache_key'],response_sha256='d'*64)})
    marker=dict(bundle_root_sha256=plan.root,authorization_sha256=plan.authorization_sha256,runtime_path=str((P.PURCHASE_LOCK.parent/plan.root).resolve()))
    init=dict(bundle_root_sha256=plan.root,probe_credits=1687)
    return plan,state,marker,init,{row['request_id']:raw},{row['request_id']:account}

def test_successor_aware_projection_proves_active_before_exemption(lineage,active,rows):
    states,pins=lineage
    # Synthetic pins here prove pure logic; no production runtime/authentication claim.
    captured={root:P.canonical(state) for root,state in states.items()}
    pins['ledger_pins']={root:P.sha(raw) for root,raw in captured.items()}
    captured[active[0].root]=P.canonical(active[1])
    result=P.settled_projection(captured,pins,rows,active=active)
    assert len(result['historical_roots'])==11 and result['active_attribution_sha256']
    assert not result['paid_execution_enabled'] and not result['adopted']
    assert states[pins['retired_root']]['attempts'][pins['pending_id']]['reserved_credits']==60
    with pytest.raises(ValueError):P.settled_projection(captured,pins,rows)

@pytest.mark.parametrize('change',['wrong_authority','pending','lost_receipt','changed_receipt','lost_carry','unknown_request','terminal_incomplete','different_account_body'])
def test_active_root_cannot_be_excluded_by_name_alone(active,rows,change):
    plan,state,marker,init,receipts,accounts=copy.deepcopy(active);rid=next(iter(state['attempts']))
    if change=='wrong_authority':marker['authorization_sha256']='0'*64
    elif change=='pending':state['pending']=rid
    elif change=='lost_receipt':receipts.clear()
    elif change=='changed_receipt':receipts[rid]=b'changed'
    elif change=='lost_carry':state['other_usage_reserved']=0
    elif change=='unknown_request':state['attempts']['unknown']=copy.deepcopy(state['attempts'][rid])
    elif change=='terminal_incomplete':state['status']='nba_n0_epoch_complete'
    elif change=='different_account_body':accounts[rid]['body']='different'
    with pytest.raises(ValueError):P.active_attribution(plan,state,marker,init,rows,receipts,accounts)

def test_no_factory_or_packet_flag_can_enable_production(plan):
    sentinel=lambda *a,**k:pytest.fail('Factory must not reach key/HTTP/account/runtime')
    for fun in (P.historical_session_factory,P.require_packet_admission):
        with pytest.raises(P.Held):fun(session=sentinel,plan=plan,account_boundary=sentinel,approved=True,fake_session=sentinel)


def test_source_verified_lock_graph_and_no_new_account_domain():
    driver=(REPO/'strategy-research/nba_sample/execution-v1/execute.py').read_text()
    frozen=(REPO/'strategy-research/football_archive/acquisition/football-archive-v4/executor.py').read_text()
    assert driver.index('flock(global_lock') < driver.index('ledger = base.Ledger') < driver.index('base.GuardedSession')
    assert "self.folder/'acquisition.lock'" in frozen and 'flock(self.lock' in frozen
    assert "self.session.get(url" in frozen # per-send account wrapper belongs INSIDE this seam
    assert P.ACCOUNT_JOURNAL.name=='journal.json' and str(P.ACCOUNT_JOURNAL).endswith('/ValueFinder/shared-account-state/journal.json')
    assert P.PURCHASE_LOCK.name=='followup-purchase.lock'
    # Static actual-driver graph only; operational owners/PR167 runtime unverified.


def test_real_v4_plan_lock_between_outer_and_synthetic_account_lock(tmp_path):
    """Actual Ledger and kernel locks, temporary synthetic authority/account only.

    Does not prove a deployed account wrapper, lock graph or writer inventory.
    """
    import fcntl
    from test_execute import frozen_base, approval
    base,bundle=frozen_base()
    root='a'*64
    manifest={'request_list_sha256':stage.EXPECTED['request-list.csv'],
              'request_set_sha256':stage.REQUEST_SET_SHA256,'new_credits':7540,
              'new_credits_by_priority':{'1':7540},'requests':[]}
    auth=approval(root,manifest)
    auth['priority']=1
    probe={'pending':None,'stopped':None,'attempts':[{'counted_credits':1687}],'reserved_credits':1687}
    protocol=json.loads((bundle/'protocol.json').read_text())
    with (tmp_path/'followup-purchase.lock').open('a') as outer:
        fcntl.flock(outer,fcntl.LOCK_EX|fcntl.LOCK_NB)
        ledger=base.Ledger(tmp_path/root,protocol,manifest,root,auth,probe)
        try:
            with (tmp_path/'journal.json.lock').open('a') as account:
                fcntl.flock(account,fcntl.LOCK_EX|fcntl.LOCK_NB)
                for path in (tmp_path/'followup-purchase.lock',ledger.folder/'acquisition.lock',tmp_path/'journal.json.lock'):
                    with path.open('a') as contender:
                        with pytest.raises(BlockingIOError):
                            fcntl.flock(contender,fcntl.LOCK_EX|fcntl.LOCK_NB)
                assert ledger.state['pending'] is None and not ledger.state['attempts']
        finally:
            ledger.close()
    for path in (tmp_path/'followup-purchase.lock',tmp_path/root/'acquisition.lock',tmp_path/'journal.json.lock'):
        with path.open('a') as released:
            fcntl.flock(released,fcntl.LOCK_EX|fcntl.LOCK_NB)
