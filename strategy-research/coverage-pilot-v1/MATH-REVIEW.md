# Independent assessment of the proposed statistical contract

October 2, 2026. Assessed the statistician's correction memo independently before
implementing bounds.py. This is agreement with the mathematical design subject to
the conditions below, NOT independent approval of my own implementation or paid
execution. The new code still requires a different technical reviewer.

## Assessment: mathematically sound conditional on a fixed design

Let U be the initially unknown finite game population in a stratum, n its fixed
sample size, x sampled successes and K the true count of successes in U. For
simple random sampling without replacement, X has a hypergeometric distribution.
The lower bound is the smallest integer K with P_K(X >= x) > alpha. Equality is
rejected; the exact rational implementation avoids floating-point ambiguity.
When n=U, the bound is x exactly. When n=0, it is zero. Known successes and failures
are fixed certainty components, not additional sample observations.

For a true K, the event that the lower bound exceeds K is an upper-tail rejection
with probability at most alpha. Allocate .02/12 = 1/600 to each existing-frame
primary stratum and .02/6 = 1/300 to each added props cohort; reserve .01 for the
separately fixed optional family. By the union bound all allocated statements hold
simultaneously with probability at least .95. This does not require independence
between sport/year statements or between overlapping requests. Census and unused
slots do not redistribute alpha. Optional code is not implemented by this PR.

Population-weighted sums of these same lower success counts remain valid on that
simultaneous event. Predeclared season-specific release and pooled reporting do not
require new tests or extra alpha, provided they use these saved bounds unchanged.
A failing season remains held even if other seasons make the pooled rate pass.
This is finite archive quote utility, not evidence of edge or future-season coverage.

Full-frame rate = (known successes + unknown lower count) / all intended games.
Marginal rate = unknown lower count / initially unknown games. The implementation
requires both rates to meet the declared utility floor. Marginal cost upper bound
= all projected NEW credits for that cohort (pilot plus residual) / unknown lower
count. Known2025 successes never enter that cost denominator. Zero lower count is
inconclusive/hold, not zero-cost success. A fully known census grants no new purchase.
The cost100/320 thresholds still need explicit ratification; callers currently
supply them rather than implicitly treating the earlier draft as authority.

## Conditions that remain material

- Fix the exact game identity frame, eligibility/classifier and slots before a
  once-only random draw. Missing/ambiguous/cancelled/unbound rows remain classified
  failures or unknown as predeclared, not silently excluded. Sample n=min(target,U)
  must be declared before observation; census is exact when U is small.
- Uniform sampling is the inferential assumption. The deterministic SHA ranking
  uses a single externally committed random seed as a pseudorandom implementation;
  seed integrity, no rerolls and exact unique game identities require verification.
  No convenience replacement or chronological slicing is permitted.
- Shared requests do not add sampled games. Fixed game classifications permit
  design-based inference despite correlated quotes; request-dependent selection or
  changing success definitions after observing prices would invalidate that logic.
- Existing bounds are frozen once. Added identities form a disjoint new cohort,
  sampled under its reserved allocation; never recompute old bounds as another try.
  Changed old identities or changed eligibility require explicit revalidation,
  not this added-cohort shortcut. Finality and evidence authentication are not yet
  enforced by the pure math functions.
- A utility pass can support review of listings, not automatic bulk authority.
  Expanded-frame revalidation precedes full purchases. CFB remains quote-only until
  a supported stats/settlement source plan is reviewed. Domestic book union is an
  acquisition measure; fixed-book analysis and actual executable baskets stay separate.

## Verification and sources

Six new tests passed; exhaustive subset enumeration verifies the hypergeometric
probabilities through population8. Exhaustive true-K/sample/outcome checks through
population12 verify coverage for alpha1/20,1/600,1/300, plus monotonicity, exact
alpha equality, census endpoints, fixed allocation and marginal-cost protection.
No real odds or outcomes were inspected. Saved process_guard evidence:
`/private/tmp/coverage-pilot-bounds-tests.json`, tested identity
`78bd1927d842b3f184cd44d9ae9d05c88a7ecc70f1e58799f1c940facf6058a6`.
Existing planner/timing evidence remains separate; no unchanged suite repeated.

Primary reference for the sampling probability:
[SciPy hypergeometric definition](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.hypergeom.html).
Primary reference for the simultaneous guarantee:
[NIST Bonferroni inequality](https://www.itl.nist.gov/div898/handbook/prc/section4/prc473.htm).
The inversion proof and acquisition application above are this review's derivation.
