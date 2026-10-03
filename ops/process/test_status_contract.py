import hashlib
import importlib
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
        self.assertEqual([i['n'] for i in items], [0, 2, 4, 8, 11])
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
