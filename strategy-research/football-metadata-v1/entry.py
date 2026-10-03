"""Offline default bootstrap. Verify the entire closure before executing engine bytes."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import types


def regular(path):
    path=Path(path).absolute()
    if any(p.is_symlink() for p in (path,*path.parents)):raise ValueError('Symlink dependency')
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):raise ValueError('Regular dependency required')
        with os.fdopen(fd,'rb',closefd=False) as handle:return handle.read()
    finally:os.close(fd)


def verified(packet, root, bundle):
    packet,bundle=Path(packet),Path(bundle)
    cert=json.loads(regular(packet/'FREEZE.json'))
    canonical=lambda x:json.dumps(x,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()
    if cert['root']!=root or hashlib.sha256(canonical(cert['files'])).hexdigest()!=root:raise ValueError('Wrong packet root')
    code=Path(__file__).parent
    if {p.name for p in code.glob('*.py') if not p.name.startswith('test_')}!={'entry.py','engine.py','capture.py','prepare.py','history.py'}:
        raise ValueError('Undeclared metadata executable')
    names={'code/entry.py':code/'entry.py','code/engine.py':code/'engine.py','code/capture.py':code/'capture.py',
           'code/plan.py':code.parent/'nfl-props-archive-v1/plan.py','code/prepare.py':code/'prepare.py'}
    names['code/history.py']=code/'history.py'
    names['code/f2_gate.py']=code.parent/'football_archive/f2_handoff.py'
    names['code/older_recovery.py']=code.parent/'football_archive/older-recovery-v1/recovery.py'
    names['policy/older-PROTOCOL.md']=code.parent/'football_archive/older-recovery-v1/PROTOCOL.md'
    expected_packet={'manifest.json','request-list.csv','policy.json','FREEZE.json'}
    if {p.name for p in packet.iterdir()}!=expected_packet:raise ValueError('Packet inventory changed')
    names.update({n:packet/n for n in expected_packet-{'FREEZE.json'}})
    vcert=json.loads(regular(bundle/'FREEZE.json'))
    source_root='4468a94c2b415cd5c53dd58163831f61d379ee44ec1b560f5a9b84be9c7f010d'
    if vcert['bundle_root_sha256']!=source_root or hashlib.sha256(canonical(vcert['file_sha256'])).hexdigest()!=source_root:raise ValueError('Wrong immutable shared source root')
    actual={str(p.relative_to(bundle)) for p in bundle.rglob('*') if p.is_file() and p.name!='FREEZE.json'}
    if actual!=set(vcert['file_sha256']):raise ValueError('Shared source inventory changed')
    source={n:regular(bundle/n) for n in actual}
    if {n:hashlib.sha256(b).hexdigest() for n,b in source.items()}!=vcert['file_sha256']:raise ValueError('Shared source changed')
    names['source/FREEZE.json']=bundle/'FREEZE.json'
    data={n:regular(p) for n,p in names.items()}
    if {n:hashlib.sha256(b).hexdigest() for n,b in data.items()}!=cert['files']:raise ValueError('Frozen metadata closure changed')
    # The only bootstrap compilation after full source validation; no mutable reopens.
    capture=types.ModuleType('metadata_bootstrap_capture')
    capture.__file__=str(code/'capture.py')
    exec(compile(data['code/capture.py'],capture.__file__,'exec'),capture.__dict__)
    py={n:b for n,b in source.items() if n.endswith('.py')}
    modules={(n[:-12] if n.endswith('/__init__.py') else n[:-3]).replace('/','.'):b for n,b in py.items()}
    paths={(n[:-12] if n.endswith('/__init__.py') else n[:-3]).replace('/','.'):bundle/n for n in py}
    for n in ('engine','capture','plan','history','f2_gate','older_recovery'):
        modules[n]=data['code/'+n+'.py'];paths[n]=names['code/'+n+'.py']
    load=capture.closed_modules(modules,paths)
    return load('engine'),load('executor'),data,source,load


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--packet',type=Path,required=True);p.add_argument('--root',required=True)
    p.add_argument('--bundle',type=Path,required=True);p.add_argument('--authorization',type=Path)
    p.add_argument('--key-file',type=Path);p.add_argument('--confirm-paid',action='store_true')
    a=p.parse_args()
    try:
        engine,base,data,source,load=verified(a.packet,a.root,a.bundle)
        manifest,rows,policy=engine.packet(data)
        if not a.confirm_paid:
            print(json.dumps({'offline':True,'request_count':len(rows),'new_cap':manifest['max_new_credits'],'global_acceptance_required':True}))
        else:
            if not sys.flags.isolated or not sys.dont_write_bytecode:
                raise ValueError('Paid bootstrap requires isolated Python -I -B')
            if not a.authorization or not a.key_file:p.error('Hub-only exact authorization and key-file required')
            auth=json.loads(regular(a.authorization))
            def key():return engine.key_from(a.key_file)
            print(json.dumps(engine.run(a.packet,a.root,a.bundle,auth,key=key,verify=lambda:verified(a.packet,a.root,a.bundle))))
    except BaseException:
        raise SystemExit('STOPPED: no automatic repair or resend; review local evidence') from None
