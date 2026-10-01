# V4 billing repair

The v3 review found that equality against the old probe balance and per-call counter deltas made routine shared-key usage, resets and stale headers fail. V4 changes only this execution concern and makes coverage show both purposes for shared alternate-close slots.

An approved reconciliation file records mode, reason, owner note, and optional explicit used/remaining. Capture mode adopts the first free check and records its actual numeric baseline in the durable ledger and manifest. The file hash, baseline, runtime versions and interpreter path are recorded. A draft file authorizes nothing.

During an epoch, compare highest used and lowest remaining with cumulative own bills. Reserve peak positive external discrepancy once; cap it at 100. Bounded reporting lag up to 100 is tolerated and recorded; never infer spending capacity from a stale high balance. Per-call unreadable/over-upper-bound billing still halts. Initial reconciliation cannot lower research attempt/probe debit.

Stopped account-only runs can resume through a new approved reconciliation when no paid request is pending and the approval pins the stopped ledger hash. Pending requests stay reserved and cannot be resent. `--reconcile-only` accepts only an existing exact hash-pinned valid cached response, writes receipts/history and preserves the reservation; a separate approved account-only baseline is then required before any send. A missing response or unresolved overcharge remains blocked for investigation.

A30 from the complete probe is 5,000 under the repo's formula; wrapper limits remain stricter at 100. There is no guarantee about provider billing or unrelated key activity. The runner never changes launchd jobs or reads sealed strategy signals.
