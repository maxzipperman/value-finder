import unittest
from planner import InvalidPlan, digest, frame_rows, select, residual, inventory

class PlannerTests(unittest.TestCase):
    def setUp(self):
        self.rows = [dict(game_id=str(i), season=2025, stratum='NFL2025', binding='event', classification='unknown') for i in range(5)]
        self.rows.append(dict(game_id='unbound', season=2025, stratum='NFL2025', binding=None, classification='failure'))
        self.frame = digest(frame_rows(self.rows))
        self.protocol = {'sample_sizes': {'NFL2025': 2}}
        self.record = dict(seed='a'*64, frame=self.frame, protocol=digest(self.protocol), sample_sizes=self.protocol['sample_sizes'])

    def draw(self, rows=None, record=None):
        return select(self.rows if rows is None else rows, self.record if record is None else record,
                      {'NFL2025': 2}, committed_frame=self.frame, committed_protocol=digest(self.protocol), committed_seed_record=digest(self.record), protocol=self.protocol)

    def test_order_independent_full_denominator(self):
        result = self.draw()
        self.assertEqual(result, self.draw(list(reversed(self.rows))))
        self.assertEqual(result['denominator'], 6)
        self.assertEqual(result['no_request'], ['unbound'])
        self.assertNotIn('unbound', result['selected'])

    def test_changed_frame_and_duplicate_rejected(self):
        for rows in [self.rows[:-1], self.rows + [self.rows[0]]]:
            with self.assertRaises(InvalidPlan): self.draw(rows)

    def test_sealed_and_unbound_unknown_rejected(self):
        for mutation in [dict(season=2026), dict(binding=None)]:
            rows = [dict(r) for r in self.rows]; rows[0].update(mutation)
            with self.assertRaises(InvalidPlan): frame_rows(rows)

    def test_protocol_and_seed_rejected(self):
        for mutation in [dict(protocol='changed'), dict(seed=''), dict(seed='b'*64)]:
            with self.assertRaises(InvalidPlan): self.draw(record=dict(self.record, **mutation))

    def test_changed_allocation_with_same_seed_rejected(self):
        with self.assertRaisesRegex(InvalidPlan, 'allocation'):
            select(self.rows, self.record, {'NFL2025': 3}, committed_frame=self.frame,
                   committed_protocol=digest(self.protocol), committed_seed_record=digest(self.record), protocol=self.protocol)
        changed = {'sample_sizes': {'NFL2025': 3}}
        with self.assertRaises(InvalidPlan):
            select(self.rows, self.record, changed['sample_sizes'], committed_frame=self.frame,
                   committed_protocol=digest(self.protocol), committed_seed_record=digest(self.record), protocol=changed)

    def test_census_draws_nothing(self):
        rows = [dict(r, classification='failure') for r in self.rows]
        sha = digest(frame_rows(rows)); protocol = {'sample_sizes': {'NFL2025': 0}}
        record = dict(self.record, frame=sha, protocol=digest(protocol), sample_sizes=protocol['sample_sizes'])
        self.assertEqual(select(rows, record, {'NFL2025': 0}, committed_frame=sha,
                                committed_protocol=digest(protocol), committed_seed_record=digest(record), protocol=protocol)['selected'], [])

    def test_all_attempts_removed_uncertain_blocks(self):
        original = [dict(request_id=str(i), max_credits=30) for i in range(6)]
        attempts = [dict(request_id=str(i), status=s) for i,s in enumerate(['completed','missing','uncertain','pending'])]
        result = residual(original, attempts, ['4'])
        self.assertEqual(result['requests'], [original[5]])
        self.assertEqual(result['max_credits'], 30)
        self.assertTrue(result['blocked']); self.assertEqual(result['denominator'], 6)
        with self.assertRaises(InvalidPlan): residual(original, attempts, ['0'])

    def test_inventory_branch_loss_and_overcap(self):
        base = {'base': 'ledger-sha'}
        epoch = dict(root='pilot', ledger='new-sha', predecessor=digest(base), reserved_debit=30)
        observed = dict(base, pilot='new-sha')
        self.assertEqual(inventory(base,[epoch],observed,carried=1687,ceiling=1717)['conservative_debit'],1717)
        for actual in [base, dict(observed, rogue='x'), dict(observed, base='changed')]:
            with self.assertRaises(InvalidPlan): inventory(base,[epoch],actual,carried=1687,ceiling=1717)
        with self.assertRaises(InvalidPlan): inventory(base,[epoch,epoch],observed,carried=1687,ceiling=1717)
        with self.assertRaises(InvalidPlan): inventory(base,[epoch],observed,carried=1687,ceiling=1716)

if __name__ == '__main__': unittest.main()
