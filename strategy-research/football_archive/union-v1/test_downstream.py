import json
from pathlib import Path
import shutil
import sys
import pytest
HERE=Path(__file__).parent
sys.path.insert(0,str(HERE))
import downstream,epoch,union
from test_union import snapshot,prepared,atomic


def copied(tmp_path):
    folder=tmp_path/'union'
    folder.mkdir()
    for p in HERE.glob('*.py'):shutil.copyfile(p,folder/p.name)
    shutil.copytree(HERE/'F3a',folder/'F3a')
    # Compute exactly the complete local file map used by the independent loader.
    packet=folder/'F3a';files={f'code/{p.name}':__import__('hashlib').sha256(p.read_bytes()).hexdigest() for p in folder.glob('*.py')}
    files.update({p.name:__import__('hashlib').sha256(p.read_bytes()).hexdigest() for p in packet.iterdir() if p.name!='FREEZE.json'})
    root=__import__('hashlib').sha256(downstream.canonical(dict(sorted(files.items())))).hexdigest()
    atomic(packet/'FREEZE.json',{'root':root,'files':dict(sorted(files.items()))})
    return packet,root


@pytest.mark.parametrize('file',['union.py','curves.py','plan.py','epoch.py','f3a_missing.py'])
def test_all_dependency_mutations_refused_before_any_code(tmp_path,file):
    packet,root=copied(tmp_path);sentinel=tmp_path/'EXECUTED'
    (packet.parent/file).write_text(f"from pathlib import Path\nPath({str(sentinel)!r}).write_text('BAD')\n")
    with pytest.raises(ValueError):downstream.load_verified_union(packet,root)
    assert not sentinel.exists()


def test_capture_closes_local_import_toc_tou(tmp_path):
    packet,root=copied(tmp_path);sentinel=tmp_path/'EXECUTED'
    def swap():
        for name in ('plan','curves','union'):(packet.parent/(name+'.py')).write_text(f"from pathlib import Path\nPath({str(sentinel)!r}).write_text('BAD')\n")
    loaded=downstream.load_verified_union(packet,root,after_capture=swap)
    assert callable(loaded.validate) and callable(loaded.verify_downstream_union) and not sentinel.exists()
    assert set(loaded.VERIFIED_LOCAL_DEPENDENCIES)=={'plan','curves','union'}


def test_wrapper_requires_captured_complete_certificate(tmp_path):
    packet,root=copied(tmp_path);loaded=downstream.load_verified_union(packet,root)
    with pytest.raises(ValueError):loaded.verify_downstream_union(Path('/tmp/NOT_FINAL'),authenticate=False)
    with pytest.raises(ValueError):union.verify_downstream_union(Path('/tmp/NOT_CAPTURED'),authenticate=False)


def test_whole_wrapper_exact_certificate_and_commits(prepared,tmp_path):
    target,pk,auth=prepared;cert,report=union.validate(auth)
    packet,root=copied(tmp_path)
    atomic(packet/'union-certificate.json',cert);atomic(packet/'continuation-authorization.json',auth)
    # Recompute capture after freezing final synthetic evidence.
    files={f'code/{p.name}':__import__('hashlib').sha256(p.read_bytes()).hexdigest() for p in packet.parent.glob('*.py')}
    files.update({p.name:__import__('hashlib').sha256(p.read_bytes()).hexdigest() for p in packet.iterdir() if p.name!='FREEZE.json'})
    root=__import__('hashlib').sha256(downstream.canonical(dict(sorted(files.items())))).hexdigest();atomic(packet/'FREEZE.json',{'root':root,'files':dict(sorted(files.items()))})
    loaded=downstream.load_verified_union(packet,root);loaded.RUNTIME_BASE=target
    # Still executes the complete trusted validate implementation; only relocated
    # fixture packet/hash readers are injected, just as in the full union tests.
    loaded.packet=union.packet;loaded.HERE=union.HERE
    for name in ('SOURCE_LEDGER_SHA','PILOT_SHA','PARTIAL_SHA','SECOND_PARTIAL_SHA'):setattr(loaded,name,getattr(union,name))
    final=target/union.CONTINUATION_ROOT/'spending-ledger.json'
    got,_=loaded.verify_downstream_union(final,certificate_path=packet/'union-certificate.json',authenticate=False)
    assert got==cert
    with pytest.raises(ValueError):loaded.verify_downstream_union(final,second_transition_commit='a'*40,authenticate=False)
    bad=dict(cert);bad['cumulative_debit_without_probe']-=1;atomic(packet/'union-certificate.json',bad)
    with pytest.raises(ValueError):loaded.verify_downstream_union(final,certificate_path=packet/'union-certificate.json',authenticate=False)
