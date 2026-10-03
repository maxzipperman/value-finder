"""Synthetic bridge adversity. No live state, API, credentials or outcomes."""
import copy
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
HERE=Path(__file__).parent
sys.path.insert(0,str(HERE));import bootstrap
sys.path.insert(0,str(HERE.parent/'coverage-pilot-v1'))
from test_integration import BUNDLE


def loader():
 import importlib.util
 meta=HERE.parent/'football-metadata-v1';p=meta/'capture.py'
 spec=importlib.util.spec_from_file_location('bulk_test_capture',p);cap=importlib.util.module_from_spec(spec);spec.loader.exec_module(cap)
 paths={}
 for p in BUNDLE.rglob('*.py'):
  n=str(p.relative_to(BUNDLE));key=(n[:-12] if n.endswith('/__init__.py') else n[:-3]).replace('/','.');paths[key]=p
 for p in (HERE.parent/'coverage-pilot-v1').glob('*.py'):
  if not p.name.startswith('test_'):paths[p.stem]=p
 paths.update(capture=meta/'capture.py',history=meta/'history.py',plan=HERE.parent/'nfl-props-archive-v1/plan.py',f2_gate=HERE.parent/'football_archive/f2_handoff.py',older_recovery=HERE.parent/'football_archive/older-recovery-v1/recovery.py',preparation=HERE.parent/'coverage-pass-residual-v1/build.py',packet_builder=HERE.parent/'coverage-pilot-packet-v1/build.py',runner=HERE/'validator.py',bootstrap=HERE/'bootstrap.py',orchestration=HERE/'orchestration.py')
 return cap.closed_modules({n:p.read_bytes() for n,p in paths.items()},paths)


