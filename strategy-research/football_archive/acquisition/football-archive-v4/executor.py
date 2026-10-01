"""Recent-only acquisition controls. Default CLI verifies offline; spending needs separate approval."""
from __future__ import annotations
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import importlib.metadata
import json
import os
import re
import subprocess
from pathlib import Path
import sys


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False, default=str).encode()


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def durable_directory(path):
    fd = os.open(Path(path), os.O_RDONLY)
    try: os.fsync(fd)
    finally: os.close(fd)


def atomic(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix+'.tmp')
    with tmp.open('wb') as handle:
        handle.write(canonical(value)+b'\n'); handle.flush(); os.fsync(handle.fileno())
    os.replace(tmp, path); durable_directory(path.parent)


def current_runtime():
    return {'python':sys.version.split()[0], 'distributions':{k:importlib.metadata.version(k) for k in
            ('requests','urllib3','pyarrow','PyYAML','python-dotenv','certifi','charset-normalizer','idna')}}


class Halt(RuntimeError): pass


RUNTIME_BASE = Path.home()/'Library/Application Support/ValueFinder/football-acquisition-state'
LIVE_CHECKOUT = Path.home()/'code/value-finder'


def runtime_path(root):
    if not re.fullmatch('[a-f0-9]{64}', root): raise Halt('Invalid frozen root')
    path = (RUNTIME_BASE/root).resolve()
    if path.is_relative_to(LIVE_CHECKOUT.resolve()) or any((p/'.git').exists() for p in (path,*path.parents)):
        raise Halt('Acquisition runtime must be outside every git checkout')
    return path


def execution_context(bundle, root, runtime):
    if Path(bundle).resolve().is_relative_to(LIVE_CHECKOUT.resolve()):
        raise Halt('Execution from the live checkout is prohibited')
    if Path(runtime).resolve() != runtime_path(root):
        raise Halt('Only the fixed root-keyed runtime is allowed')


def checkout_commit(bundle):
    try:
        git='/Library/Developer/CommandLineTools/usr/bin/git' if Path('/Library/Developer/CommandLineTools/usr/bin/git').is_file() else 'git'
        return subprocess.check_output([git,'-C',str(bundle),'rev-parse','HEAD'],text=True,stderr=subprocess.DEVNULL).strip()
    except (subprocess.CalledProcessError, OSError):
        raise Halt('Execution requires the approved git checkout') from None


def validate_authorization(authorization, manifest, root, commit=None):
    cap = manifest['new_credits_by_priority']['1']
    if (authorization.get('status')!='approved' or authorization.get('bundle_root_sha256')!=root
        or authorization.get('priority')!=1 or authorization.get('max_new_credits')!=cap
        or not authorization.get('human_authorization_evidence')):
        raise Halt('Missing exact recent-slice authorization')
    hub=authorization.get('hub_go_ahead',{});approved_commit=authorization.get('execution_commit','')
    expected=(f"APPROVED paid run: list {manifest['request_list_sha256']}, request-set {manifest['request_set_sha256']}, "
              f"budget {cap} credits, commit {approved_commit}")
    if (hub.get('status')!='approved' or hub.get('bundle_root_sha256')!=root
        or hub.get('request_set_sha256')!=manifest['request_set_sha256']
        or hub.get('request_list_sha256')!=manifest['request_list_sha256']
        or hub.get('budget_credits')!=cap or hub.get('commit')!=approved_commit
        or not re.fullmatch('[a-f0-9]{40}',approved_commit)
        or (commit is not None and commit!=approved_commit)
        or not re.fullmatch(r'https://github\.com/maxzipperman/value-finder/pull/99#issuecomment-[0-9]+',hub.get('comment_url',''))
        or expected not in hub.get('comment_body','').splitlines()):
        raise Halt('Hub go-ahead must bind CSV, request set, budget, current commit and approval comment')


def verify_live_hub_comment(authorization):
    hub=authorization['hub_go_ahead'];cid=hub['comment_url'].rsplit('-',1)[-1]
    try:
        comment=json.loads(subprocess.check_output(['gh','api',f'repos/maxzipperman/value-finder/issues/comments/{cid}'],text=True))
    except (OSError,subprocess.CalledProcessError,ValueError):
        raise Halt('Cannot verify hub approval comment through GitHub') from None
    if (comment.get('html_url')!=hub['comment_url'] or comment.get('body')!=hub['comment_body']
        or comment.get('user',{}).get('login')!='maxzipperman'):
        raise Halt('GitHub hub approval comment differs from recorded evidence')


def validate_reconciliation(reconciliation,root):
    if (not reconciliation or reconciliation.get('status')!='approved' or reconciliation.get('bundle_root_sha256')!=root
        or reconciliation.get('baseline_mode') not in ('capture_first_free_check','explicit')
        or not reconciliation.get('reason') or not reconciliation.get('owner_note')
        or type(reconciliation.get('max_baseline_used')) is not int or reconciliation['max_baseline_used']<0
        or reconciliation.get('billing_period_utc')!=datetime.now(timezone.utc).strftime('%Y-%m')):
        raise Halt('Approved documented account reconciliation required')
    return reconciliation


