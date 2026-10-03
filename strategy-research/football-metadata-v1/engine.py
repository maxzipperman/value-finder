"""Bounded metadata executor, hub-only. Uses captured v4 accounting/transport guards.

No price normalization, outcomes, list regeneration or automatic recovery. Listing
stage completes then stops for outcome-blind universe reconciliation.
"""
from __future__ import annotations
import csv
from datetime import datetime, timezone
import fcntl
import io
import json
from pathlib import Path
import re
import subprocess
import time
import plan
import capture

ROOT_BASE=Path.home()/'Library/Application Support/ValueFinder/football-acquisition-state'
SOURCE_ROOT=plan.SOURCE_ROOT
PROBE=1687


def key_from(path):
    from dotenv import dotenv_values
    return dotenv_values(path).get('ODDS_API_KEY')


def packet(data):
    m=json.loads(data['manifest.json']);policy=json.loads(data['policy.json'])
    rows=[]
    for item in csv.DictReader(io.StringIO(data['request-list.csv'].decode())):
        endpoint={'oddsapi/hist_events':'events','oddsapi/hist_event_markets':'markets'}.get(item['source'])
        if endpoint is None:raise ValueError('Metadata endpoints only')
        params=json.loads(item['params_json'])
        # Sport is recoverable from each exact request identity, not guessed by an event ID.
        candidates=[plan.make_request(endpoint,plan.ts(item['requested_utc']),event_id=item['event_id'] or None,sport=sport)
                    for sport in (plan.NFL,plan.CFB)]
        matching=[r for r in candidates if r['request_id']==item['request_id']]
        if len(matching)!=1:raise ValueError('CSV request identity differs')
        row=matching[0]
        if row['params']!=params or str(row['max_new_credits'])!=item['max_new_credits']:raise ValueError('CSV parameters/cap differ')
        rows.append(row)
    if (not rows or len({r['request_id'] for r in rows})!=len(rows)
        or m['request_count']!=len(rows) or m['max_new_credits']!=len(rows)
        or m['request_list_sha256']!=capture.digest(data['request-list.csv'])
        or m['request_set_sha256']!=capture.identity(rows)):
        raise ValueError('Exact finite metadata manifest differs')
    if (policy.get('stage')!='listing-gaps' or policy.get('cap')!=1544 or len(rows)!=1544
        or policy.get('allowed_missing')!=['known_snapshot_lag'] or policy.get('max_missing')!=len(rows)
        or any(r['source']!='oddsapi/hist_events' for r in rows)):
        raise ValueError('Only reviewed finite first listing stage enabled')
    return m,rows,policy


def active_authority(auth,m,policy,root,commit):
    rec=auth.get('account_reconciliation',{});snapshot=auth.get('global_snapshot',{})
    if (auth.get('status')!='approved' or auth.get('execution_commit')!=commit
        or auth.get('bundle_root_sha256')!=root or auth.get('max_new_credits')!=m['max_new_credits']
        or not auth.get('human_authorization_evidence') or rec.get('status')!='approved'
        or rec.get('bundle_root_sha256')!=root or rec.get('billing_period_utc')!=datetime.now(timezone.utc).strftime('%Y-%m')
        or rec.get('baseline_mode')!='capture_first_free_check' or rec.get('account_only_recovery')
        or 'pre_run_other_usage_budget_debit' in rec
        or type(rec.get('max_baseline_used')) is not int or rec['max_baseline_used']<0):
        raise ValueError('Exact active metadata/account authority required')
    hub=auth.get('hub_go_ahead',{});body=hub.get('comment_body','')
    required=[f"APPROVED paid run: list {m['request_list_sha256']}, request-set {m['request_set_sha256']}, budget {m['max_new_credits']} credits, commit {commit}",
              f'APPROVED metadata content: root {root}, stage listing-gaps',
              f'APPROVED account reconciliation: sha256 {capture.identity(rec)}, root {root}',
              f'APPROVED global snapshot: sha256 {capture.identity(snapshot)}, root {root}',
              f"APPROVED cache reconciliation: sha256 {capture.identity({'probe_bundle_root':auth.get('probe_bundle_root'), 'additional_raw_roots':auth.get('additional_raw_roots',[])})}, root {root}",
              f"APPROVED metadata policy: sha256 {capture.identity(policy)}, max-missing {policy['max_missing']}, root {root}",
              f"APPROVED account ceiling: max-baseline-used {rec['max_baseline_used']}, root {root}",
              'CURRENT PAID AUTHORITY: ACTIVE']
    if (not all(line in body.splitlines() for line in required)
        or re.search(r'\b(HALTED|EXHAUSTED|REVOKED|NOT APPROVED|NOT READY)\b',body,re.I)
        or not re.fullmatch(r'https://github\.com/maxzipperman/value-finder/pull/99#issuecomment-[0-9]+',hub.get('comment_url',''))):
        raise ValueError('Approval must bind content, list, account, global state and finite policy; reject revocation')
    cid=hub['comment_url'].rsplit('-',1)[-1]
    live=json.loads(subprocess.check_output(['gh','api',f'repos/maxzipperman/value-finder/issues/comments/{cid}'],text=True))
    if live.get('html_url')!=hub['comment_url'] or live.get('body')!=body or live.get('user',{}).get('login')!='maxzipperman':
        raise ValueError('Live hub authority differs')


