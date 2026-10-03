"""Synthetic strict binding, receipt reuse and metadata-only overlap failure paths."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from test_integration import loader


class BindingTests(unittest.TestCase):
    def setUp(self):
        self.load=loader();self.capture=self.load('capture');self.plan=self.load('plan');self.mapping=self.load('mapping')

    def test_strict_selected_frame_positive_and_wrong_slot_or_incomplete_cells(self):
        m=self.load('frame_binding');sport=self.plan.NFL;gid='g'
        early='2023-10-01T16:00:00Z';close='2023-10-02T15:50:00Z';kick='2023-10-02T16:00:00Z'
        obs=dict(canonical_game_id=gid,provider_id='abc',returned_utc=early,provider_kickoff_utc=kick,home_team='A',away_team='B')
        ops=[dict(slot=slot,status='bound',event_id='abc',requested_utc=at,binding_observed_utc=early) for slot,at in [('T24',early),('CLOSE_T10',close)]]
        frame=[dict(game_id=gid,season=2023,stratum='props/'+sport+'/2023',classification='unknown',binding=True,scheduled_utc=kick,source_opportunities=ops)]
        rows=[self.plan.make_request('odds',self.plan.ts(at),books=['draftkings'],markets=self.mapping.MARKETS,event_id='abc',sport=sport) for at in (early,close)]
        maps=[dict(game_id=gid,request_ids=[r['request_id'] for r in rows])]
        source={'provider-observations.json':json.dumps([obs]).encode(),'request-manifest.json':b'{"requests":[]}', 'canonical-games.json':json.dumps([dict(canonical_game_id=gid,sport=sport,season=2023,scheduled_utc=kick,close_anchor_utc=kick)]).encode()}
        data={'frame.json':json.dumps(frame).encode(),'slot-map.json':b'[]','classifier-contract.json':json.dumps(dict(market='totals',reference='pinnacle',replace_failed_slots=False,book_panel=['draftkings'])).encode(),'protocol.json':json.dumps(dict(candidate_books=['draftkings'],primary_markets=list(self.mapping.MARKETS))).encode(),'code/plan.py':b'synthetic-code'}
        proof=dict(frame_sha256=self.capture.digest(data['frame.json']),requested_slot_map_sha256=self.capture.digest(data['slot-map.json']),contract_sha256=self.capture.digest(data['classifier-contract.json']),older_metadata_proof=dict(metadata_files={n:self.capture.digest(v) for n,v in source.items()},early_decision_rule_source_sha256=self.capture.digest(data['code/plan.py'])))
        data['certainty-source-proof.json']=json.dumps(proof).encode()
        self.assertTrue(m.verify(data,source,rows,{},maps,frame))
        # Exercise actual packet validation with internally consistent frozen pins.
        def packet(f, rs, ms):
            planner=self.load('planner');runner=self.load('runner');values=copy.deepcopy(data)
            protocol=json.loads(values['protocol.json']);protocol.update(execution_status='reviewed_for_execution',sample_sizes={f[0]['stratum']:1})
            draw=dict(seed='a'*64,frame=planner.digest(planner.frame_rows(f)),protocol=planner.digest(protocol),sample_sizes=protocol['sample_sizes'])
            selected=planner.select(f,draw,protocol['sample_sizes'],committed_frame=draw['frame'],committed_protocol=draw['protocol'],committed_seed_record=planner.digest(draw),protocol=protocol)
            for name,value in [('frame.json',f),('requests.json',rs),('mappings.json',ms),('protocol.json',protocol),('draw.json',draw),('selected.json',selected),('policy.json',dict(snapshot_lag_ids=[],event_not_found_ids=[],max_missing=dict(snapshot_lag=0,event_not_found=0)))]:
                values[name]=json.dumps(value).encode()
            pr=json.loads(values['certainty-source-proof.json']);pr['frame_sha256']=self.capture.digest(values['frame.json']);values['certainty-source-proof.json']=json.dumps(pr).encode()
            manifest=dict(frame_sha256=draw['frame'],protocol_sha256=draw['protocol'],seed_record_sha256=planner.digest(draw),request_count=len(rs),max_new_credits=sum(r['max_new_credits'] for r in rs),request_list_sha256=self.capture.digest(values['requests.json']),request_set_sha256=self.capture.identity(rs))
            values['manifest.json']=json.dumps(manifest).encode();values['policy/PRIMARY-CONTRACT.json']=(Path(__file__).parent/'PRIMARY-CONTRACT.json').read_bytes()
            return runner.packet(values,source)
        pm=[dict(maps[0],reason=None)]
        self.assertTrue(packet(frame,rows,pm)['execution_protocol_ready'])
        redundant=self.plan.make_request('odds',self.plan.ts(early),books=['draftkings'],markets=['player_pass_yds'],event_id='abc',sport=sport)
        with self.assertRaisesRegex(ValueError,'internal paid'):
            packet(frame,rows+[redundant],[dict(pm[0],request_ids=pm[0]['request_ids']+[redundant['request_id']])])
        paidreuse=[dict(pm[0],reused_slots=[dict(event_id='abc',sport=sport,requested_utc=early,books=['draftkings'],markets=['player_pass_yds'])])]
        with self.assertRaisesRegex(ValueError,'paid/reused'):packet(frame,rows,paidreuse)
        for slot,wrongtime in [('T24','2023-10-02T15:00:00Z'),('CLOSE_T10','2023-10-02T15:45:00Z')]:
            wrongframe=copy.deepcopy(frame)
            for op in wrongframe[0]['source_opportunities']:
                if op['slot']==slot:op['requested_utc']=wrongtime
            wrongrows=[self.plan.make_request('odds',self.plan.ts(op['requested_utc']),books=['draftkings'],markets=self.mapping.MARKETS,event_id='abc',sport=sport) for op in wrongframe[0]['source_opportunities']]
            with self.assertRaisesRegex(ValueError,'slot clock'):
                packet(wrongframe,wrongrows,[dict(game_id=gid,request_ids=[r['request_id'] for r in wrongrows],reason=None)])
        wrongframe=copy.deepcopy(frame);wrongframe[0]['source_opportunities'].append(copy.deepcopy(ops[0]))
        with self.assertRaisesRegex(ValueError,'exactly one'):packet(wrongframe,rows,pm)
        self.assertTrue(self.load('overlap').check_internal(rows,[pm[0],pm[0]]))
        wrong=copy.deepcopy(rows);wrong[0]['event_id']='future-close-alias'
        with self.assertRaises(ValueError):m.verify(data,source,wrong,{},maps,frame)
        wrong=copy.deepcopy(rows);wrong[0]['params']['markets']='player_pass_yds'
        with self.assertRaisesRegex(ValueError,'complete designated'):m.verify(data,source,wrong,{},maps,frame)
        reused=copy.deepcopy(maps);reused[0]['request_ids']=[rows[1]['request_id']];reused[0]['reused_slots']=[dict(event_id='abc',sport=sport,requested_utc=early,books=['draftkings'],markets=list(self.mapping.MARKETS))]
        self.assertTrue(m.verify(data,source,[rows[1]],{},reused,frame))
        reused[0]['reused_slots'][0]['sport']=self.plan.CFB
        with self.assertRaises(ValueError):m.verify(data,source,[rows[1]],{},reused,frame)

    def saved(self,folder,row):
        import pyarrow as pa
        import pyarrow.parquet as pq
        raw=folder/'data/raw'/row['sport']/row['source']/row['requested_utc'][:10]/(row['cache_key']+'.parquet');raw.parent.mkdir(parents=True)
        record={k:row[k] for k in ('sport','source','url','cache_key')};record['params_json']=json.dumps(row['params'])
        pq.write_table(pa.Table.from_pylist([record]),raw)
        receipt=folder/'receipts'/(row['request_id']+'.json');receipt.parent.mkdir();receipt.write_text(json.dumps(dict(request_id=row['request_id'])))
        attempt=dict(status='completed',response_path=str(raw),response_sha256=self.capture.sha(raw),receipt_sha256=self.capture.sha(receipt))
        ledger=folder/'spending-ledger.json';ledger.write_text(json.dumps(dict(attempts={row['request_id']:attempt})))
        claim=dict(root=folder.name,request_id=row['request_id'],response_sha256=attempt['response_sha256'],receipt_sha256=attempt['receipt_sha256'])
        return raw,ledger,claim

    def test_reuse_authenticated_cells_and_wrong_pin_or_extra_cell(self):
        evidence=self.load('evidence');row=self.plan.make_request('odds',self.plan.ts('2025-10-01T16:00:00Z'),books=['draftkings'],markets=['player_pass_yds'],event_id='abc')
        with tempfile.TemporaryDirectory(dir='/private/tmp') as d:
            root=Path(d);raw,ledger,claim=self.saved(root/'prior',row)
            snapshot={'ledgers':{'prior':self.capture.sha(ledger)}}
            slot=dict(event_id='abc',sport=row['sport'],requested_utc=row['requested_utc'],books=['draftkings'],markets=['player_pass_yds'],evidence=[claim])
            maps=[dict(reused_slots=[slot])]
            self.assertTrue(evidence.authenticate_reuse(root,snapshot,maps))
            wrong=copy.deepcopy(maps);wrong[0]['reused_slots'][0]['evidence'][0]['receipt_sha256']='0'*64
            with self.assertRaises(ValueError):evidence.authenticate_reuse(root,snapshot,wrong)
            wrong=copy.deepcopy(maps);wrong[0]['reused_slots'][0]['markets'].append('player_receptions')
            with self.assertRaisesRegex(ValueError,'lack authenticated'):evidence.authenticate_reuse(root,snapshot,wrong)
            wrong=copy.deepcopy(maps);wrong[0]['reused_slots'][0]['event_id']='alias'
            with self.assertRaises(ValueError):evidence.authenticate_reuse(root,snapshot,wrong)
            with self.assertRaises(ValueError):evidence.authenticate_reuse(root,snapshot,[dict(reused_request_ids=[row['request_id']])])

    def test_direct_overlap_exact_cells_inventory_and_sealed_exclusion(self):
        overlap=self.load('overlap');row=self.plan.make_request('odds',self.plan.ts('2025-10-01T16:00:00Z'),books=['draftkings'],markets=['player_pass_yds'],event_id='abc')
        with tempfile.TemporaryDirectory(dir='/private/tmp') as d:
            folder=Path(d);raw,_,_=self.saved(folder,row);rawroot=folder/'data/raw'
            fingerprint=self.capture.identity({str(raw):self.capture.sha(raw)})
            other=self.plan.make_request('odds',self.plan.ts(row['requested_utc']),books=['fanduel'],markets=['player_pass_yds'],event_id='abc')
            self.assertEqual(overlap.check([other],[rawroot],expected_inventory_sha256=fingerprint),fingerprint)
            redundant=self.plan.make_request('odds',self.plan.ts(row['requested_utc']),books=['draftkings'],markets=['player_pass_yds','player_receptions'],event_id='abc')
            with self.assertRaisesRegex(ValueError,'internal paid'):overlap.check([row,redundant],[rawroot],expected_inventory_sha256=fingerprint)
            with self.assertRaisesRegex(ValueError,'overlap'):overlap.check([row],[rawroot],expected_inventory_sha256=fingerprint)
            with self.assertRaisesRegex(ValueError,'inventory changed'):overlap.check([other],[rawroot],expected_inventory_sha256='0'*64)
            sealed=rawroot/row['sport']/row['source']/'2026-09-01'/'sealed.parquet';sealed.parent.mkdir();sealed.write_bytes(b'never parse this')
            self.assertEqual(overlap.check([other],[rawroot],expected_inventory_sha256=fingerprint),fingerprint)

    def test_strict_older_daily_primary_and_decision_time_close_binding(self):
        m=self.load('frame_binding');sport=self.plan.NFL;early='2020-10-01T16:00:00Z';close='2020-10-02T15:50:00Z';kick='2020-10-02T16:00:00Z'
        obs=dict(canonical_game_id='g',provider_id='abc',returned_utc=early,provider_kickoff_utc=kick,home_team='A',away_team='B')
        originals=[dict(request_id=rid,sport=sport,requested_utc=at,purposes=[purpose],source='oddsapi/hist_odds') for rid,at,purpose in [('early',early,'daily_16UTC'),('close',close,'pregame_close_proxy')]]
        frame=[dict(game_id='g',season=2020,stratum='older/'+sport+'/2020',scheduled_utc=kick,classification='unknown',binding=True)]
        slotmap=[dict(game_id='g',binding=True,slots={slot:dict(request_id=rid,requested_utc=at,provider_id='abc',binding=obs) for slot,rid,at in [('EARLY','early',early),('CLOSE','close',close)]})]
        source={'provider-observations.json':json.dumps([obs]).encode(),'request-manifest.json':json.dumps(dict(requests=originals)).encode(),'canonical-games.json':json.dumps([dict(canonical_game_id='g',scheduled_utc=kick)]).encode()}
        data={'frame.json':json.dumps(frame).encode(),'slot-map.json':json.dumps(slotmap).encode(),'classifier-contract.json':json.dumps(dict(market='totals',reference='pinnacle',replace_failed_slots=False,book_panel=['draftkings'])).encode(),'protocol.json':json.dumps(dict(candidate_books=['draftkings'],primary_markets=list(self.mapping.MARKETS))).encode(),'code/plan.py':b'synthetic-code'}
        proof=dict(frame_sha256=self.capture.digest(data['frame.json']),requested_slot_map_sha256=self.capture.digest(data['slot-map.json']),contract_sha256=self.capture.digest(data['classifier-contract.json']),older_metadata_proof=dict(metadata_files={n:self.capture.digest(v) for n,v in source.items()},early_decision_rule_source_sha256=self.capture.digest(data['code/plan.py'])))
        data['certainty-source-proof.json']=json.dumps(proof).encode();maps=[dict(game_id='g',request_ids=['early','close'],metadata_disposition=dict(classification='unknown',reasons=[]))]
        self.assertTrue(m.verify(data,source,originals,{},maps,frame))
        zero=[dict(game_id='g',request_ids=[],reason='metadata_ineligible',metadata_disposition=dict(classification='failure',reasons=['CLOSE:provider_independent_conflict','EARLY:provider_independent_conflict']))]
        with self.assertRaises(ValueError):m.verify(data,source,originals,{},zero,frame)
        conflictframe=copy.deepcopy(frame);conflictframe[0]['scheduled_utc']='2020-10-02T17:00:00Z'
        conflictsource=copy.deepcopy(source);conflictsource['canonical-games.json']=json.dumps([dict(canonical_game_id='g',scheduled_utc=conflictframe[0]['scheduled_utc'])]).encode()
        conflictdata=copy.deepcopy(data);conflictdata['frame.json']=json.dumps(conflictframe).encode()
        cp=json.loads(conflictdata['certainty-source-proof.json']);cp['frame_sha256']=self.capture.digest(conflictdata['frame.json']);cp['older_metadata_proof']['metadata_files']['canonical-games.json']=self.capture.digest(conflictsource['canonical-games.json']);conflictdata['certainty-source-proof.json']=json.dumps(cp).encode()
        self.assertTrue(m.verify(conflictdata,conflictsource,originals,{},zero,conflictframe))
        with self.assertRaises(ValueError):m.verify(conflictdata,conflictsource,originals,{},maps,conflictframe)
        bad=copy.deepcopy(slotmap);bad[0]['slots']['CLOSE']['binding']=dict(obs,returned_utc='2020-10-02T15:55:00Z')
        data['slot-map.json']=json.dumps(bad).encode();proof['requested_slot_map_sha256']=self.capture.digest(data['slot-map.json']);data['certainty-source-proof.json']=json.dumps(proof).encode()
        with self.assertRaisesRegex(ValueError,'decision-time'):m.verify(data,source,originals,{},maps,frame)

    def test_provider_primary_offsets_and_authenticated_zero_failure_rule(self):
        mapping=self.load('mapping');utc=self.load('timing').utc
        # Exact six observed clock cases; synthetic identities and no quote payloads.
        cases=[('2021-08-28T17:20:00Z','2021-08-28T17:00:00Z','2021-08-28T16:55:00Z',False),
               ('2021-10-24T03:59:00Z','2021-10-24T04:00:00Z','2021-10-24T03:55:00Z',True),
               ('2022-10-16T03:59:00Z','2022-10-16T04:00:00Z','2022-10-16T03:55:00Z',True),
               ('2022-10-30T03:59:00Z','2022-10-30T04:00:00Z','2022-10-30T03:55:00Z',True),
               ('2022-09-04T03:59:00Z','2022-09-04T04:00:00Z','2022-09-04T03:55:00Z',True),
               ('2022-12-24T19:00:00Z','2022-12-24T18:00:00Z','2022-12-24T17:55:00Z',False)]
        from datetime import timedelta
        for independent,provider,close,valid in cases:
            # Pick an original16UTC early row within the independent18–54h window.
            early=(utc(independent)-timedelta(days=1)).replace(hour=16,minute=0,second=0).isoformat()
            if utc(independent)-utc(early)<timedelta(hours=18):early=(utc(early)-timedelta(days=1)).isoformat()
            rows=[dict(request_id='early',sport='nfl',requested_utc=early,purposes=['daily_16UTC']),dict(request_id='close',sport='nfl',requested_utc=close,purposes=['pregame_close_proxy'])]
            game=dict(game_id='g',season=2020,sport='nfl',binding=True,scheduled_utc=independent)
            slots={s:dict(request_id=rid,requested_utc=at,binding=dict(provider_kickoff_utc=provider,returned_utc=early)) for s,rid,at in [('EARLY','early',early),('CLOSE','close',close)]}
            with self.subTest(independent=independent):
                result=mapping.older_slots(game,rows,['close'],primary_close_id='close',primary_close_anchor=provider)
                self.assertEqual(result['primary_request_ids'],['early','close'])
                disposition=mapping.older_metadata_disposition(game,slots)
                self.assertEqual(disposition['classification'],'unknown' if valid else 'failure')
        evidence=self.load('evidence')
        args=dict(frame_sha256='a'*64,protocol_sha256='b'*64,draw_sha256='c'*64,evidence_sha256='d'*64,selected_ids=['g'],saved_bounds={},mappings=[dict(game_id='g',metadata_disposition=dict(classification='failure',reasons=['EARLY:provider_independent_conflict']))])
        with self.assertRaisesRegex(ValueError,'remain a failure'):evidence.final_record(**args,classifications={'g':True})
        self.assertFalse(evidence.final_record(**args,classifications={'g':False})['classifications']['g'])
