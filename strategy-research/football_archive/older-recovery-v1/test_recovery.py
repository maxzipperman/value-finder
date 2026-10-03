"""Synthetic delta checks only; never inspect actual runtime or provider records."""
import copy
from datetime import datetime, timedelta, timezone
import importlib.util
import json
from pathlib import Path
import socket
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

import recovery as r


def guard(event, args):
    if event in ("socket.connect", "socket.getaddrinfo"):
        raise RuntimeError("Tests forbid network")
    if event == "open" and isinstance(args[0], (str, bytes)):
        path = str(args[0])
        if "/Library/Application Support/ValueFinder/" in path or Path(path).name == ".env":
            raise RuntimeError("Tests forbid real runtime/credentials")


sys.addaudithook(guard)


def base_module():
    source = r.BUNDLE / "executor.py"
    module = types.ModuleType("synthetic_reviewed_base")
    module.__file__ = str(source)
    exec(compile(source.read_bytes(), str(source), "exec"), module.__dict__)
    return module


def row():
    return {"request_id": "a" * 64, "cache_key": "b" * 20, "sport": "americanfootball_ncaaf",
        "source": "oddsapi/hist_odds", "path": "/historical/sports/americanfootball_ncaaf/odds",
        "params": {"date": "2020-11-27T17:55:00Z"}, "requested_utc": "2020-11-27T17:55:00Z",
        "max_new_credits": 30, "priority": 2}


def record(cost=30):
    value = row()
    return {"http_status": 200, "sport": value["sport"], "source": value["source"], "cache_key": value["cache_key"],
        "url": "https://api.the-odds-api.com/v4" + value["path"], "params_json": json.dumps(value["params"]),
        "body": json.dumps({"timestamp": "2020-11-27T17:15:00Z", "previous_timestamp": "2020-11-27T17:05:00Z",
                           "next_timestamp": "2020-11-27T20:25:00Z", "data": []}),
        "headers_json": json.dumps({"x-requests-last": str(cost), "x-requests-used": str(1000 + cost),
                                   "x-requests-remaining": str(5000000 - cost)})}


def state(cost=30):
    rec = record(cost)
    return {"attempts": {row()["request_id"]: {"status": "pending", "reserved_credits": 30,
                "cache_key": row()["cache_key"], "send_started": True, "observed_http_status": 200,
                "observed_billing_headers": json.loads(rec["headers_json"])}},
        "pending": row()["request_id"], "stopped": "synthetic stop", "status": "halted", "probe_credits": 1687,
        "slice_cap": 53580, "other_usage_reserved": 150000, "provider_used": 1000, "provider_remaining": 5000000,
        "epoch": {"start_billed": 0, "start_used": 1000, "start_remaining": 5000000,
                  "used_highwater": 1000, "remaining_lowwater": 5000000, "external_peak": 0,
                  "prebaseline_other_debit": 150000}}


