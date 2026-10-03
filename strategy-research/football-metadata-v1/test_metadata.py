import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

HERE=Path(__file__).parent
sys.path.insert(0,str(HERE.parent/'nfl-props-archive-v1'))
import plan
import entry


class MetadataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.packet=HERE/'listing-gaps'
        cls.root=json.loads((cls.packet/'FREEZE.json').read_text())['root']
        cls.bundle=HERE.parent/'football_archive/acquisition/football-archive-v4'
        cls.engine,cls.base,cls.data,cls.source,loader=entry.verified(cls.packet,cls.root,cls.bundle)
        cls.load=staticmethod(loader)

    def row(self):return dict(plan.make_request('events',plan.ts('2025-10-01T06:00:00Z')),path='/historical/sports/americanfootball_nfl/events',max_credits=1,priority=1)

    def record(self,lag=0,last=1,status=200):
        row=self.row();at=plan.ts(row['requested_utc'])
        from datetime import timedelta
        stamp=at-timedelta(seconds=lag)
        body={'timestamp':plan.iso(stamp),'previous_timestamp':plan.iso(stamp-timedelta(minutes=5)),
              'next_timestamp':plan.iso(stamp+timedelta(minutes=5)),'data':[]}
        return {'http_status':status,'cache_key':row['cache_key'],'sport':row['sport'],'source':row['source'],'url':row['url'],
                'params_json':json.dumps(row['params']),'body':json.dumps(body),
                'headers_json':json.dumps({'x-requests-last':str(last),'x-requests-used':str(last),'x-requests-remaining':str(5000000-last)})}

    def auth(self,m,root):
        commit='1'*40
        rec={'status':'approved','bundle_root_sha256':root,'baseline_mode':'capture_first_free_check','reason':'synthetic',
             'owner_note':'synthetic','max_baseline_used':0,'billing_period_utc':self.engine.datetime.now(self.engine.timezone.utc).strftime('%Y-%m')}
        expected=f"APPROVED paid run: list {m['request_list_sha256']}, request-set {m['request_set_sha256']}, budget {m['max_new_credits']} credits, commit {commit}"
        return {'status':'approved','bundle_root_sha256':root,'priority':1,'max_new_credits':m['max_new_credits'],
                'human_authorization_evidence':'synthetic only','execution_commit':commit,'account_reconciliation':rec,
                'global_snapshot':{},'probe_bundle_root':'/synthetic',
                'hub_go_ahead':{'status':'approved','bundle_root_sha256':root,'request_set_sha256':m['request_set_sha256'],
                               'request_list_sha256':m['request_list_sha256'],'budget_credits':m['max_new_credits'],'commit':commit,
                               'comment_url':'https://github.com/maxzipperman/value-finder/pull/99#issuecomment-1','comment_body':expected}}

    def test_exact_finite_listing_packet(self):
        m,rows,policy=self.engine.packet(self.data)
        self.assertEqual((len(rows),m['max_new_credits'],policy['max_missing']),(1544,1544,1544))
        self.assertTrue(all(r['source']=='oddsapi/hist_events' for r in rows))
        self.assertEqual(sum(r['sport']==plan.NFL for r in rows),765)

    def test_changed_list_or_policy_refused(self):
        data=dict(self.data);data['request-list.csv']+=b'\n'
        with self.assertRaises(ValueError):self.engine.packet(data)
        data=dict(self.data);p=json.loads(data['policy.json']);p['allowed_missing'].append('timeout');data['policy.json']=json.dumps(p).encode()
        with self.assertRaises(ValueError):self.engine.packet(data)

    def test_known_lag_missing_and_zero_bill_preserve_category(self):
        self.assertEqual(self.engine.metadata_valid(self.row(),self.record(lag=601,last=0))[:2],('missing',0))
        self.assertEqual(self.engine.metadata_valid(self.row(),self.record(lag=600))[:2],('completed',1))

    def test_adverse_metadata_not_accepted_missing(self):
        variants=[self.record(lag=-1),self.record(last=2),self.record(status=404),self.record(status=500)]
        bad=self.record();bad['headers_json']=json.dumps({'x-requests-last':'unknown'});variants.append(bad)
        bad=self.record();bad['body']='not JSON';variants.append(bad)
        bad=self.record();body=json.loads(bad['body']);body['data']=[{'id':'e','sport_key':plan.NFL,'home_team':'h','away_team':'a','commence_time':'2025-10-02T00:00:00Z','bookmakers':[]}];bad['body']=json.dumps(body);variants.append(bad)
        for rec in variants:
            with self.subTest(rec=rec),self.assertRaises((ValueError,KeyError)):self.engine.metadata_valid(self.row(),rec)

    def test_undeclared_local_import_refused(self):
        with self.assertRaises(ImportError):
            loader=self.load('capture').closed_modules({'sentinel_entry':b'import undeclared_local_sentinel'}, {'sentinel_entry':HERE/'never.py'})
            loader('sentinel_entry')

    def test_allowed_external_name_cannot_load_ambient_module(self):
        capture=self.load('capture')
        loader=capture.closed_modules({'checked_entry':b'import requests'}, {'checked_entry':HERE/'never.py'})
        with patch.object(capture.importlib.util,'find_spec',return_value=SimpleNamespace(origin='/private/tmp/requests.py')):
            with self.assertRaises(ImportError):loader('checked_entry')

    def test_regular_file_rejects_symlink(self):
        with tempfile.TemporaryDirectory(dir='/private/tmp') as d:
            p=Path(d);(p/'file').write_text('x');(p/'alias').symlink_to(p/'file')
            with self.assertRaises(ValueError):entry.regular(p/'alias')

    def test_full_source_capture_refuses_mutation_before_execution(self):
        import shutil
        for mutation in ('shared_code','own_code','undeclared_file'):
            with self.subTest(mutation=mutation),tempfile.TemporaryDirectory(dir='/private/tmp') as d:
                directory=Path(d);code=directory/'football-metadata-v1';props=directory/'nfl-props-archive-v1'
                code.mkdir();props.mkdir()
                for name in ('entry.py','engine.py','capture.py','prepare.py','history.py'):shutil.copyfile(HERE/name,code/name)
                shutil.copyfile(HERE.parent/'nfl-props-archive-v1/plan.py',props/'plan.py')
                archive=directory/'football_archive';archive.mkdir()
                shutil.copyfile(HERE.parent/'football_archive/f2_handoff.py',archive/'f2_handoff.py')
                recovery=archive/'older-recovery-v1';recovery.mkdir()
                for name in ('recovery.py','PROTOCOL.md'):shutil.copyfile(HERE.parent/'football_archive/older-recovery-v1'/name,recovery/name)
                bundle=directory/'bundle';shutil.copytree(self.bundle,bundle)
                if mutation=='shared_code':(bundle/'executor.py').write_bytes((bundle/'executor.py').read_bytes()+b'\nraise RuntimeError("SENTINEL EXECUTED")\n')
                elif mutation=='own_code':(code/'engine.py').write_bytes((code/'engine.py').read_bytes()+b'\nraise RuntimeError("SENTINEL EXECUTED")\n')
                else:(bundle/'undeclared.py').write_text('raise RuntimeError("SENTINEL EXECUTED")')
                with patch.object(entry,'__file__',str(code/'entry.py')):
                    with self.assertRaises(ValueError):entry.verified(self.packet,self.root,bundle)

    def test_metadata_default_format_and_time_alias_never_repurchased(self):
        import pyarrow as pa
        import pyarrow.parquet as pq
        with tempfile.TemporaryDirectory(dir='/private/tmp') as d:
            root=Path(d);directory=root/plan.NFL/'oddsapi/hist_events/2025-10-01';directory.mkdir(parents=True)
            rec={'sport':plan.NFL,'source':'oddsapi/hist_events','url':self.row()['url'],
                 'params_json':json.dumps({'date':'2025-10-01T06:00:00+00:00'})}
            pq.write_table(pa.Table.from_pylist([rec]),directory/'different-key.parquet')
            self.assertTrue(self.engine.metadata_cache_overlap([self.row()],[root]))
            self.assertFalse(self.engine.metadata_cache_overlap([dict(self.row(),requested_utc='2025-10-02T06:00:00Z')],[root]))

    def test_actual_unresolved_global_store_blocks_without_mutation(self):
        # No private fixture/result read; supply synthetic pending state and matching marker.
        with tempfile.TemporaryDirectory(dir='/private/tmp') as d,patch.object(self.engine,'ROOT_BASE',Path(d)):
            root=Path(d);(root/'registrations').mkdir();r=root/plan.SOURCE_ROOT;r.mkdir()
            (r/'spending-ledger.json').write_text(json.dumps({'pending':'uncertain','stopped':None}))
            (root/'registrations'/(plan.SOURCE_ROOT+'.json')).write_text('{}')
            before=(r/'spending-ledger.json').read_bytes()
            with self.assertRaisesRegex(ValueError,'Unresolved global purchase'):self.engine.global_inventory()
            self.assertEqual(before,(r/'spending-ledger.json').read_bytes())

    def test_missing_original_store_cannot_reset_budget(self):
        with tempfile.TemporaryDirectory(dir='/private/tmp') as d,patch.object(self.engine,'ROOT_BASE',Path(d)):
            (Path(d)/'registrations').mkdir()
            with self.assertRaises(ValueError):self.engine.global_inventory()

    def exercise_ledger(self,crash=None,lag=0,bill=1):
        with tempfile.TemporaryDirectory(dir='/private/tmp') as d:
            runtime=Path(d);row=self.row();root='c'*64
            m={'max_new_credits':1,'request_list_sha256':'a'*64,'request_set_sha256':'b'*64,'new_credits_by_priority':{'1':1},'requests':[row]}
            auth=self.auth(m,root)
            ledger=self.engine.metadata_ledger(self.base,{'max_missing':1})(runtime,json.loads(self.source['protocol.json']),m,root,auth,json.loads(self.source['probe-spending-ledger.json']))
            self.addCleanup(ledger.close)
            ledger.account(0,5000000);ledger.reserve(row)
            # Transport boundary persists send_started before any callback/network call.
            class Session:
                adapters={'fake':SimpleNamespace(max_retries=SimpleNamespace(total=0))}
                count=0
                def get(s,url,**kw):
                    s.count+=1
                    self.assertFalse(kw['allow_redirects'])
                    state=json.loads(ledger.path.read_text())
                    self.assertTrue(state['attempts'][row['request_id']]['send_started'])
                    if crash=='transport':raise TimeoutError('synthetic timeout')
                    return SimpleNamespace(status_code=200,text=self.record(lag,bill)['body'],headers=json.loads(self.record(lag,bill)['headers_json']))
                def close(s):pass
            session=Session();guard=self.base.GuardedSession(session,ledger,[row]);guard.ledger_key='synthetic-key-only'
            if crash=='transport':
                with self.assertRaises(TimeoutError):guard.get(row['url'],params=row['params'])
                with self.assertRaises(self.base.Halt):guard.get(row['url'],params=row['params'])
                self.assertEqual(session.count,1);self.assertEqual(ledger.reserved(),1);ledger.close();return
            response=guard.get(row['url'],params=row['params'])
            os.environ.update(MARKETS_ROOT=str(runtime),MARKETS_DATA_DIR=str(runtime/'data'))
            RawCache=self.load('archive_markets.cache').RawCache;Fetched=self.load('archive_markets.cache').Fetched
            cache=RawCache(runtime/'data/raw')
            rec=cache.get_or_fetch(sport=row['sport'],source=row['source'],data_date=row['requested_utc'][:10],url=row['url'],params=row['params'],fetch=lambda:Fetched(200,response.headers,response.text))
            path=cache.lookup(row['sport'],row['source'],row['cache_key'])
            def checkpoint(name):
                if crash==name:raise RuntimeError('synthetic crash')
            ledger.checkpoint=checkpoint
            if crash=='after_receipt':
                with self.assertRaises(RuntimeError):ledger.complete(row,rec,path)
                self.assertIsNotNone(ledger.state['pending']);self.assertEqual(ledger.reserved(),1)
                with self.assertRaises(self.base.Halt):guard.get(row['url'],params=row['params'])
            else:
                ledger.complete(row,rec,path);self.engine.terminal_evidence(ledger,[row])
                self.assertEqual(ledger.reserved(),1);self.assertEqual(ledger.billed(),bill)
                self.assertEqual(ledger.state['attempts'][row['request_id']]['status'],'missing' if lag>600 else 'completed')
                path.write_bytes(b'changed')
                with self.assertRaises(ValueError):self.engine.terminal_evidence(ledger,[row])
            ledger.close()

    def test_receipt_cache_billing_validated(self):self.exercise_ledger()
    def test_zero_bill_missing_keeps_full_reservation(self):self.exercise_ledger(lag=601,bill=0)
    def test_receipt_crash_stays_pending_never_resends(self):self.exercise_ledger(crash='after_receipt')
    def test_timeout_never_resends(self):self.exercise_ledger(crash='transport')

    def test_synthetic_driver_completes_exhausts_and_rejects_revocation(self):
        for revoke in (False,True):
            with self.subTest(revoke=revoke),tempfile.TemporaryDirectory(dir='/private/tmp') as d:
                directory=Path(d);engine=self.engine;base=self.base
                rows=[plan.make_request('events',plan.ts('2025-10-01T06:00:00Z'),sport=s) for s in (plan.NFL,plan.CFB)]
                m={'request_count':2,'max_new_credits':2,'request_list_sha256':'a'*64,'request_set_sha256':'b'*64}
                policy={'max_missing':2};auth=self.auth(m,self.root)
                auth['probe_bundle_root']=str(directory);source=dict(self.source);source['input-provenance.json']=b'{"raw_probe_sources":[]}'
                seed={'root':plan.SOURCE_ROOT,'ledger_path':str(directory/plan.SOURCE_ROOT/'spending-ledger.json'),
                      'ledger_sha256':'a'*64,'probe_credits':1687,'cumulative_debit_without_probe':0}
                approval_calls=[];keys=[]
                def authority(*args):
                    approval_calls.append(True)
                    # Initial + under-lock + free account + first paid. Revoke before the second paid GET.
                    if revoke and len(approval_calls)==5:raise ValueError('Revoked synthetic live authority')
                class Session:
                    adapters={'fake':SimpleNamespace(max_retries=SimpleNamespace(total=0))}
                    calls=[];paid=0
                    def get(obj,url,**kwargs):
                        obj.calls.append(url)
                        self.assertFalse(kwargs['allow_redirects'])
                        if url.endswith('/sports'):
                            last=0;text='[]'
                        else:
                            obj.paid+=1;last=1
                            request=next(r for r in rows if r['url']==url)
                            at=plan.ts(request['requested_utc']);from datetime import timedelta
                            text=json.dumps({'timestamp':plan.iso(at),'previous_timestamp':plan.iso(at-timedelta(minutes=5)),
                                             'next_timestamp':plan.iso(at+timedelta(minutes=5)),'data':[]})
                        return SimpleNamespace(status_code=200,text=text,headers={'x-requests-last':str(last),
                                              'x-requests-used':str(obj.paid),'x-requests-remaining':str(5000000-obj.paid)})
                    def close(obj):pass
                session=Session()
                def key():keys.append(True);return 'synthetic-key-only'
                verified=lambda:(engine,base,self.data,source,self.load)
                with patch.object(engine,'ROOT_BASE',directory),patch.object(base,'RUNTIME_BASE',directory), \
                     patch.object(engine,'packet',return_value=(m,rows,policy)),patch.object(engine,'global_inventory',return_value=({},seed)), \
                     patch.object(engine,'active_authority',side_effect=authority),patch.object(base,'checkout_commit',return_value='1'*40), \
                     patch.object(engine.subprocess,'run'),patch.object(engine.subprocess,'check_output',return_value=str(Path.cwd())):
                    if revoke:
                        with self.assertRaises(self.base.Halt):engine.run(self.packet,self.root,self.bundle,auth,key=key,verify=verified,fake_session=session)
                        state=json.loads((directory/self.root/'spending-ledger.json').read_text())
                        self.assertIsNotNone(state['pending']);self.assertEqual(session.paid,1)
                        before=len(session.calls)
                        with self.assertRaises(ValueError):engine.run(self.packet,self.root,self.bundle,auth,key=key,verify=verified,fake_session=session)
                        self.assertEqual(len(session.calls),before)
                    else:
                        result=engine.run(self.packet,self.root,self.bundle,auth,key=key,verify=verified,fake_session=session)
                        self.assertEqual((result['new_reserved'],result['new_billed']),(2,2));self.assertFalse(result['next_stage_authorized'])
                        before=len(session.calls)
                        with self.assertRaisesRegex(ValueError,'exhausted'):engine.run(self.packet,self.root,self.bundle,auth,key=key,verify=verified,fake_session=session)
                        self.assertEqual(len(session.calls),before);self.assertEqual(len(keys),1)

    def test_authority_context_mutation_and_revocation(self):
        m,_,policy=self.engine.packet(self.data);root=self.root;a=self.auth(m,root);rec=a['account_reconciliation'];c=a['execution_commit'];identity=self.load('capture').identity
        lines=[f'APPROVED metadata content: root {root}, stage listing-gaps',f'APPROVED account reconciliation: sha256 {identity(rec)}, root {root}',
               f'APPROVED global snapshot: sha256 {identity(a["global_snapshot"])}, root {root}',
               f'APPROVED cache reconciliation: sha256 {identity({"probe_bundle_root":"/synthetic","additional_raw_roots":[]})}, root {root}',
               f'APPROVED metadata policy: sha256 {identity(policy)}, max-missing 1544, root {root}',
               f'APPROVED account ceiling: max-baseline-used 0, root {root}',
               f'APPROVED historical bindings: sha256 {identity({})}, root {root}','CURRENT PAID AUTHORITY: ACTIVE']
        a['hub_go_ahead']['comment_body']+='\n'+'\n'.join(lines)
        body=a['hub_go_ahead']['comment_body'];live={'html_url':a['hub_go_ahead']['comment_url'],'body':body,'user':{'login':'maxzipperman'}}
        with patch.object(self.engine.subprocess,'check_output',return_value=json.dumps(live)):
            self.engine.active_authority(a,m,policy,root,c)
            rec['max_baseline_used']=100
            with self.assertRaises(ValueError):self.engine.active_authority(a,m,policy,root,c)
            rec['max_baseline_used']=0
            a['historical_bindings']={'older_coverage_path':'altered'}
            with self.assertRaises(ValueError):self.engine.active_authority(a,m,policy,root,c)
            a.pop('historical_bindings')
            for word in ('HALTED','EXHAUSTED','REVOKED','NOT APPROVED'):
                a['hub_go_ahead']['comment_body']=body+'\n'+word
                with self.assertRaises(ValueError):self.engine.active_authority(a,m,policy,root,c)


if __name__=='__main__':unittest.main()