def register_runtime(runtime, root, authorization):
    """A separate durable marker survives deletion of the root's runtime folder."""
    registrations=RUNTIME_BASE/'registrations';registrations.mkdir(parents=True,exist_ok=True)
    marker=registrations/(root+'.json')
    identity={'bundle_root_sha256':root,'authorization_sha256':hashlib.sha256(canonical(authorization)).hexdigest(),
              'runtime_path':str(Path(runtime).resolve())}
    lock=(registrations/'registration.lock').open('a')
    try:
        fcntl.flock(lock,fcntl.LOCK_EX)
        if marker.exists():
            if json.loads(marker.read_text())!=identity:raise Halt('Runtime registration approval differs; never reset')
            if not (Path(runtime)/'spending-ledger.json').exists():raise Halt('Registered runtime ledger missing; never recreate')
        else:
            if (Path(runtime)/'spending-ledger.json').exists():raise Halt('Ledger without central registration; inspect')
            atomic(marker,identity)
    finally:lock.close()


class Ledger:
    """Reservations persist at their upper bound even when a response costs less."""
    def __init__(self, folder, protocol, manifest, root, authorization, probe, reconciliation=None):
        self.folder = Path(folder); self.folder.mkdir(parents=True,exist_ok=True)
        self.path = self.folder/'spending-ledger.json'
        self.protocol, self.manifest, self.root = protocol, manifest, root
        cap = manifest['new_credits_by_priority']['1']
        validate_authorization(authorization,manifest,root)
        if probe.get('pending') or probe.get('stopped') or sum(a['counted_credits'] for a in probe['attempts']) != 1687 or probe['reserved_credits'] != 1687:
            raise Halt('Probe accounting cannot be seeded')
        reconciliation = reconciliation or authorization.get('account_reconciliation')
        validate_reconciliation(reconciliation,root)
        self.reconciliation=reconciliation
        self.reconciliation_sha256=hashlib.sha256(canonical(reconciliation)).hexdigest()
        self.authorization_sha256 = hashlib.sha256(canonical(authorization)).hexdigest()
        self.lock = (self.folder/'acquisition.lock').open('a')
        try:
            fcntl.flock(self.lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            if self.path.exists():
                self.state = json.loads(self.path.read_text())
                if self.state['bundle_root_sha256'] != root or self.state['authorization_sha256'] != self.authorization_sha256:
                    raise Halt('Ledger root or authorization differs; no budget reset')
            else:
                # Marker makes accidental removal of an initialized ledger a stop, not a fresh budget.
                marker = self.folder/'INITIALIZED.json'
                if marker.exists(): raise Halt('Previously initialized ledger missing; inspect rather than reset')
                self.state = {'bundle_root_sha256':root,'authorization_sha256':self.authorization_sha256,
                              'probe_credits':1687,'slice_cap':cap,'pending':None,'stopped':None,
                              'attempts':{},'cache_reuse':{},'accounts':[],
                              'provider_used':None,'provider_remaining':None,'epoch':None,'reconciliation_history':[],
                              'other_usage_reserved':0,'status':'prepared'}
                atomic(marker,{'bundle_root_sha256':root,'probe_credits':1687})
                self.save()
            self.validate_state(check_floor=False)
            if self.state['pending']:
                raise Halt('Pending paid attempt: offline hash-pinned cached-response reconciliation only; never resend')
            if self.state['stopped']:
                if (not reconciliation.get('account_only_recovery') or reconciliation.get('prior_ledger_sha256')!=sha(self.path)
                    or any(a['status'] not in ('completed','missing') for a in self.state['attempts'].values())):
                    raise Halt('Stopped ledger requires explicit account-only recovery; pending attempts cannot be cleared')
                self.state['reconciliation_history'].append({'prior_ledger_sha256':sha(self.path),'reconciliation_sha256':self.reconciliation_sha256,'reason':'approved account-only recovery; budgets retained'})
                self.state['stopped']=None;self.state['epoch']=None;self.state['provider_used']=None;self.state['provider_remaining']=None;self.save()
            if self.state['epoch'] is None and reconciliation['baseline_mode']=='explicit':
                self.adopt_baseline(integer(reconciliation.get('used')),integer(reconciliation.get('remaining')))
            if self.state.get('active_reconciliation_sha256') not in (None,self.reconciliation_sha256) and self.state['epoch'] is not None:
                raise Halt('Changed reconciliation requires explicit account-only recovery')
            self.budget_check(0)
        except BaseException:
            self.lock.close(); raise

    def validate_state(self,check_floor=True):
        allowed = {r['request_id']:r for r in self.manifest['requests'] if r['priority']==1 and r['max_new_credits']}
        if self.state['probe_credits'] != 1687 or self.state['slice_cap'] != self.manifest['new_credits_by_priority']['1']:
            raise Halt('Ledger budget baseline changed')
        for rid, a in self.state['attempts'].items():
            if rid not in allowed or a['reserved_credits'] < allowed[rid]['max_new_credits']:
                raise Halt('Attempt differs from authorized allowlist')
        if self.state['pending'] and self.state['pending'] not in self.state['attempts']:
            raise Halt('Pending attempt missing from ledger')
        self.budget_check(0,check_floor=check_floor)

    def close(self): self.lock.close()
    def save(self): atomic(self.path,self.state)
    def halt(self, reason):
        self.state['stopped']=reason; self.state['status']='halted'; self.save()
    def reserved(self): return sum(a['reserved_credits'] for a in self.state['attempts'].values())
    def budget_check(self, extra, check_floor=True):
        budgets = self.protocol['budgets']; total=self.state['probe_credits']+self.state['other_usage_reserved']+self.reserved()+extra
        if self.reserved()+extra > self.state['slice_cap']: raise Halt('Recent-slice credit ceiling')
        for name in ('first_tranche_cumulative_credits','day_one_cumulative_ceiling','broader_cumulative_ceiling'):
            if total > budgets[name]: raise Halt('Cumulative budget exceeded: '+name)
        if check_floor and self.state['provider_remaining'] is not None and self.conservative_remaining()-extra < budgets['account_reserve_floor']: raise Halt('Account reserve floor')

    def billed(self):
        return sum(a.get('billed_credits',0) for a in self.state['attempts'].values() if a['status'] in ('completed','missing'))

    def adopt_baseline(self,used,remaining):
        if min(used,remaining)<0: raise Halt('Invalid baseline')
        if used>self.reconciliation['max_baseline_used']:raise Halt('Approved max_baseline_used exceeded; never adopt a spent balance')
        explicit=self.reconciliation.get('pre_run_other_usage_budget_debit')
        debit=used if explicit is None else integer(explicit)
        self.state['other_usage_reserved']=max(self.state['other_usage_reserved'],debit)
        self.state['epoch']={'start_used':used,'start_remaining':remaining,'start_billed':self.billed(),
                             'used_highwater':used,'remaining_lowwater':remaining,'external_peak':0,
                             'prebaseline_other_debit':self.state['other_usage_reserved']}
        self.state['provider_used'],self.state['provider_remaining']=used,remaining
        self.state['active_reconciliation_sha256']=self.reconciliation_sha256
        self.state['reconciliation_history'].append({'reconciliation_sha256':self.reconciliation_sha256,
            'baseline_used':used,'baseline_remaining':remaining,'pre_run_other_debit':debit,
            'utc':datetime.now(timezone.utc).isoformat(),'reason':self.reconciliation['reason']})
        self.save();self.budget_check(0)

    def conservative_remaining(self):
        epoch=self.state['epoch']
        if epoch is None: return self.state['provider_remaining']
        own=self.billed()-epoch['start_billed']
        return min(epoch['remaining_lowwater'],epoch['start_remaining']-own-epoch['external_peak'])

    def measure_counters(self,used,remaining,own):
        epoch=self.state['epoch'];rules=self.protocol['billing_reconciliation'];lag_limit=rules['counter_lag_tolerance_credits']
        if epoch is None:raise Halt('No adopted account baseline')
        if epoch['used_highwater']-used>lag_limit or remaining-epoch['remaining_lowwater']>lag_limit:
            raise Halt('Large counter regression/reset requires fresh documented reconciliation')
        hi=max(epoch['used_highwater'],used);lo=min(epoch['remaining_lowwater'],remaining)
        external=max(0,hi-epoch['start_used']-own,epoch['start_remaining']-lo-own)
        peak=max(epoch['external_peak'],external)
        lag=max(0,own-(hi-epoch['start_used']),own-(epoch['start_remaining']-lo))
        self.state['other_usage_reserved']=max(self.state['other_usage_reserved'],epoch['prebaseline_other_debit']+peak)
        epoch.update(used_highwater=hi,remaining_lowwater=lo,external_peak=peak,
                     last_counter_lag=lag,peak_counter_lag=max(epoch.get('peak_counter_lag',0),lag))
        self.state['provider_used'],self.state['provider_remaining']=used,remaining
        self.save()
        if peak>rules['shared_usage_margin_credits']:raise Halt('Cumulative external-usage margin exceeded')
        if lag>lag_limit:raise Halt('Cumulative counter lag tolerance exceeded')
        effective=min(lo,epoch['start_remaining']-own-peak)
        if effective<self.protocol['budgets']['account_reserve_floor']:raise Halt('Conservative account reserve breached')
        self.budget_check(0)

    def account(self, used, remaining):
        if type(used) is not int or type(remaining) is not int or min(used,remaining)<0:
            raise Halt('Unreadable account billing')
        if self.state['epoch'] is None:self.adopt_baseline(used,remaining)
        else:self.measure_counters(used,remaining,self.billed()-self.state['epoch']['start_billed'])
        self.budget_check(0)
        self.state['accounts'].append({'used':used,'remaining':remaining,'utc':datetime.now(timezone.utc).isoformat()})
        self.state['free_account_attempt']={'status':'completed','reserved_credits':0,'used':used,'remaining':remaining}
        self.save()

    def reserve(self,row):
        allowed = next((r for r in self.manifest['requests'] if r['request_id']==row.get('request_id')),None)
        if allowed != row or row['priority']!=1 or row['max_new_credits']==0: raise Halt('Outside authorized paid allowlist')
        if self.state['pending'] or self.state['stopped']: raise Halt('Unresolved/stopped attempt')
        if row['request_id'] in self.state['attempts']: raise Halt('Never resend an existing attempt')
        if self.state['epoch'] is None:raise Halt('Free account baseline must precede any paid reservation')
        self.budget_check(row['max_new_credits'])
        self.state['attempts'][row['request_id']]={'reserved_credits':row['max_new_credits'],'status':'pending','cache_key':row['cache_key']}
        self.state['pending']=row['request_id']; self.state['status']='running'; self.save()

    def observe_headers(self,headers,status=None):
        rid=self.state['pending']
        safe={k:headers.get(k) for k in ('x-requests-last','x-requests-used','x-requests-remaining')}
        a=self.state['attempts'][rid];a['observed_billing_headers']=safe;a['observed_http_status']=status
        try:
            last=integer(safe['x-requests-last']);used=integer(safe['x-requests-used']);left=integer(safe['x-requests-remaining'])
            a['reserved_credits']=max(a['reserved_credits'],last)
            # Counter attribution is cumulative and happens once at completion, not once per header.
        except Halt:
            pass  # Unreadable billing stays conservatively reserved and unresolved.
        self.save()

    def complete(self,row,record,path):
        if self.state['pending'] != row['request_id']: raise Halt('Response has no durable reservation')
        validate_response(row,record,self.protocol)
        headers=json.loads(record['headers_json']); last=integer(headers.get('x-requests-last')); used=integer(headers.get('x-requests-used')); remaining=integer(headers.get('x-requests-remaining'))
        if last>row['max_new_credits']:raise Halt('Per-call bill exceeds reserved upper bound')
        self.measure_counters(used,remaining,self.billed()-self.state['epoch']['start_billed']+last)
        receipt=self.folder/'receipts'/f"{row['request_id']}.json"
        atomic(receipt,{'request_id':row['request_id'],'cache_key':row['cache_key'],'record_sha256':sha(path),
                        'body_sha256':hashlib.sha256(record['body'].encode()).hexdigest(),'headers':headers,'record':record})
        getattr(self,'checkpoint',lambda _:None)('after_receipt_durability')
        a=self.state['attempts'][row['request_id']]
        a.update(status='completed',billed_credits=last,response_path=str(Path(path).resolve()),response_sha256=sha(path),receipt_sha256=sha(receipt))
        self.state['provider_used'],self.state['provider_remaining']=used,remaining
        self.state['pending']=None; self.save()


def integer(value):
    if isinstance(value,bool): raise Halt('Invalid billing number')
    text=str(value)
    if not text.isdigit(): raise Halt('Unreadable billing number')
    return int(text)


def validate_response(row,record,protocol):
    from price_eligibility import timestamp
    if (record['cache_key'] != row['cache_key'] or record['sport'] != row['sport'] or record['source'] != row['source']
        or record['url'] != 'https://api.the-odds-api.com/v4'+row['path'] or json.loads(record['params_json']) != row['params']):
        raise Halt('Response request identity mismatch')
    if record['http_status'] != 200: raise Halt('HTTP response requires inspection')
    body=json.loads(record['body'])
    if not isinstance(body.get('data'),list): raise Halt('Malformed historical response')
    returned=timestamp(body.get('timestamp')); requested=timestamp(row['requested_utc'])
    if returned is None or not 0 <= (requested-returned).total_seconds() <= protocol['price_row_eligibility']['maximum_snapshot_lag_seconds']:
        raise Halt('Invalid returned snapshot timing')
    for field in ('previous_timestamp','next_timestamp'):
        if timestamp(body.get(field)) is None: raise Halt('Missing historical snapshot neighbors')
    if not timestamp(body['previous_timestamp']) < returned < timestamp(body['next_timestamp']):
        raise Halt('Invalid historical snapshot neighbors')
    headers=json.loads(record['headers_json'])
    for field in ('x-requests-last','x-requests-used','x-requests-remaining'): integer(headers.get(field))


class GuardedSession:
    """Existing BulkClient sends through this exact-allowlist boundary; redirects disabled."""
    def __init__(self, session, ledger, rows):
        self.session,self.ledger=session,ledger
        self.rows={r['request_id']:r for r in rows}
        self.account_permitted=True
        for adapter in session.adapters.values():
            if adapter.max_retries.total != 0: raise Halt('HTTP adapter retries must be zero')
    def get(self,url,params=None,**kwargs):
        params=dict(params or {});params.pop('apiKey',None)
        if url=='https://api.the-odds-api.com/v4/sports' and not params and self.account_permitted:
            self.account_permitted=False
            self.ledger.state['free_account_attempt']={'status':'started','reserved_credits':0,'path':'/sports'}
            self.ledger.save()
        else:
            rid=self.ledger.state['pending']; row=self.rows.get(rid)
            if row is None or url != 'https://api.the-odds-api.com/v4'+row['path'] or params != row['params']:
                raise Halt('Send outside durably reserved allowlist')
            disk=json.loads(self.ledger.path.read_text())
            if disk['pending']!=rid or disk['attempts'][rid]['status']!='pending': raise Halt('Reservation not durable')
            # One transport call per reservation; persists before sending. Any crash stays unresolved.
            if disk['attempts'][rid].get('send_started'): raise Halt('No resend of unresolved transport attempt')
            self.ledger.state['attempts'][rid]['send_started']=True; self.ledger.save()
        kwargs['allow_redirects']=False
        response = self.session.get(url,params={**params,**({'apiKey':self.ledger_key} if hasattr(self,'ledger_key') else {})},**kwargs)
        from urllib.parse import quote,quote_plus
        forms={self.ledger_key,quote(self.ledger_key,safe=''),quote_plus(self.ledger_key)} if hasattr(self,'ledger_key') else set()
        if any(secret in response.text or any(secret in str(v) for v in response.headers.values()) for secret in forms):
            raise Halt('Credential exposure in response; halt before persisting')
        if self.ledger.state['pending']:
            self.ledger.observe_headers(response.headers,response.status_code)
        else:
            self.ledger.state['free_account_attempt'].update(status='received',billing_headers={k:response.headers.get(k) for k in ('x-requests-last','x-requests-used','x-requests-remaining')})
            self.ledger.save()
        if not self.ledger.state['pending'] and integer(response.headers.get('x-requests-last')) != 0:
            self.ledger.state['other_usage_reserved'] += integer(response.headers.get('x-requests-last'))
            self.ledger.save()
            raise Halt('Free account check unexpectedly billed')
        return response
    def close(self): self.session.close()


def vendor_imports(bundle,runtime):
    os.environ['MARKETS_ROOT']=str(Path(runtime).resolve())
    os.environ['MARKETS_DATA_DIR']=str(Path(runtime).resolve()/'data')
    if (Path(runtime)/'.env').exists(): raise Halt('Runtime directory must not contain implicit credentials')
    sys.path.insert(0,str(bundle));sys.dont_write_bytecode=True
    from archive_markets.cache import RawCache,read_record
    from archive_markets.oddsapi.bulk import BulkClient,Call
    from archive_markets.http import new_session,remember_secret,scrub
    return RawCache,read_record,BulkClient,Call,new_session,remember_secret,scrub


def run(bundle,root,authorization, runtime, key=None, fake_session=None, checkpoint=lambda _:None, reconciliation=None):
    from validator import verify
    bundle=Path(bundle); runtime=Path(runtime)
    execution_context(bundle,root,runtime)
    verify(bundle,root,check_cache=True)
    if current_runtime()!=json.loads((bundle/'runtime-lock.json').read_text()): raise Halt('External runtime differs from frozen lock')
    cfg=json.loads((bundle/'protocol.json').read_text());m=json.loads((bundle/'request-manifest.json').read_text())
    probe=json.loads((bundle/'probe-spending-ledger.json').read_text())
    validate_authorization(authorization,m,root,checkout_commit(bundle))
    if fake_session is None:verify_live_hub_comment(authorization)
    validate_reconciliation(reconciliation or authorization.get('account_reconciliation'),root)
    register_runtime(runtime,root,authorization)
    ledger=Ledger(runtime,cfg,m,root,authorization,probe,reconciliation=reconciliation)
    client=None
    try:
        RawCache,read_record,BulkClient,Call,new_session,remember_secret,scrub=vendor_imports(bundle,runtime)
        # Only invoked after all offline verification and approval checks; no key during preparation.
        key=key() if callable(key) else key
        if not key or len(key)<8: raise Halt('Missing API key')
        remember_secret(key)
        session=GuardedSession(fake_session or new_session(),ledger,[r for r in m['requests'] if r['priority']==1]);session.ledger_key=key
        cache=RawCache(runtime/'data/raw')
        client=BulkClient(cache,max_credits=ledger.state['slice_cap']-ledger.reserved(),floor=cfg['budgets']['account_reserve_floor'],max_retries=0,session=session,api_key=key,rate_per_sec=4,alarm_margin=cfg['billing_reconciliation']['bulk_client_alarm_margin_credits'])
        if fake_session: client.limiter.wait=lambda:None
        ledger.checkpoint=checkpoint
        account=client.account();ledger.account(integer(account['used']),integer(account['remaining']))
        atomic(runtime/'account-baseline.json',{'reconciliation_sha256':ledger.reconciliation_sha256,'numeric_baseline':ledger.state['epoch'],'latest_free_check':ledger.state['accounts'][-1]})
        atomic(runtime/'run-manifest.json',{'account_baseline_sha256':sha(runtime/'account-baseline.json'),'bundle_root_sha256':root,'authorization_sha256':ledger.authorization_sha256,
               'reconciliation_sha256':ledger.reconciliation_sha256,'reconciliation':ledger.reconciliation,
               'execution_commit':authorization['execution_commit'],'adopted_account_baseline':ledger.state['epoch'],'interpreter_path':sys.executable,'interpreter_realpath':str(Path(sys.executable).resolve()),
               'source_sha256':json.loads((bundle/'FREEZE.json').read_text())['file_sha256'], 'runtime':current_runtime(),
               'scope':'priority 1 only; outcomes prohibited; unconditional stop before priority 2'})
        for row in m['requests']:
            if row['priority']!=1: continue
            if row['max_new_credits']==0:
                rec=read_record(bundle/row['cache_source']);validate_response(row,rec,cfg)
                ledger.state['cache_reuse'][row['request_id']]=row['cache_sha256'];ledger.save();continue
            attempt=ledger.state['attempts'].get(row['request_id'])
            call=Call('FOOTBALL_ARCHIVE_V4',row['sport'],row['source'],row['path'],tuple(sorted(row['params'].items())),
                      __import__('datetime').datetime.fromisoformat(row['requested_utc'].replace('Z','+00:00')),row['max_credits'],False,cache_sport=row['sport'])
            cached=cache.lookup(row['sport'],row['source'],row['cache_key'])
            if attempt:
                receipt=runtime/'receipts'/f"{row['request_id']}.json"
                if attempt['status']=='missing':
                    if sha(receipt)!=attempt['receipt_sha256']:raise Halt('Missing-response receipt changed')
                    if attempt.get('response_path') and sha(Path(attempt['response_path']))!=attempt['response_sha256']:raise Halt('Missing-response source changed')
                    continue
                if attempt['status']!='completed' or cached is None or sha(cached)!=attempt['response_sha256'] or sha(receipt)!=attempt['receipt_sha256']:
                    raise Halt('Completed response evidence changed or missing; no repurchase')
                continue
            if cached is not None: raise Halt('Cache has no corresponding completed attempt; inspect, never repurchase')
            if call.key!=row['cache_key']: raise Halt('Vendored cache identity differs')
            ledger.reserve(row);checkpoint('after_reservation')
            rec=client.fetch(call);checkpoint('after_transport')
            cached=cache.lookup(row['sport'],row['source'],row['cache_key'])
            if cached is None: raise Halt('Response missing from local cache')
            with cached.open('rb') as f: os.fsync(f.fileno())
            durable_directory(cached.parent);checkpoint('after_response_durability')
            ledger.complete(row,rec,cached);checkpoint('after_completion')
        ledger.state['status']='recent_complete_stopped_before_older';ledger.save()
        from coverage_report import build_report
        report=build_report(bundle,runtime,read_record)
        atomic(runtime/'coverage-report.json',report)
        return {'status':ledger.state['status'],'reserved_new_credits':ledger.reserved(),'counted_probe_and_new':1687+ledger.reserved()+ledger.state['other_usage_reserved'],'coverage_report_sha256':sha(runtime/'coverage-report.json')}
    except Exception as exc:
        # Avoid embedding secrets in the wrapper or ledger errors.
        from archive_markets.http import scrub
        ledger.halt(scrub(str(exc)))
        raise Halt(scrub(str(exc))) from None
    finally:
        if client: client.session.close()
        ledger.close()


def reconcile_cached_response(bundle,root,authorization,reconciliation,runtime):
    from validator import verify
    verify(bundle,root,check_cache=True)
    bundle,runtime=Path(bundle),Path(runtime);execution_context(bundle,root,runtime);path=runtime/'spending-ledger.json'
    validate_authorization(authorization,json.loads((bundle/'request-manifest.json').read_text()),root,checkout_commit(bundle))
    if authorization.get('status')!='approved' or reconciliation.get('status')!='approved' or reconciliation.get('bundle_root_sha256')!=root:
        raise Halt('Approved root-bound reconciliation required')
    resolution=reconciliation.get('pending_response_resolution',{})
    if not resolution.get('owner_note') or not resolution.get('response_sha256'):raise Halt('Explicit pending-response hash and owner note required')
    lock=(runtime/'acquisition.lock').open('a')
    try:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);state=json.loads(path.read_text())
        if state['bundle_root_sha256']!=root or state['authorization_sha256']!=hashlib.sha256(canonical(authorization)).hexdigest():raise Halt('Ledger approval/root mismatch')
        rid=state['pending']
        if rid is None or resolution.get('request_id')!=rid:raise Halt('Resolution must identify the pending attempt')
        row=next(r for r in json.loads((bundle/'request-manifest.json').read_text())['requests'] if r['request_id']==rid)
        files=list((runtime/'data/raw'/row['sport']/row['source']).glob('*/'+row['cache_key']+'.parquet'))
        if len(files)!=1 or sha(files[0])!=resolution['response_sha256']:raise Halt('No exact hash-pinned saved response; no resend')
        import pyarrow.parquet as pq
        record=pq.read_table(files[0]).to_pylist()[0];validate_response(row,record,json.loads((bundle/'protocol.json').read_text()))
        headers=json.loads(record['headers_json']);last=integer(headers['x-requests-last'])
        if last>row['max_new_credits']:raise Halt('Overcharge requires separate investigation')
        receipt=runtime/'receipts'/f'{rid}.json';atomic(receipt,{'request_id':rid,'record_sha256':sha(files[0]),'record':record,'offline_reconciliation':reconciliation})
        state['attempts'][rid].update(status='completed',billed_credits=last,response_path=str(files[0].resolve()),response_sha256=sha(files[0]),receipt_sha256=sha(receipt))
        # Do not erase external reservations, lower attempt reservations, or reset budgets.
        state['pending']=None;state['status']='reconciled_response_requires_approved_account_baseline'
        state['reconciliation_history'].append({'prior_ledger_sha256':sha(path),'reconciliation_sha256':hashlib.sha256(canonical(reconciliation)).hexdigest(),'reason':'offline saved-response reconciliation; no send'})
        state['stopped']='Account baseline must be reconciled before continuing'
        atomic(path,state)
        return {'status':state['status'],'new_API_calls':0,'attempt_reservation_preserved':state['attempts'][rid]['reserved_credits']}
    finally:lock.close()


