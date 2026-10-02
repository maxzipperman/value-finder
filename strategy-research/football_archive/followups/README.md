# Follow-up acquisition preparation

The owner authorized the next download if the hub's checks pass, and waived the backup gate.
This branch needs the independent auditor's agreement on its exact final head before execution.
No paid call is authorized by a draft packet or this document.

This work needs the Mac: it reconciles local paid caches and the completed cumulative ledger.
The completed v4 bundle is immutable. Its exhausted approval cannot authorize a follow-up.

F2 buys NFL alternate spreads/totals in 2023–25; F3a buys six NFL prop markets in 2025.
The inventory preserves provider-only events and missing listing bindings in denominators.
Binding uses the last available sweep at or before the requested instant. It never claims an
unseen event was never offered, or a first observation was a first listing.

Proposed slots are T−24h and T−10min relative to the earlier independent scheduled clock.
That clock is a retrospective safety restriction, not an input claimed to have been known
at decision time. Provider-only events lack independent clock verification. A scheduled
pregame snapshot is not independently verified before first play. These packets authorize
acquisition only: registration amendments and quote-age/identity eligibility precede grading.

F2 starts with a deterministic, outcome-blind pilot: the first eight canonical NFL games
after September 1 in each of 2023, 2024 and 2025, both slots. The pilot is part of F2's list,
not an extra purchase. The remaining list must reuse the pilot's paid responses. A coverage
report and independent review precede the remainder, F3a or older F1.

## Report for the hub

READY FOR THE HUB to review, NOT READY to spend until independent exact-head agreement and
new paid approval. Cache reconciliation and 50 adversarial follow-up tests passed; all 146
original v4 tests also passed. No credentials, outcomes or sealed 2026 data have been opened.
Run at 4 RPS, zero retries, only after exact CSV/request-set/budget/root/commit approval. The
reviewed predecessor carries 86,212 credits conservatively, including the 1,687-credit probe.

The exact F2 candidate list is 1,773 requests / 35,460 credits; F3a is 570 / 34,200. Those
counts preserve provider-only opportunities and one unbound F2 opportunity. The 48-request
pilot costs at most 960 credits and is included in F2, leaving at most 34,500 after reuse.
This executor refuses the remainder, F3a and older F1; extending it requires separate review.
No new strategy grading, forecast replay, simulation, model fit or holdout access is enabled.

`prepare.py` is offline and regenerates selection, exact-key cache reconciliation, predecessor
pin and pilot freeze. Never regenerate an active packet or silently adopt a changed predecessor.
`epoch.py` verifies offline by default. `--confirm` additionally requires authorization matching
the authenticated hub comment on PR #99, the frozen root and exact checkout commit. It verifies
all original frozen bytes/runtime versions, the clean committed packet, source-generated selection,
ancestor debits and caches before reading a key. A fixed global lock, root registration marker,
durable reservation and durable send-start prevent competing follow-up epochs and resends.

On any stop, preserve the ledger and response. No automatic retries or recovery are implemented.
Pending paid attempts require separately reviewed, hash-pinned offline recovery or missing
acceptance before a later run. Stopping is an expected controlled state, not permission to
generate a fresh root and send again. Seed ancestry prohibits rebuying every earlier attempt.

`pilot_coverage.py` checks receipt/cache hashes and the predeclared gate: at least 90% valid
responses and 12 canonical games (at least 4 per era) with the same named book's fresh alternate
spread and total curves at both times, two points per side. No actual-play certification is
claimed. Missing reference/books/markets and failures stay visible. A pass permits review of
the remainder; it does not authorize it or establish a betting edge.
