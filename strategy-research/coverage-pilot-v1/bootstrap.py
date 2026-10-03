"""Verified-byte bootstrap: offline validation by default; explicit hub-only paid CLI."""
import hashlib
import json
from pathlib import Path
import types
import os
import stat

SOURCE_ROOT='4468a94c2b415cd5c53dd58163831f61d379ee44ec1b560f5a9b84be9c7f010d'
MODULES={'planner','bounds','timing','mapping','receipts','baseline','evidence','transport','authority','bootstrap','runner','classifier','execution','certainty','overlap','orchestration','frame_binding'}
PACKET={'manifest.json','requests.json','policy.json','protocol.json','frame.json','draw.json','selected.json','mappings.json','baseline.json','overlap.json','slot-map.json','classifier-contract.json','certainty-source-proof.json'}


def regular(path):
    path=Path(path).absolute()
    if any(p.is_symlink() for p in (path,*path.parents)):raise ValueError('symlink capture')
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):raise ValueError('regular capture required')
        with os.fdopen(fd,'rb',closefd=False) as handle:return handle.read()
    finally:os.close(fd)


def canonical(obj):
    return json.dumps(obj,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()


def verified(packet, root, bundle):
    packet,bundle=Path(packet),Path(bundle);here=Path(__file__).parent;parent=here.parent
    cert=json.loads(regular(packet/'FREEZE.json'))
    if cert['root']!=root or hashlib.sha256(canonical(cert['files'])).hexdigest()!=root:
        raise ValueError('pilot root differs')
    if {p.name for p in packet.iterdir()}!=PACKET|{'FREEZE.json'}:
        raise ValueError('pilot packet inventory differs')
    if {p.stem for p in here.glob('*.py') if not p.name.startswith('test_')}!=MODULES:
        raise ValueError('pilot executable inventory differs')
    paths={n:here/(n+'.py') for n in MODULES}
    paths.update(capture=parent/'football-metadata-v1/capture.py',history=parent/'football-metadata-v1/history.py',
                 plan=parent/'nfl-props-archive-v1/plan.py',f2_gate=parent/'football_archive/f2_handoff.py',
                 older_recovery=parent/'football_archive/older-recovery-v1/recovery.py')
    data={n:regular(packet/n) for n in PACKET}
    data.update({'code/'+n+'.py':regular(p) for n,p in paths.items()})
    data['policy/older-PROTOCOL.md']=regular(parent/'football_archive/older-recovery-v1/PROTOCOL.md')
    data['policy/PRIMARY-CONTRACT.json']=regular(here/'PRIMARY-CONTRACT.json')
    data['source/FREEZE.json']=regular(bundle/'FREEZE.json')
    source_cert=json.loads(data['source/FREEZE.json'])
    if source_cert['bundle_root_sha256']!=SOURCE_ROOT or hashlib.sha256(canonical(source_cert['file_sha256'])).hexdigest()!=SOURCE_ROOT:
        raise ValueError('immutable shared root differs')
    actual={str(p.relative_to(bundle)) for p in bundle.rglob('*') if p.is_file() and p.name!='FREEZE.json'}
    if actual!=set(source_cert['file_sha256']):raise ValueError('immutable inventory differs')
    source={n:regular(bundle/n) for n in actual}
    if {n:hashlib.sha256(v).hexdigest() for n,v in source.items()}!=source_cert['file_sha256']:
        raise ValueError('immutable bytes changed')
    if {n:hashlib.sha256(v).hexdigest() for n,v in data.items()}!=cert['files']:
        raise ValueError('pilot closure changed')
    capture=types.ModuleType('pilot_verified_capture');capture.__file__=str(paths['capture'])
    exec(compile(data['code/capture.py'],capture.__file__,'exec'),capture.__dict__)
    modules={n:data['code/'+n+'.py'] for n in paths}
    for name,blob in source.items():
        if name.endswith('.py'):
            key=(name[:-12] if name.endswith('/__init__.py') else name[:-3]).replace('/','.')
            if key in modules:raise ValueError('shared module collision')
            modules[key]=blob;paths[key]=bundle/name
    load=capture.closed_modules(modules,paths)
    return load('runner'),load('executor'),data,source,load


if __name__=='__main__':
    import argparse
    import sys
    parser=argparse.ArgumentParser()
    parser.add_argument('--packet',type=Path,required=True);parser.add_argument('--root',required=True)
    parser.add_argument('--bundle',type=Path,required=True);parser.add_argument('--authorization',type=Path)
    parser.add_argument('--key-file',type=Path);parser.add_argument('--confirm-paid',action='store_true')
    args=parser.parse_args()
    try:
        runner,base,data,source,load=verified(args.packet,args.root,args.bundle)
        if not args.confirm_paid:print(json.dumps(runner.packet(data,source)))
        else:
            if not sys.flags.isolated or not sys.dont_write_bytecode:raise ValueError('paid bootstrap requires -I -B')
            if not args.authorization or not args.key_file:raise ValueError('exact external authority and explicit key source required')
            auth=json.loads(regular(args.authorization))
            def key():
                from dotenv import dotenv_values
                return dotenv_values(args.key_file).get('ODDS_API_KEY')
            def http():return load('archive_markets.http').new_session()
            print(json.dumps(load('orchestration').run(args.packet,args.root,args.bundle,auth,key_factory=key,http_factory=http)))
    except BaseException:
        raise SystemExit('STOPPED: retain evidence/reservations; no automatic retry or recovery') from None
