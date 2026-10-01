# Football archive v4 — refrozen after hub review

The reviewed request rows remain exactly unchanged: 2023–25 first, 82,830 new credits, then stop for outcome-blind coverage; 2020–22 costs 68,010 and requires a separate approval. Research purchases including probe: 152,527. This revision repairs execution and makes scheduled timing mandatory, so hindsight can only exclude prices. Read BILLING-REPAIR.md and ELIGIBILITY.md.

Spending requires owner evidence recorded after an authenticated hub APPROVED comment. The comment and artifact bind CSV hash, request-set hash, credit cap, current full commit and root. The hub supplies max_baseline_used and the billing period in its reconciliation approval. No approval is supplied by this bundle.

Runtime state is fixed at ~/Library/Application Support/ValueFinder/football-acquisition-state/<root>, outside every checkout. A separate durable registration marker survives root-folder deletion. Execution under ~/code/value-finder is refused. No automatic resend occurs, including accepted-missing responses. A30=5,000; shared usage and counter lag are each bounded at 100. Approvals never reset probe/attempt budgets.

Use an isolated Python 3.12.11 venv built to runtime-lock.json, not the live checkout venv. Offline: python -B executor.py --root PINNED_ROOT. Checks: PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -B -m pytest -q -p no:cacheprovider test_v4.py. Fixtures stay local and are restored by exact hash.

The hub's separate price-engine --handoff/amendment 2 work settles the registered reader before purchase. The adapter includes the exact manifest, paid/reused paths and terminal missing requests. No legacy F1 repurchase, outcome join, grading, live-job pause or sealed-season read happens here.