def global_inventory(exclude=None, verify_receipts=True, source_manifest=None):
    """Read-only exact global snapshot and a fully covering linear carry lineage.

    No max-over-disjoint-epochs estimate. An unknown branch requires reviewed
    reconciliation; pending/uncertain global work always blocks a new stage.
    """
    ledgers={p.parent.name:p for p in ROOT_BASE.glob('*/spending-ledger.json') if p.parent.name!=exclude}
    markers={p.stem:p for p in (ROOT_BASE/'registrations').glob('*.json') if p.stem!=exclude}
    if set(ledgers)!=set(markers) or SOURCE_ROOT not in ledgers:raise ValueError('Global registration/ledger inventory lost or changed')
    states={root:capture.read(p) for root,p in ledgers.items()}
    if any(s.get('pending') or s.get('stopped') for s in states.values()):
        raise ValueError('Unresolved global purchase; never new-root escape')
    original=states[SOURCE_ROOT]
    if len(original.get('attempts',{}))!=2761 or len(original.get('cache_reuse',{}))!=12:
        raise ValueError('Completed original acquisition lost coverage; no fresh-store reset')
    if source_manifest is not None:
        old_rows=json.loads(source_manifest)['requests']
        paid={r['request_id'] for r in old_rows if r['priority']==1 and r['max_new_credits']}
        reuse={r['request_id']:r['cache_sha256'] for r in old_rows if r['priority']==1 and not r['max_new_credits']}
        if set(original['attempts'])!=paid or original['cache_reuse']!=reuse:
            raise ValueError('Original coverage differs from immutable manifest')
    snapshots={'ledgers':{},'registrations':{}}
    for root,state in states.items():
        marker=capture.read(markers[root])
        if (state.get('bundle_root_sha256')!=root or state.get('pending') or state.get('stopped')
            or marker.get('bundle_root_sha256')!=root or marker.get('authorization_sha256')!=state.get('authorization_sha256')
            or Path(marker.get('runtime_path','')).absolute()!=ledgers[root].parent.absolute() or state.get('probe_credits')!=PROBE):
            raise ValueError('Unresolved or mismatched shared state; never new-root escape')
        if state.get('status') not in ('recent_complete_stopped_before_older','event_epoch_complete','event_epoch_partial_reconciled',
                                       'older_epoch_complete','older_epoch_partial_reconciled','metadata_complete'):
            raise ValueError('Unapproved global restart state')
        for rid,a in state['attempts'].items():
            reserve=capture.integer(a['reserved_credits']);bill=capture.integer(a.get('billed_credits',0))
            if a['status'] not in ('completed','missing') or bill>reserve or reserve==0:raise ValueError('Nonterminal or invalid shared debit')
            if not verify_receipts:
                continue
            receipt=ledgers[root].parent/'receipts'/(rid+'.json')
            if capture.sha(receipt)!=a['receipt_sha256']:raise ValueError('Shared receipt changed')
            proof=capture.read(receipt)
            if proof.get('request_id')!=rid:raise ValueError('Shared receipt identity differs')
            if a.get('response_path'):
                if capture.sha(a['response_path'])!=a['response_sha256'] or proof.get('record_sha256',proof.get('response_sha256'))!=a['response_sha256']:
                    raise ValueError('Shared cache evidence changed')
        snapshots['ledgers'][root]=capture.sha(ledgers[root]);snapshots['registrations'][root]=capture.sha(markers[root])
    def chain(root):
        seen=set()
        while root:
            if root in seen or root not in states:raise ValueError('Broken/cyclic shared carry lineage')
            seen.add(root);s=states[root];parent=s.get('predecessor_seed')
            if parent:
                older=states.get(parent['root'])
                if older is None or parent.get('ledger_sha256')!=snapshots['ledgers'][parent['root']]:raise ValueError('Shared ancestor pin changed')
                debit=capture.integer(older['other_usage_reserved'])+sum(capture.integer(a['reserved_credits']) for a in older['attempts'].values())
                if parent.get('cumulative_debit_without_probe')!=debit or s['other_usage_reserved']<debit:raise ValueError('Shared ancestor debit decreased')
                root=parent['root']
            else:
                if root!=SOURCE_ROOT:raise ValueError('Unreviewed independent accounting base')
                root=None
        return seen
    heads=[root for root in states if chain(root)==set(states)]
    if len(heads)!=1:raise ValueError('No unique shared carry lineage; reconcile before purchase')
    head=heads[0];s=states[head]
    seed={'root':head,'ledger_path':str(ledgers[head]),'ledger_sha256':snapshots['ledgers'][head],
          'probe_credits':PROBE,'cumulative_debit_without_probe':capture.integer(s['other_usage_reserved'])+sum(capture.integer(a['reserved_credits']) for a in s['attempts'].values())}
    return snapshots,seed


