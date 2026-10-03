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
