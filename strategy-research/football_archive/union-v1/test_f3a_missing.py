import copy
import json
from pathlib import Path
import sys
import pytest
sys.path.insert(0,str(Path(__file__).parent))
import f3a_missing as policy
import plan
HERE=Path(__file__).parent


class Base:
    class Halt(Exception):pass
    @staticmethod
    def integer(value):
        if not isinstance(value,str) or not value.isdigit():raise Base.Halt('Numeric counter required')
        return int(value)


def inputs():
    packet=HERE/'F3a';return json.loads((packet/'requests.json').read_text()),json.loads((packet/'opportunities.json').read_text())


def test_exact_frozen570_and60_reservations():
    rows,ops=inputs();obj=policy.expected(rows,ops)
    assert obj['cohort_request_count']==obj['max_missing']==570 and obj['maximum_missing_reserved_credits']==34200
    assert obj==json.loads((HERE/'F3a/exact-missing-policy.json').read_text())
    assert obj['featured_endpoint_extension'] is False


@pytest.mark.parametrize('fault',['none','id','date','books','market','key','endpoint','status','code','bill','counters','body'])
def test_exact_missing_identity_error_billing(fault):
    rows,ops=inputs();obj=policy.expected(rows,ops);row=copy.deepcopy(rows[0])
    rec={'http_status':404,'cache_key':row['cache_key'],'sport':row['sport'],'source':row['source'],'url':plan.BASE+row['path'],
        'params_json':json.dumps(row['params']),'body':'{"error_code":"EVENT_NOT_FOUND"}',
        'headers_json':'{"x-requests-last":"0","x-requests-used":"96149","x-requests-remaining":"4903851"}'}
    if fault=='id':row['event_id']='OTHER'
    if fault in ('date','books','market'):
        params=json.loads(rec['params_json']);params[{'date':'date','books':'bookmakers','market':'markets'}[fault]]='OTHER';rec['params_json']=json.dumps(params)
    if fault=='key':rec['cache_key']='OTHER'
    if fault=='endpoint':rec['source']='oddsapi/hist_odds'
    if fault=='status':rec['http_status']=403
    if fault=='code':rec['body']='{"error_code":"OTHER"}'
    if fault=='bill':rec['headers_json']='{"x-requests-last":"60","x-requests-used":"96209","x-requests-remaining":"4903791"}'
    if fault=='counters':rec['headers_json']='{"x-requests-last":"0"}'
    if fault=='body':rec['body']='[]'
    if fault=='none':assert policy.valid(row,rec,obj,Base)[1:]==(96149,4903851)
    else:
        with pytest.raises(Exception):policy.valid(row,rec,obj,Base)


def test_reused_id_never_enabled_for_missing_send():
    rows,ops=inputs();rows[0].update(max_new_credits=0,cache_source='SYNTHETIC',cache_sha256='SYNTHETIC')
    obj=policy.expected(rows,ops)
    assert rows[0]['request_id'] not in obj['eligible_request_ids'] and obj['max_missing']==569 and obj['maximum_missing_reserved_credits']==34140
