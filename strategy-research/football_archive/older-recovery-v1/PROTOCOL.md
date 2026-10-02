# Older snapshot-lag recovery proposal

LOCAL-BECAUSE: the immutable stopped acquisition ledger, cached response and
completed receipts are on this Mac. This is a separate execution-risk proposal
against the single paid queue (#38), following merged #120. No worker transition,
paid request, key access, outcome join or runtime write is authorized.

## Offline transition

The only supported original packet is the executed older packet in #120. A
separately supplied local pin file identifies its exact stopped ledger, pending
request and cached response bytes. Those operational details and raw records
remain local. Source review publishes code and synthetic fixtures, not records or
account balances.

The preview verifies the complete original packet/source map before importing
any historical helper, its registration/initialization/run manifest, all completed
receipt/response hashes, and the exact pending reservation/send identity. It
accepts only a hash-pinned HTTP200 response with the original request identity,
readable billing and an as-returned snapshot more than 600 seconds behind the
requested slot. Missing/unknown/future clocks, malformed neighbors, mismatched
identity or overcharge fail closed. The full reservation and observed bill remain;
the response is terminal missing, never an eligible price.

Preview is read-only. The hub-only transition requires a committed code/proposal
identity and fresh authenticated exact offline approval. Under the existing
global and local locks, recheck all evidence, preserve original stopped bytes,
durably save the approval and missing receipt, and only then atomically install
the exact certified partial ledger. An interrupted write never enables resend.

## Continuation

No paid packet may be prepared from preview's hypothetical post-state. Prepare
only after the hub has actually installed the independently approved transition.
Retain the full original request/opportunity/book/market denominator; old paid
attempts and original reuse are not paid again. Derive the exact never-sent set
from the certified actual parent. Expected remaining scope is 1,786 original
requests, each at most 30 credits, for a 53,580-credit maximum. No identity,
timestamp, book, market, retry allowance or season is regenerated.

A separately hash-bound prospective policy can classify only those finite
never-sent IDs, after a sole durably reserved send, as terminal snapshot-lag
missing: HTTP200, complete original identity, valid historical body/neighbors,
known nonnegative lag greater than 600 seconds and exact readable charge/counter
headers within the original per-call cap. Preserve the full reservation and
observed charge, all denominators and the exact cached evidence. No timing limit
for usable quotes is widened. All other errors, uncertainty, unreadable billing,
future clocks and conflicts stop; there is no automatic retry or pending repair.

The new packet binds content separately from supporting tests/explanations. Its
captured legacy dependency loader is an explicit separately reviewed closure;
the generic prospective process helper does not certify dynamic legacy imports
or positive-billed missing responses. Reusable test evidence uses the process
evidence format. No executed historical freeze is migrated or edited.

Before key access and under the shared lock, verify exact code/list/policy/parent
hashes, all retained receipts, global settlement, exact-key cache overlap and the
full cumulative debit including the once-counted probe. Fresh paid/list/cap,
account-ceiling and lag-policy authority are separate from offline reconciliation
or merge agreement. N0 still requires actual completed older acquisition and its
reviewed full ancestry proof.

## Report for the hub

NOT READY — implementation and targeted adversarial checks are in progress.
Actual transition and continuation packet remain unperformed/unprepared.
