# F2 second continuation: exact canonical missing recovery

Local worker uses captured paid caches and non-secret ledgers read-only. Hub alone authenticates approvals, transitions and runs purchases. This sibling version leaves original v4, pilot, execution-v1 and recovery-v1 frozen bytes unchanged. Related PRs116/119/120; issues7/10. No outcomes, sealed2026, credentials, orders, grading, registration mutation or worker paid calls.

## Exact scope

Original1773 request slots /1774 opportunities /10 books /2 F2 markets stay unchanged. Source observations and ID/time binding remain original. At the halt:581 valid (417 original +48 pilot +116 continuation), initial missing1 +provider-only missing4 +canonical pending1 =6 missing after the exact offline transition, and1186 NEVER-sent rows. Only those1186 unchanged IDs may be sent, with23720 maximum new reservations. Cumulative97956 before continuation becomes at most121676 before any further external debit. Every missing keeps20 reserved /0 billed and its place in entry/close/book/market denominators. No missing record claims a game was played, settled, cancelled, never offered, or profitable.

Pending canonical2023_19_LA_DET/T24: requestcbacd1c8b9929a1386777465ca18148ea7feb7a88e6917542cca3a9ff4eba719, responseff1c10256fc992326336b0c9ecd3d75a555389d96e3fd4a46a58bf5159213e03, exact404/EVENT_NOT_FOUND, last0 /used96149 /remaining4903851, durable send_started,20 reservation. EVIDENCE.json records source observation before the request and the15-minute schedule/provider discrepancy; actual play is unverified.

## Offline transition, separately authenticated

`prepare.py` is read-only: validates immutable405 packet and exact stopped ledgerdbf689..., all120 terminal receipts/caches, first partialcc2f17..., first stopped backupfb9edf..., original offline approval fields at commit20bcaa35, pilot gate, and source selection. It freezes a deterministic new missing certificate and unchanged remainder. No paid-v1 modules are imported/executed by the ancestry verifier. Historical continuation authorization is pinned by SHA9adb99..., central registration, original run manifest, exact stopped bytes and receipt chain. Exhausted paid comment5958391692 is historical evidence and never new send authority.

Hub invokes `missing.py --bundle <v4> --certificate <packet/missing-certificate.json> --approval <new-offline-approval.json> --confirm-offline` from the reviewed clean CURRENT121 implementation commit. Approval must contain exactly:

```
APPROVED offline missing: proposal <proposal_sha256>, ledger <prior_ledger_sha256>, request <request_id>, response <response_sha256>, commit <current121_sha>
```

The transition holds global/per-root locks, durably preserves exact second stopped bytes BEFORE approval/receipt/ledger writes, changes only the one pending row and terminal status/stop markers, and retains all accounts/reservations/epoch/seed/caps/old missing categories. Pre-commit interrupted transitions permit only an explicit identical offline retry; committed transition never reapplies. No key or transport path exists in this CLI.

## Paid second continuation, separately authenticated

Hub invokes `epoch.py --packet <F2-second-continuation> --root <frozen_root> --bundle <v4> --authorization <new-paid-authorization.json> --key-file <hub-key-file> --confirm` only after exact current-head agreements and new PR99 approval. Alongside normal exact CSV/request-set/budget/current-commit approval and account-ceiling line, require:

```
APPROVED exact missing policy: sha256 <exact_missing_policy_sha256>, max-missing 1186, root <frozen_root>
```

Policy JSON freezes only1186 IDs, regardless of original canonical/provider-only classification. Exact endpoint/event/date/markets/books/cache identity,404 +parsed EVENT_NOT_FOUND +integer last0 +complete counters are required. Full20 reservation remains; durable cached error/receipt/reason/policy hash precede terminal ledger commit. Ledger counter/lag/external-use/reserve-floor/cap guards still apply. Other errors halt. No retry, redirect, reselection, replacement or resend. New root cannot escape any unrelated global pending/stop or lost registration/evidence. All ancestor proof/reuse/approval checks run before key loading, including all581 valid +6 missing rows.

## Stable data-only downstream API

`ancestry.verify_first(bundle, authenticate=True)` fixes original offline commit20bcaa35.

`ancestry.verify_second(cert, bundle, *, expected_commit, authenticate=True)` requires an independently frozen ORIGINAL121 transition implementation commit. Downstream callers must pin that historical commit in their own reviewed packet/code, not use their current checkout or copy an arbitrary approval field. It validates the precise second partial/certificate/stopped backup/historical registration/run manifest and authenticates the offline comment at that original commit. `ancestry.reuse(seed, rows, bundle)` validates disjoint ancestor receipts/caches and every missing category; `seed_state` permits only the exact two specific partial roots in source→pilot→first→second order and no debit reduction.

PR119 full-F2 coverage/union remains dependent on ACTUAL final completed recovery-v2 evidence and all1774 opportunities. Its prospective F3a must freeze its own exact570 original event-odds IDs, distinct missing policy/approval and60 reserved per six-market request (34200 maximum inside the purchase cap); missing coverage gates F3b. Older featured endpoint retains its existing snapshot validator. No new profitability gate for independent older core data.

## Report for the hub

Implementation is reviewable in PR121. Fake-key, offline, temporary-runtime tests cover exact real preview, transitions, approvals, both full1186 integrations, missing/identity/billing/counter/floor/keyecho failures, durable crash boundaries, no resend, lost evidence, original historical commit and unrelated global stops. Real runtime has not been mutated. Final current-head review and separate hub offline/paid approvals remain required.

NOT READY pending final test results and current-head audit.
