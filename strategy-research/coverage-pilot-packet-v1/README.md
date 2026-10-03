# Coverage pilot deterministic packet assembly

Research/execution risk: this builds a request list, but never sends it. New PR
review is required before using the helper. The merged executor remains unchanged.
`protocol.json` is **pending pre-draw review**, with exact frame/code/raw pins,
seven books, six markets, price-only scope,30×six older strata,50×five unknown
props strata, and0 for the NFL2025 census. The missing caps are separately
max(1,ceil(eligible_count/20)) when positive, else0; lag applies to all selected new
requests, zero-bill EVENT_NOT_FOUND404 only to selected new props. All other errors
halt. No retries/replacement; all selected denominators remain. No seed exists.

Hub and independent reviewer must agree on the exact protocol before hub changes
execution_status to reviewed_for_execution, pins that FINAL file's canonical/raw
identities, and draws once. The pending protocol hash is not the final commitment.
Review source/frame pins, alpha/floors and finite missing policy before drawing.
The helper rejects the pending status before accessing a seed or live state.

`build.py` consumes an externally supplied seed record and its digest. It uses the
fixed existing global lock opened read-only, authenticates the complete baseline
and all historical receipts, projects request metadata, creates exact reuse proofs,
subtracts previously attempted cells, checks current raw/probe overlap and cumulative
budget, constructs the14-file packet/freeze and runs the actual captured validator.
It writes only a NEW output directory, never live runtime/receipts or credentials.
Unknown/prospective history fails closed: this builder is for the FIRST pilot only.
A raw-less prior designated attempt blocks; preserve its exclusion and resolve a
frozen zero disposition before purchase. Failed assembly never causes a redraw.

Once-only seed schema:
```
{"seed":"<64lowercasehex>","frame":"<canonical frame digest>",
 "protocol":"<FINAL canonical protocol digest>","sample_sizes":{...}}
```
Suggested persistent exclusive record:
`research-lab/acquisition/coverage-pilot-once/seed-record.json` in the project mirror.
Hub must open with O_CREAT|O_EXCL|O_NOFOLLOW mode0600 BEFORE generating randomness,
write/fsync and fsync its directory. Existing/partial record blocks; never generate
again automatically. Save/publish planner.digest(record) externally. Builder has
no seed-generation function. Replays use the identical supplied record.

After review and one seed, from the isolated reviewed checkout:
```
<PINNED_PYTHON> -B strategy-research/coverage-pilot-packet-v1/build.py \
 --repo <isolated_checkout> \
 --protocol strategy-research/coverage-pilot-packet-v1/protocol.json \
 --protocol-sha256 <FINAL_exact_file_SHA256> \
 --certainty /private/tmp/value-finder-older-certainty \
 --seed-record <persistent_exclusive_seed_record> \
 --seed-record-sha256 <planner.digest(record)> \
 --historical-bindings <reviewed_bindings_JSON> \
 --probe-bundle <actual_verified_football-probe-v1_root> \
 --output <NEW_packet_directory_inside_isolated_checkout>
```
The pinned Python is the existing football-v4-review-repo/.venv-football-archive
interpreter; no installation. Historical bindings schema is the exact reviewed
PR132 bindings: older_coverage_path points to original source-root coverage-report.json,
older_successors is the reviewed mapping (currently{}). Resolve actual probe root
from immutable input-provenance and verify all raw hashes; never guess it.

The builder prints exact root/list/cap/denominators/carried debit, not approval.
Hub must review/freeze the actual packet and obtain live exact paid authority/account
reconciliation. Current code/packet/global/cache checks run again in the merged
executor before keys or HTTP. No automatic statistical look or later-tranche release.
