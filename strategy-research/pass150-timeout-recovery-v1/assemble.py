"""Read-only successor construction under the existing lock; no registration."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import types

def assemble(a):
 path=Path(__file__).parent/'bootstrap.py';raw=path.read_bytes()
 import hashlib
 if hashlib.sha256(raw).hexdigest()!=a.bootstrap_sha256:raise ValueError('reviewed successor bootstrap differs')
 boot=types.ModuleType('successor_assembler_bootstrap');boot.__file__=str(path);exec(compile(raw,str(path),'exec'),boot.__dict__)
 data,source=boot.inputs(a.repo,a.old_packet,a.proposal);load=boot.load_modules(a.repo,data,source)
 base=load('executor');capture=load('capture');v=load('runner');q=load('timeout_quarantine');evidence=load('prior_evidence');baseline=load('baseline')
 repo,out=load('packet_builder').validate_output(a.repo,a.output)
 if base.current_runtime()!=json.loads(source['runtime-lock.json']):raise ValueError('reviewed runtime differs')
 with (base.RUNTIME_BASE/'followup-purchase.lock').open('rb') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  old=v.original(data);bindings=json.loads(old['baseline.json']);cert=json.loads(data['recovery/certificate.json'])
  def stopped():return q.verify(base.RUNTIME_BASE/q.ROOT,json.loads(old['requests.json']),json.loads(old['policy.json']),cert,capture,evidence)
  stopped()
  def check(ledgers,markers):return baseline.verify_base(ledgers,markers,bindings['base_snapshot'],source['request-manifest.json'],bindings['historical_bindings'])
  snap,carry=evidence.global_union(base.RUNTIME_BASE,bindings['base_snapshot'],bindings['pilot_bindings'],check,active_root=q.ROOT,active_verifier=stopped)
  if snap!=bindings['expected_global_snapshot'] or carry['conservative_debit']!=207386 or cert['predecessor_snapshot_sha256']!=capture.identity(snap):raise ValueError('original global history differs')
  rows,maps,cells,m,successor_baseline,cfg,roots=v.objects(data,base.RUNTIME_BASE)
  inventory={}
  for root in roots:
   root=Path(root)
   for sport in ('americanfootball_nfl','americanfootball_ncaaf'):
    for family in ('oddsapi/hist_odds','oddsapi/hist_event_odds','oddsapi/hist_event_markets'):
     for p in (root/sport/family).glob('*/*.parquet'):
      if '2020-01-01'<=p.parent.name<'2026-02-10':inventory[str(p)]=capture.sha(p)
  cache=dict(json.loads(old['overlap.json']),raw_roots=roots,inventory_sha256=capture.identity(inventory))
  config=dict(repo=str(repo),old_packet=str(Path(a.old_packet).absolute()),proposal=str(Path(a.proposal).absolute()),retired_root=q.ROOT,restart_policy=dict(allowed=['prepared','running','pilot_clean_pause'],pending='block_no_resend',stopped='block_reconciliation',terminal='exhausted',automatic_retries=0,automatic_redirects=0))
  objects={'config.json':config,'manifest.json':m,'baseline.json':successor_baseline,'overlap.json':cache,'execution-protocol.json':cfg}
  data.update({n:boot.canonical(obj) for n,obj in objects.items()});data['protocol.json']=boot.canonical({'execution_status':'reviewed_for_execution'})
  v.packet(data,source);v.residual(data,source,load,base.RUNTIME_BASE,successor_baseline['expected_global_snapshot'])
  evidence.authenticate_reuse(base.RUNTIME_BASE,successor_baseline['expected_global_snapshot'],maps,frozen_source={'freeze':data['source/FREEZE.json'],'files':source})
  load('overlap').check(rows,roots,expected_inventory_sha256=cache['inventory_sha256'])
  stopped();again,shared=boot.inputs(repo,a.old_packet,a.proposal)
  if shared!=source or any(again[n]!=raw for n,raw in data.items() if n not in boot.PHYSICAL|{'protocol.json'}):raise ValueError('captured source changed during preparation')
  files={n:boot.sha(raw) for n,raw in data.items()};root=capture.identity(files)
  out.mkdir(mode=0o700)
  for n,raw in {**{n:data[n] for n in boot.PHYSICAL},'FREEZE.json':boot.canonical(dict(root=root,files=files,scope='exact_immutable_timeout_successor'))}.items():
   with (out/n).open('xb') as h:h.write(raw);h.flush();os.fsync(h.fileno())
  base.durable_directory(out);boot.verified(out,root)
  return dict(root=root,certificate_sha256=capture.identity(cert),request_list_sha256=m['request_list_sha256'],request_count=1290,max_new_credits=66480,conservative_carry=208106,first_tranche_ceiling=274686,paid_authority=False,runtime_writes=0,paid_calls=0,offline_preflight=True,installation_required=True)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--repo',type=Path,required=True);p.add_argument('--old-packet',type=Path,required=True);p.add_argument('--proposal',type=Path,required=True);p.add_argument('--bootstrap-sha256',required=True);p.add_argument('--output',type=Path,required=True);print(json.dumps(assemble(p.parse_args()),sort_keys=True))
