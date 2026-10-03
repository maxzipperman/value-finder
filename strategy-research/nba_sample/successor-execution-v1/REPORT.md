# Disabled N0 successor helpers — review report

Related #38, PR128 and auditor-owned PR167. This PR supplies pure checks and an exact historical-account interface; it does not connect the existing executor to a transport or create an approved packet.

## Implemented contract

`prospective.py` verifies the immutable v4 protocol and derives exactly one proposed change: first-tranche cumulative ceiling 250000 to 400000. Both returned adoption/paid flags are false. The original protocol and existing driver are unchanged. Existing day-one400000, broader4440000, reserve531630 and zero retries remain fixed. Conservative prior debit274586 plus candidate7540 equals282126; this arithmetic is not a current provider baseline.

The full754-row canonical set, stable historical request IDs, exact URL/public parameters and explicit10credit reservation bind to a captured plan identity. Plan hashes and receipt validation are consistency checks, not approval authentication. The factory and packet admission functions raise unconditionally, before consulting fake/session/approved inputs. No account initializer, key loader, transport, runtime writer or factory fallback is implemented.

`settled_projection` invokes the merged successor151 validator for the exact eleven historical roots. It validates a separately captured active N0 root before removing that root from the historical inventory projection, including root/authorization markers, initialization, full carry, completed known requests, exact receipt inventory and per-plan/account receipt agreement. Every attempt/receipt/record cache key must equal the frozen request identity, and plan record fetched_at must be present, timezone-aware and represent the same instant as account observed_utc. Replays preserve the original instant; equivalent offset representations compare as instants. Unknown or uncertain active attempts reject. Historical pending60 and F2 restrictions remain the merged validator's responsibility. Its supplied pins, marker and account receipts must be authenticated upstream by the eventual native admission; caller-supplied metadata alone proves no authority. Native raw response-file hashes are not revalidated here.

## Lock and account boundary

Source inspection and a source-bound assertion verify the real existing N0 driver acquires followup-purchase.lock before constructing the v4 Ledger (which owns acquisition.lock), then creates GuardedSession. Its per-send session.get seam is where a future account-owning wrapper belongs. This PR provides an interface only: purchase → plan → canonical account journal.json.lock; recurring callers take only account lock. Never add a second account lock around an account-owning wrapper or acquire outer locks inside account admission.

A temporary synthetic test additionally instantiates the actual v4 Ledger between outer purchase and synthetic account locks, verifies kernel contention for each lock and verifies release. It writes only temporary synthetic ledger state. This establishes real plan-lock behavior in that harness; it does not exercise a deployed account transport. No dynamic integrated account transport exists here. Operational lock ownership, contention, recurring/manual writer integration, source/month no-reset migration, fsync/crash windows, provider billing regressions and cap/reserve concurrency remain unverified and block adoption. Static source inspection does not establish deployed deadlock freedom. Account receipts must preserve original observation UTC and billing on replay; the pure test validates fields, not durable replay behavior or actual zero-cost recovery. Timestamp equality does not authenticate either input or reject a jointly forged future clock: future-bound checks require an explicit trusted captured reference in upstream admission, never an implicit current-time read.

## Provisional coverage rationale and fixed denominator

The intended H1/H2 feasibility work needs an independently timestamped decision/start join, same-response two-team h2h pairs for each declared book, original quote freshness, mapped Kalshi market, executable price/fees and matching settlement terms. A game counts usable only when its predeclared required timing/paired-price cells exist; snapshots/books/minutes of that game are not additional independent games. Freeze exact required cells and minimum usable independent games before any sample quotes are read.

80% is only an initial economic/usability proposal allowing no more than11 of56 games to be unusable (minimum45); it is not statistically derived and is not adopted. The bounded purchase cost at45 usable games is at most167.56credits/game. This does not yet demonstrate that45 games can answer H1/H2: the analysis owner must justify an absolute minimum using the paired timestamp/price design and intended precision. If that minimum or day/cell coverage cannot be justified prospectively, leave the gate unadopted; never adjust it using observed quotes/results. At80% per day, the immutable metadata denominators and rounded minimums are:

| ET listing day | Fixed games | Provisional minimum |
|---|---:|---:|
| 26JAN05 | 8 | 7 |
| 26JAN06 | 6 | 5 |
| 26JAN07 | 12 | 10 |
| 26JAN08 | 4 | 4 |
| 26JAN09 | 10 | 8 |
| 26JAN10 | 6 | 5 |
| 26JAN11 | 10 | 8 |

These listing dates are candidate metadata, not independent schedule-as-issued/start certification. The expected-expiration-minus-three-hours tip proxy is not an executable quote or first-play clock. Report all56/all7days, every original request slot, and missing reasons (unknown independent clock, unmatched identity, missing book/pair/required timing cell, stale quote, missing executable market/fee/terms, cancellation) without dropping or replacing games. Disjoint primary missing reasons and overlapping secondary flags must reconcile to fixed denominators. Per-book/day/cell yields remain visible; post-tip observations are descriptive only.

This seven-day census cannot establish full-season representativeness, independence-based precision or a sports edge. Existing N1 H1/H2 gate remains intact, no variant count/registered analysis changes, no full-season release, no grading/quote/outcome inspection. Any readiness threshold needs separate prospective review/adoption.

## Validation and remaining holds

46 focused source-bound synthetic tests cover exact protocol/set/request/plan mutation, retained historical state through the actual successor validator, active-root attribution failures, original receipt clocks/bills, static actual-driver lock order and unconditional production holds. Synthetic pins and receipts are marked synthetic; no native runtime authentication claim is made. EVIDENCE.json records the exact input inventory, interpreter/environment and command. Prior PR128 evidence is not asserted valid after STATUS changes. Native complete v4 captured-file acceptance remains unverified; ignored native probe parquet was not restored/read.

Production adoption still needs authenticated current inventory/cache/account exposure, reviewed historical/manual writer integration or enforced exclusion, all required crash/concurrency/lock proofs, prospective protocol adoption and exact current list/set/root/cap/source-commit paid authority. No paid calls, account query, native raw quotes, outcomes, keys, runtime state, live jobs or deployment touched.

READY FOR THE HUB for separate independent review of disabled source infrastructure. NOT READY for execution or packet freeze. Author does not self-AGREE.

## Independent review repair

The reviewer reproduced two P2 consistency gaps on5644ee73: cache keys could agree across supplied layers while differing from the frozen candidate, and timestamps could disagree or be absent. Both are repaired here. 13 new regressions cover consistent wrong/malformed cache keys, request-key binding, missing/malformed/naive/divergent plan times, changed account future time, and equivalent original replay instants. The active fixture now includes original fetched_at. No transport/adoption changes.
