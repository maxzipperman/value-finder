"""Offline execution packet assembly/preflight; metadata only, no authority/keys."""
import argparse
import fcntl
import json
from pathlib import Path
import types
import os


def assemble(a):
 here=Path(__file__).parent;boot_raw=(here/'bootstrap.py').read_bytes()
 import hashlib
 if hashlib.sha256(boot_raw).hexdigest()!=a.bootstrap_sha256:raise ValueError('reviewed bridge bootstrap differs')
 boot=types.ModuleType('bulk_assembler_bootstrap');boot.__file__=str(here/'bootstrap.py');exec(compile(boot_raw,boot.__file__,'exec'),boot.__dict__)
 data,source,oldload=boot.inputs(a.repo,a.preparation,a.final_record);load=boot.load_modules(a.repo,data,source)
 capture=load('capture');base=load('executor');prep=load('preparation');builder=load('packet_builder')
 # validate_output rejects existing paths, runtime/live roots and symlink traversal.
 repo,out=builder.validate_output(a.repo,a.output)
 if base.current_runtime()!=json.loads(source['runtime-lock.json']):raise ValueError('reviewed runtime differs')
 final=json.loads(data['final-record.json']);snapshot=final['proof']['global_snapshot']
 with (base.RUNTIME_BASE/'followup-purchase.lock').open('rb') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  prep.verify_snapshot(base.RUNTIME_BASE,snapshot,capture)
  old=json.loads(data['original-pilot-baseline.json']);pilotroot=final['fingerprint']['root'];runtime=base.RUNTIME_BASE/pilotroot
  state=capture.read(runtime/'spending-ledger.json')
  binding=dict(ledger_sha256=capture.sha(runtime/'spending-ledger.json'),marker_sha256=capture.sha(base.RUNTIME_BASE/'registrations'/(pilotroot+'.json')),initialization_sha256=capture.sha(runtime/'INITIALIZED.json'),rows=json.loads(data['original-pilot-requests.json']),policy=json.loads(data['original-pilot-policy.json']),predecessor_snapshot=state['predecessor_snapshot'],authorization_sha256=state['authorization_sha256'],plan_sha256=pilotroot)
  baseline=dict(old,pilot_bindings=dict(old['pilot_bindings'],**{pilotroot:binding}),expected_global_snapshot=snapshot)
  history=json.loads(data['preparation/history-proof.json']);overlap=json.loads(data['overlap.json'])
  overlap.update(raw_roots=history['raw_roots'],inventory_sha256=history['raw_inventory_sha256'])
  cfg=json.loads(source['protocol.json']);cfg['budgets']=json.loads(data['future-budget-policy.json'])['budgets']
  m=json.loads(data['preparation/manifest.json']);m=dict(m,request_set_sha256=capture.identity(json.loads(data['requests.json'])))
  config=dict(repo=str(repo),preparation=str(Path(a.preparation).absolute()),final_record=str(Path(a.final_record).absolute()),restart_policy=dict(allowed=['prepared','running','pilot_clean_pause'],pending='block_no_resend',stopped='block_reconciliation',terminal='exhausted',automatic_retries=0,automatic_redirects=0))
  objects={'config.json':config,'manifest.json':m,'baseline.json':baseline,'overlap.json':overlap,'execution-protocol.json':cfg}
  data.update({n:boot.canonical(obj) for n,obj in objects.items()});data['protocol.json']=boot.canonical({'execution_status':'reviewed_for_execution'})
  load=boot.load_modules(repo,data,source);load('runner').packet(data,source)
  # Receipt/raw hashes + terminal metadata only. Global live certificate/approval
  # authentication occurs again in hub orchestration; no network in this preflight.
  load('runner').residual(data,source,load,base.RUNTIME_BASE,snapshot)
  load('evidence').authenticate_reuse(base.RUNTIME_BASE,snapshot,json.loads(data['mappings.json']),frozen_source={'freeze':data['source/FREEZE.json'],'files':source})
  load('overlap').check(json.loads(data['requests.json']),overlap['raw_roots'],expected_inventory_sha256=overlap['inventory_sha256'])
  prep.verify_snapshot(base.RUNTIME_BASE,snapshot,capture)
  again,shared,_=boot.inputs(repo,a.preparation,a.final_record)
  if any(again[n]!=v for n,v in data.items() if n not in boot.PHYSICAL|{'protocol.json'}) or shared!=source:raise ValueError('source changed during offline preflight')
  files={n:boot.sha(v) for n,v in data.items()};root=capture.identity(files)
  out.mkdir(mode=0o700)
  for name,raw in {**{n:data[n] for n in boot.PHYSICAL},'FREEZE.json':boot.canonical(dict(root=root,files=files,scope='prospective_bulk_execution_captured_closure'))}.items():
   with (out/name).open('xb') as h:h.write(raw);h.flush();os.fsync(h.fileno())
  base.durable_directory(out)
  boot.verified(out,root)
  return dict(root=root,request_count=1302,max_new_credits=67200,conservative_carry=207386,paid_authority=False,offline_preflight=True,live_account_verified=False,runtime_writes=0,paid_calls=0)


if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--repo',type=Path,required=True);p.add_argument('--preparation',type=Path,required=True);p.add_argument('--final-record',type=Path,required=True);p.add_argument('--bootstrap-sha256',required=True);p.add_argument('--output',type=Path,required=True);print(json.dumps(assemble(p.parse_args()),sort_keys=True))
