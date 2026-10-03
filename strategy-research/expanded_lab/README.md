# Value Finder research lab

The broader research runner is ready on this Mac. The existing chat **Audit result grading code** is preparing six fixed models and a historical-odds plan. This lab reuses a pinned copy of that study's data loader and six models, and adds 20 explicitly listed model specifications.

## Start and stop

Double-click **Run Research.command** in this folder to run the frozen batch. The launcher keeps the Mac awake while the run executes. Closing the display does not necessarily keep a laptop awake; this setup was verified on the Studio. No scheduled job has been installed.

Double-click **Resume Research.command** to resume the newest incomplete run. Completed cohorts are reused only when protocol, code, historical inputs, historical outcomes, and trial count match. A cohort interrupted before its checkpoint is recomputed. Use Control-C in the terminal to stop; its manifest records interruption or failure.

The initial batch already finished. Open **results.md** for the first result, or each dated folder under **runs/** for its full evidence. Each run saves its protocol, trial ledger, input fingerprints, exclusions, per-season folds, coefficients, predictions, paired errors, bootstrap diagnostics, leaderboard, and status. New runs never replace old evidence.

This batch is small enough that it finished in about ten seconds on this Mac. There is no benefit to repeating identical deterministic fits merely to occupy the machine. The runner supplies the structure for broader batches; additional hypothesis families require a new versioned protocol.

## Current batch

- 26 specifications: six already recorded by the other chat plus 20 new local specifications. There are 23 paired candidate/control comparisons.
- Families: forecast revisions, wind persistence at the existing 15 mph threshold, threshold crossings, nonlinear wind effects, and wind/revision interactions with prior-game passing style.
- Fit on earlier seasons and predict the next season. The minimum is five prior seasons, 300 training games, and 25 test games.
- Fit scaling only on training data, with a fixed ridge penalty of 10. Every candidate and its baseline share the same evaluation games within a cohort.
- Score actual points minus the consensus closing total. Lower squared prediction error is the objective. This is a scoring diagnostic; the closing total is not represented as an executable entry price.
- 50,000 nested season/game-day bootstrap draws per comparison, leave-one-season-out diagnostics, and 100,000 joint season sign flips for a diagnostic of searching across the comparisons. The sign-flip diagnostic assumes symmetry; it is not a full model-refit null experiment or an alternative approval gate.

## Safeguards and accounting

The runner filters seasons to 2025 or earlier before the parquet reader returns rows. It checks forecast publication against the decision clock and builds style from previously available games. It blocks network/subprocess use within the evaluator, credential/forward-ledger reads, and writes outside this lab. It uses the existing NFL Python environment; it installs no packages.

The prior project-count snapshot is **294** in the other chat's worktree. This local batch adds **20**, giving an adjustment floor of **314**. All 20 are recorded before outcomes and stay counted even if a fit fails. The 20 are recorded in this registration PR; incorporation into the main branch is pending review. Reconcile them there before any promotion or project-wide result reporting; increase the prior count if another study has added trials. A rerun of these same frozen specifications is not 20 additional hypotheses.

The launcher accepts a current prior count when invoked from a terminal: `launch.py run CURRENT_PRIOR_COUNT`. The supplied one-click launcher uses the recorded floor. Existing historical seasons are discovery data, not fresh confirmation. No model in this report changes the live rules or authorizes staking.

## Next batches

| Stage | What must happen before it runs |
|---|---|
| Market response and price edge | Reuse the existing planned odds download, audit timestamps and matching, then freeze entry/close/settlement and candidate definitions. |
| College early-season uncertainty | Audit release dates and revisions of returning-production and talent inputs before constructing features. |
| Price-engine robustness | Use the cached odds and freeze fair-price alternatives, stale-quote criteria, and execution delays. |
| Full search false-positive simulation | Define a credible null data-generating process and rerun the complete fitting/selection pipeline. The current sign flips are a narrower diagnostic. |
| GitHub parser comparison | Pin pyIEM and cross-check fixed MOS fixtures independently; this integration is not implemented in this batch. |

Raw inputs stay in `/Users/maxzipperman/code/value-finder`. This lab is a separate artifact in the ChatGPT project workspace. It does not edit synced `sources/`, the live checkout, alerts, ledgers, or API settings.

The upstream adapter is copied from the other chat's worktree at `f3b56b31aadff4e0c17bf8f8f5c102e21c09c840`; its source and protocol hashes are pinned. The launcher's frozen-file checks prevent unnoticed source changes.
