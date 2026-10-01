# Football archive v3: audit repair plan

Prepared September 30, 2026. Planning only: no credential reads, API calls, outcome joins, or sealed-season reads were performed. Preserve the v2 bundle unchanged.

## Recommendation and scope

Keep the three-market football archive, the original 665 MOS diagnostic slots, and the recent-first purchase order. Repair eligibility and coverage accounting, implement and rehearse the spending controls, then freeze v3 before purchasing 2023–25. Stop after that slice. Buying 2020–22 requires an accepted outcome-blind coverage report and a separate scoped go-ahead.

This archive supplies daily prices, fixed MOS decision-time diagnostics, and candidate close proxies. It does not supply a complete live first-trigger replay, all four daily alert times, or reliable 5/15/30/60-minute execution follow-ups. Those remain separately registered expansions. Do not change significance thresholds, revise prior grades, or loosen freshness limits during these repairs.

## Audit evidence and disagreements

Inputs reviewed:

- `/Users/maxzipperman/code/value-finder/reviews/2026-09-30-odds-plan-review.md`, especially its v2 addendum. Its original sections and first addendum describe earlier plans; do not reintroduce superseded scope or costs.
- `/Users/maxzipperman/.codex/attachments/8a57495f-2d1d-4430-bdae-9add64877db8/Pasted text.txt`, the targeted v2 audit.
- Current lab eligibility, builder, probe runner, protocol, test source, and frozen v2 metadata.

Both audits substantiate the request arithmetic, cache reuse, canonical reconstruction, historical-season restriction, and value of a recent-first archive. Neither establishes execution readiness.

Independent synthetic reproduction confirms that an entry decision at 16:55 with a 16:50 quote, verified first play at 16:52, and scheduled starts at 17:00 currently returns `eligible=True` and `actual_play_certified=True`. An arbitrary `side="NoSuchSide"` also passes. Therefore the second addendum's blanket assurance of timing safety is too broad; implement the targeted audit's corrections.

The proposal to add 54 independently scheduled close candidates counts games rather than incremental calls. Offline reconstruction finds 54 affected games (32 recent, 22 older), but their alternate sport/time requests require only **28 new union slots**, 14 recent and 14 older; 50 distinct alternate slots exist; 22 slots are already in the request union, covering 25 affected games. At 30 credits per request, the incremental ceiling is **840**, split **420 / 420**, not 1,620. These are planning estimates until the v3 builder and validator reproduce the complete request set.

Buying an alternate close candidate does not prove that its returned quote is valid or pre-play. Provider revisions, payload timestamps, conflicts, and actual-play evidence still determine eligibility. The example game's date or a final schedule alone must never certify actual first play.

## Ordered fixes

### 1. Write the v3 protocol and timing contract first

Owner: this chat, in the local research lab.

- Distinguish quote-snapshot time, requested decision time, simulated execution time, provider schedule-observation time, independent schedule time, and independently verified first play.
- Bind every price row to the exact provider ID, canonical identity, immutable source observation, and source response. Validate those bindings; a free-form old observation timestamp cannot authenticate a later kickoff.
- Use the schedule associated with the exact provider listing known at the decision. Simultaneous conflicting versions for that listing are quarantined. Conflicting IDs are not resolved by alphabetical ID order; selecting a quoted ID requires evidence linking the quote to it.
- If independent schedule availability is unverified, label its final kickoff a retrospective safety check. Never use it as a forecast-time feature or pretend it was known then. Preserve both the decision-time decision and the later safety/exclusion status.
- Separate snapshot-pre-play, decision-pre-play, and execution-pre-play certification. When first play is verified, reject a decision or execution at or after it even if the snapshot precedes it. Missing actual-play evidence means uncertified; an otherwise scheduled-pregame eligible proxy may remain eligible.
- Normalize totals to Over/Under and moneyline/spread outcomes to canonical team identity. Validate the team against the event and preserve provider home/away ordering as provenance. Generic home/away labels cannot join prices across the 42 flagged games.
- Give postponement, cancellation, unresolved settlement, and missing first-play evidence separate statuses. Preserve the existing paper-replay 24-hour listing/void policy for studies governed by it, including multiple listings. A later void must remain in attempted-decision accounting rather than erase the original entry. Do not equate this policy with verified settlement rules for every sportsbook.

Acceptance: the known counterexamples fail appropriately; a future schedule revision cannot pass as an old observation; unknown IDs/sides and unresolved conflicting listings cannot enter primary pairs. Tests cover exact start boundaries and delayed execution crossing first play.

### 2. Repair close candidates and opportunity accounting

- Keep existing close candidates and add an independently scheduled close candidate for each of the 54 games with discrepancies over five minutes. Deduplicate by the exact request/cache identity, add purposes and affected-game links even when a call already exists, and regenerate phase costs.
- Treat final schedule times as acquisition-planning metadata, not entry-time information. The response's exact event/listing and independently supported timing determine whether either candidate can be used.
- Freeze a provider-observed opportunity registry that retains every observed ID and history, including unmatched, contingent, displaced, and cancelled candidates. Record matching status as an attribute. Do not silently inner-join to played-game metadata.
- Document that the external NFL metadata universe is a played-game source, not a complete historical opportunity schedule. The current sweep registry is itself an observed universe, not proof of all opportunities ever available.
- Annotate unmatched IDs with candidate canonical games through other IDs, supporting evidence, and ambiguity. Link only uniquely supported resolutions; same pair and season alone is not sufficient to collapse an attempted opportunity or postponement listing.
- For the 73 recent unmatched IDs, inventory overlap with existing decision-time request slots. The audit reports nine absent candidate close slots across 19 IDs; classify these offline before considering any purchase. Do not buy every rejected listing's close automatically. Any additional purchase must appear in the regenerated v3 allowlist and ceiling.
- Preserve all 85 original reconciliation groups and the 2,293 legacy groups. Keep "absent from observed sweeps" and "first observed" wording; do not silently rename these to never offered or first listed.

