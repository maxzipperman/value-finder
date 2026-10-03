"""Read-only prior response/certification checks; no status-only recovery admission.

F2's pinned gate reuses the reviewed complete dependency capture and deep union
validator. Unknown recovery families stay blocked; a new snapshot approval cannot certify their history.
"""
import hashlib
import json
import re
from pathlib import Path
import capture
import f2_gate
import older_recovery
from types import SimpleNamespace

F2_ROOTS={f2_gate.PILOT_ROOT,f2_gate.FIRST_ROOT,f2_gate.SECOND_ROOT,f2_gate.FINAL_ROOT}
PROBE=1687
SOURCE_LEDGER_SHA256='eb9e93e354babef2be73ddaa13ea6e2913c58eaaff706ed4e78aec1381636190'
PARTIAL_ROOTS={f2_gate.FIRST_ROOT,f2_gate.SECOND_ROOT}


def certified_partials(states,ledgers,full=True,bindings=None):
    partials={r for r,s in states.items() if s.get('status') in
              ('event_epoch_partial_reconciled','older_epoch_partial_reconciled')}
    f2_partials=partials & PARTIAL_ROOTS
    older_partials=partials - PARTIAL_ROOTS
    if older_partials - {older_recovery.OLD_ROOT}:
        raise ValueError('Unknown certified partial family')
    if F2_ROOTS & set(states):
        if f2_partials!=PARTIAL_ROOTS or not F2_ROOTS.issubset(states):
            raise ValueError('Unknown or incomplete certified partial family')
        for root in f2_partials:
            f2_gate.verify_partial(root,ledgers[root],states[root],capture.sha(ledgers[root]))
        if full:f2_gate.verify_full_union(ledgers[f2_gate.FINAL_ROOT])
    elif f2_partials:
        raise ValueError('Incomplete certified F2 lineage')
    if older_recovery.OLD_ROOT in states and older_partials!={older_recovery.OLD_ROOT}:
        raise ValueError('Original older root must remain exactly certified partial')
    if not older_partials:return set()
    return older_lineage(states,ledgers,bindings or {},full)


def older_lineage(states,ledgers,bindings,full):
    """Adopt PR129's captured read-only verifier; no transition/run/key call.

    Exact actual successor packet/auth/final-ledger bindings are external inputs
    in the metadata approval. No final child root or completion is invented.
    """
    old=older_recovery;root=old.OLD_ROOT;path=ledgers[root]
    if path.absolute()!=old.RUNTIME_BASE/root/'spending-ledger.json':raise ValueError('Older fixed runtime differs')
    coverage=bindings.get('older_coverage_path')
    if not coverage:raise ValueError('Reviewed older coverage binding required')
    directory=path.parent/'older-lag-recovery-v1';cert=old.read(directory/'certificate.json')
    auth=old.read(directory/'offline-approval.json')
    if (auth.get('execution_commit')!='18dc3eae65beb941b341a88c3a356613ab1c015b'
            or capture.sha(path)!=cert.get('post_ledger_sha256')
            or states[root].get('older_lag_reconciliation',{}).get('proposal_sha256')!=cert.get('proposal_sha256')):
        raise ValueError('Exact installed older transition differs')
    if full:
        verified,state,_=old.verified_partial(coverage)
        if verified!=cert or state!=states[root]:raise ValueError('Older certified transition changed')
    # Finite explicit successors only. An unknown partial never enters this route.
    successors=bindings.get('older_successors',{})
    if not isinstance(successors,dict):raise ValueError('Exact successor map required')
    actual={r for r,s in states.items() if s.get('predecessor_seed',{}).get('root')==root}
    if set(successors)!=actual:raise ValueError('Actual older successor bindings differ')
    accepted={root}
    for child in actual:
        binding=successors[child];child_path=ledgers[child];state=states[child]
        if (state.get('status')!='older_epoch_complete' or capture.sha(child_path)!=binding.get('ledger_sha256')
                or binding.get('packet_root')!=child):raise ValueError('Actual completed older successor required')
        if full:
            packet=Path(binding['packet_path'])
            # Source capture includes this helper/protocol; verify_packet also
            # validates original immutable dependency freezes and actual parent.
            m,rows,seed,base=old.verify_packet(packet,child,coverage)
            original_auth=old.read(binding['authorization_path'])
            if capture.sha(binding['authorization_path'])!=binding.get('authorization_sha256'):
                raise ValueError('Original successor approval archive changed')
            internal,_=old.paid_authority(original_auth,m,child,original_auth['execution_commit'],base,authenticate=False)
            if (state.get('authorization_sha256')!=old.identity(internal) or state.get('predecessor_seed')!=seed
                    or set(state['attempts'])!={r['request_id'] for r in rows}):
                raise ValueError('Completed older successor identity/scope differs')
            run=old.read(child_path.parent/'run-manifest.json')
            expected={'stage':'older-lag-continuation','packet_root':child,'predecessor':seed,'source_root':old.SOURCE_ROOT,
                      'external_authorization_sha256':old.identity(original_auth),'internal_priority_bridge':1,
                      'commit':original_auth['execution_commit'],'runtime':old.read(old.BUNDLE/'runtime-lock.json'),
                      'policy_sha256':m['policy_sha256'],'scope':'exact never-sent original rows; no retries; no outcomes'}
            if run!=expected or old.read(child_path.parent/'INITIALIZED.json')!={'bundle_root_sha256':child,'probe_credits':PROBE}:
                raise ValueError('Completed older initialization/run proof differs')
            if state.get('slice_cap')!=old.NEW_CAP or sum(capture.integer(a['reserved_credits']) for a in state['attempts'].values())!=old.NEW_CAP:
                raise ValueError('Older successor full reservations differ')
            ledger=SimpleNamespace(state=state,folder=child_path.parent,protocol=old.read(old.BUNDLE/'protocol.json'))
            old.terminal_evidence(ledger,rows,base,old.policy(rows))
        accepted.add(child)
    return accepted


