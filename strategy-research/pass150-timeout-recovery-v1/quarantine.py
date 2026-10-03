"""Exact immutable stopped-epoch admission; no journal/HTTP receipt invention."""
import copy
import json
from pathlib import Path
import re
import subprocess

ROOT='c75ef924f5d44c62176de915f47744515f2ca35088f2a82e507a105c0733bacb'
BEFORE='4e9afd9cf99499171b928551dd3fc79873f188b25a30b8b5702f9d2fc4192370'
RID='5dbee52007065c15abd196e69f73a02665da1fb3e98965ff1cfed9bc0c7737ca'
MARKER='a19d40fd9527afccfefd9e520c2ae47d4b9ea542a1fab34b811252d419030587'
INIT='d1398bb633d8498d814218b1af1dd46b3bcd8b9482847ae47765471917fc5a09'


def verify(folder,rows,policy,certificate,capture,evidence):
 folder=Path(folder);state=capture.read(folder/'spending-ledger.json')
 if (certificate['source_root']!=ROOT or certificate['ledger_sha256']!=BEFORE or capture.sha(folder/'spending-ledger.json')!=BEFORE
     or capture.sha(folder.parent/'registrations'/(ROOT+'.json'))!=MARKER or capture.sha(folder/'INITIALIZED.json')!=INIT):raise ValueError('exact stopped ledger/registration/init differs')
 if state['bundle_root_sha256']!=ROOT or state['status']!='halted' or state['pending']!=RID or not state['stopped'] or len(state['attempts'])!=12:raise ValueError('not exact retired stopped epoch')
 pending=state['attempts'][RID]
 if pending!={'cache_key':'05175510dc14de25e2ca','reserved_credits':60,'status':'pending'}:raise ValueError('pending send/response evidence exists or reserve differs')
 indexed={r['request_id']:r for r in rows};r=indexed[RID]
 path=folder/'data/raw'/r['sport']/r['source']/r['requested_utc'][:10]/(r['cache_key']+'.parquet')
 if path.exists() or (folder/'receipts'/(RID+'.json')).exists():raise ValueError('raw-less quarantine has response/receipt')
 other=copy.deepcopy(state);other['attempts'].pop(RID);other['pending']=None
 if any(a['status']!='completed' for a in other['attempts'].values()):raise ValueError('other attempt not completed')
 proof=evidence.captured_receipts(folder,rows,other,policy)
 reserved=sum(a['reserved_credits'] for a in state['attempts'].values());billed=sum(a.get('billed_credits',0) for a in state['attempts'].values())
 # Native receipt_union authenticates every classification bill against the
 # ledger. It returns reservations, not a billed aggregate: sum verified bills.
 if proof['reserved']!=660 or reserved!=720 or billed!=660 or state['other_usage_reserved']!=205699 or state['probe_credits']!=1687:raise ValueError('carry/reservations/bills differ')
 untouched=[r for r in rows if r['request_id'] not in state['attempts']]
 if len(untouched)!=1290 or sum(r['max_new_credits'] for r in untouched)!=66480:raise ValueError('untouched scope differs')
 if certificate['attempted_ids']!=sorted(state['attempts']) or certificate['untouched_ids']!=sorted(r['request_id'] for r in untouched) or certificate['request_list_sha256']!=capture.identity(untouched):raise ValueError('certified selection differs')
 if certificate['journal_unchanged'] is not True or certificate['no_resend'] is not True or certificate['reserved']!=720 or certificate['billed']!=660 or certificate['conservative_carry']!=208106:raise ValueError('certificate lowered debit')
 if (certificate['version']!=1 or certificate['kind']!='exact_pre_send_authority_timeout_retirement'
     or certificate['marker_sha256']!=MARKER or certificate['initialization_sha256']!=INIT
     or certificate['quarantined_request_id']!=RID or certificate['pending_reserved']!=60
     or certificate['untouched_count']!=1290 or certificate['untouched_cap']!=66480
     or certificate['completed_ids']!=sorted(other['attempts'])
     or certificate['predecessor_snapshot_sha256']!=state['predecessor_snapshot']
     or certificate['no_response_or_receipt_fabricated'] is not True
     or certificate['usable_quote'] is not False or certificate['next_purchase_authorized'] is not False):raise ValueError('finite certificate differs')
 expected_raw={Path(a['response_path']).absolute() for a in other['attempts'].values()}
 if {p.absolute() for p in (folder/'data/raw').rglob('*.parquet')}!=expected_raw or {p.stem for p in (folder/'receipts').glob('*.json')}!=set(other['attempts']):raise ValueError('unledgered stopped raw/receipt')
 if capture.sha(folder/'spending-ledger.json')!=BEFORE:raise ValueError('stopped state changed during verification')
 return dict(reserved=720,billed=660,untouched_ids=certificate['untouched_ids'],missing={'certified_pre_send_authority_timeout':1},conservative_carry=208106)


def selection(rows,mappings,state):
 """Deterministic projection; every original game stays in the denominator."""
 indexed={r['request_id']:r for r in rows}
 untouched=[r for r in rows if r['request_id'] not in state['attempts']]
 result=[]
 for old in mappings:
  item=copy.deepcopy(old);item['request_ids']=[rid for rid in old['request_ids'] if rid not in state['attempts']]
  reused=item.setdefault('reused_slots',[])
  for rid in old['request_ids']:
   if rid not in state['attempts']:continue
   if rid==RID:
    item['certified_unavailable_request_ids']=[RID];item['certified_unavailable_reason']='exact_pre_send_timeout_no_response_no_resend';continue
   r=indexed[rid];a=state['attempts'][rid]
   if r['source']!='oddsapi/hist_event_odds' or a['status']!='completed':raise ValueError('unexpected completed family')
   reused.append(dict(sport=r['sport'],event_id=r['event_id'],requested_utc=r['requested_utc'],books=r['params']['bookmakers'].split(','),markets=r['params']['markets'].split(','),evidence=[dict(root=ROOT,request_id=rid,response_sha256=a['response_sha256'],receipt_sha256=a['receipt_sha256'])]))
  if not reused:item.pop('reused_slots',None)
  item['reason']=None if item['request_ids'] else 'all_designated_cells_authenticated_or_certified_unavailable'
  result.append(item)
 return untouched,result


def verify_approval(binding,*,fetch=None):
 import hashlib
 cert=binding['certificate'];pin=hashlib.sha256(json.dumps(cert,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
 if pin!=binding['certificate_sha256']:raise ValueError('quarantine certificate differs')
 approval=binding['approval'];url=approval['comment_url'];body=approval['comment_body']
 expected=f'APPROVED offline pre-send quarantine: certificate {pin}, ledger {BEFORE}, pending {RID}, keep reserve 60, no resend'
 if not re.fullmatch(r'https://github\.com/maxzipperman/value-finder/pull/[0-9]+#issuecomment-[0-9]+',url) or body.splitlines().count(expected)!=1 or re.search(r'\b(HALTED|EXHAUSTED|REVOKED|NOT APPROVED|NOT READY)\b',body,re.I):raise ValueError('exact offline quarantine approval required')
 cid=url.rsplit('-',1)[-1]
 live=fetch(cid) if fetch else json.loads(subprocess.check_output(['gh','api',f'repos/maxzipperman/value-finder/issues/comments/{cid}'],text=True,timeout=15))
 if live.get('html_url')!=url or live.get('body')!=body or live.get('user',{}).get('login')!='maxzipperman':raise ValueError('offline quarantine approval changed')
 return cert
