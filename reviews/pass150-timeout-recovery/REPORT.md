# PR150 exact authority-timeout recovery — PR151

Prepared October 3, 2026. READY FOR INDEPENDENT REVIEW; NOT READY FOR PAID EXECUTION until the hub steps below. LOCAL-BECAUSE: authenticating the Mac's stopped ledger and actual cached receipts. No provider calls, credentials, outcomes, sealed2026, runtime/authority writes, or paid orchestration invocation by worker.

## Problem and resulting behavior

The live GitHub paid-approval lookup timed out between reservation and provider transport. The original c75 epoch stays halted, pending and permanently non-resumable. A separate exact certificate admits that epoch as historical evidence for a new strict successor, without changing any ledger bytes or inventing an HTTP response/receipt. All12 attempted IDs remain excluded. The11 completed requests contribute real receipt/raw claims; the unsent pending request stays explicitly unavailable in each affected game mapping and completion reporting. No original selected game is dropped. Completion of the new1290 purchases does not certify full original coverage or authorize grading.

## Exact identities

| Item | SHA256 or value |
|---|---|
| Stopped root | `c75ef924f5d44c62176de915f47744515f2ca35088f2a82e507a105c0733bacb` |
| Unchanged stopped ledger | `4e9afd9cf99499171b928551dd3fc79873f188b25a30b8b5702f9d2fc4192370` |
| Pending request, permanently excluded | `5dbee52007065c15abd196e69f73a02665da1fb3e98965ff1cfed9bc0c7737ca` |
| Certificate | `7cb292bf53c8f7352522516b3a799b00d0fab1370cd0e75742f9f8e0a25ae880` |
| Successor root | `c7d3ea3d938918735e3ec99f9b56652f67f4f200c93f233385b4d6429fbe1376` |
| List and request-set SHA256 | `d37ddb53e3a645f4c924fd7f99443347cefb84cf69c49165139b59f8f7aa4444` |
| New requests / cap | 1,290 /66,480 credits |
| Stopped billed / reserved | 660 /720, including pending60 |
| Carry / cumulative ceiling | 208,106 /274,686 |

Arithmetic:205,699 prior other usage +1,687 original probe +720 retained reservations =208,106 carry. Carry +66,480 new cap +100 shared margin =274,686. The probe and margin are counted once. Original day400,000/month4,440,000/reserve531,630 limits remain. Fresh account reconciliation and free provider baseline are still mandatory in hub execution.

## What is bound and what changes

- The original reviewed bootstrap SHA48ba33f06b02c1024d49f2758ddd3a5106fcc34ab6c0f09420e71c6407d41213 validates the entire original packet/source/nested union closure. Its original real dependency paths remain declared. The handed-off `/private/tmp/vf-captured-path-fix` checkout is an explicit immutable dependency, not a fabricated module path; keep it intact. This worker's new executable paths are separately declared and frozen. The original executed freezes and code are unchanged.
- Original1302/67200 eligibility/stage acceptance is validated first, then exactly12 known attempted IDs are removed. Every remaining row is unchanged and in original order. New manifest/cells/mappings/finite policy/baseline/cache inventory are root-bound and reconstructed, rather than accepted as assertions.
- The six saved PASS groups, original draw, final coverage decision, held exclusions, timing and settlement gates stay unchanged. Only the exact c75 halted/pending epoch is admissible, and only after exact live hub certificate acceptance and installed metadata. Other pending/stopped roots, unknown/missing roots, changed journals, missing receipts and unsupported carry still reject.
- The pending request receives no synthetic HTTP result, no terminal ledger rewrite and no coverage success. It retains60 reserved and `usable_quote:false`; successor mappings carry explicit certified unavailable IDs/reason. Result reporting carries affected games and the original denominator hash. Analysis readers must retain those unavailable cells before grading; this PR releases no analysis gate.
- Successor926 NFL2023–24 six-market props requests (55,560) precede364 older featured calls (10,920) for NFL2020–22/CFB2020. No CFB2021–22 totals or held college props are released. The finite missing caps are65 snapshot-lag and47 event-not-found responses; quote decimal1 remains raw/non-executable.
- GitHub live GET has at most3 attempts, each10s plus1s/2s backoff. Only enumerated transport/transient failures retry. JSON, live body/login/url mismatch, revoked/inactive approval, missing executable and other errors stop with no cached fallback. Authority is checked before each reservation and again before each HTTP GET. A failure between those steps can still strand a reservation; it is preserved, never resent. Provider transport stays zero-retry, no redirects, one send_started flag per durable reservation,4RPS ceiling.

## Verification and reproducibility

Read-only preparation and assembly authenticated the native11 receipts and per-receipt billed amounts, the original nine-root global lineage (including native live historical GitHub approval checks), full source/nested pins, exact residual reconstruction, real reuse claims and outcome-blind overlap inventory. Original before-ledger bytes are saved verbatim. No metadata installation occurred. The first assembly rejected a concurrent worker source edit before writing its output; the final assembly ran with sources unchanged. Preparation originally failed because native receipt_union returns reservations, not a `billed` aggregate; the correction sums individually authenticated receipt bills to exactly660 while checking720 reservations independently.

