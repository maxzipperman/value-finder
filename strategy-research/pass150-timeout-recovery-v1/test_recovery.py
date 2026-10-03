"""Focused synthetic adversity. No live state/network/key/provider access."""
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

HERE=Path(__file__).parent
REPO=HERE.parent.parent

def loader():
 p=HERE.parent/'football-metadata-v1/capture.py';spec=importlib.util.spec_from_file_location('timeout_test_capture',p);cap=importlib.util.module_from_spec(spec);spec.loader.exec_module(cap)
 paths={}
 source=HERE.parent/'football_archive/acquisition/football-archive-v4'
 for p in source.rglob('*.py'):
  n=str(p.relative_to(source));key=(n[:-12] if n.endswith('/__init__.py') else n[:-3]).replace('/','.');paths[key]=p
 pilot=HERE.parent/'coverage-pilot-v1';bridge=HERE.parent/'coverage-pass-execution-v1'
 for p in pilot.glob('*.py'):
  if not p.name.startswith('test'):paths[p.stem]=p
 paths.update(capture=HERE.parent/'football-metadata-v1/capture.py',history=HERE.parent/'football-metadata-v1/history.py',plan=HERE.parent/'nfl-props-archive-v1/plan.py',f2_gate=HERE.parent/'football_archive/f2_handoff.py',older_recovery=HERE.parent/'football_archive/older-recovery-v1/recovery.py',preparation=HERE.parent/'coverage-pass-residual-v1/build.py',packet_builder=HERE.parent/'coverage-pilot-packet-v1/build.py',prior_runner=bridge/'validator.py',prior_authority=pilot/'authority.py',prior_evidence=pilot/'evidence.py')
 paths.update({k:HERE/n for k,n in {'bootstrap':'bootstrap.py','runner':'validator.py','orchestration':'orchestration.py','evidence':'evidence.py','authority':'authority.py','execution':'execution.py','timeout_quarantine':'quarantine.py','timeout_authority':'authority.py'}.items()})
 return cap.closed_modules({n:p.read_bytes() for n,p in paths.items()},paths)

