"""Prospective exact timeout admission; original evidence functions retained."""
import json
from pathlib import Path
import capture
import timeout_quarantine
import timeout_authority
import prior_evidence
from planner import digest, InvalidPlan
captured_receipts=prior_evidence.captured_receipts
authenticate_reuse=prior_evidence.authenticate_reuse
frozen_probe_record=prior_evidence.frozen_probe_record
write_once=prior_evidence.write_once

def global_union(root_base, baseline_snapshot, pilot_bindings, verify_baseline, *, active_root=None, active_verifier=None):
    """Complete inventory first, then authenticate every base and pilot root.

    pilot_bindings root -> externally frozen ledger/marker hashes, rows, policy,
    predecessor snapshot digest, authorization hash and plan identity. Terminal
    epochs only; the in-progress current executor is handled separately under lock.
    """
    root_base = Path(root_base)
    ledgers = {p.parent.name:p for p in root_base.glob('*/spending-ledger.json')}
    markers = {p.stem:p for p in (root_base/'registrations').glob('*.json')}
    initialized = {p.parent.name for p in root_base.glob('*/INITIALIZED.json')}
    if initialized != set(ledgers):
        raise InvalidPlan('initialized store or ledger lost')
    if active_root is not None:
        if active_root in baseline_snapshot['ledgers'] or active_root in pilot_bindings or active_root not in ledgers or active_root not in markers or active_verifier is None:
            raise InvalidPlan('unbound active epoch partition')
        active_verifier()
        ledgers.pop(active_root);markers.pop(active_root)
    base = set(baseline_snapshot['ledgers'])
    if (set(baseline_snapshot['registrations']) != base or base & set(pilot_bindings)
            or set(ledgers) != base | set(pilot_bindings) or set(markers) != set(ledgers)):
        raise InvalidPlan('unknown/missing/overlapping global root')
    snapshot, seed = verify_baseline({r:ledgers[r] for r in base},{r:markers[r] for r in base})
    if snapshot != baseline_snapshot: raise InvalidPlan('baseline proof differs')
    pending = dict(pilot_bindings)
    carry = seed['cumulative_debit_without_probe']
    while pending:
        matching = [r for r,b in pending.items() if b['predecessor_snapshot'] == digest(snapshot)]
        if len(matching) != 1: raise InvalidPlan('forked or broken prospective history')
        root = matching[0]; b = pending.pop(root)
        raw = capture.regular(ledgers[root]); marker_raw = capture.regular(markers[root])
        if capture.digest(raw) != b['ledger_sha256'] or capture.digest(marker_raw) != b['marker_sha256']:
            raise InvalidPlan('prospective ledger/registration changed')
        initialization = capture.regular(ledgers[root].parent/'INITIALIZED.json')
        if (capture.digest(initialization) != b['initialization_sha256']
                or json.loads(initialization) != {'bundle_root_sha256':root,'probe_credits':1687}):
            raise InvalidPlan('prospective initialization proof differs')
        s = json.loads(raw); marker = json.loads(marker_raw)
        is_timeout=root==timeout_quarantine.ROOT and b.get('kind')=='exact_pre_send_authority_timeout_retirement'
        if (s.get('status') not in ('pilot_complete','pilot_partial_reconciled','halted') or (s.get('status')=='halted' and not is_timeout) or (s.get('pending') and not is_timeout) or (s.get('stopped') and not is_timeout)
                or s.get('probe_credits') != 1687 or s.get('bundle_root_sha256') != root
                or s.get('authorization_sha256') != b['authorization_sha256']
                or marker.get('authorization_sha256') != b['authorization_sha256']
                or marker.get('bundle_root_sha256') != root
                or Path(marker.get('runtime_path','')).absolute() != ledgers[root].parent.absolute()
                or s.get('pilot_plan_sha256') != b['plan_sha256']
                or s.get('predecessor_snapshot') != b['predecessor_snapshot']
                or type(s.get('other_usage_reserved')) is not int or s['other_usage_reserved'] < carry):
            raise InvalidPlan('prospective epoch proof differs')
        if is_timeout:
            folder=ledgers[root].parent;installed=folder/'authority-timeout-retirement'
            rec=b['reconciliation']
            if rec['approval_path']!=str(installed/'approval.json'):raise InvalidPlan('offline acceptance path escaped stopped epoch')
            approval=capture.read(installed/'approval.json')
            cert=timeout_quarantine.verify_approval(dict(rec,approval=approval),fetch=timeout_authority.fetch_live_comment)
            if capture.read(installed/'certificate.json')!=cert:raise InvalidPlan('exact quarantine must be installed by hub')
            proof=timeout_quarantine.verify(folder,b['rows'],b['policy'],cert,capture,prior_evidence)
        elif s.get('status')=='pilot_partial_reconciled':
            import quarantine
            certificate=quarantine.verify_approval(b['reconciliation'])
            proof=quarantine.verify_partial(ledgers[root].parent,b['rows'],s,b['policy'],certificate)
            if proof['untouched_ids']!=certificate['untouched_ids'] or proof['reserved']!=270:raise InvalidPlan('certified untouched scope differs')
        else:
            if b.get('reconciliation'):raise InvalidPlan('unexpected reconciliation on complete pilot')
            proof = captured_receipts(ledgers[root].parent,b['rows'],s,b['policy'])
            if proof['untouched_ids'] or proof['reserved'] != s.get('slice_cap'):
                raise InvalidPlan('incomplete terminal pilot')
        carry = s['other_usage_reserved'] + proof['reserved']
        snapshot = {'ledgers':dict(snapshot['ledgers'],**{root:b['ledger_sha256']}),
                    'registrations':dict(snapshot['registrations'],**{root:b['marker_sha256']})}
    if carry + 1687 > 274686: raise InvalidPlan('first tranche cumulative cap exceeded')
    return snapshot, {'conservative_debit':carry+1687,'probe_counted_once':1687}