Acceptance: every observed provider opportunity has a traceable status; every intended decision and missing reference survives coverage accounting. Primary paired-price counts reconcile to the starting population plus exclusions. Counts of provider IDs, canonical games, attempted decisions, and timestamp groups are reported separately.

### 3. Implement durable execution controls and coverage reporting

- Reuse the existing BulkClient and cache infrastructure. Freeze the wrapper and hashes of loaded request/cache/HTTP dependencies; verify them before spending. The run manifest also records the runtime and dependency versions. Freeze cannot cover only code that plans requests while omitting code that sends them.
- Require an independently supplied pinned v3 root and an exact priority-1 allowlist. No automatic expansion or older-season execution.
- Seed one persistent cumulative ledger from the completed probe's 1,687 credits, referencing its evidence hashes. Track this run, the tranche, day-one scope, and the broader budget without resetting them on restarts or a provider monthly reset.
- Hold a process lock; write and flush the worst-case reservation before any send. Use atomic durable writes, including parent-directory durability where required. Persist response identity/hash and billing evidence before marking an attempt reconciled.
- A timeout or crash after sending leaves an unresolved, conservatively charged attempt. Restart halts. Recovery may reconcile an existing validated response, but must never automatically resend an unknown attempt.
- Disable automatic retries in both the client and underlying transport. Reject missing or changed frozen probe caches rather than repurchasing them. Verify resumed responses against the ledger; an unexplained cache does not become a free completed call.
- Enforce slice, cumulative 250,000-credit tranche, existing 400,000 day-one and 4.44M broader limits, and 531,630 remaining-credit reserve. Reconcile provider usage and other activity; counters resetting never reset research spending. A local lock cannot prevent another application using the key, so shared-key usage must be detectable and documented.
- Fail closed on billing/balance problems, response or source hash mismatch, malformed timestamps, credential exposure, or unresolved accounting. Keep legitimate missing books/events/quotes as coverage statuses rather than silently dropping them.
- Produce an outcome-blind report by sport, season, month, book, market, lead time and first-observed strata. Include quote-age distributions, snapshot gaps above five minutes even when within the ten-minute eligibility ceiling, schedule conflicts, valid Pinnacle pairs, and every exclusion/unmatched opportunity.
- Stop unconditionally when the recent allowlist completes. A report file merely existing is insufficient for the older slice: require a separately recorded acceptance tied to the report hash and bundle root. Do not select an automatic coverage threshold after seeing the panel.

Acceptance: network-disabled rehearsal demonstrates that concurrency, changed files, missing caches, malformed billing, reserve breaches, monthly resets, external usage, and crashes at each persistence boundary allow no send outside the authorized allowlist or without a durable reservation, no automatic resend of an unresolved attempt, and conservative accounting with a halt on unreconciled billing. Test secret scrubbing using synthetic keys only. Replay cached probe responses and synthetic transport failures; do not treat rehearsal as permission for a live call.

### 4. Make verification portable and freeze once

- Package tests so they run from the frozen bundle in an isolated environment with no live-checkout paths or network access. Mutation tests operate on temporary copies, never the actual v2/v3 bundle.
- Strengthen the validator: exact MOS sport/time set equality, priority request sets and subtotals, request/cache equivalence, all reused-response hashes, source-observation bindings, expanded close-purpose mappings, execution-source hashes, and sealed-season exclusion.
- Add adversarial cases for the demonstrated entry bug, invalid sides/IDs, simultaneous conflicts, swapped neutral-site sides, midnight/DST boundaries, first-play boundaries, postponement listings, missing references and restart recovery. Preserve all existing meaningful guards.
- Preserve v2 as evidence. Save the protocol before building requests; produce v3, its change log, regenerated request list, validation results, and joint root. Keep execution status and mutable ledgers outside the immutable bundle.
- Perform one bounded final check of the corrected counterexamples, dedup/cost totals and offline execution rehearsal. No broad hypothesis redesign is required to finish this acquisition repair.

Acceptance: one pinned root binds the protocol, eligibility, opportunity registry, request plan, verification code and spending code; the bundle verifies and tests without relying on external mutable source files. A root is a byte-integrity certificate, not independent proof of registration chronology.

## Expected purchase budget and gates

If only the independently reproduced alternate-close additions change paid scope:

| Stage | Current v2 | Planned extra | Estimated v3 ceiling |
|---|---:|---:|---:|
| 2023–25 | 82,410 | 420 | 82,830 |
| 2020–22 | 67,590 | 420 | 68,010 |
| New purchases | 150,000 | 840 | 150,840 |
| Including completed probe | 151,687 | 840 | 152,527 |

Estimated v3 manifest: 5,052 calls, including 24 previously purchased cached calls and 5,028 new paid calls. Regeneration, union validation, and any explicitly added unmatched-event requests determine the final numbers; these estimates are not authorization to spend.

Gate A: protocol and code repairs complete, offline tests/rehearsal pass, v3 frozen and independently pinned, exact recent ceiling recorded, and recent purchase scope authorized.

Gate B: run only the recent slice, preserve raw responses and accounting, publish coverage before joining outcomes, and halt.

Gate C: review accepted coverage and whether older-era data adds useful coverage. Authorize the older slice separately; otherwise keep it unpurchased. Existing research thresholds and the sealed 2026 season remain unchanged.

No owner choice is needed to prepare these fixes. The next spending decision should concern the concrete v3 recent slice, after its final cost and verification evidence exist.
