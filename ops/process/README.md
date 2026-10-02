# Prospective process tooling

Standard library; no credentials, APIs, runtime stores, ledger writes or outcome
access. This does not migrate or relax any existing acquisition freeze/executor.
The example is synthetic and has **no spending authority**.

## One verification artifact per tested version

From the repo root:

```
python3 -B ops/process/process_guard.py test --config ops/process/verification.json --output /tmp/process-evidence.json
python3 -B ops/process/process_guard.py verify-test --config ops/process/verification.json --saved /tmp/process-evidence.json
```

Evidence binds declared inputs (source, tests, locks, fixtures and relevant config),
runner argv, actual interpreter/binary bytes, installed package versions, platform
and configured environment. Tests run without inherited secrets/environment;
stdout/stderr are retained only as hashes. Reviewers must verify trusted artifact
provenance, review the logic independently and run targeted missing/delta checks.
The report digest catches corruption, not deliberate forgery by its producer.
Declare **all** relevant dependency/config/test inputs in a project's config.

The focused CI workflow restores evidence by complete tested identity, verifies it
and runs only when absent/incompatible/failed. No fuzzy cache fallback. It uploads
a fresh provenance link even on docs-only commits. Workflow/runner/environment
changes invalidate evidence; docs outside the test input set do not. Concurrent
first-time runs can both miss the cache, so this is reuse, not global exactly-once
execution. This workflow covers these process guards only; it does not pretend to
replace every project's test environment or private-data acceptance.

## Purchase content versus supporting provenance

```
python3 -B ops/process/process_guard.py freeze --config ops/process/example-freeze.json --output /tmp/example-content.json
python3 -B ops/process/process_guard.py verify-freeze --config ops/process/example-freeze.json --saved /tmp/example-content.json
python3 -B ops/process/process_guard.py plan --config ops/process/example-stage/policy.json --request-list ops/process/example-stage/requests.json
```

The manifest shows **purchase_identity**, binding executable/dependency/request/
eligibility/policy bytes, and **supporting_identity**, binding tests/explanations
separately. The test report adds a distinct **tested_identity**. Editing a test
preserves purchase identity but invalidates affected verification. Editing budget,
recovery, eligibility, requests or executable bytes changes purchase identity.
Changing explanatory docs updates supporting provenance. New/missing undeclared
files or symlinks fail closed. Add a supporting file to the spec before rebuilding. Within unchanged declared
scopes, this changes provenance but not bound content identity; adding a new scope
also changes purchase identity.

Reviewers must establish complete dependency boundaries: static Python checks
catch direct imports/package initializers outside them, including imports inside
bound dependency sources, and reject common dynamic import/eval/exec forms. This
is **not a general proof of Python's runtime behavior**. Shell calls, extension
modules, indirect import aliases and filesystem/config access require independent
review and a runtime loader enforcing the captured closure. Non-Python executables
require explicit dependency review. The adopting stage must include guard/loader
source and external dependency locks in its freeze, verify under the shared lock,
execute captured verified bytes and prove undeclared inputs cannot be loaded.

A plan is the bound policy file; it contains no purchase root or executing Git HEAD,
so there is no self-referential hash. Request list bytes and finite IDs/costs must
match. `prior_reserved` excludes the separately itemized probe and other usage.
Its sum plus new cap must fit the cumulative ceiling. Real adoption must derive
these disjoint values from the durable global ledger, never from hand estimates.
The external hub approval binds executing commit + purchase identity + exact list
+ cap and remains subject to live revocation.

## Preplanned recovery and coverage halt

`validate_plan` freezes exact missing response handling and clean restart states.
`restart_candidates` is a pure validator taking a verified checkpoint and current
verified purchase identity. It returns untouched IDs only, retaining full missing
reservations and denominators, enforcing the reserve floor, and halting the next
tranche unless completed outcome-blind coverage passes. Unknown IDs, pending/
uncertain attempts, invalid receipts, released reservations or revoked authority
are rejected. No automatic resend or replacement.

The adopting executor must authenticate all inputs from actual receipts/global
ledger/provider counters, check HTTP/body/billing identity against missing policy,
compute coverage against all opportunities, acquire the existing global lock and
validate current live approval before sending. Booleans supplied to the pure
helper are assertions, not authenticators. The helper neither authorizes a run
nor modifies runtime. A clean restart within reviewed authority needs verification
only; any uncertainty or out-of-policy state needs separate reviewed reconciliation.
Completed acquisition evidence remains byte-for-byte unchanged.
