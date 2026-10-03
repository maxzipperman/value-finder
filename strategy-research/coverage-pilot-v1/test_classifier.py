import copy
import unittest
from classifier import bind_asof, slot_pairs, props_feasibility, older_totals_feasibility
from mapping import older_slots, early_rank
from timing import utc

class ClassifierTests(unittest.TestCase):
    def obs(self,**kw):
        return dict(dict(canonical_game_id='g',provider_id='early-id',returned_utc='2020-10-01T16:00:00Z',provider_kickoff_utc='2020-10-02T16:00:00Z',home_team='A',away_team='B'),**kw)

    def test_latest_across_aliases_never_future_close_binding(self):
        observations=[self.obs(returned_utc='2020-10-01T10:00:00Z',provider_id='stale'),self.obs(),self.obs(returned_utc='2020-10-02T15:00:00Z',provider_id='close-id')]
        bound=bind_asof(observations,'g','2020-10-01T16:00:00Z')
        self.assertEqual(bound['event_id'],'early-id');self.assertEqual(bound['stale_alias_count'],1)
        for change in [dict(provider_id='conflict'),dict(provider_kickoff_utc='2020-10-02T17:00:00Z'),dict(home_team='B',away_team='A')]:
            self.assertEqual(bind_asof(observations+[self.obs(**change)],'g','2020-10-01T16:00:00Z')['status'],'unbound')

    def test_daily_source_only_and_primary_diagnostic_separation(self):
        game=dict(game_id='g',season=2020,sport='nfl',binding=True,scheduled_utc='2020-10-02T17:00:00Z')
        rows=[dict(request_id='z-daily',sport='nfl',requested_utc='2020-10-01T16:00:00Z',purposes=['daily_16UTC']),
              dict(request_id='a-closer-nondaily',sport='nfl',requested_utc='2020-10-01T17:00:00Z',purposes=['pregame_close_proxy']),
              dict(request_id='close',sport='nfl',requested_utc='2020-10-02T16:50:00Z',purposes=['pregame_close_proxy']),
              dict(request_id='diagnostic',sport='nfl',requested_utc='2020-10-02T16:45:00Z',purposes=['alternate_independent_close_proxy'])]
        result=older_slots(game,rows,['close','diagnostic'],primary_close_id='close')
        self.assertEqual(result['request_ids'],['z-daily','close']);self.assertEqual(result['diagnostic_request_ids'],['diagnostic'])
        # A daily label alone is insufficient if the actual clock is not16UTC.
        rows[0]['requested_utc']='2020-10-01T15:00:00Z'
        self.assertEqual(older_slots(game,rows,['close'],primary_close_id='close')['reason'],'missing_original_slot')

    def test_rank_tie_prefers_earlier_clock_over_lexicographic_id(self):
        # Ranking contract independently tested; source16UTC filter is tested above.
        # Strict16UTC daily spacing does not itself supply18h/30h equidistant rows.
        earlier=dict(request_id='z-earlier',requested_utc='2020-10-01T06:00:00Z')
        later=dict(request_id='a-later',requested_utc='2020-10-01T18:00:00Z')
        kickoff=utc('2020-10-02T12:00:00Z')
        self.assertLess(early_rank(earlier,kickoff),early_rank(later,kickoff))

    def test_family_specific_pairs_do_not_require_same_player_or_book_across_families(self):
        early={'pairs':{('player_pass_yds','draftkings','QB',200),('player_receptions','fanduel','WR',4)}}
        close={'pairs':{('player_pass_yds','draftkings','QB',210),('player_receptions','fanduel','WR',4)}}
        result=props_feasibility(early,close)
        self.assertTrue(result['success']);self.assertFalse(result['same_point_success'])
        self.assertFalse(result['grading_enabled'])
        changed={'pairs':{('player_pass_yds','fanduel','QB',200),('player_receptions','fanduel','WR',4)}}
        self.assertFalse(props_feasibility(early,changed)['success'])

    def test_totals_requires_retail_and_reference_both_slots(self):
        early={'pairs':{('totals','draftkings','__total__',44),('totals','pinnacle','__total__',44)}}
        close={'pairs':{('totals','draftkings','__total__',43),('totals','pinnacle','__total__',43)}}
        self.assertTrue(older_totals_feasibility(early,close,['draftkings'])['success'])
        close['pairs'].remove(('totals','pinnacle','__total__',43))
        self.assertFalse(older_totals_feasibility(early,close,['draftkings'])['success'])

    def test_close_equality_and_two_sides_same_point(self):
        binding=bind_asof([self.obs()],'g','2020-10-02T15:50:00Z')
        body=dict(timestamp='2020-10-02T15:50:00Z',previous_timestamp='2020-10-02T15:45:00Z',next_timestamp='2020-10-02T15:55:00Z',
                  data=dict(id='early-id',commence_time='2020-10-02T16:00:00Z',home_team='A',away_team='B',bookmakers=[dict(key='draftkings',last_update='2020-10-02T15:50:00Z',markets=[dict(key='totals',outcomes=[dict(name='Over',point=44,price=1.91),dict(name='Under',point=44,price=1.91)])])]))
        args=dict(requested='2020-10-02T15:50:00Z',execution='2020-10-02T15:50:00Z',binding=binding,independent_kickoff='2020-10-02T15:55:00Z',slot='CLOSE_T10',candidate_books=['draftkings'],markets=['totals'])
        self.assertEqual(len(slot_pairs(body,**args)['pairs']),1)
        boundary=slot_pairs(body,**dict(args,requested='2020-10-02T15:55:00Z',execution='2020-10-02T15:55:00Z'))
        self.assertEqual(boundary['pairs'],set())
        body['data']['bookmakers'][0]['markets'][0]['outcomes'][1]['point']=45
        self.assertEqual(slot_pairs(body,**args)['pairs'],set())
