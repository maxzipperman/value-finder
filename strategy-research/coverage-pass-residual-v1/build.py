"""Outcome-blind passing-group residual preparation. No sends/keys/runtime writes.

Saved final artifact is externally pinned. Current history is matched byte-for-byte
to its authenticated inventory; only request metadata columns are projected.
"""
import argparse
from collections import Counter,defaultdict
import fcntl
import hashlib
import json
import os
from pathlib import Path
import stat
import types

FINAL_SHA='100a53275119fba283b3e8938cfee994f0d1a535201f2bab2e8769bfba9fdbdb'
PASS={
 'older/americanfootball_ncaaf/2020','older/americanfootball_nfl/2020',
 'older/americanfootball_nfl/2021','older/americanfootball_nfl/2022',
 'props/americanfootball_nfl/2023','props/americanfootball_nfl/2024'}
CARRY=207386;CEILING=250000;RESERVE=531630;SHARED_ALLOWANCE=100
PRIORITY=['props/americanfootball_nfl/2023','props/americanfootball_nfl/2024','older/americanfootball_nfl/2020','older/americanfootball_nfl/2021','older/americanfootball_nfl/2022','older/americanfootball_ncaaf/2020']


def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False,default=str).encode()
def sha(raw):return hashlib.sha256(raw).hexdigest()
def identity(value):return sha(canonical(value))


def regular(path):
 path=Path(path).absolute()
 if any(p.is_symlink() for p in (path,*path.parents)):raise ValueError('symlink input/output forbidden')
 fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
 try:
  if not stat.S_ISREG(os.fstat(fd).st_mode):raise ValueError('regular input required')
  with os.fdopen(fd,'rb',closefd=False) as h:return h.read()
 finally:os.close(fd)


def module(raw,path,name,expected):
 if sha(raw)!=expected:raise ValueError('source changed before execution')
 m=types.ModuleType(name);m.__file__=str(path);exec(compile(raw,str(path),'exec'),m.__dict__);return m


def verify_snapshot(root_base,expected,capture):
 ledgers={p.parent.name:capture.sha(p) for p in root_base.glob('*/spending-ledger.json')}
 markers={p.stem:capture.sha(p) for p in (root_base/'registrations').glob('*.json')}
 initialized={p.parent.name for p in root_base.glob('*/INITIALIZED.json')}
 if {'ledgers':ledgers,'registrations':markers}!=expected or initialized!=set(ledgers):raise ValueError('saved final authenticated history changed/unknown root')
 for root in ledgers:
  state=capture.read(root_base/root/'spending-ledger.json');mark=capture.read(root_base/'registrations'/(root+'.json'))
  if state.get('pending') or state.get('stopped') or any(a['status'] not in ('completed','missing') for a in state['attempts'].values()):raise ValueError('unresolved prior attempt')
  if capture.read(root_base/root/'INITIALIZED.json')!={'bundle_root_sha256':root,'probe_credits':1687} or mark.get('authorization_sha256')!=state['authorization_sha256'] or mark.get('runtime_path')!=str((root_base/root).absolute()):raise ValueError('historical initialization/registration differs')
 return expected


def target_selection(frame,final):
 saved=final['record']['saved_bounds']['strata']
 passing={r['stratum'] for r in saved if r['status']=='utility_pass'}
 if passing!=PASS:raise ValueError('saved gate differs; no threshold re-evaluation')
 if sum(r['population'] for r in saved)!=6790 or len(saved)!=12:raise ValueError('saved full-frame denominator differs')
 targets=[g['game_id'] for g in frame if g['stratum'] in passing and g['classification']=='unknown']
 if len(targets)!=len(set(targets)):raise ValueError('duplicate passing-frame identity')
 return dict(selected=sorted(targets)),[dict(game_id=g['game_id'],stratum=g['stratum'],original_classification=g['classification'],purchase_candidate=g['game_id'] in set(targets)) for g in frame if g['stratum'] in passing]


