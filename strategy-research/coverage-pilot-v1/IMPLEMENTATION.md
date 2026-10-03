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

Seven synthetic tests pass with process_guard evidence at
/private/tmp/coverage-pilot-planner-tests.json; tested identity
`e08c4e62abea0066b22bf96c30216c1bafe8a57e5ad649cdf97b4013f52f1bd4`.
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
