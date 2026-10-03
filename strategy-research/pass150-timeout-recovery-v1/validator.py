"""Exact original scope proof followed by deterministic no-resend projection."""
import json
from pathlib import Path
import capture
import prior_runner
import timeout_quarantine as quarantine
import prior_evidence
import preparation
import packet_builder
import receipts
import overlap
import executor

def original(data):return {n[14:]:v for n,v in data.items() if n.startswith('original-bulk/')}

def objects(data,root_base):
 old=original(data);cert=json.loads(data['recovery/certificate.json']);state=json.loads(data['recovery/before-ledger.json'])
 rows,maps=quarantine.selection(json.loads(old['requests.json']),json.loads(old['mappings.json']),state)
 old_baseline=json.loads(old['baseline.json']);snapshot=old_baseline['expected_global_snapshot']
 current={'ledgers':dict(snapshot['ledgers'],**{quarantine.ROOT:quarantine.BEFORE}),'registrations':dict(snapshot['registrations'],**{quarantine.ROOT:quarantine.MARKER})}
 folder=Path(root_base)/quarantine.ROOT
 binding=dict(kind=cert['kind'],ledger_sha256=quarantine.BEFORE,marker_sha256=quarantine.MARKER,initialization_sha256=quarantine.INIT,rows=json.loads(old['requests.json']),policy=json.loads(old['policy.json']),predecessor_snapshot=state['predecessor_snapshot'],authorization_sha256=state['authorization_sha256'],plan_sha256=quarantine.ROOT,reconciliation=dict(certificate=cert,certificate_sha256=capture.identity(cert),approval_path=str(folder/'authority-timeout-retirement/approval.json')))
 baseline=dict(old_baseline,pilot_bindings=dict(old_baseline['pilot_bindings'],**{quarantine.ROOT:binding}),expected_global_snapshot=current)
 cells=preparation.cell_rectangles(rows)
 budget=dict(prior_conservative_debit=208106,new_cap=66480,proposed_cumulative_purchase_debit=274586,proposed_first_tranche_ceiling=274686,day_one_cumulative_ceiling=400000,monthly_cumulative_ceiling=4440000,account_reserve_floor=531630,shared_usage_allowance=100,paid_authority=False)
 manifest=dict(version=1,stage='exact_authority_timeout_untouched_successor',request_count=1290,max_new_credits=66480,request_list_sha256=capture.identity(rows),request_set_sha256=capture.identity(rows),cell_rectangles_sha256=capture.identity(cells),mappings_sha256=capture.identity(maps),denominator_sha256=capture.digest(data['denominators.json']),original_accepted_manifest_sha256=capture.digest(old['manifest.json']),certificate_sha256=capture.identity(cert),passing_groups=json.loads(old['manifest.json'])['passing_groups'],global_snapshot=current,budget=budget,paid_authority=False,no_new_draw=True,no_new_statistical_look=True)
 cfg=dict(json.loads(old['execution-protocol.json']),authority_timeout_retirement=dict(source_root=quarantine.ROOT,certificate_sha256=capture.identity(cert),attempted_excluded=12,completed_reused=11,certified_unavailable=1,successor_count=1290,successor_cap=66480,journal_mutation=False,no_resend=True))
 roots=sorted(set(json.loads(old['overlap.json'])['raw_roots'])|{str(folder/'data/raw')})
 return rows,maps,cells,manifest,baseline,cfg,roots

def packet(data,source):
 old=original(data);prior_runner.packet(old,source)
 cert=json.loads(data['recovery/certificate.json']);state=json.loads(data['recovery/before-ledger.json'])
 if (capture.digest(data['recovery/before-ledger.json'])!=quarantine.BEFORE or cert['source_root']!=quarantine.ROOT or cert['ledger_sha256']!=quarantine.BEFORE
     or cert['original_request_list_sha256']!=capture.digest(old['requests.json']) or cert['original_mappings_sha256']!=capture.digest(old['mappings.json'])
     or cert['attempted_ids']!=sorted(state['attempts']) or len(state['attempts'])!=12
     or cert['quarantined_request_id']!=quarantine.RID or state['pending']!=quarantine.RID
     or cert['reserved']!=720 or cert['billed']!=660 or cert['pending_reserved']!=60 or cert['conservative_carry']!=208106
     or cert['journal_unchanged'] is not True or cert['no_resend'] is not True or cert['usable_quote'] is not False or cert['next_purchase_authorized'] is not False):raise ValueError('finite certificate/stop identity differs')
 rows,maps,cells,m,baseline,cfg,roots=objects(data,executor.RUNTIME_BASE)
 if (len(rows)!=1290 or sum(r['max_new_credits'] for r in rows)!=66480 or cert['untouched_ids']!=sorted(r['request_id'] for r in rows)
     or cert['request_list_sha256']!=capture.identity(rows) or cert['untouched_count']!=1290 or cert['untouched_cap']!=66480
     or set(state['attempts']) & {r['request_id'] for r in rows}):raise ValueError('untouched no-resend scope differs')
 for n,value in [('requests.json',rows),('mappings.json',maps),('cell-allowlist.json',cells),('manifest.json',m),('baseline.json',baseline),('execution-protocol.json',cfg)]:
  if json.loads(data[n])!=value:raise ValueError('successor '+n+' differs')
 if any(data[n]!=old[n] for n in ('denominators.json','frame.json','final-record.json','future-budget-policy.json')):raise ValueError('original denominator/gate changed')
 policy=packet_builder.missing_policy(rows);policy['quote_policy']={'decimal_one':'retain_raw_non_executable'}
 if json.loads(data['policy.json'])!=policy:raise ValueError('successor finite missing policy differs')
 receipts.validate_policy(rows,policy);overlap.check_internal(rows,maps)
 cache=json.loads(data['overlap.json']);prior=json.loads(old['overlap.json'])
 if set(cache)!=set(prior) or cache['raw_roots']!=roots or cache['probe_bundle_root']!=prior['probe_bundle_root']:raise ValueError('successor cache inventory scope differs')
 return dict(status='offline_validated_hub_installation_and_paid_authority_required',requests=1290,max_new_credits=66480,conservative_carry=208106,full_denominator=len(json.loads(data['denominators.json'])),purchase_candidate_denominator=len(maps),completed_reused=11,certified_unavailable=1,paid_authority=False)

def residual(data,source,load,root_base,snapshot):
 old=original(data);prior=json.loads(old['baseline.json'])['expected_global_snapshot']
 expected=json.loads(data['baseline.json'])['expected_global_snapshot']
 if snapshot!=expected:raise ValueError('successor snapshot differs')
 # Reconstruct the accepted1302 scope against its original nine-root history.
 # The new retired epoch is authenticated separately, never parsed as a terminal
 # history row with an invented response or missing classification.
 prior_runner.residual(old,source,load,root_base,prior)
 quarantine.verify(Path(root_base)/quarantine.ROOT,json.loads(old['requests.json']),json.loads(old['policy.json']),json.loads(data['recovery/certificate.json']),capture,prior_evidence)
 packet(data,source)
 return True
