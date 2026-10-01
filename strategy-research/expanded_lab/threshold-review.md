# Significance policy review

The current global rule uses 0.05 divided by every recorded specification. At 314, the raw-p cutoff is about **0.000159**. The issue is whether that cutoff is too stringent for the decision we are making, not whether alpha is too high.

My working recommendation is to separate **discovery shortlisting** from **confirmation**:

1. Discovery: record the complete search, report effects and stability, and use a prospective, clearly defined family with an FDR criterion to form a research shortlist. FDR permits some false discoveries in a selected set; it is not the probability that an individual strategy is false. Dependence assumptions matter. This would be a new policy for future studies, not a way to reset the current family's count after seeing results.
2. Confirmation: freeze a small number of candidates and all execution/settlement definitions before evaluating an untouched period. Apply Holm or a properly calibrated dependence-aware family-wise procedure to that complete confirmation family, at an explicit alpha budget. If more families or repeated looks are added, budget for them. Do not spend the same holdout repeatedly.
3. Economic gate: require actual decision-time prices, meaningful CLV/return effect sizes, realistic execution, and uncertainty. Prediction error alone cannot establish betting value.

Holm is a step-down family-wise method. BH is an FDR method, with dependence qualifications; a dependence-robust alternative or simulation evidence is needed when those qualifications fail. `arch` supplies SPA/Reality Check and StepM procedures for comparing many forecasting models with a benchmark while accounting for dependence. These are candidates to validate, not substitutes to install and trust automatically.

Sources: [statsmodels multiple-testing reference](https://www.statsmodels.org/stable/generated/statsmodels.stats.multitest.multipletests.html), [arch multiple-comparison reference](https://bashtage.github.io/arch/multiple-comparison/multiple-comparison-reference.html).

The prepared experiment refits all 26 models across chronological folds on each synthetic outcome vector. It uses three noise regimes (independent, correlated heavy-tailed game days, and correlated days plus season drift), effects of 0, 0.5, 1, and 2 scoring points per standard deviation of an additional revision signal, and independent calibration/evaluation samples. The full setting is **30,000 complete simulated searches**, with two workers and per-cell checkpoints.

A cached design matrix/factorization saves work; every simulation still fits new coefficients and evaluates new losses. Synthetic results describe power under the specified assumptions, not an inferred real-world edge. The calibrated maximum-t alternative covers a hypothetical 23-comparison prospective family; it does not cover all 314 historical specifications. Under the all-null scenario, any selection measures family-wise false positives. Under planted effects, any selection is not itself FDR or a count of true discoveries.

The first historical batch already has no comparison passing its adjusted cutoff. The simulation protocol was written afterward and says so. Existing registered gates stay fixed while this review informs a possible future policy.
