# Football completion and next-run readiness audit

**Verdict:** the recent acquisition is intact and its billing reconciles. **Do not run the strategy backtest yet. Do not execute priority 2 with the current runner.** The saved data need no repurchase. The analysis blockers and the separate purchase prerequisites below are concrete and reproducible.

Audited October 1, 2026. Main baseline: `f095bacc2e7f34d3205d89de1e38356c54c74ca4`. Executed acquisition commit: `fc096230d337fb03d4136d6b41c422b91289dfa0`. Follow-up to [completion report on PR 99](https://github.com/maxzipperman/value-finder/pull/99#issuecomment-5942265156), merged PR 102 and backup PR 79. LOCAL-BECAUSE: the receipts, raw cache and coverage report are available only on this Mac.

This is an audit of implementation and outcome-blind metadata. No strategy was scored, no game results or forward ledgers were opened, no credentials were read and no API purchase was made. Only this audit's report/scripts/derived evidence and STATUS.md are changed. The frozen bundle and global acquisition state are untouched. The user-appointed Codex hub handoff is already recorded on PR 99; the older coordinator text in AGENTS.md does not supersede that instruction.

## What passed

- Independently recomputed the frozen file map and root; all bundle files match.
- Rehashed **5,522** paid response/receipt files and all **12** reused response hashes. Every completed receipt is accounted for; no pending or unresolved attempt.
- Recomputed bills from response headers: **82,830 credits**, exactly the reserved purchase ceiling. **2,760 valid new responses + 12 reused = 2,772 usable snapshots**, and one paid slot is explicitly missing.
- Recomputed the full **9,939,544,295-byte** coverage report hash; it matches the executor's completion hash. All required recent request IDs are accounted for in the ledger.
- Synthetic guards pass for the one-hour decision cutoff when kickoff is later delayed, unregistered handoff refusal, priority-2 refusal, exact missing-response approval and restart without repurchase.
- Eight targeted frozen-executor tests passed; six independent reader checks reproduced the behavior in `reader-evidence.json`. These are synthetic checks of the actual reader functions, with credential/outcome/network access forbidden. They are not profitability tests.

Evidence: [saved-run-evidence.json](saved-run-evidence.json), [reader-evidence.json](reader-evidence.json). Final ledger hash: `eb9e93e354babef2be73ddaa13ea6e2913c58eaaff706ed4e78aec1381636190`. Coverage hash: `adb6c303948a18de52b9213bc2afacf7886213598ac3d64e05d45b3f7919d3e3`. These are historical end-of-run balances, not a fresh account query: used 84,525; remaining 4,915,475. Increase during acquisition: 82,830 own + 2 external. Probe plus new purchase is 84,517; conservative ledger debit 86,212 includes the retained 1,695 external reservation and is not another bill.

## Analysis blockers

### A1 — P1: canonical identities and team orientation do not reach the engine

**Evidence:** `sharp-markets/src/markets/research/price_engine/quotes.py:110` groups on provider event ID; `engine.py:185` sorts on event ID and `engine.py:186` deduplicates on it, not canonical game identity. `engine.py:123` discards home/away labels before merging reference prices; `engine.py:194` selects a close by event ID and `engine.py:196` drops team identity from that close. The registration acknowledges these unresolved limits at `sharp-markets/docs/PRICE_ENGINE_PREREGISTRATION.md:412` and `:429`.

**Observed relevance:** 223 of 3,471 matched canonical games seen in valid recent responses have more than one observed provider ID (**6.42%**), above the registration's 1% trigger for a hub decision. Twenty-seven provider events have reversed canonical home/away identities across sightings. This is a metadata census before the engine's eligibility cuts; it does not mean 223 duplicate bets or 27 misgraded bets occurred. Five examples of each are recorded in the evidence JSON. There are also 3,125 repeated sightings with no unique binding in the frozen map, which must remain explicit rather than silently become primary canonical games.

**Reproduction:** `reader_reproductions.py` feeds two IDs for the same teams and kickoff to the real loader and entry selector: it returns two synthetic entries. A second case retains `home=H` at entry and `home=A` at the selected close; the close output carries no team label to detect the mismatch. This can double-count one game or compare a team with its opponent's close.

**Smallest correction:** before the first analysis, adopt an outcome-blind canonical-ID mapping for the exact acquired universe and key one-bet grouping/joins on canonical game plus canonical team side. Normalize spread signs consistently. Until that mapping is implemented, quarantine multi-ID/changed-orientation partitions with explicit exclusion counts and a dated registration amendment. Never resolve conflicts by price or result. Require synthetic regressions for both cases and a names-only census on the exact handoff population.

### A2 — P1: a future kickoff correction can admit an earlier out-of-window quote

**Evidence:** `quotes.py:124` uses a nine-day coarse window; `quotes.py:194` replaces kickoff with the latest listing; `quotes.py:197` applies the exact seven-day bound only to that later kickoff. `engine.py:174` checks both kickoffs for the one-hour cutoff but supplies no missing seven-day decision-time guard.

**Reproduction:** on September 1 at 16:00 a synthetic game is scheduled for September 9 (eight days away). The row is excluded when that is all the history. A September 2 snapshot moves kickoff to September 7. The same September 1 row now survives and becomes the first entry. No prices change. Thus later information admits a decision that did not meet the declared seven-day window at its own timestamp. The existing delayed-kickoff one-hour regression passes; it does not cover this direction/window.

**Smallest correction:** apply the exact seven-day maximum to the decision-time `commence` as well as the later safety-check kickoff, and keep later corrections exclusion-only. Add the supplied synthetic case as a regression before registering the reader. No real-data fit is necessary to fix it.

### A3 — registration gate: data acceptance is not analysis eligibility

`handoff.py:117` still has `REGISTERED_ROOT = None`; `_check_registered` at `:238` correctly refuses the run. Amendment 2 at `PRICE_ENGINE_PREREGISTRATION.md:443` is draft; its season choice at `:493` is unresolved. Register the intended three- or six-season decision exactly once, before the first result, and update the root/tests/help consistently.

The engine intentionally ignores acquisition eligibility labels (`PRICE_ENGINE_PREREGISTRATION.md:535`). Synthetic evidence confirms that it can accept a 24-hour-old quote; the acquisition evaluator checks quote age and future timestamps at `price_eligibility.py:87`. The acquisition close proxy uses a 5–20-minute window and independent scheduled-kickoff conflict checks (`:119`), while the engine uses a last-hour provider-based close. Consequently the completion report's 76.8% Pinnacle figure is **not** a certified engine sample or permission to bypass its own checks. Before scoring, explicitly map accepted/rejected rows under the chosen registered policy, including future quote updates, stale quotes, revised schedules and postponements. Different policies can be legitimate research specifications, but their populations and limitations must be stated prospectively.

The existing 38 variants use count 271 (`engine.py:57`, `:82`; Amendment 2 `:552`), while the acquisition protocol sets a historical trial floor of 314 (`protocol.json:193`) and open PR 96 records the additional historical search. This is a **registration decision to reconcile**, not proof that the older preregistered family must be retrospectively regraded. State which bar applies to the unchanged family and which applies to newly added/redefined tests; do not silently mix them or count the original 38 twice.

## Older-purchase prerequisites

### P1 — current executor and handoff are recent-only

`executor.py:76` accepts priority 1 and its recent cap; `:417` skips all other rows. `cache_handoff.py:34` also skips priority 2. The supplied `test_older_and_modified_allowlist_rejected` passes. Editing an authorization JSON alone cannot purchase or hand off 2020–22. This is an intentional gate, not a regression.

The frozen manifest reconciles to **2,279 older slots: 2,267 new, 12 reusable, 68,010 credits**. A separately reviewed priority-2 runner/reader change must carry forward the existing 1,687-credit probe, 82,830-credit recent purchase, conservative external debits, receipts and durable reservations. Do not create a fresh ledger that forgets prior spending. Do not change the existing frozen bundle in place. Preserve exact allowlists, no automatic retries, bounded snapshot-gap acceptance, restart checks and account ceilings. Add overlap tests proving that recent/reused calls cannot be repurchased and that a six-season reader includes both purchased slices.

`protocol.json:187` additionally requires owner acceptance tied to the recent coverage-report hash and bundle root, then a new exact-commit/list/budget approval. This audit reports evidence; it is not that acceptance or purchase approval.

### P2 — verified backup of this store is not established; proposed backup omits it

Backup PR 79 remains draft/open at `9c8a5e52bf5fd79c57306e5ddd55f442e5f7ae37`. Its `ops/backup_data.sh:109–130` copies project raw folders, forward records, the home weather cache and DuckDB. The actual acquisition is under `~/Library/Application Support/ValueFinder/football-acquisition-state/` (`executor.py:47`), including sibling `registrations/` markers (`:117`). These are outside every default source in that script. Changing MARKETS_DATA_DIR to this runtime's `data` could include raw parquet but still omits the ledger, receipts and registration markers.

**Reproduction:** compare the script's explicit `add` source list with the fixed runtime and marker paths. No default source is an ancestor of either. Only the system disk and two installer images were mounted at audit time. That does **not** prove no remote/offline backup exists; no verifiable backup/restore evidence for this new runtime was found in the handoff.

**Smallest correction before more purchases:** include the complete immutable bundle/reuse fixtures, runtime data, receipts, ledger, manifests, central registration markers and non-secret approval/reconciliation evidence in an encrypted off-device backup. Test a restore into scratch and verify frozen/receipt/response hashes; do not run its executor or duplicate the live state registration. Record destination identifier, backup timestamp and restore hashes. Complete PR 79 review separately.

## Runtime/performance finding

**P2, before full analysis:** `cache_handoff.py:27` calls `json.loads(coverage_path.read_text())` on a **9.26 GiB** document just to inspect three header fields, and `:14` later hashes files with `read_bytes`, allocating another full-file buffer when used for the report. This Mac has 64 GiB RAM. A full materialized report includes the raw text and a much larger object graph while the reader also constructs its data tables. The report itself was streamed successfully for this audit, but the end-to-end analysis memory peak is **not measured** and no OOM is claimed.

Use a streaming, hash-verified header/manifest check (or a small completion certificate bound to the full report hash), stream the report hash, then benchmark the production handoff with a declared memory budget before fitting. Registration currently blocks an ordinary real handoff; this audit did not bypass it to allocate the full report. A new frozen reader version or reviewed adapter is required if changing code inside the hashed bundle. This performance issue need not invalidate the completed acquisition or prevent separately validated older-data storage.

## Coverage and the missing snapshot

The missing college daily request on October 15, 2023 targets **54 canonical games × 10 books × 3 markets = 1,620 intended entry instruments**. All 1,620 remain in the coverage report as `missing_or_ineligible_entry`; all 54 target games are seen elsewhere in valid saved responses. This rules out losing those games entirely from the acquired universe, but does not establish that their first signal or eventual close would be unchanged. No hypothetical bets or results were inspected. The stale returned response contained one event and was not used to invent an eligible replacement. Its 30-credit charge and reservation remain intact.

| Stratum | Instruments with a valid entry/close pair | Intended instruments | Coverage |
|---|---:|---:|---:|
| americanfootball_ncaaf / 2023 | 103,284 | 170,250 | 60.7% |
| americanfootball_ncaaf / 2024 | 121,899 | 193,830 | 62.9% |
| americanfootball_ncaaf / 2025 | 129,462 | 191,610 | 67.6% |
| americanfootball_nfl / 2023 | 48,439 | 61,380 | 78.9% |
| americanfootball_nfl / 2024 | 52,422 | 61,410 | 85.4% |
| americanfootball_nfl / 2025 | 57,496 | 61,410 | 93.6% |
| 24_to_72h | 173,450 | 217,500 | 79.7% |
| over_72h | 251,243 | 416,400 | 60.3% |
| under_24h | 78,328 | 94,920 | 82.5% |
| first_observed_at_least_48h | 500,380 | 707,820 | 70.7% |
| first_observed_under_48h | 2,641 | 21,000 | 12.6% |

Pinnacle's aggregate reproduces: **56,803 / 73,989 = 76.8%**. Full book/market aggregates are in the JSON. These are slot/game/book/market instruments, not independent games or trading opportunities; MOS-only cells do not infer a triggered game cohort. Dates of first observation refer to the two-day provider sweep, not first listing or proof of no earlier offering. The inherited registry's 6,880 matched / 4 matched-without-valid-listing / 350 unmatched counts cover 2020–25 and are not recent-only counts.

Coverage is useful for a restricted retrospective study, but no predefined numeric threshold here makes it an automatic purchase/strategy pass. Late-observed strata are particularly sparse. Report season/book availability and excluded opportunities rather than pooling these differences away. The weather slots remain diagnostics: they do not reproduce the live Open-Meteo multiple-look trigger.

**Season-boundary check:** a December 2, 2025 requested snapshot contains one provider event carrying a November 21, 2026 kickoff. Only its ID/time metadata was inspected and it was excluded from the recent metadata census before any market fields were used. The frozen coverage normalizer rejects events outside 2020–25 (`coverage_report.py:25`), and the downstream reader must retain its independent season filters. This is not evidence of a 2026 result read or a strategy holdout test; it is a reminder that an unsealed request timestamp alone does not certify every returned event. See `boundary-metadata.json`. Do not claim raw responses contain no future-season listing.

## Recommended order and release criteria

1. Record the completed acquisition and owner coverage decision using the verified hashes. Preserve the missing slot and all denominator exclusions.
2. Obtain/verify an independent backup covering the global store and registration markers.
3. Review a priority-2 implementation with cumulative-budget and no-repurchase tests; approve only the frozen 68,010-credit request set after the coverage acceptance. Analysis bugs above do not require repurchasing recent data.
4. Before any strategy result, fix canonical/team-side joins and the seven-day timing regression, settle the policy/season/count registration and make the handoff's report check memory-bounded. Run a real cache-only, outcome-blind reader preflight and record the resulting population.
5. Only then run the registered analysis. Keep 2026 outcome exposure and any forecast replay behind their own registered scope. No profit gate was evaluated by this audit.

## Reproduction

Use an isolated checkout at the audited baseline plus these audit files. Install the project's locked sharp-markets dependencies into that checkout's own environment. `reader_reproductions.py` requires those dependencies; it disables dotenv loading and forbids network, forward data, score tables and pricing cohorts. It never calls the strategy grader.

```sh
sharp-markets/.venv/bin/python -B reviews/football-completion-audit/reader_reproductions.py
```

For the local saved-run check, supply the verified frozen bundle and completed runtime, with pyarrow and ijson in an isolated audit environment. ijson was installed into a separate temporary dependency directory, not the frozen executor environment.

```sh
python -B reviews/football-completion-audit/audit_saved_run.py \
  --bundle strategy-research/football_archive/acquisition/football-archive-v4 \
  --runtime '<completed global runtime>' --output '<derived evidence JSON>'
python -B reviews/football-completion-audit/boundary_metadata.py \
  '<completed global runtime>' strategy-research/football_archive/acquisition/football-archive-v4
```

Targeted frozen tests: `pytest -q -p no:cacheprovider test_v4.py -k 'older_and_modified or approved_missing_can_continue or explicit_account_only_recovery or intended_missing_instruments or new_checkout_commit or deleted_runtime_folder'` with plugin autoload disabled and bytecode writes disabled: **8 passed**. Full acquisition tests previously passed 146; this audit reran the eight relevant controls rather than claiming a new full-suite run.

Review dimensions: **correctness—blocked for analysis by A1/A2; security/integrity—hashes and fail-closed registration pass, no new secret/network access; performance—unbounded report materialization needs a bounded check/measurement; maintainability/readiness—recent-only scope and draft registrations are explicit, backup integration remains incomplete.**

**READY FOR THE HUB to review this audit. NOT READY for strategy grading or an older purchase under the existing approval.**
