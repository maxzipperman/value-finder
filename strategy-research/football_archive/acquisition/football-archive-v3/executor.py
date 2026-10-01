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


class Ledger:
    """Reservations persist at their upper bound even when a response costs less."""
    def __init__(self, folder, protocol, manifest, root, authorization, probe):
        self.folder = Path(folder); self.folder.mkdir(parents=True,exist_ok=True)
        self.path = self.folder/'spending-ledger.json'
        self.protocol, self.manifest, self.root = protocol, manifest, root
        cap = manifest['new_credits_by_priority']['1']
        if (authorization.get('bundle_root_sha256') != root or authorization.get('priority') != 1
            or authorization.get('max_new_credits') != cap or not authorization.get('human_authorization_evidence')):
            raise Halt('Missing exact recent-slice authorization')
        if probe.get('pending') or probe.get('stopped') or sum(a['counted_credits'] for a in probe['attempts']) != 1687 or probe['reserved_credits'] != 1687:
            raise Halt('Probe accounting cannot be seeded')
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
                              'provider_used':1687,'provider_remaining':4998313,
                              'other_usage_reserved':0,'status':'prepared'}
                atomic(marker,{'bundle_root_sha256':root,'probe_credits':1687})
                self.save()
            self.validate_state()
            if self.state['pending'] or self.state['stopped']: raise Halt('Unresolved/stopped ledger requires documented reconciliation; never automatically resend')
        except BaseException:
            self.lock.close(); raise

    def validate_state(self):
        allowed = {r['request_id']:r for r in self.manifest['requests'] if r['priority']==1 and r['max_new_credits']}
        if self.state['probe_credits'] != 1687 or self.state['slice_cap'] != self.manifest['new_credits_by_priority']['1']:
            raise Halt('Ledger budget baseline changed')
        for rid, a in self.state['attempts'].items():
            if rid not in allowed or a['reserved_credits'] < allowed[rid]['max_new_credits']:
                raise Halt('Attempt differs from authorized allowlist')
        if self.state['pending'] and self.state['pending'] not in self.state['attempts']:
            raise Halt('Pending attempt missing from ledger')
        self.budget_check(0)

    def close(self): self.lock.close()
    def save(self): atomic(self.path,self.state)
    def halt(self, reason):
        self.state['stopped']=reason; self.state['status']='halted'; self.save()
    def reserved(self): return sum(a['reserved_credits'] for a in self.state['attempts'].values())
    def budget_check(self, extra):
        budgets = self.protocol['budgets']; total=self.state['probe_credits']+self.state['other_usage_reserved']+self.reserved()+extra
        if self.reserved()+extra > self.state['slice_cap']: raise Halt('Recent-slice credit ceiling')
        for name in ('first_tranche_cumulative_credits','day_one_cumulative_ceiling','broader_cumulative_ceiling'):
            if total > budgets[name]: raise Halt('Cumulative budget exceeded: '+name)
        if self.state['provider_remaining']-extra < budgets['account_reserve_floor']: raise Halt('Account reserve floor')

    def account(self, used, remaining):
        if type(used) is not int or type(remaining) is not int or min(used,remaining)<0:
            raise Halt('Unreadable account billing')
        if used != self.state['provider_used'] or remaining != self.state['provider_remaining']:
            raise Halt('Provider reset or other key usage requires documented reconciliation; local budgets do not reset')
        self.budget_check(0)
        self.state['accounts'].append({'used':used,'remaining':remaining,'utc':datetime.now(timezone.utc).isoformat()})
        self.save()

    def reserve(self,row):
        allowed = next((r for r in self.manifest['requests'] if r['request_id']==row.get('request_id')),None)
        if allowed != row or row['priority']!=1 or row['max_new_credits']==0: raise Halt('Outside authorized paid allowlist')
        if self.state['pending'] or self.state['stopped']: raise Halt('Unresolved/stopped attempt')
        if row['request_id'] in self.state['attempts']: raise Halt('Never resend an existing attempt')
        self.budget_check(row['max_new_credits'])
        self.state['attempts'][row['request_id']]={'reserved_credits':row['max_new_credits'],'status':'pending','cache_key':row['cache_key']}
        self.state['pending']=row['request_id']; self.state['status']='running'; self.save()

    def observe_headers(self,headers):
        rid=self.state['pending']
        safe={k:headers.get(k) for k in ('x-requests-last','x-requests-used','x-requests-remaining')}
        a=self.state['attempts'][rid];a['observed_billing_headers']=safe
        try:
            last=integer(safe['x-requests-last']);used=integer(safe['x-requests-used']);left=integer(safe['x-requests-remaining'])
            a['reserved_credits']=max(a['reserved_credits'],last)
            external=max(0,used-self.state['provider_used']-last,self.state['provider_remaining']-left-last)
            self.state['other_usage_reserved']=max(self.state['other_usage_reserved'],external)
        except Halt:
            pass  # Unreadable billing stays conservatively reserved and unresolved.
        self.save()

    def complete(self,row,record,path):
        if self.state['pending'] != row['request_id']: raise Halt('Response has no durable reservation')
        validate_response(row,record,self.protocol)
        headers=json.loads(record['headers_json']); last=integer(headers.get('x-requests-last')); used=integer(headers.get('x-requests-used')); remaining=integer(headers.get('x-requests-remaining'))
        if last>row['max_new_credits'] or used-self.state['provider_used'] != last or self.state['provider_remaining']-remaining != last:
            raise Halt('Unreconciled billing, reset or other key usage')
        if remaining < self.protocol['budgets']['account_reserve_floor']: raise Halt('Account reserve breached')
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
            self.ledger.observe_headers(response.headers)
        elif integer(response.headers.get('x-requests-last')) != 0:
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


