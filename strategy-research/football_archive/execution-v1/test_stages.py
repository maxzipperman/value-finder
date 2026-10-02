"""Real stage selection, pilot evidence and full synthetic F2 then F3a transport."""
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import sys
sys.dont_write_bytecode = True
import pytest
from test_followups import epoch, plan, BUNDLE, HERE, Session, approval


def packet_rows(packet):
    cert = json.loads((packet / 'FREEZE.json').read_text())
    m, rows = epoch.verify_packet(packet, cert['root'])
    return cert['root'], m, rows, json.loads((packet / 'seed.json').read_text())


def test_actual_pilot_integrity_gate_reuse_and_inventory():
    _, m, rows, seed = packet_rows(HERE / 'F2')
    epoch.verify_source_plan(HERE / 'F2', BUNDLE, m, rows)
    assert epoch.seed_state(seed, rows) == 85489
    epoch.stage_guard(HERE / 'F2', m, seed, rows, BUNDLE)
    assert m['new_credits'] == 34500 and len(rows) == 1773
    assert sum(not r['max_new_credits'] for r in rows) == 48
    assert m['opportunity_count'] == 1774
    ops = json.loads((HERE / 'F2/opportunities.json').read_text())
    assert sum(o['identity_type'] == 'provider-only' for o in ops) == 64
    assert sum(o['status'] != 'planned' for o in ops) == 1


@pytest.mark.parametrize('mode', ['stage', 'pilot_hash', 'pilot_rebuy', 'reuse_hash', 'seed_root'])
def test_stage_guards_reject(mode):
    _, m, rows, seed = packet_rows(HERE / 'F2')
    if mode == 'stage': m['stage'] = 'pilot'
    if mode == 'pilot_hash': seed['ledger_sha256'] = '0' * 64
    if mode == 'pilot_rebuy': next(r for r in rows if not r['max_new_credits'])['max_new_credits'] = 20
    if mode == 'reuse_hash': next(r for r in rows if not r['max_new_credits'])['cache_sha256'] = '0' * 64
    if mode == 'seed_root': seed['root'] = plan.SOURCE_ROOT
    with pytest.raises(ValueError): epoch.stage_guard(HERE / 'F2', m, seed, rows, BUNDLE)


def test_coverage_pin(monkeypatch):
    monkeypatch.setattr(epoch, 'PILOT_COVERAGE_SHA', '0' * 64)
    with pytest.raises(ValueError, match='coverage differs'): epoch.pilot_gate(BUNDLE)


@pytest.mark.parametrize('change', ['cycle', 'decrease', 'ancestor_duplicate'])
def test_every_ancestor_guard(tmp_path, monkeypatch, change):
    monkeypatch.setattr(epoch, 'ROOT_BASE', tmp_path)
    old = tmp_path / plan.SOURCE_ROOT / 'spending-ledger.json'; old.parent.mkdir()
    old.write_bytes(plan.canonical({'bundle_root_sha256': plan.SOURCE_ROOT, 'probe_credits': 1687,
        'status': 'recent_complete_stopped_before_older', 'pending': None, 'stopped': None,
        'attempts': {'ancestor': {'status': 'completed', 'reserved_credits': 82830}}, 'other_usage_reserved': 1699}))
    monkeypatch.setattr(epoch, 'SEED_HASH', plan.sha(old))
    original = {'root': plan.SOURCE_ROOT, 'ledger_path': str(old), 'ledger_sha256': plan.sha(old),
        'probe_credits': 1687, 'cumulative_debit_without_probe': 84529}
    newer = tmp_path / 'newer' / 'spending-ledger.json'; newer.parent.mkdir()
    state = {'bundle_root_sha256': 'newer', 'probe_credits': 1687, 'status': 'event_epoch_complete',
        'pending': None, 'stopped': None, 'attempts': {}, 'other_usage_reserved': 84529, 'predecessor_seed': original}
    if change == 'decrease': state['other_usage_reserved'] -= 1
    if change == 'cycle': state['predecessor_seed'] = {'root': 'newer'}
    newer.write_bytes(plan.canonical(state))
    seed = {'root': 'newer', 'ledger_path': str(newer), 'ledger_sha256': plan.sha(newer),
        'probe_credits': 1687, 'cumulative_debit_without_probe': state['other_usage_reserved']}
    rows = [{'request_id': 'ancestor', 'max_new_credits': 20}] if change == 'ancestor_duplicate' else []
    with pytest.raises(ValueError): epoch.seed_state(seed, rows)


