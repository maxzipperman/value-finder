import copy
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / 'sharp-markets/src/markets/research/props_grade'
sys.path.insert(0, str(SOURCE))
import union as U
import archive as A


def sample(season=2025):
    at = f'{season}-10-01T16:50:00Z'; kick = f'{season}-10-01T17:00:00Z'
    row = dict(request_id='r', event_id='e', requested_utc=at, seasons=[season])
    op = dict(season=season, opportunity_id='o', slot='CLOSE_T10', game_identity='g', identity_type='canonical',
              provider_kickoff_utc=kick, anchor_utc=kick, requested_utc=at,
              binding_observed_utc=f'{season}-09-30T00:00:00Z', schedule_discrepancy_minutes=0,
              home_team='Home', away_team='Away')
    event = dict(id='e', sport_key=A.NFL, commence_time=kick, home_team='Home', away_team='Away',
                 bookmakers=[dict(key='draftkings', last_update=f'{season}-10-01T16:48:00Z', markets=[
                     dict(key='player_rush_yds', outcomes=[dict(name=side, description='Player', point=50.5, price=1.91)
                                                        for side in ('Over', 'Under')])])])
    body = dict(timestamp=at, previous_timestamp=f'{season}-10-01T16:45:00Z',
                next_timestamp=f'{season}-10-01T16:55:00Z', data=event)
    return row, op, body


