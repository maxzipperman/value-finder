import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
import diagnostic as d


class ReadinessTests(unittest.TestCase):
    def test_measured_artifact_preserves_all_fixed_denominators_and_missing_events(self):
        measured = json.loads(Path(__file__).with_name('readiness.json').read_text())
        self.assertEqual(sum(measured['denominators'].values()), 2401)
        keys = [(r['sport'], r['season'], r['market'], r['book'], r['slot']) for r in measured['coverage']]
        self.assertEqual(len(keys), len(set(keys)))
        for row in measured['coverage']:
            group = ('older' if row['market'] == 'totals' else 'props') + '/' + row['sport'] + '/' + str(row['season'])
            self.assertEqual(row['game_denominator'], measured['denominators'][group])
            self.assertLessEqual(row['games_with_pairs'], row['game_denominator'])
        current = [r for r in measured['provenance']['receipt_projection'].values() if r['root'] == d.ROOT]
        self.assertEqual(len(current), 1290)
        self.assertEqual(sum(r['status'] == 'missing' for r in current), 2)
        self.assertFalse(measured['grading_enabled'])
        self.assertFalse(measured['actual_play_certified'])
        self.assertFalse(measured['provenance']['native_outcomes_read'])
        self.assertEqual(d.sha(Path(__file__).with_name('diagnostic.py').read_bytes()), measured['provenance']['diagnostic_sha256'])

    def test_temporal_points_do_not_require_common_cross_book_point(self):
        import ast
        source = Path(__file__).resolve().parents[2] / 'strategy-research/coverage-pilot-v1/classifier.py'
        node = next(n for n in ast.parse(source.read_text()).body
                    if isinstance(n, ast.FunctionDef) and n.name == 'older_totals_feasibility')
        namespace = {}
        exec(compile(ast.Module(body=[node], type_ignores=[]), str(source), 'exec'), namespace)
        slot = {'pairs': {('totals', 'draftkings', '__total__', 40),
                          ('totals', 'pinnacle', '__total__', 42)}}
        result = namespace['older_totals_feasibility'](slot, slot, ['draftkings'])
        self.assertTrue(result['same_point_success'])
        self.assertEqual({p[3] for p in slot['pairs']}, {40, 42})
        measured = json.loads(Path(__file__).with_name('readiness.json').read_text())
        self.assertEqual(sum(r['each_book_preserves_own_point_across_slots']
                             for r in measured['older_paired_readiness'].values()), 334)
        self.assertTrue(all('four_quote_sets_same_point' not in r
                            for r in measured['older_paired_readiness'].values()))

    def test_slot_failure_leaves_opposite_slot_quotes_visible(self):
        slot_quotes = {('totals', 'draftkings', '__total__', 40),
                       ('totals', 'pinnacle', '__total__', 42)}
        for failed, valid in [('EARLY_18_54', 'CLOSE_T10'), ('CLOSE_T10', 'EARLY_18_54')]:
            prefix = 'EARLY' if failed == 'EARLY_18_54' else 'CLOSE'
            mapping = {'metadata_disposition': {'classification': 'failure',
                       'reasons': [prefix + ':provider_independent_conflict']}}
            projected = {slot: set() if d.frozen_failures_for_slot(mapping, slot) else slot_quotes
                         for slot in (failed, valid)}
            self.assertEqual(projected[failed], set())
            self.assertEqual(projected[valid], slot_quotes)
            self.assertTrue(d.metrics({'pairs': projected[valid]}, 'totals', 'draftkings')['present'])
            self.assertFalse(d.metrics({'pairs': projected[failed]}, 'totals', 'draftkings')['present'])
            self.assertEqual(mapping['metadata_disposition']['classification'], 'failure')

    def test_global_unknown_and_reasonless_failures_stay_fail_closed(self):
        for disposition in ({'reasons': ['unqualified_failure']},
                            {'reasons': ['UNKNOWN:provider_independent_conflict']},
                            {'reason': 'certified_quarantined_response'}, {},
                            {'reasons': ['EARLY:outside_early_horizon', 'global_failure']}):
            mapping = {'coverage_disposition': dict(classification='failure', **disposition)}
            for slot in ('EARLY_18_54', 'CLOSE_T10'):
                self.assertTrue(d.frozen_failures_for_slot(mapping, slot))
        both = {'metadata_disposition': {'classification': 'failure',
                'reasons': ['EARLY:provider_independent_conflict', 'CLOSE:provider_independent_conflict']}}
        self.assertEqual(d.frozen_failures_for_slot(both, 'CLOSE_T10'), ['CLOSE:provider_independent_conflict'])
        with self.assertRaisesRegex(ValueError, 'unknown diagnostic slot'):
            d.frozen_failures_for_slot(both, 'unknown')

    def test_slot_repair_artifact_preserves_gates_and_exact_deltas(self):
        root = Path(__file__).parent
        measured = json.loads((root / 'readiness.json').read_text())
        delta = json.loads((root / 'slot-correction-delta.json').read_text())
        self.assertEqual(delta['unchanged_denominators'], measured['denominators'])
        self.assertEqual(delta['unchanged_older_paired_readiness'], measured['older_paired_readiness'])
        self.assertEqual(delta['new_book_game_close_pairs'], 14)
        self.assertEqual(delta['clock_count_changes']['snapshot_0_600']['delta'], 2)
        self.assertEqual(delta['clock_count_changes']['quote_decision_0_1500']['delta'], 42)
        self.assertEqual(delta['exclusion_record_count']['after'], len(measured['exclusions']))
        self.assertEqual(sum(r['same_domestic_plus_reference_both_slots']
                             for r in measured['older_paired_readiness'].values()), 1267)
        self.assertTrue(all(r['key'][2] == 'totals' for r in delta['changed_coverage_rows']))
        self.assertTrue(all(r['after'] in measured['coverage'] for r in delta['changed_coverage_rows']))
        exclusions = {(r['game_id'], r['slot']): r for r in measured['exclusions']}
        for gid in ('americanfootball_ncaaf/2020/401249032', 'americanfootball_nfl/2020/2020_12_BAL_PIT'):
            self.assertIn('no_designated_matching_snapshot', exclusions[(gid, 'CLOSE_T10')]['reasons'])
        for gid in ('americanfootball_ncaaf/2020/401249878', 'americanfootball_nfl/2020/2020_17_TEN_HOU'):
            self.assertNotIn((gid, 'CLOSE_T10'), exclusions)

    def test_missing_older_slots_still_have_both_denominators(self):
        game = {'stratum': 'older/americanfootball_nfl/2020', 'game_id': 'g'}
        ops = d.operations(game, {})
        self.assertEqual([o['slot'] for o in ops], ['EARLY_18_54', 'CLOSE_T10'])
        self.assertTrue(all(o['requested_utc'] is None for o in ops))

    def test_missing_other_slot_cannot_poison_this_slot(self):
        rec = {'params_json': json.dumps({'date': 'early'}), 'sport': 'nfl', 'url': '/events/id/odds'}
        self.assertFalse(d.matches(rec, 'nfl', 'close', 'id'))
        self.assertTrue(d.matches(rec, 'nfl', 'early', 'id'))
        with self.assertRaises(ValueError): d.matches(rec, 'cfb', 'early', 'id')
        with self.assertRaises(ValueError): d.matches(rec, 'nfl', 'early', 'another')

    def test_primary_family_book_and_provider_label_counts_stay_separate(self):
        result = {'pairs': {('player_rush_yds', 'draftkings', 'label', 10),
                            ('player_rush_yds', 'draftkings', 'label', 11),
                            ('player_reception_yds', 'draftkings', 'label', 20),
                            ('player_rush_yds', 'pinnacle', 'label', 10)}}
        self.assertEqual(d.metrics(result, 'player_rush_yds', 'draftkings'),
                         {'pairs': 2, 'players': 1, 'present': True})
        self.assertFalse(d.metrics(result, 'player_pass_yds', 'draftkings')['present'])
        self.assertFalse(d.metrics({'pairs': set()}, 'player_rush_yds', 'draftkings')['present'])

    def test_schema_access_never_reads_outcome_values(self):
        with tempfile.TemporaryDirectory() as name:
            path = Path(name).resolve() / 'schema.parquet'; path.touch()
            fake = SimpleNamespace(ParquetFile=lambda _: SimpleNamespace(schema_arrow=SimpleNamespace(names=['rushing_yards'])))
            self.assertEqual(d.schema_columns(path, fake), ['rushing_yards'])
            self.assertEqual(d.schema_columns(path.parent / 'missing', fake), [])
            link = path.with_name('alias.parquet'); link.symlink_to(path)
            with self.assertRaisesRegex(ValueError, 'symlink'): d.schema_columns(link, fake)

    def test_age_clocks_are_separate(self):
        from datetime import datetime
        body = {'timestamp': '2025-01-01T00:05:00+00:00', 'data': {'id': 'e', 'commence_time': 'later',
                'bookmakers': [{'markets': [{'last_update': '2025-01-01T00:00:00+00:00'}]}]}}
        result = d.describe_ages(body, {'event_id': 'e'}, '2025-01-01T00:10:00+00:00', datetime.fromisoformat)
        self.assertEqual(result['snapshot_age_seconds'], 300)
        self.assertEqual(result['quote_ages_seconds'], [600])
        self.assertEqual(result['quote_snapshot_ages_seconds'], [300])


if __name__ == '__main__': unittest.main()
