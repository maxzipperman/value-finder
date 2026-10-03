"""Synthetic only: temporary ledgers, fake sessions, actual guard and transport functions."""
import ast
import concurrent.futures
import importlib.util
import json
import multiprocessing
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from datetime import datetime, timedelta, timezone

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('guard', ROOT / 'ops/collector_guard.py')
g = importlib.util.module_from_spec(spec)
spec.loader.exec_module(g)
KEY = 'SYNTHETIC_KEY_ONLY'
URL = 'https://api.the-odds-api.com/v4/sports/basketball_nba/odds'
PARAMS = dict(bookmakers='pinnacle,lowvig,betonlineag', markets='h2h', oddsFormat='decimal', dateFormat='iso')


class Session:
    def __init__(self, *, status=200, headers=None, failure=None, retries=0):
        self.calls = []
        self.status, self.failure, self.retries = status, failure, retries
        self.headers = headers if headers is not None else {'x-requests-last': '1', 'x-requests-used': '101', 'x-requests-remaining': '899'}

    def get_adapter(self, url):
        return SimpleNamespace(max_retries=SimpleNamespace(total=self.retries))

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if self.failure:
            raise self.failure
        return SimpleNamespace(status_code=self.status, headers=self.headers, text='["' + KEY + '"]')


class GuardTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.ledger = self.root/'shared.json'
        self.config = self.root/'envelope.json'
        now = datetime.now(timezone.utc)
        self.c = dict(version=1, source_sha='a'*40, approval='SYNTHETIC TEST ONLY', month=now.strftime('%Y-%m'),
                      valid_until_utc=(now + timedelta(hours=1)).isoformat(), account_fingerprint=g.digest(KEY.encode())[:12],
                      account_ceiling=900, plan_credits=1000, reserve_floor=100, ledger=str(self.ledger),
                      shared_writers=['synthetic-foreground', 'synthetic-collectors'], collectors={
                          name: dict(cap=20, path_pattern=r'/v4/sports/basketball_nba/odds', params=PARAMS)
                          for name in g.LABELS})
        self.bind()
        self.ledger.write_text(json.dumps(dict(version=1, envelope_sha256=self.identity, baseline_used=100,
                                              external_reserved=0, external_state='ready', attempts={})))
        self.ledger.with_suffix('.json.lock').touch()
        self.env = patch.dict(os.environ, VF_COLLECTOR_ENVELOPE=str(self.config), VF_COLLECTOR_ENVELOPE_SHA256=self.identity)
        self.env.start()
        self.sha = patch.object(g, 'source_sha', return_value='a'*40)
        self.sha.start()
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(self.env.stop)
        self.addCleanup(self.sha.stop)

    def bind(self):
        self.config.write_text(json.dumps(self.c))
        self.identity = g.digest(self.config.read_bytes())
        os.environ['VF_COLLECTOR_ENVELOPE_SHA256'] = self.identity

    def send(self, session=None, slot='slot1', label='nba', **kwargs):
        return g.paid_get(session or Session(), URL, {**PARAMS, 'apiKey':KEY}, label=label, request_slot=slot, **kwargs)

    def state(self):
        return json.loads(self.ledger.read_text())

    def test_reserves_before_send_and_stores_sanitized_receipt(self):
        s = Session()
        original = s.get
        def get(*a, **kw):
            attempt = next(iter(self.state()['attempts'].values()))
            self.assertEqual((attempt['state'], attempt['reserved']), ('pending',1))
            self.assertFalse(kw['allow_redirects'])
            return original(*a, **kw)
        s.get = get
        r = self.send(s)
        self.assertEqual(r.json(), ['REDACTED'])
        self.assertEqual(next(iter(self.state()['attempts'].values()))['state'],'complete')
        self.assertNotIn(KEY, ''.join(p.read_text() for p in self.root.glob('*.json') if p != self.config))

    def test_props_nine_market_upper_bound_is_reserved_before_transport(self):
        params={**PARAMS,'markets':','.join('market'+str(i) for i in range(9)),
                'bookmakers':','.join('book'+str(i) for i in range(10))}
        url='https://api.the-odds-api.com/v4/sports/americanfootball_nfl/events/synthetic/odds'
        self.c['collectors']['nfl-props'].update(params=params,path_pattern=r'/v4/sports/americanfootball_nfl/events/[^/]+/odds')
        self.bind();state=self.state();state['envelope_sha256']=self.identity;self.ledger.write_text(json.dumps(state))
        s=Session();original=s.get
        def get(*a,**kw):
            self.assertEqual(next(iter(self.state()['attempts'].values()))['reserved'],9)
            return original(*a,**kw)
        s.get=get
        g.paid_get(s,url,{**params,'apiKey':KEY},label='nfl-props',request_slot='synthetic:24')
        self.assertEqual(next(iter(self.state()['attempts'].values()))['reserved'],9)

    def test_provider_warning_redacts_key(self):
        import logging
        self.send()
        record=logging.LogRecord('urllib3.connection',logging.WARNING,'',0,'URL apiKey=%s',(KEY,),None)
        self.assertTrue(g.SecretFilter().filter(record))
        self.assertNotIn(KEY,record.getMessage())

    def test_duplicate_complete_is_not_resent(self):
        s=Session(); self.send(s)
        with self.assertRaises(g.Blocked): self.send(s)
        self.assertEqual(len(s.calls),1)

    def test_timeout_halts_even_different_slots_and_retains_reservation(self):
        s=Session(failure=TimeoutError('url apiKey='+KEY))
        with self.assertRaises(g.Blocked) as e: self.send(s)
        self.assertNotIn(KEY,str(e.exception))
        with self.assertRaises(g.Blocked): self.send(s,slot='slot2')
        self.assertEqual(len(s.calls),1)
        self.assertEqual(next(iter(self.state()['attempts'].values()))['reserved'],1)

    def test_process_death_after_reservation_is_restart_safe(self):
        ctx=multiprocessing.get_context('fork')
        s=Session()
        s.get=lambda *a,**kw: os._exit(17)
        p=ctx.Process(target=lambda: self.send(s));p.start();p.join(10)
        self.assertEqual(p.exitcode,17)
        with self.assertRaises(g.Blocked): self.send(slot='after-crash')
        self.assertEqual(next(iter(self.state()['attempts'].values()))['state'],'pending')

    def test_disk_failures_before_send_after_response_and_at_terminal_write(self):
        for fail_at in (1,2,3):
            with self.subTest(fail_at=fail_at):
                self.ledger.write_text(json.dumps(dict(version=1,envelope_sha256=self.identity,baseline_used=100,external_reserved=0,external_state='ready',attempts={})))
                original=g.atomic_json; calls=[]; s=Session()
                def write(*a):
                    calls.append(a)
                    if len(calls)==fail_at: raise OSError('synthetic disk failure')
                    return original(*a)
                with patch.object(g,'atomic_json',side_effect=write),self.assertRaises(OSError):self.send(s)
                self.assertEqual(len(s.calls),int(fail_at>1))
                if fail_at>1:
                    with self.assertRaises(g.Blocked):self.send(s,slot='restart')
                    self.assertEqual(len(s.calls),1)

    def test_bad_status_headers_and_untracked_account_usage_halt(self):
        cases=[dict(status=k) for k in (302,401,429,500)] + [dict(headers=h) for h in (
            {}, {'x-requests-last':'1.0'}, {'x-requests-last':'2','x-requests-used':'102','x-requests-remaining':'898'},
            {'x-requests-last':'1','x-requests-used':'110','x-requests-remaining':'890'},
            {'x-requests-last':'1','x-requests-used':'101','x-requests-remaining':'1'})]
        for i,kw in enumerate(cases):
            with self.subTest(kw=kw):
                self.ledger.write_text(json.dumps(dict(version=1,envelope_sha256=self.identity,baseline_used=100,external_reserved=0,external_state='ready',attempts={})))
                s=Session(**kw)
                with self.assertRaises(g.Blocked):self.send(s,slot=str(i))
                with self.assertRaises(g.Blocked):self.send(s,slot='next')
                self.assertEqual(len(s.calls),1)

    def test_missing_authority_ledger_lock_wrong_source_and_request_do_not_send(self):
        s=Session()
        with patch.dict(os.environ,VF_COLLECTOR_ENVELOPE_SHA256=''):
            with self.assertRaises(g.Blocked):self.send(s)
        with patch.object(g,'source_sha',return_value='b'*40):
            with self.assertRaises(g.Blocked):self.send(s)
        self.ledger.unlink()
        with self.assertRaises(g.Blocked):self.send(s)
        self.assertEqual(s.calls,[])

    def test_transport_retries_and_scope_change_are_rejected(self):
        s=Session(retries=2)
        with self.assertRaises(g.Blocked):self.send(s)
        s=Session()
        with self.assertRaises(g.Blocked):g.paid_get(s,URL,{**PARAMS,'apiKey':KEY,'markets':'totals'},label='nba',request_slot='x')
        self.assertEqual(s.calls,[])

    def test_concurrency_same_slot_sends_once(self):
        s=Session()
        def run(_):
            try:self.send(s);return 'sent'
            except g.Blocked:return 'blocked'
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:out=list(ex.map(run,range(8)))
        self.assertEqual(out.count('sent'),1)
        self.assertEqual(len(s.calls),1)

    def test_shared_ceiling_with_external_reservations_and_concurrent_collectors(self):
        state=self.state();state['external_reserved']=799;self.ledger.write_text(json.dumps(state))
        s=Session(headers={'x-requests-last':'1','x-requests-used':'900','x-requests-remaining':'100'})
        def run(label):
            try:self.send(s,label=label);return 'sent'
            except g.Blocked:return 'blocked'
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:out=list(ex.map(run,sorted(g.LABELS)))
        self.assertEqual(out.count('sent'),1);self.assertEqual(len(s.calls),1)

    def test_external_writer_pending_is_a_shared_halt(self):
        state=self.state();state['external_state']='pending';self.ledger.write_text(json.dumps(state))
        s=Session()
        with self.assertRaises(g.Blocked):self.send(s)
        self.assertEqual(s.calls,[])

    def test_collector_cap_checked_before_send(self):
        self.c['collectors']['nba']['cap']=1;self.bind()
        state=self.state();state['envelope_sha256']=self.identity;self.ledger.write_text(json.dumps(state))
        self.send()
        s=Session()
        with self.assertRaises(g.Blocked):self.send(s,slot='2')
        self.assertEqual(s.calls,[])

    def test_receipt_corruption_halts(self):
        self.send(); next(self.root.glob('*.receipt.json')).write_text('tampered')
        s=Session()
        with self.assertRaises(g.Blocked):self.send(s,slot='next')
        self.assertEqual(s.calls,[])

    def test_revocation_while_waiting_for_lock_does_not_send(self):
        # Second validation is the admission linearization point.
        original=g.envelope;count=[]
        def check(now):
            count.append(1)
            if len(count)==2:raise g.Blocked('revoked')
            return original(now)
        s=Session()
        with patch.object(g,'envelope',side_effect=check),self.assertRaises(g.Blocked):self.send(s)
        self.assertEqual(s.calls,[])