class UnionTests(unittest.TestCase):
    def test_generalized_quotes_preserve_legacy_2025_and_allow_only_three_seasons(self):
        row, op, body = sample()
        record = {'body': json.dumps(body)}
        self.assertEqual(A.quote_rows(row, [op], record, {'draftkings'}),
                         A.quote_rows(row, [op], record, {'draftkings'}, season=2025))
        for season in U.SEASONS:
            row, op, body = sample(season)
            quotes = A.quote_rows(row, [op], {'body': json.dumps(body)}, {'draftkings'}, season=season)
            self.assertEqual({r['season'] for r in quotes}, {season})
            self.assertEqual({r['role'] for r in quotes}, {'CLOSE_T10'})
        with self.assertRaisesRegex(ValueError, 'Sealed'):
            A.quote_rows({}, [], {'body': 'unparsed'}, set(), season=2026)
        row, op, body = sample(); body['data']['commence_time'] = '2026-09-01T00:00:00Z'
        with self.assertRaisesRegex(ValueError, 'sealed'):
            A.quote_rows(row, [op], {'body': json.dumps(body)}, set())

    def test_scope_full_denominators_provider_only_and_no_duplicate_or_2026(self):
        games = []
        for season, n in U.DENOMINATORS.items():
            for i in range(n):
                games.append(dict(game_id=f'{A.NFL}/{season}/{i}', season=season,
                    stratum=f'props/{A.NFL}/{season}', source_opportunities=[dict(
                    slot=slot, opportunity_id=f'{season}/{i}/{slot}', requested_utc=f'{season}-10-01T16:50:00Z') for slot in U.SLOTS]))
        U.validate_games(games)
        games[0]['game_id'] = f'{A.NFL}/provider-only/2023/unresolved'
        U.validate_games(games)  # Kept in denominator; never eligible by identity.
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            U.validate_games(games+[games[0]])
        games[0]['season'] = 2026
        with self.assertRaisesRegex(ValueError, 'sealed'):
            U.validate_games(games)

    def test_both_kickoff_clocks_and_freshness_are_exclusions(self):
        for change, reason in [('independent', 'not_scheduled_pregame'), ('provider', 'kickoff_conflict'),
                               ('future_quote', 'quote_age_at_snapshot'), ('old_quote', 'quote_age_at_snapshot'),
                               ('binding', 'listing_binding_after_decision')]:
            row, op, body = sample()
            if change=='independent': op['anchor_utc']=row['requested_utc']
            if change=='provider': op['provider_kickoff_utc']='2025-10-01T17:06:00Z'; op['schedule_discrepancy_minutes']=6
            if change=='future_quote': body['data']['bookmakers'][0]['last_update']='2025-10-01T16:51:00Z'
            if change=='old_quote': body['data']['bookmakers'][0]['last_update']='2025-10-01T16:20:00Z'
            if change=='binding': op['binding_observed_utc']='2025-10-01T16:51:00Z'
            got=A.quote_rows(row,[op],{'body':json.dumps(body)},{'draftkings'})
            self.assertTrue(all(reason in r['eligibility_reasons'] for r in got))

    def test_same_response_pairs_do_not_invent_cross_book_label_point_or_side(self):
        row, op, body = sample(); offers=body['data']['bookmakers'][0]['markets'][0]['outcomes']
        offers.pop(); quotes=A.quote_rows(row,[op],{'body':json.dumps(body)},{'draftkings'})
        got=U.pair_flags(quotes, {'r': set()})
        self.assertEqual({r['side'] for r in got}, {'Over'})
        self.assertFalse(any(r['quote_pair_eligible'] for r in got))
        key=('player_rush_yds','draftkings','Player',50.5)
        for accepted in [('player_rush_yds','pinnacle','Player',50.5),
                         ('player_rush_yds','draftkings','Other',50.5),
                         ('player_rush_yds','draftkings','Player',51.5)]:
            self.assertFalse(U.pair_flags(copy.deepcopy(quotes), {'r':{accepted}})[0]['quote_pair_eligible'])
        row, op, full=sample()
        full_quotes=A.quote_rows(row,[op],{'body':json.dumps(full)},{'draftkings'})
        self.assertTrue(all(r['quote_pair_eligible'] for r in U.pair_flags(full_quotes, {'r':{key}})))

    def test_actual_frozen_classifier_never_pairs_cross_response_sides(self):
        evidence=json.loads((ROOT/'reviews/post151-readiness/readiness.json').read_text())
        _, classifier, _, _=U.readers(evidence['provenance'])
        row, op, body=sample()
        binding=dict(status='bound',event_id='e',provider_kickoff_utc=op['provider_kickoff_utc'],
                     binding_observed_utc=op['binding_observed_utc'],home_team='Home',away_team='Away')
        args=dict(requested=row['requested_utc'],execution=row['requested_utc'],binding=binding,
                  independent_kickoff=op['anchor_utc'],slot='CLOSE_T10',candidate_books=['draftkings'],markets=A.PRIMARY)
        left=copy.deepcopy(body);right=copy.deepcopy(body)
        left['data']['bookmakers'][0]['markets'][0]['outcomes'].pop()
        right['data']['bookmakers'][0]['markets'][0]['outcomes'].pop(0)
        self.assertEqual(classifier.slot_pairs(left,**args)['pairs'],set())
        self.assertEqual(classifier.slot_pairs(right,**args)['pairs'],set())
        self.assertEqual(len(classifier.slot_pairs(body,**args)['pairs']),1)
        body['data']['bookmakers'][0]['markets'][0]['outcomes'][1]['point']=51.5
        self.assertEqual(classifier.slot_pairs(body,**args)['pairs'],set())

    def test_conflicting_duplicates_not_rescued_and_no_grading(self):
        row, op, body=sample(); quotes=A.quote_rows(row,[op],{'body':json.dumps(body)},{'draftkings'})
        extra=copy.deepcopy(quotes[0]); extra['price']=2.1;quotes.append(extra)
        accepted={'r':{('player_rush_yds','draftkings','Player',50.5)}}
        got=U.pair_flags(quotes,accepted)
        self.assertTrue(all('conflicting_duplicate_quote' in r['eligibility_reasons'] for r in got))
        self.assertFalse(any(r['quote_pair_eligible'] or r['grading_enabled'] for r in got))

    def test_missing_unresolved_cells_remain_in_every_book_denominator(self):
        games=[dict(game_id='unresolved',season=2025,identity_type='provider_only_unresolved',source_opportunities=[
            dict(slot=s,requested_utc='2025-10-01T16:50:00Z') for s in U.SLOTS]),
            dict(game_id='g',season=2025,identity_type='canonical',source_opportunities=[
            dict(slot=s,requested_utc='2025-10-01T16:50:00Z') for s in U.SLOTS])]
        p=dict(receipt_projection={},ledger_pins={},classifier_sha256='c',timing_sha256='t',original_final_sha256='f')
        classifier=type('Classifier',(),{'bind_asof':staticmethod(lambda *_: {'status':'bound'})})
        with patch.object(U,'metadata',return_value=({'provenance':p},games,{}, {},[{'canonical_game_id':'g'}],[],{})), \
             patch.object(U,'readers',return_value=(None,classifier,None,lambda *_:[])):
            quotes, report=U.project(Path('/unused'),'eligibility')
        self.assertEqual(quotes,[])
        self.assertEqual(report['statuses']['fixed_opportunities'],4)
        self.assertEqual(report['statuses']['missing_designated_opportunities'],2)
        self.assertEqual(report['statuses']['unresolved_identity_opportunities'],2)
        self.assertEqual(len(report['coverage']),40)
        self.assertTrue(all(r['game_denominator']==2 for r in report['coverage']))
        self.assertFalse(report['grading_enabled'] or report['outcomes_read'])

    def test_dry_run_does_not_call_saved_raw_reader_and_mode_cannot_grade(self):
        with self.assertRaisesRegex(ValueError,'No grading'):
            U.read_union(Path('/unused'),mode='grade')
        with self.assertRaisesRegex(ValueError,'accepted shared runtime'):
            U.read_union(Path('/unused'))
        games=[dict(game_id='g',season=2025,identity_type='canonical',certainty_evidence={'source_request_ids':['must-not-read']},
                    source_opportunities=[dict(slot=s,requested_utc='2025-10-01T16:50:00Z') for s in U.SLOTS])]
        p=dict(receipt_projection={'must-not-read':{}},ledger_pins={},classifier_sha256='c',timing_sha256='t',original_final_sha256='f')
        classifier=type('Classifier',(),{'bind_asof':staticmethod(lambda *_: {'status':'bound'})})
        def forbidden(*args,**kwargs): self.fail('Dry run opened a raw receipt')
        with patch.object(U,'metadata',return_value=({'provenance':p},games,{}, {},[{'canonical_game_id':'g'}],[],{})), \
             patch.object(U,'readers',return_value=(None,classifier,forbidden,lambda *_:[])):
            quotes, dry=U.project(Path('/unused'),'dry-run')
        self.assertEqual(quotes,[])
        self.assertEqual(dry['authenticated_records'],0)
        # Published native dry-run likewise retains every fixed opportunity.
        root=ROOT/'sharp-markets/docs/props-union'
        report=json.loads((root/'dry-run.json').read_text())
        self.assertEqual(report['authenticated_records'],0)
        self.assertEqual(report['statuses']['fixed_opportunities'],1774)

    def test_measured_union_matrix_and_hold_invariants(self):
        root=ROOT/'sharp-markets/docs/props-union'
        matrix=json.loads((root/'discovery-matrix.json').read_text())
        self.assertEqual(matrix['additional_deciding_cells'],len(matrix['cells']))
        self.assertEqual(len({r['id'] for r in matrix['cells']}),8)
        self.assertIsNone(matrix['global_count'])
        self.assertEqual(matrix['original_pooled_variant_already_counted'],1)
        report=json.loads((root/'eligibility.json').read_text())
        self.assertEqual(sum(report['fixed_games'].values()),887)
        self.assertEqual(report['fixed_opportunities'],1774)
        self.assertFalse(report['grading_enabled'] or report['outcomes_read'] or report['actual_play_certified'])
        self.assertEqual(set(report['holds']),set(U.HOLDS))
        self.assertTrue(all(r['game_denominator']==U.DENOMINATORS[r['season']] for r in report['coverage']))
        self.assertEqual(report['reader_sha256'],A.digest(A.regular(SOURCE/'union.py')))
        self.assertEqual(report['archive_reader_sha256'],A.digest(A.regular(SOURCE/'archive.py')))

    def test_receipt_byte_checks_reject_changes_and_symlinks(self):
        with tempfile.TemporaryDirectory() as name:
            p=Path(name).resolve()/'receipt';p.write_bytes(b'original'); pin=A.digest(p.read_bytes())
            p.write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'hash mismatch'):A.checked(p,pin)
            alias=p.with_name('alias');alias.symlink_to(p)
            with self.assertRaisesRegex(ValueError,'nonsymlink'):A.regular(alias)

if __name__=='__main__':unittest.main()
