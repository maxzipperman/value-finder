"""A separately frozen event-odds epoch using v4's reviewed reservation/accounting library.

Never edits the completed bundle/ledger. New epochs pin the predecessor ledger and carry its full
probe/reservation/external debit. Offline by default; no transport without exact live hub approval.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import stat
import types
import fcntl
from pathlib import Path
import sys

import plan

ROOT_BASE = Path.home() / 'Library/Application Support/ValueFinder/football-acquisition-state'
LIVE = Path.home() / 'code/value-finder'
SEED_HASH = 'eb9e93e354babef2be73ddaa13ea6e2913c58eaaff706ed4e78aec1381636190'
PRIOR_ROOT = plan.SOURCE_ROOT
PILOT_ROOT = 'cbe125474acf46becd3f7e01903675ece864adb683cdc73734bad7e1635dddcc'
PILOT_LEDGER_SHA = '754c81b87bb22af671bcf8cc6d8dd02accd5123296ad43d0ce50a119adc49d77'
PILOT_COVERAGE_SHA = '70035da9cac544a94d6c5f44155d97008c5300e24f064fa1dc7979e77ffb0f27'


def verified_pilot_bytes(folder):
    """Trusted extension verifies the entire historical freeze before executing code.

    Capture once through non-following regular-file descriptors; execution uses
    those exact verified bytes rather than reopening a mutable source path.
    """
    folder = Path(folder)
    packet = folder / 'F2-pilot'
    if folder.is_symlink() or packet.is_symlink() or not packet.is_dir():
        raise ValueError('Pilot source/packet must be ordinary directories')
    def read_regular(path):
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise ValueError('Pilot freeze permits regular files only')
            with os.fdopen(fd, 'rb', closefd=False) as handle:
                return handle.read()
        finally:
            os.close(fd)
    paths = {f'code/{p.name}': p for p in folder.glob('*.py')}
    for path in packet.iterdir():
        if path.is_symlink() or not path.is_file():
            raise ValueError('Pilot packet permits regular immediate files only')
        if path.name != 'FREEZE.json':
            paths[path.name] = path
    if any(path.is_symlink() or not path.is_file() for path in paths.values()):
        raise ValueError('Pilot code permits regular files only')
    captured = {name: read_regular(path) for name, path in paths.items()}
    files = {name: __import__('hashlib').sha256(data).hexdigest()
             for name, data in sorted(captured.items())}
    cert = json.loads(read_regular(packet / 'FREEZE.json'))
    if (cert.get('root') != PILOT_ROOT or cert.get('files') != files
            or __import__('hashlib').sha256(plan.canonical(files)).hexdigest() != PILOT_ROOT):
        raise ValueError('Pilot frozen bytes changed before import')
    return captured


def pilot_module(name, folder, filename, captured):
    module = types.ModuleType(name)
    module.__file__ = str(folder / filename)
    exec(compile(captured['code/' + filename], module.__file__, 'exec'), module.__dict__)
    return module


def pilot_gate(bundle):
    folder = Path(__file__).parent.parent / 'followups'
    captured = verified_pilot_bytes(folder)
    old = pilot_module('immutable_pilot_epoch', folder, 'epoch.py', captured)
    old.verify_packet(folder / 'F2-pilot', PILOT_ROOT)
    ledger = ROOT_BASE / PILOT_ROOT / 'spending-ledger.json'
    if plan.sha(ledger) != PILOT_LEDGER_SHA:
        raise ValueError('Completed pilot ledger changed')
    coverage = pilot_module('immutable_pilot_coverage', folder, 'pilot_coverage.py', captured)
    coverage.epoch = old
    report = coverage.report(folder / 'F2-pilot', PILOT_ROOT, bundle, ledger)
    if __import__('hashlib').sha256(plan.canonical(report) + b'\n').hexdigest() != PILOT_COVERAGE_SHA:
        raise ValueError('Pinned pilot coverage differs')
    if not report['remainder_gate_passed']:
        raise ValueError('Pilot coverage gate failed')
    return report


def stage_guard(packet, manifest, seed, rows, bundle, *, authenticate=True):
    import ancestry,missing,policy
    pilot_gate(bundle)
    if manifest.get('stage')!='F2-second-continuation' or manifest['pull']!='F2':
        raise ValueError('Only exact F2 second continuation enabled')
    policy.load(packet,manifest,rows)
    cert=json.loads((Path(packet)/'missing-certificate.json').read_text())
    ancestry.verify_first(bundle,authenticate=authenticate)
    ancestry.verify_second(cert,bundle,expected_commit=source_executor(bundle).checkout_commit(packet),authenticate=authenticate)
    if seed['root']!=missing.ORIGINAL_ROOT or seed['ledger_sha256']!=cert['post_ledger_sha256']:
        raise ValueError('Exact second partial predecessor required')
    state=json.loads(Path(seed['ledger_path']).read_text())
    _,_,original_rows=missing.original()
    want={r['request_id'] for r in original_rows if r['max_new_credits'] and r['request_id'] not in state['attempts']}
    if {r['request_id'] for r in rows if r['max_new_credits']}!=want or len(want)!=1186 or manifest['new_credits']!=23720:
        raise ValueError('Exact unsent list/cap differs')
    proofs=ancestry.reuse(seed,rows,bundle)
    if len(proofs)!=587 or sum(a['status']=='missing' for a in proofs.values())!=6:
        raise ValueError('All 581 valid and six missing ancestor slots required')


def source_executor(bundle):
    cert = json.loads((bundle / 'FREEZE.json').read_text())
    if any(p.is_symlink() for p in bundle.rglob('*')):
        raise ValueError('Frozen source cannot contain symlinks')
    paths = {str(p.relative_to(bundle)): plan.sha(p) for p in bundle.rglob('*')
             if p.is_file() and p != bundle / 'FREEZE.json'}
    if paths != cert['file_sha256']:
        raise ValueError('Completed frozen source bytes differ')
    plan.verify_source(bundle)
    spec = importlib.util.spec_from_file_location('reviewed_v4_executor', bundle / 'executor.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module



def matches(row, raw_roots):
    return sorted({p.resolve() for raw in raw_roots
        for p in (Path(raw)/row['sport']/row['source']).glob('*/'+row['cache_key']+'.parquet')})

def bindings(packet):
    if any(p.is_symlink() or p.is_dir() for p in packet.iterdir()):
        raise ValueError('Packet must contain regular immediate files only')
    fixed = {f'code/{p.name}': p for p in Path(__file__).parent.glob('*.py')}
    fixed.update({p.name: p for p in packet.iterdir() if p.is_file() and p.name != 'FREEZE.json'})
    return {name: plan.sha(path) for name, path in sorted(fixed.items())}


def freeze(packet):
    files = bindings(packet)
    root = __import__('hashlib').sha256(plan.canonical(files)).hexdigest()
    (packet / 'FREEZE.json').write_bytes(plan.canonical({'root': root, 'files': files}) + b'\n')
    return root


def verify_packet(packet, root):
    cert = json.loads((packet / 'FREEZE.json').read_text())
    files = bindings(packet)
    if files != cert['files'] or __import__('hashlib').sha256(plan.canonical(files)).hexdigest() != root or cert['root'] != root:
        raise ValueError('Epoch root or frozen bytes changed')
    manifest = json.loads((packet / 'manifest.json').read_text())
    rows = json.loads((packet / 'requests.json').read_text())
    if (manifest['request_count'] != len(rows) or len({r['request_id'] for r in rows}) != len(rows)
            or manifest['request_set_sha256'] != __import__('hashlib').sha256(plan.canonical(rows)).hexdigest()
            or manifest['request_list_sha256'] != plan.sha(packet / 'request-list.csv')
            or manifest['new_credits'] != sum(r['max_new_credits'] for r in rows)):
        raise ValueError('Exact epoch manifest differs')
    if manifest['pull'] not in plan.SPECS or manifest['new_credits'] > manifest['planning_ceiling']:
        raise ValueError('Unreviewed pull or planning ceiling')
    if manifest['scope_seasons'] != list(plan.SPECS[manifest['pull']][0]) or len(set(manifest['books'])) != 10:
        raise ValueError('Unreviewed seasons or books')
    for row in rows:
        expected = plan.request(row['sport'], row['event_id'], plan.ts(row['requested_utc']),
                                row['params']['markets'], row['params']['bookmakers'].split(','))
        if (any(row[k] != expected[k] for k in ('request_id', 'cache_key', 'path', 'params', 'max_credits'))
                or row['priority'] != 1 or row['retry_allowance'] != 0 or row['sealed']
                or row['source'] != expected['source'] or row['sport'] != plan.NFL
                or not row['seasons'] or not set(row['seasons']) <= set(manifest['scope_seasons'])
                or row['max_new_credits'] not in (0, row['max_credits'])
                or row['params']['markets'] != plan.SPECS[manifest['pull']][1]
                or row['params']['bookmakers'].split(',') != manifest['books']
                or plan.ts(row['requested_utc']).year > 2026
                or (row['max_new_credits'] == 0 and (not row['cache_source'] or not row['cache_sha256']))):
            raise ValueError('Unreviewed request identity/cost/scope')
    opportunities = json.loads((packet / 'opportunities.json').read_text())
    ids = {o['opportunity_id'] for o in opportunities}
    if len(ids) != manifest['opportunity_count'] or len(ids) != len(opportunities):
        raise ValueError('Opportunity denominator differs')
    by_request = {r['request_id']: r for r in rows}
    for op in opportunities:
        if op['status'] == 'planned':
            row = by_request.get(op['request_id'])
            if not row or op['opportunity_id'] not in row['opportunities'] or op['requested_utc'] != row['requested_utc']:
                raise ValueError('Opportunity binding differs')
            if not (plan.ts(op['binding_observed_utc']) <= plan.ts(op['requested_utc']) <
                    min(plan.ts(op['provider_kickoff_utc']), plan.ts(op['anchor_utc']))):
                raise ValueError('Unsafe opportunity clock')
    if any(not r['opportunities'] or not set(r['opportunities']) <= ids for r in rows):
        raise ValueError('Unaccounted request')
    import csv
    with (packet / 'request-list.csv').open(newline='') as f:
        csv_rows = list(csv.DictReader(f))
    expected_csv = [{'request_id': r['request_id'], 'sport': r['sport'], 'event_id': r['event_id'],
                     'requested_utc': r['requested_utc'], 'markets': r['params']['markets'],
                     'bookmakers': r['params']['bookmakers'], 'max_new_credits': str(r['max_new_credits'])} for r in rows]
    if csv_rows != expected_csv:
        raise ValueError('CSV differs from executable request set')
    return manifest, rows



def partial_certificate():
    return json.loads((Path(__file__).parent/'F2-second-continuation/missing-certificate.json').read_text())


def seed_state(seed,rows,seen=None):
    import ancestry
    return ancestry.seed_state(seed,rows,seen)


def checkout_clean(packet):
    import subprocess
    paths = [p for p in packet.iterdir() if p.is_file()]
    paths += list(Path(__file__).parent.glob('*.py'))
    repo = subprocess.check_output(['git', '-C', str(packet), 'rev-parse', '--show-toplevel'], text=True).strip()
    relative = [str(p.resolve().relative_to(repo)) for p in paths]
    subprocess.run(['git', '-C', repo, 'ls-files', '--error-unmatch', '--', *relative],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(['git', '-C', repo, 'diff', '--exit-code', 'HEAD', '--', *relative],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def verify_source_plan(packet, bundle, manifest, rows):
    inputs = plan.verify_source(bundle)
    if manifest['source_bundle_root'] != plan.SOURCE_ROOT or inputs != manifest['source_input_sha256']:
        raise ValueError('Selection source provenance differs')
    cfg = json.loads((bundle / 'protocol.json').read_text())
    expected, ops = plan.plan(manifest['pull'], json.loads((bundle / 'canonical-games.json').read_text()),
                              json.loads((bundle / 'provider-observations.json').read_text()), cfg['book_panel'])
    if manifest.get('stage') == 'pilot':
        if manifest['pull'] != 'F2':
            raise ValueError('Only F2 pilot reviewed')
        expected, ops = plan.pilot_subset(expected, ops)
    if json.loads((packet / 'opportunities.json').read_text()) != ops or len(expected) != len(rows):
        raise ValueError('Frozen opportunity selection differs from source algorithm')
    cache_fields = {'max_new_credits', 'cache_source', 'cache_sha256'}
    for got, want in zip(rows, expected):
        if {k: v for k, v in got.items() if k not in cache_fields} != {k: v for k, v in want.items() if k not in cache_fields}:
            raise ValueError('Frozen request selection differs from source algorithm')


def event_valid(row, record, base, protocol):
    if (record['cache_key'] != row['cache_key'] or record['sport'] != row['sport']
            or record['source'] != row['source'] or record['url'] != plan.BASE + row['path']
            or json.loads(record['params_json']) != row['params']):
        raise base.Halt('Response identity differs')
    headers = json.loads(record['headers_json'])
    for field in ('x-requests-last', 'x-requests-used', 'x-requests-remaining'):
        base.integer(headers.get(field))
    if record['http_status'] != 200:
        raise base.Halt('HTTP response requires approved missing reconciliation')
    body = json.loads(record['body'])
    if not isinstance(body.get('data'), dict) or body['data'].get('id') != row['event_id'] or body['data'].get('sport_key') != row['sport']:
        raise base.Halt('Historical event identity differs')
    try:
        stamp, prev, nxt = [plan.ts(body[k]) for k in ('timestamp', 'previous_timestamp', 'next_timestamp')]
    except (ValueError, KeyError, TypeError):
        raise base.Halt('Historical event clock missing') from None
    if not prev < stamp < nxt or not 0 <= (plan.ts(row['requested_utc']) - stamp).total_seconds() <= protocol['price_row_eligibility']['maximum_snapshot_lag_seconds']:
        raise base.Halt('Historical event snapshot timing invalid')


def event_ledger(base, missing_policy):
    class EventLedger(base.Ledger):
        def save(self):
            super().save()
            pending=self.state.get('pending')
            if pending and self.state['attempts'][pending].get('send_started') and hasattr(self,'checkpoint'):
                emitted=getattr(self,'_send_checkpoints',set())
                if pending not in emitted:
                    emitted.add(pending);self._send_checkpoints=emitted
                    self.checkpoint('after_send_started')
        def complete(self, row, record, path):
            if self.state['pending'] != row['request_id']:
                raise base.Halt('No durable event reservation')
            if record['http_status'] == 404:
                import policy
                headers, used, remaining = policy.valid(row, record, missing_policy, base)
                if sum(a['status']=='missing' for a in self.state['attempts'].values()) >= missing_policy['max_missing']:
                    raise base.Halt('Prospective missing bound exceeded')
                self.measure_counters(used, remaining, self.billed()-self.state['epoch']['start_billed'])
                receipt = self.folder/'receipts'/(row['request_id']+'.json')
                base.atomic(receipt, {'request_id':row['request_id'],'cache_key':row['cache_key'],
                    'record_sha256':plan.sha(path),'headers':headers,'record':record,'status':'missing',
                    'reason':'exact approved requested event slot absent; full reservation retained; no resend',
                    'missing_policy_sha256':policy.sha(missing_policy)})
                getattr(self,'checkpoint',lambda _:None)('after_receipt_durability')
                self.state['attempts'][row['request_id']].update(status='missing',billed_credits=0,
                    response_path=str(Path(path).resolve()),response_sha256=plan.sha(path),
                    receipt_sha256=plan.sha(receipt),missing_policy_sha256=policy.sha(missing_policy))
                self.state['provider_used'],self.state['provider_remaining']=used,remaining
                self.state['pending']=None
                self.save()
                return
            event_valid(row, record, base, self.protocol)
            headers = json.loads(record['headers_json'])
            last, used, remaining = [base.integer(headers.get(k)) for k in ('x-requests-last', 'x-requests-used', 'x-requests-remaining')]
            if last > row['max_new_credits']:
                raise base.Halt('Event billed above reserved upper bound')
            self.measure_counters(used, remaining, self.billed() - self.state['epoch']['start_billed'] + last)
            receipt = self.folder / 'receipts' / f"{row['request_id']}.json"
            base.atomic(receipt, {'request_id': row['request_id'], 'cache_key': row['cache_key'],
                                  'record_sha256': plan.sha(path), 'headers': headers, 'record': record})
            getattr(self, 'checkpoint', lambda _: None)('after_receipt_durability')
            self.state['attempts'][row['request_id']].update(status='completed', billed_credits=last,
                response_path=str(Path(path).resolve()), response_sha256=plan.sha(path), receipt_sha256=plan.sha(receipt))
            self.state['provider_used'], self.state['provider_remaining'] = used, remaining
            self.state['pending'] = None
            self.save()
    return EventLedger


def run(packet, root, bundle, authorization, *, key, fake_session=None, checkpoint=lambda _: None):
    packet, bundle = Path(packet).resolve(), Path(bundle).resolve()
    manifest, rows = verify_packet(packet, root)
    base = source_executor(bundle)
    seed = json.loads((packet / 'seed.json').read_text())
    seed_state(seed, rows)
    stage_guard(packet, manifest, seed, rows, bundle, authenticate=fake_session is None)
    verify_source_plan(packet, bundle, manifest, rows)
    import policy
    missing_policy = policy.load(packet, manifest, rows)
    checkout_clean(packet)
    source_books = json.loads((bundle / 'protocol.json').read_text())['book_panel']
    if manifest['books'] != source_books:
        raise base.Halt('Frozen book panel differs')
    runtime = base.runtime_path(root)
    base.execution_context(packet, root, runtime)
    if base.current_runtime() != json.loads((bundle / 'runtime-lock.json').read_text()):
        raise base.Halt('Runtime differs from reviewed lock')
    m = {**manifest, 'requests': rows, 'new_credits_by_priority': {'1': manifest['new_credits']}}
    base.validate_authorization(authorization, m, root, base.checkout_commit(packet))
    if fake_session is None:
        base.verify_live_hub_comment(authorization)
    seed = json.loads((packet / 'seed.json').read_text())
    prior = seed_state(seed, rows)
    protocol = json.loads((bundle / 'protocol.json').read_text())
    probe = json.loads((bundle / 'probe-spending-ledger.json').read_text())
    # Serializes all follow-up epochs. The completed source run is exhausted and never executed here.
    ROOT_BASE.mkdir(parents=True, exist_ok=True)
    global_lock = (ROOT_BASE / 'followup-purchase.lock').open('a')
    ledger = client = None
    try:
        fcntl.flock(global_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        seed_state(seed, rows)
        stage_guard(packet, manifest, seed, rows, bundle, authenticate=fake_session is None)
        cache_info = json.loads((packet / 'cache-reconciliation.json').read_text())
        if cache_info['status'] != 'reconciled' or cache_info['request_set_sha256'] != manifest['request_set_sha256']:
            raise base.Halt('Cache reconciliation missing or stale')
        for row in rows:
            hits = matches(row, cache_info['raw_roots'])
            if row['max_new_credits'] and hits:
                raise base.Halt('New overlapping cache appeared; review list without repurchase')
            if not row['max_new_credits'] and any(plan.sha(p) != row['cache_sha256'] for p in hits):
                raise base.Halt('Reused cache conflict')
            if not row['max_new_credits'] and Path(row['cache_source']).resolve() not in hits:
                raise base.Halt('Reuse outside inspected raw stores')
        # A stopped/pending epoch cannot be escaped via a new root, even if it is not
        # named by the proposed seed. Only non-secret global ledgers are inspected.
        for path in ROOT_BASE.glob('*/spending-ledger.json'):
            if path.parent.name == root:
                continue
            state = json.loads(path.read_text())
            if state.get('pending') or state.get('stopped'):
                raise base.Halt('Unresolved global predecessor; no new-root escape')
        existing = runtime / 'spending-ledger.json'
        if existing.exists():
            state = json.loads(existing.read_text())
            if state.get('pending') or state.get('stopped'):
                raise base.Halt('Pending/stopped extension cannot recover automatically')
            for rid, attempt in state['attempts'].items():
                if (attempt['status'] not in ('completed', 'missing')
                        or plan.sha(Path(attempt['response_path'])) != attempt['response_sha256']
                        or plan.sha(runtime / 'receipts' / (rid + '.json')) != attempt['receipt_sha256']):
                    raise base.Halt('Completed event evidence missing/changed; no repurchase')
                if attempt['status'] == 'missing':
                    _, read_missing, *_ = base.vendor_imports(bundle, runtime)
                    row = next(r for r in rows if r['request_id']==rid)
                    policy.valid(row, read_missing(Path(attempt['response_path'])), missing_policy, base)
                    if attempt.get('missing_policy_sha256') != policy.sha(missing_policy):
                        raise base.Halt('Terminal missing policy evidence differs')
        base.validate_reconciliation(authorization.get('account_reconciliation'), root)
        if 'pre_run_other_usage_budget_debit' in authorization['account_reconciliation']:
            raise base.Halt('Stage cannot override fresh account usage debit')
        ceiling = authorization['account_reconciliation']['max_baseline_used']
        line = f'APPROVED account ceiling: max-baseline-used {ceiling}, root {root}'
        if line not in authorization['hub_go_ahead']['comment_body'].splitlines():
            raise base.Halt('Stage account ceiling must be authenticated by hub comment')
        if policy.approval_line(missing_policy, root) not in authorization['hub_go_ahead']['comment_body'].splitlines():
            raise base.Halt('Prospective missing policy must be authenticated by hub comment')
        if authorization['account_reconciliation'].get('account_only_recovery'):
            raise base.Halt('Automatic account-only recovery disabled for extension')
        import missing
        cert = json.loads((packet / 'missing-certificate.json').read_text())
        offline_auth_path = ROOT_BASE / missing.ORIGINAL_ROOT / ('missing-approval-' + cert['proposal_sha256'] + '.json')
        offline_auth = json.loads(offline_auth_path.read_text())
        missing.validate_approval(offline_auth, cert, base)
        if fake_session is None:
            base.verify_live_hub_comment(offline_auth)
        import ancestry
        proofs=ancestry.reuse(seed,rows,bundle)
        base.register_runtime(runtime, root, authorization)
        ledger = event_ledger(base, missing_policy)(runtime, protocol, m, root, authorization, probe)
        prior_seed = ledger.state.get('predecessor_seed')
        if prior_seed is not None and prior_seed != seed:
            raise base.Halt('Predecessor seed changed; never reset history')
        ledger.state['predecessor_seed'] = seed
        ledger.state['other_usage_reserved'] = max(ledger.state['other_usage_reserved'], prior)
        ledger.save()
        ledger.budget_check(0)
        RawCache, read_record, BulkClient, Call, new_session, remember_secret, scrub = base.vendor_imports(bundle, runtime)
        ledger.checkpoint = checkpoint
        key = key() if callable(key) else key
        if not key or len(key) < 8:
            raise base.Halt('Missing API key')
        remember_secret(key)
        session = base.GuardedSession(fake_session or new_session(), ledger, rows)
        session.ledger_key = key
        cache = RawCache(runtime / 'data/raw')
        client = BulkClient(cache, max_credits=manifest['new_credits'] - ledger.reserved(),
                           floor=protocol['budgets']['account_reserve_floor'], rate_per_sec=4,
                           max_retries=0, session=session, api_key=key, alarm_margin=5000)
        if fake_session:
            client.limiter.wait = lambda: None
        account = client.account()
        ledger.account(base.integer(account['used']), base.integer(account['remaining']))
        base.atomic(runtime / 'run-manifest.json', {'epoch_root': root, 'commit': authorization['execution_commit'],
                    'frozen_source_root': plan.SOURCE_ROOT, 'seed': seed, 'runtime': base.current_runtime(),
                    'pull': manifest['pull'], 'stage': manifest['stage'], 'missing_certificate': cert, 'exact_missing_policy': missing_policy,
                    'request_set_sha256': manifest['request_set_sha256'],
                    'scope': 'exact event-odds rows only; no outcomes; no retries; no replan'})
        for row in rows:
            attempt = ledger.state['attempts'].get(row['request_id'])
            cached = cache.lookup(row['sport'], row['source'], row['cache_key'])
            if attempt:
                if (attempt['status'] not in ('completed', 'missing') or cached is None
                        or plan.sha(cached) != attempt['response_sha256']
                        or plan.sha(runtime / 'receipts' / f"{row['request_id']}.json") != attempt['receipt_sha256']):
                    raise base.Halt('Completed event evidence missing/changed; no repurchase')
                continue
            if row['max_new_credits'] == 0:
                source = Path(row['cache_source'])
                if plan.sha(source) != row['cache_sha256']:
                    raise base.Halt('Reused cache changed')
                proof=proofs[row['request_id']]
                if proof['status']=='missing':
                    ledger.state.setdefault('accepted_missing_reuse',{})[row['request_id']]=proof['proof_sha256']
                    ledger.save()
                    continue
                event_valid(row,read_record(source),base,protocol)
                ledger.state['cache_reuse'][row['request_id']] = row['cache_sha256']
                ledger.save()
                continue
            if cached is not None:
                raise base.Halt('Unreconciled existing cache; no repurchase')
            call = Call(manifest['pull'], row['sport'], row['source'], row['path'], tuple(sorted(row['params'].items())),
                        plan.ts(row['requested_utc']), row['max_credits'], False, row['event_id'], row['sport'])
            if call.key != row['cache_key']:
                raise base.Halt('Cache identity mismatch')
            ledger.reserve(row)
            checkpoint('after_reservation')
            record = client.fetch(call)
            checkpoint('after_transport')
            cached = cache.lookup(row['sport'], row['source'], row['cache_key'])
            if cached is None:
                raise base.Halt('Event response not cached')
            with cached.open('rb') as f:
                os.fsync(f.fileno())
            base.durable_directory(cached.parent)
            checkpoint('after_cache_durability')
            ledger.complete(row, record, cached)
            checkpoint('after_terminal_ledger')
            if len(ledger.state['attempts']) % 25 == 0:
                print(json.dumps({'completed': len(ledger.state['attempts']), 'reserved': ledger.reserved(),
                                  'billed': ledger.billed()}), flush=True)
        verify_packet(packet, root)
        seed_state(seed, rows)
        ledger.state['status'] = 'event_epoch_complete'
        ledger.save()
        return {'status': ledger.state['status'], 'new_reserved': ledger.reserved(), 'new_billed': ledger.billed(),
                'cumulative_reserved': 1687 + ledger.state['other_usage_reserved'] + ledger.reserved(),
                'provider_used': ledger.state['provider_used'], 'provider_remaining': ledger.state['provider_remaining']}
    except BaseException:
        if ledger:
            ledger.halt('Follow-up event epoch stopped; reservations retained; review before recovery')
        raise
    finally:
        if client:
            client.session.close()
        if ledger:
            ledger.close()
        global_lock.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--packet', type=Path, required=True)
    parser.add_argument('--root', required=True)
    parser.add_argument('--bundle', type=Path, required=True)
    parser.add_argument('--authorization', type=Path)
    parser.add_argument('--confirm', action='store_true')
    parser.add_argument('--key-file', type=Path)
    args = parser.parse_args()
    if not args.confirm:
        manifest, _ = verify_packet(args.packet, args.root)
        print(json.dumps({'offline': True, 'request_count': manifest['request_count'], 'new_credits': manifest['new_credits']}))
        return
    if not args.authorization or not args.key_file:
        raise SystemExit('Exact authorization and key-file required')
    def load_key():
        from dotenv import dotenv_values
        return dotenv_values(args.key_file).get('ODDS_API_KEY')
    try:
        result = run(args.packet, args.root, args.bundle, json.loads(args.authorization.read_text()), key=load_key)
        print(json.dumps(result, indent=2))
    except BaseException:
        # The detailed transport exception may embed a key. Safe ledger/receipts hold diagnosis.
        raise SystemExit('STOPPED: reservations retained; inspect local ledger/receipts; never automatically retry') from None


if __name__ == '__main__':
    sys.dont_write_bytecode = True
    main()
