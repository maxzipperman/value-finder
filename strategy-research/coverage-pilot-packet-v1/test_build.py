"""Offline deterministic assembly helpers only; no actual draw/history/API access."""
import copy
import importlib.util
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
        frame=[dict(game_id=g,season=2020,stratum='older/'+sport+'/2020') for g in ('a','b')]
        slotmap=[dict(game_id=g,slots={'EARLY':{'request_id':'e'},'CLOSE':{'request_id':'c'}}) for g in ('a','b')]
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
            args=SimpleNamespace(repo=Path(d),protocol=p,protocol_sha256=build.sha(p.read_bytes()))
            with self.assertRaisesRegex(ValueError,'review still pending'):build.assemble(args)
