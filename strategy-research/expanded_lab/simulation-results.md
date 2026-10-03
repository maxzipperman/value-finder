# Full-refit calibration and power study

Completed 30,000 synthetic searches across three noise regimes and four scoring-effect sizes. Every outcome vector refitted all 26 models through chronological folds. Historical predictors only; no final scores, API calls, or 2026 rows.

These experiments review future policy. They do not replace existing registrations or confirm a profitable strategy.

| Noise regime | Method | Null: any selection | 1-point signal: designated revision detection |
|---|---|---:|---:|
| independent | global_bonferroni_314 | 0.00% | 8.1% |
| independent | prospective_family_holm_23 | 0.05% | 51.4% |
| independent | prospective_family_bh_05 | 0.05% | 88.8% |
| independent | prospective_family_bh_10 | 0.05% | 97.9% |
| independent | prospective_family_calibrated_max_t | 7.00% | 100.0% |
| game_day_heavy_tail | global_bonferroni_314 | 0.00% | 7.8% |
| game_day_heavy_tail | prospective_family_holm_23 | 0.00% | 46.9% |
| game_day_heavy_tail | prospective_family_bh_05 | 0.00% | 82.2% |
| game_day_heavy_tail | prospective_family_bh_10 | 0.10% | 95.2% |
| game_day_heavy_tail | prospective_family_calibrated_max_t | 4.70% | 100.0% |
| game_day_plus_season_drift | global_bonferroni_314 | 0.00% | 7.0% |
| game_day_plus_season_drift | prospective_family_holm_23 | 0.05% | 45.1% |
| game_day_plus_season_drift | prospective_family_bh_05 | 0.05% | 80.6% |
| game_day_plus_season_drift | prospective_family_bh_10 | 0.10% | 92.4% |
| game_day_plus_season_drift | prospective_family_calibrated_max_t | 5.75% | 99.8% |

Each estimate uses 2,000 independent evaluation replicates; the CSV reports Wilson intervals. Calibration uses another 2,000 null searches per regime.

The global cutoff has very low detection power in these specified scenarios. Prospective-family Holm and FDR have different error-control targets; none is an automatic replacement for the full historical search correction. The calibrated maximum-t method exceeded the desired 5% null-selection rate in the independent-noise evaluation (7.0%, interval approximately 6.0–8.2%). Do not adopt that calibration as a validated 5% family-wise procedure.

Recommendation for review: retain current frozen gates; define a prospective discovery shortlist policy separately from a small independent confirmation family. Validate the chosen dependence handling and effect-size requirements before changing policy. Synthetic scoring power is not evidence of executable betting returns.
