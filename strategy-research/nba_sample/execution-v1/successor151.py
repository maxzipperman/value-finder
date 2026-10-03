"""Exact metadata-only successor151 ancestry; no generic status exemption or execution.

Reuse already accepted, byte-pinned readiness/F2 evidence. No raw bodies/outcomes,
HTTP, certificate installation, ledger rewrite, approval generation or recovery.
"""
import hashlib
import json
import os
from pathlib import Path
import stat

ROOT = 'c7d3ea3d938918735e3ec99f9b56652f67f4f200c93f233385b4d6429fbe1376'
PINS_SHA = '61f0c1cc6f53b68c52eaa535b43eef4bf9a88e077255b419bf34e98e8ae124e0'
HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
PROPOSED_CEILING = 400000
CAP = 7540


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode()


def checked(path, pin):
    path = Path(path)
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError('Linked ancestry metadata')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise ValueError('Nonregular ancestry metadata')
        with os.fdopen(fd, 'rb', closefd=False) as f:
            raw = f.read()
    finally:
        os.close(fd)
    if hashlib.sha256(raw).hexdigest() != pin:
        raise ValueError('Exact ancestry metadata hash changed')
    return raw


def debit(state):
    values = [state['probe_credits'], state['other_usage_reserved']]
    values += [a['reserved_credits'] for a in state['attempts'].values()]
    if any(type(v) is not int or v < 0 for v in values) or state['probe_credits'] != 1687:
        raise ValueError('Invalid retained debit')
    return sum(values)


def validate(states, pins, rows):
    if pins['root'] != ROOT or pins['paid_execution_enabled'] is not False:
        raise ValueError('Exact preparation-only successor required')
    if set(states) != set(pins['ledger_pins']):
        raise ValueError('Global ancestry inventory changed')
    ids = {r['request_id'] for r in rows}
    keys = {r['cache_key'] for r in rows}
    if len(ids) != len(rows) or len(keys) != len(rows):
        raise ValueError('Duplicate candidate identities')
    for root, state in states.items():
        if state['bundle_root_sha256'] != root or state['status'] != pins['statuses'][root]:
            raise ValueError('Exact ancestor identity/status changed')
        debit(state)
        if ids & (set(state['attempts']) | set(state.get('cache_reuse', {}))):
            raise ValueError('Ancestor request overlap')
        if keys & {a['cache_key'] for a in state['attempts'].values()}:
            raise ValueError('Ancestor cache overlap')
        if root != pins['retired_root'] and (state['pending'] or state['stopped']):
            raise ValueError('Uncertified pending/stopped ancestor')
        prior = state.get('predecessor_seed')
        if prior:
            parent = states[prior['root']]
            if (prior['ledger_sha256'] != pins['ledger_pins'][prior['root']]
                    or prior['probe_credits'] != 1687
                    or prior['cumulative_debit_without_probe'] != debit(parent)-1687
                    or state['other_usage_reserved'] < debit(parent)-1687):
                raise ValueError('Ancestry/F2 carry decreased')
    retired = states[pins['retired_root']]
    pending = retired['attempts'][pins['pending_id']]
    if (retired['pending'] != pins['pending_id'] or not retired['stopped']
            or pending != {'cache_key':'05175510dc14de25e2ca','reserved_credits':60,'status':'pending'}
            or len(retired['attempts']) != 12 or debit(retired) != 208106
            or sum(a['reserved_credits'] for a in retired['attempts'].values()) != 720
            or sum(a.get('billed_credits',0) for a in retired['attempts'].values()) != 660):
        raise ValueError('Permanent pending60/retired reservations changed')
    final = states[ROOT]
    if (len(final['attempts']) != 1290
            or sum(a['status']=='completed' for a in final['attempts'].values()) != 1288
            or sum(a['status']=='missing' for a in final['attempts'].values()) != 2
            or sum(a['reserved_credits'] for a in final['attempts'].values()) != 66480
            or final['other_usage_reserved'] != debit(retired)-1687
            or debit(final) != pins['conservative_debit']):
        raise ValueError('Exact completed successor accounting changed')
    if (type(pins['proposed_ceiling']) is not int or pins['proposed_ceiling'] != PROPOSED_CEILING
            or debit(final)+CAP > pins['proposed_ceiling']):
        raise ValueError('Prospective ceiling insufficient or changed')


