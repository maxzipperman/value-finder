"""Read-only exact certificate preparation. Hub installs metadata separately."""
import argparse
import hashlib
import json
from pathlib import Path
import types
import fcntl
import os

ROOT='c75ef924f5d44c62176de915f47744515f2ca35088f2a82e507a105c0733bacb'
BOOT='48ba33f06b02c1024d49f2758ddd3a5106fcc34ab6c0f09420e71c6407d41213'

def module(raw,path,name):
 m=types.ModuleType(name);m.__file__=str(path);exec(compile(raw,str(path),'exec'),m.__dict__);return m

def prepare(a):
 old=Path(a.old_packet);cfg=json.loads((old/'config.json').read_bytes());path=Path(cfg['repo'])/'strategy-research/coverage-pass-execution-v1/bootstrap.py';raw=path.read_bytes()
 if hashlib.sha256(raw).hexdigest()!=BOOT:raise ValueError('original reviewed bootstrap differs')
 boot=module(raw,path,'stopped_pass150_bootstrap');runner,base,data,source,load=boot.verified(old,ROOT)
 capture=load('capture');evidence=load('evidence');builder=load('packet_builder');repo,out=builder.validate_output(a.repo,a.output)
 qpath=Path(__file__).parent/'quarantine.py';qraw=boot.regular(qpath);q=module(qraw,qpath,'exact_timeout_quarantine')
 own=boot.regular(Path(__file__))
 with (base.RUNTIME_BASE/'followup-purchase.lock').open('rb') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  folder=base.RUNTIME_BASE/ROOT;before=boot.regular(folder/'spending-ledger.json');state=json.loads(before);rows=json.loads(data['requests.json'])
  if hashlib.sha256(before).hexdigest()!=q.BEFORE:raise ValueError('exact stop ledger differs')
  untouched=[r for r in rows if r['request_id'] not in state['attempts']]
  cert=dict(version=1,kind='exact_pre_send_authority_timeout_retirement',source_root=ROOT,ledger_sha256=q.BEFORE,marker_sha256=q.MARKER,initialization_sha256=q.INIT,quarantined_request_id=q.RID,attempted_ids=sorted(state['attempts']),completed_ids=sorted(rid for rid,a in state['attempts'].items() if a['status']=='completed'),untouched_ids=sorted(r['request_id'] for r in untouched),request_list_sha256=capture.identity(untouched),untouched_count=1290,untouched_cap=66480,reserved=720,billed=660,conservative_carry=208106,pending_reserved=60,journal_unchanged=True,no_resend=True,no_response_or_receipt_fabricated=True,usable_quote=False,next_purchase_authorized=False,original_request_list_sha256=capture.digest(data['requests.json']),original_mappings_sha256=capture.digest(data['mappings.json']),original_packet_root=ROOT,predecessor_snapshot_sha256=state['predecessor_snapshot'],code_sha256={'prepare.py':capture.digest(own),'quarantine.py':capture.digest(qraw)},retirement_policy='original root remains halted/pending; exactcertificate permits only1290neverattempted successor')
  q.verify(folder,rows,json.loads(data['policy.json']),cert,capture,evidence)
  expected=json.loads(data['baseline.json']);baseline=load('baseline')
  def check(ledgers,markers):return baseline.verify_base(ledgers,markers,expected['base_snapshot'],source['request-manifest.json'],expected['historical_bindings'])
  snap,carry=evidence.global_union(base.RUNTIME_BASE,expected['base_snapshot'],expected['pilot_bindings'],check,active_root=ROOT,active_verifier=lambda:q.verify(folder,rows,json.loads(data['policy.json']),cert,capture,evidence))
  if snap!=expected['expected_global_snapshot'] or carry['conservative_debit']!=207386:raise ValueError('historical predecessor differs')
  cert['predecessor_snapshot_sha256']=capture.identity(snap)
  projected,mappings=q.selection(rows,json.loads(data['mappings.json']),state)
  if projected!=untouched:raise ValueError('selection projection differs')
  if boot.regular(folder/'spending-ledger.json')!=before or boot.regular(qpath)!=qraw or boot.regular(Path(__file__))!=own:raise ValueError('preparation source/state changed')
  _,_,again,shared,_=boot.verified(old,ROOT)
  if again!=data or shared!=source:raise ValueError('original closure changed')
  out.mkdir(mode=0o700)
  objects={'certificate.json':cert,'untouched-requests.json':untouched,'successor-mappings.json':mappings,'before-ledger.json':state,'baseline-source.json':expected}
  for name,obj in objects.items():
   raw=before if name=='before-ledger.json' else boot.canonical(obj)
   with (out/name).open('xb') as h:h.write(raw);h.flush();os.fsync(h.fileno())
  base.durable_directory(out)
  return dict(certificate_sha256=capture.identity(cert),untouched_count=1290,untouched_cap=66480,conservative_carry=208106,journal_unchanged=True,paid_calls=0,runtime_writes=0)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--repo',type=Path,required=True);p.add_argument('--old-packet',type=Path,required=True);p.add_argument('--output',type=Path,required=True);print(json.dumps(prepare(p.parse_args()),sort_keys=True))
