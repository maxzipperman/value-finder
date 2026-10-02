"""Read only the exact planned event-odds keys; never inspect unrelated files or outcomes."""
import argparse
import json
from pathlib import Path

import plan


def matches(row, raw_roots):
    paths = set()
    for root in raw_roots:
        directory = Path(root) / row['sport'] / row['source']
        paths.update(p.resolve() for p in directory.glob(f"*/{row['cache_key']}.parquet"))
    return sorted(paths)


def reconcile(packet, bundle, raw_roots):
    from epoch import source_executor, event_valid
    base = source_executor(bundle)
    _, read_record, *_ = base.vendor_imports(bundle, packet)
    protocol = json.loads((bundle / 'protocol.json').read_text())
    manifest = json.loads((packet / 'manifest.json').read_text())
    rows = json.loads((packet / 'requests.json').read_text())
    ops = json.loads((packet / 'opportunities.json').read_text())
    reused = []
    for row in rows:
        hits = matches(row, raw_roots)
        if not hits:
            continue
        hashes = {plan.sha(p) for p in hits}
        if len(hashes) != 1:
            raise ValueError('Conflicting exact cache copies; do not repurchase')
        event_valid(row, read_record(hits[0]), base, protocol)
        row.update(max_new_credits=0, cache_source=str(hits[0]), cache_sha256=next(iter(hashes)))
        reused.append({'request_id': row['request_id'], 'paths': [str(p) for p in hits], 'sha256': row['cache_sha256']})
    manifest['cache_reconciliation'] = 'complete; exact key-only cross-store inspection'
    manifest = plan.write_packet(packet, manifest, rows, ops)
    report = {'status': 'reconciled', 'raw_roots': sorted(set(str(Path(p).resolve()) for p in raw_roots)),
              'request_set_sha256': manifest['request_set_sha256'], 'reused': reused,
              'paid_count': sum(bool(r['max_new_credits']) for r in rows), 'new_credits': manifest['new_credits'],
              'outcomes_joined': False, 'unrelated_cache_files_read': False,
              'other_plans_checked': ['exhausted original v4 featured list: different source/endpoint/markets',
                                      'F2 versus F3a: different requested markets; no identical request identity',
                                      'PR107 phase caps are planning estimates, not an active executor']}
    (packet / 'cache-reconciliation.json').write_bytes(plan.canonical(report) + b'\n')
    return report


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--packet', type=Path, required=True)
    p.add_argument('--bundle', type=Path, required=True)
    p.add_argument('--raw-root', action='append', required=True)
    a = p.parse_args()
    print(json.dumps(reconcile(a.packet, a.bundle, a.raw_root), indent=2))
