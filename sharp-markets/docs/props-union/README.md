# Outcome-blind NFL props union — PR161

LOCAL-BECAUSE: accepted odds caches/receipts exist only on the Mac. Quotes and
eligibility only. No outcome/stat/roster join, APIs, credentials, grading command,
2026 input, paid credit, pilot final look, adoption or runtime/job write.

The new `props_grade/union.py` extends the trusted coverage-only archive reader to
exact acquired NFL2023–25, rushing/receiving only. Existing2025 entry point and
registered grader remain unchanged. The accepted PR151 completion and corrected
PR159 readiness artifact are reused by exact hashes; original final is not opened
or recomputed. Only accepted designated request IDs are considered, not a cache
scan or a replan. Every receipt/raw byte and saved-record equivalence is verified
through the pinned existing reader. All shared ledger pins are checked before and
after projection under a read-only shared lock. It refuses other runtime locations.

887 fixed games /1774 opportunities:294/308/285 by season, T24+CLOSE_T10 each.
Provider-only/ambiguous games stay in every game denominator but cannot supply
eligible quotes. The native read authenticates1707 designated records. There are
64 unresolved-identity opportunities, one unbound opportunity, two missing designated
opportunities and two terminal-missing records. Missing counts can overlap other
absence counts; these are not mutually exclusive partitions or proof of never offered.

Quote pairs require the same authenticated response, book, exact provider label
and point, both actually offered sides and finite prices>1. No complementary side,
book fill-in, identity guess or price averaging. Conflicting duplicate prices are
excluded. Row flags mean quote-pair eligibility only; main-line choice, player identity,
participation, terms and registration remain held. Returned quotes stay in memory;
CLI writes only aggregate JSON to stdout. Exact names/prices/outcomes are not committed.

| Season | Fixed games | CandidateDK rush CLOSE: games / label-games | CandidateDK receive CLOSE: games / label-games |
|---|---:|---:|---:|
|2023|294|221 /1109|222 /2507|
|2024|308|215 /1167|215 /2506|
|2025|285|191 /1057|192 /2164|

All120 game/book/market/slot coverage counts match accepted PR159. One2025 Pinnacle
rushing T24 pair/player-label count falls331→330 after four quote rows are excluded
for conflicting duplicate prices. [Exact comparison](comparison.json) records this;
no candidateDK count or original gate changes. Provider labels are not verified GSIS
players. Available quotes are not fills; scheduled proxies are not first-play proof.

## Ready versus blocked

| Item | State | Smallest next resolution / owner |
|---|---|---|
| Exact acquired union, missing denominators, authenticated receipt reader | Ready for independent code/evidence review | Worker reviews current head; hub merges |
| Scheduled/fresh quote pairs and aggregate dry run | Implemented and measured | Review synthetic adverse paths/native hashes; no grading |
| T10 vs registered T5, unknown/null stats | DRAFT | Hub adopts dated [decision draft](DECISIONS-DRAFT.md) before affected outcome join; never claim T5 purchased |
| DraftKings book note | Conditional candidate, inactive | Hub activates dated original section8 note after timing/lineage decision; don't reselect using2023/24 |
| Variant/header accounting | Blocked | Worker/hub reconcile executed PR96+intervening trials and original frozen threshold applicability; fill exact original and discovery fields |
|8 proposed discovery cells | Finite DRAFT | Adopt B and K separately; no count change/new family/confirmation claim here |
| Roster identity | Unverified | Validate committed outcome-free season/team roster schema/provenance/hash; normalize names and require unique player on either canonical team; keep ambiguous/unmatched counts; no future role helper |
| Game/stat linkage | Unverified | Declare canonical schedule↔stat game/team/week/phase crosswalk before stats are opened; do not match silently against only played games or shrink frame |
| Main-line selection | Not applied | Bridge exact original all-lines-usable, power closest-half/tie rule with identity-preserving synthetic tests; no post-outcome selector |
| Participation / settlement / pushes / voids | Unverified | Commit dated market+book terms and participation source policy, retain unknown/void/push/missing separately; no missing-row-as-general-void assumption |
| NFL primary outcome sources | Declared columns only | Verify finite/null/conflicting record handling after amendment, not by reading outcomes in this PR |
| Pooled discovery inference | Not implemented/adopted | Fixed eight-cell procedure and reviewed game/day dependence; no model/subset search disguised as robustness |
| CFB/other markets | Unsupported here | Separate reviewed stat/identity/terms protocol; held CFB remains held |
| Older totals | Separate finite follow-on | Two-market/slot union adapter with independent game/settlement linkage, price-engine root/cohort/timing amendment; do not expand this PR |

Committed roster is `sharp-markets/config/props/nfl_rosters_2023_2025.csv`; its
existence and earlier implementation do not verify quote-specific linkage. Neither
it nor `player_week.parquet` values are read by this reader. NFL primary schema names
rushing_yards/receiving_yards are supported, but names alone do not prove a zero,
participation, overtime treatment, corrected-stat timing or book settlement rule.
Terms are not fabricated from present-day rules for historical bets. All-player
scope avoids the season-wide RB1/QB helper's demonstrated future-membership issue;
a future role filter requires a separate prefix-invariant policy.

## Exact next commands

From this reviewed isolated checkout, after current-head independent review:

```sh
VF_REVIEW_PYTHON=/Users/maxzipperman/.codex/.chatgpt-projects/g-p-6abd9b86b9548191a07ce7f1180bc80a/football-v4-review-repo/.venv-football-archive/bin/python
"$VF_REVIEW_PYTHON" -B sharp-markets/src/markets/research/props_grade/union.py --mode dry-run
"$VF_REVIEW_PYTHON" -B sharp-markets/src/markets/research/props_grade/union.py --mode eligibility
python3 -B ops/process/process_guard.py verify-test --config sharp-markets/docs/props-union/verification.json --saved sharp-markets/docs/props-union/test-evidence.json
```

Dry-run validates fixed metadata/ledger pins and opens **zero raw records**.
Eligibility requires existing pyarrow in the review environment, reads only accepted
historical quote receipts, prints aggregate exclusions, and leaves grading false.
There is deliberately no grading command or `--book-recorded`/outcome flag in this
reader. A future outcome join command requires a separately reviewed bridge and
adopted timing/stat/count/book/identity/main-line/participation/terms decisions.
No current `markets props-grade --archive-runtime` bypass or live replacement.

Native evidence: [dry-run](dry-run.json), [eligibility](eligibility.json),
[accepted-baseline comparison](comparison.json). Both reports bind reader and archive
source hashes, accepted readiness hash, ledgers, classifier/timing and final hash.
The finite [matrix](discovery-matrix.json) separates8 new claims from the original
already-counted pooled1; current count/bar remain unresolved, not silently314+8.
Bootstrap replicates are not thousands of new strategies; any new deciding selector,
threshold, sensitivity, model or subset expands K before outcome access.

Minimal hub decisions: adopt timing/stat clarification; reconcile baseline/original
header and proposed K; activate conditional original book note after those decisions.
The remaining linkage/main-line/terms checks are implementation tasks, not reasons
to ask the owner to manually audit each row. No further purchase is recommended.
