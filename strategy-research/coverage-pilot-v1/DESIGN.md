# Prospective bounded coverage pilot — design for independent review

October 2, 2026. Related to #130. DRAFT: no executable purchase, sample seed,
request selection or paid authority. LOCAL-BECAUSE: implementation must authenticate
Mac-only cached receipts and historical accounting. No keys, provider calls,
outcomes, sealed seasons, runtime mutation or live jobs in this design work.

## Boundary and sequence

Build a NEW sibling adapter. Do not modify installed PR129 recovery.py/PROTOCOL,
executed freezes, or run the 1,786-row continuation to obtain a sample. Do not
parameterize its hardcoded 53,580 cap. Existing full listing/availability/price
stages remain held. PR132's engine.run is also NOT reusable as a pilot runner:
it deliberately accepts exactly 1,544 listing requests.

1. **Cache-only classification:** authenticate existing history, then classify all
   intended game pairs using committed outcome-blind timing/identity/pair rules.
   Known success/failure classifications become a frozen certainty component.
   A partially cached pair stays unknown; a certified terminal-missing necessary
   slot makes the pair a known failure and cannot be repurchased.
2. **Frame preparation:** separate older original-list frame from NFL/CFB props
   observation/schedule union. Do not join outcomes or played-only tables to select
   games. Include unresolved, late, cancelled/contingent and provider-only identities.
   Freeze all-game and bound-provider denominator layers. Missing binding has zero
   primary usability, not exclusion from the frame.
3. **Bounded frame-discovery stage if required:** selected finite listing requests
   require their own protocol/list/cap/authority. It is not permission to run all
   1,544 listings or 7,032 market-availability calls. The statistician must resolve
   the frame-coverage limitation before the final once-only draw. Never silently
   add newly found identities after freezing the frame or substitute easy games.
4. **Once-only draw:** after frame and protocol are committed, hub generates one
   OS-random 256-bit seed and commits a draw record before new selected prices.
   Hash canonical JSON [seed, stratum, identity], tie-break by identity, and take
   the prescribed sample from unknown games without replacement. Record seed,
   frame/protocol hashes, n/N and selected identity hash. A seed cannot be replaced;
   planner requires the previously committed seed record on every rerun. Seed
   generation is a separate preparation operation, never part of paid restart.
5. **Selected availability and price stages:** freeze only selected opportunities,
   including no-request denominator rows. Older slots are original request IDs:
   nearest eligible original daily snapshot 18–54 hours before anchor plus original
   close, with deterministic tie-breaking fixed before classification. No exact T24
   substitution. Shared sweeps deduplicate by identity; incidental games never
   increase sample size. Props use T24/actual scheduled close and declared book panel.
6. **One final measurement:** only after every selected attempt is terminal and
   certified, produce game-level paired coverage and the predeclared finite-population
   bound. A pending attempt blocks a final release; it never triggers replacement.
   Gate release is basket-specific and binds the exact evidence digest. Operational
   halts are not statistical passes. No full stage automatically follows a pass.

## NFL 2025 census and revised planning arithmetic

The existing 570 F3a requests cover the 285 currently known NFL 2025 identities as a census for the original six
markets. Use its exact quote-coverage classification without drawing another 50
or attaching sampling uncertainty. Hub's reported 215/285 proposed core successes
must be reproduced under the final registered acquisition classifier before being
bound into a gate; this design does not independently certify that external result.
The independent reviewer reports strict-clock coverage of 215/285 for any eligible
retail book with at least two families at early and close, versus 66/285 (23.2%)
for fixed DraftKings early-and-close and 192/285 for fixed DraftKings close-only.
These are three separate metrics and gates; archive-union coverage cannot release
a fixed-book early strategy. These supplied counts still require reproducible
classifier evidence before freezing. Quote availability does not establish executable
edge or settlement support.

The new eight-core-market proposal adds passing/rushing attempts, which are NOT
covered by that census. Those two markets do not define the four-family core gate.
Do not purchase them merely to pretend the census needs another sample.

