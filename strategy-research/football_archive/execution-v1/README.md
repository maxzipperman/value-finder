# F2 remainder / F3a execution extension

Mac-only implementation worker: requires exact paid historical cache keys and cumulative local ledgers. No worker credential reads, purchases, game-result joins, grading or sealed reads. Completed v4 and F2 pilot bytes are unchanged. This sibling directory preserves the historical code/packet freezes. Stacked on [PR #108](https://github.com/maxzipperman/value-finder/pull/108); follows [audit #104](https://github.com/maxzipperman/value-finder/pull/104), issues [#7](https://github.com/maxzipperman/value-finder/issues/7) and [#10](https://github.com/maxzipperman/value-finder/issues/10).

## Exact stage packets

| Stage | Candidate requests | Reused | New calls | New reserved credits | Execution status |
|---|---:|---:|---:|---:|---|
| F2, 2023–25 | 1,773 | 48 | 1,725 | 34,500 | Frozen for exact-head review |
| F3a, six markets, 2025 | 570 | 0 | 570 | 34,200 | Candidate only; reprepare after F2 completes |

F2 preserves all 1,774 opportunities: 64 provider-only and one unbound. Its full CSV includes all 48 pilot rows with zero new cost. `opportunities.json` retains every source listing binding, missing/ambiguous status and as-of sweep evidence; no played-game selection. T−24h/T−10min are scheduled acquisition restrictions, not independently verified actual play or independent schedules known at entry time.

F2 root: `059fc135b00bbbc36db208a8bb622d7444a43d42bb2607675d30671ad455f4e4`.
F2 CSV SHA256: `1ca4e3ccfafe89c33d8ea1e0cc395dd1afb2442a9174bdc5af1b0c799f561c89`.
F2 request-set SHA256: `2f92159e384e612ccca2101c5862f6ee067ddfcb7f42860608ac8980c9946519`.

F3a candidate root: `ba90220ec439e023f9f58257737aaf7b21264e8fadf38ee551ef40a11d50b011` (cannot execute).
F3a CSV SHA256: `a0f915c2af66f8d370faf3b21c84a404ce43b3ac55b06720a3aa0f4724c6029b`.
F3a candidate request-set SHA256: `7850428dd798383946ff091893744d97762f5c9ca0e681bccf4bded7e16cf267`.
After F2, `prepare.py --stage F3a` pins its completed ledger and reconciles fresh exact-key overlap. Commit the resulting new F3a freeze and obtain new exact-head review/approval; candidate approval cannot substitute. Any list/cache change changes its root and exact approval.

## Seed and execution interface

`prepare.py --stage F2` is offline. It regenerates the exact inventory from immutable v4, reads only the planned historical keys, recomputes the pinned pilot coverage and binds the immutable completed predecessor ledger. It refuses to regenerate a root with an existing global runtime. F3a uses the same interface but requires completed F2. `--stage F3a --candidate` builds an explicitly non-executable inventory.

`epoch.py --packet <packet> --root <root> --bundle <v4>` verifies frozen packet bytes offline by default. `--confirm --authorization <file> --key-file <file>` is **hub only**, after the following review gates. Execute from an isolated checkout with the committed packet. Copy ignored v4 probe reuse files byte-for-byte from the hub if needed; do not regenerate v4 or pilot. Own runtime: Python 3.12.11 and the exact eight distributions in v4 `runtime-lock.json` (this worker has its own environment).

The seed carries root, fixed global ledger path/hash, probe=1,687, cumulative debit without probe. Fixed runtime remains `~/Library/Application Support/ValueFinder/football-acquisition-state/<root>`; common global lock is `followup-purchase.lock`; central v4 registration/INITIALIZED markers, per-root process lock, durable reservation/send-start/header/receipt/cache chain are retained. Every ancestor is checked for cycles, duplicate paid identity, unresolved attempts and debit reduction. F3a also verifies completed F2's exact allowlist, reuse, predecessor pin, reservation amounts, caches and receipts. No transport for older F1, NBA, heat or other stages is enabled.

F2 starts from **87,176** conservative cumulative credits, including probe and external/carry debits. In the full synthetic integration, F2 ends at 121,676 and F3a at 155,876. These are conservative reservation totals under no additional external use, not claims of live account balances or future billing. Every stage adopts a fresh free account check and preserves the larger prior/fresh account debit. Explicit debit overrides and automatic account-only recovery are disabled. The original reserve floor, 250,000 first-tranche cap, 400,000 day-one cap and 4,440,000 broader cap remain unchanged.

The trusted extension reads and hashes the complete pilot packet and all sibling Python files, recomputes the pinned pilot root, and rejects changed/missing/unexpected/symlink/nonregular files before importing any pilot code. Pilot modules execute the captured verified bytes, so a path replacement after verification cannot execute new bytes. Sentinel regressions cover changed epoch, coverage and plan modules through the actual pilot_gate entry point. All offline source/pilot/seed/scope/approval/cache/runtime/restart guards precede key loading. Transport remains 4 RPS, zero client and adapter retries, no redirects; each paid attempt is durably reserved and marked sent before GET. The existing billing, cumulative external-use, lag, reset, overcharge and floor stops remain active.

## Hub approval and remaining gates

1. Auditor reviews this PR's exact current head (plus outstanding PR #108 review). Both assistants agree on the same head before hub merge; only hub merges.
2. Hub verifies fresh predecessor/cache overlap and uses the frozen CSV/request set/root/current commit. A changed file, source, cache, predecessor or commit invalidates prior approval.
3. Hub supplies the exact authenticated comment on PR #99 required by the preserved v4 authorization guard:
   `APPROVED paid run: list <CSV sha256>, request-set <request-set sha256>, budget <exact N> credits, commit <full current sha>`
   plus a separate line `APPROVED account ceiling: max-baseline-used <explicit stage ceiling>, root <frozen root>`.
   Both lines must be present in the authenticated hub comment. Authorization JSON mirrors them and includes approved `account_reconciliation` for the current UTC billing month, `baseline_mode=capture_first_free_check`, reason, owner note and explicit `max_baseline_used`. Choose that ceiling from the hub's current account evidence; do not inherit the pilot's 100,000 ceiling for F3a when used exceeds it.
4. Hub alone executes and reports ledger/receipt/cache/coverage hashes, conservative reservations and actual billing/header deltas, exclusions and all stops. The owner's queue authorization and backup waiver persist; no repeated owner decision is needed within scope. No analysis registration or grading is enabled by acquisition readiness.

## Missing/error and recovery policy

A valid 200 with empty books/markets completes as acquired but retains missing quote coverage. A 404, 403, 429, 5xx, malformed identity/clock, missing billing, overcharge, counter reset, unexpected external use, crash or disk failure stops with reservations and observed headers retained. A cached 404 is **not** treated as zero-cost permission to resend. No stop automatically clears a pending attempt, recovers an account, changes roots, retries, drops an opportunity or relaxes a source guard. Any unresolved global epoch blocks new-root execution.

There is deliberately no offline reconciliation command for this extension. A future pending-response/missing acceptance must be separately reviewed and hash-pinned to the exact ledger, attempt, cached response or explicit unavailable-response evidence, and authenticated hub evidence. It must preserve reserved/observed debit, terminal missing exclusions and ancestor no-repurchase identity, then require a fresh separately approved account reconciliation. Do not use the original v4 recovery CLI on an event stage. Until that reviewed reconciliation exists, preserve the stopped runtime and do not resume or prepare a replacement epoch.

## Reproducible validation

From the repo root, with the worker's own pinned `sharp-markets/.venv` and restored ignored v4 probe reuse bytes:

```sh
PYTHONDONTWRITEBYTECODE=1 sharp-markets/.venv/bin/python -m pytest -q strategy-research/football_archive/execution-v1
PYTHONDONTWRITEBYTECODE=1 sharp-markets/.venv/bin/python -m pytest -q strategy-research/football_archive/acquisition/football-archive-v4/test_v4.py
```

**Observed results:** 80 extension tests passed; 146 immutable v4 tests passed (5.84s). The full synthetic integration bought exactly 1,725 new F2 rows, reused all 48 actual pilot responses, then bought 570 synthetic F3a rows; cumulative reservations were 121,676 and 155,876. Missing F2 receipt blocked both stages before key loading. No real transport occurred.

Tests prohibit sockets, credential files, forward logs, pricing cohort and outcome files; transport uses synthetic keys. Library tests isolate real frozen transport/cache/accounting; stage tests use the actual 48 historical pilot response/receipt hashes and gate, full 1,773-row F2 selection and 570-row F3a list, then fake all new transport. Only git checkout/commit proof is replaced in synthetic runs. They cover failed/mutated coverage, source/pilot corruption, scope/book/market/season errors, every-ancestor duplicate/cycle/debit reduction, crashes and restart, missing/changed evidence, 429/403/404, billing/overcharge/reset/external use, exact approvals/caps, authenticated ceiling tampering, debit overrides and global pending/stopped escape.

## Report for the hub

Exact F2 packet and F3a candidate inventory are prepared; the unchanged v4/pilot freezes and actual pilot gate are verified. No worker purchases, credentials, outcomes, holdout, registration changes or merges. F2 is reviewable independently of post-F2 F3a refreeze. Remaining gates are auditor/current-head agreement, hub's fresh reconciliation, exact paid approval with explicit authenticated stage account ceiling, and hub-only execution.

READY FOR THE HUB
