"""Recheck final certainty pins and selected as-of request mappings before purchase."""
import json
import capture
import classifier
import mapping
from timing import utc


def verify(data,source,rows,selected,mappings,frame):
    proof=json.loads(data['certainty-source-proof.json'])
    if (capture.digest(data['frame.json'])!=proof['frame_sha256']
            or capture.digest(data['slot-map.json'])!=proof['requested_slot_map_sha256']
            or capture.digest(data['classifier-contract.json'])!=proof['contract_sha256']):
        raise ValueError('final certainty/slot/contract pins differ')
    protected=proof['older_metadata_proof']
    for name,sha in protected['metadata_files'].items():
        if capture.digest(source[name])!=sha:raise ValueError('certainty metadata source changed')
    if capture.digest(data['code/plan.py'])!=protected['early_decision_rule_source_sha256']:
        raise ValueError('protected binding rule changed')
    oldmap={r['game_id']:r for r in json.loads(data['slot-map.json'])}
    games={r['game_id']:r for r in frame};by_id={r['request_id']:r for r in rows}
    observations=json.loads(source['provider-observations.json'])
    originals=json.loads(source['request-manifest.json'])['requests']
    original_by_id={r['request_id']:r for r in originals}
    contract=json.loads(data['classifier-contract.json'])
    if contract['market']!='totals' or contract['reference']!='pinnacle' or contract['replace_failed_slots'] is not False:
        raise ValueError('older primary classifier contract differs')
    protocol=json.loads(data['protocol.json'])
    if protocol.get('candidate_books')!=contract['book_panel'] or protocol.get('primary_markets')!=list(mapping.MARKETS):
        raise ValueError('fixed books/six markets differ')
    for item in mappings:
        game=games[item['game_id']];sport=game['stratum'].split('/')[1]
        if game['stratum'].startswith('older/'):
            declared=oldmap[item['game_id']]
            if not declared['binding']:raise ValueError('selected unknown old game has no designated slots')
            early=declared['slots']['EARLY'];close=declared['slots']['CLOSE']
            expected=mapping.older_slots(dict(game,sport=sport,binding=True),originals,[close['request_id']],primary_close_id=close['request_id'])
            if expected['primary_request_ids']!=[early['request_id'],close['request_id']]:
                raise ValueError('original daily/primary-close mapping differs')
            bound=classifier.bind_asof(observations,game['game_id'],early['requested_utc'])
            if bound.get('event_id')!=early['provider_id'] or utc(bound['binding_observed_utc'])!=utc(early['binding']['returned_utc']):
                raise ValueError('early asof provider changed')
            close_binding=close['binding']
            if utc(close_binding['returned_utc'])>utc(close['requested_utc']) or not any(
                    o.get('canonical_game_id')==game['game_id'] and o['provider_id']==close['provider_id']
                    and utc(o['returned_utc'])==utc(close_binding['returned_utc'])
                    and utc(o['provider_kickoff_utc'])==utc(close_binding['provider_kickoff_utc'])
                    and (o['home_team'],o['away_team'])==(close_binding['home_team'],close_binding['away_team']) for o in observations):
                raise ValueError('frozen close provider has no decision-time source binding')
            expected_ids={early['request_id'],close['request_id']}
            paid=set(item['request_ids']);reused=set(item.get('reused_request_ids',[]))
            if paid & reused or paid|reused!=expected_ids:raise ValueError('complete designated old slots required')
            for rid in paid:
                if by_id[rid]['source']!='oddsapi/hist_odds':raise ValueError('old slot replaced with new endpoint')
        else:
            ops=game.get('source_opportunities',[])
            if {op['slot'] for op in ops}!={'T24','CLOSE_T10'}:raise ValueError('both props slots required')
            allowed=set()
            for op in ops:
                if op['status']!='bound':raise ValueError('unbound props zero row cannot purchase')
                bound=classifier.bind_asof(observations,game['game_id'],op['requested_utc'])
                if (bound.get('event_id')!=op['event_id'] or utc(bound['binding_observed_utc'])!=utc(op['binding_observed_utc'])):
                    raise ValueError('props decision-time mapping differs')
                allowed.add((op['event_id'],utc(op['requested_utc'])))
            seen=set()
            for rid in item['request_ids']:
                r=by_id[rid];key=(r.get('event_id'),utc(r['requested_utc']))
                if r['sport']!=sport or key not in allowed:raise ValueError('props request outside designated identity/slot')
                if r['source']=='oddsapi/hist_event_odds':
                    if not set(r['params']['bookmakers'].split(','))<=set(protocol['candidate_books']):
                        raise ValueError('undeclared candidate book')
                    seen.add(key)
            # Any reused slots/cells need the exact frozen compatible cache union.
            required={(eid,at,b,m) for eid,at in allowed for b in protocol['candidate_books'] for m in mapping.MARKETS}
            covered=set()
            for rid in item['request_ids']:
                r=by_id[rid]
                if r['source']=='oddsapi/hist_event_odds':
                    covered.update((r['event_id'],utc(r['requested_utc']),b,m) for b in r['params']['bookmakers'].split(',') for m in r['params']['markets'].split(','))
            for r in item.get('reused_slots',[]):
                if r['sport']!=sport:raise ValueError('reused props sport differs')
                covered.update((r['event_id'],utc(r['requested_utc']),b,m) for b in r['books'] for m in r['markets'])
            if covered!=required:raise ValueError('complete designated props cells required')
    return True
