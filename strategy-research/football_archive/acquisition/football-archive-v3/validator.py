"""Offline exact-set, request/cost, source-integrity and immutable reuse validation."""
import csv
import hashlib
import json
from pathlib import Path


def canonical(v):return json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def verify(folder,expected_root=None,check_cache=False):
    from builder import close_time,request,iso,ts
    folder=Path(folder);cert=json.loads((folder/'FREEZE.json').read_text());expected=cert['file_sha256']
    actual={str(p.relative_to(folder)):sha(p) for p in sorted(folder.rglob('*')) if p.is_file() and p.name!='FREEZE.json'}
    if actual!=expected:raise ValueError('Frozen file set or bytes changed')
    root=hashlib.sha256(canonical(actual)).hexdigest()
    if root!=cert['bundle_root_sha256'] or (expected_root is not None and root!=expected_root):raise ValueError('Independently pinned root mismatch')
    cfg=json.loads((folder/'protocol.json').read_text());m=json.loads((folder/'request-manifest.json').read_text());rows=m['requests']
    if m['protocol_sha256']!=actual['protocol.json'] or cert['protocol_sha256']!=actual['protocol.json']:raise ValueError('Protocol not bound')
    if m['request_set_sha256']!=hashlib.sha256(canonical(rows)).hexdigest():raise ValueError('Request set not bound')
    if len(rows)!=m['request_count'] or len({r['cache_key'] for r in rows})!=len(rows):raise ValueError('Request count/dedup mismatch')
    for r in rows:
        if r['sealed'] or not set(r['seasons'])<=set(cfg['seasons']) or r['priority']!=(1 if min(r['seasons'])>=2023 else 2):raise ValueError('Season/priority mismatch')
        identity={'source':r['source'],'url':'https://api.the-odds-api.com/v4'+r['path'],'params':r['params']}
        if r['request_id']!=hashlib.sha256(canonical(identity)).hexdigest() or r['cache_key']!=hashlib.sha1(json.dumps(identity,sort_keys=True,default=str).encode()).hexdigest()[:20]:raise ValueError('Request identity mismatch')
        if (r['source']!='oddsapi/hist_odds' or r['path']!=f"/historical/sports/{r['sport']}/odds" or r['sport'] not in cfg['sports']
            or r['requested_utc']!=r['params']['date'] or r['params']['bookmakers'].split(',')!=cfg['book_panel']
            or r['params']['markets'].split(',')!=cfg['markets'] or r['params']['oddsFormat']!='decimal' or r['params']['dateFormat']!='iso'
            or set(r['params'])!={'bookmakers','markets','oddsFormat','dateFormat','date'}):raise ValueError('Unexpected request parameters')
        if r['max_credits']!=30 or r['max_new_credits'] not in (0,30) or r['retry_allowance']!=0:raise ValueError('Cost/retry mismatch')
        if r['max_new_credits']==0:
            rel=Path(r['cache_source'])
            if rel.is_absolute() or '..' in rel.parts or str(rel) not in actual or actual[str(rel)]!=r['cache_sha256']:raise ValueError('Missing/changed frozen reused cache')
            if check_cache:
                import pyarrow.parquet as pq
                from executor import validate_response
                record=pq.read_table(folder/rel).to_pylist()[0];validate_response(r,record,cfg)
    costs={str(k):sum(r['max_new_credits'] for r in rows if r['priority']==k) for k in (1,2)}
    if costs!=m['new_credits_by_priority'] or sum(costs.values())!=m['new_credits_after_probe_reuse'] or m['gross_credits']!=len(rows)*30:raise ValueError('Priority subtotals mismatch')
    if m['completed_probe_credits']!=1687 or sum(costs.values())+1687>cfg['budgets']['first_tranche_cumulative_credits']:raise ValueError('Cumulative cost mismatch')
    legacy=list(csv.DictReader((folder/'inputs/legacy-weather-request-list.csv').open()))
    sports={'nfl':'americanfootball_nfl','cfb':'americanfootball_ncaaf'}
    expected_mos={(sports[r['sport']],iso(ts(r['date_utc']))) for r in legacy if 'forecast_decision' in r['purposes']}
    actual_mos={(r['sport'],r['requested_utc']) for r in rows if 'MOS_original_evening_slot_diagnostic' in r['purposes']}
    if expected_mos!=actual_mos or len(actual_mos)!=665:raise ValueError('Exact MOS slot set mismatch')
    games=json.loads((folder/'canonical-games.json').read_text());gids={g['canonical_game_id'] for g in games}
    if len(gids)!=len(games) or any(g['season'] not in cfg['seasons'] for g in games):raise ValueError('Canonical identity/season mismatch')
    observations=json.loads((folder/'provider-observations.json').read_text())
    external_ids={g['canonical_game_id'] for g in json.loads((folder/'inputs/external-game-index.json').read_text())}
    if any(o['season'] not in cfg['seasons'] or (o.get('canonical_game_id') and o['canonical_game_id'] not in external_ids) for o in observations):raise ValueError('Observation binding/season mismatch')
    parent=json.loads((folder/'v2-origin-certificate.json').read_text())
    if hashlib.sha256(canonical(parent['file_sha256'])).hexdigest()!='954cd9cb6e763603a609f109043a77fedbb020e7f2fc3e4c626038fa5dd17c69':raise ValueError('Parent provenance root mismatch')
    for name in ('canonical-games.json','aliases.json','exclusions.json','inputs/external-game-index.json'):
        if actual[name]!=parent['file_sha256'][name]:raise ValueError('Inherited matching metadata changed')
    raw_observations=[{k:v for k,v in o.items() if k!='source_body_sha256'} for o in observations]
    if hashlib.sha256(canonical(raw_observations)+b'\n').hexdigest()!=parent['file_sha256']['provider-observations.json']:raise ValueError('Inherited observation history changed')
    headers=list(csv.DictReader((folder/'probe-response-provenance.csv').open()))
    source_hashes={r['cache_key']:r['sha256'] for r in headers if r.get('cache_key')}
    if any(o['source_body_sha256']!=source_hashes.get(o['source_cache_key']) for o in observations):raise ValueError('Observation response hash unbound')
    registry=json.loads((folder/'opportunity-registry.json').read_text())
    if {(r['sport'],r['provider_id']) for r in registry}!={(o['sport'],o['provider_id']) for o in observations}:raise ValueError('Observed opportunities dropped')
    maps=json.loads((folder/'close-candidates.json').read_text());actual_maps={(r['canonical_game_id'],r['basis'],r['requested_utc']) for r in maps}
    expected_maps={(g['canonical_game_id'],'provider_anchor',close_time(g['close_anchor_utc'])) for g in games}
    expected_maps|={(g['canonical_game_id'],'independent_schedule',close_time(g['scheduled_utc'])) for g in games if abs(g['schedule_discrepancy_minutes'])>5}
    if actual_maps!=expected_maps or len(maps)!=len(expected_maps):raise ValueError('Exact close candidates mismatch')
    byid={r['request_id']:r for r in rows}
    for link in maps:
        r=byid.get(link['request_id'])
        if not r or r['cache_key']!=link['cache_key'] or link['canonical_game_id'] not in r['canonical_game_ids']:raise ValueError('Close/request linkage mismatch')
    for name,count in [('legacy-close-reconciliation.json',2293),('original-85-close-resolution.json',85)]:
        if len(json.loads((folder/name).read_text()))!=count:raise ValueError('Legacy exclusions missing')
    required={'executor.py','validator.py','coverage_report.py','price_eligibility.py','builder.py','test_v3.py','runtime-lock.json',
              'archive_markets/oddsapi/bulk.py','archive_markets/cache.py','archive_markets/http.py','archive_markets/settings.py'}
    if not required<=set(actual):raise ValueError('Execution/test dependencies not frozen')
    return {'bundle_root_sha256':root,'manifest_requests':len(rows),'new_paid_requests':sum(r['max_new_credits']>0 for r in rows),
            'new_credits':sum(costs.values()),'phase_credits':costs,'all_MOS_slots_preserved':True,'all_observed_opportunities_retained':True,
            'execution_sources_bound':True,'reused_cache_hashes_checked':True,'independently_pinned_root_checked':expected_root is not None}


if __name__=='__main__':
    import sys
    sys.dont_write_bytecode=True
    print(json.dumps(verify(sys.argv[1],sys.argv[2] if len(sys.argv)>2 else None,check_cache=True),indent=2))
