"""Read-only acquisition audit; no outcomes, credentials, network or strategy scoring.
Run with pyarrow and ijson installed; writes only the explicitly named derived output.
"""
import argparse, hashlib, json, sys
from pathlib import Path
from collections import Counter, defaultdict
from datetime import datetime

def guard(event,args):
    if event in ('socket.connect','socket.getaddrinfo'): raise RuntimeError('Audit network forbidden')
    if event=='open' and isinstance(args[0],(str,bytes)):
        p=str(args[0])
        if Path(p).name.startswith('.env') or '/data/forward/' in p or p.endswith(('games.parquet','scores.parquet')):
            raise RuntimeError('Credentials, forward data and outcomes forbidden')
sys.addaudithook(guard)
import pyarrow.parquet as pq
import ijson

def digest(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for chunk in iter(lambda:f.read(8*1024*1024),b''):h.update(chunk)
    return h.hexdigest()
def ts(x):return datetime.fromisoformat(x.replace('Z','+00:00'))
def canon(x):return json.dumps(x,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--bundle',type=Path,required=True);ap.add_argument('--runtime',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
    b,r=a.bundle,a.runtime
    cert=json.loads((b/'FREEZE.json').read_text());m=json.loads((b/'request-manifest.json').read_text());s=json.loads((r/'spending-ledger.json').read_text())
    files={str(p.relative_to(b)):digest(p) for p in sorted(b.rglob('*')) if p.is_file() and p.name!='FREEZE.json'}
    assert files==cert['file_sha256'];assert hashlib.sha256(canon(files)).hexdigest()==cert['bundle_root_sha256']==s['bundle_root_sha256']
    assert s['pending'] is None and s['stopped'] is None and s['status']=='recent_complete_stopped_before_older'
    recent=[x for x in m['requests'] if x['priority']==1];old=[x for x in m['requests'] if x['priority']==2]
    assert set(s['attempts'])=={x['request_id'] for x in recent if x['max_new_credits']}
    assert set(s['cache_reuse'])=={x['request_id'] for x in recent if not x['max_new_credits']}
    aliases={(x['sport'],x['provider_name']):x['canonical_team_key'] for x in json.loads((b/'aliases.json').read_text())}
    games={x['canonical_game_id']:x for x in json.loads((b/'canonical-games.json').read_text())}
    pidmap=defaultdict(set)
    for g in games.values():
        for pid in g['provider_ids']:pidmap[(g['sport'],pid)].add(g['canonical_game_id'])
    orientations=defaultdict(set);kickoffs=defaultdict(set);observed=defaultdict(set);bygid=defaultdict(set);event_counts=Counter();lag=Counter();missing=[];counter_bills=[];checks=0
    for row in recent:
        rid=row['request_id'];attempt=s['attempts'].get(rid)
        if attempt:
            p=Path(attempt['response_path']);assert digest(p)==attempt['response_sha256'];assert digest(r/'receipts'/f'{rid}.json')==attempt['receipt_sha256'];checks+=2
        else:
            p=b/row['cache_source'];assert digest(p)==row['cache_sha256']==s['cache_reuse'][rid]
        rec=pq.read_table(p).to_pylist()[0];body=json.loads(rec['body']);head=json.loads(rec['headers_json'])
        assert rec['cache_key']==row['cache_key'];assert json.loads(rec['params_json'])==row['params']
        gap=(ts(row['requested_utc'])-ts(body['timestamp'])).total_seconds();lag[str(int(gap))]+=1
        if attempt:counter_bills.append(int(head['x-requests-last']))
        if attempt and attempt['status']=='missing':
            assert gap>600 and attempt['missing_reason']=='snapshot_lag'
            missing.append({'request_id':rid,'requested_utc':row['requested_utc'],'returned_utc':body['timestamp'],'next_snapshot_utc':body['next_timestamp'],'lag_seconds':gap,'intended_game_ids':row['canonical_game_ids'],'intended_book_market_cells':len(row['canonical_game_ids'])*30,'returned_stale_event_count':len(body['data'])})
            continue
        assert 0<=gap<=600 and rec['http_status']==200
        for e in body['data']:
            k=ts(e['commence_time']);season=k.year if k.month>=7 else k.year-1
            event_counts['returned_event_sightings']+=1
            if season not in (2023,2024,2025):
                event_counts['outside_recent_season_sightings']+=1;event_counts['outside_recent_season_'+str(season)]+=1;continue
            key=(row['sport'],e['id']);pair=tuple(aliases.get((row['sport'],e.get(z))) for z in ['home_team','away_team'])
            if None not in pair:orientations[key].add(pair)
            kickoffs[key].add(e['commence_time']);observed[key].add(body['timestamp'])
            gids=pidmap.get(key,set())
            if len(gids)!=1:event_counts['unbound_or_ambiguous_sightings']+=1
            else:bygid[next(iter(gids))].add(e['id'])
    report=r/'coverage-report.json';report_sha=digest(report)
    with report.open('rb') as f:coverage=next(ijson.items(f,'before_older_slice'))
    strata=coverage.pop('sport_season_month_book_market_lead_first_observed_strata');grouped={x:defaultdict(Counter) for x in ['sport_season','book','market','lead','first_observed']}
    for key,counts in strata.items():
        sport,season,month,book,market,lead,first=key.split('|')
        for dimension,value in [('sport_season',sport+'|'+season),('book',book),('market',market),('lead',lead),('first_observed',first)]:
            for name in ['intended_entry_instruments','intended_instruments_with_valid_pair','quote_present','missing_quote']:
                grouped[dimension][value][name]+=counts.get(name,0)
    missing_ids={x['request_id'] for x in missing};missing_rows=[]
    with report.open('rb') as f:
        for x in ijson.items(f,'intended_decision_pair_accounting.item'):
            if x['request_id'] in missing_ids:missing_rows.append(x)
    for x in missing:
        x['coverage_rows']=sum(z['request_id']==x['request_id'] for z in missing_rows)
        x['coverage_statuses']=dict(Counter(z['pair_status'] for z in missing_rows if z['request_id']==x['request_id']))
        x['targets_seen_elsewhere']=sum(bool(bygid.get(g)) for g in x['intended_game_ids'])
    out={'bundle_root_sha256':s['bundle_root_sha256'],'ledger_sha256':digest(r/'spending-ledger.json'),'coverage_report_sha256':report_sha,'coverage_report_bytes':report.stat().st_size,'attempt_status_counts':dict(Counter(x['status'] for x in s['attempts'].values())),'paid_files_rehashed':checks,'reused':len(s['cache_reuse']),'new_credits_from_response_headers':sum(counter_bills),'reserved':sum(x['reserved_credits'] for x in s['attempts'].values()),'provider_used':s['provider_used'],'provider_remaining':s['provider_remaining'],'conservative_external_debit':s['other_usage_reserved'],'older_slice':{'requests':len(old),'paid':sum(x['max_new_credits']>0 for x in old),'reused':sum(x['max_new_credits']==0 for x in old),'credits':sum(x['max_new_credits'] for x in old)},'snapshot_lag_seconds_histogram':dict(lag),'missing':missing,'event_metadata':{**event_counts,'unique_recent_provider_events':len(observed),'canonical_games_observed':len(bygid),'canonical_games_with_multiple_observed_provider_ids':sum(len(v)>1 for v in bygid.values()),'events_with_multiple_kickoff_values':sum(len(v)>1 for v in kickoffs.values()),'events_with_reversed_canonical_home_away':sum(any((q[1],q[0]) in v for q in v) for v in orientations.values())},'identity_examples':{'multi_id_games':[{'canonical_game_id':g,'provider_ids':sorted(v)} for g,v in sorted(bygid.items()) if len(v)>1][:5],'swapped_events':[{'sport':k[0],'provider_id':k[1],'canonical_orientations':sorted(v)} for k,v in sorted(orientations.items()) if any((q[1],q[0]) in v for q in v)][:5]},'coverage':coverage,'coverage_strata_aggregates':{k:dict(v) for k,v in grouped.items()},'limitations':['No outcome joins or strategy grading','Metadata-only identities do not certify actual first-play time','Missing-slot effects measured on intended instruments, not hypothetical bets','Inherited opportunity registry spans 2020–25']}
    a.output.write_text(json.dumps(out,indent=2)+'\n');print(json.dumps({k:out[k] for k in ['paid_files_rehashed','new_credits_from_response_headers','coverage_report_bytes','event_metadata','missing']},indent=2))
if __name__=='__main__':main()
