"""Read-only prospective evidence and exclusive final-record creation helpers.

No function here authorizes execution. capture is the verified PR132 dependency.
"""
import json
import os
from pathlib import Path
import capture
from planner import digest, InvalidPlan
from receipts import receipt_union


def captured_receipts(folder, rows, state, policy):
    import pyarrow as pa
    import pyarrow.parquet as pq
    by_id = {r['request_id']:r for r in rows}
    if len(by_id) != len(rows) or not set(state['attempts']) <= by_id.keys():
        raise InvalidPlan('unexpected prospective attempt')
    evidence = {}
    for rid,a in state['attempts'].items():
        row = by_id[rid]
        expected = Path(folder)/'data/raw'/row['sport']/row['source']/row['requested_utc'][:10]/(row['cache_key']+'.parquet')
        if Path(a['response_path']).absolute() != expected.absolute():
            raise InvalidPlan('cache path escaped exact request')
        raw = capture.regular(expected)
        records = pq.read_table(pa.BufferReader(raw)).to_pylist()
        if len(records) != 1: raise InvalidPlan('single raw record required')
        evidence[rid] = {'response_sha256':capture.digest(raw),'record':records[0],
                         'receipt_bytes':capture.regular(Path(folder)/'receipts'/(rid+'.json'))}
    return receipt_union(rows,state['attempts'],evidence,policy)


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
        if (s.get('status') != 'pilot_complete' or s.get('pending') or s.get('stopped')
                or s.get('probe_credits') != 1687 or s.get('bundle_root_sha256') != root
                or s.get('authorization_sha256') != b['authorization_sha256']
                or marker.get('authorization_sha256') != b['authorization_sha256']
                or marker.get('bundle_root_sha256') != root
                or Path(marker.get('runtime_path','')).absolute() != ledgers[root].parent.absolute()
                or s.get('pilot_plan_sha256') != b['plan_sha256']
                or s.get('predecessor_snapshot') != b['predecessor_snapshot']
                or type(s.get('other_usage_reserved')) is not int or s['other_usage_reserved'] < carry):
            raise InvalidPlan('prospective epoch proof differs')
        proof = captured_receipts(ledgers[root].parent,b['rows'],s,b['policy'])
        if proof['untouched_ids'] or proof['reserved'] != s.get('slice_cap'):
            raise InvalidPlan('incomplete terminal pilot')
        carry = s['other_usage_reserved'] + proof['reserved']
        snapshot = {'ledgers':dict(snapshot['ledgers'],**{root:b['ledger_sha256']}),
                    'registrations':dict(snapshot['registrations'],**{root:b['marker_sha256']})}
    if carry + 1687 > 250000: raise InvalidPlan('first tranche cumulative cap exceeded')
    return snapshot, {'conservative_debit':carry+1687,'probe_counted_once':1687}


def final_record(*, frame_sha256, protocol_sha256, draw_sha256, evidence_sha256,
                 selected_ids, classifications, saved_bounds, mappings, previous=None):
    """Bind one final look. Require authenticated ALL-terminal evidence upstream.

    Reuse returns the identical record only; any changed old inputs/bounds fail.
    Added-frame looks must reference this record separately, never replace it.
    """
    if len(selected_ids) != len(set(selected_ids)) or set(classifications) != set(selected_ids):
        raise InvalidPlan('final selected denominator incomplete')
    mapped={m['game_id']:m for m in mappings}
    if len(mapped)!=len(mappings) or set(mapped)!=set(selected_ids):raise InvalidPlan('final mapping denominator differs')
    for gid,item in mapped.items():
        if item.get('metadata_disposition',{}).get('classification')=='failure' and classifications[gid] is not False:
            raise InvalidPlan('selected metadata zero must remain a failure in final bounds')
    if any(type(v) is not bool for v in classifications.values()):
        raise InvalidPlan('pending/unknown classification blocks final look')
    for pin in (frame_sha256,protocol_sha256,draw_sha256,evidence_sha256):
        if not isinstance(pin,str) or len(pin)!=64 or any(c not in '0123456789abcdef' for c in pin):
            raise InvalidPlan('invalid final evidence pin')
    record = dict(frame=frame_sha256,protocol=protocol_sha256,draw=draw_sha256,
                  evidence=evidence_sha256,mappings_sha256=digest(mappings),classifications=dict(sorted(classifications.items())),
                  saved_bounds=saved_bounds,next_purchase_authorized=False)
    # Ensure exact JSON serializability now; Fraction values need explicit num/den.
    digest(record)
    if previous is not None and previous != record: raise InvalidPlan('one-look record changed')
    return record


