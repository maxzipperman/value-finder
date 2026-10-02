import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import os
from unittest.mock import patch
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('guard', Path(__file__).with_name('process_guard.py'))
g = importlib.util.module_from_spec(spec)
spec.loader.exec_module(g)


class Guards(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        for name, text in {'stage/main.py': 'import json\n', 'stage/requests.json': '[]',
                           'stage/runtime.json': '{}', 'stage/eligibility.json': '{}', 'stage/policy.json': '{}',
                           'stage/tests/test_main.py': '# test', 'stage/README.md': '# Explain'}.items():
            p = self.root / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text)
        self.spec = {'version': 1, 'scopes': ['stage'], 'files': {
            'stage/main.py': 'executable', 'stage/requests.json': 'requests',
            'stage/runtime.json': 'dependency', 'stage/eligibility.json': 'eligibility', 'stage/policy.json': 'policy',
            'stage/tests/test_main.py': 'test', 'stage/README.md': 'documentation'}}

    def plan(self):
        return {'version': 1, 'request_list_sha256': 'a' * 64,
                'requests': [{'id': 'b'*64, 'max_credits': 30}, {'id': 'c'*64, 'max_credits': 30}],
                'budget': {'new_cap': 60, 'prior_reserved': 20, 'probe': 10, 'other_usage': 5,
                           'cumulative_cap': 95, 'reserve_floor': 100},
                'missing': {'ids': ['b'*64], 'http_status': 404, 'error_code': 'EVENT_NOT_FOUND',
                            'last_cost': 0, 'retain_full_reservation': True, 'retain_denominator': True},
                'restart': {'states': ['clean_stopped', 'complete'], 'automatic_retries': 0,
                            'send_only_untouched': True, 'live_authority_required': True,
                            'global_lock_ledger_required': True},
                'coverage': {'metric': 'fresh_pairs', 'minimum': 0.95,
                             'denominator': 'all_planned_opportunities',
                             'halt_before_next_tranche': True, 'outcome_blind': True}}

    def checkpoint(self):
        return {'purchase_identity': 'd'*64, 'request_list_sha256': 'a'*64,
                'state': 'clean_stopped', 'attempts': {}, 'remaining_credits': 160,
                'coverage_passed': None}

    def restart(self, plan=None, checkpoint=None, **kw):
        return g.restart_candidates(plan or self.plan(), checkpoint or self.checkpoint(),
                                    purchase_identity='d'*64, live_authority=kw.get('live', True),
                                    shared_lock=kw.get('lock', True))

    def test_support_changes_preserve_purchase_identity(self):
        original = g.content_manifest(self.root, self.spec)
        for name in ['stage/README.md', 'stage/tests/test_main.py']:
            (self.root/name).write_text('# changed')
        checked = g.verify_content(self.root, self.spec, original)
        self.assertTrue(checked['supporting_changed'])
        self.assertEqual(checked['purchase_identity'], original['purchase_identity'])

    def test_each_bound_input_invalidates_identity(self):
        original = g.content_manifest(self.root, self.spec)
        for name in ['stage/main.py', 'stage/requests.json', 'stage/eligibility.json', 'stage/policy.json', 'stage/runtime.json']:
            path = self.root/name
            before = path.read_bytes()
            path.write_bytes(before + b'\n')
            with self.assertRaisesRegex(ValueError, 'content changed'):
                g.verify_content(self.root, self.spec, original)
            path.write_bytes(before)

    def test_new_or_missing_file_rejected(self):
        new = self.root/'stage/surprise.py'
        new.write_text('pass')
        with self.assertRaisesRegex(ValueError, 'undeclared'):
            g.content_manifest(self.root, self.spec)
        new.unlink()
        (self.root/'stage/main.py').unlink()
        with self.assertRaisesRegex(ValueError, 'missing'):
            g.content_manifest(self.root, self.spec)

    def test_symlink_and_path_escape_rejected(self):
        (self.root/'stage/main.py').unlink()
        (self.root/'stage/main.py').symlink_to(self.root/'stage/policy.json')
        with self.assertRaisesRegex(ValueError, 'symlink'):
            g.content_manifest(self.root, self.spec)
        with self.assertRaisesRegex(ValueError, 'path'):
            g.relative('../secrets')

    def test_misclassified_rule_and_program_rejected(self):
        self.spec['files']['stage/main.py'] = 'documentation'
        with self.assertRaisesRegex(ValueError, 'cannot be supporting'):
            g.content_manifest(self.root, self.spec)
        (self.root/'stage/STRATEGY.md').write_text('# rule')
        self.spec['files']['stage/main.py'] = 'executable'
        self.spec['files']['stage/STRATEGY.md'] = 'documentation'
        with self.assertRaisesRegex(ValueError, 'cannot be supporting'):
            g.content_manifest(self.root, self.spec)

    def test_undeclared_local_and_dynamic_import_rejected(self):
        (self.root/'external.py').write_text('pass')
        for code, error in [('import external', 'undeclared local'),
                            ('__import__("external")', 'dynamic'),
                            ('exec("print(1)")', 'dynamic')]:
            (self.root/'stage/main.py').write_text(code)
            with self.assertRaisesRegex(ValueError, error):
                g.content_manifest(self.root, self.spec)

    def test_package_initializer_and_dependency_transitive_import_rejected(self):
        (self.root/'helpers').mkdir()
        (self.root/'helpers/__init__.py').write_text('pass')
        (self.root/'helpers/worker.py').write_text('pass')
        self.spec['scopes'].append('helpers/worker.py')
        self.spec['files']['helpers/worker.py'] = 'dependency'
        (self.root/'stage/main.py').write_text('import helpers.worker')
        with self.assertRaisesRegex(ValueError, 'undeclared local import: helpers/__init__.py'):
            g.content_manifest(self.root, self.spec)
        self.spec['scopes'].append('helpers/__init__.py')
        self.spec['files']['helpers/__init__.py'] = 'dependency'
        (self.root/'external.py').write_text('pass')
        (self.root/'helpers/worker.py').write_text('import external')
        with self.assertRaisesRegex(ValueError, 'undeclared local import: external.py'):
            g.content_manifest(self.root, self.spec)

    def test_from_import_child_package_initializer_rejected(self):
        (self.root/'pkg/sub').mkdir(parents=True)
        (self.root/'pkg/__init__.py').write_text('pass')
        (self.root/'pkg/sub/__init__.py').write_text('pass')
        self.spec['scopes'].append('pkg/__init__.py')
        self.spec['files']['pkg/__init__.py'] = 'dependency'
        (self.root/'stage/main.py').write_text('from pkg import sub')
        with self.assertRaisesRegex(ValueError, 'undeclared local import: pkg/sub/__init__.py'):
            g.content_manifest(self.root, self.spec)
        self.spec['scopes'].append('pkg/sub/__init__.py')
        self.spec['files']['pkg/sub/__init__.py'] = 'dependency'
        g.content_manifest(self.root, self.spec)

    def evidence(self):
        subprocess.run(['git', 'init', '-q', str(self.root)], check=True)
        subprocess.run(['git', '-C', str(self.root), '-c', 'user.name=Test', '-c', 'user.email=test@example.test',
                        'commit', '--allow-empty', '-qm', 'initial'], check=True)
        config = {'version': 1, 'scopes': ['stage/main.py', 'stage/tests/test_main.py',
                                         'stage/policy.json'],
                  'commands': [['{python}', '-c', 'print("ok")']], 'environment': {'PYTHONHASHSEED': '0'}}
        return config, g.run_evidence(self.root, config)

    def test_caller_path_cannot_change_hashed_or_executed_binary(self):
        config, _ = self.evidence()
        fake = self.root/'caller-bin'
        fake.mkdir()
        (fake/'false').write_text('#!/bin/sh\nexit 0\n')
        (fake/'false').chmod(0o755)
        config['commands'] = [['false']]
        with patch.dict(os.environ, {'PATH': str(fake) + os.pathsep + os.defpath}):
            report = g.run_evidence(self.root, config)
        self.assertFalse(report['passed'])
        self.assertEqual(report['inputs']['effective_environment']['PATH'], os.defpath)
        self.assertNotEqual(report['inputs']['command_binaries']['false']['path'], str(fake/'false'))

    def test_changed_effective_binary_and_path_invalidate_evidence(self):
        config, _ = self.evidence()
        folder = self.root/'effective-bin'; folder.mkdir()
        binary = folder/'vf-guard-test-command'
        # Symlink to genuine binaries so the runner binds and executes their bytes.
        binary.symlink_to('/usr/bin/true')
        config['commands'] = [['vf-guard-test-command']]
        config['environment']['PATH'] = str(folder)
        report = g.run_evidence(self.root, config)
        self.assertTrue(report['passed'])
        self.assertEqual(report['inputs']['command_binaries']['vf-guard-test-command']['path'], str(binary))
        binary.unlink(); binary.symlink_to('/usr/bin/false')
        with self.assertRaisesRegex(ValueError, 'mismatch'):
            g.verify_evidence(self.root, config, report)
        self.assertFalse(g.run_evidence(self.root, config)['passed'])
        config['environment']['PATH'] = os.defpath
        with self.assertRaisesRegex(ValueError, 'missing command'):
            g.verify_evidence(self.root, config, report)

    def test_implicit_script_interpreter_and_undeclared_script_rejected(self):
        config, _ = self.evidence()
        script = self.root/'unbound.sh'; script.write_text('#!/bin/sh\nexit 0\n')
        script.chmod(0o755)
        config['commands'] = [[str(script)]]
        with self.assertRaisesRegex(ValueError, 'explicitly bound interpreter'):
            g.evidence_inputs(self.root, config)
        config['commands'] = [['{python}', str(script)]]
        with self.assertRaisesRegex(ValueError, 'outside declared'):
            g.evidence_inputs(self.root, config)

    def test_evidence_reuse_and_unchanged_docs(self):
        config, report = self.evidence()
        (self.root/'stage/README.md').write_text('# docs only')
        self.assertTrue(g.verify_evidence(self.root, config, report)['passed'])

    def test_test_source_dependency_or_command_change_invalidates_evidence(self):
        config, report = self.evidence()
        for name in ['stage/main.py', 'stage/tests/test_main.py', 'stage/policy.json']:
            path = self.root/name
            before = path.read_bytes()
            path.write_bytes(before + b'\n')
            with self.assertRaisesRegex(ValueError, 'mismatch'):
                g.verify_evidence(self.root, config, report)
            path.write_bytes(before)
        for field, value in [('commands', [['{python}', '-c', 'print("different")']]),
                             ('environment', {'PYTHONHASHSEED': '1'})]:
            changed = copy.deepcopy(config)
            changed[field] = value
            with self.assertRaisesRegex(ValueError, 'mismatch'):
                g.verify_evidence(self.root, changed, report)

    def test_tampered_failed_incomplete_evidence_rejected(self):
        config, report = self.evidence()
        bad = copy.deepcopy(report)
        bad['results'][0]['stdout_sha256'] = 'e'*64
        with self.assertRaisesRegex(ValueError, 'integrity'):
            g.verify_evidence(self.root, config, bad)
        for patch in [{'passed': False}, {'results': []}]:
            bad = {**report, **patch}
            bad['evidence_digest'] = g.digest({k: v for k, v in bad.items() if k != 'evidence_digest'})
            with self.assertRaisesRegex(ValueError, 'failed/incomplete'):
                g.verify_evidence(self.root, config, bad)
        failed = copy.deepcopy(config)
        failed['commands'] = [['{python}', '-c', 'raise SystemExit(1)']]
        self.assertFalse(g.run_evidence(self.root, failed)['passed'])

    def test_plan_rejects_duplicates_cap_and_unsafe_policy(self):
        for field, patch in [('requests', [self.plan()['requests'][0]]*2),
                             ('budget', {'new_cap': 59}), ('budget', {'cumulative_cap': 94}),
                             ('missing', {'ids': ['f'*64]}), ('missing', {'retain_denominator': False}),
                             ('restart', {'automatic_retries': 1}), ('coverage', {'outcome_blind': False})]:
            p = self.plan()
            if isinstance(patch, dict): p[field].update(patch)
            else: p[field] = patch
            with self.assertRaises(ValueError): g.validate_plan(p)

    def test_restart_only_untouched_and_no_released_missing_reserve(self):
        cp = self.checkpoint()
        cp['attempts']['b'*64] = {'status': 'allowed_missing', 'reserved': 30, 'billed': 0,
                                  'receipt_verified': True}
        self.assertEqual(self.restart(checkpoint=cp)['untouched_ids'], ['c'*64])
        cp['attempts']['b'*64]['reserved'] = 0
        with self.assertRaises(ValueError): self.restart(checkpoint=cp)

    def test_pending_unverified_unknown_and_revoked_blocked(self):
        for state in ['pending', 'uncertain', 'conflicting']:
            cp = self.checkpoint(); cp['state'] = state
            with self.assertRaises(ValueError): self.restart(checkpoint=cp)
        cp = self.checkpoint()
        cp['attempts']['b'*64] = {'status': 'valid', 'reserved': 30, 'billed': 30,
                                  'receipt_verified': False}
        with self.assertRaises(ValueError): self.restart(checkpoint=cp)
        cp['attempts'] = {'f'*64: {'status': 'valid', 'reserved': 30, 'billed': 30,
                                  'receipt_verified': True}}
        with self.assertRaises(ValueError): self.restart(checkpoint=cp)
        for kw in [{'live': False}, {'lock': False}]:
            with self.assertRaises(ValueError): self.restart(**kw)

    def test_floor_identity_and_coverage_halt(self):
        cp = self.checkpoint(); cp['remaining_credits'] = 159
        with self.assertRaisesRegex(ValueError, 'floor'): self.restart(checkpoint=cp)
        cp = self.checkpoint(); cp['purchase_identity'] = 'e'*64
        with self.assertRaisesRegex(ValueError, 'identity'): self.restart(checkpoint=cp)
        cp = self.checkpoint(); cp['state'] = 'complete'; cp['coverage_passed'] = False
        with self.assertRaisesRegex(ValueError, 'incomplete'): self.restart(checkpoint=cp)
        cp['attempts'] = {r['id']: {'status': 'valid', 'reserved': 30, 'billed': 30,
                                   'receipt_verified': True} for r in self.plan()['requests']}
        self.assertFalse(self.restart(checkpoint=cp)['next_tranche_allowed'])
        cp['coverage_passed'] = True
        self.assertTrue(self.restart(checkpoint=cp)['next_tranche_allowed'])


if __name__ == '__main__':
    unittest.main()
