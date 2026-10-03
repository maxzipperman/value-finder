"""Narrow extraction of PR132 global inventory proof over explicit baseline paths.

Caller must inventory ALL actual roots and split only against frozen base/pilot
bindings. This never discovers or hides arbitrary roots. The reviewed history and
capture modules must be loaded from the verified closure, not ambient imports.
"""
import json
from pathlib import Path
import capture
import history
SOURCE_ROOT = '4468a94c2b415cd5c53dd58163831f61d379ee44ec1b560f5a9b84be9c7f010d'
PROBE = 1687

def verify_base(ledgers, markers, expected_snapshot, source_manifest, historical_bindings):
    """Read-only exact global snapshot and a fully covering linear carry lineage.

    No max-over-disjoint-epochs estimate. An unknown branch requires reviewed
    reconciliation; pending/uncertain global work always blocks a new stage.
    """
    verify_receipts = True
    if ({r:capture.sha(p) for r,p in ledgers.items()} != expected_snapshot['ledgers']
            or {r:capture.sha(p) for r,p in markers.items()} != expected_snapshot['registrations']):
        raise ValueError('Exact captured baseline changed')
    if set(ledgers)!=set(markers) or SOURCE_ROOT not in ledgers:raise ValueError('Global registration/ledger inventory lost or changed')
    states={root:capture.read(p) for root,p in ledgers.items()}
    if any(s.get('pending') or s.get('stopped') for s in states.values()):
        raise ValueError('Unresolved global purchase; never new-root escape')
    original=states[SOURCE_ROOT]
    if capture.sha(ledgers[SOURCE_ROOT])!=history.SOURCE_LEDGER_SHA256:
        raise ValueError('Reviewed original completed ledger changed')
    if len(original.get('attempts',{}))!=2761 or len(original.get('cache_reuse',{}))!=12:
        raise ValueError('Completed original acquisition lost coverage; no fresh-store reset')
    if source_manifest is not None:
        old_rows=json.loads(source_manifest)['requests']
        paid={r['request_id'] for r in old_rows if r['priority']==1 and r['max_new_credits']}
        reuse={r['request_id']:r['cache_sha256'] for r in old_rows if r['priority']==1 and not r['max_new_credits']}
        if set(original['attempts'])!=paid or original['cache_reuse']!=reuse:
            raise ValueError('Original coverage differs from immutable manifest')
    # Partial statuses are certificates, never a general restart class.
    certified_older=history.certified_partials(states,ledgers,verify_receipts,historical_bindings)
    snapshots={'ledgers':{},'registrations':{}}
    for root,state in states.items():
        marker=capture.read(markers[root])
        if (state.get('bundle_root_sha256')!=root or state.get('pending') or state.get('stopped')
            or marker.get('bundle_root_sha256')!=root or marker.get('authorization_sha256')!=state.get('authorization_sha256')
            or Path(marker.get('runtime_path','')).absolute()!=ledgers[root].parent.absolute() or state.get('probe_credits')!=PROBE):
            raise ValueError('Unresolved or mismatched shared state; never new-root escape')
        if state.get('status') not in ('recent_complete_stopped_before_older','event_epoch_complete','event_epoch_partial_reconciled',
                                       'older_epoch_complete','older_epoch_partial_reconciled','metadata_complete'):
            raise ValueError('Unapproved global restart state')
        for rid,a in state['attempts'].items():
            reserve=capture.integer(a['reserved_credits']);bill=capture.integer(a.get('billed_credits',0))
            if a['status'] not in ('completed','missing') or bill>reserve or reserve==0:raise ValueError('Nonterminal or invalid shared debit')
            if not verify_receipts:
                continue
            history.response_evidence(rid,a,ledgers[root].parent,
                source_row=next((r for r in old_rows if r['request_id']==rid),None) if root==SOURCE_ROOT and source_manifest is not None else None,
                original=root==SOURCE_ROOT,certified_f2=root in history.F2_ROOTS,certified_older=root in certified_older)
        snapshots['ledgers'][root]=capture.sha(ledgers[root]);snapshots['registrations'][root]=capture.sha(markers[root])
    def chain(root):
        seen=set()
        while root:
            if root in seen or root not in states:raise ValueError('Broken/cyclic shared carry lineage')
            seen.add(root);s=states[root];parent=s.get('predecessor_seed')
            if parent:
                older=states.get(parent['root'])
                if older is None or parent.get('ledger_sha256')!=snapshots['ledgers'][parent['root']]:raise ValueError('Shared ancestor pin changed')
                debit=capture.integer(older['other_usage_reserved'])+sum(capture.integer(a['reserved_credits']) for a in older['attempts'].values())
                if parent.get('cumulative_debit_without_probe')!=debit or s['other_usage_reserved']<debit:raise ValueError('Shared ancestor debit decreased')
                root=parent['root']
            else:
                if root!=SOURCE_ROOT:raise ValueError('Unreviewed independent accounting base')
                root=None
        return seen
    heads=[root for root in states if chain(root)==set(states)]
    if len(heads)!=1:raise ValueError('No unique shared carry lineage; reconcile before purchase')
    head=heads[0];s=states[head]
    seed={'root':head,'ledger_path':str(ledgers[head]),'ledger_sha256':snapshots['ledgers'][head],
          'probe_credits':PROBE,'cumulative_debit_without_probe':capture.integer(s['other_usage_reserved'])+sum(capture.integer(a['reserved_credits']) for a in s['attempts'].values())}
    return snapshots,seed

