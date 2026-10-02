"""Proposed, separately authenticated continuation-only 404 exclusions; never a resend."""
import hashlib
import json
from pathlib import Path
import plan


def expected(rows,ops):
    by_id={o['opportunity_id']:o for o in ops}
    eligible=[]
    for row in rows:
        if row['max_new_credits']:
            if (row['max_new_credits']!=row['max_credits'] or not row['opportunities']
                or any(by_id[oid]['status']!='planned' for oid in row['opportunities'])):
                raise ValueError('Only original bound event-odds slots are eligible')
            eligible.append(row['request_id'])
    if len(eligible)!=1186:raise ValueError('Exact never-sent bound differs')
    return {'schema':'exact-unsent-zero-billed-event-not-found-v2','scope':'F2 second continuation only',
        'original_root':'4053703d09fdcedb6ce1608c8a5a0d09d3e702a6426891463163224e10af792e',
        'eligible_request_ids':sorted(eligible),'max_missing':1186,'maximum_missing_reserved_credits':23720,
        'http_status':404,'error_code':'EVENT_NOT_FOUND','required_last_credits':0,
        'preserve_full_reservation':True,'no_resend':True,'original_identity_classes_preserved':True,
        'opportunity_and_book_denominators_preserved':True}


def load(packet,manifest,rows):
    obj=json.loads((Path(packet)/'exact-missing-policy.json').read_text())
    ops=json.loads((Path(packet)/'opportunities.json').read_text())
    if obj!=expected(rows,ops) or sha(obj)!=manifest['exact_missing_policy_sha256']:
        raise ValueError('Exact prospective provider-only missing policy differs')
    return obj


def sha(obj):return hashlib.sha256(plan.canonical(obj)).hexdigest()


def approval_line(obj,root):return f"APPROVED exact missing policy: sha256 {sha(obj)}, max-missing {obj['max_missing']}, root {root}"


def valid(row,record,obj,base):
    if row['request_id'] not in obj['eligible_request_ids'] or row['max_new_credits']!=row['max_credits']:
        raise base.Halt('Unlisted 404 requires separate offline review')
    if (record['http_status']!=404 or record['cache_key']!=row['cache_key'] or record['sport']!=row['sport']
        or record['source']!=row['source'] or record['url']!=plan.BASE+row['path']
        or json.loads(record['params_json'])!=row['params']):
        raise base.Halt('Prospective 404 identity/status differs')
    try:
        body=json.loads(record['body'])
        if not isinstance(body,dict) or body.get('error_code')!='EVENT_NOT_FOUND':raise ValueError()
    except (ValueError,TypeError):raise base.Halt('Unreviewed/malformed 404 error body') from None
    headers=json.loads(record['headers_json'])
    last,used,left=[base.integer(headers.get(k)) for k in ('x-requests-last','x-requests-used','x-requests-remaining')]
    if last!=0:raise base.Halt('Only exact zero-billed missing is enabled')
    return headers,used,left
