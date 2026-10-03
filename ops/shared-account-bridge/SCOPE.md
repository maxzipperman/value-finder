# Shared-account bridge: scope-first proposal

October 3, 2026. Requested by the hub after PR165 merged as disabled infrastructure.
**Proposal only: no implementation, adoption, numeric budget, permission or execution.**
The unconditional collector installation/send hold remains intact.

Source provenance: inspected isolated `a9dbf048c4059e2c292d58b2ecc2fae0e8c929e4`.
GitHub connector comparison to merged `f746e78cb042390d7f52d46edb239acbed0cfa01`
shows only dashboard files differ. STATUS/GOVERNANCE were fetched at that merge.
No credentials, provider, outcome, acquisition-ledger or live-runtime files were read.
Source-defined jobs are not evidence of their current installed/running state.

## Inventory and boundaries

| Role / entry | Current paid boundary (repository-relative evidence) |
| --- | --- |
| NFL alert | `scripts/alerts.py:186` -> `nflweather/board.py:141` -> `nflweather/oddsapi.py:102` (paths under nfl-weather) |
| CFB alert | `scripts/alerts.py:73` -> `cfbweather/board.py:209` -> `cfbweather/fetch.py:225` (paths under cfb-weather) |
| NFL close | `nfl-weather/scripts/capture_close.py:135` -> same NFL live boundary |
| CFB close | `cfb-weather/scripts/capture_close.py:119` -> same CFB fetch boundary |
| NFL trigger | `nfl-weather/scripts/poll_triggers.py`, explicit `tag='poll'` -> disabled collector entry |
| CFB trigger | `cfb-weather/scripts/poll_triggers.py` -> `cfbweather/live.py::live_totals` -> disabled collector entry |
| NFL props | `nfl-weather/scripts/log_props.py:61` -> `_get` with event/offset identity -> disabled collector entry |
| NBA collector | `sharp-markets/src/markets/collector.py:148` -> disabled collector entry |
| Manual boards/history | Same weather API funnels; NFL `historical`/backfill also reaches `_get` without collector role |
| Generic sharp historical | `sharp-markets/src/markets/oddsapi/client.py::OddsApiClient` -> `bulk.py:675` -> `_Sending.get:497`; bulk default max_retries6 is not the frozen zero-retry wrapper |
| Frozen football / prospective successor | Original v4 executor has per-epoch `acquisition.lock`; pilot/pass/recovery orchestration uses `followup-purchase.lock` before its prepared-loop/HTTP-factory boundary |
| N0 preparation | `strategy-research/nba_sample/execution-v1/stage.py` prepares/validates ancestry and packet; it is not evidence of an approved runnable integrated transport |

Current lock domains do not coordinate: historical followup lock, original per-epoch
lock, and collector private primitive's ledger-sibling lock. Alerts/close bypass them.
The legacy quota file observes post-response usage and is not admission accounting.
An inventory of names or a `ready` flag cannot establish participation.

## Recommendation: two bounded stages, one contract

This is materially larger than one collector repair. Confirm/narrow scope before coding.

1. **Account admission and live caller integration.** One durable pre-send journal/lock
   contract, exact source/live authority/caps/reserve/revocation, full upper-bound
   reservations, stable request IDs and saved-response reuse. Every live role must
   participate, including explicit role propagation through alert/close callers.
   Unclassified/manual/history paid entry points deny admission without the same
   reviewed authority. Zero automatic retry/redirect; pending/uncertain/failed
   attempts retain exposure and halt admission. Keep the collector/installer hold
   in place through implementation/review. Preserve each job's cadence, game
   selection, quote format and registration. A close's planned later observation
   after a conclusive response is distinct from resending an uncertain request;
   its existing MAX_TRIES2 and 2–20-minute eligibility remain unchanged.
2. **Prospective acquisition adapter.** Inject the same admission contract at the
   existing prepared-loop/http-factory boundary, preserving individual drivers,
   exact allowlists, caches, approvals and ledgers. Bind only future packets.
   Do not edit executed freezes/captured source closures or exhausted authority.
   Integrate the generic historical paid entry points or deny them without the
   reviewed adapter so they cannot bypass accounting. Initial account state comes
   from hub-authenticated month/global accounting: distinguish prior/probe debit,
   uncertain exposure and provider lag without double counting or discarding any
   retained reservation. No live seed/budget is inferred from estimates here.

The account journal is a budget/transport boundary, not a unified purchase runner.
Existing historical per-epoch records remain immutable and separately attributable.
Choose one canonical lock path/order in review; do not create another uncoordinated
lock alongside followup-purchase.lock or unlink/rotate a held inode. Resolve nested
lock ordering and the ownership token for an acquisition holding a lock across its
loop before enabling anything. A shared source module alone does not prove callers
actually reserve; tests must trace every paid send through it.

## Why calendar-only nonoverlap is insufficient

Alerts run four times daily; close wrapper runs900s with RunAtLoad; collectors run
600/900/60s (NBA paid cadence5min). Manual invocation and run duration bypass calendar
assumptions. A quiet-window claim cannot stop an unintegrated sender. Enforced
nonoverlap still requires gates at every paid transport, authenticated/reconciled
account state and uncertainty handling. Denying a registered close window could
lose eligible observations. No feasible preserving-schedules alternative has been
proved from this source-only inventory; recommend the bridge.

## Required proof and hub inputs

Targeted caller tests for all roles and direct/manual bypasses; simultaneous
alert/close/collector/acquisition at cap/reserve; actual crash and disk failure;
revocation while waiting for the lock; cached/restarted identity without resend;
provider lag/untracked usage; pending/failed global halt; source/month rollover
cannot reset debit; close conclusive follow-up versus uncertain attempt. Reuse
unchanged trusted evidence, bind every affected caller/default/dependency in CI.

Hub must provide actual current writer/runtime inventory and authenticated baseline,
exact finite caps/expiry/source approval, and choose the staged scope. None of those
is supplied or manufactured here. Runtime adoption remains hub-owned after the
independent review; the hold is removed only with reviewed real enforcement plus
caller/crash/concurrency proof. Metadata status producer remains secondary.

Publication limitation: shell GitHub fetch/push cannot resolve GitHub under current
network restrictions. GitHub connector reads work, but the attempted scope comment
was rejected because approval policy is never. This local committed proposal is the
reviewable result; it has not been posted or independently accepted.
