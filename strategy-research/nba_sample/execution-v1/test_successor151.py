"""Pure synthetic finite-lineage accounting and pre-transport hold tests."""
import copy
import json
from pathlib import Path
import sys
from unittest.mock import patch
import pytest
sys.path.insert(0,str(Path(__file__).parent))
import successor151 as S
import stage
import execute

@pytest.fixture
def lineage():
    pins=json.loads((S.HERE/'successor151-pins.json').read_bytes())
    states={r:dict(bundle_root_sha256=r,status=pins['statuses'][r],probe_credits=1687,
                  other_usage_reserved=0,attempts={},cache_reuse={},pending=None,stopped=None)
            for r in pins['ledger_pins']}
    retired=states[pins['retired_root']]; retired['other_usage_reserved']=205699
    retired['attempts']={str(i):dict(cache_key='old'+str(i),reserved_credits=60,status='completed',billed_credits=60) for i in range(11)}
    retired['attempts'][pins['pending_id']]=dict(cache_key='05175510dc14de25e2ca',reserved_credits=60,status='pending')
    retired['pending']=pins['pending_id'];retired['stopped']='immutable test stop'
    final=states[S.ROOT];final['other_usage_reserved']=206419
    final['attempts']={str(100+i):dict(cache_key='new'+str(i),reserved_credits=50,status='completed' if i<1288 else 'missing') for i in range(1290)}
    final['attempts']['1389']['reserved_credits']=2030
    return states,pins

def test_exact_finite_accounting_preserves_pending60_and_f2_pin(lineage):
    states,pins=lineage;before=copy.deepcopy(states)
    S.validate(states,pins,[])
    assert states==before and S.debit(states[S.ROOT])==274586
    assert S.debit(states[S.ROOT])+S.CAP==282126
    assert pins['f2_union_proof_sha256']=='b95fcfb3bcbc5508c0bf656d7a267207cf77106d9a551ca34302a7c4e21cc95f'

@pytest.mark.parametrize('change',['pending60','retiredcarry','finalcarry','missing','unknownroot','finalpending','ceiling','overlap','f2parentcarry'])
def test_adverse_lineage_changes_fail(lineage,change):
    states,pins=lineage;rows=[];retired=states[pins['retired_root']];final=states[S.ROOT]
    if change=='pending60':retired['attempts'][pins['pending_id']]['reserved_credits']=0
    elif change=='retiredcarry':retired['other_usage_reserved']=0
    elif change=='finalcarry':final['other_usage_reserved']=0
    elif change=='missing':final['attempts']['1389']['status']='completed'
    elif change=='unknownroot':states['0'*64]=copy.deepcopy(final)
    elif change=='finalpending':final['pending']='x'
    elif change=='ceiling':pins['proposed_ceiling']=250000
    elif change=='overlap':rows=[dict(request_id=pins['pending_id'],cache_key='unseen')]
    elif change=='f2parentcarry':
        parent=next(r for r in states if r not in (S.ROOT,pins['retired_root']))
        final['predecessor_seed']=dict(root=parent,ledger_sha256=pins['ledger_pins'][parent],probe_credits=1687,cumulative_debit_without_probe=-1)
    with pytest.raises(ValueError):S.validate(states,pins,rows)

def test_changed_linked_or_missing_metadata_rejected(tmp_path):
    p=tmp_path/'metadata';p.write_bytes(b'x')
    with pytest.raises(ValueError,match='hash'):S.checked(p,'0'*64)
    p.unlink();p.symlink_to(tmp_path/'missing')
    with pytest.raises(ValueError,match='Linked'):S.checked(p,'0'*64)

def test_arbitrary_pilot_or_older_parent_not_production_n0(tmp_path):
    for root in ('0'*64,stage.V4_ROOT):
        with pytest.raises(ValueError,match='Only exact successor151'):
            stage.seed(stage.RUNTIME_BASE/root/'spending-ledger.json',[],require_f2=True)

def test_actual_packet_held_before_directory_or_cache_scanning(tmp_path):
    with patch.object(stage,'source',return_value=({},[])),patch.object(stage,'seed',return_value={'kind':'exact_successor151_preparation_only'}),patch.object(stage,'reconcile',side_effect=AssertionError('held before scan')):
        with pytest.raises(ValueError,match='Actual N0 packet held'):stage.prepare(Path('parent'),tmp_path/'packet')
    assert not (tmp_path/'packet').exists()

def test_paid_executor_held_before_source_import_key_or_runtime(tmp_path):
    with patch.object(stage,'verify_packet',return_value=({},[],{'kind':'exact_successor151_preparation_only'})),patch.object(execute,'source_executor',side_effect=AssertionError('held before import')):
        with pytest.raises(ValueError,match='preparation only'):execute.run(tmp_path,'0'*64,tmp_path,{},key=lambda:pytest.fail('must never load key'))
