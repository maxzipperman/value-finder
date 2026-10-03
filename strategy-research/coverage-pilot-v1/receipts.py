"""Prospective response classification and receipt checks. No I/O or sends."""
import hashlib
import json
import math
from planner import digest, InvalidPlan
from timing import utc


def integer(v):
    if isinstance(v,bool) or not str(v).isdigit(): raise InvalidPlan('invalid counter')
    return int(v)


def validate_policy(rows, policy):
    by_id = {r['request_id']: r for r in rows}
    if len(by_id) != len(rows): raise InvalidPlan('duplicate policy rows')
    for key, source in [('snapshot_lag_ids', None), ('event_not_found_ids', 'oddsapi/hist_event_odds')]:
        ids = policy[key]
        if not isinstance(ids,list) or len(ids) != len(set(ids)) or not set(ids) <= by_id.keys():
            raise InvalidPlan('finite policy IDs differ')
        if source and any(by_id[r]['source'] != source for r in ids):
            raise InvalidPlan('missing policy endpoint differs')
        reason = 'snapshot_lag' if source is None else 'event_not_found'
        cap = policy['max_missing'][reason]
        if type(cap) is not int or not 0 <= cap <= len(ids):
            raise InvalidPlan('finite missing cap differs')
    if set(policy) != {'snapshot_lag_ids','event_not_found_ids','max_missing'} or set(policy['max_missing']) != {'snapshot_lag','event_not_found'}:
        raise InvalidPlan('unexpected missing policy')


def odds_shape(event):
    seen_books = set()
    for book in event['bookmakers']:
        if not isinstance(book,dict) or not isinstance(book.get('key'),str) or not book['key'] or book['key'] in seen_books or not isinstance(book.get('markets'),list):
            raise InvalidPlan('malformed/duplicate bookmaker')
        seen_books.add(book['key']); seen_markets = set()
        for market in book['markets']:
            if not isinstance(market,dict) or not isinstance(market.get('key'),str) or not market['key'] or market['key'] in seen_markets or not isinstance(market.get('outcomes'),list):
                raise InvalidPlan('malformed/duplicate market')
            seen_markets.add(market['key'])
            for outcome in market['outcomes']:
                if not isinstance(outcome,dict) or not isinstance(outcome.get('name'),str) or not outcome['name']:
                    raise InvalidPlan('malformed outcome')
                price = outcome.get('price')
                if type(price) not in (int,float) or not math.isfinite(price) or price <= 1:
                    raise InvalidPlan('invalid decimal price')
                if 'point' in outcome and (type(outcome['point']) not in (int,float) or not math.isfinite(outcome['point'])):
                    raise InvalidPlan('invalid offered point')


