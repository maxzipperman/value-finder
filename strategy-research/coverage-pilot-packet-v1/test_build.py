"""Offline deterministic assembly helpers only; no actual draw/history/API access."""
import copy
from pathlib import Path
import sys
import unittest
import build
sys.path.insert(0,str(Path(__file__).parent.parent/'coverage-pilot-v1'))
from test_integration import loader

class BuildTests(unittest.TestCase):
    def test_five_percent_finite_caps_and_no_metadata_404(self):
        rows=[dict(request_id=str(i),source='oddsapi/hist_event_odds' if i<21 else 'oddsapi/hist_odds') for i in range(41)]
        p=build.missing_policy(rows)
        self.assertEqual(p['max_missing'],dict(snapshot_lag=3,event_not_found=2))
        self.assertEqual(len(p['event_not_found_ids']),21)
        self.assertEqual(build.missing_policy([])['max_missing'],dict(snapshot_lag=0,event_not_found=0))

    def test_partial_props_reuse_deterministic_complete_union(self):
        load=loader();plan=load('plan');mapping=load('mapping');sport=plan.NFL
        ops=[dict(opportunity_id='g/'+slot,slot=slot,event_id='abc',requested_utc=at,status='bound') for slot,at in [('T24','2023-10-01T16:00:00Z'),('CLOSE_T10','2023-10-02T15:50:00Z')]]
        frame=[dict(game_id='g',season=2023,stratum='props/'+sport+'/2023',source_opportunities=ops)]
        row=plan.make_request('odds',plan.ts(ops[0]['requested_utc']),books=['draftkings'],markets=['player_pass_yds'],event_id='abc',sport=sport)
        claim=dict(root='historical',request_id=row['request_id'],response_sha256='a'*64,receipt_sha256='b'*64)
        prior=[dict(row,status='completed',claim=claim)]
        a=build.selected_union(frame,dict(selected=['g']),[],[],prior,load,['draftkings'])
        b=build.selected_union(frame,dict(selected=['g']),[],[],prior,load,['draftkings'])
        self.assertEqual(a,b);rows,maps=a
        self.assertEqual(sum(r['max_new_credits'] for r in rows),110)
        self.assertEqual(len(maps[0]['reused_slots']),1)
        self.assertNotIn('player_pass_yds',next(r for r in rows if r['requested_utc']==ops[0]['requested_utc'])['params']['markets'].split(','))
        self.assertTrue(load('overlap').check_internal(rows,maps))
        missing=copy.deepcopy(prior);missing[0].pop('claim')
        with self.assertRaisesRegex(ValueError,'no terminal'):build.selected_union(frame,dict(selected=['g']),[],[],missing,load,['draftkings'])

    def test_old_shared_ID_deduplicated_and_rawless_attempt_blocks(self):
        load=loader();plan=load('plan');sport=plan.NFL
        frame=[dict(game_id=g,season=2020,stratum='older/'+sport+'/2020',scheduled_utc='2020-10-02T16:00:00Z') for g in ('a','b')]
        slotmap=[dict(game_id=g,slots={slot:dict(request_id=rid,requested_utc=at,binding=dict(returned_utc='2020-10-01T16:00:00Z',provider_kickoff_utc='2020-10-02T16:00:00Z')) for slot,rid,at in [('EARLY','e','2020-10-01T16:00:00Z'),('CLOSE','c','2020-10-02T15:50:00Z')]}) for g in ('a','b')]
        originals=[dict(request_id=rid,priority=2,max_new_credits=30,path='/historical/sports/'+sport+'/odds',source='oddsapi/hist_odds',sport=sport,params={'date':at,'bookmakers':'draftkings','markets':'totals'},requested_utc=at) for rid,at in [('e','2020-10-01T16:00:00Z'),('c','2020-10-02T15:50:00Z')]]
        rows,maps=build.selected_union(frame,dict(selected=['a','b']),slotmap,originals,[],load,['draftkings'])
        self.assertEqual(len(rows),2);self.assertEqual(maps[0]['request_ids'],maps[1]['request_ids'])
        with self.assertRaisesRegex(ValueError,'raw-less'):build.selected_union(frame,dict(selected=['a']),slotmap,originals,[dict(request_id='e',status='missing')],load,['draftkings'])


    def test_pending_protocol_stops_before_seed_or_live_state(self):
        import json
        import tempfile
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory(dir='/private/tmp') as d:
            p=Path(d)/'protocol.json';p.write_text(json.dumps({'execution_status':'pending_predraw_review'}))
            import subprocess
            subprocess.run(['git','init','-q',d],check=True)
            args=SimpleNamespace(repo=Path(d),output=Path(d)/'new',protocol=p,protocol_sha256=build.sha(p.read_bytes()))
            with self.assertRaisesRegex(ValueError,'review still pending'):build.assemble(args)

    def test_frozen_probe_metadata_positive_and_mutated_claims_reject(self):
        # Immutable fixture bytes, request-metadata projection only; no quote decode.
        import json
        load=loader();capture=load('capture');evidence=load('evidence')
        bundle=Path(__file__).parent.parent/'football_archive/acquisition/football-archive-v4'
        freeze=(bundle/'FREEZE.json').read_bytes();cert=json.loads(freeze)
        context=dict(freeze=freeze,files={n:(bundle/n).read_bytes() for n in cert['file_sha256']})
        history=build.frozen_probe_history(context,load);by_id={r['request_id']:r for r in history}
        required=['31b3ecac3fd76c60be7745154cc6c32b7e64c1e1e7435da98727077e1431cf77','f83083e502e49a1e9ceda0fe8815dfe69d1da43764104ae22423c2d9bba6f8f9']
        for rid in required:
            claim=by_id[rid]['claim']
            maps=[dict(reused_request_ids=[rid],reused_evidence=[claim])]
            self.assertTrue(evidence.authenticate_reuse('unused',{'ledgers':{}},maps,frozen_source=context))
            rec=evidence.frozen_probe_record(claim,context)
            with self.assertRaisesRegex(ValueError,'paid/reused'):load('overlap').check_internal([dict(rec,request_id=rid)],maps)
            for key,value in [('source_bundle_root','0'*64),('request_id','0'*64),('cache_source','reuse/wrong.parquet'),('cache_sha256','0'*64),('probe_ledger_sha256','0'*64),('probe_attempt_sha256','0'*64),('request_manifest_sha256','0'*64)]:
                bad=dict(claim,**{key:value})
                with self.subTest(rid=rid,key=key),self.assertRaises(ValueError):evidence.frozen_probe_record(bad,context)
            missing=copy.deepcopy(context);missing['files'][claim['cache_source']]=b'changed'
            with self.assertRaises(ValueError):evidence.frozen_probe_record(claim,missing)
        self.assertEqual(len(required),2)


    def test_output_confined_before_seed_live_state_or_write(self):
        import subprocess
        import tempfile
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory(dir='/private/tmp') as d:
            repo=Path(d)/'repo';repo.mkdir();subprocess.run(['git','init','-q',str(repo)],check=True)
            self.assertEqual(build.validate_output(repo,Path('new')),(repo,repo/'new'))
            for output in (Path('../escape'),Path(d)/'escape',Path.home()/'code/value-finder/new',Path.home()/'Library/Application Support/ValueFinder/football-acquisition-state/new'):
                with self.subTest(output=str(output)),self.assertRaises(ValueError):build.validate_output(repo,output)
            link=repo/'link';link.symlink_to(Path(d),target_is_directory=True)
            with self.assertRaisesRegex(ValueError,'symlink'):build.validate_output(repo,link/'new')
            linkrepo=Path(d)/'linkrepo';linkrepo.symlink_to(repo,target_is_directory=True)
            with self.assertRaisesRegex(ValueError,'symlink'):build.validate_output(linkrepo,linkrepo/'new')
            existing=repo/'existing';existing.mkdir()
            with self.assertRaisesRegex(ValueError,'new directory'):build.validate_output(repo,existing)
            # Escaped output is rejected even when protocol/seed paths do not exist.
            with self.assertRaisesRegex(ValueError,'strictly inside'):
                build.assemble(SimpleNamespace(repo=repo,output=Path(d)/'escape'))


    def test_bootstrap_capture_mismatch_and_verified_bytes_after_mutation(self):
        import tempfile
        with tempfile.TemporaryDirectory(dir='/private/tmp') as d:
            repo=Path(d);pilot=repo/'strategy-research/coverage-pilot-v1';pilot.mkdir(parents=True)
            path=pilot/'bootstrap.py';marker=repo/'executed'
            evil=f"from pathlib import Path\nPath({str(marker)!r}).write_text('executed')\nraise RuntimeError('UNPINNED_EXECUTED')\n".encode()
            path.write_bytes(evil)
            with self.assertRaisesRegex(ValueError,'hash differs'):
                build.closure(repo,{'source_code_sha256':{'bootstrap':'0'*64}})
            self.assertFalse(marker.exists())
            # Capture mismatch uses the SAME verification-before-exec primitive.
            with self.assertRaisesRegex(ValueError,'hash differs'):build.pinned_module(evil,path,'capture','0'*64)
            self.assertFalse(marker.exists())
            old=b'VERIFIED_VALUE=42\n';path.write_bytes(old);raw=build.regular(path)
            path.write_bytes(evil)
            result=build.pinned_module(raw,path,'capture',build.sha(old))
            self.assertEqual(result.VERIFIED_VALUE,42);self.assertFalse(marker.exists())
