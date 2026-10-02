# October credit queue — Codex hub

Updated October 2, 2026, after the owner's instruction to prioritize efficient use of the prepaid month.
This is the current operational queue; it supersedes the old day-one F1/probe sequence. It is a plan,
not an executable request list or paid approval. No new purchase is authorized by this document.

## Owner decisions and completed work

- The owner explicitly waived encrypted off-device backup/restore as a purchase gate in hub chat:
  "i dont need a backup, more concerned iwth efficient use of my credits over this month".
  PR 106's tested source correction is optional backup support, not a reason to delay downloads.
- Recent F1 is DONE: 2,761 paid requests handled, 82,830 credits, 12 probe responses reused,
  one approved missing. Never run the generic F1 week/full command or re-run the archive probe.
  The one-time #99 authorization is exhausted. Reader repair #105 is merged; registration remains disabled.
- Keep local cache bytes, receipts, cumulative spending history and restart-safe reservations.
  These controls prevent duplicate charges and remain required. The backup waiver does not waive them.
- Use the prepaid month to buy reusable data needed for registered tests; useful information per credit
  is the goal. An unused credit is preferable to an unnecessary duplicate or an unmotivated large pull.
  Free simulations and validation begin promptly after each dataset is complete and its analysis is registered.

## Purchase sequence

All figures below are credit ceilings, not live balance measurements or frozen exact costs.
Run one paid purchase at a time. Derive the actual list and cache deductions before approval.

| Order | Dataset / purpose | Maximum new credits | Dependency and current state |
|---|---|---:|---|
| 1 | F2: NFL alternate spreads/totals, T−24h and registered close slots | 48,000 | Prepare exact unsealed list, reuse existing provider inventory and caches; review kickoff/identity/close eligibility. Not executable yet. |
| 2 | F3a: NFL 2025 six-market player-prop slice | 36,000 | Exact `2025` scope only; no automatic F3b expansion. Freeze list and coverage/book-selection procedure first. |
| 3 | N0: NBA January 5–11, 2026 sample week | 8,000 | Use the NBA pipeline's schedule A and existing cache, not generic football F1. Review exact list/cost. |
| 4 | HB1/HS1: qualifying 2024–25 heat-game closes | 16,000 | Free venue/forecast joins and registered trigger first; buy only qualifying slots, deduplicated by actual request identity. |
| Parallel preparation; execute at earliest ready point between runs | Older F1: NFL/CFB 2020–22 daily/close slice | 68,010 | Existing exact 2,267 paid + 12 reused slots. Outcome-blind recent coverage acceptance and separately reviewed cumulative-ledger priority-2 runner required. No calendar wait for October 20. |

F2/F3a/N0/heat together reserve at most **108,000 new credits**, plus at most **68,010** for older F1.
Including the completed recent F1, this is **258,840** in these named purchases; the probe, live alerts,
external spending and other earlier purchases are additional and must remain in the cumulative account ledger.
This leaves most of the 5M allowance for larger pulls whose data actually justify proceeding.

## Schedule and gate decisions

Dates are targets, not permission to skip a dependency. Use the actual allowance reset date once confirmed.

- **Now through October 7:** freeze/review the first lists, reconcile all local caches, and execute ready
  Phase 1 runs consecutively. Prepare the older runner concurrently with list review; do not wait for a backup.
  After each run, publish credits, missing/excluded coverage and any stop before authorizing the next one.
- **October 8–14 target:** resolve the outcome-blind older-coverage decision, execute the approved older slice,
  and complete the prospective price-engine amendments. Run free registered analyses as dependencies finish.
  This target is about finishing the six-season dataset early enough to evaluate the hourly gate.
- **By about October 20:** read the existing F3b, N1 and F4 gates; freeze/review only those larger request
  lists whose registered gate passes. No automatic purchase on an unread, failed or inconclusive gate.
  F4 requires both sports in four of six seasons; recent three-season data alone cannot satisfy it.
- **Before the allowance reset:** execute approved passing-gate purchases with a completion/recovery buffer.
  The existing October 25 cutoff for unread gates remains unless prospectively amended.
  This queue creates no subscription renewal or next-month purchase.

The old estimates for larger pulls remain estimates: F3b ~102,600, N1 ~486,440, F4 ~1,442,220 net of F1.
Do not authorize those numbers without recomputing exact lists, overlaps, scope and available credits.
No sealed 2026 football/NHL or 2026–27 NBA outcome is inspected or used to decide what to buy.
Any sealed-data acquisition needs its own explicit scope/approval and isolated storage.

## Controls before each exact approval

1. Commit/freeze endpoint, UTC timestamp, event identity, books, markets, scope and per-request maximum cost;
   publish request count, list hash, reuse hashes, total new-credit ceiling and execution commit.
2. Reconcile across the completed archive, probe and every bulk/NBA/weather cache. Deduplicate on endpoint
   plus parameters and snapshot, not pull name. Preserve cancelled/contingent/provider-only opportunities
   and unknown identities in the coverage denominator; played-game matching alone cannot select a universe.
3. A durable cumulative ledger includes the 1,687-credit probe, 82,830-credit completed run, other purchases,
   live/external account movements and unresolved worst-case reservations. New epochs do not reset history.
   Pending/uncertain calls require approved reconciliation; no automatic retry or repurchase.
4. Obtain independent agreement on current execution head and hub exact-list/budget/commit approval.
   Honor the local cache-first, circuit-breaker, credit-floor and single-purchaser controls. Run at 4 RPS
   unless a different reviewed execution plan is approved; speed does not change historical data value.
5. Outcome-blind coverage completion/report precedes the next paid stage. Grading is separately gated on
   registered rules, executable decision-time inputs, quote/close policy, season scope and trial accounting.

The hub owns list approvals, accounting, execution and this queue. The auditor reviews each current head.
Workers report implementation/list blockers through PRs; they do not create overlapping purchase plans.
