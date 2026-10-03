"""Prospective captured successor; old executed freeze remains untouched.

Original proof closure is independently pinned and revalidated, with explicit
real paths retained. This new namespace alone admits the exact retired epoch.
Default verification performs no writes or provider/credential access.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import types

ROOT='c75ef924f5d44c62176de915f47744515f2ca35088f2a82e507a105c0733bacb'
OLD_BOOT='48ba33f06b02c1024d49f2758ddd3a5106fcc34ab6c0f09420e71c6407d41213'
PHYSICAL={'config.json','manifest.json','baseline.json','overlap.json','execution-protocol.json'}
PROPOSAL={'certificate.json','untouched-requests.json','successor-mappings.json','before-ledger.json','baseline-source.json'}
OWN={'bootstrap':'bootstrap.py','runner':'validator.py','orchestration':'orchestration.py','evidence':'evidence.py','authority':'authority.py','execution':'execution.py','timeout_quarantine':'quarantine.py','timeout_authority':'authority.py'}
EXECUTABLES=set(OWN.values())|{'prepare.py','install.py','assemble.py'}

def canonical(obj):return json.dumps(obj,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def sha(raw):return hashlib.sha256(raw).hexdigest()
def regular(path):
 path=Path(path).absolute()
 if any(p.is_symlink() for p in (path,*path.parents)):raise ValueError('symlink capture')
 fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
 try:
  if not stat.S_ISREG(os.fstat(fd).st_mode):raise ValueError('regular capture required')
  with os.fdopen(fd,'rb',closefd=False) as h:return h.read()
 finally:os.close(fd)

def original(packet):
 packet=Path(packet).absolute();cfg=json.loads(regular(packet/'config.json'))
 path=Path(cfg['repo'])/'strategy-research/coverage-pass-execution-v1/bootstrap.py';raw=regular(path)
 if sha(raw)!=OLD_BOOT:raise ValueError('original reviewed bootstrap differs')
 boot=types.ModuleType('original_stopped_bootstrap');boot.__file__=str(path);exec(compile(raw,str(path),'exec'),boot.__dict__)
 _,_,data,source,load=boot.verified(packet,ROOT)
 return data,source,load

def inputs(repo,old_packet,proposal):
 repo=Path(repo).absolute();proposal=Path(proposal).absolute()
 old,source,load=original(old_packet)
 if {p.name for p in proposal.iterdir()}!=PROPOSAL:raise ValueError('certificate proposal inventory differs')
 here=repo/'strategy-research/pass150-timeout-recovery-v1'
 if {p.name for p in here.glob('*.py') if not p.name.startswith('test')}!=EXECUTABLES:raise ValueError('successor executable inventory differs')
 proof={n:regular(proposal/n) for n in PROPOSAL};cert=json.loads(proof['certificate.json'])
 if sha(proof['before-ledger.json'])!=cert['ledger_sha256'] or proof['baseline-source.json']!=old['baseline.json']:raise ValueError('certificate before/baseline pin differs')
 for n,pin in cert['code_sha256'].items():
  if n not in {'prepare.py','quarantine.py'} or sha(regular(here/n))!=pin:raise ValueError('certificate preparation code changed')
 if set(cert['code_sha256'])!={'prepare.py','quarantine.py'}:raise ValueError('certificate code scope incomplete')
 # Preserve original logical bytes separately, rather than rewriting a freeze.
 data={'original-bulk/'+n:v for n,v in old.items()}
 data.update(old);data.update({'recovery/'+n:v for n,v in proof.items()})
 paths=json.loads(old['dependency-paths.json'])
 for key in ('evidence','authority','runner'):
  data['code/prior_'+key+'.py']=old['code/'+key+'.py'];paths['prior_'+key]=paths[key]
 for key,n in OWN.items():data['code/'+key+'.py']=regular(here/n);paths[key]=str(here/n)
 for n in ('prepare.py','install.py','assemble.py'):data['recovery-code/'+n]=regular(here/n)
 data['dependency-paths.json']=canonical(paths)
 data['requests.json']=proof['untouched-requests.json'];data['mappings.json']=proof['successor-mappings.json']
 rows=json.loads(data['requests.json'])
 data['cell-allowlist.json']=canonical(load('preparation').cell_rectangles(rows))
 policy=load('packet_builder').missing_policy(rows);policy['quote_policy']={'decimal_one':'retain_raw_non_executable'}
 data['policy.json']=canonical(policy)
 return data,source

def load_modules(repo,data,source):
 paths={n:Path(p) for n,p in json.loads(data['dependency-paths.json']).items()}
 own=Path(repo).absolute()/'strategy-research/pass150-timeout-recovery-v1'
 if any(paths.get(k)!=own/n for k,n in OWN.items()):raise ValueError('successor real module path differs')
 original_paths=json.loads(data['original-bulk/dependency-paths.json'])
 expected=dict(original_paths)
 for k in ('evidence','authority','runner'):expected['prior_'+k]=original_paths[k]
 expected.update({k:str(own/n) for k,n in OWN.items()})
 if {k:str(v) for k,v in paths.items()}!=expected:raise ValueError('dependency alias inventory differs')
 modules={n[5:-3]:v for n,v in data.items() if n.startswith('code/') and n.endswith('.py')}
 original_repo=Path(json.loads(data['original-bulk/config.json'])['repo'])
 for n,v in source.items():
  if not n.endswith('.py'):continue
  key=(n[:-12] if n.endswith('/__init__.py') else n[:-3]).replace('/','.')
  if key in modules:raise ValueError('source module collision')
  modules[key]=v;paths[key]=original_repo/'strategy-research/football_archive/acquisition/football-archive-v4'/n
 cap=types.ModuleType('successor_capture');cap.__file__=str(paths['capture']);exec(compile(modules['capture'],cap.__file__,'exec'),cap.__dict__)
 return cap.closed_modules(modules,paths)

def verified(packet,root,bundle=None):
 packet=Path(packet).absolute();freeze=json.loads(regular(packet/'FREEZE.json'))
 if freeze['root']!=root or sha(canonical(freeze['files']))!=root or {p.name for p in packet.iterdir()}!=PHYSICAL|{'FREEZE.json'}:raise ValueError('successor physical inventory/root differs')
 config=json.loads(regular(packet/'config.json'))
 if set(config)!={'repo','old_packet','proposal','retired_root','restart_policy'} or config['retired_root']!=ROOT or config['restart_policy']!=dict(allowed=['prepared','running','pilot_clean_pause'],pending='block_no_resend',stopped='block_reconciliation',terminal='exhausted',automatic_retries=0,automatic_redirects=0):raise ValueError('successor configuration differs')
 data,source=inputs(config['repo'],config['old_packet'],config['proposal'])
 data.update({n:regular(packet/n) for n in PHYSICAL});data['protocol.json']=canonical({'execution_status':'reviewed_for_execution'})
 if {n:sha(v) for n,v in data.items()}!=freeze['files']:raise ValueError('successor captured closure differs')
 load=load_modules(config['repo'],data,source);load('runner').packet(data,source)
 return load('runner'),load('executor'),data,source,load

if __name__=='__main__':
 import sys
 p=argparse.ArgumentParser();p.add_argument('--packet',type=Path,required=True);p.add_argument('--root',required=True);p.add_argument('--authorization',type=Path);p.add_argument('--key-file',type=Path);p.add_argument('--confirm-paid',action='store_true');a=p.parse_args()
 try:
  runner,base,data,source,load=verified(a.packet,a.root)
  if not a.confirm_paid:print(json.dumps(runner.packet(data,source)))
  else:
   if not sys.flags.isolated or not sys.dont_write_bytecode or not a.authorization or not a.key_file:raise ValueError('isolated explicit hub paid authority/key required')
   auth=json.loads(regular(a.authorization))
   def key():
    from dotenv import dotenv_values
    return dotenv_values(a.key_file).get('ODDS_API_KEY')
   def http():return load('archive_markets.http').new_session()
   print(json.dumps(load('orchestration').run(a.packet,a.root,None,auth,key_factory=key,http_factory=http)))
 except BaseException:raise SystemExit('STOPPED: retain reservations/evidence; never automatically retry or recover') from None
