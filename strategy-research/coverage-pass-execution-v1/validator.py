"""Bulk residual validation; no sample redraw, outcomes, credentials or writes."""
import json
import capture
import plan
import mapping
import receipts
import overlap
import preparation
import packet_builder

PREPARATION_ROOT='22c546ed08e0b9f52037dd17c0c90be707d0804e5d68be66c046730639ba8f40'
FINAL_SHA='100a53275119fba283b3e8938cfee994f0d1a535201f2bab2e8769bfba9fdbdb'


def packet(data,source):
 m=json.loads(data['manifest.json']);rows=json.loads(data['requests.json']);frame=json.loads(data['frame.json'])
 final=json.loads(data['final-record.json']);original=json.loads(data['preparation/manifest.json'])
 if capture.digest(data['final-record.json'])!=FINAL_SHA:raise ValueError('saved final differs')
 selected,den=preparation.target_selection(frame,final)
 maps=json.loads(data['mappings.json']);indexed={r['request_id']:r for r in rows}
 if len(indexed)!=len(rows) or not rows:raise ValueError('duplicate/empty request list')
 if json.loads(data['denominators.json'])!=den or {x['game_id'] for x in maps}!=set(selected['selected']) or len(maps)!=len(selected['selected']):raise ValueError('bulk denominator differs')
 overlap.check_internal(rows,maps)
 if json.loads(data['cell-allowlist.json'])!=preparation.cell_rectangles(rows):raise ValueError('exact cells differ')
 if (len(rows)!=1302 or sum(r['max_new_credits'] for r in rows)!=67200
     or m['request_list_sha256']!=capture.digest(data['requests.json'])
     or m['request_set_sha256']!=capture.identity(rows)
     or original['request_list_sha256']!=m['request_list_sha256']
     or original['request_count']!=m['request_count'] or original['max_new_credits']!=m['max_new_credits']
     or original['paid_authority'] is not False or original['execution_adapter_ready'] is not False):raise ValueError('list/cap/preparation differs')
 original_rows={r['request_id']:r for r in json.loads(source['request-manifest.json'])['requests']}
 for r in rows:
  if r['source']=='oddsapi/hist_odds':
   old=original_rows.get(r['request_id'])
   if not old or old['priority']!=2 or not old['max_new_credits'] or r!=dict(old,url=plan.BASE+old['path']):raise ValueError('older row changed')
  elif r['source']=='oddsapi/hist_event_odds':
   books=r['params']['bookmakers'].split(',');markets=r['params']['markets'].split(',')
   if not set(markets)<=set(mapping.MARKETS):raise ValueError('market scope changed')
   if r!=plan.make_request('odds',plan.ts(r['requested_utc']),books=books,markets=markets,event_id=r['event_id'],sport=r['sport']):raise ValueError('props reconstruction differs')
  else:raise ValueError('unsupported endpoint')
 policy=json.loads(data['policy.json']);expected=packet_builder.missing_policy(rows)
 expected['quote_policy']={'decimal_one':'retain_raw_non_executable'}
 if policy!=expected:raise ValueError('finite missing policy differs')
 receipts.validate_policy(rows,policy)
 future=json.loads(data['future-budget-policy.json']);cfg=json.loads(data['execution-protocol.json']);old=json.loads(source['protocol.json'])
 expected_cfg=dict(old,budgets=dict(old['budgets'],first_tranche_cumulative_credits=274686))
 if cfg!=expected_cfg or future['budgets']!=cfg['budgets'] or future['billing_reconciliation']!=cfg['billing_reconciliation'] or future['shared_usage_allowance_in_ceiling']!=100 or future['paid_authority'] is not False:raise ValueError('prospective budget differs')
 if original['budget']!=preparation.assess_budget(67200):raise ValueError('carry/margin differs')
 return dict(status='offline_validated_authority_required',requests=1302,max_new_credits=67200,full_denominator=len(den),purchase_candidate_denominator=len(maps),paid_authority=False)


def residual(data,source,load,root_base,snapshot):
 """After authenticated global union, reconstruct exactly from terminal metadata."""
 frame=json.loads(data['frame.json']);final=json.loads(data['final-record.json']);selection,_=preparation.target_selection(frame,final)
 history=packet_builder.authenticated_history(root_base,snapshot,load('capture'))
 context={'freeze':data['source/FREEZE.json'],'files':source}
 history.extend(packet_builder.frozen_probe_history(context,load))
 protocol=json.loads(data['original-pilot-protocol.json'])
 rows,maps=packet_builder.selected_union(frame,selection,json.loads(data['slot-map.json']),json.loads(source['request-manifest.json'])['requests'],history,load,protocol['candidate_books'])
 groups={g['game_id']:g['stratum'] for g in frame};byid={r['request_id']:r for r in rows};priority={}
 for item in maps:
  for rid in item['request_ids']:
   i=preparation.PRIORITY.index(groups[item['game_id']]);priority[rid]=min(priority.get(rid,i),i)
 rows.sort(key=lambda r:(priority[r['request_id']],r['requested_utc'],r['request_id']))
 if rows!=json.loads(data['requests.json']) or maps!=json.loads(data['mappings.json']):raise ValueError('fresh residual reconstruction differs')
 if {h['request_id'] for h in history}&set(byid):raise ValueError('attempted request in bulk residual')
 return True
