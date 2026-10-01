"""Narrow offline v4 freeze; exact reviewed v3 request set and eligibility preserved."""
import argparse,csv,hashlib,json,shutil,sys
from pathlib import Path
from datetime import datetime,timedelta,timezone
HERE=Path(__file__).resolve().parent
LAB=HERE.parent
PARENT=LAB/'acquisition/football-archive-v3'
WORK=LAB/'acquisition/football-archive-v4.work'
OUT=LAB/'acquisition/football-archive-v4'
PARENT_ROOT='d5c441c2ddcd71a107476dd9731d1c2b11bcbbd08733870152d8075b5db65e9a'
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
    shutil.copyfile(PARENT/'FREEZE.json',WORK/'v3-origin-certificate.json');shutil.copyfile(PARENT/'request-manifest.json',WORK/'v3-origin-request-manifest.json')
    m=json.loads((WORK/'request-manifest.json').read_text());m['protocol_sha256']=protocol_hash;m['status']='v4 executor repair frozen for review; no new spending authorized';write(WORK/'request-manifest.json',m)
    if sha(WORK/'price_eligibility.py')!=cert['file_sha256']['price_eligibility.py']:raise RuntimeError('Eligibility changed')
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
    (WORK/'README.md').write_text(f"""# Football archive v4 — review before spending

This narrow repair changes billing/reconciliation and coverage-purpose reporting. The reviewed v3 request set and price eligibility are preserved byte-for-byte / exact-row-for-row and verified against v3 provenance.

Recent: {m['new_credits_by_priority']['1']:,} credits. Older: {m['new_credits_by_priority']['2']:,}, separately gated. Research purchases including probe: {m['new_credits_after_probe_reuse']+1687:,}. Shared/pre-run usage is additionally reserved conservatively against cumulative limits; it does not increase the allowed recent request list.

A separate approved, root-bound owner authorization, exact-list hub go-ahead and account reconciliation are required. Baseline may be captured from the first free check; no hard-coded September balance. Without an explicit documented prior-usage debit, the runner reserves ALL current-period used credits additionally (potentially double-counting the probe), then adds peak external usage. This avoids inventing zero other usage. Provider reset never resets local probe/attempt budgets.

Positive shared usage up to 100 credits and counter lag up to 100 are handled cumulatively. Catch-up is not charged twice. Larger deviations halt. In-run resets halt; an approved account-only reconciliation can establish a fresh baseline when no paid attempt is pending and the approval pins the stopped ledger hash. Pending calls require hash-pinned saved-response reconciliation offline; no automatic resend or ledger editing.

Vendored BulkClient uses probe-advised A30=5,000; the wrapper independently enforces the stricter 100-credit shared-usage/lag limits. Runtime manifests record the interpreter path and reconciliation hash/evidence.

Use sharp-markets/.venv/bin/python with -B. Offline preflight: `python -B executor.py --root PINNED_ROOT`. Portable tests: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -B -m pytest -q -p no:cacheprovider test_v4.py`. No approval artifact is inside this immutable bundle.

Cache handoff uses the sharp-markets RawCache format and keys. The stock price-engine CLI replans legacy F1; before grading, the hub must approve an adapter that consumes this exact manifest and both paid/reused response paths. Never buy legacy F1 again to fill a second cache.

No forward-test jobs are paused and no 2026 signal logs are inspected. Use a quiet acquisition window when available; bounded job overlap is accounted for and excess overlap halts. Stop after 2023–25 and publish the outcome-blind coverage report before any older purchase or outcome joins.
""")
    (WORK/'BILLING-REPAIR.md').write_text("# V4 billing repair\n\nThe v3 review found that equality against the old probe balance and per-call counter deltas made routine shared-key usage, resets and stale headers fail. V4 changes only this execution concern and makes coverage show both purposes for shared alternate-close slots.\n\nAn approved reconciliation file records mode, reason, owner note, and optional explicit used/remaining. Capture mode adopts the first free check and records its actual numeric baseline in the durable ledger and manifest. The file hash, baseline, runtime versions and interpreter path are recorded. A draft file authorizes nothing.\n\nDuring an epoch, compare highest used and lowest remaining with cumulative own bills. Reserve peak positive external discrepancy once; cap it at 100. Bounded reporting lag up to 100 is tolerated and recorded; never infer spending capacity from a stale high balance. Per-call unreadable/over-upper-bound billing still halts. Initial reconciliation cannot lower research attempt/probe debit.\n\nStopped account-only runs can resume through a new approved reconciliation when no paid request is pending and the approval pins the stopped ledger hash. Pending requests stay reserved and cannot be resent. `--reconcile-only` accepts only an existing exact hash-pinned valid cached response, writes receipts/history and preserves the reservation; a separate approved account-only baseline is then required before any send. A missing response or unresolved overcharge remains blocked for investigation.\n\nA30 from the complete probe is 5,000 under the repo's formula; wrapper limits remain stricter at 100. There is no guarantee about provider billing or unrelated key activity. The runner never changes launchd jobs or reads sealed strategy signals.\n")
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
