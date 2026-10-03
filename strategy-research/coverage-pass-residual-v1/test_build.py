"""Synthetic residual/gate/cache/budget tests; no runtime/provider/statistical look."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
HERE=Path(__file__).parent
sys.path.insert(0,str(HERE));import build
sys.path.insert(0,str(HERE.parent/'coverage-pilot-v1'))
from test_integration import loader

class ResidualTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.load=staticmethod(loader())

 def final(self):
  groups=[dict(stratum=k,status='utility_pass',population=100) for k in sorted(build.PASS)]
  groups += [dict(stratum='held/'+str(i),status='hold',population=100) for i in range(5)]
  groups += [dict(stratum='props/americanfootball_nfl/2025',status='census_only',population=5690)]
  return dict(record=dict(saved_bounds=dict(strata=groups)))

 def test_only_saved_pass_unknown_targets_no_resampling(self):
  k=next(iter(build.PASS));frame=[dict(game_id='u',stratum=k,classification='unknown'),dict(game_id='known',stratum=k,classification='success'),dict(game_id='failed',stratum=k,classification='failure'),dict(game_id='held',stratum='held/0',classification='unknown')]
  selected,denominator=build.target_selection(frame,self.final())
  self.assertEqual(selected['selected'],['u']);self.assertEqual(len(denominator),3)
  changed=self.final();changed['record']['saved_bounds']['strata'][0]['status']='hold'
  with self.assertRaises(ValueError):build.target_selection(frame,changed)
  with self.assertRaises(ValueError):build.target_selection(frame+frame,self.final())

 def test_budget_extension_is_finite_retains_floor_and_carry(self):
  r=build.assess_budget(67200)
  self.assertEqual(r['proposed_first_tranche_ceiling'],274686);self.assertEqual(r['account_reserve_floor'],531630)
  self.assertEqual(r['monthly_cumulative_ceiling'],4440000);self.assertEqual(r['shared_usage_allowance'],100)
  self.assertTrue(r['extension_required']);self.assertFalse(r['paid_authority'])
  self.assertFalse(build.assess_budget(40000)['extension_required'])
  for cap in (-1,True,1.5):
   with self.assertRaises(ValueError):build.assess_budget(cap)

 def test_rectangles_exact_cells_and_duplicate_refusal(self):
  plan=self.load('plan');r=plan.make_request('odds',plan.ts('2023-10-01T16:00:00Z'),books=['draftkings','fanduel'],markets=['player_pass_yds','player_receptions'],event_id='abc')
  rectangles=build.cell_rectangles([r]);self.assertEqual(rectangles[0]['cell_count'],4)
  with self.assertRaises(ValueError):build.cell_rectangles([r,r])

 def test_terminal_missing_cells_never_rebought_under_new_group(self):
  plan=self.load('plan');mapping=self.load('mapping');at='2023-10-01T16:00:00Z'
  op=dict(opportunity_id='g/T24',season=2023,sport=plan.NFL,event_id='abc',requested_utc=at,slot='T24',books=['draftkings'])
  history=[dict(cell=mapping.cell(plan.NFL,'abc',at,'draftkings',m),status='missing') for m in mapping.MARKETS]
  result=mapping.props_union([op],history,plan.make_request)
  self.assertEqual(result['requests'],[]);self.assertEqual(result['max_new_credits'],0)
  history[0]['status']='pending';self.assertTrue(mapping.props_union([op],history,plan.make_request)['blocked'])

 def test_shared_sweeps_deduplicate_and_pending_history_blocks(self):
  plan=self.load('plan');mapping=self.load('mapping')
  originals=[dict(request_id='sweep',max_new_credits=30)]
  frame=[dict(game_id=g,classification='unknown',binding=True,season=2020,stratum='older/americanfootball_nfl/2020') for g in ('g1','g2')]
  maps=[dict(game_id=g,request_ids=['sweep'],reason=None) for g in ('g1','g2')]
  result=mapping.original_union(frame,['g1','g2'],maps,originals,[],[])
  self.assertEqual(len(result['requests']),1);self.assertEqual(result['max_new_credits'],30)
  result=mapping.original_union(frame,['g1','g2'],maps,originals,[dict(request_id='sweep',status='missing')],[])
  self.assertEqual(result['requests'],[])
  result=mapping.original_union(frame,['g1','g2'],maps,originals,[dict(request_id='sweep',status='pending')],[])
  self.assertTrue(result['blocked'])

 def test_cached_cells_detect_overlap_even_without_ledger_claim(self):
  import pyarrow as pa
  import pyarrow.parquet as pq
  plan=self.load('plan');capture=self.load('capture');overlap=self.load('overlap')
  row=plan.make_request('odds',plan.ts('2023-10-01T16:00:00Z'),books=['draftkings'],markets=['player_pass_yds'],event_id='abc')
  with tempfile.TemporaryDirectory(dir='/private/tmp') as d:
   root=Path(d);p=root/row['sport']/row['source']/row['requested_utc'][:10]/(row['cache_key']+'.parquet');p.parent.mkdir(parents=True)
   rec={k:row[k] for k in ('source','sport','url','cache_key')};rec['params_json']=json.dumps(row['params']);pq.write_table(pa.Table.from_pylist([rec]),p)
   inv,metadata=build.cache_inventory([str(root)],capture)
   self.assertEqual(len(metadata),1)
   with self.assertRaisesRegex(ValueError,'overlap'):overlap.check([row],[str(root)],expected_inventory_sha256=build.identity(inv))
   sealed=root/row['sport']/row['source']/'2026-10-01'/'never-read.parquet';sealed.parent.mkdir();sealed.write_bytes(b'invalid protected input')
   self.assertEqual(build.cache_inventory([str(root)],capture)[0],inv)

 def test_saved_hold_reasons_only_and_nonexclusive_counts(self):
  frame=[dict(game_id='g',stratum='held/0')];final=self.final();final['record']['saved_bounds']['strata'][6].update(observed=0,sample=1);final['record']['classifications']={'g':False};final['details']={'g':dict(slot_reasons={'CLOSE':['kickoff_conflict','base_ineligible']},reference_both=False,paired_books=[])}
  for row in final['record']['saved_bounds']['strata'][7:11]:row.update(observed=0,sample=0)
  reasons=build.saved_exclusions(frame,final)[0]
  self.assertEqual(reasons['failed_games'],1);self.assertEqual(reasons['nonexclusive_game_reason_counts']['CLOSE:kickoff_conflict'],1)

 def test_committed_packet_totals_and_freeze_unchanged(self):
  import hashlib
  packet=HERE/'passing-groups-2020-24'
  m=json.loads((packet/'manifest.json').read_bytes());rows=json.loads((packet/'requests.json').read_bytes())
  self.assertEqual(len(rows),m['request_count']);self.assertEqual(sum(r['max_new_credits'] for r in rows),m['max_new_credits'])
  for prefix,count,cap in [('older/',364,10920),('props/',938,56280)]:
   groups=[g for g in m['per_group'] if g['stratum'].startswith(prefix)]
   self.assertEqual(sum(g['new_requests'] for g in groups),count);self.assertEqual(sum(g['new_cap'] for g in groups),cap)
  freeze=json.loads((packet/'FREEZE.json').read_bytes())
  self.assertEqual(build.identity(freeze['files']),freeze['root'])
  for name,pin in freeze['files'].items():
   if name.startswith(('code/','source/')):continue
   self.assertEqual(hashlib.sha256((packet/name).read_bytes()).hexdigest(),pin)
  self.assertEqual(freeze['files']['code/build.py'],hashlib.sha256((HERE/'build.py').read_bytes()).hexdigest())
  self.assertFalse(m['paid_authority']);self.assertFalse(m['execution_adapter_ready'])

 def test_source_mismatch_stops_before_execution(self):
  with tempfile.TemporaryDirectory(dir='/private/tmp') as d:
   sentinel=Path(d)/'ran';raw=f"open({str(sentinel)!r},'w').write('bad')".encode()
   with self.assertRaises(ValueError):build.module(raw,Path(d)/'bad.py','bad','0'*64)
   self.assertFalse(sentinel.exists())

if __name__=='__main__':unittest.main()
