# Football archive v4: repaired for PR #99 review

LOCAL-BECAUSE: raw-data: validation replays 24 sanitized probe responses available only on this Mac. All preparation and tests use an isolated checkout and its own Python environment.

- Root: `70214abb0f3527aed2f74005a164588fb65b62238116d43b0892f612e5a45ea1`.
- Exact CSV SHA256: `81d557cffc1a57c6fb7547cc3be319158745c985bbc746513bda039a7c972910`.
- Request-set SHA256: `63d4ab26f80d54d9316de8b9b5457adc6ca4609e4be4cb01da63e98e9dceea9b`.
- Recent 2023–25: **82,830 credits**, 2,761 paid requests plus 12 reused responses.
- Older 2020–22: **68,010 credits**, separately gated and unsupported by this executor.
- Research purchases with the probe: **152,527 credits**. Other account usage remains an additional conservative debit against cumulative ceilings.

## Six review repairs

1. Account-only recovery validates structure and preserved debits first, adopts the approved replacement baseline, then checks the reserve floor. The stopped ledger hash must match.
2. State is fixed outside all checkouts at `~/Library/Application Support/ValueFinder/football-acquisition-state/<root>`. A separate registration marker detects deleted runtime folders. The runner refuses the live checkout. Every approved reconciliation requires a current billing period and hub-supplied `max_baseline_used`; a fresh checkout cannot silently adopt a spent balance.
3. Provider and scheduled kickoff checks remain mandatory. Final first-play evidence can only exclude or certify an already eligible quote, never admit a quote using hindsight. Eligibility and protocol are bound under the same root.
4. Hub approval binds the exact CSV, request set, budget, full execution commit and approval-comment URL/body. Live execution authenticates the GitHub comment before reading a key. Owner evidence must be recorded after hub approval.
5. Exact-ledger, exact-request hub approval can accept a cached 404, an excessively lagged snapshot, or an evidenced uncached 5xx as missing. The reservation remains; no automatic resend occurs. Unreadable bills, overcharges and timeouts remain unresolved. Missing requests stay in coverage denominators and the reader manifest. A fresh approved account baseline is still required after resolution.
6. Runtime ledgers/receipts are ignored. Both v3 and v4 input-provenance files use logical local references. The historical v3 export is explicitly redacted and has its own certificate; the original reviewed certificate is preserved. The original local v3 was not changed.

Request rows, all 665 three-market MOS slots and all 28 new alternate closes are unchanged. The F1 comparison in the earlier PR report therefore still applies. A30 remains 5,000; shared usage and counter lag each have a 100-credit bound.

## Verification

**146 offline tests passed against the final sealed bundle**, plus its offline executor preflight and full validator with all reused-cache hashes. The client remains unchanged. The isolated interpreter is `.venv-football-archive/bin/python` in this review checkout: Python 3.12.11, with the frozen runtime versions. No live environment was modified.

The rehearsal uses temporary one-request execution fixtures plus full static manifest validation; it is not a 2,761-call throughput test. No new API calls, real key reads, outcome joins or sealed-season reads occurred. Raw parquet fixtures remain local and ignored. Restore them with `restore_local_reuse.py --from-bundle /path/to/verified/local/bundle`, which checks exact hashes without a purchase.

Offline preflight: run the isolated interpreter with `-B acquisition/football-archive-v4/executor.py --root 70214abb0f3527aed2f74005a164588fb65b62238116d43b0892f612e5a45ea1` from this directory. Run the frozen `test_v4.py` with pytest plugin autoload and cache disabled.

## Approval artifacts and run window

[authorization.draft.json](authorization.draft.json) and [account-reconciliation.draft.json](account-reconciliation.draft.json) authorize nothing. The execution commit and hub baseline ceiling remain unset intentionally. After review, the authenticated hub comment must contain:

`APPROVED paid run: list 81d557cffc1a57c6fb7547cc3be319158745c985bbc746513bda039a7c972910, request-set 63d4ab26f80d54d9316de8b9b5457adc6ca4609e4be4cb01da63e98e9dceea9b, budget 82830 credits, commit <full current SHA>`

A missing-response approval additionally binds the root, request, stopped ledger, commit and reason; see the frozen BILLING-REPAIR.md and executor for the exact format. Do not edit a frozen bundle to add approvals: runtime artifacts are separate.

Proposed window, subject to hub resumption and approval: **Friday October 2, 15:00–15:30 UTC (08:00–08:30 PDT)**. No alert job is scheduled inside that window. Expected shared usage is zero alerts plus one credit per due close-capture slot; the hub must confirm whether any kickoff slot is due. The no-kickoff condition has not been checked against sealed 2026 data here. An extension across 18:30 UTC adds approximately 2–4 alert credits. The 30-minute window is a proposal, not a throughput guarantee or scheduled run. No jobs were paused.

## Reader integration and stop gate

[PR #102](https://github.com/maxzipperman/value-finder/pull/102) owns the registered price-engine integration. Its default runtime path must match the fixed global root above, or its explicit `--handoff-runtime` must point there. Its tests should cover the updated adapter's accepted-missing entries, which have no response path. `as_calls` retains those requests and `ReadOnlyCache` returns no data without fetching.

Before acquisition, the hub checks overlap, backup readiness and the registered reader, approves the exact current commit/list/budget and baseline ceiling; the owner then completes authorization evidence. The hub was paused at the latest review, so this refreeze awaits review when it resumes. No merge or spending approval is implied by this repair.

**READY FOR THE HUB:** review this repaired root and current PR head. Stop after 2023–25 for the outcome-blind coverage report. Older seasons and strategy grading remain gated.

First-provider-observation repair (October 1): both explicit and capture baselines enforce the approved account ceiling against the first provider check of every new or recovered epoch, before a paid reservation. Verified epochs persist across intact-ledger resumption. Total-store deletion and first-observation-above-ceiling regressions cover both modes; explicit recovery is also covered. Hub review and renewed current-commit agreements are required before acquisition.

## Owner-requested 30 RPS cap (October 1)

The owner requested 30 RPS before the first paid call. Only `rate_per_sec` changes from 4 to 30 in the source and frozen executor. Requests remain sequential, no automatic retries remain enabled, and all request bytes, prices, credit ceilings and eligibility rules are unchanged. The provider documents a 30 requests/second paid-plan limit: https://the-odds-api.com/guide/rate-limit.html. This is a pacing ceiling, not a throughput promise; provider latency and durable writes can keep throughput lower, and any rate-limit response still stops the run.

Previous root: `4468a94c2b415cd5c53dd58163831f61d379ee44ec1b560f5a9b84be9c7f010d`. New root: `70214abb0f3527aed2f74005a164588fb65b62238116d43b0892f612e5a45ea1`. Only `executor.py` changes within the frozen file map. Prior PR 99 approval at `fc096230d337fb03d4136d6b41c422b91289dfa0` does not authorize this changed executor. The hub must renew exact-commit approval in PR 99 (the executor validates that PR URL), and confirm baseline ceiling and run window. No paid requests or real credential reads occurred during this amendment. Reader Amendment 2 remains draft; its acquisition-root reference must be reconciled before reader registration, not silently treated as approved for this new root.