def metadata_cache_overlap(rows,raw_roots):
    """Normalize default ISO format/time spelling; different keys cannot hide prior queries."""
    import pyarrow.parquet as pq
    targets={(r['sport'],capture.stamp(r['requested_utc'])) for r in rows}
    for root in raw_roots:
        for sport in (plan.NFL,plan.CFB):
            for path in (root/sport/'oddsapi/hist_events').glob('*/*.parquet'):
                if not plan.START[:10]<=path.parent.name<plan.CUTOFF[:10]:continue
                if path.is_symlink():raise ValueError('Symlink metadata cache')
                metadata=pq.read_table(path,columns=['sport','source','url','params_json']).to_pylist()
                if len(metadata)!=1:raise ValueError('Ambiguous metadata cache')
                rec=metadata[0];params=json.loads(rec['params_json'])
                if 'date' not in params:raise ValueError('Metadata cache date absent')
                if (sport,capture.stamp(params['date'])) not in targets:continue
                if rec['sport']!=sport or rec['source']!='oddsapi/hist_events' or rec['url']!=plan.BASE+f'/historical/sports/{sport}/events':
                    raise ValueError('Conflicting metadata source identity')
                # Unknown filters/format at this exact slot remain blocked for review, never a key-miss repurchase.
                if set(params)-{'date','dateFormat'} or params.get('dateFormat','iso')!='iso':raise ValueError('Unreviewed overlapping metadata parameters')
                return True
    return False


