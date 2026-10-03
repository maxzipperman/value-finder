import unittest
import json
from pathlib import Path
import plan


class PlanningTests(unittest.TestCase):
    def setUp(self):
        self.at = plan.ts('2025-10-01T06:00:00Z')
        self.books = [f'book{i}' for i in range(10)]
        self.markets = [f'player_stat{i}' for i in range(59)]

    def test_partial_market_union_never_repays_six(self):
        rows = plan.residual_requests('event', self.at, plan.cells(self.books,self.markets), plan.cells(self.books,self.markets[:6]))
        self.assertEqual(sum(r['max_new_credits'] for r in rows),530)
        self.assertTrue(all(not set(r['params']['markets'].split(',')) & set(self.markets[:6]) for r in rows))

    def test_twenty_book_partial_union(self):
        books=self.books+[f'other{i}' for i in range(10)]
        rows=plan.residual_requests('event',self.at,plan.cells(books,self.markets),plan.cells(self.books,self.markets[:6]))
        self.assertEqual(sum(r['max_new_credits'] for r in rows),1120)
        emitted=set()
        for r in rows:
            c=plan.cells(r['params']['bookmakers'].split(','),r['params']['markets'].split(','))
            self.assertFalse(c & emitted);emitted |= c
        self.assertEqual(emitted,plan.cells(books,self.markets)-plan.cells(self.books,self.markets[:6]))

    def test_uncertain_subset_blocks_superset(self):
        with self.assertRaisesRegex(ValueError,'never replace'):
            plan.residual_requests('event',self.at,plan.cells(self.books,self.markets),blocked={(self.books[0],self.markets[0])})

    def test_covered_and_uncertain_does_not_clear_uncertainty(self):
        c={('a','player_x')}
        with self.assertRaises(ValueError):plan.residual_requests('event',self.at,c,c,c)

    def test_cost_book_band_and_both_sides(self):
        for n,cost in [(1,10),(10,10),(11,20),(20,20),(21,30)]:
            r=plan.make_request('odds',self.at,[str(i) for i in range(n)],['player_rush_yds'],'event')
            self.assertEqual(r['max_new_credits'],cost)
            self.assertNotIn('side',r['params'])

    def test_sealed_sport_and_time_bounds(self):
        for date in ['2026-09-01T00:00:00Z','2023-05-03T05:25:00Z']:
            with self.assertRaises(ValueError):plan.make_request('events',plan.ts(date))
        with self.assertRaises(ValueError):plan.make_request('events',self.at,sport='basketball_nba')
        self.assertEqual(plan.make_request('events',plan.ts('2026-02-09T23:55:00Z'))['max_new_credits'],1)

    def test_deterministic_order(self):
        a=plan.make_request('odds',self.at,['a','b'],['player_x','player_y'],'event')
        b=plan.make_request('odds',self.at,['b','a'],['player_y','player_x'],'event')
        self.assertEqual(a,b)

    def test_duplicate_inputs_rejected(self):
        with self.assertRaises(ValueError):plan.make_request('odds',self.at,['a','a'],['player_x'],'event')
        with self.assertRaises(ValueError):plan.make_request('odds',self.at,['a'],['player_x','player_x'],'event')

    def test_no_hindsight_binding(self):
        game={'sport':plan.NFL,'season':2025,'canonical_game_id':'g','external_game_id':'g','scheduled_utc':'2025-10-02T06:00:00Z','close_anchor_utc':'2025-10-02T06:00:00Z'}
        o={'sport':plan.NFL,'season':2025,'canonical_game_id':'g','provider_id':'event','returned_utc':'2025-10-01T06:05:00Z','provider_kickoff_utc':game['scheduled_utc'],'home_team':'h','away_team':'a'}
        rows=plan.opportunities([game],[o],[],['T24'])
        self.assertEqual(rows[0]['status'],'unbound')
        o['returned_utc']='2025-10-01T05:55:00Z'
        self.assertEqual(plan.opportunities([game],[o],[],['T24'])[0]['status'],'bound')

    def test_ambiguity_retained(self):
        game={'sport':plan.CFB,'season':2025,'canonical_game_id':'g','external_game_id':'g','scheduled_utc':'2025-10-02T06:00:00Z','close_anchor_utc':'2025-10-02T06:00:00Z'}
        a={'sport':plan.CFB,'season':2025,'canonical_game_id':'g','provider_id':'e1','returned_utc':'2025-10-01T05:55:00Z','provider_kickoff_utc':game['scheduled_utc'],'home_team':'h','away_team':'a'}
        b=dict(a,provider_id='e2')
        self.assertEqual(plan.opportunities([game],[a,b],[],['T24'],plan.CFB)[0]['status'],'ambiguous')

    def test_availability_required_for_every_target(self):
        ops=[{'status':'bound','event_id':'e','requested_utc':plan.iso(self.at),'opportunity_id':'g/T24'}]
        with self.assertRaises(ValueError):plan.all_book_requests(ops,[],[])
        avail=[{'event_id':'e','requested_utc':plan.iso(self.at),'status':'verified_completed','book_markets':{'a':['player_x','h2h']}}]
        rows=plan.all_book_requests(ops,avail,[])
        self.assertEqual(rows[0]['params']['markets'],'player_x')
        avail[0]['status']='pending'
        with self.assertRaises(ValueError):plan.all_book_requests(ops,avail,[])

    def test_sports_have_separate_cache_coverage(self):
        op={'status':'bound','event_id':'e','requested_utc':plan.iso(self.at),'opportunity_id':'g/T24'}
        inv=[{'sport':plan.NFL,'event_id':'e','requested_utc':plan.iso(self.at),'status':'verified_completed','books':['a'],'requested_markets':['player_x']}]
        self.assertEqual(plan.price_requests([op],['player_x'],['a'],inv,plan.CFB)[0][0]['max_new_credits'],10)

    def test_catalog_and_daily_discovery(self):
        path=Path(__file__).parent
        nfl=json.loads((path/'catalog.json').read_text())['markets']
        cfb=json.loads((path/'cfb-catalog.json').read_text())['markets']
        self.assertEqual((len(nfl),len(cfb)),(59,33))
        self.assertTrue(all(not x.endswith('_alternate') for x in cfb))
        for sport in (plan.NFL,plan.CFB):
            rows=plan.listing_requests(sport)
            self.assertEqual(len(rows),1014)
            self.assertEqual(len(set(r['request_id'] for r in rows)),1014)
            self.assertTrue(all(r['requested_utc'].endswith('06:00:00Z') for r in rows))


if __name__=='__main__':unittest.main()
