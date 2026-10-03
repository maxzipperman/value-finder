# Implementation checkpoint

Planner and integration primitives implemented; verified offline bootstrap implemented; no runnable paid entrypoint yet. LOCAL-BECAUSE:
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

Planner/timing synthetic tests pass with process_guard evidence at
/private/tmp/coverage-pilot-planner-tests.json. The current tested identity is recorded
in that artifact and the PR handoff; earlier checkpoint identities are superseded.
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

## Receipt/request integration checkpoint

- Exact original older ID union, including three-ID costs and no-request rows.
- Six-market props cells exclude completed, absent, missing, pending and uncertain
  prior cells. Overlapping book panels do not double-buy cells; partial reuse can
  fragment requests, so only the actual union sets the cap.
- Finite selected-ID HTTP200 lag and event-odds EVENT_NOT_FOUND404 zero-bill
  classification. Other HTTP, future/malformed data and overcharge reject.
- Prospective parquet/receipt validation binds raw bytes, exact request/cache key,
  ledger reservation, bill and classification. Complete global inventory splits
  only into authenticated historical base and explicitly bound pilot epochs.
- New baseline extraction passed read-only against all seven actual stores with
  conservative debit170,306; baseline.py hash
  e85672d2232876cbfdb3539144bda0a428d05a8480054a8744a2274742c1ab67.
  All actual ledger hashes unchanged. No real prospective pilot exists or was tested.
- Captured v4 GuardedSession adapter checks live authority and unchanged inputs
  before each GET; targeted synthetic use of the real guard confirms revocation
  prevents send, redirects are disabled and a started reservation cannot resend.
- Final look binds frame/protocol/draw/terminal-evidence hashes and classifications;
  exclusive durable creation refuses overwrite. Pure helper still relies on the
  caller to authenticate terminal evidence and predeclared bound identities.
- Reviewer defect fixed: stratum sample sizes now match BOTH the committed protocol
  digest and committed seed record; changing n while preserving commitments fails.
  Planner/timing verification now has explicit test selectors rather than a broad
  discovery command that could execute undeclared tests.

Cost gate correction:244 credits per newly usable props game includes both
selected availability requests;240 is price-only and is superseded. Older stays100.
Pair definition: same player/book WITHIN each family across times, not the same
player/book across all families. CFB remains quote-coverage-only.

Still outstanding (not claimed complete): paid orchestration under the global lock; final frame-to-opportunity classifier wiring;
metadata stage identity/schema/policy and exact selected union; real synthetic
crash/restart end-to-end checks using that orchestration. The factories alone do
not constitute a runnable or approved executor. No production seed/list exists.

The offline bootstrap now verifies exact packet inventory, all declared pilot code,
reviewed historical dependency bytes and the immutable v4 source inventory before
loading captured modules. The offline packet validator reconstructs six-market
props requests and exact original older rows, and binds selected mappings/list/cap.
A synthetic full packet passes; changed packet bytes reject. This is not proof that
the final frame/classifier adapter or paid orchestration already exists.

Current verification artifacts (latest identities in their JSON and PR handoff):
- /private/tmp/coverage-pilot-planner-tests.json:8 selector/accounting +5 timing tests.
- /private/tmp/coverage-pilot-bounds-tests.json:6 exact-bound tests.
- /private/tmp/coverage-pilot-integration-tests.json:13 integration tests.
All use the pinned football review interpreter. Integration evidence covers the
entire pilot directory and captured historical dependencies; planner/timing uses
explicit test selectors so the new bounds/integration suites cannot enter silently.
The first integration attempt under ambient Python failed its dependency-origin
guard before running tests; the reviewed interpreter is required, not a loosened
capture policy. No real-state write, provider request or credentials were involved.

## Executable review checkpoint (October 2)

The sibling executor is implemented: captured bootstrap and selected-frame binding,
fixed shared lock, full authenticated history, exact receipt-bound reused IDs/cells,
metadata-only semantic overlap, live authority/account binding, durable reservations,
4RPS/no retries, clean pause and fail-closed crash/reopen. This supersedes the
earlier unfinished-code statements above. The final existing frame and slot pins
were verified; certainty.py reports fixed-sample attainability, without a draw.

Saved integration evidence now covers 15 integration, 6 classifier, 2 orchestration
and 4 binding/reuse/overlap tests; bounds evidence covers 7 tests. Crash checks
include the actual PilotLedger.complete after-receipt cut and reopening refusal.
Strict selected props and older bindings pass synthetic positive fixtures; wrong
provider/slot, incomplete cells, changed receipt and overlapping query fail.
The orchestration fixture uses real lock/ledger/cache/transport but MOCKS historical
bootstrap, authority, baseline and overlap adapters. The real seven-store baseline
proof remains separate. Neither constitutes a complete live paid preflight.

Concrete remaining gates: independent current-head code/protocol review; hub's
once-only draw and exact residual union; frozen packet with each reused slot's
terminal historical root/request/receipt/raw pins and complete book/market cells;
current full shared-state/cache verification, exact cap and live active authority
with current account reconciliation. No production draw/list/paid authority or
statistical release has been created. Terminal final-look helpers require separate
authenticated classifications and saved bounds; acquisition does not auto-release
a later tranche. Uncached prior attempts cannot support a reused-slot proof: they
remain excluded from repurchase and require a frozen zero/failure disposition.
