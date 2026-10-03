# Stage 1: disabled recurring-writer admission

Hub-directed implementation, October 3, 2026. Issue #166 / PR #167.
**Implementation review only. No activation, spending or live account seed.**

All eight source-defined recurring paid roles enter `ops/collector_guard.py::paid_get`:
NFL/CFB alerts (explicit board role), NFL/CFB closes (explicit role and scheduled
observation identity), NFL/CFB trigger polling, NFL props, and NBA collection.
`require_bridge()` still unconditionally raises before admission or transport.
The installer still calls that same unconditional hold before keys or installation.
No flag, environment, envelope or populated ledger enables production.

## Contract exercised with synthetic state

The v2 envelope binds the clean exact source commit, hash-pinned authority file,
month/expiry, key fingerprint, exact per-role endpoint/params/cap, account ceiling,
plan size/reserve floor and all eight role names. A declared writer list is not
operational proof. A key fingerprint alone is not authenticated account lineage.
Only the hub can provide actual account/authority evidence at activation.

Every caller uses one fixed journal at
`~/Library/Application Support/ValueFinder/shared-account-state/journal.json`,
with its persistent sibling `journal.json.lock`. Callers cannot choose another
ledger domain. No initializer/migrator/reset is provided. Missing, malformed,
changed-authority, noncanonical or symlink state blocks. Tests replace that constant
with temporary paths; production contains no switch for doing so.

Under the same lock: revalidate source/authority, validate saved receipt hashes and
states, check cumulative baseline plus external exposure plus every full reservation
against account/per-role ceilings, persist+fsync the full upper bound before sending,
revalidate authority again, issue one GET without retries/redirects, persist+fsync its
sanitized receipt, then persist+fsync the terminal state. Pending, failed, uncertain
or disk-failed attempts retain their entire reservation and halt later sends across
roles. Provider counter regressions, foreign usage above retained exposure, missing
billing, bad statuses and reserve/ceiling violations fail closed. Provider counters
may lag accounted reservations; reservations are never reduced on that basis.

Successful same-ID/same-request replay returns the validated original receipt with
its original observed UTC time and no new send/reservation. Conflicting identity is
blocked. NFL/CFB raw snapshot clocks and NBA cache `fetched_at` preserve that receipt
time. Replayed headers do not overwrite a newer quota observation or charge the
local budget again. The NBA cache utility's optional `observed_at` field defaults to
its previous behavior for all existing callers. Billing headers in saved quotes
remain the original provider headers, not a new bill.

## Timing and exclusions

No launchd schedules, windows, selections, registration/scoring files or executed
freezes change. Alerts identify their existing four-hour observation window;
trigger polls use their existing ten-minute windows; props retain event/offset IDs;
NBA retains its configured cadence. Close IDs include due kickoff slots, persisted
try numbers and the scheduled fifteen-minute observation tick. A restart in that
observation reuses a complete receipt. A later scheduled observation after a
conclusive empty answer gets a distinct ID. An uncertain first send blocks either
ID. The helper neither decides eligibility nor updates tries: both close scripts
retain MAX_TRIES2 and scheduled 2–20-minute eligibility, with existing matching and
missing-close handling. These are scheduled pregame clocks, not independent
first-play verification.

Unclassified weather live/manual/historical cache misses have no admitted role;
only the exact known free event listing bypasses paid admission (no retries or
redirects). NBA likewise only bypasses for its exact known free event listing.
Existing saved weather historical cache reads are unaffected.

**Not total account coordination:** generic sharp BulkClient, immutable executed
football transport closures and prospective acquisition orchestration remain
unintegrated in this stage. Their existing locks do not become the account lock.
Activation must integrate future historical transport or prove actual enforced
exclusion, settle lock ownership/order with existing purchase locks, and deny all
other account writers. No calendar-only exclusion or absence-of-plist inference is
accepted as that proof. Original frozen bytes and records remain untouched.

## Evidence and readiness

Synthetic test support `ops/shared_account_testkit.py` is imported only by tests;
it creates temporary journals using fake keys/baselines/caps and patches the hold
only inside scoped tests. It is not an operational bootstrap or authority producer.
Three separate project environments and the updated collector-safety CI bind the
caller/default/dependency/test source. Historical PR165 evidence is not reused as
proof of this changed source. The original scope snapshot is in SCOPE.md; its
publication-limit paragraph describes the earlier proposal state only.

The bound evidence/report is added after testing. Independent current-head review
and CI are needed for source adoption. Live deployment is separately blocked by
historical integration/exclusion, full writer inventory, authenticated cumulative
account baseline including prior/probe/uncertain exposure, exact caps/reserve/expiry
and source authority, and reviewed activation. No running job, key, provider,
raw runtime data, outcome, holdout or live ledger was accessed or changed.
