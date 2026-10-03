"""Build a source-only finite listing packet; no runtime, secrets or network."""
import argparse
import csv
import hashlib
import io
import json
from pathlib import Path


def canonical(x):return json.dumps(x,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()


def prepare(folder):
    here=Path(__file__).parent
    props=here.parent/'nfl-props-archive-v1'
    sources=[props/'discovery'/s/'listing-discovery-net' for s in ('americanfootball_nfl','americanfootball_ncaaf')]
    records=[];request_rows=[]
    for source in sources:
        raw=(source/'request-list.csv').read_bytes();m=json.loads((source/'manifest.json').read_text())
        if hashlib.sha256(raw).hexdigest()!=m['request_list_sha256']:raise ValueError('Reviewed listing source changed')
        records.extend(csv.DictReader(io.StringIO(raw.decode())))
    records.sort(key=lambda r:(r['requested_utc'],r['request_id']))
    for r in records:
        # Reconstruct the exact identity; sport is determined from the original per-sport lists.
        candidates=[]
        for sport in ('americanfootball_nfl','americanfootball_ncaaf'):
            params=json.loads(r['params_json']);identity={'source':'oddsapi/hist_events','url':f'https://api.the-odds-api.com/v4/historical/sports/{sport}/events','params':params}
            if hashlib.sha256(canonical(identity)).hexdigest()==r['request_id']:
                candidates.append(dict(identity,request_id=r['request_id'],cache_key=hashlib.sha1(json.dumps(identity,sort_keys=True,default=str).encode()).hexdigest()[:20],sport=sport,event_id=None,requested_utc=r['requested_utc'],max_new_credits=1,retry_allowance=0,sealed=False))
        if len(candidates)!=1:raise ValueError('Listing identity invalid')
        request_rows.extend(candidates)
    if len(records)!=1544:raise ValueError('Exact first listing cap changed')
    if folder.exists():raise ValueError('New output required; no silent packet replacement')
    folder.mkdir(parents=True)
    f=io.StringIO(newline='');w=csv.DictWriter(f,fieldnames=list(records[0]));w.writeheader();w.writerows(records)
    (folder/'request-list.csv').write_bytes(f.getvalue().encode())
    m={'status':'prepared_not_authorized','request_count':1544,'max_new_credits':1544,
       'request_list_sha256':hashlib.sha256((folder/'request-list.csv').read_bytes()).hexdigest(),
       'request_set_sha256':hashlib.sha256(canonical(request_rows)).hexdigest(),'API_calls':0}
    policy={'stage':'listing-gaps','cap':1544,'allowed_missing':['known_snapshot_lag'],'max_missing':1544,
            'restart':'unchanged active authority; valid receipts and no pending/stopped state; untouched IDs only',
            'terminal':'stop for outcome-blind universe reconciliation; no next-stage authority',
            'billing':'full 1-credit reservation retained even when empty/lagged response bills zero',
            'scope':'NFL/CFB metadata only; May3 2023 through Feb9 2026; no 2026-season price analysis'}
    (folder/'manifest.json').write_bytes(canonical(m)+b'\n');(folder/'policy.json').write_bytes(canonical(policy)+b'\n')
    paths={'code/'+n:here/n for n in ('entry.py','engine.py','capture.py','prepare.py','history.py')}
    paths['code/f2_gate.py']=here.parent/'football_archive/f2_handoff.py'
    paths['code/plan.py']=props/'plan.py'
    paths.update({n:folder/n for n in ('manifest.json','request-list.csv','policy.json')})
    paths['source/FREEZE.json']=here.parent/'football_archive/acquisition/football-archive-v4/FREEZE.json'
    files={n:hashlib.sha256(p.read_bytes()).hexdigest() for n,p in sorted(paths.items())}
    root=hashlib.sha256(canonical(files)).hexdigest()
    (folder/'FREEZE.json').write_bytes(canonical({'root':root,'files':files})+b'\n')
    return root


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    print(json.dumps({'root':prepare(a.out),'new_cap':1544,'paid_calls':0}))