def saved_exclusions(frame,final):
 games={g['game_id']:g for g in frame};groups={r['stratum']:r for r in final['record']['saved_bounds']['strata'] if r['status']=='hold'};reason_counts=defaultdict(Counter);failed=Counter()
 for gid,d in final['details'].items():
  key=games[gid]['stratum']
  if key not in groups or final['record']['classifications'][gid]:continue
  failed[key]+=1;labels=set()
  for role,reasons in d.get('slot_reasons',{}).items():
   labels.update(role+':'+reason for reason in reasons)
  for forced in d.get('forced_dispositions',[]):
   labels.add('forced:'+forced.get('reason','metadata_ineligible'))
   labels.update('metadata:'+r for r in forced.get('reasons',[]))
  if d.get('reference_both') is False:labels.add('missing_Pinnacle_pair_at_one_or_both_slots')
  if 'paired_books' in d and not d['paired_books']:labels.add('no_same_domestic_book_pair_both_slots')
  if 'paired_families' in d and len(d['paired_families'])<2:labels.add('fewer_than_two_paired_core_families')
  if not labels:labels.add('saved_primary_failure_no_finer_reason')
  reason_counts[key].update(labels)
 return [dict(stratum=key,saved_observed=groups[key]['observed'],saved_sample=groups[key]['sample'],saved_status='hold',failed_games=failed[key],nonexclusive_game_reason_counts=dict(sorted(reason_counts[key].items())),source='saved_final_details_only_no_reclassification') for key in sorted(groups)]


def cell_rectangles(rows):
 result=[];seen=set()
 for row in rows:
  params=row['params'];books=params['bookmakers'].split(',');markets=params['markets'].split(',')
  for book in books:
   for market in markets:
    key=(row['sport'],row['source'],row['url'],row['requested_utc'],book,market)
    if key in seen:raise ValueError('duplicate purchase cell')
    seen.add(key)
  result.append(dict(request_id=row['request_id'],sport=row['sport'],source=row['source'],url=row['url'],requested_utc=row['requested_utc'],books=sorted(books),markets=sorted(markets),cell_count=len(books)*len(markets)))
 return result


def cache_inventory(roots,capture):
 import pyarrow as pa
 import pyarrow.parquet as pq
 inventory={};metadata=[]
 for root in roots:
  for sport in ('americanfootball_nfl','americanfootball_ncaaf'):
   for src in ('oddsapi/hist_odds','oddsapi/hist_event_odds','oddsapi/hist_event_markets'):
    for path in (Path(root)/sport/src).glob('*/*.parquet'):
     if not '2020-01-01'<=path.parent.name<'2026-02-10':continue
     raw=capture.regular(path);inventory[str(path)]=sha(raw)
     records=pq.read_table(pa.BufferReader(raw),columns=['sport','source','url','params_json','cache_key']).to_pylist()
     if len(records)!=1:raise ValueError('ambiguous cache metadata')
     r=records[0];r['params']=json.loads(r.pop('params_json'));metadata.append(dict(r,cache_path=str(path),cache_sha256=sha(raw)))
 return inventory,metadata


def assess_budget(cap):
 if type(cap) is not int or cap<0:raise ValueError('invalid cap')
 return dict(prior_conservative_debit=CARRY,prior_first_tranche_ceiling=CEILING,available_under_prior_ceiling=CEILING-CARRY,new_cap=cap,proposed_cumulative_purchase_debit=CARRY+cap,shared_usage_allowance=SHARED_ALLOWANCE,proposed_first_tranche_ceiling=CARRY+cap+SHARED_ALLOWANCE,day_one_cumulative_ceiling=400000,monthly_cumulative_ceiling=4440000,account_reserve_floor=RESERVE,extension_required=CARRY+cap+SHARED_ALLOWANCE>CEILING,paid_authority=False)