class LagTests(unittest.TestCase):
    def test_valid_positive_and_zero_billed_lag(self):
        for cost in (0, 30):
            with self.subTest(cost=cost):
                result = r.lag_record(row(), record(cost))
                self.assertEqual((result["lag_seconds"], result["billed"]), (2400, cost))

    def test_http_and_identity_failures(self):
        changes = {"http_status": [404, 500, "200"], "sport": ["nba"], "source": ["other"],
                   "cache_key": ["wrong"], "url": ["https://elsewhere"], "params_json": ['{}']}
        for key, values in changes.items():
            for value in values:
                with self.subTest(key=key, value=value):
                    rec = record(); rec[key] = value
                    with self.assertRaises((ValueError, KeyError, TypeError)):
                        r.lag_record(row(), rec)

    def test_body_clock_neighbor_failures(self):
        changes = [("data", None), ("timestamp", None), ("timestamp", "bad"),
            ("timestamp", "2020-11-27T17:15:00"), ("timestamp", "2020-11-27T18:15:00Z"),
            ("timestamp", "2020-11-27T17:45:00Z"), ("timestamp", "2020-11-27T17:50:00Z"),
            ("previous_timestamp", None), ("previous_timestamp", "2020-11-27T17:15:00Z"),
            ("next_timestamp", "2020-11-27T17:10:00Z"), ("next_timestamp", "2020-11-27T20:25:00")]
        for key, value in changes:
            with self.subTest(key=key, value=value):
                rec = record(); body = json.loads(rec["body"]); body[key] = value; rec["body"] = json.dumps(body)
                with self.assertRaises((ValueError, KeyError, TypeError)):
                    r.lag_record(row(), rec)

    def test_billing_failures(self):
        for key in ("x-requests-last", "x-requests-used", "x-requests-remaining"):
            for value in (None, True, -1, "1.0", "NaN"):
                with self.subTest(key=key, value=value):
                    rec = record(); h = json.loads(rec["headers_json"]); h[key] = value; rec["headers_json"] = json.dumps(h)
                    with self.assertRaises(ValueError):
                        r.lag_record(row(), rec)
        with self.assertRaises(ValueError):
            r.lag_record(row(), record(31))

    def test_copy_preserves_bill_reservation_carry_and_input(self):
        base = base_module(); cfg = json.loads((r.BUNDLE / "protocol.json").read_text())
        for cost in (0, 30):
            original = state(cost); before = copy.deepcopy(original)
            post, receipt, _ = r.pure_missing(base, original, cfg, row(), record(cost), Path('/synthetic/cache.parquet'), 'c'*64)
            self.assertEqual(original, before)
            self.assertIsNone(post["pending"]); self.assertIsNone(post["stopped"])
            self.assertEqual(post["other_usage_reserved"], 150000)
            self.assertEqual(post["attempts"][row()["request_id"]]["reserved_credits"], 30)
            self.assertEqual(post["attempts"][row()["request_id"]]["billed_credits"], cost)
            self.assertFalse(receipt["usable_quote"])

    def test_uncertain_or_conflicting_attempt_rejected(self):
        base = base_module(); cfg = json.loads((r.BUNDLE / "protocol.json").read_text())
        for change in ("pending", "reservation", "headers"):
            s = state()
            if change == "pending": s["pending"] = None
            elif change == "reservation": s["attempts"][row()["request_id"]]["reserved_credits"] = 0
            else: s["attempts"][row()["request_id"]]["observed_billing_headers"] = {}
            with self.subTest(change=change), self.assertRaises(ValueError):
                r.pure_missing(base, s, cfg, row(), record(), Path('/synthetic/cache.parquet'), 'c'*64)

    def test_counter_and_cumulative_stops_remain(self):
        base = base_module(); cfg = json.loads((r.BUNDLE / "protocol.json").read_text())
        for kind in ("external", "floor", "cap"):
            s = state(); rec = record()
            if kind == "external":
                h = json.loads(rec["headers_json"]); h["x-requests-used"] = "1200"; rec["headers_json"] = json.dumps(h)
                s["attempts"][row()["request_id"]]["observed_billing_headers"] = h
            elif kind == "floor": s["epoch"]["remaining_lowwater"] = cfg["budgets"]["account_reserve_floor"] - 1
            else: s["other_usage_reserved"] = 250000
            with self.subTest(kind=kind), self.assertRaises(base.Halt):
                r.pure_missing(base, s, cfg, row(), rec, Path('/synthetic/cache.parquet'), 'c'*64)


def approval():
    return {"status": "approved", "execution_commit": "a"*40, "human_authorization_evidence": "SYNTHETIC",
            "hub_go_ahead": {"status": "approved", "comment_url": "https://github.com/maxzipperman/value-finder/pull/129#issuecomment-1",
                             "comment_body": "synthetic exact line"}}


