"""One exact offline certified quarantine, never resend or implicit recovery.

No mutation here. The hub installs externally approved plan bytes separately.
Completed prior receipts retain strict original policy; one exact captured invalid
quote response becomes missing/ineligible with bill and full reserve preserved.
"""
import copy
import json
from pathlib import Path
import capture
import receipts

ROOT='f499935c05191d9583f891d9f859575ad7419472829fd802e39e2f62549eb22f'
RID='02734fb895e4ccd034ecd84a85fd6a5c0bb4d7867670efbdbfe8bc7d1eccce71'
BEFORE='9310c6dea6fca635fa2057bc03baacba5f3cf5586b3c07243ae68b303493d048'
RAW='0ee20ca94808cebd2ed02c4ce8e02987c983dce0c4a84a87448d1f8200e2b8d7'


def transition(state,row,record,policy,base,protocol,raw_path):
    if (state['bundle_root_sha256']!=ROOT or state['pending']!=RID or row['request_id']!=RID
            or state['status']!='halted' or len(state['attempts'])!=7):raise ValueError('not the exact stopped pilot')
    a=state['attempts'][RID]
    headers=json.loads(record['headers_json'])
    if (a['status']!='pending' or a['send_started'] is not True or a['reserved_credits']!=30
            or a['observed_http_status']!=200 or record['http_status']!=200
            or a['observed_billing_headers']!=headers or int(headers['x-requests-last'])!=30):
        raise ValueError('pending observed evidence differs')
    try:receipts.classify(row,record,policy)
    except ValueError as e:
        if str(e)!='invalid decimal price':raise
    else:raise ValueError('original strict classification unexpectedly passed')
    amended=dict(policy,quote_policy={'decimal_one':'retain_raw_non_executable'})
    observed=receipts.classify(row,record,amended)
    if observed.get('ineligible_quote_counts')!={'decimal_one':1} or observed['status']!='completed':raise ValueError('not exact one literal-one defect')
    result=dict(status='missing',reason='certified_invalid_quote_quarantine',bill=30,used=observed['used'],remaining=observed['remaining'],usable_quote=False)
    proof=dict(request_id=RID,response_sha256=RAW,record=record,classification=result,
               certified_quarantine=dict(root=ROOT,before_ledger_sha256=BEFORE,scope='exact_one_cached_response_no_resend'))
    receipt=base.canonical(proof)+b'\n';after=copy.deepcopy(state)
    # Use reviewed counter primitive with save replaced by a memory-only callback.
    simulated=object.__new__(base.Ledger);simulated.state=after;simulated.protocol=protocol
    simulated.save=lambda:None
    simulated.measure_counters(result['used'],result['remaining'],simulated.billed()-after['epoch']['start_billed']+30)
    after['attempts'][RID].update(status='missing',missing_reason=result['reason'],billed_credits=30,response_path=str(Path(raw_path).absolute()),response_sha256=RAW,receipt_sha256=capture.digest(receipt))
    after.update(pending=None,stopped=None,status='pilot_partial_reconciled')
    after['quarantine_reconciliation']=dict(before_ledger_sha256=BEFORE,quarantined_request_id=RID,response_sha256=RAW,usable_quote=False,no_resend=True,next_stage_authorized=False)
    if simulated.reserved()!=270 or simulated.billed()!=210 or after['probe_credits']!=1687:raise ValueError('debit changed')
    return after,receipt


def verify_partial(folder,rows,state,policy,certificate):
    """Read-only exact installed state/raw/receipt proof, no general missing escape."""
    import pyarrow as pa
    import pyarrow.parquet as pq
    folder=Path(folder);ledger=folder/'spending-ledger.json'
    if (certificate['source_root']!=ROOT or capture.sha(ledger)!=certificate['after_ledger_sha256']
            or state['status']!='pilot_partial_reconciled' or state.get('pending') or state.get('stopped')
            or set(state['attempts'])!=set(certificate['attempted_ids'])):raise ValueError('certified partial state differs')
    by_id={r['request_id']:r for r in rows};row=by_id[RID];a=state['attempts'][RID]
    expected=folder/'data/raw'/row['sport']/row['source']/row['requested_utc'][:10]/(row['cache_key']+'.parquet')
    if Path(a['response_path']).absolute()!=expected.absolute():raise ValueError('quarantine cache escaped')
    raw=capture.regular(expected)
    if capture.digest(raw)!=RAW or certificate['cache_sha256']!=RAW:raise ValueError('quarantine bytes differ')
    records=pq.read_table(pa.BufferReader(raw)).to_pylist()
    if len(records)!=1:raise ValueError('single quarantine record required')
    record=records[0];receipt=capture.regular(folder/'receipts'/(RID+'.json'));proof=json.loads(receipt)
    if (capture.digest(receipt)!=certificate['receipt_sha256'] or a['receipt_sha256']!=certificate['receipt_sha256']
            or proof['request_id']!=RID or proof['response_sha256']!=RAW
            or json.dumps(proof['record'],sort_keys=True,default=str)!=json.dumps(record,sort_keys=True,default=str)
            or proof['classification']!={'status':'missing','reason':'certified_invalid_quote_quarantine','bill':30,'used':167405,'remaining':4832595,'usable_quote':False}
            or a['status']!='missing' or a['billed_credits']!=30 or a['reserved_credits']!=30
            or proof['certified_quarantine']!={'root':ROOT,'before_ledger_sha256':BEFORE,'scope':'exact_one_cached_response_no_resend'}):
        raise ValueError('exact quarantine receipt differs')
    amended=dict(policy,quote_policy={'decimal_one':'retain_raw_non_executable'})
    observed=receipts.classify(row,record,amended)
    if observed.get('ineligible_quote_counts')!={'decimal_one':1} or observed['bill']!=30:raise ValueError('quarantine response classification changed')
    # Remaining original receipts use ORIGINAL strict policy, not the amendment.
    from evidence import captured_receipts
    other=copy.deepcopy(state);other['attempts'].pop(RID)
    captured_receipts(folder,rows,other,policy)
    reserved=sum(a['reserved_credits'] for a in state['attempts'].values())
    if reserved!=270 or sum(a['billed_credits'] for a in state['attempts'].values())!=210:raise ValueError('certified carry differs')
    return dict(untouched_ids=sorted(by_id.keys()-state['attempts'].keys()),reserved=reserved,missing={'certified_invalid_quote_quarantine':1})


def verify_approval(binding, *, fetch=None):
    import re
    import subprocess
    cert=binding['certificate'];pin=capture.identity(cert)
    if pin!=binding['certificate_sha256']:raise ValueError('certificate pin differs')
    approval=binding['approval'];url=approval['comment_url'];body=approval['comment_body']
    expected=f"APPROVED offline reconciliation: certificate {pin}, before-ledger {BEFORE}, after-ledger {cert['after_ledger_sha256']}, receipt {cert['receipt_sha256']}, no resend"
    if not re.fullmatch(r'https://github\.com/maxzipperman/value-finder/pull/[0-9]+#issuecomment-[0-9]+',url) or expected not in body.splitlines():raise ValueError('exact offline approval required')
    cid=url.rsplit('-',1)[-1]
    live=fetch(cid) if fetch else json.loads(subprocess.check_output(['gh','api',f'repos/maxzipperman/value-finder/issues/comments/{cid}'],text=True))
    if live.get('html_url')!=url or live.get('body')!=body or live.get('user',{}).get('login')!='maxzipperman':raise ValueError('offline approval changed')
    return cert
