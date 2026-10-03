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
        self.root = Path(self.tmp.name).resolve()
        self.ledger = self.root/'shared.json'
        self.config = self.root/'envelope.json'
        now = datetime.now(timezone.utc)
        self.c = dict(version=2, source_sha='a'*40, approval='SYNTHETIC TEST ONLY', month=now.strftime('%Y-%m'),
                      valid_until_utc=(now + timedelta(hours=1)).isoformat(), account_fingerprint=g.digest(KEY.encode())[:12],
                      account_ceiling=900, plan_credits=1000, reserve_floor=100, ledger=str(self.ledger),
                      shared_writers=sorted(g.LABELS), roles={
                          name: dict(cap=20, path_pattern=g.ROLE_PATHS[name], params=PARAMS)
                          for name in g.LABELS})
        self.bind()
        self.ledger.write_text(json.dumps(dict(version=2, envelope_sha256=self.identity, baseline_used=100,
                                              external_reserved=0, external_state='ready', attempts={})))
        self.ledger.with_suffix('.json.lock').touch()
        self.env = patch.dict(os.environ, VF_COLLECTOR_ENVELOPE=str(self.config), VF_COLLECTOR_ENVELOPE_SHA256=self.identity)
        self.env.start()
        self.sha = patch.object(g, 'source_sha', return_value='a'*40)
        self.sha.start()
        self.canonical = patch.object(g, 'ACCOUNT_LEDGER', self.ledger)
        self.canonical.start()
        self.addCleanup(self.canonical.stop)
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(self.env.stop)
        self.addCleanup(self.sha.stop)

    def bind(self):
        self.config.write_text(json.dumps(self.c))
        self.identity = g.digest(self.config.read_bytes())
        os.environ['VF_COLLECTOR_ENVELOPE_SHA256'] = self.identity

    def send(self, session=None, slot='slot1', label='nba', **kwargs):
        if label in {'nfl-alert','cfb-alert'}:
            from ops.shared_account_testkit import synthetic_current_occurrence
            slot=synthetic_current_occurrence()
        url = ('https://api.the-odds-api.com' + g.ROLE_PATHS[label].replace('[^/]+', 'synthetic'))
        return g._reservation_get(session or Session(), url, {**PARAMS, 'apiKey':KEY}, label=label, request_slot=slot, **kwargs)

    def state(self):
        return json.loads(self.ledger.read_text())

    def test_populated_configuration_cannot_enable_unintegrated_production(self):
        # Reviewer's reproduction: one unaccounted legacy credit already spent;
        # baseline100, cap101, external0/ready and a writer inventory aren't a bridge.
        self.c['account_ceiling']=101
        self.c['shared_writers']=['legacy-writer-with-no-bridge']
        self.bind();state=self.state();state['envelope_sha256']=self.identity;self.ledger.write_text(json.dumps(state))
        s=Session(headers={'x-requests-last':'1','x-requests-used':'102','x-requests-remaining':'898'})
        with self.assertRaises(g.Blocked):g.paid_get(s,URL,{**PARAMS,'apiKey':KEY},label='nba',request_slot='legacy-overlap')
        with self.assertRaises(g.Blocked):g.require_bridge()  # same install admission
        self.assertEqual(s.calls,[])
        self.assertEqual(self.state()['attempts'],{})

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
        self.c['roles']['nfl-props'].update(params=params,path_pattern=r'/v4/sports/americanfootball_nfl/events/[^/]+/odds')
        self.bind();state=self.state();state['envelope_sha256']=self.identity;self.ledger.write_text(json.dumps(state))
        s=Session();original=s.get
        def get(*a,**kw):
            self.assertEqual(next(iter(self.state()['attempts'].values()))['reserved'],9)
            return original(*a,**kw)
        s.get=get
        g._reservation_get(s,url,{**params,'apiKey':KEY},label='nfl-props',request_slot='synthetic:24')
        self.assertEqual(next(iter(self.state()['attempts'].values()))['reserved'],9)

    def test_provider_warning_redacts_key(self):
        import logging
        self.send()
        record=logging.LogRecord('urllib3.connection',logging.WARNING,'',0,'URL apiKey=%s',(KEY,),None)
        self.assertTrue(g.SecretFilter().filter(record))
        self.assertNotIn(KEY,record.getMessage())

    def test_duplicate_complete_reuses_original_receipt_without_resend(self):
        s=Session(); first=self.send(s)
        replay=self.send(s)
        self.assertEqual(first.observed_utc,replay.observed_utc)
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
                self.ledger.write_text(json.dumps(dict(version=2,envelope_sha256=self.identity,baseline_used=100,external_reserved=0,external_state='ready',attempts={})))
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
                self.ledger.write_text(json.dumps(dict(version=2,envelope_sha256=self.identity,baseline_used=100,external_reserved=0,external_state='ready',attempts={})))
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
        with self.assertRaises(g.Blocked):g._reservation_get(s,URL,{**PARAMS,'apiKey':KEY,'markets':'totals'},label='nba',request_slot='x')
        self.assertEqual(s.calls,[])

    def test_concurrency_same_slot_sends_once(self):
        s=Session()
        def run(_):
            try:self.send(s);return 'sent'
            except g.Blocked:return 'blocked'
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:out=list(ex.map(run,range(8)))
        self.assertEqual(out.count('sent'),8)  # seven callers reuse the saved receipt
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
        self.c['roles']['nba']['cap']=1;self.bind()
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


    def test_all_eight_roles_use_one_journal_and_foreign_role_path_is_denied(self):
        for i, label in enumerate(sorted(g.LABELS)):
            self.send(Session(headers={'x-requests-last':'1', 'x-requests-used':str(101+i),
                                       'x-requests-remaining':str(899-i)}),label=label)
        self.assertEqual(set(a['label'] for a in self.state()['attempts'].values()),g.LABELS)
        s=Session()
        with self.assertRaises(g.Blocked):
            g._reservation_get(s,URL,{**PARAMS,'apiKey':KEY},label='nfl-alert',request_slot='x')
        self.assertEqual(s.calls,[])

    def test_concurrent_alert_close_collectors_compete_for_last_credit(self):
        self.c['account_ceiling']=101;self.bind()
        state=self.state();state['envelope_sha256']=self.identity;self.ledger.write_text(json.dumps(state))
        s=Session()
        def run(label):
            try:self.send(s,label=label);return 'sent'
            except g.Blocked:return 'blocked'
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
            out=list(ex.map(run,sorted(g.LABELS)))
        self.assertEqual(out.count('sent'),1)
        self.assertEqual(len(s.calls),1)
        self.assertEqual(sum(a['reserved'] for a in self.state()['attempts'].values()),1)

    def test_month_source_or_new_envelope_cannot_implicitly_reset_ledger(self):
        self.send()
        before=self.ledger.read_bytes();s=Session()
        for field,value in [('month','2000-01'),('source_sha','b'*40),('approval','replacement authority')]:
            original=self.c[field];self.c[field]=value;self.bind()
            with self.assertRaises(g.Blocked):self.send(s,slot='new')
            self.assertEqual(self.ledger.read_bytes(),before)
            self.c[field]=original;self.bind()
        self.assertEqual(s.calls,[])

    def test_noncanonical_ledger_and_symlink_lock_reject_before_send(self):
        s=Session();self.c['ledger']=str(self.root/'another.json');self.bind()
        with self.assertRaises(g.Blocked):self.send(s)
        self.c['ledger']=str(self.ledger);self.bind()
        lock=self.ledger.with_suffix('.json.lock');lock.unlink()
        other=self.root/'other.lock';other.touch();lock.symlink_to(other)
        with self.assertRaises(g.Blocked):self.send(s)
        self.assertEqual(s.calls,[])

    def test_close_observation_replay_then_next_tick_and_uncertain_halt(self):
        t=datetime.now(timezone.utc).replace(second=0,microsecond=0)
        kicks=['synthetic-kickoff'];tries={}
        a=g.close_slot(kicks,tries,t);b=g.close_slot(kicks,tries,t+timedelta(minutes=15))
        self.assertNotEqual(a,b)
        self.assertEqual(a,g.close_slot(['newly-due'],{'newly-due':1},t+timedelta(seconds=1)))
        s=Session();self.send(s,label='nfl-close',slot=a);self.send(s,label='nfl-close',slot=a)
        self.send(s,label='nfl-close',slot=b)
        self.assertEqual(len(s.calls),2)  # planned observation, no automatic resend
        failed=Session(failure=TimeoutError())
        with self.assertRaises(g.Blocked):self.send(failed,label='cfb-close',slot=a)
        with self.assertRaises(g.Blocked):self.send(failed,label='cfb-close',slot=b)
        self.assertEqual(len(failed.calls),1)

    def test_complete_identity_conflict_is_not_a_cache_hit(self):
        self.send();s=Session()
        # A changed public request cannot reuse an existing slot even when newly
        # authorized scope is injected for this adverse-path synthetic test.
        original=g.envelope
        def changed(now):
            c,identity=original(now)
            c['roles']['nba']['params']={**PARAMS,'markets':'totals'}
            return c,identity
        with patch.object(g,'envelope',side_effect=changed),self.assertRaises(g.Blocked):
            g._reservation_get(s,URL,{**PARAMS,'markets':'totals','apiKey':KEY},label='nba',request_slot='slot1')
        self.assertEqual(s.calls,[])


    def test_actual_lock_wait_revalidates_revoked_authority(self):
        import fcntl
        import threading
        entered=threading.Event();original=g.envelope
        def checked(now):
            result=original(now);entered.set();return result
        s=Session()
        def waiting():
            try:self.send(s);return 'sent'
            except g.Blocked:return 'blocked'
        with self.ledger.with_suffix('.json.lock').open('r+') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX)
            with patch.object(g,'envelope',side_effect=checked), concurrent.futures.ThreadPoolExecutor() as ex:
                future=ex.submit(waiting)
                try:
                    self.assertTrue(entered.wait(5))
                    self.config.write_text('revoked synthetic authority')
                finally:fcntl.flock(lock,fcntl.LOCK_UN)
                self.assertEqual(future.result(timeout=5),'blocked')
        self.assertEqual(s.calls,[])


    def test_cross_process_roles_respect_single_last_credit(self):
        self.c['account_ceiling']=101;self.bind()
        state=self.state();state['envelope_sha256']=self.identity;self.ledger.write_text(json.dumps(state))
        ctx=multiprocessing.get_context('fork');queue=ctx.Queue()
        def worker(label):
            try:self.send(label=label);queue.put('sent')
            except g.Blocked:queue.put('blocked')
        children=[ctx.Process(target=worker,args=(label,)) for label in sorted(g.LABELS)]
        for child in children:child.start()
        out=[queue.get(timeout=10) for _ in children]
        for child in children:child.join(10);self.assertEqual(child.exitcode,0)
        self.assertEqual(out.count('sent'),1)
        self.assertEqual(sum(a['reserved'] for a in self.state()['attempts'].values()),1)

    def test_revocation_after_fsync_retains_pending_without_transport(self):
        original=g.envelope;count=[];s=Session()
        def check(now):
            count.append(1)
            if len(count)==4:raise g.Blocked('revoked after durable reservation')
            return original(now)
        with patch.object(g,'envelope',side_effect=check),self.assertRaises(g.Blocked):self.send(s)
        self.assertEqual(s.calls,[])
        self.assertEqual(next(iter(self.state()['attempts'].values()))['state'],'pending')
        with self.assertRaises(g.Blocked):self.send(s,slot='later')
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
        f(self_,'/sports/basketball_nba/events',{'dateFormat':'iso'})
        self.assertEqual(calls,[('guard',{'label':'nba','request_slot':'stable'}),('http',{'max_retries':0,'allow_redirects':False})])

    def test_actual_nfl_get_uses_guard_only_when_explicit_collector(self):
        calls=[];s=Session()
        def guard(*a,**kw):calls.append(kw);return SimpleNamespace(status_code=200,ok=True)
        f=self.extract(Path('nfl-weather/nflweather/oddsapi.py'),'_get',dict(paid_get=guard,session=s,BASE='https://api.the-odds-api.com/v4',SPORT='americanfootball_nfl',api_key=lambda:KEY,quota=SimpleNamespace(record=lambda *a:None),Blocked=g.Blocked,OddsAPIUnavailable=SystemExit,requests=SimpleNamespace(RequestException=ConnectionError)))
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

    def test_actual_nba_paid_entry_cannot_reach_transport(self):
        s=Session()
        f=self.extract(Path('sharp-markets/src/markets/collector.py'),'_odds_get',
                       {'paid_get':g.paid_get,'ODDS_BASE':'https://api.the-odds-api.com/v4'})
        obj=SimpleNamespace(key=KEY,odds=s,limiter=None)
        with self.assertRaisesRegex(g.Blocked,'enforcement bridge not implemented'):
            f(obj,'/sports/basketball_nba/odds',PARAMS,request_slot='x')
        self.assertEqual(s.calls,[])

    def test_actual_installer_metadata_preflight_is_unconditionally_held(self):
        # Execute only its read-only Python metadata preflight, NEVER the installer.
        import sys
        script=(ROOT/'ops/install_live_uses.sh').read_text()
        preflight=script.split("<<'PYGUARD'\n",1)[1].split('\nPYGUARD',1)[0]
        self.assertLess(script.index('require_bridge()'),script.index('k="$(env_key'))
        with patch.object(sys,'argv',['synthetic-metadata-preflight',str(ROOT)]),self.assertRaisesRegex(RuntimeError,'enforcement bridge not implemented'):
            exec(compile(preflight,'installer-metadata-preflight','exec'),{})

    def test_named_paths_stable_slots_and_kernel_lock_are_connected(self):
        sources={p:(ROOT/p).read_text() for p in ('nfl-weather/scripts/log_props.py','nfl-weather/nflweather/oddsapi.py','cfb-weather/cfbweather/live.py','sharp-markets/src/markets/collector.py')}
        self.assertIn('collector_label="nfl-props", request_slot=f"{ev[\'id\']}:{h}"',sources['nfl-weather/scripts/log_props.py'])
        self.assertIn('role = "nfl-trigger"',sources['nfl-weather/nflweather/oddsapi.py'])
        self.assertIn('label="cfb-trigger", request_slot=slot',sources['cfb-weather/cfbweather/live.py'])
        self.assertIn('fcntl.LOCK_EX | fcntl.LOCK_NB',sources['sharp-markets/src/markets/collector.py'])
        self.assertNotIn('lock.unlink',sources['sharp-markets/src/markets/collector.py'])


