import csv
import tempfile
import unittest
from pathlib import Path
from projected_coverage import aggregate, BASE, COVERAGE, COLUMNS


class CoverageTests(unittest.TestCase):
    def write(self, directory, rows, extras=()):
        p = Path(directory) / 'metadata.csv'
        with p.open('w', newline='') as f:
            w = csv.DictWriter(f, fieldnames=sorted(COLUMNS) + list(extras))
            w.writeheader()
            w.writerows(rows)
        return p

    def row(self, identity, **changes):
        r = {'game_id': identity, 'season': '2024', **{k: 'False' for k in (*BASE, *COVERAGE)}}
        r.update(fbs='True', venue_mapped='True')
        r.update(changes)
        return r

    def test_candidates_keep_missing_forecasts_and_exclude_ineligible_schedule(self):
        with tempfile.TemporaryDirectory() as d:
            rows = [self.row('a', mos_T24='True'), self.row('b'), self.row('c', indoor='True'),
                    self.row('d', tbd='True'), self.row('e', venue_unknown='True'), self.row('f', fbs='False')]
            r = aggregate(self.write(d, rows))['rows'][0]
            self.assertEqual((r['all_schedule_games'], r['weather_candidates'], r['mos_T24']), (6, 2, 1))

    def test_outcome_or_price_column_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            for extra in ('total', 'price', 'wind_value'):
                with self.assertRaises(ValueError):
                    aggregate(self.write(d, [dict(self.row('a'), **{extra: '9'})], [extra]))

    def test_sealed_duplicate_and_nonboolean_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            for rows in ([self.row('a', season='2026')], [self.row('a'), self.row('a')], [self.row('a', mos_T24='15')]):
                with self.assertRaises(ValueError):
                    aggregate(self.write(d, rows))


if __name__ == '__main__':
    unittest.main()
