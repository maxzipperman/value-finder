"""Synthetic integration only: verified-byte loader, no keys/network/live state."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

HERE=Path(__file__).parent
METADATA=HERE.parent/'football-metadata-v1'
BUNDLE=HERE.parent/'football_archive/acquisition/football-archive-v4'


def loader():
    spec=importlib.util.spec_from_file_location('pilot_test_capture',METADATA/'capture.py')
    capture=importlib.util.module_from_spec(spec);spec.loader.exec_module(capture)
    paths={}
    for p in BUNDLE.rglob('*.py'):
        n=str(p.relative_to(BUNDLE));name=(n[:-12] if n.endswith('/__init__.py') else n[:-3]).replace('/','.')
        paths[name]=p
    for p in HERE.glob('*.py'):
        if not p.name.startswith('test_'): paths[p.stem]=p
    paths.update(capture=METADATA/'capture.py',history=METADATA/'history.py',
                 plan=HERE.parent/'nfl-props-archive-v1/plan.py',
                 f2_gate=HERE.parent/'football_archive/f2_handoff.py',
                 older_recovery=HERE.parent/'football_archive/older-recovery-v1/recovery.py')
    return capture.closed_modules({n:p.read_bytes() for n,p in paths.items()},paths)


class IntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.load=staticmethod(loader());cls.mapping=cls.load('mapping');cls.plan=cls.load('plan')
        cls.receipts=cls.load('receipts');cls.capture=cls.load('capture');cls.evidence=cls.load('evidence')
        cls.transport=cls.load('transport');cls.base=cls.load('executor')

    def row(self):
        return self.plan.make_request('odds',self.plan.ts('2025-10-01T06:00:00Z'),
                  books=['draftkings'],markets=self.mapping.MARKETS,event_id='abc')

    def policy(self,row):
        return {'snapshot_lag_ids':[row['request_id']],'event_not_found_ids':[row['request_id']],
                'max_missing':{'snapshot_lag':1,'event_not_found':1}}

    def record(self,row,lag=0,status=200,bill=60):
        from datetime import timedelta
        at=self.plan.ts(row['requested_utc'])-timedelta(seconds=lag)
        body={'timestamp':self.plan.iso(at),'previous_timestamp':self.plan.iso(at-timedelta(minutes=5)),
              'next_timestamp':self.plan.iso(at+timedelta(minutes=5)),
              'data':{'id':'abc','sport_key':row['sport'],'commence_time':'2025-10-02T06:00:00Z','bookmakers':[]}}
        if status==404:body={'error_code':'EVENT_NOT_FOUND'}
        return dict(source=row['source'],url=row['url'],sport=row['sport'],cache_key=row['cache_key'],
                    params_json=json.dumps(row['params']),http_status=status,body=json.dumps(body),
                    headers_json=json.dumps({'x-requests-last':str(bill),'x-requests-used':str(bill),'x-requests-remaining':str(5000000-bill)}))

    def test_bootstrap_inventory_requires_offline_runner_only(self):
        boot=self.load('bootstrap')
        actual={p.stem for p in HERE.glob('*.py') if not p.name.startswith('test_')}
        self.assertEqual(boot.MODULES,actual)
        runner=self.load('runner')
        self.assertFalse(hasattr(runner,'run'))

    def test_full_offline_bootstrap_and_changed_packet(self):
        boot=self.load('bootstrap');planner=self.load('planner');row=self.row()
        frame=[dict(game_id='g',season=2025,stratum='NFL2025',binding='abc',classification='unknown')]
        protocol={'sample_sizes':{'NFL2025':1}}
        draw=dict(seed='a'*64,frame=planner.digest(planner.frame_rows(frame)),protocol=planner.digest(protocol),sample_sizes=protocol['sample_sizes'])
        selected=planner.select(frame,draw,protocol['sample_sizes'],committed_frame=draw['frame'],committed_protocol=draw['protocol'],committed_seed_record=planner.digest(draw),protocol=protocol)
        with tempfile.TemporaryDirectory(dir='/private/tmp') as d:
            folder=Path(d)
            payload={'requests.json':[row],'policy.json':self.policy(row),'protocol.json':protocol,'frame.json':frame,'draw.json':draw,'selected.json':selected,
                     'mappings.json':[{'game_id':'g','request_ids':[row['request_id']],'reason':None}],
                     'baseline.json':{},'overlap.json':{}}
            for name,value in payload.items():(folder/name).write_text(json.dumps(value))
            manifest=dict(frame_sha256=draw['frame'],protocol_sha256=draw['protocol'],seed_record_sha256=planner.digest(draw),request_count=1,max_new_credits=60,
                          request_list_sha256=self.capture.sha(folder/'requests.json'),request_set_sha256=self.capture.identity([row]))
            (folder/'manifest.json').write_text(json.dumps(manifest))
            files={n:self.capture.sha(folder/n) for n in boot.PACKET}
            paths={n:HERE/(n+'.py') for n in boot.MODULES}
            paths.update(capture=METADATA/'capture.py',history=METADATA/'history.py',plan=HERE.parent/'nfl-props-archive-v1/plan.py',
                         f2_gate=HERE.parent/'football_archive/f2_handoff.py',older_recovery=HERE.parent/'football_archive/older-recovery-v1/recovery.py')
            files.update({'code/'+n+'.py':self.capture.sha(p) for n,p in paths.items()})
            files['policy/older-PROTOCOL.md']=self.capture.sha(HERE.parent/'football_archive/older-recovery-v1/PROTOCOL.md')
            files['policy/PRIMARY-CONTRACT.json']=self.capture.sha(HERE/'PRIMARY-CONTRACT.json')
            files['source/FREEZE.json']=self.capture.sha(BUNDLE/'FREEZE.json')
            root=hashlib.sha256(boot.canonical(files)).hexdigest()
            (folder/'FREEZE.json').write_text(json.dumps({'root':root,'files':files}))
            runner,base,data,source,_=boot.verified(folder,root,BUNDLE)
            result=runner.packet(data,source)
            self.assertEqual(result['max_new_credits'],60)
            self.assertFalse(result['paid_entrypoint_available'])
            with (folder/'requests.json').open('a') as f:f.write(' ')
            with self.assertRaises(ValueError):boot.verified(folder,root,BUNDLE)

    def test_six_market_cell_absence_and_uncertain_no_resend(self):
        op=dict(opportunity_id='one',season=2025,sport=self.plan.NFL,event_id='abc',slot='T24',
                requested_utc='2025-10-01T06:00:00Z',books=['draftkings'])
        prior=[{'cell':self.mapping.cell(op['sport'],'abc',op['requested_utc'],'draftkings',m),'status':s}
               for m,s in zip(self.mapping.MARKETS,['completed','absent','missing','pending','uncertain'])]
        result=self.mapping.props_union([op],prior,self.plan.make_request)
        self.assertTrue(result['blocked']);self.assertEqual(result['max_new_credits'],10)
        self.assertEqual(result['requests'][0]['params']['markets'],'player_kicking_points')
        allprior=prior+[{'cell':self.mapping.cell(op['sport'],'abc',op['requested_utc'],'draftkings','player_kicking_points'),'status':'absent'}]
        self.assertEqual(self.mapping.props_union([op],allprior,self.plan.make_request)['requests'],[])

    def test_shared_request_dedup_and_zero_denominator(self):
        op=dict(opportunity_id='a',season=2024,sport=self.plan.CFB,event_id='abc',slot='T24',requested_utc='2024-10-01T06:00:00Z',books=['draftkings'])
        other=dict(op,opportunity_id='b');zero=dict(op,opportunity_id='c',no_request_reason='unbound')
        result=self.mapping.props_union([op,other,zero],[],self.plan.make_request)
        self.assertEqual(len(result['requests']),1);self.assertEqual(result['max_new_credits'],60)
        self.assertEqual(result['opportunity_denominator'],3)
        with self.assertRaises(ValueError):self.mapping.props_union([dict(op,requested_utc='2024-10-01T06:01:00Z')],[],self.plan.make_request)

    def test_overlapping_book_panels_never_duplicate_cells(self):
        op=dict(opportunity_id='a',season=2024,sport=self.plan.NFL,event_id='abc',slot='T24',requested_utc='2024-10-01T06:00:00Z',books=['draftkings'])
        result=self.mapping.props_union([op,dict(op,opportunity_id='b',books=['draftkings','fanduel'])],[],self.plan.make_request)
        cells=[]
        for r in result['requests']:
            for m in r['params']['markets'].split(','):
                for b in r['params']['bookmakers'].split(','):cells.append((b,m))
        self.assertEqual(len(cells),len(set(cells)))
        self.assertEqual(len(cells),12)

    def test_older_three_original_ids_exact_cost(self):
        game=dict(game_id='g',season=2020,sport=self.plan.NFL,binding='abc',scheduled_utc='2020-10-02T13:00:00Z',classification='unknown',stratum='NFL2020')
        rows=[dict(request_id=str(i),sport=self.plan.NFL,requested_utc=t,max_new_credits=30)
              for i,t in enumerate(['2020-10-01T13:00:00Z','2020-10-02T12:45:00Z','2020-10-02T12:50:00Z'])]
        mapped=self.mapping.older_slots(game,rows,['1','2'])
        union=self.mapping.original_union([game],['g'],[mapped],rows,[],[])
        self.assertEqual(union['max_new_credits'],90)
        union=self.mapping.original_union([game],['g'],[mapped],rows,[{'request_id':'0','status':'missing'}],[])
        self.assertEqual(union['max_new_credits'],60)
        self.assertEqual(union['selected_denominator'],1)

    def test_finite_missing_and_halts(self):
        row=self.row();policy=self.policy(row)
        self.assertEqual(self.receipts.classify(row,self.record(row,601),policy)['reason'],'snapshot_lag')
        self.assertEqual(self.receipts.classify(row,self.record(row,status=404,bill=0),policy)['reason'],'event_not_found')
        for rec in [self.record(row,-1),self.record(row,status=429),self.record(row,status=500),self.record(row,bill=61),self.record(row,status=404,bill=1)]:
            with self.assertRaises(ValueError):self.receipts.classify(row,rec,policy)
        with self.assertRaises(ValueError):self.receipts.classify(row,self.record(row,601),dict(policy,snapshot_lag_ids=[]))
        bad=self.record(row);body=json.loads(bad['body']);body['data']['id']='other';bad['body']=json.dumps(body)
        with self.assertRaises(ValueError):self.receipts.classify(row,bad,policy)

    def save_evidence(self,folder,row,rec):
        import pyarrow as pa
        import pyarrow.parquet as pq
        path=folder/'data/raw'/row['sport']/row['source']/row['requested_utc'][:10]/(row['cache_key']+'.parquet');path.parent.mkdir(parents=True)
        pq.write_table(pa.Table.from_pylist([rec]),path)
        result=self.receipts.classify(row,rec,self.policy(row))
        proof={'request_id':row['request_id'],'response_sha256':self.capture.sha(path),'record':rec,'classification':result}
        receipt=folder/'receipts'/(row['request_id']+'.json');receipt.parent.mkdir();receipt.write_text(json.dumps(proof))
        attempt=dict(status=result['status'],reserved_credits=60,billed_credits=result['bill'],send_started=True,
                     response_path=str(path),response_sha256=self.capture.sha(path),receipt_sha256=self.capture.sha(receipt))
        return {'attempts':{row['request_id']:attempt}},path,receipt

    def test_actual_parquet_receipt_validation_and_tamper(self):
        row=self.row();rec=self.record(row)
        with tempfile.TemporaryDirectory(dir='/private/tmp') as d:
            folder=Path(d);state,path,receipt=self.save_evidence(folder,row,rec)
            result=self.evidence.captured_receipts(folder,[row],state,self.policy(row))
            self.assertEqual(result['reserved'],60);self.assertEqual(result['untouched_ids'],[])
            path.write_bytes(b'changed')
            with self.assertRaises(Exception):self.evidence.captured_receipts(folder,[row],state,self.policy(row))

    def test_receipt_only_replacement_cannot_certify(self):
        row=self.row()
        with tempfile.TemporaryDirectory(dir='/private/tmp') as d:
            folder=Path(d);state,path,receipt=self.save_evidence(folder,row,self.record(row))
            receipt.write_text(json.dumps({'request_id':row['request_id']}))
            state['attempts'][row['request_id']]['receipt_sha256']=self.capture.sha(receipt)
            with self.assertRaises((ValueError,KeyError)):self.evidence.captured_receipts(folder,[row],state,self.policy(row))

    def test_final_look_reuse_and_exclusive_write(self):
        args=dict(frame_sha256='a'*64,protocol_sha256='b'*64,draw_sha256='c'*64,evidence_sha256='d'*64,
                  selected_ids=['g'],classifications={'g':False},saved_bounds={'lower':0})
        record=self.evidence.final_record(**args)
        self.assertEqual(record,self.evidence.final_record(**args,previous=record))
        with self.assertRaises(ValueError):self.evidence.final_record(**dict(args,classifications={'g':True}),previous=record)
        with self.assertRaises(ValueError):self.evidence.final_record(**dict(args,classifications={'g':None}))
        with tempfile.TemporaryDirectory(dir='/private/tmp') as d:
            path=Path(d)/'final.json';self.evidence.write_once(path,record)
            with self.assertRaises(FileExistsError):self.evidence.write_once(path,record)

    def test_prospective_inventory_positive_and_unknown_store(self):
        row=self.row()
        with tempfile.TemporaryDirectory(dir='/private/tmp') as d:
            root=Path(d);base_dir=root/'base';base_dir.mkdir();(root/'registrations').mkdir()
            (base_dir/'spending-ledger.json').write_text('{}');(base_dir/'INITIALIZED.json').write_text('{}')
            (root/'registrations/base.json').write_text('{}')
            snapshot={'ledgers':{'base':self.capture.sha(base_dir/'spending-ledger.json')},'registrations':{'base':self.capture.sha(root/'registrations/base.json')}}
            child=root/'pilot';state,_,_=self.save_evidence(child,row,self.record(row))
            state.update(status='pilot_complete',pending=None,stopped=None,probe_credits=1687,
                         bundle_root_sha256='pilot',authorization_sha256='auth',pilot_plan_sha256='plan',
                         predecessor_snapshot=self.load('planner').digest(snapshot),other_usage_reserved=100,slice_cap=60)
            (child/'spending-ledger.json').write_text(json.dumps(state));(child/'INITIALIZED.json').write_text('{}')
            marker={'bundle_root_sha256':'pilot','authorization_sha256':'auth','runtime_path':str(child)}
            (root/'registrations/pilot.json').write_text(json.dumps(marker))
            binding=dict(ledger_sha256=self.capture.sha(child/'spending-ledger.json'),marker_sha256=self.capture.sha(root/'registrations/pilot.json'),
                         rows=[row],policy=self.policy(row),predecessor_snapshot=state['predecessor_snapshot'],authorization_sha256='auth',plan_sha256='plan')
            verify=lambda *args:(snapshot,{'cumulative_debit_without_probe':100})
            result=self.evidence.global_union(root,snapshot,{'pilot':binding},verify)
            self.assertEqual(result[1]['conservative_debit'],1847)
            (root/'rogue').mkdir();(root/'rogue/INITIALIZED.json').write_text('{}')
            with self.assertRaises(ValueError):self.evidence.global_union(root,snapshot,{'pilot':binding},verify)

    def test_authority_context_and_live_revocation(self):
        authority=self.load('authority');digest=self.load('planner').digest
        root='a'*64;commit='b'*40;cap=60
        manifest={'new_credits_by_priority':{'1':cap},'request_list_sha256':'c'*64,'request_set_sha256':'d'*64}
        context={k:'e'*64 for k in ('policy_sha256','plan_sha256','global_snapshot_sha256','historical_bindings_sha256','cache_union_sha256','captured_closure_sha256')}
        rec={'status':'approved','bundle_root_sha256':root,'baseline_mode':'capture_first_free_check','reason':'test','owner_note':'test','max_baseline_used':0,'billing_period_utc':self.base.datetime.now(self.base.timezone.utc).strftime('%Y-%m')}
        text=(f"APPROVED paid run: list {manifest['request_list_sha256']}, request-set {manifest['request_set_sha256']}, budget {cap} credits, commit {commit}\n"
              f"APPROVED pilot context: sha256 {digest(context)}, root {root}\n"
              f"APPROVED account reconciliation: sha256 {digest(rec)}, root {root}\nCURRENT PAID AUTHORITY: ACTIVE")
        hub=dict(status='approved',bundle_root_sha256=root,request_set_sha256=manifest['request_set_sha256'],request_list_sha256=manifest['request_list_sha256'],budget_credits=cap,commit=commit,comment_url='https://github.com/maxzipperman/value-finder/pull/99#issuecomment-1',comment_body=text)
        auth=dict(status='approved',bundle_root_sha256=root,priority=1,max_new_credits=cap,human_authorization_evidence='synthetic',execution_commit=commit,account_reconciliation=rec,hub_go_ahead=hub,pilot_context=context)
        live=dict(html_url=hub['comment_url'],body=text,user={'login':'maxzipperman'})
        authority.check(self.base,auth,manifest,root,commit,context,fetch=lambda _:live)
        with self.assertRaises(ValueError):authority.check(self.base,auth,manifest,root,commit,dict(context,plan_sha256='f'*64),fetch=lambda _:live)
        with self.assertRaises(ValueError):authority.check(self.base,auth,manifest,root,commit,context,fetch=lambda _:dict(live,body='REVOKED'))

    def test_real_guarded_session_revocation_before_get_and_no_resend(self):
        row=dict(self.row(),path=self.row()['url'].removeprefix(self.plan.BASE),priority=1)
        with tempfile.TemporaryDirectory(dir='/private/tmp') as d:
            path=Path(d)/'ledger.json';state={'pending':row['request_id'],'attempts':{row['request_id']:{'status':'pending'}}}
            def save():path.write_text(json.dumps(state))
            ledger=SimpleNamespace(state=state,path=path,save=save,observe_headers=lambda *a:None)
            save();calls=[]
            session=SimpleNamespace(adapters={'https':SimpleNamespace(max_retries=SimpleNamespace(total=0))},
                                    get=lambda *a,**kw:calls.append(kw) or SimpleNamespace(text='{}',headers={},status_code=200))
            def revoked():raise ValueError('revoked')
            guarded=self.transport.guarded_session(self.base,revoked,lambda:None)(session,ledger,[row])
            with self.assertRaises(ValueError):guarded.get(row['url'],params=row['params'])
            self.assertEqual(calls,[]);self.assertNotIn('send_started',state['attempts'][row['request_id']])
            guarded=self.transport.guarded_session(self.base,lambda:None,lambda:None)(session,ledger,[row])
            guarded.get(row['url'],params=row['params'])
            self.assertFalse(calls[0]['allow_redirects'])
            with self.assertRaises(Exception):guarded.get(row['url'],params=row['params'])
            self.assertEqual(len(calls),1)
