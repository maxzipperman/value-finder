"""Self-contained bootstrap: authenticate/capture complete freeze BEFORE local imports.

Consumers must pin/capture this bootstrap's own bytes in their reviewed code,
then call load_verified_union(packet, expected_root). Only captured plan/curves/union
modules execute, with a closed local import mapping; no global sys.modules swap.
"""
import builtins
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import types


def canonical(obj):return json.dumps(obj,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()


def regular(path):
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):raise ValueError('Regular captured dependency required')
        with os.fdopen(fd,'rb',closefd=False) as h:return h.read()
    finally:os.close(fd)


def load_verified_union(packet,expected_root,*,after_capture=lambda:None):
    packet=Path(packet)
    if (not re.fullmatch('[a-f0-9]{64}',expected_root) or packet.is_symlink() or packet.parent.is_symlink()):
        raise ValueError('Pinned ordinary union packet required')
    paths={f'code/{p.name}':p for p in packet.parent.glob('*.py')}
    for p in packet.iterdir():
        if p.is_symlink() or not p.is_file():raise ValueError('Regular immediate union files required')
        if p.name!='FREEZE.json':paths[p.name]=p
    captured={name:regular(p) for name,p in paths.items()}
    files={name:hashlib.sha256(data).hexdigest() for name,data in sorted(captured.items())}
    freeze=json.loads(regular(packet/'FREEZE.json'))
    if freeze!={'root':expected_root,'files':files} or hashlib.sha256(canonical(files)).hexdigest()!=expected_root:
        raise ValueError('Complete union dependency/packet map changed before import')
    after_capture()  # Regression hook: subsequent compilation never reopens code.
    modules={};local_names={p.stem for p in packet.parent.glob('*.py')}
    original_import=builtins.__import__
    def closed_import(name,globals=None,locals=None,fromlist=(),level=0):
        if level:raise ImportError('Relative local imports prohibited')
        if name in modules:return modules[name]
        if name.split('.')[0] in local_names:raise ImportError('Unmapped local executable dependency')
        return original_import(name,globals,locals,fromlist,level)
    for name in ('plan','curves','union'):
        module=types.ModuleType('captured_union_'+name);module.__file__=str(packet.parent/(name+'.py'))
        module.__dict__['__builtins__']={**vars(builtins),'__import__':closed_import}
        modules[name]=module
        exec(compile(captured['code/'+name+'.py'],module.__file__,'exec'),module.__dict__)
    union=modules['union']
    union.PINNED_PACKET={name:json.loads(data) for name,data in captured.items() if name.endswith('.json') and not name.startswith('code/')}
    union.PINNED_PACKET_ROOT=expected_root
    union.VERIFIED_LOCAL_DEPENDENCIES={name:files['code/'+name+'.py'] for name in ('plan','curves','union')}
    return union
