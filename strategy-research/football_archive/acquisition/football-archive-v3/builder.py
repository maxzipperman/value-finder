"""Network-free v3 repair derived from independently pinned v2 metadata; never reads results."""
import argparse
from collections import Counter, defaultdict
import csv
from datetime import datetime, timedelta, timezone
import hashlib
import importlib.metadata
import json
from pathlib import Path
import shutil
import sys

HERE=Path(__file__).resolve().parent
LAB=HERE.parent
PARENT=LAB/'acquisition/football-archive-v2'
WORK=LAB/'acquisition/football-archive-v3.work'
OUT=LAB/'acquisition/football-archive-v3'
PARENT_ROOT='954cd9cb6e763603a609f109043a77fedbb020e7f2fc3e4c626038fa5dd17c69'
VENDOR=Path('/Users/maxzipperman/code/value-finder/sharp-markets/src/markets')
PROBE=LAB/'acquisition/football-probe-v1'


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


def offline_guard(event,args):
    if event in ('socket.connect','socket.getaddrinfo','subprocess.Popen','os.system'): raise RuntimeError('Builder is offline')
    if event=='open' and isinstance(args[0],(str,bytes)):
        value=str(args[0])
        if Path(value).name=='.env' or '/data/forward/' in value: raise RuntimeError('No credentials or forward data')


