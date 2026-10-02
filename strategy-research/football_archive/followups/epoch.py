"""A separately frozen event-odds epoch using v4's reviewed reservation/accounting library.

Never edits the completed bundle/ledger. New epochs pin the predecessor ledger and carry its full
probe/reservation/external debit. Offline by default; no transport without exact live hub approval.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import fcntl
from pathlib import Path
import sys

import plan

ROOT_BASE = Path.home() / 'Library/Application Support/ValueFinder/football-acquisition-state'
LIVE = Path.home() / 'code/value-finder'
SEED_HASH = 'eb9e93e354babef2be73ddaa13ea6e2913c58eaaff706ed4e78aec1381636190'
PRIOR_ROOT = plan.SOURCE_ROOT


def source_executor(bundle):
    cert = json.loads((bundle / 'FREEZE.json').read_text())
    paths = {str(p.relative_to(bundle)): plan.sha(p) for p in bundle.rglob('*')
             if p.is_file() and p.name != 'FREEZE.json'}
    if paths != cert['file_sha256']:
        raise ValueError('Completed frozen source bytes differ')
    plan.verify_source(bundle)
    spec = importlib.util.spec_from_file_location('reviewed_v4_executor', bundle / 'executor.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def bindings(packet):
    fixed = {'code/epoch.py': Path(__file__), 'code/plan.py': Path(plan.__file__)}
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
    for row in rows:
        expected = plan.request(row['sport'], row['event_id'], plan.ts(row['requested_utc']),
                                row['params']['markets'], row['params']['bookmakers'].split(','))
        if (any(row[k] != expected[k] for k in ('request_id', 'cache_key', 'path', 'params', 'max_credits'))
                or row['priority'] != 1 or row['retry_allowance'] != 0 or row['sealed']
                or row['sport'] != plan.NFL or not set(row['seasons']) <= {2023, 2024, 2025}
                or row['max_new_credits'] not in (0, row['max_credits'])
                or row['params']['markets'] not in {v[1] for v in plan.SPECS.values()}):
            raise ValueError('Unreviewed request identity/cost/scope')
    return manifest, rows


def seed_state(seed, rows):
    path = Path(seed['ledger_path'])
    if plan.sha(path) != seed['ledger_sha256']:
        raise ValueError('Predecessor ledger changed')
    state = json.loads(path.read_text())
    if state['bundle_root_sha256'] != seed['root'] or state['pending'] or state['stopped']:
        raise ValueError('Unresolved predecessor ledger')
    if state['status'] not in ('recent_complete_stopped_before_older', 'event_epoch_complete') or state['probe_credits'] != 1687:
        raise ValueError('Incomplete predecessor epoch')
    prior = sum(a['reserved_credits'] for a in state['attempts'].values()) + state['other_usage_reserved']
    if seed['cumulative_debit_without_probe'] != prior or seed['probe_credits'] != 1687:
        raise ValueError('Cumulative seed debit differs')
    duplicate = {r['request_id'] for r in rows if r['max_new_credits']} & set(state['attempts'])
    if duplicate:
        raise ValueError('Prior request cannot be bought twice')
    return prior


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


def event_ledger(base):
    class EventLedger(base.Ledger):
        def complete(self, row, record, path):
            if self.state['pending'] != row['request_id']:
                raise base.Halt('No durable event reservation')
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
    fcntl.flock(global_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    ledger = client = None
    try:
        base.register_runtime(runtime, root, authorization)
        ledger = event_ledger(base)(runtime, protocol, m, root, authorization, probe)
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
                    'scope': 'exact event-odds rows only; no outcomes; no retries; no replan'})
        for row in rows:
            attempt = ledger.state['attempts'].get(row['request_id'])
            cached = cache.lookup(row['sport'], row['source'], row['cache_key'])
            if attempt:
                if (attempt['status'] != 'completed' or cached is None
                        or plan.sha(cached) != attempt['response_sha256']
                        or plan.sha(runtime / 'receipts' / f"{row['request_id']}.json") != attempt['receipt_sha256']):
                    raise base.Halt('Completed event evidence missing/changed; no repurchase')
                continue
            if row['max_new_credits'] == 0:
                source = Path(row['cache_source'])
                if plan.sha(source) != row['cache_sha256']:
                    raise base.Halt('Reused cache changed')
                event_valid(row, read_record(source), base, protocol)
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
            ledger.complete(row, record, cached)
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