| Component | Conditional planning upper bound, credits |
|---|---:|
| Older unknown-frame samples: at most 180 games × two original slots ×30 | 10,800 |
| Props unknown strata: NFL2023/24 + CFB2023/24/25, at most250 games ×2 ×8 ×10 | 40,000 |
| Selected availability for those250 games: at most500 one-credit calls | 500 |
| Listing frame discovery, IF separately justified and authorized | up to1,544 |
| Illustrative total before further authenticated reuse | **52,844** |

This replaces the draft54,944 estimate, not an approval cap. Adding52,844 to the
reported170,306 conservative carry yields223,150, leaving26,850 beneath the250,000
first-tranche ceiling before other usage. Exact game counts, early-slot mappings,
shared sweep reuse, metadata needs and counter reconciliation can change these
figures. More than two original requests/game invalidates the10,800 assumption.

If frame discovery finds genuinely new NFL2025 identities, reconcile the frame
before drawing. Up to50 genuinely unknown games at eight markets/two slots plus
100 availability calls adds8,100: the conditional bound becomes60,944. This is
not authority to sample50 already-cached games. Exact cap follows the reconciled
frame; the285 census claim is limited to the currently known identities.

**Practical minimal proposal:** use the six supported NFL markets for the primary
NFL purchase, deferring passing/rushing attempts until a reviewed settlement plan
exists. Removing those two markets from the100 unknown NFL2023/24 games saves
4,000 gross credits, giving48,844 under the otherwise unchanged eight-market CFB
assumptions. CFB settlement remains unsupported: its quotes can measure archive
coverage, but cannot be labeled gradable. Resolve whether to defer that basket or
fund it explicitly as coverage-only before freezing. A six-market basket across
all250 unknown games would instead imply42,844, but requires a separately agreed
CFB market/support contract; this is arithmetic, not a recommended approved cap.
Do not buy extra markets to certify the existing four-family primary metric.

Optional completion of the two additional NFL2025 markets across all285 games
would be11,400 gross credits (285×2×2×10), separately justified/listed; it is not
needed for the four-family census gate. Optional exotic/depth tranches are deferred,
not included. Do not reuse the old45,600 optional estimate without accounting for
its changed sampling frame and existing market cells. Books above ten require
re-costing. No negative cost deduction for unverified cache equivalence.

## Exact reuse architecture

| Existing reviewed component | Reuse boundary | New code required |
|---|---|---|
| PR132 entry/capture/history at3f63f6a | Capture verified bytes and call read-only historical certificate/receipt validators | Bootstrap binds these dependency hashes plus new selector/gate/policy; no ambient imports or mutable rereads |
| PR129 verified_partial and original packet proof | Read-only proof of installed transition, original rows and retained reservations | Select a strict subset; never invoke its install/prepare/run for sampling |
| Immutable v4 Ledger/GuardedSession | Captured accounting and one-send transport with exact allowlist | New bounded manifest bridge, finite pilot policy, authority checks and stage classifications |
| Existing RawCache/receipt formats | Exact key/endpoint/params and raw bytes authenticated | Market-cell reuse index; no fetch on ambiguous/uncertain overlap; residual markets only when compatible |
| PR133 props reader, pending separate review | Outcome-blind quote/schedule clocks and exact F3a receipt handoff | Paired same-player/book intersection by game/slot, point/reference layers and explicit missing denominators |

**Important integration gap:** PR132 global_inventory cannot simply be called on
a future pilot store and expected to recognize it. Its historical checker permits
specific existing epoch families and detects actual children of the older partial.
The new adapter must explicitly verify two disjoint inventories: (a) the exact
historical seven-store base, through the reviewed validators, and (b) all prospective
pilot successors through the new finite-plan verifier. Then validate their joined
registration inventory and one carry chain. Do not monkeypatch roots, hide stores,
copy runtime to bypass checks, or relabel a pilot as older_epoch_complete.

Implement a pure inventory-validation boundary taking captured base state/paths;
review its narrow extraction/adaptation against PR132. Read all filesystem inventory
once under the global lock, reject every unrecognized/missing ledger/marker, verify
base certificates/receipts, and verify each prospective successor against its bound
plan and full terminal receipts. Freeze the captured baseline identities. Any base
change or new store must be reconciled and reviewed, never ignored. A later adapter
must also recognize pilot epochs before metadata/N0/full residual can execute.