Ten focused tests pass, including actual prospective packet mutation/path/inventory rejection; strict selection and denominator preservation; native synthetic parquet receipt bills/tampering; exact retirement/probe-once admission versus unknown/other-pending roots; retained reserve-floor exposure; finite GitHub retry exhaustion; immediate revocation/body/login mismatch; lookup failure before reservation; revocation before send_started; and no paid resend after a transport failure. Initial fixture failures (PR99-only inherited paid approval URL, a missing synthetic billing header and missing synthetic durable path) were repaired in tests only; the failed artifact is retained. No production/source freeze changed for those fixture repairs.

Saved verification: `test-evidence.json`, tested identityf6bfc45565b8ea0a055aa49ed2927716bfe3762fdb1a67508cff80c29d3d9ccc. The report was produced on an uncommitted worker tree; source/test/config/interpreter/package hashes bind its exact tested version. Verify the artifact rather than repeating unchanged broad suites:

```sh
<reviewed-python> -B ops/process/process_guard.py verify-test --config strategy-research/pass150-timeout-recovery-v1/verification.json --saved reviews/pass150-timeout-recovery/test-evidence.json
<reviewed-python> -B strategy-research/pass150-timeout-recovery-v1/bootstrap.py --packet strategy-research/pass150-timeout-recovery-v1/untouched-successor-final --root c7d3ea3d938918735e3ec99f9b56652f67f4f200c93f233385b4d6429fbe1376
```

Review the separately captured aliases and source loading, not only test results. Default bootstrap validates only; worker has not invoked paid orchestration. Actual guarded production orchestration to the registration boundary is a remaining hub/reviewer check after metadata adoption, with per-fresh-executor registration/Ledger/key/provider blockers and runtime write denial as established on PR150. Do not reuse a probe that patches only an outer executor; bootstrap creates fresh instances.

## Hub adoption and next run

1. Independent reviewer reviews exact PR151 current head/root and code/receipt provenance; both reviewer and hub post current-head AGREE before merge. Preparation agreement grants no installation or spending authority.
2. Hub posts live exact offline acceptance and saves its full exact URL/body as external approval metadata. Required line (no paid authority is implied):

```
APPROVED offline pre-send quarantine: certificate 7cb292bf53c8f7352522516b3a799b00d0fab1370cd0e75742f9f8e0a25ae880, ledger 4e9afd9cf99499171b928551dd3fc79873f188b25a30b8b5702f9d2fc4192370, pending 5dbee52007065c15abd196e69f73a02665da1fb3e98965ff1cfed9bc0c7737ca, keep reserve 60, no resend
```

3. Hub alone uses the reviewed `install.py` with `-I -B`, exact bootstrap SHA, root, external approval and `--confirm-hub-install`. It takes the existing shared/acquisition locks, reauthenticates exact ledger/receipts/live approval/source, and creates only `authority-timeout-retirement/certificate.json` plus `approval.json`. Journal/pending/reservation/registration/init remain unchanged. Existing metadata must match exactly; partial/different installation blocks for separate reviewed reconciliation. Worker must not invoke it.
4. Hub/reviewer verifies actual protected orchestration reaches the registration boundary with all native historical/global/cache/certificate proofs and hard registration/Ledger/key/provider blockers. No synthetic substitution for prior approvals or certificate acceptance.
5. Hub obtains fresh account reconciliation, checks no competing executor or overlapping purchase, and issues a new exact root/context/list/set/66,480-budget/executing-commit paid approval on PR99 (inherited v4 authorization intentionally binds that PR). Previous c75 approval remains halted. Hub alone registers/executes the successor, one run at a time. The guarded CLI requires `-I -B`, explicit external authorization/key-file paths and `--confirm-paid`; worker does not invoke it.
6. After acquisition, reconcile actual receipts/billing/reservations and all missing/unavailable denominators. No automatic additional download, new coverage look, outcome inspection or grading release.

READY FOR THE HUB to route independent review. NOT READY for paid execution until steps1–5 above. The next run is only the1290 untouched combined passing-group residual; any later queue or download schedule is a separate hub decision under its registered gates.

Final installer additionally rejects runtime-lock mismatch and validates the complete native historical inventory/carry under both locks before metadata adoption. This changed only the prospective successor root; certificate/list/cap/carry stayed identical. The earlier never-executed prototypea97d6b5f and its verification/preflight records are preserved as superseded evidence; `superseded-prototype/install.py` preserves its sole changed source bytes. Use only `untouched-successor-final`. Final bootstrap SHA35d3f047831b0921e7af11ee39dba2962b267a231acefb2a3fc30f2762c93067.
