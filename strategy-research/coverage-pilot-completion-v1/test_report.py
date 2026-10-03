"""Synthetic only; production runtime/payloads/final look are never opened."""
import copy
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

HERE=Path(__file__).parent;REPO=HERE.parent.parent
sys.path.insert(0,str(HERE));import report
sys.path.insert(0,str(HERE.parent/'coverage-pilot-v1'));from test_integration import loader


class ReportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.load=staticmethod(loader())

    def fixture(self):
        plan=self.load('plan');mapping=self.load('mapping');sport=plan.NFL;gid='g';at='2023-10-01T16:00:00Z';close='2023-10-02T15:50:00Z';kick='2023-10-02T16:00:00Z'
        obs=dict(canonical_game_id=gid,provider_id='abc',returned_utc=at,provider_kickoff_utc=kick,home_team='A',away_team='B')
        ops=[dict(slot=slot,event_id='abc',requested_utc=t) for slot,t in [('T24',at),('CLOSE_T10',close)]]
        rows=[plan.make_request('odds',plan.ts(t),books=['draftkings'],markets=mapping.MARKETS,event_id='abc',sport=sport) for t in (at,close)]
        frame=[dict(game_id=gid,stratum='props/'+sport+'/2023',classification='unknown',source_opportunities=ops)]
        maps=[dict(game_id=gid,request_ids=[r['request_id'] for r in rows])]
        data={n:report.canonical(v) for n,v in {'frame.json':frame,'selected.json':{'selected':[gid]},'mappings.json':maps,'slot-map.json':[],'protocol.json':{'candidate_books':['draftkings'],'primary_markets':list(mapping.MARKETS)}}.items()}
        source={'provider-observations.json':report.canonical([obs]),'canonical-games.json':report.canonical([dict(canonical_game_id=gid,scheduled_utc=kick)])}
        projection={}
        for row in rows:
            t=row['requested_utc'];utc=self.load('timing').utc(t)
            from datetime import timedelta
            body=dict(timestamp=t,previous_timestamp=(utc-timedelta(minutes=5)).isoformat(),next_timestamp=(utc+timedelta(minutes=5)).isoformat(),data=dict(id='abc',commence_time=kick,home_team='A',away_team='B',bookmakers=[dict(key='draftkings',last_update=t,markets=[dict(key=m,outcomes=[dict(name=side,description='Player',point=200,price=1.91) for side in ('Over','Under')]) for m in ('player_pass_yds','player_receptions')])]))
            projection[row['request_id']]=dict(status='completed',record=dict(body=json.dumps(body),params_json=json.dumps(row['params']),sport=sport,url=row['url']))
        return data,source,projection,rows

    def test_primary_pairs_and_literal_one_exclusion(self):
        data,source,p,rows=self.fixture();classification,_=report.classify_selected(data,source,self.load,p);self.assertTrue(classification['g'])
        for entry in p.values():
            b=json.loads(entry['record']['body']);b['data']['bookmakers'][0]['markets'][0]['outcomes'][0]['price']=1;entry['record']['body']=json.dumps(b)
        classification,_=report.classify_selected(data,source,self.load,p);self.assertFalse(classification['g'])

    def test_missing_payload_and_duplicate_mapping_refusals(self):
        data,source,p,rows=self.fixture();p.pop(rows[0]['request_id'])
        with self.assertRaises(KeyError):report.classify_selected(data,source,self.load,p)
        data,source,p,rows=self.fixture();maps=json.loads(data['mappings.json']);data['mappings.json']=report.canonical(maps+maps)
        with self.assertRaises(ValueError):report.classify_selected(data,source,self.load,p)

    def test_terminal_missing_false_and_forced_failure_does_not_open_payload(self):
        data,source,p,rows=self.fixture();p[rows[0]['request_id']]['status']='missing'
        result,_=report.classify_selected(data,source,self.load,p);self.assertFalse(result['g'])
        maps=json.loads(data['mappings.json']);maps[0]['coverage_disposition']=dict(classification='failure',reason='certified_quarantined_response');data['mappings.json']=report.canonical(maps)
        result,_=report.classify_selected(data,source,self.load,{})
        self.assertEqual(result,{'g':False})

    def test_lookahead_and_player_book_reference_constraints(self):
        for mutation in ('future_binding','stale_quote','changed_player','changed_book'):
            data,source,p,rows=self.fixture()
            if mutation=='future_binding':
                obs=json.loads(source['provider-observations.json']);obs[0]['returned_utc']='2023-10-02T15:00:00Z';source['provider-observations.json']=report.canonical(obs)
            else:
                entry=p[rows[1]['request_id']];body=json.loads(entry['record']['body']);book=body['data']['bookmakers'][0]
                if mutation=='stale_quote':book['last_update']='2023-10-01T16:00:00Z'
                if mutation=='changed_player':
                    for market in book['markets']:
                        for quote in market['outcomes']:quote['description']='Other'
                if mutation=='changed_book':book['key']='fanduel'
                entry['record']['body']=json.dumps(body)
            with self.subTest(mutation=mutation):self.assertFalse(report.classify_selected(data,source,self.load,p)[0]['g'])

    def test_sides_from_different_responses_never_synthesized(self):
        data,source,p,rows=self.fixture();maps=json.loads(data['mappings.json'])
        for row in rows:
            entry=p[row['request_id']];other=copy.deepcopy(entry)
            for target,side in ((entry,'Over'),(other,'Under')):
                body=json.loads(target['record']['body'])
                for market in body['data']['bookmakers'][0]['markets']:market['outcomes']=[q for q in market['outcomes'] if q['name']==side]
                target['record']['body']=json.dumps(body)
            p[row['request_id']+'other']=other;maps[0]['request_ids'].append(row['request_id']+'other')
        data['mappings.json']=report.canonical(maps)
        self.assertFalse(report.classify_selected(data,source,self.load,p)[0]['g'])

    def test_older_designated_shared_sweep_requires_pinnacle_both_slots(self):
        data,source,projection,rows=self.fixture();sport=self.load('plan').NFL
        frame=json.loads(data['frame.json']);frame[0]['stratum']='older/'+sport+'/2020';frame[0].pop('source_opportunities');data['frame.json']=report.canonical(frame)
        obs=json.loads(source['provider-observations.json'])[0]
        slots={role:dict(request_id=r['request_id'],requested_utc=r['requested_utc'],provider_id='abc',binding=obs) for role,r in zip(('EARLY','CLOSE'),rows)}
        data['slot-map.json']=report.canonical([dict(game_id='g',slots=slots)])
        for entry in projection.values():
            body=json.loads(entry['record']['body']);event=body['data'];book=event['bookmakers'][0]
            book['markets']=[dict(key='totals',outcomes=[dict(name=s,point=44,price=1.91) for s in ('Over','Under')])]
            ref=copy.deepcopy(book);ref['key']='pinnacle';event['bookmakers'].append(ref);body['data']=[event,dict(event,id='unselected')];entry['record']['body']=json.dumps(body)
        classification,_=report.classify_selected(data,source,self.load,projection)
        self.assertEqual(classification,{'g':True})  # Incidental second event never expands n.
        entry=projection[rows[1]['request_id']];body=json.loads(entry['record']['body']);body['data'][0]['bookmakers'].pop();entry['record']['body']=json.dumps(body)
        self.assertFalse(report.classify_selected(data,source,self.load,projection)[0]['g'])

    def test_terminal_gate_exact_scope_and_reserve(self):
        root='r';runtime=Path('/private/tmp/synthetic');rows=[dict(request_id='x',max_new_credits=30)];pin=dict(authorization_sha256='a',billed=30,reserved=30,predecessor_snapshot_sha256='b')
        state=dict(status='pilot_complete',pending=None,stopped=None,bundle_root_sha256=root,pilot_plan_sha256=root,authorization_sha256='a',probe_credits=1687,slice_cap=30,predecessor_snapshot='b',attempts={'x':dict(status='completed',send_started=True,reserved_credits=30,billed_credits=30)})
        marker=dict(bundle_root_sha256=root,authorization_sha256='a',runtime_path=str(runtime));init=dict(bundle_root_sha256=root,probe_credits=1687)
        self.assertEqual(report.terminal_state(state,rows,pin,root,runtime,marker,init)['reserved'],30)
        for field,value in [('pending','x'),('stopped','halt'),('status','running')]:
            with self.subTest(field=field),self.assertRaises(ValueError):report.terminal_state(dict(state,**{field:value}),rows,pin,root,runtime,marker,init)
        for attempts in ({},dict(state['attempts'],y=state['attempts']['x'])):
            with self.assertRaises(ValueError):report.terminal_state(dict(state,attempts=attempts),rows,pin,root,runtime,marker,init)
        with self.assertRaises(ValueError):report.terminal_state(state,rows+rows,pin,root,runtime,marker,init)

    def test_fixed_strata_cost_denominator_no_sample_promotion(self):
        # Frozen metadata only; no sample result from production is consulted.
        packet=HERE.parent/'coverage-pilot-packet-v1/pilot-successor-142'
        data={n:(packet/n).read_bytes() for n in ('frame.json','protocol.json','selected.json')}
        selected=json.loads(data['selected.json'])['selected'];classes={gid:False for gid in selected}
        result=report.bound_record(data,self.load,classes)
        self.assertEqual(len(result['strata']),12)
        for row in result['strata']:
            unit=60 if row['stratum'].startswith('older/') else 122
            self.assertEqual(row['projected_new_credits'],unit*row['unknown_population'])
        census=next(r for r in result['strata'] if r['stratum']=='props/americanfootball_nfl/2025')
        self.assertEqual(census['known_successes'],215);self.assertEqual(census['population'],285);self.assertEqual(census['sample'],0)
        with self.assertRaises(ValueError):report.bound_record(data,self.load,{})

    def test_output_and_bad_bootstrap_before_exec(self):
        for out in (Path.home()/'code/value-finder/final-record.json',Path('/private/tmp/final-record.json'),report.OUTPUT_BASE/'wrong.json'):
            with self.assertRaises(ValueError):report.output_path(out,'finalize')
        with tempfile.TemporaryDirectory(dir='/private/tmp') as d:
            repo=Path(d);packet=repo/'packet';packet.mkdir();path=repo/'strategy-research/coverage-pilot-v1/bootstrap.py';path.parent.mkdir(parents=True);sentinel=repo/'executed';path.write_text(f"open({str(sentinel)!r},'w').write('bad')")
            cert={'code/bootstrap.py':'0'*64};root=report.identity(cert)
            (packet/'FREEZE.json').write_bytes(report.canonical(dict(root=root,files=cert)))
            with patch.object(report,'ROOT',root),self.assertRaises(ValueError):report.captured_closure(repo,packet,root)
            self.assertFalse(sentinel.exists())

    def test_frozen_counter_replay_is_pure_and_detects_changed_epoch(self):
        from datetime import timedelta
        base=self.load('executor');receipts=self.load('receipts');plan=self.load('plan');mapping=self.load('mapping')
        rows=[plan.make_request('odds',plan.ts(t),books=['draftkings'],markets=mapping.MARKETS,event_id='abc') for t in ('2025-10-01T06:00:00Z','2025-10-02T06:00:00Z')]
        state=dict(epoch=dict(start_used=100,start_remaining=4900000,start_billed=0,prebaseline_other_debit=200,first_provider_observation_verified=True,used_highwater=100,remaining_lowwater=4900000,external_peak=0),provider_used=100,provider_remaining=4900000,other_usage_reserved=200,probe_credits=1687,slice_cap=120,attempts={r['request_id']:dict(status='completed',reserved_credits=60,billed_credits=60) for r in rows},accounts=[dict(used=100,remaining=4900000)],free_account_attempt=dict(status='completed',used=100,remaining=4900000))
        protocol=dict(billing_reconciliation=dict(counter_lag_tolerance_credits=0,shared_usage_margin_credits=0),budgets=dict(first_tranche_cumulative_credits=250000,day_one_cumulative_ceiling=250000,broader_cumulative_ceiling=250000,account_reserve_floor=0))
        records={};policy=dict(snapshot_lag_ids=[r['request_id'] for r in rows],event_not_found_ids=[r['request_id'] for r in rows],max_missing=dict(snapshot_lag=1,event_not_found=1))
        simulated=object.__new__(base.Ledger);simulated.state=state;simulated.protocol=protocol;simulated.save=lambda:None
        simulated.measure_counters(100,4900000,0)
        for i,row in enumerate(rows,1):
            at=plan.ts(row['requested_utc']);body=dict(timestamp=plan.iso(at),previous_timestamp=plan.iso(at-timedelta(minutes=5)),next_timestamp=plan.iso(at+timedelta(minutes=5)),data=dict(id='abc',sport_key=row['sport'],commence_time='2025-10-03T06:00:00Z',bookmakers=[]))
            records[row['request_id']]=dict(source=row['source'],sport=row['sport'],url=row['url'],cache_key=row['cache_key'],params_json=json.dumps(row['params']),body=json.dumps(body),http_status=200,headers_json=json.dumps({'x-requests-last':'60','x-requests-used':str(100+60*i),'x-requests-remaining':str(4900000-60*i)}))
            simulated.measure_counters(100+60*i,4900000-60*i,60*i)
        before=copy.deepcopy(state)
        self.assertEqual(report.counter_replay(base,state,rows,records,policy,protocol,receipts)['billed'],120)
        self.assertEqual(state,before)
        state['epoch']['external_peak']=1
        with self.assertRaises(ValueError):report.counter_replay(base,state,rows,records,policy,protocol,receipts)

    def modes(self,folder,mode='verify'):
        folder=Path(folder);runtime=folder/'runtime';runtime.mkdir();(runtime/'followup-purchase.lock').touch()
        base=SimpleNamespace(RUNTIME_BASE=runtime,current_runtime=lambda:{})
        evidence=self.load('evidence');load=lambda n:{'executor':base,'capture':self.load('capture'),'evidence':evidence}[n]
        pin=dict(root=report.ROOT,adapter_sha256=report.digest(report.regular(HERE/'report.py')))
        p=folder/'completion.json';p.write_bytes(report.canonical(pin));output=folder/'artifacts';output.mkdir()
        args=SimpleNamespace(mode=mode,completion_binding=p,completion_sha256=report.digest(p.read_bytes()),output=output/('receipt-verification.json' if mode=='verify' else 'final-record.json'),repo=folder,packet=folder/'packet',existing_final_sha256=None,final_authorization=folder/'authorization.json',final_authorization_sha256=None,verified_receipts=output/'receipt-verification.json',verified_sha256=None)
        fingerprint=dict(root=report.ROOT,completion_sha256=args.completion_sha256,adapter_sha256=pin['adapter_sha256'],packet_files_sha256=report.identity({}))
        proof=dict(receipts='synthetic')
        verified=dict(status='receipts_verified',fingerprint=fingerprint,proof=proof,final_look_run=False)
        if mode=='finalize':
            args.verified_receipts.write_bytes(report.canonical(verified));args.verified_sha256=report.digest(args.verified_receipts.read_bytes());args.final_authorization.write_bytes(b'{}');args.final_authorization_sha256=report.digest(b'{}')
        closure=({}, {'runtime-lock.json':b'{}'}, load)
        return args,output,closure,proof,fingerprint

    def test_verify_mode_never_classifies_or_computes_bounds(self):
        with tempfile.TemporaryDirectory(dir='/private/tmp') as d:
            args,out,closure,proof,fingerprint=self.modes(d)
            with patch.object(report,'OUTPUT_BASE',out),patch.object(report,'captured_closure',return_value=closure),patch.object(report,'authenticate',return_value=({},proof)),patch.object(report,'classify_selected',side_effect=AssertionError('final look')),patch.object(report,'bound_record',side_effect=AssertionError('bounds')):
                result=report.run(args)
            self.assertFalse(result['final_look_run']);self.assertTrue(args.output.exists())

    def test_final_authority_refusal_precedes_receipt_payload_read(self):
        with tempfile.TemporaryDirectory(dir='/private/tmp') as d:
            args,out,closure,proof,fingerprint=self.modes(d,'finalize')
            with patch.object(report,'OUTPUT_BASE',out),patch.object(report,'captured_closure',return_value=closure),patch.object(report,'final_authority',side_effect=ValueError('not authorized')),patch.object(report,'authenticate',side_effect=AssertionError('payload read')):
                with self.assertRaisesRegex(ValueError,'not authorized'):report.run(args)
            self.assertFalse(args.output.exists())

    def test_saved_final_reuse_requires_external_pin_and_never_recomputes(self):
        with tempfile.TemporaryDirectory(dir='/private/tmp') as d:
            args,out,closure,proof,fingerprint=self.modes(d,'finalize');record={'saved':'synthetic'}
            saved=dict(fingerprint=fingerprint,verification_sha256=args.verified_sha256,proof=proof,record=record,record_sha256=report.identity(record))
            args.output.write_bytes(report.canonical(saved))
            with patch.object(report,'OUTPUT_BASE',out),patch.object(report,'captured_closure',return_value=closure),patch.object(report,'final_authority'),patch.object(report,'authenticate',return_value=({},proof)),patch.object(report,'classify_selected',side_effect=AssertionError('second look')),patch.object(report,'bound_record',side_effect=AssertionError('second bounds')):
                with self.assertRaisesRegex(ValueError,'external saved artifact pin'):report.run(args)
                args.existing_final_sha256=report.digest(args.output.read_bytes())
                self.assertEqual(report.run(args),saved)
                args.output.write_bytes(report.canonical(dict(saved,record={'changed':True})))
                with self.assertRaises(ValueError):report.run(args)

    def test_explicit_final_authority_and_revocation(self):
        pin=dict(adapter_sha256='a');vp='b';line=f"APPROVED final coverage look: root {report.ROOT}, completion {report.identity(pin)}, verification {vp}, adapter a";url='https://github.com/maxzipperman/value-finder/pull/144#issuecomment-1'
        auth=dict(comment_url=url,comment_body=line);live=dict(html_url=url,body=line,user=dict(login='maxzipperman'))
        report.final_authority(auth,pin,vp,fetch=lambda _:live)
        for body in (line+'\nREVOKED',line+'\nNOT READY',line+'\n'+line):
            with self.assertRaises(ValueError):report.final_authority(dict(auth,comment_body=body),pin,vp,fetch=lambda _:dict(live,body=body))
        with self.assertRaises(ValueError):report.final_authority(auth,pin,vp,fetch=lambda _:dict(live,body='HALTED'))

if __name__=='__main__':unittest.main()