class AuthorityTests(unittest.TestCase):
    def test_active_exact_authority(self):
        r.active_authority(approval(), ["synthetic exact line"], commit="a"*40, authenticate=False)

    def test_revocation_anywhere_case_insensitive(self):
        for term in ("HALTED", "EXHAUSTED", "revoked", "NOT APPROVED"):
            for place in ("before", "after"):
                auth = approval(); auth["hub_go_ahead"]["comment_body"] = (term + '\nsynthetic exact line' if place == "before" else 'synthetic exact line\n'+term)
                with self.subTest(term=term, place=place), self.assertRaises(ValueError):
                    r.active_authority(auth, ["synthetic exact line"], authenticate=False)

    def test_wrong_commit_duplicate_line_and_wrong_destination(self):
        for kind in ("commit", "duplicate", "destination", "owner"):
            auth = approval()
            if kind == "commit": auth["execution_commit"] = 'b'*40
            elif kind == "duplicate": auth["hub_go_ahead"]["comment_body"] *= 2
            elif kind == "destination": auth["hub_go_ahead"]["comment_url"] = 'https://github.com/other/repo/pull/129#issuecomment-1'
            else: auth.pop('human_authorization_evidence')
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                r.active_authority(auth, ["synthetic exact line"], commit='a'*40, authenticate=False)

    def test_live_edited_body_and_other_user_rejected(self):
        auth = approval()
        live = {'html_url': auth['hub_go_ahead']['comment_url'], 'body': 'synthetic exact line', 'user': {'login':'maxzipperman'}}
        for key, value in [('body','edited'),('user',{'login':'other'}),('html_url','elsewhere')]:
            bad = {**live,key:value}
            with self.subTest(key=key), patch.object(r.subprocess,'check_output',return_value=json.dumps(bad)), self.assertRaises(ValueError):
                r.active_authority(auth,['synthetic exact line'])

    def test_paid_binds_account_content_policy_and_cap(self):
        base=base_module(); root='b'*64; commit='a'*40
        m={'request_list_sha256':'c'*64,'request_set_sha256':'d'*64,'policy_sha256':'e'*64}
        auth=approval();auth.update(stage='older-lag-continuation',priority=2,bundle_root_sha256=root,max_new_credits=r.NEW_CAP)
        rec={'status':'approved','bundle_root_sha256':root,'baseline_mode':'capture_first_free_check',
             'reason':'synthetic','owner_note':'synthetic','max_baseline_used':1700,'billing_period_utc':datetime.now(timezone.utc).strftime('%Y-%m')}
        auth['account_reconciliation']=rec
        hub=auth['hub_go_ahead'];hub.update(bundle_root_sha256=root,request_list_sha256=m['request_list_sha256'],request_set_sha256=m['request_set_sha256'],budget_credits=r.NEW_CAP,commit=commit,comment_url='https://github.com/maxzipperman/value-finder/pull/99#issuecomment-1')
        hub['comment_body']='\n'.join([f"APPROVED paid run: list {m['request_list_sha256']}, request-set {m['request_set_sha256']}, budget {r.NEW_CAP} credits, commit {commit}",
            f'APPROVED content: root {root}, stage older-lag-continuation',f'APPROVED account ceiling: max-baseline-used 1700, root {root}',
            f'APPROVED account reconciliation: sha256 {r.identity(rec)}, root {root}',f"APPROVED snapshot lag policy: sha256 {m['policy_sha256']}, max-missing {r.REMAINING_COUNT}, root {root}"])
        r.paid_authority(auth,m,root,commit,base,authenticate=False)
        for kind in ('ceiling','debit','month','stage','cap','policy','revoked'):
            bad=copy.deepcopy(auth)
            if kind=='ceiling':bad['account_reconciliation']['max_baseline_used']+=1
            elif kind=='debit':bad['account_reconciliation']['pre_run_other_usage_budget_debit']=0
            elif kind=='month':bad['account_reconciliation']['billing_period_utc']='2000-01'
            elif kind=='stage':bad['stage']='older-priority-2'
            elif kind=='cap':bad['max_new_credits']+=30
            elif kind=='policy':bad['hub_go_ahead']['comment_body']=bad['hub_go_ahead']['comment_body'].replace('max-missing 1786','max-missing 1787')
            else:bad['hub_go_ahead']['comment_body']='HALTED\n'+bad['hub_go_ahead']['comment_body']
            with self.subTest(kind=kind),self.assertRaises((ValueError,base.Halt)):
                r.paid_authority(bad,m,root,commit,base,authenticate=False)