def metadata_valid(row,record):
    if (record.get('http_status')!=200 or record.get('cache_key')!=row['cache_key'] or record.get('sport')!=row['sport']
        or record.get('source')!=row['source'] or record.get('url')!=row['url'] or json.loads(record['params_json'])!=row['params']):
        raise ValueError('Metadata HTTP/request identity invalid')
    headers=json.loads(record['headers_json'])
    last,used,left=[capture.integer(headers.get(k)) for k in ('x-requests-last','x-requests-used','x-requests-remaining')]
    if last>1:raise ValueError('Metadata bill exceeds full reservation')
    body=json.loads(record['body'])
    stamp=capture.stamp(body['timestamp']);requested=capture.stamp(row['requested_utc'])
    lag=(requested-stamp).total_seconds()
    if lag<0 or not isinstance(body.get('data'),list):raise ValueError('Future or malformed metadata')
    for k in ('previous_timestamp','next_timestamp'):
        if k not in body:raise ValueError('Metadata snapshot neighbor absent')
    if body['previous_timestamp'] is not None and not capture.stamp(body['previous_timestamp'])<stamp:raise ValueError('Bad previous snapshot')
    if body['next_timestamp'] is not None and not stamp<capture.stamp(body['next_timestamp']):raise ValueError('Bad next snapshot')
    seen=set()
    for event in body['data']:
        if (not isinstance(event,dict) or not isinstance(event.get('id'),str) or not event['id'] or event['id'] in seen
            or event.get('sport_key')!=row['sport'] or not event.get('home_team') or not event.get('away_team')
            or 'bookmakers' in event or 'scores' in event):raise ValueError('Listing must contain metadata only')
        capture.stamp(event['commence_time']);seen.add(event['id'])
    return ('missing' if lag>600 else 'completed'),last,used,left


def metadata_ledger(base,policy):
    class MetadataLedger(base.Ledger):
        def complete(self,row,record,path):
            if self.state['pending']!=row['request_id']:raise ValueError('No durable metadata reservation')
            status,last,used,left=metadata_valid(row,record)
            if status=='missing' and sum(a['status']=='missing' for a in self.state['attempts'].values())>=policy['max_missing']:raise ValueError('Finite missing policy exhausted')
            self.measure_counters(used,left,self.billed()-self.state['epoch']['start_billed']+last)
            receipt=self.folder/'receipts'/(row['request_id']+'.json')
            base.atomic(receipt,{'request_id':row['request_id'],'cache_key':row['cache_key'],'record_sha256':capture.sha(path),
                                'record':record,'status':status,'reason':'known_snapshot_lag' if status=='missing' else None,
                                'usable_quote':False,'headers':json.loads(record['headers_json'])})
            self.checkpoint('after_receipt')
            self.state['attempts'][row['request_id']].update(status=status,billed_credits=last,response_path=str(path),
                          response_sha256=capture.sha(path),receipt_sha256=capture.sha(receipt))
            self.state['pending']=None;self.save()
    return MetadataLedger


def terminal_evidence(ledger,rows):
    by_id={r['request_id']:r for r in rows}
    from archive_markets.cache import read_record
    for rid,a in ledger.state['attempts'].items():
        if rid not in by_id or a['status'] not in ('completed','missing') or a['reserved_credits']!=1 or a.get('send_started') is not True:
            raise ValueError('Unknown/nonterminal/released metadata reservation')
        row=by_id[rid];path=Path(a['response_path'])
        expected=ledger.folder/'data/raw'/row['sport']/row['source']/row['requested_utc'][:10]/(row['cache_key']+'.parquet')
        if path.absolute()!=expected.absolute() or capture.sha(path)!=a['response_sha256']:raise ValueError('Metadata cache changed')
        receipt=ledger.folder/'receipts'/(rid+'.json')
        if capture.sha(receipt)!=a['receipt_sha256']:raise ValueError('Metadata receipt changed')
        proof=capture.read(receipt);rec=read_record(path)
        if (proof['request_id']!=rid or proof['cache_key']!=row['cache_key'] or proof['record_sha256']!=a['response_sha256']
            or capture.identity(proof['record'])!=capture.identity(rec) or proof['usable_quote'] is not False):raise ValueError('Metadata receipt body/identity changed')
        status,last,_,_=metadata_valid(row,rec)
        if status!=a['status'] or last!=a['billed_credits']:raise ValueError('Metadata status/bill changed')


