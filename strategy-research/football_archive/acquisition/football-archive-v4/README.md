# Football archive v4 — review before spending

This narrow repair changes billing/reconciliation and coverage-purpose reporting. The reviewed v3 request set and price eligibility are preserved byte-for-byte / exact-row-for-row and verified against v3 provenance.

Recent: 82,830 credits. Older: 68,010, separately gated. Research purchases including probe: 152,527. Shared/pre-run usage is additionally reserved conservatively against cumulative limits; it does not increase the allowed recent request list.

A separate approved, root-bound owner authorization, exact-list hub go-ahead and account reconciliation are required. Baseline may be captured from the first free check; no hard-coded September balance. Without an explicit documented prior-usage debit, the runner reserves ALL current-period used credits additionally (potentially double-counting the probe), then adds peak external usage. This avoids inventing zero other usage. Provider reset never resets local probe/attempt budgets.

Positive shared usage up to 100 credits and counter lag up to 100 are handled cumulatively. Catch-up is not charged twice. Larger deviations halt. In-run resets halt; an approved account-only reconciliation can establish a fresh baseline when no paid attempt is pending and the approval pins the stopped ledger hash. Pending calls require hash-pinned saved-response reconciliation offline; no automatic resend or ledger editing.

Vendored BulkClient uses probe-advised A30=5,000; the wrapper independently enforces the stricter 100-credit shared-usage/lag limits. Runtime manifests record the interpreter path and reconciliation hash/evidence.

Use sharp-markets/.venv/bin/python with -B. Offline preflight: `python -B executor.py --root PINNED_ROOT`. Portable tests: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -B -m pytest -q -p no:cacheprovider test_v4.py`. No approval artifact is inside this immutable bundle.

Cache handoff uses the sharp-markets RawCache format and keys. The stock price-engine CLI replans legacy F1; before grading, the hub must approve an adapter that consumes this exact manifest and both paid/reused response paths. Never buy legacy F1 again to fill a second cache.

No forward-test jobs are paused and no 2026 signal logs are inspected. Use a quiet acquisition window when available; bounded job overlap is accounted for and excess overlap halts. Stop after 2023–25 and publish the outcome-blind coverage report before any older purchase or outcome joins.