class IntegrityTests(unittest.TestCase):
    def test_capture_executes_bytes_and_rejects_ambient_module(self):
        with tempfile.TemporaryDirectory(dir='/private/tmp') as td:
            p=Path(td)/'helper.py';p.write_text('VALUE=999\n')
            load=r.closed_modules({'helper':b'VALUE=1\n','main':b'import helper\nVALUE=helper.VALUE\n'}, {'helper':p,'main':Path(td)/'main.py'})
            p.write_text("raise RuntimeError('reopened')\n")
            self.assertEqual(load('main').VALUE,1)
            load2=r.closed_modules({'main':b'import unlisted_local_sentinel\n'}, {'main':Path(td)/'main.py'})
            with self.assertRaises(ImportError):load2('main')

    def test_regular_rejects_symlink_fifo(self):
        import os
        with tempfile.TemporaryDirectory(dir='/private/tmp') as td:
            p=Path(td);(p/'file').write_bytes(b'original');(p/'link').symlink_to(p/'file');os.mkfifo(p/'fifo')
            for f in ('link','fifo'):
                with self.subTest(f=f),self.assertRaises(ValueError):r.regular(p/f)

    def test_prepare_requires_actual_transition_before_output_creation(self):
        with tempfile.TemporaryDirectory(dir='/private/tmp') as td:
            output=Path(td)/'packet'
            with patch.object(r,'verified_partial',side_effect=ValueError('actual transition absent')),self.assertRaises(ValueError):
                r.prepare(output,Path(td)/'coverage')
            self.assertFalse(output.exists())

    def test_exact_remaining_scope_and_attempted_keys(self):
        rows=[{'request_id':str(i),'cache_key':str(i),'max_new_credits':30} for i in range(2267)]
        rows += [{'request_id':'reuse'+str(i),'cache_key':'reuse'+str(i),'max_new_credits':0} for i in range(12)]
        s={'pending':None,'stopped':None,'status':r.PARTIAL_STATUS,'attempts':{str(i):{'status':'completed','cache_key':str(i)} for i in range(481)}}
        remaining=r.remaining_rows(rows,s)
        self.assertEqual(len(remaining),1786);self.assertEqual(sum(x['max_new_credits'] for x in remaining),53580)
        for kind in ('pending','stopped','count','cache'):
            bad=copy.deepcopy(s)
            if kind in ('pending','stopped'):bad[kind]='uncertain'
            elif kind=='count':bad['attempts'].pop('0')
            else:bad['attempts']['0']['cache_key']='481'
            with self.subTest(kind=kind),self.assertRaises(ValueError):r.remaining_rows(rows,bad)

    def test_install_crash_keeps_stopped_bytes_until_last_write(self):
        base=base_module()
        for crash in ('after_backup','after_authority','after_receipt',None):
            with self.subTest(crash=crash),tempfile.TemporaryDirectory(dir='/private/tmp') as td:
                rootbase=Path(td);runtime=rootbase/r.OLD_ROOT;runtime.mkdir()
                old=b'{"stopped":"synthetic"}\n';(runtime/'spending-ledger.json').write_bytes(old)
                post={'status':r.PARTIAL_STATUS,'pending':None,'stopped':None}
                receipt={'request_id':'synthetic'}
                pins={'request_id':'synthetic','stopped_ledger_sha256':r.digest(old)}
                cert={'post_ledger_sha256':r.digest(r.canonical(post)+b'\n')}
                paths=[]
                for name,obj in [('cert',cert),('pins',pins),('original',{}),('approval',{})]:
                    p=rootbase/(name+'.json');p.write_bytes(r.canonical(obj));paths.append(p)
                def checkpoint(point):
                    if point==crash:raise RuntimeError('synthetic crash')
                with patch.object(r,'RUNTIME_BASE',rootbase),patch.object(r,'clean_commit',return_value='a'*40),patch.object(r,'offline_authority'),patch.object(r,'preview',return_value=(cert,post,receipt,base)):
                    if crash:
                        with self.assertRaises(RuntimeError):r.install(*paths,rootbase/'coverage',checkpoint=checkpoint)
                        self.assertEqual((runtime/'spending-ledger.json').read_bytes(),old)
                    else:
                        r.install(*paths,rootbase/'coverage',checkpoint=checkpoint)
                        self.assertEqual((runtime/'spending-ledger.json').read_bytes(),r.canonical(post)+b'\n')
                self.assertEqual((runtime/'older-lag-recovery-v1/stopped-ledger.json').read_bytes(),old)

    def test_continuation_lag_receipt_crash_keeps_pending(self):
        base=base_module();original=row();finite=r.policy([original])
        cls=r.continuation_ledger(base,finite)
        with tempfile.TemporaryDirectory(dir='/private/tmp') as td:
            ledger=cls.__new__(cls);ledger.folder=Path(td);ledger.state=state();ledger.protocol=json.loads((r.BUNDLE/'protocol.json').read_text())
            ledger.original_rows=[original];ledger.save=lambda:None
            p=Path(td)/'synthetic.parquet';p.write_bytes(b'synthetic')
            ledger.checkpoint=lambda point: (_ for _ in ()).throw(RuntimeError('crash'))
            with self.assertRaises(RuntimeError):ledger.complete(original,record(),p)
            self.assertEqual(ledger.state['pending'],original['request_id'])
            ledger.checkpoint=lambda point:None;ledger.complete(original,record(),p)
            self.assertIsNone(ledger.state['pending']);self.assertEqual(ledger.state['attempts'][original['request_id']]['billed_credits'],30)
            self.assertEqual(ledger.state['attempts'][original['request_id']]['reserved_credits'],30)


