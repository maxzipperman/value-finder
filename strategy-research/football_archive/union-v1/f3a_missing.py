"""Prospective exact570-ID event-odds policy; separate future hub approval required."""
import hashlib
import json
import plan


def sha(obj):return hashlib.sha256(plan.canonical(obj)).hexdigest()


def expected(rows,ops):
    byid={o['opportunity_id']:o for o in ops}
    if len(rows)!=570 or len({r['request_id'] for r in rows})!=570:raise ValueError('Exact570-slot F3a cohort required')
    for row in rows:
        if (row['source']!='oddsapi/hist_event_odds' or row['sport']!=plan.NFL or row['seasons']!=[2025]
            or row['max_credits']!=60 or row['max_new_credits'] not in (0,60)
            or row['params']['markets']!=plan.SPECS['F3a'][1] or not row['opportunities']
            or any(byid[oid]['status']!='planned' for oid in row['opportunities'])):
            raise ValueError('Only original F3a six-market event-odds slots enabled')
    new=sorted(r['request_id'] for r in rows if r['max_new_credits'])
    identities={r['request_id']:sha({k:v for k,v in r.items() if k not in ('max_new_credits','cache_source','cache_sha256')}) for r in rows}
    return {'schema':'f3a-exact-event-slot-zero-billed-missing-v1','scope':'F3a2025 event-odds only',
        'request_identity_sha256':identities,'eligible_request_ids':new,'cohort_request_count':570,
        'max_missing':len(new),'maximum_missing_reserved_credits':60*len(new),'reservation_per_missing':60,
        'http_status':404,'error_code':'EVENT_NOT_FOUND','required_last_credits':0,
        'preserve_full_reservation':True,'no_resend':True,'opportunity_and_book_denominators_preserved':True,
        'featured_endpoint_extension':False}


def approval_line(obj,root):return f"APPROVED F3a exact missing policy: sha256 {sha(obj)}, max-missing {obj['max_missing']}, root {root}"


def valid(row,record,obj,base):
    identity={k:v for k,v in row.items() if k not in ('max_new_credits','cache_source','cache_sha256')}
    if (row['request_id'] not in obj['eligible_request_ids'] or sha(identity)!=obj['request_identity_sha256'].get(row['request_id'])
        or row['max_new_credits']!=60 or row['source']!='oddsapi/hist_event_odds'):
        raise base.Halt('Unlisted F3a event slot; separate review required')
    if (record['http_status']!=404 or record['cache_key']!=row['cache_key'] or record['sport']!=row['sport']
        or record['source']!=row['source'] or record['url']!=plan.BASE+row['path']
        or json.loads(record['params_json'])!=row['params']):raise base.Halt('F3a missing response identity/status differs')
    body=json.loads(record['body'])
    if not isinstance(body,dict) or body.get('error_code')!='EVENT_NOT_FOUND':raise base.Halt('Unreviewed F3a error')
    headers=json.loads(record['headers_json'])
    last,used,left=[base.integer(headers.get(k)) for k in ('x-requests-last','x-requests-used','x-requests-remaining')]
    if last!=0:raise base.Halt('Only exact zero-billed F3a missing permitted')
    return headers,used,left