def response_evidence(rid,attempt,folder,*,source_row=None,original=False,certified_f2=False,certified_older=False):
    """Require saved response bytes and exact receipt/HTTP/billing classification.

    The sole uncached exception is v4's explicit approved observed-5xx receipt;
    its observed bill, reservation and exact approved attempt digest are checked.
    Other missing records require certified F2 or exact original-v4 reconciliation.
    """
    receipt=Path(folder)/'receipts'/(rid+'.json')
    if capture.sha(receipt)!=attempt['receipt_sha256']:raise ValueError('Shared receipt changed')
    proof=capture.read(receipt)
    if proof.get('request_id')!=rid:raise ValueError('Shared receipt identity differs')
    status=attempt['status'];reserve=capture.integer(attempt['reserved_credits']);bill=capture.integer(attempt['billed_credits'])
    if attempt.get('send_started') is not True or reserve==0 or bill>reserve:
        raise ValueError('Unstarted or invalid historical reservation')
    path=attempt.get('response_path')
    if not path:
        if not (original and status=='missing' and proof.get('status')=='accepted_missing'
                and attempt.get('missing_reason')==proof.get('reason')=='http_5xx'
                and attempt.get('response_sha256') is None and proof.get('response_sha256') is None
                and 500<=attempt.get('observed_http_status',0)<600):
            raise ValueError('Required shared response bytes absent')
        headers=attempt.get('observed_billing_headers',{})
        if proof.get('observed_billing_headers')!=headers:raise ValueError('Uncached missing billing differs')
        # Approved digest is of the original pending attempt; completion only
        # changes these terminal fields, preserving original observed evidence.
        pending=dict(attempt,status='pending')
        for name in ('missing_reason','billed_credits','response_path','response_sha256','receipt_sha256'):
            pending.pop(name,None)
        resolution=proof.get('reconciliation',{}).get('missing_response_resolution',{})
        if resolution.get('attempt_sha256')!=capture.identity(pending):raise ValueError('Uncached missing attempt proof differs')
        original_missing(rid,attempt,proof,folder,None)
        bill_check(headers,bill)
        return
    data=capture.regular(path)
    digest=capture.digest(data)
    if digest!=attempt['response_sha256']:raise ValueError('Shared cache evidence changed')
    import pyarrow as pa
    import pyarrow.parquet as pq
    records=pq.read_table(pa.BufferReader(data)).to_pylist()
    if len(records)!=1:raise ValueError('One saved historical response required')
    record=records[0];headers=json.loads(record['headers_json']);bill_check(headers,bill)
    params=json.loads(record['params_json'])
    identity={'source':record['source'],'url':record['url'],'params':params}
    key=hashlib.sha1(json.dumps(identity,sort_keys=True,default=str).encode()).hexdigest()[:20]
    if capture.identity(identity)!=rid or key!=record['cache_key']:
        raise ValueError('Historical request/cache identity differs')
    if source_row is not None and (source_row['request_id']!=rid or source_row['cache_key']!=key
            or source_row['sport']!=record['sport'] or source_row['params']!=params
            or reserve!=source_row['max_new_credits']):raise ValueError('Original manifest response differs')
    if original and status=='missing':
        if proof.get('response_sha256')!=digest or proof.get('observed_billing_headers')!=headers:
            raise ValueError('Original missing receipt/cache differs')
        original_missing(rid,attempt,proof,folder,record)
        return
    if (proof.get('record_sha256')!=digest or proof.get('cache_key')!=key
            or capture.identity(proof.get('record'))!=capture.identity(record) or proof.get('headers')!=headers):
        raise ValueError('Full historical receipt/cache record differs')
    if status=='missing':
        if certified_older:
            body=json.loads(record['body'])
            if (proof.get('status')!='missing' or proof.get('reason')!='snapshot_lag' or proof.get('usable_quote') is not False
                    or record['http_status']!=200 or (capture.stamp(params['date'])-capture.stamp(body['timestamp'])).total_seconds()<=600
                    or not capture.stamp(body['previous_timestamp'])<capture.stamp(body['timestamp'])<capture.stamp(body['next_timestamp'])):
                raise ValueError('Certified older lag response differs')
            return
        if not certified_f2:raise ValueError('Unrecognized historical missing policy; reviewed integration required')
        if (proof.get('status')!='missing' or record['http_status']!=404 or bill!=0
                or json.loads(record['body']).get('error_code')!='EVENT_NOT_FOUND'):
            raise ValueError('Certified F2 missing response differs')
        # The deep union verifier binds each exact request to its certificate or
        # frozen prospective policy, not merely to this 404 category.
        return
    if status!='completed' or record['http_status']!=200 or proof.get('status') not in (None,'completed'):
        raise ValueError('Historical completed response classification differs')
    body=json.loads(record['body']);requested=capture.stamp(params['date']);stamp=capture.stamp(body['timestamp'])
    if not 0<=(requested-stamp).total_seconds()<=600:raise ValueError('Historical completed snapshot invalid')
    if not capture.stamp(body['previous_timestamp'])<stamp<capture.stamp(body['next_timestamp']):
        raise ValueError('Historical completed neighbors invalid')
    payload=body['data']
    if record['source']=='oddsapi/hist_odds':
        if not isinstance(payload,list):raise ValueError('Historical featured body invalid')
    elif record['source']=='oddsapi/hist_event_odds':
        if (not isinstance(payload,dict) or payload.get('sport_key')!=record['sport']
                or record['url']!='https://api.the-odds-api.com/v4/historical/sports/'+record['sport']+'/events/'+str(payload.get('id'))+'/odds'):
            raise ValueError('Historical event body identity invalid')
    else:raise ValueError('Unrecognized historical response schema')


