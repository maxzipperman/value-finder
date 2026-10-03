"""Captured bulk bootstrap. Offline default; hub-only isolated paid CLI."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import types

PREP_ROOT='22c546ed08e0b9f52037dd17c0c90be707d0804e5d68be66c046730639ba8f40'
FINAL_SHA='100a53275119fba283b3e8938cfee994f0d1a535201f2bab2e8769bfba9fdbdb'
REPORT_SHA='2370ab54c14fc491d9e9b35f9ac929b687c159059aff7ed8aff8f82512f20691'
BUILDER_SHA='12e87e644b5243ff7854ed4457291438df902efc4afdfb436dba5caa63a9845e'
PREP_FILES={'manifest.json','future-budget-policy.json','requests.json','cell-allowlist.json','mappings.json','denominators.json','history-proof.json','held-exclusions.json','response-policy.json'}
PHYSICAL={'config.json','manifest.json','baseline.json','overlap.json','execution-protocol.json'}


def regular(path):
 path=Path(path).absolute()
 if any(p.is_symlink() for p in (path,*path.parents)):raise ValueError('symlink capture')
 fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
 try:
  if not stat.S_ISREG(os.fstat(fd).st_mode):raise ValueError('regular capture required')
  with os.fdopen(fd,'rb',closefd=False) as h:return h.read()
 finally:os.close(fd)


def canonical(obj):return json.dumps(obj,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def sha(raw):return hashlib.sha256(raw).hexdigest()
def module(raw,path,name,pin):
 if sha(raw)!=pin:raise ValueError('external source pin differs')
 m=types.ModuleType(name);m.__file__=str(path);exec(compile(raw,str(path),'exec'),m.__dict__);return m


def module_paths(repo,names):
 repo=Path(repo).absolute();parent=repo/'strategy-research';pilot=parent/'coverage-pilot-v1';here=parent/'coverage-pass-execution-v1'
 old={'planner','bounds','timing','mapping','receipts','baseline','evidence','transport','authority','classifier','execution','certainty','overlap','frame_binding','quarantine'}
 paths={n:pilot/(n+'.py') for n in old}
 paths.update(capture=parent/'football-metadata-v1/capture.py',history=parent/'football-metadata-v1/history.py',plan=parent/'nfl-props-archive-v1/plan.py',f2_gate=parent/'football_archive/f2_handoff.py',older_recovery=parent/'football_archive/older-recovery-v1/recovery.py',preparation=parent/'coverage-pass-residual-v1/build.py',packet_builder=parent/'coverage-pilot-packet-v1/build.py',completion_report=parent/'coverage-pilot-completion-v1/report.py',bootstrap=here/'bootstrap.py',runner=here/'validator.py',orchestration=here/'orchestration.py',assembler=here/'assemble.py')
 if set(names)!=set(paths):raise ValueError('undeclared captured module path')
 return paths


def nested_union_inputs(gate):
 path=gate.UNION_BOOTSTRAP_PATH;packet=gate.UNION_PACKET_PATH
 raw=regular(path)
 if sha(raw)!=gate.UNION_BOOTSTRAP_SHA256:raise ValueError('nested union bootstrap changed')
 cert=json.loads(regular(packet/'FREEZE.json'))
 files={n:regular(packet.parent/n[5:] if n.startswith('code/') else packet/n) for n in cert['files']}
 if cert!={'root':gate.UNION_PACKET_ROOT,'files':{n:sha(v) for n,v in files.items()}} or sha(canonical(cert['files']))!=gate.UNION_PACKET_ROOT:raise ValueError('nested union closure differs')
 # Exact nested inventory matches the independently pinned union bootstrap rule.
 actual={'code/'+p.name for p in packet.parent.glob('*.py')}|{p.name for p in packet.iterdir() if p.name!='FREEZE.json'}
 if actual!=set(files):raise ValueError('nested union inventory differs')
 if sha(files['union-certificate.json'])!=gate.UNION_CERTIFICATE_SHA256:raise ValueError('nested union certificate changed')
 files['FREEZE.json']=regular(packet/'FREEZE.json')
 return {'nested-union/'+n:v for n,v in files.items()}


def inputs(repo,prep,final_path):
 repo=Path(repo).absolute();prep=Path(prep).absolute();final_raw=regular(final_path)
 if sha(final_raw)!=FINAL_SHA:raise ValueError('saved final record changed')
 f=json.loads(final_raw);cert=json.loads(regular(prep/'FREEZE.json'))
 if cert['root']!=PREP_ROOT or sha(canonical(cert['files']))!=PREP_ROOT or {p.name for p in prep.iterdir()}!=PREP_FILES|{'FREEZE.json'}:raise ValueError('preparation inventory/root differs')
 rp=repo/'strategy-research/coverage-pilot-completion-v1/report.py';report=module(regular(rp),rp,'bulk_saved_report',REPORT_SHA)
 pilot=repo/'strategy-research/coverage-pilot-packet-v1/pilot-successor-142'
 old,source,oldload=report.captured_closure(repo,pilot,f['fingerprint']['root'])
 if sha(canonical({n:sha(v) for n,v in old.items()}))!=f['fingerprint']['packet_files_sha256']:raise ValueError('saved closure changed')
 bp=repo/'strategy-research/coverage-pilot-packet-v1/build.py';br=regular(bp)
 if sha(br)!=BUILDER_SHA:raise ValueError('packet builder changed')
 pp=repo/'strategy-research/coverage-pass-residual-v1/build.py';pr=regular(pp)
 actual={n:sha(regular(prep/n)) for n in PREP_FILES}
 actual.update({'source/final-record.json':sha(final_raw),'code/build.py':sha(pr),'code/report.py':sha(regular(rp)),'code/packet-builder.py':sha(br),'source/pilot-FREEZE.json':sha(regular(pilot/'FREEZE.json'))})
 if actual!=cert['files']:raise ValueError('preparation physical/logical pins differ')
 data={('preparation/'+n):regular(prep/n) for n in PREP_FILES|{'FREEZE.json'}}
 data.update(old)
 data.update({'final-record.json':final_raw,'code/preparation.py':pr,'code/packet_builder.py':br,'code/completion_report.py':regular(rp)})
 data['original-pilot-protocol.json']=old['protocol.json'];data['original-pilot-baseline.json']=old['baseline.json'];data['original-pilot-requests.json']=old['requests.json'];data['original-pilot-policy.json']=old['policy.json']
 for n in ('requests.json','mappings.json','cell-allowlist.json','denominators.json','future-budget-policy.json'):data[n]=regular(prep/n)
 data['policy.json']=regular(prep/'response-policy.json')
 here=repo/'strategy-research/coverage-pass-execution-v1'
 if {p.name for p in here.glob('*.py') if not p.name.startswith('test')}!={'bootstrap.py','validator.py','orchestration.py','assemble.py'}:raise ValueError('bulk executable inventory differs')
 for name,file in [('bootstrap','bootstrap.py'),('runner','validator.py'),('orchestration','orchestration.py'),('assembler','assemble.py')]:data['code/'+name+'.py']=regular(here/file)
 names={n[5:-3] for n in data if n.startswith('code/') and n.endswith('.py')}
 data['dependency-paths.json']=canonical({n:str(p) for n,p in module_paths(repo,names).items()})
 data.update(nested_union_inputs(oldload('f2_gate')))
 return data,source,oldload


def load_modules(repo,data,source):
 # The original frozen source is retained, including its430-game validator.
 # Only this separate captured namespace replaces bulk runner/bootstrap/orchestration.
 names={n[5:-3] for n in data if n.startswith('code/') and n.endswith('.py')}
 paths=module_paths(repo,names);modules={}
 if json.loads(data['dependency-paths.json'])!={n:str(p) for n,p in paths.items()}:raise ValueError('captured dependency path mapping differs')
 for n,v in data.items():
  if n.startswith('code/') and n.endswith('.py'):
   key=n[5:-3];modules[key]=v
 for n,v in source.items():
  if n.endswith('.py'):
   key=(n[:-12] if n.endswith('/__init__.py') else n[:-3]).replace('/','.')
   if key in modules:raise ValueError('source module collision')
   modules[key]=v;paths[key]=Path(repo)/'strategy-research/football_archive/acquisition/football-archive-v4'/n
 cap=module(modules['capture'],paths['capture'],'bulk_capture',sha(modules['capture']))
 return cap.closed_modules(modules,paths)


def verified(packet,root,bundle=None):
 packet=Path(packet);cert=json.loads(regular(packet/'FREEZE.json'))
 if cert['root']!=root or sha(canonical(cert['files']))!=root or {p.name for p in packet.iterdir()}!=PHYSICAL|{'FREEZE.json'}:raise ValueError('execution packet inventory/root differs')
 cfg=json.loads(regular(packet/'config.json'))
 if set(cfg)!={'repo','preparation','final_record','restart_policy','superseded_unexecuted_root'} or cfg['superseded_unexecuted_root']!='05904da51d2487f4295dd41c45b105ea3b187dd7dbaf964f6a7e549fdc67a017' or cfg['restart_policy']!=dict(allowed=['prepared','running','pilot_clean_pause'],pending='block_no_resend',stopped='block_reconciliation',terminal='exhausted',automatic_retries=0,automatic_redirects=0):raise ValueError('configuration/restart policy differs')
 data,source,_=inputs(cfg['repo'],cfg['preparation'],cfg['final_record'])
 data.update({n:regular(packet/n) for n in PHYSICAL})
 data['protocol.json']=canonical({'execution_status':'reviewed_for_execution'})
 if {n:sha(v) for n,v in data.items()}!=cert['files']:raise ValueError('execution captured closure differs')
 load=load_modules(cfg['repo'],data,source);load('runner').packet(data,source)
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