def run(bundle,root,authorization, runtime, key=None, fake_session=None, checkpoint=lambda _:None):
    from validator import verify
    bundle=Path(bundle); runtime=Path(runtime)
    verify(bundle,root,check_cache=True)
    if current_runtime()!=json.loads((bundle/'runtime-lock.json').read_text()): raise Halt('External runtime differs from frozen lock')
    cfg=json.loads((bundle/'protocol.json').read_text());m=json.loads((bundle/'request-manifest.json').read_text())
    probe=json.loads((bundle/'probe-spending-ledger.json').read_text())
    ledger=Ledger(runtime,cfg,m,root,authorization,probe)
    client=None
    try:
        RawCache,read_record,BulkClient,Call,new_session,remember_secret,scrub=vendor_imports(bundle,runtime)
        # Only invoked after all offline verification and approval checks; no key during preparation.
        key=key() if callable(key) else key
        if not key or len(key)<8: raise Halt('Missing API key')
        remember_secret(key)
        session=GuardedSession(fake_session or new_session(),ledger,[r for r in m['requests'] if r['priority']==1]);session.ledger_key=key
        cache=RawCache(runtime/'data/raw')
        client=BulkClient(cache,max_credits=ledger.state['slice_cap']-ledger.reserved(),floor=cfg['budgets']['account_reserve_floor'],max_retries=0,session=session,api_key=key,rate_per_sec=4,alarm_margin=0)
        if fake_session: client.limiter.wait=lambda:None
        ledger.checkpoint=checkpoint
        account=client.account();ledger.account(integer(account['used']),integer(account['remaining']))
        atomic(runtime/'run-manifest.json',{'bundle_root_sha256':root,'authorization_sha256':ledger.authorization_sha256,
               'source_sha256':json.loads((bundle/'FREEZE.json').read_text())['file_sha256'], 'runtime':current_runtime(),
               'scope':'priority 1 only; outcomes prohibited; unconditional stop before priority 2'})
        for row in m['requests']:
            if row['priority']!=1: continue
            if row['max_new_credits']==0:
                rec=read_record(bundle/row['cache_source']);validate_response(row,rec,cfg)
                ledger.state['cache_reuse'][row['request_id']]=row['cache_sha256'];ledger.save();continue
            attempt=ledger.state['attempts'].get(row['request_id'])
            call=Call('FOOTBALL_ARCHIVE_V3',row['sport'],row['source'],row['path'],tuple(sorted(row['params'].items())),
                      __import__('datetime').datetime.fromisoformat(row['requested_utc'].replace('Z','+00:00')),row['max_credits'],False,cache_sport=row['sport'])
            cached=cache.lookup(row['sport'],row['source'],row['cache_key'])
            if attempt:
                receipt=runtime/'receipts'/f"{row['request_id']}.json"
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


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--root',required=True);parser.add_argument('--confirm',action='store_true')
    parser.add_argument('--authorization');parser.add_argument('--key-file');a=parser.parse_args()
    bundle=Path(__file__).resolve().parent
    from validator import verify
    result=verify(bundle,a.root,check_cache=True)
    if not a.confirm:
        print(json.dumps({'status':'offline preflight; no credential reads or API calls',**result},indent=2));return
    if not a.authorization or not a.key_file: raise SystemExit('Separate exact authorization and key-file required')
    authorization=json.loads(Path(a.authorization).read_text())
    runtime=bundle.parent/'football-acquisition-runtime'  # stable across restarts; no alternate live ledger
    if Path(a.key_file).resolve().is_relative_to(bundle): raise SystemExit('Credentials cannot be placed in immutable bundle')
    def key():
        from dotenv import dotenv_values
        return dotenv_values(a.key_file).get('ODDS_API_KEY')
    print(json.dumps(run(bundle,a.root,authorization,runtime,key=key),indent=2))


if __name__=='__main__':
    sys.dont_write_bytecode=True
    try: main()
    except Halt as exc: raise SystemExit('HALTED: '+str(exc)) from None
