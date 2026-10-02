"""Offline Mac-only preparation. No key reads, HTTP, outcomes or sealed-cache scans."""
import json
from pathlib import Path

import epoch
import plan
import pilot_coverage
import reconcile


def main():
    here = Path(__file__).resolve().parent
    repo = here.parents[2]
    bundle = here.parent / 'acquisition/football-archive-v4'
    raw_roots = {Path.home() / 'code/value-finder/sharp-markets/data/raw', repo / 'sharp-markets/data/raw'}
    raw_roots.update(repo.parent.glob('*/sharp-markets/data/raw'))
    raw_roots.update(epoch.ROOT_BASE.glob('*/data/raw'))
    raw_roots = sorted(str(p.resolve()) for p in raw_roots)
    reports = {}
    for pid in ('F2', 'F3a'):
        packet = here / pid
        plan.build(bundle, packet, pid)
        reports[pid] = reconcile.reconcile(packet, bundle, raw_roots)
    packet = here / 'F2-pilot'
    plan.pilot(here / 'F2', packet)
    reports['F2-pilot'] = reconcile.reconcile(packet, bundle, raw_roots)
    path = epoch.ROOT_BASE / plan.SOURCE_ROOT / 'spending-ledger.json'
    if plan.sha(path) != epoch.SEED_HASH:
        raise ValueError('Original completed ledger changed; review instead of resetting')
    state = json.loads(path.read_text())
    seed = {'root': plan.SOURCE_ROOT, 'ledger_path': str(path), 'ledger_sha256': plan.sha(path),
            'probe_credits': state['probe_credits'],
            'cumulative_debit_without_probe': state['other_usage_reserved'] +
                sum(a['reserved_credits'] for a in state['attempts'].values())}
    epoch.seed_state(seed, json.loads((packet / 'requests.json').read_text()))
    (packet / 'seed.json').write_bytes(plan.canonical(seed) + b'\n')
    (packet / 'coverage-gate.json').write_bytes(plan.canonical(pilot_coverage.GATE) + b'\n')
    (packet / 'analysis-status.json').write_bytes(plan.canonical({
        'strategy_grading_enabled': False, 'registrations_changed': False, 'outcomes_joined': False,
        'sealed_2026_included': False, 'actual_play_certified': False,
        'source_eligibility_protocol_sha256': json.loads((packet / 'manifest.json').read_text())['source_input_sha256']['protocol.json'],
        'coverage_gate_is_not_profit_gate': True,
        'acquisition_slot': 'T-24h and T-10min scheduled safety restriction; analysis amendment required',
        'scheduled_vs_asof': 'Final independent clock may exclude; it is not claimed as an as-of entry feature.',
        'forecast_live_rule': 'No validation of repeated Open-Meteo alerts or forecast noise under this acquisition.',
        'before_grading': 'Register exact markets/slots/cohort/variants/chronology/settlement/calibration and execution stresses.'
    }) + b'\n')
    root = epoch.freeze(packet)
    m, rows = epoch.verify_packet(packet, root)
    epoch.verify_source_plan(packet, bundle, m, rows)
    summary = {'status': 'ready_for_independent_review_not_authorized', 'root': root,
               'seed_probe_and_conservative_debit': 1687 + seed['cumulative_debit_without_probe'],
               'F2': {k: reports['F2'][k] for k in ('paid_count', 'new_credits')},
               'F3a': {k: reports['F3a'][k] for k in ('paid_count', 'new_credits')},
               'F2-pilot': {k: reports['F2-pilot'][k] for k in ('paid_count', 'new_credits')},
               'pilot_is_subset_not_additional_cost': True, 'API_calls': 0,
               'outcomes_joined': False, 'sealed_2026_read': False}
    (here / 'PREPARATION.json').write_bytes(plan.canonical(summary) + b'\n')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
