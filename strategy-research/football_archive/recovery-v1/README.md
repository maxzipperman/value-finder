# F2 404: offline reconciliation and exact continuation

Mac-only implementation worker: validates exact captured non-secret ledger/cache/receipts. No worker credentials, API purchases, outcomes, registration, grading, sealed data, live jobs or global runtime mutation. Original v4, pilot, all execution-v1 sibling Python and the paid F2 packet are unchanged. This separate versioned adapter is related to [PR #113](https://github.com/maxzipperman/value-finder/pull/113), paused report/F3a [#115](https://github.com/maxzipperman/value-finder/pull/115), older adapter [#114](https://github.com/maxzipperman/value-finder/pull/114), issues #7/#10.

## Exact stopped attempt and offline transition

Original root: `059fc135b00bbbc36db208a8bb622d7444a43d42bb2607675d30671ad455f4e4`.
Stopped ledger SHA256: `fb9edfb65460c5f4fe84539ac2405b8e49d813dd5f9892bd32692bfbc86a4163`.
Pending request: `850c02077a7ef01010d277ad63cff3a88847548a9a1a70424fa8252ccf632c9a`.
Cached 404 SHA256: `25923e8f5db247b52ed7b7ca2bdac5f938cbb0d7833e7aad90bdd0bd2dc917b6`.
Proposal SHA256: `8e8bb95f87b7b51e04eca912e1a30db44578f2746d33b5ccc3ad796a435aeb30`.
Expected reconciled ledger SHA256: `cc2f17d3289ac1dbebac6bcf5d828f4384f2ea4c9d88829c2d8510a014a57313`.

The exact original request/cache identity, 404 `EVENT_NOT_FOUND`, durable send_started, observed last=0 / used=93,829 / remaining=4,906,171, 20 reservation and all 417 completed receipt/cache hashes are checked. Preview performs no mutation. The hub explicitly approves this terminal missing transition, then runs it offline. It first durably preserves the exact original stopped ledger bytes under `recovery/original-ledger-<stopped-sha>.json`, saves authenticated approval evidence, writes the missing receipt, and finally atomically changes only the pending attempt's completion fields plus pending/stopped/status/missing_resolution. All existing attempts, accounts, epoch, prior debits, reuse records and slice caps remain unchanged. Status becomes `event_epoch_partial_reconciled`; it is not full acquisition completion.

The one missing attempt retains 20 reserved / 0 billed, its exact body/header/cache/receipt hashes and opportunity. Every transition write has a crash checkpoint. A stopped transition cannot send; explicit repeat after a pre-commit interruption rechecks the exact stopped ledger and matching existing artifacts. A committed transition refuses safely rather than reapplies. Conflicting artifacts or partial temporary writes fail closed; no automatic cleanup, budget reset or missing response resend.

The trusted adapter captures and verifies the complete original paid execution-v1 F2 file map/root before compiling any original module. Original source and pilot integrity checks remain; the historical Python bytes never change.

## Frozen continuation

Root: `4053703d09fdcedb6ce1608c8a5a0d09d3e702a6426891463163224e10af792e`.
CSV SHA256: `9c31daa0a31c2038a4b3897a700400efbba1d66ac867033f9cf6d4a68435ea66`.
Request-set SHA256: `388c75d96f33ed7d6ca44e8131bccc49492ee0480ed62e2e0ede3f044de6c2b4`.
Full denominator: 1,774 opportunities / 1,773 request slots / 10 books / two alternate markets.
Paid allowlist: **1,307 unsent calls / 26,140 credits**.
Reuse: **417 completed responses + all 48 pilot responses**, plus the one distinct accepted-missing row.
Conservative predecessor: **95,536 credits** (87,176 prior carry + 8,360 reservations, including the 20 missing reservation). Maximum continuation reservation total before additional external usage: **121,676**. Header bills may be lower; no reservation is released.

The packet retains all original rows and opportunity/listing evidence; cache reconciliation marks the 417 completed, 48 pilot and one missing rows zero new cost. A new root cannot start until the exact predicted terminal-partial ledger exists, the original stopped backup and authenticated offline approval are verified, all ancestors/caches/receipts are intact, and the hub separately authenticates the new exact list/root/budget/current commit and account ceiling. The continuation keeps global/per-root locks, central registration/INITIALIZED markers, durable reservation/send-start/headers/cache/receipt chain, 4 RPS, zero client/adapter retries, no redirects, all original reserve/lag/external-use/reset/cumulative caps and every-ancestor duplicate prohibition. No non-F2 stage is enabled.

## Proposed prospective provider-only 404 policy

This policy is an explicit reviewed proposal, **not approval**. Both reviewer agreement and the hub's authenticated paid comment must include it before any send. [Auditor direction](https://github.com/maxzipperman/value-finder/pull/116#issuecomment-5958107687) accepts this narrow design in principle.

Policy SHA256: `d0450fdf88f0d557e6e4abd00ae5421bf3f0b4e5865398c480989482752e1e8a`.
The policy freezes exactly **63 unsent request IDs** derived from the unchanged original provider-only opportunities and every row's linked opportunities. All linked opportunities must be provider-only and planned. The already-pending 64th request is excluded and still requires the separate exact offline transition. Maximum future terminal-missing requests: 63; maximum associated reservations: **1,260**, within the 26,140 total cap.

Only HTTP 404 with JSON error_code `EVENT_NOT_FOUND`, exact request/cache identity and numeric last=0/used/remaining can become terminal missing during this continuation. The reviewed Ledger verifies current cumulative counters, lag, external usage and floor before writing a durable missing receipt and clearing that attempt's pending flag. Its full 20 reservation, 0 bill, cached response and policy/receipt hashes remain. Canonical or mixed-linked rows, wrong error codes, malformed bodies, missing/nonzero billing, 403/429/5xx, identity mismatch, echo, overcharge, counter resets, lag, external-use overruns or receipt loss halt and retain reservations. No retry or resend occurs. All opportunity/book/market denominators remain, and no quote, actual-play certification, profit or strategy eligibility is inferred from a missing response.

## Hub-only commands and approvals

Use this PR's exact final committed branch head and the pinned Python 3.12.11 / eight-distribution v4 runtime. Do not regenerate registered packets. The worker only ran offline preview/tests.

1. Auditor and hub review the exact current head. A new commit voids prior agreements. Only the hub merges and executes.
2. Record an authenticated comment on PR #99:
   `APPROVED offline missing: proposal <proposal-sha>, ledger <stopped-ledger-sha>, request <pending-id>, response <404-sha>, commit <full recovery head>`
   Put the exact comment URL/body and mirrored status/proposal/ledger/request/response/execution_commit into an approval JSON. The comment author and body are verified through GitHub; original code/packet and current clean committed recovery files are checked.
3. Inspect the default offline preview, then hub alone runs the explicit transition:

```sh
PYTHONDONTWRITEBYTECODE=1 sharp-markets/.venv/bin/python strategy-research/football_archive/recovery-v1/missing.py --bundle strategy-research/football_archive/acquisition/football-archive-v4 --certificate strategy-research/football_archive/recovery-v1/F2-continuation/missing-certificate.json
# Hub only, after exact offline approval/current-head review:
PYTHONDONTWRITEBYTECODE=1 sharp-markets/.venv/bin/python strategy-research/football_archive/recovery-v1/missing.py --bundle strategy-research/football_archive/acquisition/football-archive-v4 --certificate strategy-research/football_archive/recovery-v1/F2-continuation/missing-certificate.json --approval /absolute/path/to/offline-approval.json --confirm-offline
```

4. Verify the post-transition ledger/receipt/backup hashes. Post a separate paid approval on PR #99 binding exact CSV, request set, budget 26,140, current commit and the new root. Include these separate authenticated lines:
   `APPROVED paid run: list <CSV-sha>, request-set <set-sha>, budget 26140 credits, commit <full recovery head>`
   `APPROVED account ceiling: max-baseline-used <explicit stage ceiling>, root <continuation root>`
   `APPROVED provider-only missing policy: sha256 <policy-sha>, max-missing 63, root <continuation root>`
   Paid authorization JSON uses the unchanged v4 schema with this root/budget/commit; current-month approved account_reconciliation has capture_first_free_check and an explicit fresh max_baseline_used, reason and owner note. No inherited baseline ceiling, debit override or automatic account recovery.
5. Hub alone uses recovery-v1/epoch.py with the packet/root/bundle, authorization/key-file and --confirm. Offline transition approval must match the same current implementation commit; stage_guard verifies its authenticated evidence and original backup before key loading. Reuse and the missing row require exact receipts/caches. Report bills, conservative reservations, header deltas, exclusions and every stop.

Subsequent F3a/older adapters must pin this continuation's completed root/ledger, carry both missing categories and every ancestor debit, and be independently reviewed; original execution-v1/prepare.py cannot pretend its now-partial F2 root completed. Optional coverage/F3a work is paused on branch acquisition/f3a-completed-f2 (34 standalone report tests passed there).

## Reproducible offline tests

```sh
PYTHONDONTWRITEBYTECODE=1 sharp-markets/.venv/bin/python -m pytest -q strategy-research/football_archive/recovery-v1
```

**Observed result:** 37 tests passed in 163.15s. Both full 1,307-call integrations preserved cumulative reservations of 121,676; the all-404 integration retained 63 additional missing reservations of 20 each with zero bills and durable policy receipts. The original actual stopped ledger SHA remained fb9edfb65460c5f4fe84539ac2405b8e49d813dd5f9892bd32692bfbc86a4163.

Tests use actual frozen selection and read-only pinned historical evidence, relocate non-secret ledgers/receipts to temporary runtimes, and use synthetic keys/fake new transport. They prohibit sockets, credentials, outcomes/holdout, and all writes to the actual global runtime. Git checkout proof and runtime paths are replaced only for synthetic temporary runs. Full continuation sends exactly the 1,307 new identities; no ancestor identity is sent. A second integration returns all 63 permitted zero-billed 404s, proving 20 reservations/0 bills/durable receipts and unchanged cumulative reservation total. Fault tests cover offline approval tampering, every transition write, missing/changed approval/backup/post-ledger, rejection before acceptance/key, all-linked canonical/mixed disqualification, wrong status/error/identity/billing/counters, canonical404/403/429, timeout, lag, resets, external use, overcharge and no-resend restarts.

## Report for the hub

The exact stopped evidence, deterministic missing certificate, complete ancestor reuse and 1,307-call/26,140-credit continuation are prepared and tested. Prospective policy explicitly freezes the 63 unsent provider-only IDs and 1,260-reservation bound. Authenticated offline transition evidence and stopped-byte backup are required in stage_guard before key loading. No runtime mutation, credentials, paid calls, outcomes, grading, sealed access or merge by worker. Both current-head agreements and two explicit hub approval steps remain.

READY FOR THE HUB
