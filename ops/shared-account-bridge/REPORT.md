# Stage 1 implementation evidence

Issue #166 / PR #167. October 3, 2026. Author implementation report;
independent technical disposition and CI are separate.

Tested clean source commit: `0bd9d67735a9fd94c73e6643f832f791253ffbb5`.
The subsequent report/evidence-only commit reuses these identical tested inputs.
All three `verify-test` checks passed; they verify integrity, not independent trust.

| Project runtime | Complete tested-input identity | Checks passed |
| --- | --- | --- |
| sharp | `65643e910c445d2b4324c3da95ea639d2bca2c3d1c79113a6d06fef2d31ab941` | 58 |
| nfl | `42d9142b1cc6a666565f8d9b077307d33788a56129b623ab8d51d6e07f4655a5` | 74 |
| cfb | `0d786c0720ca4fce596a8083c9482febd46815a95803bee9af79fd46dd0c416a` | 54 |

186 targeted checks passed: 35 standard-library accounting/integration tests,
23 sharp collector/cache/localhost HTTP tests, 74 NFL checks (including 27
existing synthetic close regressions), and 54 CFB checks (including 29 close
regressions). One existing external `.invalid` DNS test is explicitly excluded;
localhost HTTP cases ran. No provider/network purchase test ran. Each project
used its own isolated environment; current dependency/environment inventories and
exact commands/return codes are inside EVIDENCE_SHARP/NFL/CFB.json.

Proof covers all eight recurring role boundaries, direct/unclassified weather
live/history misses, strict free event listings, shared thread/process cap contention,
retained pre-send reservation after process death, disk failure at each persistence
step, actual lock-wait revocation and post-fsync revocation, global pending/failure
halts, source/month/authority changes without automatic reset, canonical journal/
symlink denial, receipt corruption, stable-ID conflict, successful cache replay,
original quote/cache clocks and unchanged close matching/window/try semantics.
Alert run functions are stopped at fake board admission; close transport expressions
are checked without job startup. Existing close regression harnesses run only against
made-up feeds/schedules and temporary forward directories, never live jobs/data.

No source/data changes under `strategy-research/` or frozen test closures; no rule,
registration, scorer or launchd schedule changes. The unconditional production
`paid_get` and installer hold is still proved. Historical PR165 evidence is historical
only, not reused as current-source proof.

**Source implementation is ready for independent review; deployment is NOT READY.**
Generic sharp historical and captured/prospective purchase transports remain outside
this stage. Activation needs their integration or actual enforced exclusion, reviewed
lock ordering, complete operational writer inventory, authenticated prior/probe/
uncertain cumulative baseline and exact caps/reserve/expiry/source authority.
No such authority or runtime seed is invented here. Stage1 alone does not establish
total coordination. No keys, provider calls, runtime data, actual outcomes, sealed
holdouts or scheduled jobs were accessed or mutated. Credits spent: zero.
