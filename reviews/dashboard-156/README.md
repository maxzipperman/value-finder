# Dashboard operations refresh

Owner request: replace stale download/status views, show source freshness and all
seven jobs, and simplify Home. Closes #156.

LOCAL-BECAUSE: live-checkout/jobs/raw-data: this review needs the Studio's local
acquisition journals and browser preview. Implementation is isolated. No purchase,
scoring, registration, live checkout edit or launchd change is authorized here.

Validation focuses on missing/corrupt/stale sources, overlapping attempt IDs,
loaded versus successful jobs, and read-only/secret boundaries. The dashboard is
an observation tool, never acquisition authority. Independent review and hub
coordination precede deployment.

## Result

Implemented read-only acquisition journal summaries and the existing canonical
queue table, explicit STATUS action classification, data-source freshness, seven
job displays, and reordered Home. The legacy pull API/hash remains compatible.
Scoring/rules/paid code/launchd installers and executed freezes are unchanged.

Validation (October 3, Mac Studio): full dashboard suite 376 passed / 2 skipped
(optional weather-environment chart rebuild checks). After that full run, the
final two display fixes (journal header timestamp and plan-date disagreement)
passed all 18 operational checks and JS syntax validation. Reusable evidence is
`operations-evidence.json`, produced/verified with `dashboard/verification.json`;
it covers the focused operational suite, not an asserted authenticated CI run.
Test identity: 2688d71085ef1eb8e487b1d0d37bbda9e52454ff187e57e41d5431a0c2fdbd93.
Browser inspection used current Mac journal metadata and live alert records,
with scorer execution disabled. Nothing under the live checkout/runtime was edited.

Limits: journal values are not re-authenticated receipts. Planned caps remain
separate from recorded charges; unknown bills are explicit; duplicate IDs withhold
aggregates. A saved running state is not a liveness heartbeat. Existing collector
formats lack a reliable success receipt, so UI says collection success is
unverified rather than inferring success from loaded/exit-zero. The canonical
queue can lag a newer runtime; that disagreement is flagged, never auto-rewritten.
Historical reconciled/halted roots remain visible alongside successor completion.

Hub next action: independent review, verify classifications of unresolved owner
items, and coordinate reviewed deployment. Preview currently runs on loopback
8787 with --root pointing at the live data, --operations-root at this isolated
review checkout, and --scorer-root at a missing directory. It is temporary and
not a login job. Select a durable reviewed checkout before permanent deployment;
never switch the scheduled-job checkout to this branch. Reconcile stale canonical
queue separately from changing acquisition authority.
