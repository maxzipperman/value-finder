from fractions import Fraction as F
from itertools import combinations
import unittest
from bounds import (tail, lower_successes, stratum, pooled_report,
                    EXISTING_ALPHA, ADDED_ALPHA, OPTIONAL_ALPHA_RESERVED)

class BoundTests(unittest.TestCase):
    def test_tail_against_enumerated_subsets(self):
        # Independent enumeration, not the implementation's combinatorial formula.
        for N in range(1,9):
            for n in range(N+1):
                samples=list(combinations(range(N),n))
                for K in range(N+1):
                    successes=[sum(i<K for i in draw) for draw in samples]
                    for x in range(n+1):
                        self.assertEqual(tail(N,K,n,x),F(sum(v>=x for v in successes),len(samples)))

    def test_exact_frequentist_coverage_all_small_populations(self):
        # Every true K, sample size and possible observed count; no Monte Carlo.
        for N in range(1,13):
            for n in range(N+1):
                for alpha in (F(1,20), EXISTING_ALPHA, ADDED_ALPHA):
                    bounds=[lower_successes(N,n,x,alpha) for x in range(n+1)]
                    self.assertEqual(bounds,sorted(bounds))
                    for K in range(N+1):
                        failure=F(0)
                        for x in range(n+1):
                            mass=tail(N,K,n,x)-(tail(N,K,n,x+1) if x<n else 0)
                            if bounds[x]>K: failure+=mass
                        self.assertLessEqual(failure,alpha)

    def test_endpoints_and_exact_alpha_equality(self):
        self.assertEqual(lower_successes(100,0,0,EXISTING_ALPHA),0)
        self.assertEqual(lower_successes(0,0,0,EXISTING_ALPHA),0)
        self.assertEqual(lower_successes(285,285,215,EXISTING_ALPHA),215)
        # P_K=1(X>=1) = 1/2 exactly, so at alpha=1/2 reject K=1.
        self.assertEqual(lower_successes(2,1,1,F(1,2)),2)
        for args in [(2,3,1,F(1,20)),(2,1,2,F(1,20)),(2,1,1,.05)]:
            with self.assertRaises(ValueError): lower_successes(*args)

    def test_family_allocation(self):
        self.assertEqual(12*EXISTING_ALPHA+6*ADDED_ALPHA+OPTIONAL_ALPHA_RESERVED,F(1,20))

    def record(self, **kw):
        args=dict(known_successes=0,known_failures=0,unknown=100,sample=100,observed=60,
                  phase='existing',projected_new_credits=6000,utility_floor=F(3,5),cost_ceiling=100)
        return stratum(**dict(args,**kw))

    def test_known_census_cannot_subsidize_bad_new_cohort(self):
        result=self.record(known_successes=10000,observed=10)
        self.assertGreater(result['full_coverage_lower'],F(9,10))
        self.assertEqual(result['status'],'hold')
        self.assertEqual(result['new_credits_per_usable_upper'],600)
        self.assertEqual(self.record()['status'],'utility_pass')
        self.assertEqual(self.record(projected_new_credits=6001)['status'],'hold')

    def test_census_and_pooled_no_release(self):
        result=self.record(known_successes=215,known_failures=70,unknown=0,sample=0,observed=0,projected_new_credits=0)
        self.assertEqual(result['status'],'census_only');self.assertEqual(result['alpha'],0)
        good=self.record(observed=100);bad=self.record(observed=0)
        pool=pooled_report([good,bad]);self.assertEqual(pool['coverage_lower'],F(1,2))
        self.assertFalse(pool['release_authority']);self.assertEqual(bad['status'],'hold')
