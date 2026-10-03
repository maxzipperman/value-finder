# Independent review repair (PR165)

Supersedes the readiness claims for head `70b9f4c`; original REPORT/EVIDENCE remain
historical provenance. No merge or deployment approval is asserted here.

## P1: declaration-only coordination could admit an over-cap send

Reproduced review case: baseline100, external0/ready, ceiling101, a listed legacy
writer already spending1. Declaration validation cannot know that writer is active.
The previous implementation could send before detecting provider used102.

Smallest bounded correction: production `paid_get()` and installer metadata preflight
call `require_bridge()`, which unconditionally raises. No populated envelope, ready
ledger, writer list, environment flag or approval string can enable production.
Existing reservation implementation is now `_reservation_get()`, a private source-only
primitive exercised synthetically and unused by every collector/installer. The bridge
itself remains unimplemented; changing the source hold needs a later reviewed change
that actually enforces coordination. This PR no longer offers an executable configured
mode. A functioning enforced bridge or nonoverlap/reconciliation mechanism is still
needed before installation, followed by exact live authority/caps.

Adverse tests exercise the reviewer's populated-envelope over-cap scenario (zero
fake GETs), actual NBA paid entry, actual read-only installer metadata preflight,
NFL `tag=poll`, both real poll scripts and the real props logger. The installer itself
was not executed; no key comparison or launchd operation occurred.

## P2: affected weather callers/evidence omitted

Existing NFL filename/cache and CFB cached-poll tests explicitly replace paid admission
to test downstream behavior; their fixtures do not imply live permission. The props
logger's fake `_get` accepts its new admission keywords. New integration tests import
the actual packages and run actual scripts with synthetic ledgers and fake sessions.
They prove the production hold reaches every named weather paid caller. These are
not AST-only caller tests. Each weather project uses its own isolated venv installed
from its declared requirements, including statsmodels.

Verification binds both package source trees, fetch/config/quota/board/notify/default
modules, caller scripts (including NFL's tag selector), selected tests, requirements,
workflow and verification declarations. CI path triggers include all those dependencies.
CI independently captures evidence for each project runtime. No outcome/data file is
a verification input or opened by these targeted tests; test quotes/ledgers are synthetic.

## Exact-input evidence

| Checks | Count | Clean tested source | Input identity / saved file |
| --- | --- | --- | --- |
| Reservation/disabled-production integration + selected existing sharp collector/HTTP | 24 + 19 | `92a1f48b2967565880340611f748aa361cddf647` | `58aeda3ab14632ddf1fe7435ee0eebc77dad0ec0ebc9e548d28cdb39f91432a4`, EVIDENCE_REPAIR.json |
| Actual NFL live/odds/quota/caller tests | 40 | `98c7dabda05893984452b83ce654a63bb56f10bd` | `89ee3bd3575ec5ea5fb69e083510d19ad1f8f6089169c9ac1df650e9b376c1f3`, EVIDENCE_NFL.json |
| Actual CFB live/odds/quota/caller tests | 21 | Same `98c7dab` | `8a3689a3ccee006f80be94b61a559f2ced610767b9a698d31067c390cdb034a4`, EVIDENCE_CFB.json |

All pass. Weather evidence was reused after adding only sharp guard/installer
integration tests; each weather input identity still verifies unchanged. No unchanged
broad research/backup suite was rerun. External `.invalid` DNS test stays excluded;
the selected localhost regression is synthetic. Installer syntax and diff whitespace
checks pass. Publish-only evidence/doc commits preserve all three input identities.

Reproduce/verify using each project's own Python with its corresponding config:
`verification.json`, `nflweather-verification.json`, `cfbweather-verification.json`.
Use `ops/process/process_guard.py test --config <config> --output <new-evidence>`
and `verify-test --config <config> --saved <corresponding saved evidence>`.

READY FOR THE HUB for renewed independent source-only review. NOT READY for
installation/send: production is unconditionally disabled pending the missing reviewed
enforcement mechanism and exact authority. No credentials/provider/outcomes/live files,
paid requests, runtime adoption or merge. Dashboard producer remains separate.