def accept_as_missing(bundle,root,authorization,reconciliation,runtime):
    """Hub-approved terminal missing result; no resend, no reduced reservation."""
    from validator import verify
    verify(bundle,root,check_cache=True)
    bundle,runtime=Path(bundle),Path(runtime);execution_context(bundle,root,runtime)
    manifest=json.loads((bundle/'request-manifest.json').read_text())
    validate_authorization(authorization,manifest,root,checkout_commit(bundle))
    path=runtime/'spending-ledger.json';lock=(runtime/'acquisition.lock').open('a')
    try:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);state=json.loads(path.read_text())
        resolution=reconciliation.get('missing_response_resolution',{});rid=state['pending']
        prior=sha(path);hub=resolution.get('hub_go_ahead',{});commit=authorization['execution_commit']
        reason=resolution.get('reason');expected=(f"APPROVED missing response: root {root}, request {rid}, "
            f"ledger {prior}, commit {commit}, reason {reason}")
        if (state['bundle_root_sha256']!=root or state['authorization_sha256']!=hashlib.sha256(canonical(authorization)).hexdigest()
            or reconciliation.get('status')!='approved' or reconciliation.get('bundle_root_sha256')!=root
            or reconciliation.get('prior_ledger_sha256')!=prior or rid is None or resolution.get('request_id')!=rid
            or not resolution.get('owner_note') or hub.get('status')!='approved' or hub.get('commit')!=commit
            or not re.fullmatch(r'https://github\.com/maxzipperman/value-finder/pull/99#issuecomment-[0-9]+',hub.get('comment_url',''))
            or expected not in hub.get('comment_body','').splitlines()):
            raise Halt('Hub approval must bind missing request, reason, ledger hash and current commit')
        row=next(r for r in manifest['requests'] if r['request_id']==rid)
        attempt=state['attempts'][rid]
        if row['priority']!=1 or not row['max_new_credits'] or attempt['status']!='pending':raise Halt('Not a pending recent paid attempt')
        files=list((runtime/'data/raw'/row['sport']/row['source']).glob('*/'+row['cache_key']+'.parquet'))
        record=None;source=None;digest=None
        if len(files)>1:raise Halt('Ambiguous missing-response cache evidence')
        if files:
            import pyarrow.parquet as pq
            source=files[0];digest=sha(source)
            if resolution.get('response_sha256')!=digest:raise Halt('Missing-response source hash differs')
            record=pq.read_table(source).to_pylist()[0]
            if (record['cache_key']!=row['cache_key'] or record['sport']!=row['sport'] or record['source']!=row['source']
                or record['url']!='https://api.the-odds-api.com/v4'+row['path'] or json.loads(record['params_json'])!=row['params']):
                raise Halt('Missing-response request identity mismatch')
            if reason=='http_404':
                if record['http_status']!=404:raise Halt('Not a cached 404')
            elif reason=='snapshot_lag':
                from price_eligibility import timestamp
                if record['http_status']!=200:raise Halt('Not a lagged HTTP 200')
                try:
                    lag=(timestamp(row['requested_utc'])-timestamp(json.loads(record['body'])['timestamp'])).total_seconds()
                except (ValueError,TypeError,KeyError):raise Halt('No readable lag evidence') from None
                if lag<=json.loads((bundle/'protocol.json').read_text())['price_row_eligibility']['maximum_snapshot_lag_seconds']:
                    raise Halt('Snapshot lag not beyond the frozen limit')
            else:raise Halt('Saved response is not an approved missing category')
            headers=json.loads(record['headers_json'])
        else:
            if reason!='http_5xx' or not 500<=attempt.get('observed_http_status',0)<600:
                raise Halt('No saved response or observed 5xx evidence')
            if resolution.get('attempt_sha256')!=hashlib.sha256(canonical(attempt)).hexdigest():
                raise Halt('Uncached failure evidence hash differs')
            headers=attempt.get('observed_billing_headers',{})
        last=integer(headers.get('x-requests-last'))
        integer(headers.get('x-requests-used'));integer(headers.get('x-requests-remaining'))
        if last>row['max_new_credits'] or attempt['reserved_credits']>row['max_new_credits']:
            raise Halt('Overcharge requires investigation, not missing-response acceptance')
        receipt=runtime/'receipts'/f'{rid}.json'
        atomic(receipt,{'request_id':rid,'status':'accepted_missing','reason':reason,'response_sha256':digest,
                       'observed_billing_headers':headers,'reconciliation':reconciliation})
        attempt.update(status='missing',missing_reason=reason,billed_credits=last,response_path=str(source.resolve()) if source else None,
                       response_sha256=digest,receipt_sha256=sha(receipt))
        state['pending']=None;state['stopped']='Fresh approved account baseline required after missing-response acceptance'
        state['status']='missing_reconciled_requires_approved_account_baseline'
        state['reconciliation_history'].append({'prior_ledger_sha256':prior,'reconciliation_sha256':hashlib.sha256(canonical(reconciliation)).hexdigest(),
                                               'reason':'accepted as missing; no resend or lowered reservation'})
        atomic(path,state)
        return {'status':state['status'],'new_API_calls':0,'request_id':rid,'reservation_preserved':attempt['reserved_credits']}
    finally:lock.close()


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--root',required=True);parser.add_argument('--confirm',action='store_true')
    parser.add_argument('--authorization');parser.add_argument('--key-file');parser.add_argument('--reconciliation');parser.add_argument('--reconcile-only',action='store_true');parser.add_argument('--accept-missing',action='store_true');a=parser.parse_args()
    bundle=Path(__file__).resolve().parent
    from validator import verify
    result=verify(bundle,a.root,check_cache=True)
    if a.reconcile_only or a.accept_missing:
        if not a.authorization or not a.reconciliation:raise SystemExit('Approved authorization and reconciliation required')
        authorization=json.loads(Path(a.authorization).read_text());reconciliation=json.loads(Path(a.reconciliation).read_text())
        verify_live_hub_comment(authorization)
        if a.accept_missing:verify_live_hub_comment({'hub_go_ahead':reconciliation['missing_response_resolution']['hub_go_ahead']})
        operation=accept_as_missing if a.accept_missing else reconcile_cached_response
        print(json.dumps(operation(bundle,a.root,authorization,reconciliation,runtime_path(a.root)),indent=2));return
    if not a.confirm:
        print(json.dumps({'status':'offline preflight; no credential reads or API calls',**result},indent=2));return
    if not a.authorization or not a.key_file or not a.reconciliation: raise SystemExit('Separate exact authorization, account reconciliation and key-file required')
    authorization=json.loads(Path(a.authorization).read_text())
    runtime=runtime_path(a.root)  # outside every checkout; fixed by root
    if Path(a.key_file).resolve().is_relative_to(bundle): raise SystemExit('Credentials cannot be placed in immutable bundle')
    def key():
        from dotenv import dotenv_values
        return dotenv_values(a.key_file).get('ODDS_API_KEY')
    print(json.dumps(run(bundle,a.root,authorization,runtime,key=key,reconciliation=json.loads(Path(a.reconciliation).read_text())),indent=2))


if __name__=='__main__':
    sys.dont_write_bytecode=True
    try: main()
    except Halt as exc: raise SystemExit('HALTED: '+str(exc)) from None