def prepare(args):
 own_raw=regular(Path(__file__))
 final_raw=regular(args.final_record)
 if sha(final_raw)!=FINAL_SHA or args.final_sha256!=FINAL_SHA:raise ValueError('external immutable final record differs')
 final=json.loads(final_raw);repo=Path(args.repo).absolute()
 rp=repo/'strategy-research/coverage-pilot-completion-v1/report.py';rr=regular(rp)
 report=module(rr,rp,'passing_saved_report',final['fingerprint']['adapter_sha256'])
 bp=repo/'strategy-research/coverage-pilot-packet-v1/build.py';br=regular(bp)
 build=module(br,bp,'passing_packet_builder',args.packet_builder_sha256)
 repo,out=build.validate_output(repo,args.output)
 data,source,load=report.captured_closure(repo,args.packet,final['fingerprint']['root']);capture=load('capture');base=load('executor')
 if identity({n:sha(v) for n,v in data.items()})!=final['fingerprint']['packet_files_sha256']:raise ValueError('saved packet closure differs')
 if base.current_runtime()!=json.loads(source['runtime-lock.json']):raise ValueError('frozen environment differs')
 frame=json.loads(data['frame.json']);protocol=json.loads(data['protocol.json']);selection,denominator=target_selection(frame,final)
 with (base.RUNTIME_BASE/'followup-purchase.lock').open('rb') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  snapshot=verify_snapshot(base.RUNTIME_BASE,final['proof']['global_snapshot'],capture)
  history=build.authenticated_history(base.RUNTIME_BASE,snapshot,capture)
  context={'freeze':data['source/FREEZE.json'],'files':source};history.extend(build.frozen_probe_history(context,load))
  rows,maps=build.selected_union(frame,selection,json.loads(data['slot-map.json']),json.loads(source['request-manifest.json'])['requests'],history,load,protocol['candidate_books'])
  load('evidence').authenticate_reuse(base.RUNTIME_BASE,snapshot,maps,frozen_source=context)
  # Audit every raw root, including unledgered/pre-probe caches. No quote columns.
  oldcache=json.loads(data['overlap.json']);roots=sorted(set(oldcache['raw_roots'])|{str((base.RUNTIME_BASE/r/'data/raw').absolute()) for r in snapshot['ledgers']})
  inv,metadata=cache_inventory(roots,capture)
  # Residual constructors already subtract authenticated terminal cells. Any
  # remaining cache intersection is unresolved evidence, not permission to rebuy.
  load('overlap').check(rows,roots,expected_inventory_sha256=identity(inv))
  attempted={h['request_id'] for h in history}
  if attempted & {r['request_id'] for r in rows}:raise ValueError('attempted ID in residual')
  row_groups=defaultdict(set);game_groups={g['game_id']:g['stratum'] for g in frame}
  for m in maps:
   for rid in m['request_ids']:row_groups[rid].add(game_groups[m['game_id']])
  if any(len(groups)!=1 for groups in row_groups.values()):raise ValueError('cross-stratum shared request requires explicit cost allocation')
  rows.sort(key=lambda r:(PRIORITY.index(next(iter(row_groups[r['request_id']]))),r['requested_utc'],r['request_id']))
  rectangles=cell_rectangles(rows);cap=sum(r['max_new_credits'] for r in rows)
  by_game={g['game_id']:g for g in frame};per_group=[]
  for group in sorted(PASS):
   mapped=[m for m in maps if by_game[m['game_id']]['stratum']==group];ids={rid for m in mapped for rid in m['request_ids']};rs=[r for r in rows if r['request_id'] in ids]
   per_group.append(dict(stratum=group,full_frame=sum(g['stratum']==group for g in frame),initially_unknown=sum(g['stratum']==group and g['classification']=='unknown' for g in frame),new_requests=len(rs),new_cap=sum(r['max_new_credits'] for r in rs),residual_game_references=sum(bool(m['request_ids']) for m in mapped),no_new_request_game_references=sum(not m['request_ids'] for m in mapped)))
  manifest=dict(version=1,stage='passing_groups_existing_frame_residual_preparation',final_artifact_sha256=FINAL_SHA,source_packet_root=final['fingerprint']['root'],frame_sha256=sha(data['frame.json']),original_protocol_sha256=identity(protocol),passing_groups=sorted(PASS),request_count=len(rows),max_new_credits=cap,request_list_sha256=sha(canonical(rows)),cell_rectangles_sha256=identity(rectangles),denominator_sha256=identity(denominator),mappings_sha256=identity(maps),global_snapshot=snapshot,budget=assess_budget(cap),per_group=per_group,no_new_draw=True,no_new_statistical_look=True,paid_authority=False,execution_adapter_ready=False)
  proof=dict(raw_roots=roots,raw_inventory_sha256=identity(inv),metadata_columns=['sport','source','url','params_json','cache_key'],request_metadata_sha256=identity(metadata),history_request_metadata_sha256=identity(history),attempted_ids_sha256=identity(sorted(attempted)),attempted_count=len(attempted),cache_overlap_remaining=0,snapshot=snapshot,source_report_sha256=sha(rr),source_packet_builder_sha256=sha(br),preparer_sha256=sha(own_raw))
  future_budgets=dict(json.loads(source['protocol.json'])['budgets'],first_tranche_cumulative_credits=assess_budget(cap)['proposed_first_tranche_ceiling'])
  amendment=dict(status='prospective_owner_authorized_ceiling_increase_pending_exact_review_and_paid_authority',scope='only_current_exact_passing_groups_list',original_protocol_sha256=sha(source['protocol.json']),budgets=future_budgets,billing_reconciliation=json.loads(source['protocol.json'])['billing_reconciliation'],shared_usage_allowance_in_ceiling=SHARED_ALLOWANCE,never_edit_executed_freezes=True,max_baseline_used='hub_supplies_exact_fresh_approved_ceiling_before_execution',paid_authority=False)
  objects={'manifest.json':manifest,'future-budget-policy.json':amendment,'requests.json':rows,'cell-allowlist.json':rectangles,'mappings.json':maps,'denominators.json':denominator,'history-proof.json':proof,'held-exclusions.json':saved_exclusions(frame,final),'response-policy.json':dict(build.missing_policy(rows),quote_policy={'decimal_one':'retain_raw_non_executable'})}
  verify_snapshot(base.RUNTIME_BASE,snapshot,capture)
  if sha(regular(args.final_record))!=FINAL_SHA or regular(rp)!=rr or regular(bp)!=br or regular(Path(__file__))!=own_raw:raise ValueError('preparation source changed')
  now,shared,_=report.captured_closure(repo,args.packet,final['fingerprint']['root'])
  if now!=data or shared!=source:raise ValueError('frozen source closure changed')
  again,_=cache_inventory(roots,capture)
  if again!=inv:raise ValueError('raw metadata inventory changed during preparation')
  build.validate_output(repo,out);out.mkdir(mode=0o700)
  for name,obj in objects.items():
   with (out/name).open('xb') as h:h.write(canonical(obj));h.flush();os.fsync(h.fileno())
  files={n:sha(regular(out/n)) for n in objects}
  files.update({'source/final-record.json':FINAL_SHA,'code/build.py':sha(own_raw),'code/report.py':sha(rr),'code/packet-builder.py':sha(br),'source/pilot-FREEZE.json':sha(regular(args.packet/'FREEZE.json'))})
  load('evidence').write_once(out/'FREEZE.json',dict(root=identity(files),files=files,scope='reviewed_preparation_only_not_executable_packet'))
  base.durable_directory(out)
  return dict(root=identity(files),request_count=len(rows),cap=cap,budget=assess_budget(cap),per_group=per_group,paid_calls=0,runtime_writes=0)


if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--repo',type=Path,required=True);p.add_argument('--packet',type=Path,required=True);p.add_argument('--final-record',type=Path,required=True);p.add_argument('--final-sha256',required=True);p.add_argument('--packet-builder-sha256',required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 print(json.dumps(prepare(a),sort_keys=True))
