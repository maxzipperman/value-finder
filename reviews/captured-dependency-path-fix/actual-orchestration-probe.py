"""Actual orchestration proof with per-instance guards and runtime-write denial.

Future successor authority is fixture ONLY. Every historical/global/nested/cache
verification runs unchanged. Existing GitHub approvals are authenticated live.
Registration, Ledger construction, key and Odds HTTP are forbidden. Never rerun
until the hub has restored the exact historical inventory after failed05904probe.
"""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import sys
from unittest.mock import patch
HERE=Path(__file__).resolve().parents[2]
s=importlib.util.spec_from_file_location('actual_bulk_probe',HERE/'strategy-research/coverage-pass-execution-v1/bootstrap.py');b=importlib.util.module_from_spec(s);s.loader.exec_module(b)
p=argparse.ArgumentParser();p.add_argument('--packet',type=Path,required=True);p.add_argument('--root',required=True);a=p.parse_args();ROOT=a.root;PACKET=a.packet
runner,base,data,source,load=b.verified(PACKET,ROOT);runtime=base.runtime_path(ROOT);store=base.RUNTIME_BASE
assert not runtime.exists();assert not (store/'registrations'/(ROOT+'.json')).exists()
seen=[];guarded=[]
class RegistrationBoundary(Exception):pass
class RuntimeWriteBlocked(Exception):pass

def is_runtime(path):
 try:return Path(os.fsdecode(path)).resolve().is_relative_to(store.resolve())
 except (TypeError,ValueError):return False

def deny_runtime_writes(event,args):
 if event=='open' and is_runtime(args[0]):
  flags=args[2] or 0
  if flags&(os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND):
   # Actual orchestration opens the existing sharedlock before proof. No writes
   # to its bytes are performed; registration.lock is NOT exempt.
   if Path(args[0]).absolute()==store/'followup-purchase.lock' and (store/'followup-purchase.lock').is_file():return
   raise RuntimeWriteBlocked('runtime writable open forbidden')
 elif event in {'os.mkdir','os.remove','os.rmdir','os.rename','os.chmod','os.utime','os.link','os.symlink'} and any(is_runtime(v) for v in args[:2]):raise RuntimeWriteBlocked('runtime mutation forbidden')

sys.addaudithook(deny_runtime_writes)

def forbidden(name):
 def stop(*a,**k):seen.append(name);raise AssertionError('Forbidden probe action:'+name)
 return stop

def stop_registration(*a,**k):seen.append('registration_boundary');raise RegistrationBoundary()

class ForbiddenLedger:
 def __init__(self,*a,**k):forbidden('ledger')()

def future_authority_fixture(base,auth,manifest,root,commit,context):
 assert root==ROOT and manifest['max_new_credits']==67200 and manifest['request_count']==1302
 assert set(context)=={'policy_sha256','plan_sha256','global_snapshot_sha256','historical_bindings_sha256','cache_union_sha256','captured_closure_sha256'} and context['plan_sha256']==ROOT
 seen.append('future_authority_fixture')

m=load('orchestration');real_verified=m.bootstrap.verified

def guarded_verified(*args,**kwargs):
 result=real_verified(*args,**kwargs);fresh=result[1]
 fresh.register_runtime=stop_registration;fresh.Ledger=ForbiddenLedger
 guarded.append(id(fresh))
 return result

try:
 with patch.object(m.bootstrap,'verified',guarded_verified),patch.object(m.authority,'check',future_authority_fixture):
  try:m.run(PACKET,ROOT,None,{'offline_fixture':'no_paid_authority'},key_factory=forbidden('key'),http_factory=forbidden('odds_http'))
  except RegistrationBoundary:pass
  else:raise AssertionError('Registration boundary not reached')
 assert seen[-1]=='registration_boundary' and not {'key','odds_http','ledger'}&set(seen)
 assert len(set(guarded))>=2 # every new verified executor received hard blockers
 assert not runtime.exists();assert not (store/'registrations'/(ROOT+'.json')).exists()
 result=dict(root=ROOT,status='actual_orchestration_reached_registration_boundary',calls=seen,guarded_verified_instances=len(guarded),runtime_write_deny_hook=True,historical_verification='unchanged native proof, historical GitHub approvals authenticated live',future_authority='fixture only; exact live successor authority required',runtime_created=False,registration_created=False,credentials_read=False,odds_http_calls=0)
except Exception as e:
 result=dict(root=ROOT,status='failed_guarded_probe',exception_type=type(e).__name__,message=str(e),calls=seen,guarded_verified_instances=len(guarded),runtime_write_deny_hook=True)
 (Path(__file__).parent/'actual-orchestration-evidence.json').write_text(json.dumps(result,indent=2)+'\n')
 raise
(Path(__file__).parent/'actual-orchestration-evidence.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