class RolePropagationTests(unittest.TestCase):
    def test_alert_run_passes_explicit_role_without_executing_job(self):
        # Compile ONLY the run function, stop at board admission. No script
        # startup, weather/model/data, notification or ledger execution.
        for sport in ('nfl','cfb'):
            source=ROOT/f'{sport}-weather/scripts/alerts.py'
            tree=ast.parse(source.read_text())
            node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='run')
            seen=[]
            def stop(**kwargs):seen.append(kwargs);raise StopIteration()
            ns=dict(board=SimpleNamespace(compute=stop),args=SimpleNamespace(days=8,dry_run=False,scheduled_occurrence_utc='fixture-occurrence'),
                    alert_occurrence=lambda token:token,
                    oddsapi=SimpleNamespace(has_key=lambda:True))
            exec(compile(ast.Module(body=[node],type_ignores=[]),str(source),'exec'),ns)
            with self.assertRaises(StopIteration):ns['run']({})
            self.assertEqual(seen[0]['odds_role'],f'{sport}-alert')
            self.assertEqual(seen[0]['odds_slot'],'fixture-occurrence')

    def test_close_transport_expression_and_registered_constants_unchanged(self):
        for sport in ('nfl','cfb'):
            path=ROOT/f'{sport}-weather/scripts/capture_close.py'
            tree=ast.parse(path.read_text())
            constants={n.targets[0].id:ast.unparse(n.value) for n in tree.body
                       if isinstance(n,ast.Assign) and isinstance(n.targets[0],ast.Name)}
            self.assertEqual(constants['MAX_TRIES'],'2')
            self.assertEqual(constants['WINDOW'],'(pd.Timedelta(minutes=2), pd.Timedelta(minutes=20))')
            method='live' if sport=='nfl' else 'odds_api_totals'
            node=next(n for n in ast.walk(tree) if isinstance(n,ast.Call)
                      and isinstance(n.func,ast.Attribute) and n.func.attr==method)
            seen=[]
            def capture(*a,**kwargs):seen.append(kwargs)
            now=datetime.now(timezone.utc)
            ns=dict(oddsapi=SimpleNamespace(live=capture),fetch=SimpleNamespace(odds_api_totals=capture),
                    odds_team_names=lambda:{},close_slot=g.close_slot,slots=['kick'],state={'tries':{}},
                    now=SimpleNamespace(to_pydatetime=lambda:now),observation=g.close_slot(['kick'],{},now))
            eval(compile(ast.Expression(body=node),str(path),'eval'),ns)
            self.assertEqual(seen[0]['role'],f'{sport}-close')
            self.assertEqual(seen[0]['request_slot'],g.close_slot(['kick'],{},now))


