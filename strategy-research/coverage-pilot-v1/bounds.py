"""Exact one-look finite-population bounds. Pure math, not execution authority."""
from fractions import Fraction
from math import comb


EXISTING_ALPHA = Fraction(1, 600)  # .02 / 12, census slots never redistributed
ADDED_ALPHA = Fraction(1, 300)     # .02 / 6
OPTIONAL_ALPHA_RESERVED = Fraction(1, 100)


def count(value):
    if type(value) is not int or value < 0:
        raise ValueError('nonnegative integer required')
    return value


def tail(population, successes, sample, observed):
    """P[X >= observed], X ~ Hypergeometric(population, successes, sample)."""
    for v in (population, successes, sample, observed):
        count(v)
    if successes > population or sample > population or observed > sample:
        raise ValueError('inconsistent hypergeometric counts')
    start = max(observed, sample - (population - successes))
    stop = min(successes, sample)
    return Fraction(sum(comb(successes, k) * comb(population-successes, sample-k)
                        for k in range(start, stop+1)), comb(population, sample))


def lower_successes(population, sample, observed, alpha):
    """Smallest K with P_K[X>=observed] > alpha; reject equality exactly.

    Input alpha must be exact Fraction. No sample = lower bound zero; census
    returns observed exactly. This is a bound on the initially unknown population,
    INCLUDING sampled games, not just the unobserved remainder.
    """
    for v in (population, sample, observed):
        count(v)
    if sample > population or observed > sample:
        raise ValueError('inconsistent sample')
    if not isinstance(alpha, Fraction) or not 0 < alpha < 1:
        raise ValueError('exact rational alpha required')
    if sample == population:
        return observed
    lo, hi = observed, population - sample + observed
    while lo < hi:
        mid = (lo + hi) // 2
        if tail(population, mid, sample, observed) > alpha:
            hi = mid
        else:
            lo = mid + 1
    return lo


def stratum(*, known_successes, known_failures, unknown, sample, observed,
            phase, projected_new_credits, utility_floor, cost_ceiling):
    """One predeclared stratum, for reporting and marginal acquisition gating.

    projected_new_credits must include sample AND residual costs for the initially
    unknown cohort. Never include known census successes in its cost denominator.
    No unknown population means census_only, not permission for a new purchase.
    This function does not authenticate a saved one-look result or finality.
    """
    for v in (known_successes, known_failures, unknown, sample, observed,
              projected_new_credits, cost_ceiling):
        count(v)
    if phase not in {'existing', 'added'}:
        raise ValueError('unallocated phase')
    if not isinstance(utility_floor, Fraction) or not 0 < utility_floor <= 1 or cost_ceiling == 0:
        raise ValueError('invalid utility/cost threshold')
    alpha = EXISTING_ALPHA if phase == 'existing' else ADDED_ALPHA
    bound = lower_successes(unknown, sample, observed, alpha)
    total = known_successes + known_failures + unknown
    if not total or (unknown == 0 and projected_new_credits):
        raise ValueError('empty frame or purchase against census')
    full_lower = Fraction(known_successes + bound, total)
    marginal_lower = Fraction(bound, unknown) if unknown else None
    cost_upper = Fraction(projected_new_credits, bound) if bound else None
    passes = bool(unknown and full_lower >= utility_floor and
                  marginal_lower >= utility_floor and cost_upper is not None and
                  cost_upper <= cost_ceiling)
    return {'population': total, 'unknown_population': unknown,
            'known_successes': known_successes, 'unknown_successes_lower': bound,
            'full_successes_lower': known_successes + bound,
            'full_coverage_lower': full_lower, 'marginal_coverage_lower': marginal_lower,
            'new_credits_per_usable_upper': cost_upper,
            'alpha': alpha if unknown and sample < unknown else Fraction(0),
            'status': 'census_only' if not unknown else ('utility_pass' if passes else 'hold')}


def pooled_report(strata):
    """Population-weighted reporting only; never overrides a failed season gate.

    Caller must authenticate distinct predeclared strata and saved bound identities;
    old bounds cannot be recomputed after added-frame discovery.
    """
    if not strata:
        raise ValueError('empty pool')
    total = sum(r['population'] for r in strata)
    lower = sum(r['full_successes_lower'] for r in strata)
    return {'population': total, 'full_successes_lower': lower,
            'coverage_lower': Fraction(lower, total), 'release_authority': False}


def attainable(*, known_successes, known_failures, unknown, sample, phase,
               projected_new_credits, utility_floor, cost_ceiling):
    """Before any draw: minimum successful sampled games for the fixed contract.

    Full denominator and marginal unknown-cohort cost BOTH apply. A structural
    fail means no possible population can meet the utility floor; a fixed-sample
    fail means even x=n cannot certify this predeclared sampling design. Neither
    permits automatic sample expansion. No outcome or actual sample is consulted.
    """
    for v in (known_successes,known_failures,unknown,sample):count(v)
    if sample>unknown:raise ValueError('sample exceeds unknown population')
    if not isinstance(utility_floor,Fraction) or not 0<utility_floor<=1:
        raise ValueError('exact utility floor required')
    total=known_successes+known_failures+unknown
    if not total:raise ValueError('empty stratum')
    ceiling=Fraction(known_successes+unknown,total)
    args=dict(known_successes=known_successes,known_failures=known_failures,unknown=unknown,
              sample=sample,phase=phase,projected_new_credits=projected_new_credits,
              utility_floor=utility_floor,cost_ceiling=cost_ceiling)
    best=stratum(**args,observed=sample)
    if not unknown:status='census_only';minimum=None
    elif ceiling<utility_floor:status='structural_utility_fail';minimum=None
    else:
        minimum=next((x for x in range(sample+1) if stratum(**args,observed=x)['status']=='utility_pass'),None)
        status='attainable' if minimum is not None else 'fixed_sample_cannot_certify'
    return {'status':status,'sample':sample,'population':total,'unknown_population':unknown,
            'minimum_sample_successes':minimum,'full_coverage_ceiling':ceiling,
            'best_full_lower':best['full_coverage_lower'],'best_marginal_lower':best['marginal_coverage_lower'],
            'best_cost_upper':best['new_credits_per_usable_upper'],'paid_authority':False}
