# Separate older lag successor

Execution-risk proposal for #38, following #120. LOCAL-BECAUSE: acceptance needs
existing local cached acquisition evidence. The worker prepares/reviews only;
the hub owns actual offline mutation and paid execution.

`recovery.py` is self-contained. It captures the entire original older dependency
map before compiling its helpers, then the complete v4 map before compiling its
accounting/client helpers. Its closed loader resolves local imports from captured
bytes, including vendor relative imports, and rejects undeclared external roots.
The existing byte-pinned F2 gate retains its reviewed nested ancestry verification.
This explicitly reviewed legacy closure is separate from the generic process
helper's static freeze validator. No historical code/freeze is migrated.

## Local evidence first

Supply a **local** pins JSON with `stopped_ledger_sha256`, `request_id` and
`response_sha256`. Preserve the original external authorization locally. Operational
pins, detailed certificates, cached records, receipts and account counters are
not source-control artifacts. The certificate binds code and semantic protocol,
old packet/list/source, the full completed history, parent proof, actual billing,
exact pending response and deterministic resulting ledger. A preview never clears
the pending attempt or creates a paid packet.

Commands, from the repository root, with the isolated frozen interpreter:

```
python -B strategy-research/football_archive/older-recovery-v1/recovery.py preview --coverage <existing-coverage> --pins <local-pins> --original-authorization <archived-original-authorization> --certificate <local-certificate>
```

Only after independent review and fresh authenticated offline authority may the
hub call `install` with those inputs plus `--authorization <new-offline-approval>
--confirm-offline`. Its public approval line is privacy-preserving:

```
APPROVED offline snapshot lag: proposal <local-proposal-sha256>, root <old-root>, commit <reviewed-head>
```

The local approval also binds the exact stopped hash, request ID and response hash,
with owner evidence and exact live comment body/URL. Under global/local locks,
the installer rechecks every input, durably archives stopped bytes and authority,
writes the exact missing receipt, and writes the resulting ledger last. Interrupted
installation preserves the stopped ledger until that final atomic step. It never
loads a key or makes a provider request. Installed code/protocol must thereafter
remain unchanged; historical offline approval stays tied to its transition commit.

## Actual parent only

`prepare --packet <new-output> --coverage <existing-coverage>` refuses before output
creation unless the actual global ledger exactly matches the independently
approved certificate, archived stopped state and missing receipt. It derives only
the 1,786 original never-sent paid rows, in original order, cap 53,580; all 2,279
original requests remain in the denominator through the immutable parent/reuse
partition. It never regenerates timestamps, books, markets or IDs. Freeze binds
code/protocol, finite lag policy, exact CSV/set, current exact-key cache inventory,
actual partial parent and old/v4 content roots. Supporting tests/docs have separate
test provenance. No hypothetical packet is committed by this proposal.

`verify --packet <packet> --root <root> --coverage <existing-coverage>` is read-only.
Only the hub's `run ... --confirm-paid --authorization <new-approval> --key-file
<local-key>` can send. Its active PR #99 authority must contain exact lines for
paid CSV/set/cap/current commit, content root/stage, account ceiling, complete
account-reconciliation digest and finite lag-policy digest/maximum. See
`paid_authority` for exact syntax. Old paid authority is never new permission;
HALTED/EXHAUSTED/REVOKED bodies fail. Live authority is checked before every send.

Clean resumptions verify all retained receipts/responses; pending/stopped states
remain blocked and cannot be auto-repaired. A completed successor cannot execute
again. Positive-billed lag is allowed only by the finite policy, keeps its full
reservation and actual bill, and is always missing, never an eligible quote.
Malformed clocks, bodies, neighbors, identities, unreadable billing and overcharges
halt. Existing shared-use, counter-lag, reserve-floor and cumulative rules apply.
Interruption after a missing receipt still leaves the paid attempt pending.

The final successor has `older_epoch_complete`, preserving the old certified
partial in `predecessor_seed`. N0 must explicitly validate this two-epoch older
chain and pin the **actual successor root/final ledger** after completion. Current
N0 ancestry deliberately does not generic-accept this partial; its adaptation and
paid packet remain a separate review. No outcomes or registration are enabled.

## Targeted evidence

Run the new synthetic delta suite with `verification.json` through the unchanged
process evidence runner. It declares complete captured v4 Python inputs and the
protocol/manifest/lock used by fixtures; ignored raw reuse files are not test inputs.
Tests deny network, actual runtime and credential reads. Existing old/union/F2/v4
suite evidence is reused for unchanged dependencies; the new tests exercise the
loader, approval, lag, accounting, actual-parent gate, atomic transition and paid
driver paths. Real preview acceptance is separately local and read-only; it does
not claim a 1,786-call provider throughput test.
