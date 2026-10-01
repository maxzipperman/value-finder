"""Narrow offline v4 freeze; exact reviewed request set; hub-requested execution and exclusion-only eligibility repairs."""
import argparse,csv,hashlib,json,shutil,sys
from pathlib import Path
from datetime import datetime,timedelta,timezone
HERE=Path(__file__).resolve().parent
LAB=HERE.parent
PARENT=LAB/'acquisition/football-archive-v3'
WORK=LAB/'acquisition/football-archive-v4.work'
OUT=LAB/'acquisition/football-archive-v4'
PARENT_ROOT='54a610657255041d7db441f43c24dacf3f2d64d49840722bc1fdf129184060e2'
def canonical(v): return json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p,v):
    p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(canonical(v)+b'\n')
def ts(v): return datetime.fromisoformat(v.replace('Z','+00:00'))
def iso(v): return v.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
def close_time(k):
    v=ts(k)-timedelta(minutes=5);return iso(v.replace(second=0,microsecond=0)-timedelta(minutes=v.minute%5))
def request(sport,season,at,books):
    params={'bookmakers':','.join(books),'markets':'h2h,spreads,totals','oddsFormat':'decimal','dateFormat':'iso','date':at}
    path=f'/historical/sports/{sport}/odds';ident={'source':'oddsapi/hist_odds','url':'https://api.the-odds-api.com/v4'+path,'params':params}
    return {'request_id':hashlib.sha256(canonical(ident)).hexdigest(),'cache_key':hashlib.sha1(json.dumps(ident,sort_keys=True,default=str).encode()).hexdigest()[:20],
            'sport':sport,'source':ident['source'],'path':path,'params':params,'requested_utc':at,'seasons':[season],
            'purposes':[],'canonical_game_ids':[],'max_credits':30,'max_new_credits':30,'priority':1 if season>=2023 else 2,
            'retry_allowance':0,'sealed':False,'cache_source':None,'cache_sha256':None}



def guard(event,args):
    if event in ('socket.connect','socket.getaddrinfo','subprocess.Popen','os.system'):raise RuntimeError('Builder offline')
    if event=='open' and isinstance(args[0],(str,bytes)) and (Path(str(args[0])).name=='.env' or '/data/forward/' in str(args[0])):raise RuntimeError('No credentials or forward data')

def build():
    if OUT.exists():raise SystemExit('Refuse to overwrite frozen v4')
    protocol_bytes=(HERE/'protocol.json').read_bytes();protocol_hash=hashlib.sha256(protocol_bytes).hexdigest()
    cert=json.loads((PARENT/'FREEZE.json').read_text());files={str(p.relative_to(PARENT)):sha(p) for p in sorted(PARENT.rglob('*')) if p.is_file() and p.name!='FREEZE.json'}
    if files!=cert['file_sha256'] or hashlib.sha256(canonical(files)).hexdigest()!=PARENT_ROOT:raise RuntimeError('Reviewed v3 changed')
    if WORK.exists():shutil.rmtree(WORK)
    shutil.copytree(PARENT,WORK)
    for name in ('FREEZE.json','test_v3.py','rehearsal-report.json'): (WORK/name).unlink()
    (WORK/'protocol.json').write_bytes(protocol_bytes)
    for source in HERE.glob('*.py'):shutil.copyfile(source,WORK/source.name)
    shutil.copyfile(PARENT/'original-reviewed-certificate.json',WORK/'v3-origin-certificate.json');shutil.copyfile(PARENT/'request-manifest.json',WORK/'v3-origin-request-manifest.json')
    m=json.loads((WORK/'request-manifest.json').read_text());m['protocol_sha256']=protocol_hash;m['request_list_sha256']=sha(WORK/'request-list.csv');m['status']='v4 executor repair frozen for review; no new spending authorized';write(WORK/'request-manifest.json',m)
    write(WORK/'eligibility-amendment.json',{'original_eligibility_sha256':cert['file_sha256']['price_eligibility.py'],'new_eligibility_sha256':sha(WORK/'price_eligibility.py'),'reason':'Hub review: scheduled/provider timing remains mandatory; independent final first play can only exclude, never admit.'})
    # Reproduce the repo recommendation using its public manifest-only formula, without importing dotenv settings.
    manifest=list(csv.DictReader((WORK/'probe-response-provenance.csv').open()))
    readings=[r for r in manifest if r.get('pull')!='account' and r.get('remaining') and r.get('credits_last')]
    prior=5000000;count=0;lag=0;stretch=0;longest=0
    for r in readings:
        cost=int(float(r['credits_last']));left=int(float(r['remaining']));count+=cost
        stretch=stretch+1 if cost and left>=prior else 0;longest=max(longest,stretch)
        lag=max(lag,max(0,5000000-left-count));prior=left
    write(WORK/'probe-billing-margin.json',{'probe_responses':len(readings),'measured_max_unexplained_credits':lag,'longest_nonfall_answer_stretch':longest,
         'per_call_credits':30,'repo_A30_formula':'max(5000, 2 * lateness_answers * 30)','advised_A30':max(5000,2*longest*30),
         'wrapper_shared_usage_margin':100,'wrapper_counter_lag_tolerance':100,'client_margin':5000,
         'note':'Client retains the repo advised floor; wrapper is stricter and governs shared usage and bounded lag. A baseline is explicitly adopted rather than assumed from probe.'})
    for name in ('README.md','BILLING-REPAIR.md','ELIGIBILITY.md'):
        shutil.copyfile(HERE/name,WORK/name)
    print(json.dumps({'status':'v4 prepared offline','recent_credits':82830,'requests_preserved':len(m['requests'])},indent=2))

def seal():
    if OUT.exists():raise SystemExit('Refuse to overwrite frozen v4')
    for source in HERE.glob('*.py'):
        if sha(source)!=sha(WORK/source.name):raise RuntimeError('Source changed; rebuild')
    if sha(HERE/'protocol.json')!=sha(WORK/'protocol.json'):raise RuntimeError('Protocol changed')
    report=json.loads((WORK/'rehearsal-report.json').read_text())
    if report['status']!='passed' or not report['network_disabled']:raise RuntimeError('Offline tests required')
    files={str(p.relative_to(WORK)):sha(p) for p in sorted(WORK.rglob('*')) if p.is_file() and p.name!='FREEZE.json'}
    root=hashlib.sha256(canonical(files)).hexdigest();write(WORK/'FREEZE.json',{'algorithm':'sha256','bundle_root_sha256':root,'protocol_sha256':sha(WORK/'protocol.json'),'file_sha256':files,'API_calls_made_by_builder':0,'frozen_utc':datetime.now(timezone.utc).isoformat()})
    from validator import verify
    result=verify(WORK,root,check_cache=True);WORK.rename(OUT);print(json.dumps(result,indent=2))

if __name__=='__main__':
    sys.dont_write_bytecode=True;sys.addaudithook(guard);p=argparse.ArgumentParser();p.add_argument('--seal',action='store_true');a=p.parse_args();seal() if a.seal else build()