def retired_absence(runtime, pins):
    folder = Path(runtime)/pins['retired_root']
    receipt = folder/'receipts'/(pins['pending_id']+'.json')
    if receipt.exists() or receipt.is_symlink() or any((folder/'data/raw').rglob('05175510dc14de25e2ca.parquet')):
        raise ValueError('Retired pending60 acquired new response/receipt; reconciliation required')


def seed(path, rows, runtime):
    """Caller holds shared read-only global lock; recheck every pin before returning."""
    runtime, path = Path(runtime), Path(path)
    if path != runtime/ROOT/'spending-ledger.json':
        raise ValueError('Only exact successor151 is an N0 predecessor')
    pins = json.loads(checked(HERE/'successor151-pins.json', PINS_SHA))
    source = {rel:checked(REPO/rel,pin) for rel,pin in pins['source_pins'].items()}
    base = json.loads(source['strategy-research/pass150-timeout-recovery-v1/untouched-successor-final/baseline.json'])
    expected = base['expected_global_snapshot']
    if (pins['ledger_pins'] != expected['ledgers'] | {ROOT:pins['ledger_pins'][ROOT]}
            or set(p.parent.name for p in runtime.glob('*/spending-ledger.json')) != set(pins['ledger_pins'])
            or {p.stem for p in (runtime/'registrations').glob('*.json')} != set(pins['ledger_pins'])
            or {p.parent.name for p in runtime.glob('*/INITIALIZED.json')} != set(pins['ledger_pins'])):
        raise ValueError('Global ancestry inventory changed')
    captured = {rel:checked(runtime/rel,pin) for rel,pin in pins['runtime_pins'].items()}
    states = {root:json.loads(captured[root+'/spending-ledger.json']) for root in pins['ledger_pins']}
    validate(states,pins,list(rows))
    retired_absence(runtime,pins)
    if states[ROOT]['predecessor_snapshot'] != hashlib.sha256(canonical(expected)).hexdigest():
        raise ValueError('Native predecessor snapshot changed')
    for root in states:
        marker = json.loads(captured['registrations/'+root+'.json'])
        init = json.loads(captured[root+'/INITIALIZED.json'])
        if marker['bundle_root_sha256'] != root or init != {'bundle_root_sha256':root,'probe_credits':1687}:
            raise ValueError('Exact registration/initialization changed')
    cert = json.loads(source['strategy-research/pass150-timeout-recovery-v1/exact-stop-certificate/certificate.json'])
    installed = json.loads(captured[pins['retired_root']+'/authority-timeout-retirement/certificate.json'])
    if installed != cert or cert['pending_reserved'] != 60 or cert['no_resend'] is not True:
        raise ValueError('Installed exact retirement changed')
    f2 = json.loads(source['strategy-research/football_archive/union-v1/F3a/union-certificate.json'])
    proof = dict(certificate_sha256=pins['source_pins']['strategy-research/football_archive/union-v1/F3a/union-certificate.json'],
                 final_ledger_sha256=f2['continuation_ledger_sha256'],coverage_sha256=f2['coverage_sha256'],
                 response_evidence_sha256=f2['response_evidence_sha256'])
    if hashlib.sha256(canonical(proof)).hexdigest() != pins['f2_union_proof_sha256']:
        raise ValueError('Accepted F2 proof changed')
    retired_absence(runtime,pins)
    for rel,pin in pins['runtime_pins'].items(): checked(runtime/rel,pin)
    for rel,pin in pins['source_pins'].items(): checked(REPO/rel,pin)
    return dict(kind='exact_successor151_preparation_only',root=ROOT,ledger_path=str(path),
                ledger_sha256=pins['ledger_pins'][ROOT],probe_credits=1687,
                cumulative_debit_without_probe=debit(states[ROOT])-1687,
                conservative_cumulative_reserved=debit(states[ROOT]),
                cumulative_with_n0=debit(states[ROOT])+CAP,proposed_ceiling=PROPOSED_CEILING,
                lineage_pins_sha256=PINS_SHA,f2_union_proof_sha256=pins['f2_union_proof_sha256'],
                paid_execution_enabled=False)