def test_f3_candidate_cannot_execute():
    _, m, rows, seed = packet_rows(HERE / 'F3a')
    assert len(rows) == 570 and m['new_credits'] == 34200 and m['scope_seasons'] == [2025]
    with pytest.raises(ValueError, match='Unreviewed stage'): epoch.stage_guard(HERE / 'F3a', m, seed, rows, BUNDLE)


@pytest.mark.parametrize('field', ['book', 'market', 'season'])
def test_scope_errors(tmp_path, field):
    packet = tmp_path / 'F2'; shutil.copytree(HERE / 'F2', packet)
    rows = json.loads((packet / 'requests.json').read_text())
    if field == 'book': rows[0]['params']['bookmakers'] = 'wrong'
    if field == 'market': rows[0]['params']['markets'] = 'h2h'
    if field == 'season': rows[0]['seasons'] = [2026]
    m = json.loads((packet / 'manifest.json').read_text())
    plan.write_packet(packet, m, rows, json.loads((packet / 'opportunities.json').read_text()))
    root = epoch.freeze(packet)
    with pytest.raises(ValueError): epoch.verify_packet(packet, root)


def test_source_integrity(tmp_path):
    source = tmp_path / 'source'; shutil.copytree(BUNDLE, source)
    with (source / 'executor.py').open('ab') as f: f.write(b'\n# changed\n')
    with pytest.raises(ValueError, match='source bytes differ'): epoch.source_executor(source)


def test_pilot_integrity(tmp_path):
    source = tmp_path / 'followups'; shutil.copytree(HERE.parent / 'followups', source)
    spec = importlib.util.spec_from_file_location('changed_pilot', source / 'epoch.py')
    old = importlib.util.module_from_spec(spec); spec.loader.exec_module(old)
    with (source / 'plan.py').open('ab') as f: f.write(b'\n# changed\n')
    with pytest.raises(ValueError, match='frozen bytes changed'): old.verify_packet(source / 'F2-pilot', epoch.PILOT_ROOT)


def raise_ceiling(auth):
    auth['account_reconciliation']['max_baseline_used'] = 200000
    auth['hub_go_ahead']['comment_body'] = auth['hub_go_ahead']['comment_body'].replace('max-baseline-used 100000', 'max-baseline-used 200000')


def test_full_f2_then_f3_reuse_and_debits(tmp_path, monkeypatch):
    original_base = epoch.ROOT_BASE
    monkeypatch.setattr(epoch, 'ROOT_BASE', tmp_path / 'state')
    base = epoch.source_executor(BUNDLE)
    monkeypatch.setattr(base, 'RUNTIME_BASE', epoch.ROOT_BASE)
    monkeypatch.setattr(epoch, 'source_executor', lambda _: base)
    monkeypatch.setattr(epoch, 'checkout_clean', lambda _: None)
    monkeypatch.setattr(base, 'checkout_commit', lambda _: 'b' * 40)
    prior = json.loads((original_base / plan.SOURCE_ROOT / 'spending-ledger.json').read_text())
    path = epoch.ROOT_BASE / plan.SOURCE_ROOT / 'spending-ledger.json'; base.atomic(path, prior)
    monkeypatch.setattr(epoch, 'SEED_HASH', plan.sha(path))
    pilot = json.loads((original_base / epoch.PILOT_ROOT / 'spending-ledger.json').read_text())
    pilot['predecessor_seed']['ledger_path'] = str(path)
    path = epoch.ROOT_BASE / epoch.PILOT_ROOT / 'spending-ledger.json'; base.atomic(path, pilot)
    shutil.copytree(original_base / epoch.PILOT_ROOT / 'receipts', path.parent / 'receipts')
    monkeypatch.setattr(epoch, 'PILOT_LEDGER_SHA', plan.sha(path))
    spec = importlib.util.spec_from_file_location('test_immutable_coverage', HERE.parent / 'followups/pilot_coverage.py')
    cov = importlib.util.module_from_spec(spec); spec.loader.exec_module(cov)
    spec = importlib.util.spec_from_file_location('test_immutable_epoch', HERE.parent / 'followups/epoch.py')
    old = importlib.util.module_from_spec(spec); spec.loader.exec_module(old); cov.epoch = old
    report = cov.report(HERE.parent / 'followups/F2-pilot', epoch.PILOT_ROOT, BUNDLE, path)
    monkeypatch.setattr(epoch, 'PILOT_COVERAGE_SHA', hashlib.sha256(plan.canonical(report) + b'\n').hexdigest())
    packet = tmp_path / 'F2'; shutil.copytree(HERE / 'F2', packet)
    seed = json.loads((packet / 'seed.json').read_text()); seed.update(ledger_path=str(path), ledger_sha256=plan.sha(path))
    base.atomic(packet / 'seed.json', seed)
    root = epoch.freeze(packet); _, m, rows, _ = packet_rows(packet)
    auth = approval(root, m); raise_ceiling(auth)
    session = Session(); session.used = 85489; session.remaining = 4914511
    result = epoch.run(packet, root, BUNDLE, auth, key='SYNTHETIC_KEY_ONLY', fake_session=session)
    assert len(session.calls) == 1726 and result['new_billed'] == result['new_reserved'] == 34500
    assert result['cumulative_reserved'] == 121676
    state = json.loads((base.runtime_path(root) / 'spending-ledger.json').read_text())
    assert len(state['cache_reuse']) == 48 and len(state['attempts']) == 1725
    props = tmp_path / 'F3a'; shutil.copytree(HERE / 'F3a', props)
    m3 = json.loads((props / 'manifest.json').read_text()); m3['stage'] = '2025-props'; base.atomic(props / 'manifest.json', m3)
    predecessor = base.runtime_path(root) / 'spending-ledger.json'
    seed3 = {'root': root, 'ledger_path': str(predecessor), 'ledger_sha256': plan.sha(predecessor),
        'probe_credits': 1687, 'cumulative_debit_without_probe': state['other_usage_reserved'] + 34500}
    base.atomic(props / 'seed.json', seed3)
    root3 = epoch.freeze(props); auth3 = approval(root3, m3); raise_ceiling(auth3)
    third = Session(); third.used = session.used; third.remaining = session.remaining
    result3 = epoch.run(props, root3, BUNDLE, auth3, key='SYNTHETIC_KEY_ONLY', fake_session=third)
    assert len(third.calls) == 571 and result3['new_billed'] == 34200 and result3['cumulative_reserved'] == 155876
    receipt = base.runtime_path(root) / 'receipts' / (next(iter(state['attempts'])) + '.json'); receipt.unlink()
    reads = []; again = Session()
    with pytest.raises(Exception): epoch.run(packet, root, BUNDLE, auth, key=lambda: reads.append(1), fake_session=again)
    with pytest.raises(Exception): epoch.run(props, root3, BUNDLE, auth3, key=lambda: reads.append(1), fake_session=again)
    assert not reads and not again.calls


