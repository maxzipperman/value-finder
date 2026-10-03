# Implementation checkpoint

Pure planner implemented; no executable purchase adapter yet. LOCAL-BECAUSE:
this adapter will bind Mac-only historical receipts and inventory; this checkpoint
uses synthetic inputs only and does not inspect operational data.

- Canonical full frame retains unbound zero rows; rejects duplicate identities and
  sealed/out-of-scope seasons. Census allocation can be zero.
- Deterministic selection requires externally committed frame, protocol and seed
  record digests; no randomness or record creation. Caller must authenticate those
  committed references, not compute them from untrusted replacement inputs.
- Original-ID residual excludes completed, missing, pending and uncertain attempts;
  unresolved attempts block execution, while original denominators remain intact.
- Prospective inventory checks exact baseline/child union, predecessor inventory
  binding and retained cumulative debit. This is an invariant checker, NOT receipt
  authentication. Never call it alone to declare real-state acceptance.

Twelve synthetic tests pass with process_guard evidence at
/private/tmp/coverage-pilot-planner-tests.json; tested identity
`0944499a700f556d1e076324a8d8e54ca8a97a6b5ae7e91b3845a45622d4d993`.
Tests cover changed frame/seed/protocol, duplicate identity, missing binding,
sealed season, census reuse, all-attempt subtraction, changed/missing/rogue stores,
forked epochs and retained-reservation cap overrun. No old suites repeated.

Next implementation: map exact original requests and props market cells to selected
opportunities; extract authenticated baseline/prospective receipt validation from
reviewed history without hiding roots; captured transport and authority bridge.
Final classifier/frame and finite missing-response policy remain concrete external
prerequisites for freezing an executable packet, not for continuing pure code.
No actual seed, request list, authority, paid call, credentials, outcomes or runtime
mutation was created by this checkpoint. All purchase holds remain in force.

Prospective timing.py adds a mandatory veto for entry AND close: every request,
snapshot and historical execution clock must precede every supplied provider and
independent scheduled kickoff. Equality fails. Invalid/missing/naive clocks,
future snapshots and execution before decision fail. A valid result remains a
scheduled proxy and cannot rescue base ineligibility or certify actual play.
The execution clock means hypothetical historical fill, never acquisition time.
This helper still needs wiring into the new classifier; installed v4 is unchanged.

Latest sequencing: existing-frame measurement first, without comprehensive listing
claims. Eight-market conditional bound is51,300 (500availability+40,000props+
10,800older), not52,844; six-market NFL reduces this by4,000 before other changes.
Full1,544listing remains held for separate review and expanded-frame revalidation.
If older mapping needs three original requests/game, recalculate before freezing.
Statistical review proposes error allocations .02 existing/.02 added/.01 optional;
original bounds are reused, never rerun until pass. Marginal cost uses newly usable
unknown-cohort games, never already-purchased census successes. These sequencing
corrections supersede the listing-inclusive illustration in DESIGN.md; none grants
paid authority. Final classifier and error contract still need independent approval.

Math checkpoint: bounds.py implements exact hypergeometric inversion, fixed alpha
allocations, census behavior, marginal cost/utility and weighted reporting without
pooled release. Six additional tests passed (separate evidence). MATH-REVIEW.md
independently assesses the statistician's proposal; another reviewer must review
this implementation. PRIMARY-CONTRACT.json fixes six proposed markets and41,300
existing-frame gross illustration, superseding prior eight-market estimates.
