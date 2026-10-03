import unittest
from timing import scheduled_guard

class TimingTests(unittest.TestCase):
    def args(self):
        return dict(base_eligible=True, requested='2020-10-01T12:54:00Z',
                    returned='2020-10-01T12:50:00Z', execution='2020-10-01T12:54:00Z',
                    provider_kickoffs=['2020-10-01T13:00:00Z'],
                    independent_kickoffs=['2020-10-01T12:55:00Z'])

    def test_close_boundary_repro(self):
        args = self.args(); args.update(requested='2020-10-01T12:55:00Z',execution='2020-10-01T12:55:00Z')
        self.assertIn('decision_snapshot_or_execution_not_before_schedule',scheduled_guard(**args)['reasons'])

    def test_each_clock_equality_rejected(self):
        for field in ['requested','returned','execution']:
            args=self.args();args[field]='2020-10-01T12:55:00Z'
            self.assertFalse(scheduled_guard(**args)['eligible'])

    def test_valid_remains_proxy_and_no_rescue(self):
        result=scheduled_guard(**self.args())
        self.assertTrue(result['eligible']); self.assertFalse(result['actual_play_certified'])
        self.assertEqual(result['timing_basis'],'scheduled_proxy')
        args=self.args();args['base_eligible']=False
        self.assertFalse(scheduled_guard(**args)['eligible'])

    def test_all_sources_missing_invalid_future(self):
        changes=[{'independent_kickoffs':[]},{'execution':None},
                 {'requested':'2020-10-01T12:54:00'},
                 {'provider_kickoffs':['2020-10-01T13:00:00Z','2020-10-01T12:53:00Z']},
                 {'returned':'2020-10-01T12:54:01Z'},
                 {'execution':'2020-10-01T12:53:00Z'}]
        for change in changes:
            self.assertFalse(scheduled_guard(**dict(self.args(),**change))['eligible'])

    def test_timezone_equivalence(self):
        args=self.args();args['execution']='2020-10-01T05:54:00-07:00'
        self.assertTrue(scheduled_guard(**args)['eligible'])