def run(packet_path,root,bundle,auth,*,key,verify,fake_session=None,checkpoint=lambda _:None):
    engine,base,data,source,load=verify();m,rows,policy=packet(data)
    commit=base.checkout_commit(packet_path)
    active_authority(auth,m,policy,root,commit)
    if base.current_runtime()!=json.loads(source['runtime-lock.json']):raise ValueError('Immutable runtime lock differs')
    runtime=base.runtime_path(root);base.execution_context(packet_path,root,runtime)
    with (ROOT_BASE/'followup-purchase.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        _,base,data2,source2,load=verify()
        if data2!=data or source2!=source:raise ValueError('Source changed under shared lock')
        snapshot,seed=global_inventory(root,source_manifest=source['request-manifest.json'])
        if snapshot!=auth['global_snapshot']:raise ValueError('Exact approved global snapshot differs')
        active_authority(auth,m,policy,root,commit)
        existing=runtime/'spending-ledger.json'
        if existing.exists():
            state=capture.read(existing)
            if state.get('status')=='metadata_complete':raise ValueError('Completed one-time authority exhausted')
            if state.get('pending') or state.get('stopped') or state.get('free_account_attempt',{}).get('status')=='started':raise ValueError('Uncertain metadata attempt; never resend')
        # Probe store is authenticated in full to prevent another clone forgetting its completed listings.
        probe_root=Path(auth['probe_bundle_root'])
        for item in json.loads(source['input-provenance.json'])['raw_probe_sources']:
            suffix=item['path'].removeprefix('local://football-probe-v1/')
            if suffix==item['path'] or capture.sha(probe_root/suffix)!=item['sha256']:raise ValueError('Prior probe cache evidence missing/changed')
        raw_roots={Path.home()/'code/value-finder/sharp-markets/data/raw',probe_root/'data/raw'}
        raw_roots.update(p/'data/raw' for p in ROOT_BASE.iterdir() if p.is_dir() and p.name!=root)
        raw_roots.update(Path(p) for p in auth.get('additional_raw_roots',[]))
        if metadata_cache_overlap(rows,raw_roots):
            raise ValueError('Existing semantically compatible metadata cache; amend list, never repurchase')
        effective=[dict(r,path=r['url'].removeprefix(plan.BASE),max_credits=1,priority=1) for r in rows]
        bridge=dict(m,requests=effective,new_credits_by_priority={'1':len(rows)})
        internal=dict(auth,priority=1)
        # v4 authenticates exact list/request-set/commit/approval too; strengthened checks above bind all separate context.
        base.validate_authorization(internal,bridge,root,commit)
        base.validate_reconciliation(auth['account_reconciliation'],root)
        paths=[Path(packet_path)/n for n in ('manifest.json','policy.json','request-list.csv','FREEZE.json')]
        paths.extend(Path(__file__).parent/n for n in ('entry.py','engine.py','capture.py','prepare.py'))
        paths.append(Path(__file__).parent.parent/'nfl-props-archive-v1/plan.py')
        repo=subprocess.check_output(['git','-C',str(packet_path),'rev-parse','--show-toplevel'],text=True).strip()
        relative=[str(p.resolve().relative_to(repo)) for p in paths]
        subprocess.run(['git','-C',repo,'ls-files','--error-unmatch','--',*relative],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        subprocess.run(['git','-C',repo,'diff','--exit-code','HEAD','--',*relative],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        base.register_runtime(runtime,root,internal)
        ledger=metadata_ledger(base,policy)(runtime,json.loads(source['protocol.json']),bridge,root,internal,json.loads(source['probe-spending-ledger.json']))
        session=None
        try:
            if ledger.state.get('predecessor_seed') not in (None,seed):raise ValueError('Global predecessor changed')
            ledger.state['predecessor_seed']=seed
            ledger.state['other_usage_reserved']=max(ledger.state['other_usage_reserved'],seed['cumulative_debit_without_probe'])
            ledger.save();ledger.budget_check(0);ledger.checkpoint=checkpoint
            import os
            if (runtime/'.env').exists():raise ValueError('No implicit runtime credentials')
            os.environ.update(MARKETS_ROOT=str(runtime),MARKETS_DATA_DIR=str(runtime/'data'),MARKETS_REPORTS_DIR=str(runtime/'reports'))
            terminal_evidence(ledger,effective)
            from archive_markets.cache import RawCache,Fetched
            from archive_markets.http import new_session,remember_secret
            secret=key() if callable(key) else key
            if not secret or len(secret)<8:raise ValueError('Missing API key')
            remember_secret(secret)
            class AuthorizedSession(base.GuardedSession):
                def get(self,url,**kwargs):
                    active_authority(auth,m,policy,root,commit)
                    _,_,now_data,now_source,_=verify()
                    if now_data!=data or now_source!=source:raise ValueError('Source changed before send')
                    if global_inventory(root,verify_receipts=False,source_manifest=source['request-manifest.json'])[0]!=snapshot:raise ValueError('Shared state changed before send')
                    return super().get(url,**kwargs)
            session=AuthorizedSession(fake_session or new_session(),ledger,effective);session.ledger_key=secret
            response=session.get(plan.BASE+'/sports',params={},timeout=30)
            if response.status_code!=200:raise ValueError('Free account check failed')
            ledger.account(capture.integer(response.headers['x-requests-used']),capture.integer(response.headers['x-requests-remaining']))
            base.atomic(runtime/'run-manifest.json',{'stage':'listing-gaps','packet_root':root,'execution_commit':commit,
                        'global_snapshot_sha256':capture.identity(snapshot),'predecessor_seed':seed,'policy_sha256':capture.identity(policy),
                        'runtime':base.current_runtime(),'source_root':SOURCE_ROOT,'scope':'historical listing metadata only; stop before market/price stages'})
            cache=RawCache(runtime/'data/raw')
            for row in effective:
                if row['request_id'] in ledger.state['attempts']:continue
                if cache.lookup(row['sport'],row['source'],row['cache_key']) is not None:raise ValueError('Unreconciled own cache; no repurchase')
                ledger.reserve(row);checkpoint('after_reservation')
                def fetch():
                    response=session.get(row['url'],params=row['params'],timeout=30)
                    return Fetched(response.status_code,dict(response.headers),response.text)
                rec=cache.get_or_fetch(sport=row['sport'],source=row['source'],data_date=row['requested_utc'][:10],url=row['url'],params=row['params'],fetch=fetch,cache_statuses=tuple(range(100,600)))
                checkpoint('after_transport')
                path=cache.lookup(row['sport'],row['source'],row['cache_key'])
                if path is None:raise ValueError('Metadata response cache absent')
                with path.open('rb') as handle:
                    import os
                    os.fsync(handle.fileno())
                base.durable_directory(path.parent);checkpoint('after_cache')
                ledger.complete(row,rec,path);checkpoint('after_completion')
                if fake_session is None:time.sleep(.25)
            terminal_evidence(ledger,effective)
            if set(ledger.state['attempts'])!={r['request_id'] for r in rows}:raise ValueError('Full metadata denominator incomplete')
            if global_inventory(root,source_manifest=source['request-manifest.json'])[0]!=snapshot:raise ValueError('Global evidence changed before completion')
            ledger.state['status']='metadata_complete';ledger.save()
            base.atomic(runtime/'coverage-report.json',{'requests':len(rows),'completed':sum(a['status']=='completed' for a in ledger.state['attempts'].values()),
                        'missing_lag':sum(a['status']=='missing' for a in ledger.state['attempts'].values()),'usable_prices':0,
                        'next_stage_authorized':False,'universe_reconciliation_required':True})
            return {'status':'metadata_complete','new_reserved':ledger.reserved(),'new_billed':ledger.billed(),'next_stage_authorized':False}
        except BaseException:
            ledger.halt('Metadata stage halted; full reservations retained; no automatic recovery or resend')
            raise base.Halt('Metadata stage halted; inspect local evidence; never automatically retry') from None
        finally:
            if session:session.close()
            ledger.close()
