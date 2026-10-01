"""Read provider event timestamp metadata only; never inspect the out-of-scope odds fields."""
import json,sys
from pathlib import Path
sys.dont_write_bytecode=True
import pyarrow.parquet as pq
root=Path(sys.argv[1]);b=Path(sys.argv[2]);s=json.loads((root/'spending-ledger.json').read_text());m=json.loads((b/'request-manifest.json').read_text());out=[]
for row in m['requests']:
 if row['priority']!=1:continue
 a=s['attempts'].get(row['request_id']);p=Path(a['response_path']) if a else b/row['cache_source']
 if a and a['status']=='missing':continue
 rec=pq.read_table(p,columns=['body']).to_pylist()[0];body=json.loads(rec['body'])
 for e in body['data']:
  stamp=e['commence_time'];year=int(stamp[:4]);season=year if int(stamp[5:7])>=7 else year-1
  if season not in (2023,2024,2025):out.append({'request_id':row['request_id'],'requested_utc':row['requested_utc'],'snapshot_utc':body['timestamp'],'provider_id':e['id'],'provider_kickoff':stamp,'inferred_season':season})
print(json.dumps(out,indent=2))