def bill_check(headers,bill):
    values=[capture.integer(headers.get(k)) for k in ('x-requests-last','x-requests-used','x-requests-remaining')]
    if values[0]!=bill:raise ValueError('Historical bill differs from ledger')


def original_missing(rid,attempt,proof,folder,record):
    rec=proof.get('reconciliation',{});resolution=rec.get('missing_response_resolution',{});hub=resolution.get('hub_go_ahead',{})
    root=Path(folder).name;reason=proof.get('reason');commit=hub.get('commit');prior=rec.get('prior_ledger_sha256')
    expected=(f'APPROVED missing response: root {root}, request {rid}, ledger {prior}, commit {commit}, reason {reason}')
    if (proof.get('status')!='accepted_missing' or attempt.get('missing_reason')!=reason
            or rec.get('status')!='approved' or rec.get('bundle_root_sha256')!=root
            or resolution.get('request_id')!=rid or hub.get('status')!='approved'
            or resolution.get('reason')!=reason or not re.fullmatch('[a-f0-9]{40}',commit or '')
            or not re.fullmatch('[a-f0-9]{64}',prior or '')
            or not re.fullmatch(r'https://github\.com/maxzipperman/value-finder/pull/99#issuecomment-[0-9]+',hub.get('comment_url',''))
            or not resolution.get('owner_note') or expected not in hub.get('comment_body','').splitlines()
            or rec.get('bundle_root_sha256')!=root):raise ValueError('Original missing approval differs')
    if record is not None:
        if resolution.get('response_sha256')!=attempt['response_sha256']:raise ValueError('Missing approval response differs')
        if reason=='http_404' and record['http_status']==404:return
        if reason=='snapshot_lag' and record['http_status']==200:
            body=json.loads(record['body']);params=json.loads(record['params_json'])
            if (capture.stamp(params['date'])-capture.stamp(body['timestamp'])).total_seconds()>600:return
        raise ValueError('Original missing reason/HTTP classification differs')
