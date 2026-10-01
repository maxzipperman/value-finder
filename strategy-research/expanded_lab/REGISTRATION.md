# Expanded local research batch: accounting and provenance

The user requested a bounded expanded historical search on the Studio. This adds **20 specifications** to the project's **294** already committed variants. The six original forecast/style models are reused unchanged; they are not six new variants. The resulting floor is **314**, plus any intervening studies. Existing registrations retain their frozen thresholds.

## Exact local record

- Protocol: `protocol.json`, SHA256 `5869f0088fac1f504c4feb244ce8a89bc0ae6acb56fd65a862bbc8903e9f30bd`.
- Outcome-blind preflight began: September 30, 2026, 23:44:00.763675 UTC (16:44 Pacific).
- First historical run began: September 30, 2026, 23:44:09.854373 UTC (16:44 Pacific); it completed in 10.3 seconds.
- The full local specification ledger was saved before outcome access. Protocol and run copies are unchanged in `registration_evidence/`.
- **This repository publication occurs after execution.** The local pre-outcome recording is not described as a pre-outcome Git commit or independently timestamped external preregistration. The historical analysis is discovery only.

Twenty new models comprise eight NFL forecast-revision models, eight CFB forecast-revision models, and four NFL passing-style models. All feature definitions, paired controls, ridge penalty, season splits, threshold definitions, and diagnostic procedures appear in the original protocol. All trials remain counted even if a fit fails. Repeated execution of the identical frozen study is not another 20 variants.

## First result and its limit

26 models generated 23 paired comparisons. No comparison passes the project-adjusted significance threshold. The small positive college persistence results do not establish an edge. The target is actual points minus a closing total, evaluated by out-of-season squared prediction error, not executable entry prices, CLV, or profit. Previously examined historical seasons are not untouched confirmation. Seasons after 2025 are excluded before the parquet reader returns rows.

The study includes 50,000 nested season/day bootstrap draws per comparison, leave-one-season-out diagnostics, and 100,000 approximate joint season sign flips. These are specified diagnostics, not outcome-selected alternative approval gates. The sign flips assume symmetry and do not refit the entire search under the null.

## Later threshold-review study

After seeing the first batch, the user requested a more demanding experiment and a review of the significance threshold. `simulation_protocol.json` explicitly records that later timing. Its full-refit simulations use historical predictors only and synthetic outcomes, with separate null calibration/evaluation seeds, three noise regimes, and four planted scoring-effect sizes.

It compares global Bonferroni at 314 against hypothetical prospective-family Holm, BH FDR at 5% and 10%, and calibrated maximum-t thresholds for the fixed 23-comparison family. These methods address different error criteria. They are not a retrospective redefinition of the current project's search family. No existing rule, staking gate, holdout, or threshold is amended by this PR.

The local runner installs no packages, makes no network request, reads no credential or forward-ledger file, and writes only to its isolated lab folder. No live checkout, API setting, alert, or scheduled job was changed.

Validation: 31 synthetic checks passed before the simulation validation pilot, including exact agreement between cached-design refits and independent ridge solves, shared outcomes for overlapping NFL cohorts, chronological fitting, sealed-data exclusion, deterministic uncertainty calculations, and fixed-feature/trial accounting.

The full 30,000-search simulation has now completed. See [the simulation summary](simulation-results.md) and the derived comparison table in registration_evidence. Its candidate maximum-t calibration did not meet the intended 5% null-selection rate in the independent-noise evaluation; no new gate is adopted.
