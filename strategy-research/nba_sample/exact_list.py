"""Offline N0 list; preserves the NBA client's original URL, parameters and cache identity."""
import csv,hashlib,json,sys
from pathlib import Path
from datetime import datetime
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'sharp-markets/src'))
from markets.cache import cache_key
BASE='https://api.the-odds-api.com/v4'

def canonical(x):return json.dumps(x,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()
def build():
    metadata=Path(__file__).parent/'metadata.json';data=json.loads(metadata.read_text());assert not data['problems']
    rows=[];raw_roots={ROOT/'sharp-markets/data/raw',Path.home()/'code/value-finder/sharp-markets/data/raw'}
    runtime=Path.home()/'Library/Application Support/ValueFinder/football-acquisition-state'
    raw_roots.update(runtime.glob('*/data/raw'))
    for stamp in data['requested_utc']:
        date=datetime.fromisoformat(stamp).strftime('%Y-%m-%dT%H:%M:%SZ');path='/historical/sports/basketball_nba/odds'
        params={'bookmakers':'pinnacle,lowvig,betonlineag','markets':'h2h','oddsFormat':'decimal','dateFormat':'iso','date':date}
        key=cache_key('oddsapi_hist',BASE+path,params)
        hits=[p for base in raw_roots for p in (base/'nba/oddsapi_hist').glob('*/'+key+'.parquet')]
        if hits:raise ValueError('Existing NBA response requires reviewed reuse validation before freezing')
        identity={'source':'oddsapi_hist','url':BASE+path,'params':params}
        rows.append({'request_id':hashlib.sha256(canonical(identity)).hexdigest(),'cache_key':key,'sport':'nba','odds_sport_key':'basketball_nba','source':'oddsapi_hist','path':path,'params':params,'requested_utc':date,'max_credits':10,'max_new_credits':10,'retry_allowance':0,'sealed':False})
    assert len(rows)==754 and sum(x['max_new_credits'] for x in rows)==7540
    here=Path(__file__).parent;request_set=hashlib.sha256(canonical(rows)).hexdigest()
    (here/'requests.json').write_bytes(canonical(rows)+b'\n')
    with (here/'request-list.csv').open('w',newline='') as f:
        fields=('request_id','cache_key','requested_utc','max_new_credits');writer=csv.DictWriter(f,fieldnames=fields,lineterminator='\n');writer.writeheader();writer.writerows({k:r[k] for k in fields} for r in rows)
    summary={'stage':'N0','scope':'Jan5-11,2026ET;NBA2025-26;scheduled-proxy scheduleA','metadata_sha256':hashlib.sha256(metadata.read_bytes()).hexdigest(),'source_metadata_fields':['event_ticker','ticker','title','open_time','close_time','expected_expiration_time'],'games':len(data['games']),'requests':len(rows),'max_new_credits':7540,'request_set_sha256':request_set,'request_list_sha256':hashlib.sha256((here/'request-list.csv').read_bytes()).hexdigest(),'raw_roots_checked':sorted(str(p) for p in raw_roots),'paid_calls':0,'outcomes_inspected':False,'settlement_based_exclusions':False,'paid_execution_enabled':False,'remaining_gates':['pin latest completed global predecessor','reviewed shared cumulative driver','fresh cross-store reuse check','exact frozen root and current-head agreements','hub exact paid approval']}
    (here/'manifest.json').write_bytes(canonical(summary)+b'\n');print(json.dumps(summary,indent=2))
if __name__=='__main__':build()