class RecoveryTests(unittest.TestCase):
 def setUp(self):self.load=loader()

 def test_projection_all12_excluded11_reused_pending_visible(self):
  q=self.load('timeout_quarantine');old=HERE.parent/'coverage-pass-execution-v1/passing-execution-confirmed-path-fix'
  rows=json.loads((old.parent.parent/'coverage-pass-residual-v1/passing-groups-2020-24/requests.json').read_bytes())
  maps=json.loads((old.parent.parent/'coverage-pass-residual-v1/passing-groups-2020-24/mappings.json').read_bytes())
  state=json.loads((HERE/'exact-stop-certificate/before-ledger.json').read_bytes());before=copy.deepcopy(state)
  untouched,projected=q.selection(rows,maps,state)
  self.assertEqual(len(untouched),1290);self.assertEqual(sum(r['max_new_credits'] for r in untouched),66480)
  self.assertFalse(set(state['attempts']) & {r['request_id'] for r in untouched})
  self.assertEqual([m['game_id'] for m in projected],[m['game_id'] for m in maps]);self.assertEqual(state,before)
  claims=[c for m in projected for s in m.get('reused_slots',[]) for c in s['evidence'] if c.get('root')==q.ROOT]
  self.assertEqual({c['request_id'] for c in claims},set(state['attempts'])-{q.RID});self.assertNotIn(q.RID,{c['request_id'] for c in claims})
  unavailable=[m for m in projected if m.get('certified_unavailable_request_ids')]
  self.assertTrue(unavailable);self.assertTrue(all(m['certified_unavailable_request_ids']==[q.RID] for m in unavailable))
  for c in claims:self.assertEqual(c['response_sha256'],state['attempts'][c['request_id']]['response_sha256'])

 def test_transport_retries_bounded_and_only_transient(self):
  a=self.load('timeout_authority');calls=[];waits=[]
  def eventual():
   calls.append(1)
   if len(calls)<3:raise subprocess.TimeoutExpired('synthetic',10)
   return json.dumps({'body':'REVOKED'})
  self.assertEqual(a.fetch_live_comment(1,query=eventual,sleep=waits.append),{'body':'REVOKED'});self.assertEqual(len(calls),3);self.assertEqual(waits,[1,2])
  for error in [subprocess.CalledProcessError(1,'synthetic',stderr='HTTP 403 Forbidden'),ValueError('body mismatch'),json.JSONDecodeError('invalid','x',0),FileNotFoundError('gh unavailable')]:
   calls=[]
   def fatal():calls.append(1);raise error
   with self.assertRaises(Exception):a.fetch_live_comment(1,query=fatal,sleep=lambda _:None)
   self.assertEqual(len(calls),1)
  calls=[]
  def exhaust():calls.append(1);raise subprocess.CalledProcessError(1,'synthetic',stderr='dial tcp: i/o timeout')
  with self.assertRaisesRegex(ValueError,'transport'):a.fetch_live_comment(1,query=exhaust,sleep=lambda _:None)
  self.assertEqual(len(calls),3)
  calls=[]
  def bad_json():calls.append(1);return 'not json'
  with self.assertRaises(json.JSONDecodeError):a.fetch_live_comment(1,query=bad_json,sleep=lambda _:None)
  self.assertEqual(len(calls),1)

 def test_live_revocation_mismatch_and_login_fatal_no_fallback(self):
  a=self.load('authority');base=self.load('executor');digest=self.load('planner').digest
  root='a'*64;commit='b'*40;manifest={'new_credits_by_priority':{'1':60},'request_list_sha256':'c'*64,'request_set_sha256':'d'*64}
  context={k:'e'*64 for k in ('policy_sha256','plan_sha256','global_snapshot_sha256','historical_bindings_sha256','cache_union_sha256','captured_closure_sha256')}
  rec=dict(status='approved',bundle_root_sha256=root,baseline_mode='capture_first_free_check',reason='synthetic',owner_note='synthetic',max_baseline_used=0,billing_period_utc=base.datetime.now(base.timezone.utc).strftime('%Y-%m'))
  text=f"APPROVED paid run: list {'c'*64}, request-set {'d'*64}, budget 60 credits, commit {commit}\nAPPROVED pilot context: sha256 {digest(context)}, root {root}\nAPPROVED account reconciliation: sha256 {digest(rec)}, root {root}\nCURRENT PAID AUTHORITY: ACTIVE"
  hub=dict(status='approved',bundle_root_sha256=root,request_list_sha256='c'*64,request_set_sha256='d'*64,budget_credits=60,commit=commit,comment_url='https://github.com/maxzipperman/value-finder/pull/99#issuecomment-1',comment_body=text)
  auth=dict(status='approved',bundle_root_sha256=root,priority=1,max_new_credits=60,human_authorization_evidence='synthetic',execution_commit=commit,account_reconciliation=rec,hub_go_ahead=hub,pilot_context=context)
  live=dict(body=text,html_url=hub['comment_url'],user={'login':'maxzipperman'})
  a.check(base,auth,manifest,root,commit,context,fetch=lambda _:live)
  for bad in (dict(live,body='REVOKED'),dict(live,body=text+' changed'),dict(live,user={'login':'other'})):
   calls=[]
   def fetch(_):calls.append(1);return bad
   with self.assertRaises(ValueError):a.check(base,auth,manifest,root,commit,context,fetch=fetch)
   self.assertEqual(len(calls),1)

 def test_offline_approval_exact_cert_no_future_purchase(self):
  q=self.load('timeout_quarantine');capture=self.load('capture');cert=json.loads((HERE/'exact-stop-certificate/certificate.json').read_bytes());pin=capture.identity(cert)
  body=f'APPROVED offline pre-send quarantine: certificate {pin}, ledger {q.BEFORE}, pending {q.RID}, keep reserve 60, no resend';url='https://github.com/maxzipperman/value-finder/pull/151#issuecomment-1'
  binding=dict(certificate=cert,certificate_sha256=pin,approval={'comment_url':url,'comment_body':body});live=dict(html_url=url,body=body,user={'login':'maxzipperman'})
  self.assertEqual(q.verify_approval(binding,fetch=lambda _:live),cert)
  for bad in (dict(live,body='REVOKED'),dict(live,body=body+' changed'),dict(live,user={'login':'other'})):
   with self.assertRaises(ValueError):q.verify_approval(binding,fetch=lambda _:bad)
  with self.assertRaises(ValueError):q.verify_approval(dict(binding,certificate=dict(cert,pending_reserved=0)),fetch=lambda _:live)
  self.assertFalse(cert['next_purchase_authorized']);self.assertFalse(cert['usable_quote'])

 def test_before_reservation_lookup_failure_and_before_send_revocation(self):
  load=self.load;loop=load('execution');base=load('executor');transport=load('transport');plan=load('plan');capture=load('capture')
  row=plan.make_request('odds',plan.ts('2025-10-01T06:00:00Z'),books=['draftkings'],markets=['player_pass_yds'],event_id='abc');row=dict(row,path=row['url'].removeprefix(plan.BASE),priority=1)
  policy=dict(snapshot_lag_ids=[row['request_id']],event_not_found_ids=[row['request_id']],max_missing={'snapshot_lag':1,'event_not_found':1})
  for fail_at in (3,4):
   with self.subTest(fail_at=fail_at),tempfile.TemporaryDirectory(dir='/private/tmp') as d:
    folder=Path(d);state=dict(attempts={},pending=None,status='running',free_account_attempt={});reserved=[];calls=[];checks=[]
    def auth():
     checks.append(1)
     if len(checks)==fail_at:raise ValueError('live authority unavailable/revoked')
    def reserve(r):reserved.append(r['request_id']);state['pending']=r['request_id'];state['attempts'][r['request_id']]=dict(status='pending',reserved_credits=10)
    def save():(folder/'ledger.json').write_text(json.dumps(state))
    ledger=SimpleNamespace(folder=folder,state=state,reserve=reserve,account=lambda *a:None,halt=lambda _:state.update(status='halted'),save=save,observe_headers=lambda *a:None)
    http=SimpleNamespace(adapters={'https':SimpleNamespace(max_retries=SimpleNamespace(total=0))},get=lambda url,**kw:calls.append(url) or SimpleNamespace(status_code=200,headers={'x-requests-last':'0','x-requests-used':'0','x-requests-remaining':'5000000'},text='[]'),close=lambda:None)
    def get_or_fetch(**kw):return kw['fetch']()
    cache=SimpleNamespace(lookup=lambda *a:None,get_or_fetch=get_or_fetch)
    with patch.object(loop.evidence,'captured_receipts',lambda *a:{'untouched_ids':[row['request_id']]}):
     with self.assertRaises(ValueError):loop.prepared_loop(base=base,ledger=ledger,rows=[row],policy=policy,raw_cache=cache,fetched_type=lambda *a:a,http_session=http,authorize_live=auth,verify_unchanged=lambda:None,credential='synthetic-test-secret')
    self.assertEqual(calls,['https://api.the-odds-api.com/v4/sports']);self.assertEqual(len(reserved),0 if fail_at==3 else 1)
    if fail_at==4:self.assertNotIn('send_started',state['attempts'][row['request_id']])

 def test_paid_session_failure_never_retries(self):
  load=self.load;base=load('executor');transport=load('transport');plan=load('plan')
  row=plan.make_request('odds',plan.ts('2025-10-01T06:00:00Z'),books=['draftkings'],markets=['player_pass_yds'],event_id='abc')
  row=dict(row,path=row['url'].removeprefix(plan.BASE),priority=1)
  with tempfile.TemporaryDirectory(dir='/private/tmp') as d:
   state={'pending':row['request_id'],'attempts':{row['request_id']:{'status':'pending'}}};calls=[]
   path=Path(d)/'ledger.json'
   def save():path.write_text(json.dumps(state))
   save();ledger=SimpleNamespace(state=state,path=path,save=save,observe_headers=lambda *a:None)
   def get(*a,**k):calls.append(1);raise TimeoutError('synthetic paid timeout')
   http=SimpleNamespace(adapters={'https':SimpleNamespace(max_retries=SimpleNamespace(total=0))},get=get,close=lambda:None)
   session=transport.guarded_session(base,lambda:None,lambda:None)(http,ledger,[row])
   with self.assertRaises(TimeoutError):session.get(row['url'],params=row['params'])
   with self.assertRaises(Exception):session.get(row['url'],params=row['params'])
   self.assertEqual(len(calls),1);self.assertIs(state['attempts'][row['request_id']]['send_started'],True)

 def test_pending_exposure_remains_in_floor_without_double_bill(self):
  load=self.load;base=load('executor');m=load('orchestration');source=HERE.parent/'football_archive/acquisition/football-archive-v4'
  ledger=object.__new__(base.Ledger);ledger.protocol=json.loads((source/'protocol.json').read_bytes());ledger.protocol['budgets']['first_tranche_cumulative_credits']=274686
  cap=66480;left=531630+cap-30
  ledger.state=dict(probe_credits=1687,other_usage_reserved=206419,slice_cap=cap,provider_remaining=left,epoch=dict(start_remaining=left,start_billed=0,remaining_lowwater=left,external_peak=0),attempts={'p':dict(status='pending',reserved_credits=60)})
  with self.assertRaises(ValueError):m.remaining_checks(ledger,cap)
  ledger.state['provider_remaining']=531630+cap;ledger.state['epoch'].update(start_remaining=531630+cap,remaining_lowwater=531630+cap)
  self.assertEqual(m.remaining_checks(ledger,cap),dict(untouched=cap-60,pending_unpaid=60,future_exposure=cap))

 def fixture(self,base):
  import pyarrow as pa
  import pyarrow.parquet as pq
  load=self.load;q=load('timeout_quarantine');cap=load('capture');plan=load('plan');receipts=load('receipts')
  original=HERE.parent/'coverage-pass-residual-v1/passing-groups-2020-24/requests.json';orig=json.loads(original.read_bytes())
  state=json.loads((HERE/'exact-stop-certificate/before-ledger.json').read_bytes());cert=json.loads((HERE/'exact-stop-certificate/certificate.json').read_bytes())
  untouched=json.loads((HERE/'exact-stop-certificate/untouched-requests.json').read_bytes())
  pending=next(r for r in orig if r['request_id']==q.RID)
  completed=[plan.make_request('odds',plan.ts('2023-10-01T06:00:00Z'),books=['draftkings'],markets=load('mapping').MARKETS,event_id='synthetic'+str(i)) for i in range(11)]
  rows=completed+[pending]+untouched;policy=load('packet_builder').missing_policy(rows);policy['quote_policy']={'decimal_one':'retain_raw_non_executable'}
  folder=base/q.ROOT;folder.mkdir();(base/'registrations').mkdir();(folder/'receipts').mkdir()
  attempts={q.RID:dict(cache_key='05175510dc14de25e2ca',reserved_credits=60,status='pending')}
  for row in completed:
   body=dict(timestamp=row['requested_utc'],previous_timestamp='2023-10-01T05:55:00Z',next_timestamp='2023-10-01T06:05:00Z',data=dict(id=row['event_id'],sport_key=row['sport'],commence_time='2023-10-02T06:00:00Z',bookmakers=[]))
   record=dict(source=row['source'],url=row['url'],sport=row['sport'],cache_key=row['cache_key'],params_json=json.dumps(row['params']),http_status=200,body=json.dumps(body),headers_json=json.dumps({'x-requests-last':'60','x-requests-used':'660','x-requests-remaining':'4999340'}))
   raw=folder/'data/raw'/row['sport']/row['source']/row['requested_utc'][:10]/(row['cache_key']+'.parquet');raw.parent.mkdir(parents=True,exist_ok=True);pq.write_table(pa.Table.from_pylist([record]),raw)
   proof=dict(request_id=row['request_id'],response_sha256=cap.sha(raw),record=record,classification=receipts.classify(row,record,policy));receipt=folder/'receipts'/(row['request_id']+'.json');receipt.write_bytes(cap.canonical(proof))
   attempts[row['request_id']]=dict(status='completed',reserved_credits=60,billed_credits=60,send_started=True,response_path=str(raw),response_sha256=cap.sha(raw),receipt_sha256=cap.sha(receipt))
  state['attempts']=attempts;state['predecessor_snapshot']=cap.identity({'ledgers':{},'registrations':{}})
  ledger=folder/'spending-ledger.json';ledger.write_bytes(cap.canonical(state));init=folder/'INITIALIZED.json';init.write_bytes(cap.canonical({'bundle_root_sha256':q.ROOT,'probe_credits':1687}))
  marker=base/'registrations'/(q.ROOT+'.json');marker.write_bytes(cap.canonical({'bundle_root_sha256':q.ROOT,'authorization_sha256':state['authorization_sha256'],'runtime_path':str(folder)}))
  cert.update(ledger_sha256=cap.sha(ledger),marker_sha256=cap.sha(marker),initialization_sha256=cap.sha(init),attempted_ids=sorted(attempts),completed_ids=sorted(a for a in attempts if a!=q.RID),predecessor_snapshot_sha256=state['predecessor_snapshot'])
  return folder,rows,policy,cert,state

 def test_native_receipt_bills_and_exact_quarantine_adverse_cases(self):
  load=self.load;q=load('timeout_quarantine');cap=load('capture');native=load('prior_evidence')
  with tempfile.TemporaryDirectory(dir='/private/tmp') as d:
   folder,rows,policy,cert,state=self.fixture(Path(d));ledger=folder/'spending-ledger.json';before=ledger.read_bytes()
   with patch.object(q,'BEFORE',cert['ledger_sha256']),patch.object(q,'MARKER',cert['marker_sha256']),patch.object(q,'INIT',cert['initialization_sha256']):
    proof=q.verify(folder,rows,policy,cert,cap,native);self.assertEqual(proof['reserved'],720);self.assertEqual(proof['billed'],660);self.assertEqual(proof['conservative_carry'],208106)
    self.assertEqual(ledger.read_bytes(),before)
    for key,value in [('pending_reserved',0),('reserved',660),('billed',0),('conservative_carry',208046),('usable_quote',True),('no_resend',False),('completed_ids',[])]:
     with self.subTest(key=key),self.assertRaises(ValueError):q.verify(folder,rows,policy,dict(cert,**{key:value}),cap,native)
    for field,value in [('send_started',True),('billed_credits',0),('response_path','invented')]:
     bad=copy.deepcopy(state);bad['attempts'][q.RID][field]=value;ledger.write_bytes(cap.canonical(bad));pin=cap.sha(ledger)
     with patch.object(q,'BEFORE',pin),self.assertRaises(ValueError):q.verify(folder,rows,policy,dict(cert,ledger_sha256=pin),cap,native)
    ledger.write_bytes(before)
    rid=cert['completed_ids'][0];bad=copy.deepcopy(state);bad['attempts'][rid]['billed_credits']=0;ledger.write_bytes(cap.canonical(bad));pin=cap.sha(ledger)
    with patch.object(q,'BEFORE',pin),self.assertRaisesRegex(ValueError,'receipt classification'):q.verify(folder,rows,policy,dict(cert,ledger_sha256=pin),cap,native)
    ledger.write_bytes(before)
    orphan=folder/'receipts'/(q.RID+'.json');orphan.write_text('{}')
    with self.assertRaisesRegex(ValueError,'response/receipt'):q.verify(folder,rows,policy,cert,cap,native)
    orphan.unlink();(folder/'data/raw/unledgered.parquet').write_bytes(b'synthetic')
    with self.assertRaisesRegex(ValueError,'unledgered'):q.verify(folder,rows,policy,cert,cap,native)

 def test_exact_global_retirement_probe_once_unknown_and_other_pending_fail(self):
  load=self.load;q=load('timeout_quarantine');cap=load('capture');e=load('evidence');authority=load('timeout_authority')
  with tempfile.TemporaryDirectory(dir='/private/tmp') as d:
   base=Path(d);folder,rows,policy,cert,state=self.fixture(base);pin=cap.identity(cert)
   body=f"APPROVED offline pre-send quarantine: certificate {pin}, ledger {cert['ledger_sha256']}, pending {q.RID}, keep reserve 60, no resend";url='https://github.com/maxzipperman/value-finder/pull/151#issuecomment-1';approval=dict(comment_url=url,comment_body=body);installed=folder/'authority-timeout-retirement';installed.mkdir();(installed/'certificate.json').write_bytes(cap.canonical(cert));(installed/'approval.json').write_bytes(cap.canonical(approval))
   binding=dict(kind=cert['kind'],ledger_sha256=cert['ledger_sha256'],marker_sha256=cert['marker_sha256'],initialization_sha256=cert['initialization_sha256'],rows=rows,policy=policy,predecessor_snapshot=state['predecessor_snapshot'],authorization_sha256=state['authorization_sha256'],plan_sha256=q.ROOT,reconciliation=dict(certificate=cert,certificate_sha256=pin,approval_path=str(installed/'approval.json')))
   baseline={'ledgers':{},'registrations':{}};verify=lambda *a:(baseline,{'cumulative_debit_without_probe':205699});live=dict(html_url=url,body=body,user={'login':'maxzipperman'})
   with patch.object(q,'BEFORE',cert['ledger_sha256']),patch.object(q,'MARKER',cert['marker_sha256']),patch.object(q,'INIT',cert['initialization_sha256']),patch.object(authority,'fetch_live_comment',lambda _:live):
    snap,carry=e.global_union(base,baseline,{q.ROOT:binding},verify);self.assertEqual(carry,dict(conservative_debit=208106,probe_counted_once=1687));self.assertEqual(snap['ledgers'],{q.ROOT:cert['ledger_sha256']})
    wrong=dict(binding,kind='other_pending')
    with self.assertRaises(ValueError):e.global_union(base,baseline,{q.ROOT:wrong},verify)
    changed=dict(cert,pending_reserved=0);(installed/'certificate.json').write_bytes(cap.canonical(changed))
    with self.assertRaises(ValueError):e.global_union(base,baseline,{q.ROOT:binding},verify)
    (installed/'certificate.json').write_bytes(cap.canonical(cert));unknown=base/'unknown';unknown.mkdir();(unknown/'INITIALIZED.json').write_text('{}')
    with self.assertRaises(ValueError):e.global_union(base,baseline,{q.ROOT:binding},verify)

 def test_actual_successor_packet_mutations_fail_closed(self):
  load=self.load;boot=load('bootstrap');folder=HERE/'untouched-successor-final';root=json.loads((folder/'FREEZE.json').read_bytes())['root']
  v,_,data,source,_=boot.verified(folder,root);result=v.packet(data,source);self.assertEqual(result['requests'],1290);self.assertEqual(result['max_new_credits'],66480)
  for name,value in [('requests.json',json.loads(data['requests.json'])[:-1]),('mappings.json',json.loads(data['mappings.json'])[:-1]),('denominators.json',[]),('policy.json',dict(json.loads(data['policy.json']),max_missing={'snapshot_lag':99999,'event_not_found':99999})),('manifest.json',dict(json.loads(data['manifest.json']),max_new_credits=66481)),('execution-protocol.json',dict(json.loads(data['execution-protocol.json']),automatic_retries=1)),('recovery/certificate.json',dict(json.loads(data['recovery/certificate.json']),no_resend=False))]:
   changed=dict(data);changed[name]=boot.canonical(value)
   with self.subTest(name=name),self.assertRaises(ValueError):v.packet(changed,source)
  changed=dict(data);changed['dependency-paths.json']=boot.canonical(dict(json.loads(data['dependency-paths.json']),f2_gate='/private/tmp/fabricated/f2_handoff.py'))
  with self.assertRaises(ValueError):boot.load_modules(REPO,changed,source)
  with tempfile.TemporaryDirectory(dir='/private/tmp') as d:
   import shutil
   dst=Path(d)/'packet';shutil.copytree(folder,dst);(dst/'unexpected').write_text('extra')
   with self.assertRaises(ValueError):boot.verified(dst,root)

if __name__=='__main__':unittest.main()