class DriverTests(unittest.TestCase):
    def test_synthetic_transport_lag_fault_and_no_resend(self):
        from requests.adapters import HTTPAdapter
        import contextlib
        bundle=r.BUNDLE
        original=next(x for x in json.loads((bundle/'request-manifest.json').read_text())['requests'] if x['priority']==2 and x['max_new_credits']==30)
        for mode in ('lag','ok','timeout','overcharge','missing_billing','future','http404','crash_reservation','crash_receipt'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory(dir='/private/tmp') as td:
                rootbase=Path(td);root='f'*64;runtime=rootbase/root
                frozen=json.loads((bundle/'FREEZE.json').read_text())['file_sha256']
                captured={name:(bundle/name).read_bytes() for name in frozen if name.endswith('.py')}
                names={n:(n[:-12] if n.endswith('/__init__.py') else n[:-3]).replace('/','.') for n in captured}
                load=r.closed_modules({names[n]:b for n,b in captured.items()},{names[n]:bundle/n for n in captured})
                base=load('executor');base.RUNTIME_BASE=rootbase
                m={'request_list_sha256':'c'*64,'request_set_sha256':'d'*64,'policy_sha256':r.identity(r.policy([original])),'new_credits':30}
                commit='a'*40
                rec={'status':'approved','bundle_root_sha256':root,'baseline_mode':'capture_first_free_check','reason':'synthetic',
                     'owner_note':'synthetic','max_baseline_used':1700,'billing_period_utc':datetime.now(timezone.utc).strftime('%Y-%m')}
                auth={'status':'approved','priority':2,'stage':'older-lag-continuation','bundle_root_sha256':root,'max_new_credits':30,
                      'human_authorization_evidence':'SYNTHETIC','execution_commit':commit,'account_reconciliation':rec,
                      'hub_go_ahead':{'status':'approved','bundle_root_sha256':root,'request_list_sha256':m['request_list_sha256'],
                          'request_set_sha256':m['request_set_sha256'],'budget_credits':30,'commit':commit,
                          'comment_url':'https://github.com/maxzipperman/value-finder/pull/99#issuecomment-1'}}
                with patch.object(r,'NEW_CAP',30),patch.object(r,'REMAINING_COUNT',1):
                    m['policy_sha256']=r.identity(r.policy([original]))
                    auth['hub_go_ahead']['comment_body']='\n'.join([f"APPROVED paid run: list {m['request_list_sha256']}, request-set {m['request_set_sha256']}, budget 30 credits, commit {commit}",
                        f'APPROVED content: root {root}, stage older-lag-continuation',f'APPROVED account ceiling: max-baseline-used 1700, root {root}',
                        f'APPROVED account reconciliation: sha256 {r.identity(rec)}, root {root}',f"APPROVED snapshot lag policy: sha256 {m['policy_sha256']}, max-missing 1, root {root}"])
                    seed={'root':'e'*64,'cumulative_debit_without_probe':150000,'probe_credits':1687}
                    calls=[];auth_checks=[]
                    class Response:
                        status_code=200
                        def __init__(self,body,headers):self.text=body;self.headers=headers
                    class Session:
                        adapters={'https':HTTPAdapter(max_retries=0)}
                        def get(self,url,params=None,**kwargs):
                            calls.append(url)
                            if url.endswith('/sports'):return Response('[]',{'x-requests-last':'0','x-requests-used':'1000','x-requests-remaining':'5000000'})
                            if mode=='timeout':raise RuntimeError('synthetic transport failure')
                            requested=r.stamp(original['requested_utc']);returned=requested-timedelta(minutes=40 if mode in ('lag','crash_receipt') else 5)
                            fmt=lambda value:value.isoformat().replace('+00:00','Z')
                            if mode=='future':returned=requested+timedelta(minutes=5)
                            body=json.dumps({'timestamp':fmt(returned),'previous_timestamp':fmt(returned-timedelta(minutes=5)),
                                             'next_timestamp':fmt(returned+timedelta(minutes=5)),'data':[]})
                            headers={'x-requests-last':'31' if mode=='overcharge' else '30','x-requests-used':'1030','x-requests-remaining':'4999970'}
                            if mode=='missing_billing':headers.pop('x-requests-last')
                            response=Response(body,headers)
                            if mode=='http404':response.status_code=404
                            return response
                        def close(self):pass
                    def checkpoint(point):
                        if (mode=='crash_reservation' and point=='after_reservation') or (mode=='crash_receipt' and point=='after_receipt'):
                            raise RuntimeError('synthetic crash')
                    actual_authority=r.paid_authority
                    def authority(*args,**kwargs):
                        auth_checks.append(True);return actual_authority(*args,authenticate=False)
                    with contextlib.ExitStack() as stack:
                        for name,value in [('RUNTIME_BASE',rootbase),('verify_packet',lambda *a:(m,[original],seed,base)),
                            ('clean_commit',lambda *a:commit),('historical',lambda *a:(types.SimpleNamespace(),types.SimpleNamespace(global_settled=lambda *a:None),base,None)),
                            ('cache_inventory',lambda *a:{'paid_exact_overlap':0}),('packet_content',lambda *a:{}),('paid_authority',authority)]:
                            stack.enter_context(patch.object(r,name,value))
                        packet=rootbase/'packet';packet.mkdir();(packet/'FREEZE.json').write_text('{"files":{}}')
                        if mode in ('lag','ok'):
                            result=r.run(packet,root,rootbase/'coverage',auth,key='SYNTHETIC_KEY_ONLY',fake_session=Session(),checkpoint=checkpoint)
                            self.assertEqual(result['reserved'],30);self.assertEqual(result['billed'],30)
                            self.assertEqual(result['missing'],int(mode=='lag'))
                            before=(runtime/'spending-ledger.json').read_bytes()
                            with self.assertRaises(ValueError):r.run(packet,root,rootbase/'coverage',auth,key=lambda:self.fail('completed authority reads key'),fake_session=Session())
                            self.assertEqual(before,(runtime/'spending-ledger.json').read_bytes())
                            self.assertEqual(len(calls),2)
                        else:
                            with self.assertRaises((RuntimeError,ValueError,base.Halt)):
                                r.run(packet,root,rootbase/'coverage',auth,key='SYNTHETIC_KEY_ONLY',fake_session=Session(),checkpoint=checkpoint)
                            s=json.loads((runtime/'spending-ledger.json').read_text());self.assertEqual(s['pending'],original['request_id'])
                            self.assertEqual(s['attempts'][original['request_id']]['reserved_credits'],31 if mode=='overcharge' else 30)
                            count=len(calls)
                            with self.assertRaises(base.Halt):r.run(packet,root,rootbase/'coverage',auth,key=lambda:self.fail('pending reads key'),fake_session=Session())
                            self.assertEqual(len(calls),count)
                        self.assertGreaterEqual(len(auth_checks),4 if mode!='crash_reservation' else 3)


if __name__ == '__main__':
    unittest.main()
