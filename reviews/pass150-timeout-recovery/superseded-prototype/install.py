"""Explicit hub-only metadata adoption; never clears or edits stopped journal.

Worker preparation does not call this. Partial metadata installation is blocked
for separately reviewed reconciliation; no automatic cleanup or replacement.
"""
import argparse
import fcntl
import json
import os
from pathlib import Path
import types

def install(a):
 import sys
 if not a.confirm_hub_install or not sys.flags.isolated or not sys.dont_write_bytecode:raise ValueError('isolated explicit hub-only certificate installation required')
 path=Path(__file__).parent/'bootstrap.py';raw=path.read_bytes()
 import hashlib
 if hashlib.sha256(raw).hexdigest()!=a.bootstrap_sha256:raise ValueError('reviewed bootstrap differs')
 boot=types.ModuleType('hub_metadata_bootstrap');boot.__file__=str(path);exec(compile(raw,str(path),'exec'),boot.__dict__)
 _,base,data,source,load=boot.verified(a.packet,a.root);q=load('timeout_quarantine');capture=load('capture');old=load('runner').original(data)
 cert=json.loads(data['recovery/certificate.json']);approval=json.loads(boot.regular(a.approval));binding=dict(certificate=cert,certificate_sha256=capture.identity(cert),approval=approval)
 folder=base.RUNTIME_BASE/q.ROOT;target=folder/'authority-timeout-retirement'
 with (base.RUNTIME_BASE/'followup-purchase.lock').open('rb') as shared, (folder/'acquisition.lock').open('rb') as local:
  fcntl.flock(shared,fcntl.LOCK_EX|fcntl.LOCK_NB);fcntl.flock(local,fcntl.LOCK_EX|fcntl.LOCK_NB)
  before=capture.regular(folder/'spending-ledger.json')
  q.verify(folder,json.loads(old['requests.json']),json.loads(old['policy.json']),cert,capture,load('prior_evidence'))
  q.verify_approval(binding,fetch=load('timeout_authority').fetch_live_comment)
  _,_,again,shared_source,_=boot.verified(a.packet,a.root)
  if again!=data or shared_source!=source or capture.regular(folder/'spending-ledger.json')!=before:raise ValueError('source/stop changed before adoption')
  if target.exists():
   if target.is_symlink() or {p.name for p in target.iterdir()}!={'certificate.json','approval.json'} or capture.regular(target/'certificate.json')!=boot.canonical(cert) or capture.regular(target/'approval.json')!=boot.canonical(approval):raise ValueError('partial/different adoption requires reviewed reconciliation')
  else:
   target.mkdir(mode=0o700)
   for name,obj in [('certificate.json',cert),('approval.json',approval)]:
    fd=os.open(target/name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'wb') as h:h.write(boot.canonical(obj));h.flush();os.fsync(h.fileno())
   base.durable_directory(target);base.durable_directory(folder)
  if capture.regular(folder/'spending-ledger.json')!=before:raise ValueError('stopped journal changed; halt')
  return dict(installed_certificate_sha256=capture.identity(cert),journal_unchanged=True,reservations_unchanged=720,pending_reserved=60,paid_authority=False,paid_calls=0)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--packet',type=Path,required=True);p.add_argument('--root',required=True);p.add_argument('--approval',type=Path,required=True);p.add_argument('--bootstrap-sha256',required=True);p.add_argument('--confirm-hub-install',action='store_true');print(json.dumps(install(p.parse_args()),sort_keys=True))
