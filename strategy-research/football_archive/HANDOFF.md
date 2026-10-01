# Football archive v4: review before spending

LOCAL-BECAUSE: raw-data: verification replays the 24 sanitized probe responses available only on this Mac and checks the pinned sharp-markets interpreter.

Proposed repair for issue #98. The reviewed v3 request rows are exactly preserved, including all 665 MOS slots and the 28 new alternate closes. Price eligibility is byte-identical to v3. The new root includes billing reconciliation, explicit hub approval checks, purpose coverage and a read-only cache handoff.

- V4 root: `09c29ac0e003c50595581e74345ffc0838a85c55c7b28aa14d61b83799e5ccd2`.
- Exact request-set hash: `63d4ab26f80d54d9316de8b9b5457adc6ca4609e4be4cb01da63e98e9dceea9b`.
- First slice, 2023–25: **82,830 new credits**, 2,761 new requests plus 12 reused responses.
- Older slice, 2020–22: **68,010 credits**, separately gated and unsupported by this executor.
- Research purchases including the completed probe: **152,527 credits**. Shared/pre-run usage is reserved additionally against the existing cumulative ceilings; it does not enlarge the request list.

## What changed

The runner adopts an approved current baseline, records its numeric counters and reconciliation hash, and preserves the probe and every attempted-request reservation across resets. It reserves cumulative positive external usage once, tolerates up to 100 credits of counter lag and up to 100 of shared usage, and stops beyond those limits. Cumulative high/low counters prevent catch-up from being charged twice; stale balances cannot create spending capacity. The client keeps the probe-derived repo margin A30=5,000, while the wrapper's limits are stricter.

Restart recovery is explicit. A stopped account-only run requires approval bound to the stopped ledger hash. An unresolved paid attempt can be reconciled only against an existing exact-hash saved response, offline; it is never automatically resent. Missing responses and overcharges stay stopped. The runtime manifest records the interpreter and every frozen source digest.

Both the owner's root-bound authorization and the hub's exact-list go-ahead are checked before any credential read or transport. The [authorization draft](authorization.draft.json) and [account reconciliation draft](account-reconciliation.draft.json) authorize nothing as saved. Approving capture mode permits the first free check to establish the numerical baseline; an unspecified prior-usage debit conservatively reserves all current-period used credits, potentially double-counting the probe. No current balance was read during preparation.

## Cache handoff

The paid runtime uses the sharp-markets RawCache layout, schema and key algorithm. Its root is `acquisition/football-acquisition-runtime/data/raw`. Twelve recent probe responses remain in the immutable bundle's `reuse/` directory. **Stock `markets price-engine` replans the legacy F1 list and will not automatically see all these inputs.** Never rerun the legacy F1 paid download to fill a second cache.

The frozen [cache_handoff.py](acquisition/football-archive-v4/cache_handoff.py) reads only after recent completion and outcome-blind coverage. `build_handoff(bundle, root, runtime)` verifies the response and receipt hashes, includes paid and reused paths, and returns the exact recent manifest. `as_calls(handoff, markets.oddsapi.bulk.Call)` and `ReadOnlyCache(handoff, runtime/'data/raw')` supply the existing price-engine `run(cfg, calls, cache)` reader interface without moving data or replanning purchases. The handoff cannot fetch or write. The hub must approve this integration and the analysis registration before grading; no scorer or outcome loader ran here.

## Verification and portability

**110 offline checks pass**, including all 24 sanitized probe bodies through the unchanged vendored market client, durable failure/restart cases, shared/lag/reset accounting, exact hub approval gates and the read-only handoff. The full frozen validator checks the pinned root with reused-cache validation. Runtime versions match `/Users/maxzipperman/code/value-finder/sharp-markets/.venv/bin/python`. The vendor client/cache/HTTP/settings/normalizer remain byte-identical to the repo.

This is a functional offline rehearsal using one-request temporary execution fixtures and separate full static validation; it is not a 2,761-request production-throughput rehearsal. No new API requests, real credentials, outcome joins or sealed 2026 data were read. No live jobs were changed or paused.

Raw response parquet files remain local and gitignored. A fresh clone needs the original 24 probe fixtures. `restore_local_reuse.py --from-bundle /path/to/verified/local/bundle` restores only matching frozen hashes without an API call. Then use the pinned interpreter with `-B` to run `executor.py --root 09c29ac0e003c50595581e74345ffc0838a85c55c7b28aa14d61b83799e5ccd2` for an offline preflight, and `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -B -m pytest -q -p no:cacheprovider test_v4.py` inside the frozen v4 folder. Source and metadata are committed; paid raw payloads are not.

## Report for the hub

Review v4 and the draft files against the Paid data entry in STATUS.md. Confirm no overlapping legacy F1 purchase, approve the exact list and owner artifact, confirm the cache handoff contract, and choose a run window. Existing jobs may remain active within the 100-credit shared-usage bound; excess activity stops acquisition. Any job pause is the hub's responsibility. Stop after 2023–25 for the outcome-blind report before buying older seasons or joining results. Backup readiness remains a hub execution check under the existing paid-data plan.

**READY FOR THE HUB**: offline repair, immutable v4 root, committed exact list and draft approval files are ready for review. **Spending remains unauthorized** until the hub's exact-list go-ahead and owner approval are recorded. This worker will not merge or start a paid run.