def write_once(path, record):
    """Exclusive durable final evidence. Interrupted write blocks automatic repair."""
    path = Path(path).absolute()
    if any(p.is_symlink() for p in (path,*path.parents)):
        raise InvalidPlan('symlink final evidence')
    data = json.dumps(record,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
    fd = os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    try:
        with os.fdopen(fd,'wb',closefd=False) as handle:
            handle.write(data);handle.flush();os.fsync(handle.fileno())
    finally: os.close(fd)
    directory = os.open(path.parent,os.O_RDONLY)
    try: os.fsync(directory)
    finally: os.close(directory)


def authenticate_reuse(root_base, snapshot, mappings, *, frozen_source=None):
    """Tie declared reused IDs/cells to already globally authenticated receipts.

    Call only AFTER global_union under the shared lock. Projection reads request
    metadata, never outcomes or quote payloads. Missing attempts cover requested
    cells for no-repurchase purposes; they do not establish a usable quote.
    """
    import pyarrow as pa
    import pyarrow.parquet as pq
    from timing import utc
    root_base=Path(root_base)
    def record(claim):
        if claim.get('kind')=='frozen_probe':return frozen_probe_record(claim,frozen_source)
        root=claim['root'];rid=claim['request_id']
        if root not in snapshot['ledgers']:raise InvalidPlan('reuse outside authenticated global history')
        folder=root_base/root;ledger=folder/'spending-ledger.json'
        if capture.sha(ledger)!=snapshot['ledgers'][root]:raise InvalidPlan('reuse ledger changed')
        attempt=capture.read(ledger)['attempts'].get(rid)
        if not attempt or attempt['status'] not in {'completed','missing'}:raise InvalidPlan('reuse requires terminal authenticated attempt')
        receipt=capture.regular(folder/'receipts'/(rid+'.json'))
        if capture.digest(receipt)!=claim['receipt_sha256'] or claim['receipt_sha256']!=attempt['receipt_sha256']:
            raise InvalidPlan('reuse receipt pin differs')
        if json.loads(receipt).get('request_id')!=rid:raise InvalidPlan('reuse receipt identity differs')
        raw=capture.regular(attempt['response_path'])
        if capture.digest(raw)!=claim['response_sha256'] or claim['response_sha256']!=attempt['response_sha256']:
            raise InvalidPlan('reuse response pin differs')
        records=pq.read_table(pa.BufferReader(raw),columns=['sport','source','url','params_json','cache_key']).to_pylist()
        if len(records)!=1:raise InvalidPlan('ambiguous reused response')
        rec=records[0];rec['params']=json.loads(rec.pop('params_json'))
        identity={k:rec[k] for k in ('source','url','params')}
        if capture.identity(identity)!=rid:raise InvalidPlan('reuse request identity differs')
        params=rec['params']
        if params.get('dateFormat','iso')!='iso' or params.get('oddsFormat','decimal')!='decimal' or set(params)-{'date','dateFormat','oddsFormat','bookmakers','markets'}:
            raise InvalidPlan('incompatible reused query')
        return rec
    for item in mappings:
        ids=item.get('reused_request_ids',[]);claims=item.get('reused_evidence',[])
        if len(ids)!=len(set(ids)) or {c['request_id'] for c in claims}!=set(ids) or len(claims)!=len(ids):
            raise InvalidPlan('every reused old ID needs exactly one receipt proof')
        for claim in claims:
            if record(claim)['source']!='oddsapi/hist_odds':raise InvalidPlan('old reuse endpoint differs')
        for slot in item.get('reused_slots',[]):
            if not slot['books'] or not slot['markets'] or len(set(slot['books']))!=len(slot['books']) or len(set(slot['markets']))!=len(slot['markets']):
                raise InvalidPlan('explicit unique reused cells required')
            requested={(b,m) for b in slot['books'] for m in slot['markets']};covered=set()
            proofs=slot['evidence']
            if not proofs or len({(c['root'],c['request_id']) for c in proofs})!=len(proofs):raise InvalidPlan('unique reused cell receipts required')
            for claim in proofs:
                rec=record(claim);params=rec['params']
                expected=f"https://api.the-odds-api.com/v4/historical/sports/{slot['sport']}/events/{slot['event_id']}/odds"
                if rec['source']!='oddsapi/hist_event_odds' or rec['sport']!=slot['sport'] or rec['url']!=expected or utc(params['date'])!=utc(slot['requested_utc']):
                    raise InvalidPlan('reused event/time/sport differs')
                covered.update((b,m) for b in params['bookmakers'].split(',') for m in params['markets'].split(','))
            if not requested<=covered:raise InvalidPlan('reused cells lack authenticated receipts')
    return True


def frozen_probe_record(claim, context):
    """Immutable original probe evidence, never a fabricated runtime receipt.

    Context is bootstrap-captured source bytes and original FREEZE, not live files.
    Only old priority2 zero-new-credit featured requests qualify. The caller's
    authenticated global carry already includes the original1687 probe once.
    Request metadata projection does not read odds/outcomes or certify usability.
    """
    import pyarrow as pa
    import pyarrow.parquet as pq
    source_root='4468a94c2b415cd5c53dd58163831f61d379ee44ec1b560f5a9b84be9c7f010d'
    required={'kind','source_bundle_root','request_id','cache_source','cache_sha256','request_manifest_sha256','probe_ledger_sha256','probe_attempt_sha256'}
    if set(claim)!=required or claim['source_bundle_root']!=source_root or context is None:
        raise InvalidPlan('exact frozen probe context/claim required')
    cert=json.loads(context['freeze']);source=context['files']
    if (cert['bundle_root_sha256']!=source_root or capture.identity(cert['file_sha256'])!=source_root
            or {n:capture.digest(v) for n,v in source.items()}!=cert['file_sha256']):
        raise InvalidPlan('immutable probe source/root differs')
    manifest=source['request-manifest.json'];ledger=source['probe-spending-ledger.json']
    if capture.digest(manifest)!=claim['request_manifest_sha256'] or capture.digest(ledger)!=claim['probe_ledger_sha256']:
        raise InvalidPlan('probe manifest/ledger pin differs')
    originals=[r for r in json.loads(manifest)['requests'] if r['request_id']==claim['request_id']]
    if len(originals)!=1:raise InvalidPlan('unique original probe request required')
    row=originals[0];name=row.get('cache_source')
    if (row['priority']!=2 or row['source']!='oddsapi/hist_odds' or row['max_new_credits']!=0
            or not name or not name.startswith('reuse/') or name!=claim['cache_source']
            or row['cache_sha256']!=claim['cache_sha256'] or capture.digest(source[name])!=claim['cache_sha256']):
        raise InvalidPlan('designated frozen zero-credit cache differs')
    probe=json.loads(ledger);attempts=[a for a in probe['attempts'] if a['request_id']==claim['request_id']]
    if (probe.get('pending') or probe.get('stopped') or probe['reserved_credits']!=1687
            or sum(a['counted_credits'] for a in probe['attempts'])!=1687
            or len(attempts)!=1 or attempts[0]['http_status']!=200
            or attempts[0]['counted_credits']!=row['max_credits']
            or capture.identity(attempts[0])!=claim['probe_attempt_sha256']):
        raise InvalidPlan('terminal frozen probe attempt differs')
    records=pq.read_table(pa.BufferReader(source[name]),columns=['sport','source','url','params_json','cache_key','http_status']).to_pylist()
    if len(records)!=1:raise InvalidPlan('single frozen probe response required')
    rec=records[0];rec['params']=json.loads(rec.pop('params_json'))
    identity={k:rec[k] for k in ('source','url','params')}
    if (rec['http_status']!=200 or capture.identity(identity)!=claim['request_id']
            or rec['source']!=row['source'] or rec['sport']!=row['sport'] or rec['cache_key']!=row['cache_key']
            or rec['params']!=row['params'] or rec['url']!='https://api.the-odds-api.com/v4'+row['path']):
        raise InvalidPlan('frozen probe request metadata differs')
    return rec
