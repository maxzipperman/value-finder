# Value Finder governance

Authoritative coordination and review policy, prospectively authorized by the owner
October 2, 2026. Project research rules and dated registrations still apply.
This change creates no purchase, registration, live-job or betting authority.

## Roles and review

The Codex **hub chat** (`01a0f4c8-b074-70a3-87be-07f4bdc156df`) coordinates
Claude/auditor workers, merges consequential changes and maintains the single
**Paid data** queue in `STATUS.md`. Work has one issue, branch and PR.

| Risk | Examples | Merge evidence |
|---|---|---|
| Ordinary | Explanatory docs, presentation, isolated utilities with no research or execution effect | Relevant checks and one reviewer |
| Research | Calculations, identity, eligibility, scoring, rule-changing documentation | Independent technical review and hub approval |
| Execution | Purchases, registration, live changes; governance affecting their controls | Independent technical review, hub approval and exact execution authority where applicable |

For research/execution changes, retain both independent technical review and hub
approval. Each reviewer posts `AGREE <full current head sha>`, or may substitute
that same reviewer's formal GitHub **Approve** review only when the hub verifies:

- the reviewer's latest effective opinionated review is `APPROVED` and its
  `commit_id` equals the full current PR head; dismissed or obsolete reviews do
  not count, and no later withdrawal or `CHANGES_REQUESTED` review supersedes it.
  The hub verifies the reviewer's continuing agreement at merge time;
- the reviewer uses a distinct, independently authenticated account, independent
  of the author and the other required reviewer;
- the review includes a one-line rubric identifying scope checked, evidence/checks
  verified and protections preserved.

A native approval replaces only that reviewer's AGREE comment, never the other
required role. One person cannot supply both independent and hub review, and the
author cannot supply their own independent review or self-approve. Reviewers using
the shared `maxzipperman` account retain exact-head AGREE comments that identify
their role; a shared-account native approval cannot establish independence.
New commits invalidate exact-head approvals and require renewed agreement, **not
repeating unchanged tests**. The hub merges these changes. Ordinary changes need
one approval and can be merged by the responsible assistant. This approval-policy
change itself uses the prior dual current-head AGREE rule. When impact is
uncertain, use the higher tier.
Rule-changing docs are never ordinary. Tests inherit the risk tier of the invariant
they guard: weakening a spending, eligibility or scoring assertion needs independent
review and hub approval, even though purchase identity stays unchanged. Merge
agreement is not paid authority.

## Reuse verification instead of repeating it

Run the applicable suite once per tested source/environment/command version.
Save the machine-readable evidence produced by `ops/process/process_guard.py`.
CI uploads it; local acceptance saves the same format. Reviewers validate its
source inventory, environment, command list, results and provenance, independently
inspect the consequential logic, and test only changed or unresolved paths.
A source/dependency/test/command/environment change invalidates affected evidence.
A docs-only commit may reuse evidence if all declared tested inputs are identical.
Never treat a passing artifact as proof of operational safety. A hash is integrity,
not authentication: use trusted CI run provenance or independently verified local
results. No proof is reusable across an undeclared dependency change.

## Purchase and recovery boundaries

Only the hub executes paid requests within the owner's authorized scope. Before
purchase: check cache and overlap across the **shared global** lock/store/ledger;
review the exact list, content freeze, eligibility, cap (including probe and other
usage), reserve floor and cumulative ceilings. Approve the executing commit with
`APPROVED paid run: list <sha256>, budget <N> credits, commit <sha>` plus the
content identity and any required account ceiling. Validate live approval/revocation
before sends. Keep durable reservations, cumulative accounting, zero automatic
retries/redirects and outcome-blind coverage halts. Report actual billing, provider
balances, coverage and every missing/error/stop. Exhaust spent one-time approval.

For **future** executors, freeze a validated acquisition plan before purchase:
finite request IDs/costs, exact missing response policy, allowed restart states and
an outcome-blind coverage gate before the next tranche. A clean restart can reuse
that authority only when its reviewed executor verifies unchanged source/list/cap,
live authority, all saved receipts, shared state, and remaining cumulative budget;
it sends only untouched, unreserved IDs. Verification of an already allowed state
needs no new implementation/review cycle. A pending, uncertain or conflicting
attempt remains blocked: retain reservation, never resend, replace or auto-repair.
Changed content/list/cap or a state outside the approved rules requires separate
review and fresh exact authority. The future helper validates a plan and computes
eligible untouched IDs; it neither reads runtime nor authorizes/sends requests.
Current executors/approvals retain their own stricter semantics.

## Short handoffs and one source of truth

Use [the PR template](.github/pull_request_template.md): scope, risk, current head,
evidence, blockers, budget and next action/owner. Authors use GitHub's draft/ready
state instead of a readiness checkbox or repeated READY/NOT READY reports;
ready for review does not mean approved to merge or execute. Keep future and
unfrozen handoffs brief and link existing artifacts. Leave completed freezes and
captured source closures byte-identical, including READMEs outside a nearby
FREEZE inventory when an executed capture binds them. Updates report only
differences and link prior evidence; read the relevant diff and artifact before
entire transcripts. No unchanged-status messages. Worker check-ins are event driven;
the hub still rechecks live paid approval when executing. Quiet local monitoring is separately proposed in PR #123;
model routing remains PR #112, not this change.

`GOVERNANCE.md` owns coordination; `CLAUDE.md` owns research/project conventions;
`STATUS.md` owns current state and the sole paid queue; `ops/CLOUD_FIRST.md` owns
routing enforcement. Do not maintain alternate copies of these policies.

## Execution and research protections remain

Cloud first for git-only work; local work declares `LOCAL-BECAUSE:` and the Mac-only
need. Use isolated checkouts. **Nobody works in or switches branches in
`~/code/value-finder`**; scheduled jobs run that checkout. Do not install/load/unload
jobs without explicit owner instruction; never run alert/close-capture jobs from a
worker. Preview scoring uses `--now` and `--ledger` on a copy. Keys/raw data stay
local; no keys or private data in CI. Paper only, GET-only APIs, no-lookahead,
pre-registration, variant counting and sealed holdouts remain mandatory. The hub
never archives itself. Owner backup waiver remains: backup is optional, not a
purchase gate; local receipts, caches and cumulative records are mandatory.

## Future freezes separate content identity from provenance

`ops/process/process_guard.py` inventories every file within declared dependency
boundaries. All executable files, dependency locks/configuration, request selection,
eligibility and recovery policy bind the purchase identity. Tests and explanatory
docs have separate provenance; changing them alone preserves content identity but
invalidates their affected test evidence. Do not classify a registration/rule as
explanatory. Unexpected, missing or changed bound inputs fail closed; symlinks are
rejected. Reviewers establish complete dependency boundaries; static Python checks
reject direct local imports outside them and dynamic import/eval/exec. This is a
future format, not a migration of executed packets. An executor adopting it must
verify under the shared lock, execute verified bytes, and deny undeclared runtime
imports/configuration. The helper itself is **not** an executor.

Keep content identity independent of Git HEAD. Record current executing commit in
external approval, never in a committed authorization claiming its own commit.
Historical acquisition freezes and original approvals are immutable evidence.
