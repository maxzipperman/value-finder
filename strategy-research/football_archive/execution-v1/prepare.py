"""Offline exact-stage preparation. Never overwrite a registered packet or read a key."""
import argparse
import json
from pathlib import Path
import sys
sys.dont_write_bytecode = True
import epoch
import plan
import reconcile


def prepare(stage, candidate=False):
    here = Path(__file__).resolve().parent
    bundle = here.parent / 'acquisition/football-archive-v4'
    packet = here / stage
    if (packet / 'FREEZE.json').exists():
        root = json.loads((packet / 'FREEZE.json').read_text())['root']
        if (epoch.ROOT_BASE / root).exists():
            raise ValueError('Registered packet cannot be regenerated')
    epoch.source_executor(bundle)
    epoch.pilot_gate(bundle)
    prior_root = epoch.PILOT_ROOT if stage == 'F2' else json.loads((here / 'F2/FREEZE.json').read_text())['root']
    prior_path = epoch.ROOT_BASE / prior_root / 'spending-ledger.json'
    if not candidate:
        state = json.loads(prior_path.read_text())
        seed = {'root': prior_root, 'ledger_path': str(prior_path), 'ledger_sha256': plan.sha(prior_path),
                'probe_credits': state['probe_credits'], 'cumulative_debit_without_probe': state['other_usage_reserved'] +
                    sum(a['reserved_credits'] for a in state['attempts'].values())}
    else:
        seed = {'status': 'candidate_only_requires_completed_F2'}
    plan.build(bundle, packet, stage)
    raw_roots = {Path.home() / 'code/value-finder/sharp-markets/data/raw', here.parents[2] / 'sharp-markets/data/raw',
        Path('/Users/maxzipperman/.codex/.chatgpt-projects/g-p-6abd9b86b9548191a07ce7f1180bc80a/football-analysis-repair/sharp-markets/data/raw')}
    raw_roots.update(epoch.ROOT_BASE.glob('*/data/raw'))
    report = reconcile.reconcile(packet, bundle, sorted(str(p.resolve()) for p in raw_roots))
    manifest = json.loads((packet / 'manifest.json').read_text())
    manifest['stage'] = 'candidate' if candidate else ('remainder' if stage == 'F2' else '2025-props')
    manifest['pilot_root'] = epoch.PILOT_ROOT
    (packet / 'manifest.json').write_bytes(plan.canonical(manifest) + b'\n')
    (packet / 'seed.json').write_bytes(plan.canonical(seed) + b'\n')
    (packet / 'pilot-gate-pin.json').write_bytes(plan.canonical({'root': epoch.PILOT_ROOT,
        'ledger_sha256': epoch.PILOT_LEDGER_SHA, 'coverage_sha256': epoch.PILOT_COVERAGE_SHA}) + b'\n')
    root = epoch.freeze(packet)
    m, rows = epoch.verify_packet(packet, root)
    epoch.verify_source_plan(packet, bundle, m, rows)
    if not candidate:
        epoch.seed_state(seed, rows)
        epoch.stage_guard(packet, m, seed, rows, bundle)
    result = {'root': root, 'pull': stage, 'stage': manifest['stage'],
        'request_count': len(rows), 'paid_count': report['paid_count'], 'new_credits': report['new_credits'],
        'request_list_sha256': manifest['request_list_sha256'], 'request_set_sha256': manifest['request_set_sha256'],
        'reused': len(report['reused']), 'cumulative_predecessor_debit': None if candidate else 1687 + seed['cumulative_debit_without_probe'],
        'api_calls': 0, 'outcomes_joined': False, 'paid_approval': False}
    print(json.dumps(result, indent=2))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--stage', choices=['F2', 'F3a'], required=True)
    parser.add_argument('--candidate', action='store_true')
    args = parser.parse_args()
    if args.candidate and args.stage != 'F3a':
        raise SystemExit('Only F3a can be candidate-only')
    prepare(args.stage, args.candidate)