class AlertOccurrenceTests(unittest.TestCase):
    def test_delayed_pdt_pst_occurrences_remain_distinct_and_restarts_stable(self):
        cases=[('2026-10-03T14:30:00Z','2026-10-03T16:01:00Z','2026-10-03T18:30:00Z'),
               ('2026-12-03T15:30:00Z','2026-12-03T16:01:00Z','2026-12-03T19:30:00Z')]
        for morning,delayed,later in cases:
            d=g.utc(delayed);l=g.utc(later)
            self.assertEqual(g.slot(d,14400),g.slot(l,14400)) # reproduce OLD defect
            self.assertNotEqual(g.alert_occurrence(morning,now=d),g.alert_occurrence(later,now=l))
            self.assertEqual(g.alert_occurrence(morning,now=d),g.alert_occurrence(morning,now=d+timedelta(seconds=30)))

    def test_explicit_identity_calendar_and_overnight_dst_boundaries(self):
        # Pacific19:30 to07:30 spans12h normally,11h spring,13h autumn.
        for occurrence,last_valid,next_run in [
            ('2026-10-04T02:30:00Z','2026-10-04T14:29:59Z','2026-10-04T14:30:00Z'),
            ('2026-03-08T03:30:00Z','2026-03-08T14:29:59Z','2026-03-08T14:30:00Z'),
            ('2026-11-01T02:30:00Z','2026-11-01T15:29:59Z','2026-11-01T15:30:00Z')]:
            self.assertEqual(g.alert_occurrence(occurrence,now=g.utc(last_valid)),occurrence)
            with self.assertRaises(g.Blocked):g.alert_occurrence(occurrence,now=g.utc(next_run))

    def test_missing_noncanonical_future_wrong_date_or_schedule_is_not_guessed(self):
        now=g.utc('2026-10-03T16:01:00Z')
        for token in [None,'', '07:30', '2026-10-03T14:30Z', '2026-10-03T14:30:00+00:00',
                      '2026-10-03T14:30:01Z','2026-10-03T15:30:00Z',
                      '2026-10-03T18:30:00Z','2026-10-02T14:30:00Z',
                      '2026-02-30T14:30:00Z','ambiguous-trigger',datetime.now(timezone.utc)]:
            with self.subTest(token=token),self.assertRaises(g.Blocked):g.alert_occurrence(token,now=now)

    def test_actual_alert_run_rejects_missing_token_before_board_or_key_side_effects(self):
        for sport in ('nfl','cfb'):
            path=ROOT/f'{sport}-weather/scripts/alerts.py';tree=ast.parse(path.read_text())
            node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='run')
            calls=[]
            def side_effect(**kw):calls.append(kw);raise StopIteration()
            ns=dict(board=SimpleNamespace(compute=side_effect),alert_occurrence=g.alert_occurrence,
                    args=SimpleNamespace(days=8,dry_run=False,scheduled_occurrence_utc=None),
                    oddsapi=SimpleNamespace(has_key=lambda:calls.append('key')))
            exec(compile(ast.Module(body=[node],type_ignores=[]),str(path),'exec'),ns)
            with self.assertRaises(g.Blocked):ns['run']({})
            self.assertEqual(calls,[])
            ns['args'].dry_run=True
            with self.assertRaises(StopIteration):ns['run']({})
            self.assertEqual(calls[-1]['odds_slot'],None) # nonpaid preview needs no identity

    def test_board_expression_forwards_literal_occurrence_without_rebucketing(self):
        for sport in ('nfl','cfb'):
            path=ROOT/f'{sport}-weather/{sport}weather/board.py';tree=ast.parse(path.read_text())
            func=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='compute')
            node=next(n for n in ast.walk(func) if isinstance(n,ast.Call) and
                      ((isinstance(n.func,ast.Name) and n.func.id=='_pinnacle_live') or
                       (isinstance(n.func,ast.Attribute) and n.func.attr=='odds_api_totals')))
            calls=[]
            def capture(*a,**kw):calls.append(kw)
            token='2026-10-03T14:30:00Z'
            ns=dict(_pinnacle_live=capture,fetch=SimpleNamespace(odds_api_totals=capture),names={},
                    odds_role=f'{sport}-alert',odds_slot=token)
            eval(compile(ast.Expression(body=node),str(path),'eval'),ns)
            self.assertEqual(calls[0],{'role':f'{sport}-alert','request_slot':token})


if __name__=='__main__':unittest.main()
