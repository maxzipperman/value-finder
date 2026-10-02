# F2 404: offline reconciliation and exact continuation

Urgent Mac-only worker: needs the captured non-secret ledger/404 cache and exact historical cache keys. No credentials, paid calls, outcomes or runtime mutation by the worker. Existing v4, pilot and execution-v1 Python/F2 packet are permanently immutable. Related #113/#115/#114, issues #7/#10.

Concrete transition proposal: hub authenticates an approval binding the stopped ledger SHA `fb9edfb65460c5f4fe84539ac2405b8e49d813dd5f9892bd32692bfbc86a4163`, pending request `850c02077a7ef01010d277ad63cff3a88847548a9a1a70424fa8252ccf632c9a`, exact cached 404 SHA `25923e8f5db247b52ed7b7ca2bdac5f938cbb0d7833e7aad90bdd0bd2dc917b6`, original root and recovery implementation commit. Hub-only offline transition validates reservation/send-start/observed headers, cache identity/status and billing, writes a durable missing receipt, preserves the 20 reservation/0 bill and every prior attempt/reuse/account, marks the predecessor `event_epoch_partial_reconciled` with no pending/stopped, and records an immutable reconciliation certificate. No automatic recovery or send.

A new separately approved frozen continuation pins that terminal partial predecessor plus its explicit transition certificate. All 417 completed responses, all 48 pilot responses and the accepted missing opportunity remain in the full denominator; only the exact 1,307 remaining request identities can spend at most 26,140 credits. New-root registration/global process lock and all previous accounting/floor/external-use/lag/transport guards remain. No duplicate ancestor attempt may ever be sent again. The accepted 404 cannot be treated as a reusable 200. A new fresh authenticated account ceiling and exact continuation budget/list/root/current-commit paid approval precede hub execution.

## Report for the hub

NOT READY: narrow recovery adapter, frozen certificate/continuation packet and adverse-path tests in progress. No state transition or paid call performed by worker.