@pytest.mark.parametrize('filename', ['epoch.py', 'pilot_coverage.py', 'plan.py'])
def test_pilot_gate_rejects_sentinel_before_any_import(tmp_path, monkeypatch, filename):
    source = tmp_path / 'followups'
    shutil.copytree(HERE.parent / 'followups', source)
    extension = tmp_path / 'execution-v1'; extension.mkdir()
    monkeypatch.setattr(epoch, '__file__', str(extension / 'epoch.py'))
    marker = tmp_path / 'UNVERIFIED_EXECUTED'
    with (source / filename).open('ab') as handle:
        handle.write(('\nfrom pathlib import Path\nPath(' + repr(str(marker)) + ').write_text("bad")\nraise RuntimeError("UNVERIFIED_EXECUTED")\n').encode())
    with pytest.raises(ValueError, match='before import'):
        epoch.pilot_gate(BUNDLE)
    assert not marker.exists()


@pytest.mark.parametrize('change', ['missing', 'unexpected', 'symlink', 'packet_directory'])
def test_pilot_gate_file_inventory_precedes_import(tmp_path, monkeypatch, change):
    source = tmp_path / 'followups'; shutil.copytree(HERE.parent / 'followups', source)
    extension = tmp_path / 'execution-v1'; extension.mkdir()
    monkeypatch.setattr(epoch, '__file__', str(extension / 'epoch.py'))
    if change == 'missing': (source / 'prepare.py').unlink()
    if change == 'unexpected': (source / 'extra.py').write_text('raise RuntimeError("bad")')
    if change == 'symlink':
        (source / 'epoch.py').unlink()
        (source / 'epoch.py').symlink_to(HERE.parent / 'followups/epoch.py')
    if change == 'packet_directory': (source / 'F2-pilot/extra').mkdir()
    with pytest.raises(ValueError): epoch.pilot_gate(BUNDLE)


def test_pilot_execution_uses_verified_bytes_not_reopened_path(tmp_path, monkeypatch):
    source = tmp_path / 'followups'; shutil.copytree(HERE.parent / 'followups', source)
    captured = epoch.verified_pilot_bytes(source)
    marker = tmp_path / 'UNVERIFIED_EXECUTED'
    (source / 'epoch.py').write_text('from pathlib import Path\nPath(' + repr(str(marker)) + ').write_text("bad")')
    old = epoch.pilot_module('verified_snapshot', source, 'epoch.py', captured)
    assert callable(old.verify_packet) and not marker.exists()