## Frozen pilot contract

A pilot content root binds:

- Frame, classifier, protocol, certainty component and once-only seed/draw hashes;
  all selected game/opportunity IDs, including unbound/no-request failures.
- Exact deduplicated request list with endpoint/sport/time/markets/books, maximum
  debit per request, supported response schema and request→game/week/cell mappings.
- Cache union: completed usable cells, requested-but-absent cells, certified missing,
  and reserved/uncertain cells separately. Reuse six NFL2025 cells including absence;
  never retry an absent cell under a differently grouped market request.
- Historical baseline and certified older transition; predecessor ledger and full
  cumulative debit, probe counted once, and all prospective prior pilot receipts.
- Finite missing policy and terminal states. Suggested initial categories: exact
  documented event-not-found zero-billed response for listed allowed IDs, and known
  HTTP200 snapshot lag. Each allowed endpoint/category/count/bill ceiling must be
  independently reviewed; unknown/malformed/future/overcharge/timeout always halts.
  No generic404 category and no broad v4 rule relaxation.
- Verified executable dependency closure, runtime lock, account reconciliation,
  reserve floor531,630, cumulative4,440,000 and existing first-tranche250,000 cap.

Live exact hub authority binds content/list/cap/commit, baseline inventory, policy,
account ceiling and current active status. Under shared followup-purchase.lock:
verify before key loading; authenticate live authority and source/shared state before
EVERY GET; preserve durable reserve→send_started→raw cache→receipt→terminal ledger.
Zero retries/redirects. Crash/uncertain response retains reservation and blocks
resend. Clean restart re-verifies unchanged receipt union and sends only never-attempted
IDs. Completion exhausts that pilot authority and writes an outcome-blind evidence
manifest; it does not release a bulk runner.

## Residual subtraction is part of pilot safety, not later cleanup

Build a terminal union across original parent, all certified pilot epochs and reused
cells. For older featured data subtract **every attempted original request ID** from
the1,786 predecessor remainder, including missing and uncertain attempts. Pending
attempts still block successor execution even though excluded from its candidate
list. Retain every original opportunity in the denominator and map it to existing,
pilot, residual or terminal-missing evidence. A shared request is purchased once.

For props, subtract book/market/time/event cells using authenticated compatible
requests, including requested-but-absent cells; do not subtract on event ID alone.
A response to a market subset does not prove unrequested markets absent. Never
add a market to a request merely to resend previously attempted cells. Unknown
compatibility blocks planning. Freeze a NEW residual list/cap and exact authority;
the original full successor approval is unusable after a pilot changes the union.

## Statistical review and concrete blockers

Starting draft proposes older30 and props50 unknown games per sport/year stratum,
one final look, exact hypergeometric-tail inversion, known/census components treated
as fixed, and alpha0.04/12 for primary strata with unused census allowance unused;
optional0.01 remains reserved. Proposed basket floors60% older/50% props and cost
ceilings100/320 credits per usable game require statistical reviewer ratification.
The final protocol must explicitly settle same-player across markets versus per-market
players, eligible accessible books/reference requirements, missing classifications,
source/frame coverage, finite population endpoints, pooled-year weights and clustered
request/week reporting. Do not infer future-season iid performance from this gate.

Implementation is NOT ready to purchase. Next concrete work:

1. Statistical reviewer publishes the final classifier/sampling/gate contract; hub
   identifies its version and finite frame-discovery authority, if any.
2. Implement pure selector, cost/residual planner and synthetic tests against frozen
   metadata; no seed draw until frame/protocol are committed. Authenticate cached
   census/known components without touching outcomes.
3. Implement the prospective union verifier and captured transport adapter with
   targeted crash/no-resend, authority revocation, ledger loss/branch, overcharge,
   equivalent-cache and residual-subtraction tests. Do not rerun unchanged suites.
4. Independent reviewer validates source plus real read-only global acceptance and
   final selected packet; hub alone grants exact pilot authority and executes.

This document is a reviewable architecture, not a promise that missing integrations
already work. No installed executor or historical freeze is changed.