def build():
    if OUT.exists(): raise SystemExit('v3 is already frozen; do not overwrite')
    # This read happens before the parent bundle or any matching inputs.
    protocol_bytes=(HERE/'protocol.json').read_bytes();protocol_hash=hashlib.sha256(protocol_bytes).hexdigest();cfg=json.loads(protocol_bytes)
    parent_certificate=json.loads((PARENT/'FREEZE.json').read_text())
    actual={str(p.relative_to(PARENT)):sha(p) for p in sorted(PARENT.rglob('*')) if p.is_file() and p.name!='FREEZE.json'}
    if actual!=parent_certificate['file_sha256'] or hashlib.sha256(canonical(actual)).hexdigest()!=PARENT_ROOT:
        raise RuntimeError('Pinned v2 changed')
    if WORK.exists(): shutil.rmtree(WORK)
    WORK.mkdir();(WORK/'protocol.json').write_bytes(protocol_bytes)
    keep=('canonical-games.json','provider-observations.json','aliases.json','exclusions.json','unmatched-provider-ids.json',
          'legacy-close-reconciliation.json','original-85-close-resolution.json','coverage-and-exclusions-summary.json','input-provenance.json')
    for name in keep: shutil.copyfile(PARENT/name,WORK/name)
    shutil.copytree(PARENT/'inputs',WORK/'inputs')
    shutil.copyfile(PARENT/'FREEZE.json',WORK/'v2-origin-certificate.json')
    games=json.loads((WORK/'canonical-games.json').read_text());observations=json.loads((WORK/'provider-observations.json').read_text())
    probe_headers=list(csv.DictReader((PROBE/'data/raw/_manifest/oddsapi_manifest.csv').open()))
    source_hashes={r['cache_key']:r['sha256'] for r in probe_headers if r.get('cache_key')}
    for obs in observations:obs['source_body_sha256']=source_hashes[obs['source_cache_key']]
    write(WORK/'provider-observations.json',observations)
    shutil.copyfile(PROBE/'data/raw/_manifest/oddsapi_manifest.csv',WORK/'probe-response-provenance.csv')
    manifest=json.loads((PARENT/'request-manifest.json').read_text());rows={r['cache_key']:r for r in manifest['requests']}
    mappings=[];alternate_slots={};new_slots={};affected=[]
    for game in games:
        candidates=[('provider_anchor',close_time(game['close_anchor_utc']))]
        if abs(game['schedule_discrepancy_minutes'])>5:
            affected.append(game)
            candidates.append(('independent_schedule',close_time(game['scheduled_utc'])))
        for basis,at in candidates:
            r=request(game['sport'],game['season'],at,cfg['book_panel']);key=r['cache_key'];existed=key in rows
            if basis=='independent_schedule': alternate_slots[key]=r
            if not existed: rows[key]=r;new_slots[key]=r
            row=rows[key]
            row['purposes']=sorted(set(row['purposes']+['pregame_close_proxy' if basis=='provider_anchor' else 'alternate_independent_close_proxy']))
            row['canonical_game_ids']=sorted(set(row['canonical_game_ids']+[game['canonical_game_id']]))
            mappings.append({'canonical_game_id':game['canonical_game_id'],'basis':basis,'request_id':row['request_id'],
                             'cache_key':key,'requested_utc':at,'diagnostic_until_quote_timing_validated':True})
    for r in rows.values():
        if r['max_new_credits']==0:
            dest=WORK/'reuse'/f"{r['cache_key']}.parquet";dest.parent.mkdir(exist_ok=True)
            src=Path(r['cache_source'])
            if sha(src)!=r['cache_sha256']: raise RuntimeError('Reused probe bytes changed')
            shutil.copyfile(src,dest);r['cache_source']=str(dest.relative_to(WORK))
    requests=sorted(rows.values(),key=lambda r:(r['priority'],r['requested_utc'],r['sport']))
    manifest.update(status='frozen plan prepared for owner review; no new paid execution authorized',protocol_sha256=protocol_hash,
        request_count=len(requests),gross_credits=30*len(requests),new_credits_after_probe_reuse=sum(r['max_new_credits'] for r in requests),
        new_credits_by_priority={str(k):sum(r['max_new_credits'] for r in requests if r['priority']==k) for k in (1,2)},requests=requests)
    # Any old request-set digest is replaced, not inherited as stale authentication.
    manifest['request_set_sha256']=hashlib.sha256(canonical(requests)).hexdigest()
    write(WORK/'request-manifest.json',manifest);write(WORK/'close-candidates.json',mappings)
    with (WORK/'request-list.csv').open('w',newline='') as f:
        fields=['priority','sport','seasons','requested_utc','purposes','max_new_credits','cache_key'];w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
        for r in requests:w.writerow({k:json.dumps(r[k]) if isinstance(r[k],list) else r[k] for k in fields})
    primary_ids={g['canonical_game_id'] for g in games}
    groups=defaultdict(list)
    for o in observations:groups[(o['sport'],o['provider_id'])].append(o)
    pair_games=defaultdict(list)
    for g in games:pair_games[(g['sport'],g['season'],tuple(sorted(g['team_keys'])))].append(g['canonical_game_id'])
    unmatched={r['provider_id']:r for r in json.loads((WORK/'unmatched-provider-ids.json').read_text())}
    registry=[];unmatched_review=[]
    request_times={(r['sport'],r['requested_utc']):r for r in requests}
    for (sport,pid),obs in sorted(groups.items()):
        canonical_ids=sorted({o['canonical_game_id'] for o in obs if o.get('canonical_game_id')})
        pair_candidates=sorted({gid for o in obs for gid in pair_games.get((sport,o['season'],tuple(sorted(k for k in o['team_keys'] if k))),[])})
        history=sorted(obs,key=lambda o:(o['returned_utc'],o['provider_kickoff_utc']))
        registry.append({'sport':sport,'provider_id':pid,'seasons':sorted({o['season'] for o in obs}),
          'canonical_game_ids':canonical_ids,'candidate_canonical_game_ids_via_other_provider_id':pair_candidates,
          'canonical_game_id_via_other_provider_id':None if not canonical_ids else canonical_ids[0],
          'other_id_link_status':'unresolved_candidate_not_a_binding' if pair_candidates and not canonical_ids else 'not_needed_or_absent',
          'status':('matched' if any(gid in primary_ids for gid in canonical_ids) else 'matched_no_valid_pregame_listing') if canonical_ids else 'unmatched_observed_opportunity','first_observed_utc':history[0]['returned_utc'],
          'last_observed_utc':history[-1]['returned_utc'],'observation_count':len(obs),'exclusion_context':unmatched.get(pid),
          'provider_kickoff_versions':sorted({o['provider_kickoff_utc'] for o in obs}),
          'interpretation':'Observed listings only; not complete market opportunity history. No cancellation or settlement inferred.'})
        if not canonical_ids and any(o['season']>=2023 for o in obs):
            slots=sorted({close_time(o['provider_kickoff_utc']) for o in obs if o['season']>=2023})
            covered=[at for at in slots if (sport,at) in request_times];absent=[at for at in slots if (sport,at) not in request_times]
            observation_windows=set()
            for o in obs:
                if o['season']<2023:continue
                kick=ts(o['provider_kickoff_utc'])
                observation_windows.update(r['cache_key'] for r in requests if r['sport']==sport and
                    kick-timedelta(days=7)<=ts(r['requested_utc'])<kick)
            unmatched_review.append({'sport':sport,'provider_id':pid,'candidate_other_id_games':pair_candidates,
                'candidate_close_slots_already_requested':covered,'candidate_close_slots_not_requested':absent,
                'existing_decision_window_request_keys':sorted(observation_windows),
                'action':'retain_unresolved_opportunity; no additional purchase; not a complete operational replay',
                'settlement_status':'unresolved; no result or bookmaker-rule read'})
    write(WORK/'opportunity-registry.json',registry);write(WORK/'recent-unmatched-request-review.json',unmatched_review)
    # Keep v2 resolution reasons, but do not carry its no-extra-purchase flag into v3 as a current claim.
    for name in ('legacy-close-reconciliation.json','original-85-close-resolution.json'):
        reconciled=json.loads((WORK/name).read_text())
        for group in reconciled:
            group['v2_extra_purchase']=group.pop('extra_purchase',False)
            r=request_times.get((group['sport'],group['legacy_request_utc']))
            group['v3_legacy_slot_in_request_union']=r is not None
            group['v3_request_id_at_legacy_slot']=r['request_id'] if r else None
            group['v3_request_purposes_at_legacy_slot']=r['purposes'] if r else []
            group['v3_new_alternate_call_at_legacy_slot']=bool(r and r['cache_key'] in new_slots)
            group['v3_interpretation']='Alternate candidates arise from the frozen timing-conflict repair, not blind purchase of unmatched legacy slots. Original group reasons and metadata denominators are retained.'
        write(WORK/name,reconciled)

    write(WORK/'alternate-close-summary.json',{'affected_games':len(affected),'distinct_alternate_slots':len(alternate_slots),
       'already_requested_distinct_alternate_slots':len(alternate_slots)-len(new_slots),
       'affected_games_with_existing_alternate_slot':sum(request(g['sport'],g['season'],close_time(g['scheduled_utc']),cfg['book_panel'])['cache_key'] not in new_slots for g in affected),
       'new_slots':len(new_slots),'new_slots_by_priority':dict(Counter(str(r['priority']) for r in new_slots.values())),
       'additional_credits':sum(r['max_new_credits'] for r in new_slots.values())})
    shutil.copyfile(PROBE/'spending-ledger.json',WORK/'probe-spending-ledger.json')
    vendor_files=['__init__.py','cache.py','http.py','settings.py','sport.py','oddsapi/__init__.py','oddsapi/normalize.py','oddsapi/bulk.py']
    vendored={}
    for rel in vendor_files:
        dest=WORK/'archive_markets'/rel;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(VENDOR/rel,dest)
        vendored[rel]={'original_sha256':sha(VENDOR/rel),'frozen_sha256':sha(dest),'changes':'none; wrapper adds transport/durability guards'}
    write(WORK/'vendor-provenance.json',vendored)
    for source in HERE.glob('*.py'):shutil.copyfile(source,WORK/source.name)
    from executor import current_runtime
    write(WORK/'runtime-lock.json',current_runtime())
    shutil.copyfile(LAB/'odds-archive-v3-fix-plan.md',WORK/'REPAIR-PLAN.md')
    write(WORK/'v3-registration-provenance.json',{'protocol_read_before_parent_inputs':True,'protocol_sha256':protocol_hash,
        'parent_root_sha256':PARENT_ROOT,'builder_api_calls':0,'builder_credentials_read':False,'builder_outcomes_read':False,
        'v2_preserved':True,'chronology_note':'Local protocol-first execution record; hash alone does not independently prove chronology.'})
    (WORK/'README.md').write_text(f'''# Football archive v3 — prepared for review

Manifest: {len(requests):,} calls, including 24 reused probe calls and {sum(r['max_new_credits']>0 for r in requests):,} new paid calls.
Recent ceiling: {manifest['new_credits_by_priority']['1']:,}; older ceiling: {manifest['new_credits_by_priority']['2']:,}; including probe: {manifest['new_credits_after_probe_reuse']+1687:,} credits.
No new spending is authorized by this freeze. The executor accepts priority 1 only and requires a separate owner approval artifact pinned to the full root and exact recent ceiling.

The 54 timing-discrepant games produce 50 distinct alternate slots, 22 already requested (covering 25 games), and 28 new calls at 840 credits.
Alternate close selection is based only on timing and freshness, never favorable prices. Missing actual-play evidence leaves a scheduled proxy uncertified; unresolved material conflicts remain diagnostic.

The provider-observed registry includes unmatched IDs. The external NFL index is played-game metadata. Neither universe alone establishes a complete historical betting opportunity denominator. The recent unmatched inventory adds no blind extra purchases.

Portable offline checks: run Python with -B, run `python -B validator.py . PINNED_ROOT`, then `python -B -m pytest -q -p no:cacheprovider test_v3.py` with PYTEST_DISABLE_PLUGIN_AUTOLOAD=1. Tests use temporary copies and fake transports; no API/key/outcome/holdout access.
Offline executor preflight: `python -B executor.py --root PINNED_ROOT`. Live execution is deferred until owner review; no approval file is included.

The runtime lock pins Python and HTTP/parquet distributions. All imported market-client source is vendored and hashed. Raw runtime responses, receipts and ledgers live outside this immutable bundle.
A provider monthly reset or other key activity halts for reconciliation; it cannot reset local budget or enable another send.
The executor stops before older seasons. Coverage report publication is not approval to purchase older seasons.
''')
    (WORK/'ELIGIBILITY.md').write_text('''# Eligibility and close selection

Three statuses are distinct: scheduled-pregame eligible, actual-play certified, and conflicted/ineligible. Missing independent first-play evidence prevents certification, but does not alone reject an otherwise eligible scheduled close proxy. Known first play overrides scheduled timing for decisions and executions.

Every quote binds its immutable response hash, exact provider ID, canonical game, market and canonical side to its schedule observation. Independent final schedule is a retrospective safety guard unless its publication vintage is verified. Conflicting simultaneous observations for the exact quoted listing are quarantined; ID sorting cannot resolve them.

Close selection partitions by canonical game, book, market and side. Among eligible candidates, choose the latest returned snapshot, then freshest update timestamp, then smallest immutable quote ID. Prices, lines, CLV and results never enter ranking. If none qualifies, retain missing primary close and all diagnostics. When first play is verified, the close lead window is 5–20 minutes relative to it; otherwise use the provider kickoff with the independent safety guard.

Sides join by canonical team key (moneyline/spreads) or Over/Under (totals), never provider home/away position. Freshness remains 15 minutes at snapshot and 25 at decision; snapshot lag up to 10 minutes with gaps over five reported explicitly.

Paper listing voids, including postponement over 24 hours, remain attempted decisions. They do not erase historical opportunities or prove a sportsbook settlement. Multiple listings, cancellation and settlement mapping must be registered for the specific later study.

All 665 original MOS slots remain three-market fixed-time diagnostics. This is not a full live trigger or execution-delay replay. The 2026 season stays sealed; no outcome joins before recent coverage. Historical grades and significance rules are unchanged.

Execution acceptance: no send outside the authorized allowlist or without a durable reservation; no automatic resend of unresolved attempts; conservative accounting and halt when billing cannot be reconciled. Provider billing and unrelated shared-key activity are not guaranteed by the wrapper.
''')
    print(json.dumps({'status':'v3 prepared offline, not sealed','manifest_requests':len(requests),
                     'recent_credits':manifest['new_credits_by_priority']['1'],'older_credits':manifest['new_credits_by_priority']['2']},indent=2))