class BridgeTests(unittest.TestCase):
 def test_logical_source_mutation_and_unknown_physical_file_fail(self):
  with tempfile.TemporaryDirectory(dir='/private/tmp') as d:
   folder=Path(d);config=dict(repo=d,preparation=d,final_record=d,restart_policy=dict(allowed=['prepared','running','pilot_clean_pause'],pending='block_no_resend',stopped='block_reconciliation',terminal='exhausted',automatic_retries=0,automatic_redirects=0))
   data={'logical-source':b'original'}
   for n in bootstrap.PHYSICAL:
    raw=bootstrap.canonical(config if n=='config.json' else {});(folder/n).write_bytes(raw);data[n]=raw
   data['protocol.json']=bootstrap.canonical({'execution_status':'reviewed_for_execution'})
   files={n:bootstrap.sha(v) for n,v in data.items()};root=bootstrap.sha(bootstrap.canonical(files));(folder/'FREEZE.json').write_bytes(bootstrap.canonical(dict(root=root,files=files)))
   inputs=lambda *a:(dict(data),{},None)
   load=lambda n:SimpleNamespace(packet=lambda *a:None)
   with patch.object(bootstrap,'inputs',inputs),patch.object(bootstrap,'load_modules',lambda *a:load):
    bootstrap.verified(folder,root)
    data['logical-source']=b'changed'
    with self.assertRaisesRegex(ValueError,'closure'):bootstrap.verified(folder,root)
    data['logical-source']=b'original';(folder/'unexpected').write_text('x')
    with self.assertRaisesRegex(ValueError,'inventory'):bootstrap.verified(folder,root)

 def test_bulk_validator_rejects_cells_policy_budget_and_denominator_drift(self):
  load=loader();v=load('runner');cap=load('capture')
  prep=HERE.parent/'coverage-pass-residual-v1/passing-groups-2020-24';pilot=HERE.parent/'coverage-pilot-packet-v1/pilot-successor-142'
  data={n:(prep/n).read_bytes() for n in ('requests.json','mappings.json','denominators.json','cell-allowlist.json','future-budget-policy.json')}
  data['preparation/manifest.json']=(prep/'manifest.json').read_bytes();m=json.loads(data['preparation/manifest.json']);m['request_set_sha256']=cap.identity(json.loads(data['requests.json']));data['manifest.json']=bootstrap.canonical(m)
  data['policy.json']=(prep/'response-policy.json').read_bytes();data['frame.json']=(pilot/'frame.json').read_bytes()
  frame=json.loads(data['frame.json']);groups=sorted({g['stratum'] for g in frame});f={'record':{'saved_bounds':{'strata':[dict(stratum=k,status='utility_pass' if k in v.preparation.PASS else 'hold',population=sum(g['stratum']==k for g in frame)) for k in groups]}}}
  data['final-record.json']=bootstrap.canonical(f);v.FINAL_SHA=cap.digest(data['final-record.json']) # synthetic source substitution only
  source={n:(BUNDLE/n).read_bytes() for n in ('protocol.json','request-manifest.json')};cfg=json.loads(source['protocol.json']);cfg['budgets']=json.loads(data['future-budget-policy.json'])['budgets'];data['execution-protocol.json']=bootstrap.canonical(cfg)
  v.packet(data,source)
  mutations={
   'cell-allowlist.json':[],
   'denominators.json':[],
   'policy.json':dict(json.loads(data['policy.json']),max_missing={'snapshot_lag':99999,'event_not_found':99999}),
   'execution-protocol.json':dict(cfg,budgets=dict(cfg['budgets'],first_tranche_cumulative_credits=999999)),
   'requests.json':json.loads(data['requests.json'])[:-1]}
  for name,value in mutations.items():
   changed=dict(data);changed[name]=bootstrap.canonical(value)
   with self.subTest(name=name),self.assertRaises(ValueError):v.packet(changed,source)

 def test_actual_ledger_pending_exposure_and_resumed_baseline_no_double_bill(self):
  load=loader();base=load('executor');m=load('orchestration');transport=load('transport')
  ledger=object.__new__(base.Ledger);ledger.protocol=json.loads((BUNDLE/'protocol.json').read_bytes());ledger.protocol['budgets']['first_tranche_cumulative_credits']=274686
  cap=67200;floor=531630;left=floor+67170
  ledger.state=dict(probe_credits=1687,other_usage_reserved=205699,slice_cap=cap,provider_remaining=left,epoch=dict(start_remaining=left,start_billed=0,remaining_lowwater=left,external_peak=0),attempts={'pending':dict(status='pending',reserved_credits=60)})
  with self.assertRaises(ValueError):m.remaining_checks(ledger,cap)
  # Resumed baseline already includes previous40 billed; retained60 reservation
  # stays in cumulative debit but is not a second future charge.
  left=floor+67120
  ledger.state['attempts']['old']=dict(status='completed',reserved_credits=60,billed_credits=40)
  ledger.state.update(provider_remaining=left,epoch=dict(start_remaining=left,start_billed=40,remaining_lowwater=left,external_peak=0))
  paid=[];http=SimpleNamespace(adapters={'https':SimpleNamespace(max_retries=SimpleNamespace(total=0))},get=lambda *a,**k:paid.append(a),close=lambda:None)
  session=transport.guarded_session(base,lambda:None,lambda:m.remaining_checks(ledger,cap))(http,ledger,[])
  with self.assertRaises(ValueError):session.get('https://api.the-odds-api.com/v4/historical/sports/americanfootball_nfl/odds',params={})
  self.assertEqual(paid,[])
  ledger.state.update(provider_remaining=floor+67140,epoch=dict(start_remaining=floor+67140,start_billed=40,remaining_lowwater=floor+67140,external_peak=0))
  self.assertEqual(m.remaining_checks(ledger,cap),dict(untouched=67080,pending_unpaid=60,future_exposure=67140))

 def test_revoked_authority_stops_before_key(self):
  load=loader();m=load('orchestration');base=load('executor');seen=[]
  data={'protocol.json':b'{"execution_status":"reviewed_for_execution"}','manifest.json':b'{"max_new_credits":10}','requests.json':b'[]','policy.json':b'{}','baseline.json':b'{"expected_global_snapshot":{}}','overlap.json':b'{}'}
  verified=lambda *a:(SimpleNamespace(packet=lambda *a:None),base,data,{},load)
  with patch.object(m.bootstrap,'verified',verified),patch.object(base,'checkout_commit',lambda *a:'a'*40),patch.object(base,'execution_context',lambda *a:None),patch.object(m.authority,'check',side_effect=ValueError('revoked')):
   with self.assertRaises(ValueError):m.run('/private/tmp/unused','a'*64,None,{},key_factory=lambda:seen.append('key'),http_factory=lambda:seen.append('http'))
  self.assertEqual(seen,[])

if __name__=='__main__':unittest.main()
