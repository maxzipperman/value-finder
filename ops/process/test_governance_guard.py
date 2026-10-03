import copy
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
import governance_guard as g


class ReviewGuards(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        subprocess.run(['git', 'init', '-q', str(self.root)], check=True)
        for name, value in {'source.py': 'pass', 'test_source.py': '# test',
                            'lock.json': '{}', 'protocol.md': '# eligibility',
                            '.github/workflows/check.yml': '# CI', 'STATUS.md': '# status', 'explanation.md': '# prose',
                            g.POLICY: json.dumps({'version': 1, 'explanatory_paths': ['explanation.md']})}.items():
            self.write(name, value)
        self.base = self.save()

    def write(self, name, value):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value)

    def save(self):
        g.git(self.root, 'add', '.')
        g.git(self.root, '-c', 'user.name=Fixture', '-c', 'user.email=test@example.test',
              'commit', '-qm', 'synthetic')
        return g.commit(self.root, 'HEAD')

    def record(self, base=None):
        return g.review_inputs(self.root, base or self.base, 'HEAD', {'python': 'synthetic', 'workflow': 'bound'})

    def test_explicit_explanation_reuse_and_current_commit_binding(self):
        saved = self.record()
        self.write('explanation.md', '# refreshed explanation')
        head = self.save()
        now = self.record()
        self.assertEqual(now['merge_result_commit'], head)
        self.assertNotEqual(saved['merge_result_commit'], head)
        self.assertFalse(now['effect_review_required'])
        self.assertTrue(g.verify_review(now, saved)['reusable_evidence'])
        self.assertFalse(g.verify_review(now, saved)['authorization'])

    def test_every_substantive_class_and_unknown_markdown_invalidates(self):
        saved = self.record()
        for name in ('source.py', 'test_source.py', 'lock.json', 'protocol.md',
                     '.github/workflows/check.yml', 'new-explanation.md'):
            self.write(name, '# changed')
            self.save()
            self.assertTrue(self.record()['effect_review_required'])
            with self.assertRaisesRegex(ValueError, 'changed'):
                g.verify_review(self.record(), saved)
            g.git(self.root, 'reset', '--hard', self.base)

    def test_author_cannot_add_exclusion_or_self_authorize(self):
        saved = self.record()
        self.write(g.POLICY, json.dumps({'version': 1, 'explanatory_paths': ['explanation.md', 'protocol.md']}))
        self.write('protocol.md', '# weaker rule')
        self.save()
        self.assertEqual(self.record()['excluded_paths'], ['explanation.md'])
        with self.assertRaises(ValueError): g.verify_review(self.record(), saved)
        forged = copy.deepcopy(saved); forged['authorization'] = True
        with self.assertRaises(ValueError): g.verify_review(saved, forged)

    def test_changed_base_environment_deletion_or_type_cannot_reuse(self):
        saved = self.record()
        changed = copy.deepcopy(saved); changed['inputs']['environment']['python'] = 'new'
        changed['relevant_identity'] = g.identity(changed['inputs'])
        with self.assertRaises(ValueError): g.verify_review(changed, saved)
        (self.root / 'STATUS.md').unlink(); self.save()
        with self.assertRaises(ValueError): g.verify_review(self.record(), saved)
        self.assertTrue(self.record()['effect_review_required'])
        g.git(self.root, 'reset', '--hard', self.base)
        self.write('source.py', '# new base'); new_base = self.save()
        with self.assertRaises(ValueError): g.verify_review(self.record(new_base), saved)
        g.git(self.root, 'reset', '--hard', self.base)
        (self.root / 'STATUS.md').chmod(0o755); self.save()
        with self.assertRaises(ValueError): g.verify_review(self.record(), saved)

    def test_immutable_packet_deleted_freeze_and_append_only_archive(self):
        self.write('packet/FREEZE.json', json.dumps({'files': {'code/shared.py': 'a'*64}, 'root': 'b'*64}))
        self.write('packet/README.md', '# completed packet')
        self.write('docs/status-archive/history.md', '# immutable')
        self.write('docs/status-archive/manifest.json', '{}')
        base = self.save()
        for name in ('packet/FREEZE.json', 'packet/README.md',
                     'docs/status-archive/history.md', 'docs/status-archive/manifest.json'):
            self.write(name, '{"changed":true}'); self.save()
            self.assertTrue(g.immutable_audit(self.root, base, 'HEAD')['violations'])
            g.git(self.root, 'reset', '--hard', base)
        (self.root / 'packet/FREEZE.json').unlink(); self.save()
        self.assertTrue(g.immutable_audit(self.root, base, 'HEAD')['violations'])
        g.git(self.root, 'reset', '--hard', base)
        self.write('docs/status-archive/new.md', '# new history'); self.save()
        result = g.immutable_audit(self.root, base, 'HEAD')
        self.assertFalse(result['violations'])
        self.assertTrue(result['coverage_gaps'])
        self.assertFalse(result['runtime_safety_proven'])

    def test_status_budget_change_invalidates_review_identity(self):
        self.write('STATUS.md', '## Paid data\nMaximum new credits: 100\n')
        base = self.save()
        saved = self.record(base)
        self.write('STATUS.md', '## Paid data\nMaximum new credits: 1000000\n')
        self.save()
        now = self.record(base)
        self.assertTrue(now['effect_review_required'])
        self.assertNotEqual(saved['relevant_identity'], now['relevant_identity'])
        with self.assertRaisesRegex(ValueError, 'changed'):
            g.verify_review(now, saved)

    def test_adopted_status_exclusion_is_rejected(self):
        self.write(g.POLICY, json.dumps({'version': 1, 'explanatory_paths': ['STATUS.md']}))
        bad_base = self.save()
        with self.assertRaisesRegex(ValueError, 'rule path'):
            self.record(bad_base)

    def test_adopted_rule_exclusion_is_rejected(self):
        self.write(g.POLICY, json.dumps({'version': 1, 'explanatory_paths': ['STRATEGY.md']}))
        bad_base = self.save()
        with self.assertRaisesRegex(ValueError, 'rule path'):
            self.record(bad_base)


if __name__ == '__main__': unittest.main()