def classify(row, record, policy):
    rid = row['request_id']; identity = {k:row[k] for k in ('source','url','params')}
    if digest(identity) != rid:
        raise InvalidPlan('request identity differs')
    cache_key = hashlib.sha1(json.dumps(identity,sort_keys=True,default=str).encode()).hexdigest()[:20]
    if (record['source'] != row['source'] or record['url'] != row['url'] or record['sport'] != row['sport']
            or record['cache_key'] != cache_key or row['cache_key'] != cache_key
            or json.loads(record['params_json']) != row['params']):
        raise InvalidPlan('response request binding differs')
    headers = json.loads(record['headers_json'])
    bill, used, left = [integer(headers.get(k)) for k in ('x-requests-last','x-requests-used','x-requests-remaining')]
    if bill > row['max_new_credits']: raise InvalidPlan('overcharge')
    body = json.loads(record['body']); status = record['http_status']
    if status == 404:
        if (row['source'] != 'oddsapi/hist_event_odds' or rid not in policy['event_not_found_ids']
                or not isinstance(body,dict) or body.get('error_code') != 'EVENT_NOT_FOUND' or bill != 0):
            raise InvalidPlan('unapproved HTTP missing response')
        return {'status':'missing','reason':'event_not_found','bill':bill,'used':used,'remaining':left}
    if status != 200: raise InvalidPlan('HTTP halt; retain reservation')
    at = utc(body['timestamp']); requested = utc(row['params']['date'])
    if requested != utc(row['requested_utc']): raise InvalidPlan('request clocks differ')
    if not utc(body['previous_timestamp']) < at < utc(body['next_timestamp']):
        raise InvalidPlan('malformed snapshot neighbors')
    lag = (requested-at).total_seconds()
    if lag < 0: raise InvalidPlan('future snapshot')
    payload = body['data']
    if row['source'] in {'oddsapi/hist_event_odds','oddsapi/hist_event_markets'}:
        suffix='odds' if row['source']=='oddsapi/hist_event_odds' else 'markets'
        expected_url = 'https://api.the-odds-api.com/v4/historical/sports/'+row['sport']+'/events/'+str(row['event_id'])+'/'+suffix
        if (not isinstance(payload,dict) or payload.get('id') != row['event_id']
                or payload.get('sport_key') != row['sport'] or row['url'] != expected_url
                or not isinstance(payload.get('bookmakers'),list)):
            raise InvalidPlan('event odds identity/schema differs')
        utc(payload['commence_time'])
        if suffix=='odds':odds_shape(payload)
        else:
            seen_books=set()
            for book in payload['bookmakers']:
                if not isinstance(book,dict) or not book.get('key') or book['key'] in seen_books or not isinstance(book.get('markets'),list):
                    raise InvalidPlan('malformed market metadata bookmaker')
                seen_books.add(book['key']);seen_markets=set()
                for market in book['markets']:
                    if not isinstance(market,dict) or not market.get('key') or market['key'] in seen_markets or 'outcomes' in market:
                        raise InvalidPlan('market metadata must contain unique keys, not prices')
                    seen_markets.add(market['key'])
                    if utc(market['last_update'])>at:raise InvalidPlan('future market metadata')
    elif row['source'] == 'oddsapi/hist_odds':
        if not isinstance(payload,list): raise InvalidPlan('featured schema differs')
        seen_events = set()
        for event in payload:
            if not isinstance(event,dict) or not event.get('id') or event.get('sport_key') != row['sport'] or not isinstance(event.get('bookmakers'),list):
                raise InvalidPlan('featured event malformed')
            if event['id'] in seen_events: raise InvalidPlan('duplicate featured event')
            seen_events.add(event['id'])
            utc(event['commence_time']); odds_shape(event)
    else: raise InvalidPlan('unreviewed endpoint')
    if lag > 600:
        if rid not in policy['snapshot_lag_ids']: raise InvalidPlan('lag not predeclared')
        return {'status':'missing','reason':'snapshot_lag','bill':bill,'used':used,'remaining':left}
    return {'status':'completed','reason':None,'bill':bill,'used':used,'remaining':left}


def receipt_union(rows, attempts, evidence, policy):
    """Validate caller-captured exact receipt/raw-byte hashes and decoded record.

    evidence[rid] contains raw bytes digest calculated by the safe filesystem
    adapter, receipt bytes, and decoded raw record. Authentication of external
    ledger pin and read-only path confinement belong to that adapter.
    """
    validate_policy(rows, policy)
    by_id = {r['request_id']:r for r in rows}
    if len(by_id) != len(rows) or not set(attempts) <= by_id.keys() or set(evidence) != set(attempts):
        raise InvalidPlan('attempt/evidence set differs')
    missing = {'snapshot_lag':0,'event_not_found':0}
    for rid, attempt in attempts.items():
        e = evidence[rid]; receipt_bytes = e['receipt_bytes']; proof = json.loads(receipt_bytes)
        if (attempt.get('send_started') is not True or attempt['status'] not in {'completed','missing'}
                or attempt['reserved_credits'] != by_id[rid]['max_new_credits']
                or hashlib.sha256(receipt_bytes).hexdigest() != attempt['receipt_sha256']
                or e['response_sha256'] != attempt['response_sha256']
                or proof['response_sha256'] != e['response_sha256']
                or proof['request_id'] != rid or json.dumps(proof['record'],sort_keys=True,default=str) != json.dumps(e['record'],sort_keys=True,default=str)):
            raise InvalidPlan('prospective receipt/raw binding differs')
        result = classify(by_id[rid],e['record'],policy)
        if proof['classification'] != result or result['status'] != attempt['status'] or result['bill'] != attempt['billed_credits']:
            raise InvalidPlan('receipt classification differs')
        if result['reason']: missing[result['reason']] += 1
    if any(missing[k] > policy['max_missing'][k] for k in missing):
        raise InvalidPlan('finite missing policy exhausted')
    return {'attempted_ids':sorted(attempts),'untouched_ids':sorted(by_id.keys()-attempts.keys()),
            'reserved':sum(a['reserved_credits'] for a in attempts.values()),'missing':missing}
