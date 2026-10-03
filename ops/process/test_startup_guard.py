"""Portable actual-function regression with synthetic adapters only.

The unmodified run function is compiled from repository source without executing
module imports. Every fresh bootstrap instance is guarded. This exercises startup
ordering, not native closure authentication or the paid execution path.
"""
import ast
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch
import socket

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'strategy-research/coverage-pass-execution-v1/orchestration.py'


class BoundaryReached(Exception): pass


def actual_run(namespace):
    parsed = ast.parse(SOURCE.read_bytes(), filename=str(SOURCE))
    run = next(n for n in parsed.body if isinstance(n, ast.FunctionDef) and n.name == 'run')
    # No copied implementation and no import of a historical executor/bootstrap.
    exec(compile(ast.Module(body=[run], type_ignores=[]), str(SOURCE), 'exec'), namespace)
    return namespace['run']


class StartupRegression(unittest.TestCase):
    def exercise(self, scenario):
        import fcntl
        with tempfile.TemporaryDirectory() as name:
            folder = Path(name)
            runtime = folder / 'synthetic-epoch'
            root, commit = 'a'*64, 'b'*40
            events, fresh = [], []
            snapshot = {'ledgers': {}, 'registrations': {}}
            cache = {'probe_bundle_root': str(folder / 'probe'), 'inventory_sha256': 'f'*64,
                     'raw_roots': [str((folder / 'probe/data/raw').absolute()),
                                   str((Path.home() / 'code/value-finder/sharp-markets/data/raw').absolute())]}
            documents = {'protocol.json': {'execution_status': 'draft' if scenario == 'draft' else 'reviewed_for_execution'},
                         'manifest.json': {'max_new_credits': 0}, 'requests.json': [], 'policy.json': {},
                         'baseline.json': {'expected_global_snapshot': snapshot, 'base_snapshot': snapshot,
                                           'pilot_bindings': {}, 'historical_bindings': {}},
                         'overlap.json': cache, 'mappings.json': []}
            data = {n: json.dumps(v).encode() for n, v in documents.items()}
            data['source/FREEZE.json'] = b'{}'
            source = {'runtime-lock.json': b'{}', 'input-provenance.json': b'{"raw_probe_sources":[]}'}
            def forbidden(kind):
                def fail(*args, **kwargs):
                    events.append(kind)
                    raise AssertionError('blocked side effect: ' + kind)
                return fail
            def stop_registration(*args):
                events.append('registration-boundary')
                raise BoundaryReached()
            def verified(*args):
                events.append('verify')
                if scenario == 'bootstrap': raise ValueError('invalid closure')
                base = SimpleNamespace(checkout_commit=lambda _: commit, runtime_path=lambda _: runtime,
                                       execution_context=lambda *a: None, current_runtime=lambda: {},
                                       RUNTIME_BASE=folder, register_runtime=stop_registration,
                                       Ledger=forbidden('ledger'), Halt=RuntimeError)
                fresh.append(base)
                values = dict(data)
                if scenario == 'drift' and len(fresh) > 1: values['changed-source'] = b'x'
                return SimpleNamespace(packet=lambda *a: None, residual=lambda *a: None), base, values, source, forbidden('cache-import')
            def authority(*args):
                events.append('authority')
                if scenario == 'revoked': raise ValueError('revoked')
            capture = SimpleNamespace(identity=lambda x: hashlib.sha256(json.dumps(x, sort_keys=True).encode()).hexdigest(),
                                      digest=lambda x: hashlib.sha256(x).hexdigest(),
                                      read=forbidden('native-read'), sha=forbidden('native-hash'))
            env = {'bootstrap': SimpleNamespace(verified=verified), 'json': json, 'Path': Path,
                   'capture': capture, 'authority': SimpleNamespace(check=authority), 'fcntl': fcntl,
                   'baseline': SimpleNamespace(verify_base=forbidden('native-baseline')),
                   'evidence': SimpleNamespace(global_union=lambda *a, **kw: (snapshot, {'conservative_debit': 207386}),
                                               authenticate_reuse=lambda *a, **kw: None),
                   'overlap': SimpleNamespace(check=lambda *a, **kw: None),
                   'transport': SimpleNamespace(pilot_ledger=forbidden('ledger')),
                   'execution': SimpleNamespace(prepared_loop=forbidden('paid-loop'))}
            run = actual_run(env)
            with patch.object(socket, 'socket', forbidden('network')):
                if scenario == 'boundary':
                    with self.assertRaises(BoundaryReached):
                        run(folder / 'packet', root, folder / 'bundle', {},
                            key_factory=forbidden('credential'), http_factory=forbidden('http'))
                    self.assertEqual(events[-1], 'registration-boundary')
                    self.assertGreaterEqual(len(fresh), 3)
                    self.assertEqual(len({id(base) for base in fresh}), len(fresh))
                    # Every freshly produced executor has the blocker, not just an outer instance.
                    self.assertTrue(all(base.register_runtime is stop_registration for base in fresh))
                else:
                    with self.assertRaises(ValueError):
                        run(folder / 'packet', root, folder / 'bundle', {},
                            key_factory=forbidden('credential'), http_factory=forbidden('http'))
                    self.assertNotIn('registration-boundary', events)
            self.assertFalse(set(events) & {'credential', 'http', 'network', 'ledger', 'native-read',
                                           'native-hash', 'native-baseline', 'paid-loop', 'cache-import'})
            # Only the actual startup's temporary shared-lock stand-in may be created.
            self.assertLessEqual({p.relative_to(folder).as_posix() for p in folder.rglob('*')},
                                 {'followup-purchase.lock'})

    def test_verified_startup_reaches_guarded_registration_before_key(self): self.exercise('boundary')
    def test_invalid_closure_prevents_registration(self): self.exercise('bootstrap')
    def test_draft_packet_prevents_registration(self): self.exercise('draft')
    def test_revoked_authority_prevents_registration(self): self.exercise('revoked')
    def test_source_drift_under_lock_prevents_registration(self): self.exercise('drift')

    def test_actual_bootstrap_checks_individual_bytes_before_execution(self):
        import types
        path = ROOT / 'strategy-research/coverage-pass-execution-v1/bootstrap.py'
        parsed = ast.parse(path.read_bytes(), filename=str(path))
        functions = [n for n in parsed.body if isinstance(n, ast.FunctionDef) and n.name in {'sha', 'module'}]
        namespace = {'hashlib': hashlib, 'types': types}
        exec(compile(ast.Module(body=functions, type_ignores=[]), str(path), 'exec'), namespace)
        malicious = b'raise AssertionError("executed before verification")'
        with self.assertRaisesRegex(ValueError, 'pin differs'):
            namespace['module'](malicious, 'synthetic.py', 'synthetic', '0'*64)
        good = b'value = 7'
        module = namespace['module'](good, 'synthetic.py', 'synthetic', hashlib.sha256(good).hexdigest())
        self.assertEqual(module.value, 7)


if __name__ == '__main__': unittest.main()
