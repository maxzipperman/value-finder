import hashlib
import importlib
import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path
import re
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'dashboard'))
status_md = importlib.import_module('vfdash.status_md')


class StatusContracts(unittest.TestCase):
    def test_props_registration_reader_retains_original_runtime_count(self):
        path = ROOT / 'sharp-markets/src/markets/research/props_grade/registration.py'
        spec = importlib.util.spec_from_file_location('status_registration_contract', path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        prereg = ROOT / 'nfl-weather/PREREGISTRATION_PROPS.md'
        old = module.bar(ROOT / 'docs/status-archive/2026-10-03-before-simplification.md', prereg)
        new = module.bar(ROOT / 'STATUS.md', prereg)
        self.assertEqual(old.status_count, 294)
        self.assertEqual(new.status_count, old.status_count)
        self.assertEqual(new.count, old.count)
        self.assertEqual(new.header, old.header)

    def test_archive_bytes_match_pinned_source(self):
        import subprocess
        record = json.loads((ROOT / 'docs/status-archive/manifest.json').read_text())
        saved = (ROOT / record['snapshot']).read_bytes()
        self.assertEqual(hashlib.sha256(saved).hexdigest(), record['sha256'])
        # Offline identity comparison; never joins or reads outcomes/runtime.
        original = subprocess.check_output(['git', '-C', str(ROOT), 'show',
                                            record['source_commit'] + ':' + record['source_path']])
        self.assertEqual(saved, original)

    def test_real_dashboard_parser_and_live_mac_contract(self):
        text = (ROOT / 'STATUS.md').read_text()
        self.assertEqual(status_md.variants(text), 294)
        items = status_md.waiting_items(text, datetime(2026, 10, 3, tzinfo=timezone.utc), timezone.utc)
        self.assertEqual([i['n'] for i in items], [0, 2, 4, 8, 11, 12, 13])
        self.assertIn('no renewal or new spend', next(i for i in items if i['n'] == 12)['detail'])
        self.assertIn('paper-only', next(i for i in items if i['n'] == 13)['detail'])
        self.assertEqual(next(i for i in items if i['n'] == 2)['due_iso'], '2026-10-20')
        body = status_md.section(text, 'Forward tests')
        lines = [l for l in body.splitlines() if l.startswith('The live Mac (the one that runs the scheduled jobs): ')]
        self.assertEqual(len(lines), 1)
        archived = (ROOT / 'docs/status-archive/2026-10-03-before-simplification.md').read_text()
        self.assertIn(lines[0], archived)
        self.assertLess(len(text.encode()), 8500)

    def test_current_links_resolve_and_runtime_artifact_path_is_preserved(self):
        text = (ROOT / 'STATUS.md').read_text()
        for target in re.findall(r'\]\(([^)]+)\)', text):
            if not target.startswith(('https:', '/', '#')):
                self.assertTrue((ROOT / target.split('#')[0]).exists(), target)
        self.assertIn('football-older-recovery-hub/HUB_PROGRESS.md', text)
        self.assertEqual(text.count('## Paid data'), 1)


if __name__ == '__main__': unittest.main()