def seal():
    if OUT.exists():raise SystemExit('Refuse to replace frozen v3')
    for source in HERE.glob('*.py'):
        if sha(source)!=sha(WORK/source.name):raise RuntimeError('Source changed; rebuild before sealing')
    if sha(HERE/'protocol.json')!=sha(WORK/'protocol.json'):raise RuntimeError('Protocol changed')
    report=json.loads((WORK/'rehearsal-report.json').read_text())
    if report['status']!='passed' or report['network_disabled'] is not True:raise RuntimeError('Offline rehearsal required')
    files={str(p.relative_to(WORK)):sha(p) for p in sorted(WORK.rglob('*')) if p.is_file() and p.name!='FREEZE.json'}
    root=hashlib.sha256(canonical(files)).hexdigest();write(WORK/'FREEZE.json',{'algorithm':'sha256','bundle_root_sha256':root,
          'protocol_sha256':sha(WORK/'protocol.json'),'file_sha256':files,'frozen_utc':datetime.now(timezone.utc).isoformat(),
          'API_calls_made_by_builder':0})
    from validator import verify
    result=verify(WORK,root,check_cache=True);WORK.rename(OUT);print(json.dumps(result,indent=2))


if __name__=='__main__':
    sys.dont_write_bytecode=True;sys.addaudithook(offline_guard)
    parser=argparse.ArgumentParser();parser.add_argument('--seal',action='store_true');args=parser.parse_args()
    seal() if args.seal else build()