class IntegrationTests(unittest.TestCase):
    def extract(self,path,name,ns):
        tree=ast.parse((ROOT/path).read_text())
        node=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name==name)
        exec(compile(ast.Module(body=[node],type_ignores=[]),str(path),'exec'),ns)
        return ns[name]

    def test_actual_nba_paid_transport_uses_guard_and_free_transport_zero_retry_redirect(self):
        calls=[]
        response=SimpleNamespace(status_code=200,headers={},text='[]')
        def guarded(*a,**kw):calls.append(('guard',kw));return response
        def http(*a,**kw):calls.append(('http',kw));return response
        f=self.extract(Path('sharp-markets/src/markets/collector.py'),'_odds_get',{'paid_get':guarded,'http_get':http,'ODDS_BASE':'https://api.the-odds-api.com/v4'})
        self_=SimpleNamespace(key=KEY,odds=Session(),limiter=None)
        f(self_,'/sports/basketball_nba/odds',PARAMS,request_slot='stable')
        f(self_,'/sports/basketball_nba/events',{})
        self.assertEqual(calls,[('guard',{'label':'nba','request_slot':'stable'}),('http',{'max_retries':0,'allow_redirects':False})])

    def test_actual_nfl_get_uses_guard_only_when_explicit_collector(self):
        calls=[];s=Session()
        def guard(*a,**kw):calls.append(kw);return SimpleNamespace(status_code=200,ok=True)
        f=self.extract(Path('nfl-weather/nflweather/oddsapi.py'),'_get',dict(paid_get=guard,session=s,BASE='https://api.the-odds-api.com/v4',api_key=lambda:KEY,quota=SimpleNamespace(record=lambda *a:None),Blocked=g.Blocked,OddsAPIUnavailable=SystemExit,requests=SimpleNamespace(RequestException=ConnectionError)))
        f('/sports/americanfootball_nfl/events/id/odds',PARAMS,collector_label='nfl-props',request_slot='id:24')
        self.assertEqual(calls,[{'label':'nfl-props','request_slot':'id:24'}]);self.assertEqual(s.calls,[])

    def test_actual_cfb_path_routes_to_guard_and_surfaces_block(self):
        tree=ast.parse((ROOT/'cfb-weather/cfbweather/live.py').read_text())
        node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='live_totals')
        class NoImports(ast.NodeTransformer):
            def visit_Import(self,n):return None
            def visit_ImportFrom(self,n):return None
        node=NoImports().visit(node);calls=[]
        def guard(*a,**kw):calls.append(kw);raise g.Blocked('missing authority')
        ns=dict(pd=SimpleNamespace(DataFrame=object),quota=SimpleNamespace(check=lambda:None),ROOT=ROOT,
                RAW=ROOT/'synthetic-unused',sys=SimpleNamespace(path=[]),_env=lambda k:KEY,
                paid_get=guard,Blocked=g.Blocked,slot=g.slot,datetime=datetime,timezone=timezone,
                LIVE_BOOKS=['pinnacle'],ODDS_API='https://api.the-odds-api.com/v4/sports/americanfootball_ncaaf/odds',
                session=Session(),requests=SimpleNamespace(RequestException=ConnectionError))
        exec(compile(ast.Module(body=[node],type_ignores=[]),'cfb-live','exec'),ns)
        self.assertEqual(ns['live_totals']({}),'missing authority')
        self.assertEqual(calls[0]['label'],'cfb-trigger')

    def test_actual_nba_tick_kernel_lock_excludes_overlapping_owner(self):
        import fcntl
        import threading
        with tempfile.TemporaryDirectory() as td:
            started,release=threading.Event(),threading.Event()
            def schedule(now):started.set();release.wait(5);return []
            obj=SimpleNamespace(c={'start':datetime.now(timezone.utc).date(),'every_min':5},dir=Path(td),
                                _state=lambda:{},schedule=schedule,windows=lambda e,n:(0,False),
                                _heartbeat=lambda row,state,now:row)
            f=self.extract(Path('sharp-markets/src/markets/collector.py'),'tick',
                           dict(datetime=datetime,timezone=timezone,utcnow=lambda:datetime.now(timezone.utc),
                                fcntl=fcntl,parse_ts=lambda x:None,timedelta=timedelta,scrub=str))
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
                first=ex.submit(f,obj)
                self.assertTrue(started.wait(5))
                self.assertIsNone(f(obj))
                release.set();self.assertEqual(first.result()['action'],'idle')
            self.assertTrue((Path(td)/'tick.lock').exists())

    def test_named_paths_stable_slots_and_kernel_lock_are_connected(self):
        sources={p:(ROOT/p).read_text() for p in ('nfl-weather/scripts/log_props.py','nfl-weather/nflweather/oddsapi.py','cfb-weather/cfbweather/live.py','sharp-markets/src/markets/collector.py')}
        self.assertIn('collector_label="nfl-props", request_slot=f"{ev[\'id\']}:{h}"',sources['nfl-weather/scripts/log_props.py'])
        self.assertIn('if tag == "poll" else {}',sources['nfl-weather/nflweather/oddsapi.py'])
        self.assertIn('label="cfb-trigger", request_slot=slot',sources['cfb-weather/cfbweather/live.py'])
        self.assertIn('fcntl.LOCK_EX | fcntl.LOCK_NB',sources['sharp-markets/src/markets/collector.py'])
        self.assertNotIn('lock.unlink',sources['sharp-markets/src/markets/collector.py'])


if __name__=='__main__':unittest.main()
