"""Offline packet validator for the prospective pilot; no credential access."""
import json
import capture
import plan
import planner
import receipts
import mapping
import frame_binding


def packet(data, source):
    manifest=json.loads(data['manifest.json']);rows=json.loads(data['requests.json'])
    policy=json.loads(data['policy.json']);protocol=json.loads(data['protocol.json'])
    frame=json.loads(data['frame.json']);draw=json.loads(data['draw.json'])
    selected=json.loads(data['selected.json']);mappings=json.loads(data['mappings.json'])
    result=planner.select(frame,draw,protocol['sample_sizes'],committed_frame=manifest['frame_sha256'],
                          committed_protocol=manifest['protocol_sha256'],committed_seed_record=manifest['seed_record_sha256'],protocol=protocol)
    if selected!=result:raise ValueError('frozen selected frame differs')
    by_game=planner.unique(mappings,'game_id')
    if set(by_game)!=set(selected['selected']):raise ValueError('selected mapping denominator differs')
    originals={r['request_id']:r for r in json.loads(source['request-manifest.json'])['requests']}
    indexed=planner.unique(rows,'request_id')
    if not indexed:raise ValueError('no new requests; no purchase packet needed')
    for row in rows:
        if row['source']=='oddsapi/hist_odds':
            original=originals.get(row['request_id'])
            if original is None or original['priority']!=2 or not original['max_new_credits']:
                raise ValueError('not an original paid older ID')
            if row!=dict(original,url=plan.BASE+original['path']):
                raise ValueError('original older row changed')
        elif row['source']=='oddsapi/hist_event_odds':
            markets=row['params']['markets'].split(',');books=row['params']['bookmakers'].split(',')
            if not set(markets)<=set(mapping.MARKETS):raise ValueError('primary six markets only')
            expected=plan.make_request('odds',plan.ts(row['requested_utc']),books=books,markets=markets,event_id=row['event_id'],sport=row['sport'])
            if expected!=row:raise ValueError('props request reconstruction differs')
        elif row['source']=='oddsapi/hist_event_markets':
            expected=plan.make_request('markets',plan.ts(row['requested_utc']),event_id=row['event_id'],sport=row['sport'])
            if expected!=row:raise ValueError('selected availability reconstruction differs')
        else:raise ValueError('full listing stage not enabled')
    referenced=set()
    for op in mappings:
        ids=op['request_ids']
        if len(ids)!=len(set(ids)) or not set(ids)<=indexed.keys():raise ValueError('mapped request differs')
        if (not ids)!=bool(op['reason']):raise ValueError('missing explicit zero-row reason')
        referenced.update(ids)
    if referenced!=set(indexed):raise ValueError('unmapped paid request')
    cap=sum(r['max_new_credits'] for r in rows)
    if (manifest['request_count']!=len(rows) or manifest['max_new_credits']!=cap
            or manifest['request_list_sha256']!=capture.digest(data['requests.json'])
            or manifest['request_set_sha256']!=capture.identity(rows)):
        raise ValueError('exact list/set/cap differs')
    receipts.validate_policy(rows,policy)
    contract=json.loads(data['policy/PRIMARY-CONTRACT.json'])
    if (contract['props_cost_ceiling']!=244 or contract['older_cost_ceiling']!=100
            or set(contract['primary_markets'])!=set(mapping.MARKETS)):
        raise ValueError('primary contract changed')
    if protocol.get('execution_status')=='reviewed_for_execution':
        frame_binding.verify(data,source,rows,selected,mappings,frame)
    return {'status':'offline_validated_authority_required','requests':len(rows),'max_new_credits':cap,
            'selected_denominator':len(mappings),'full_denominator':selected['denominator'],
            'paid_entrypoint_available':True,'execution_protocol_ready':protocol.get('execution_status')=='reviewed_for_execution'}
