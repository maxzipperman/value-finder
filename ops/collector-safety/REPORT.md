# PR165 synthetic verification

Implementation commit tested clean: `38fba6ef8ad626110a6127abce0c7301e04511af`.
Complete declared test-input identity:
`42f8fdea446c3d64bb962c9b9956c305039b11beed97a2f825811081a855964d`.
Evidence is in `EVIDENCE.json`; evidence-only publication does not change those inputs.

- 21 actual-guard/source integration tests pass. They include process death,
  disk failures at three stages, duplicate slots, concurrent same-slot/other-collector
  admission, external pending state, nine-market reservations, stale/missing
  authority, reserve/cap checks, receipt tampering and real NBA kernel-lock overlap.
- 19 selected existing NBA collector/HTTP checks pass. Cadence/cache/quota behavior
  tests explicitly mock admission; they do not claim production spend permission.
  HTTP checks use fake sessions/localhost. One pre-existing external `.invalid`
  DNS check was deliberately excluded. The first loopback attempt was blocked by
  sandbox socket permissions; repeating with authorized localhost access passed.
- `zsh -n ops/install_live_uses.sh` and `git diff --check` pass. Installer was not run.
- No paid requests, credentials, quotes/outcomes, sealed files, live-job changes,
  merge or runtime adoption. Local packages exist only in this isolated test checkout.

Reproduce (the localhost test needs permission to bind loopback):

```
sharp-markets/.venv/bin/python -B ops/process/process_guard.py test --config ops/collector-safety/verification.json --output /tmp/collector-evidence.json
sharp-markets/.venv/bin/python -B ops/process/process_guard.py verify-test --config ops/collector-safety/verification.json --saved ops/collector-safety/EVIDENCE.json
```

CI independently computes its own runtime-bound evidence from the PR head. An
independent technical disposition and passing required CI remain merge prerequisites.
See README for the exact envelope/ledger schema and shared-account integration seam.
No approval text, initialized live ledger or finite live caps are supplied by this PR.

READY FOR THE HUB for independent review. NOT READY for deployment until exact
live approval/caps and verified shared-account coordination exist; installation
and adoption remain hub-owned. Dashboard status producer is a separate dependency.
