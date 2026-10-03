# CFB complete weather inputs — implementation and prospective adoption

October 2, 2026. PR #136 / issue #135. Research tier; independent review and hub
current-head agreement required. LOCAL-BECAUSE: synthetic validation against the
Mac's project interpreter and private forecast-availability projections. No paid
calls, keys, actual outcomes, observed weather, sealed-season values, fitting,
retrospective regrading, installed freezes or live jobs touched.

## Reproduction and resulting behavior

Five synthetic hourly rows at 19:00–23:00 UTC; kickoff 19:30 UTC; wind
`[15, null, null, null, 10]`, precipitation/snow all null. Original live summary
reported wind 15, precipitation 0, snow 0. Replay's previous-day wind also
reported 15. Neither is a complete forecast.

The live summary now requires four finite wind values at kickoff hour through
+3h, finite kickoff temperature, and four finite total-precipitation/snow values
at +1h through +4h. Accumulations retain their original alignment. An absent hour,
missing field or nonfinite value returns `None` through the existing `summarize`
contract. The board labels that row `no_forecast`; its precipitation/snow remain
NaN. A finite all-zero window remains valid dry weather. Complete inputs retain
old numbers and keys. Incomplete gusts, a display field, remain NaN without
invalidating the required inputs.

`summarize_checked` exposes per-field required/present/finite counts and reason;
the returned board row adds `wx_missing_reason`. The existing saved snapshot and
ledger schemas are unchanged; consumers needing detailed diagnostics must use
that returned column or checked API. Parse errors have an explicit payload/time
reason rather than manufactured per-field counts. Duplicate timestamps fail
closed; timezone-aware timestamps normalize to UTC; naive response hours retain
the requested-UTC interpretation; unknown kickoff timezone is refused. Midnight
windows require the actual following-day hours, never a truncated day's slice.

Replay requires all four wind hours independently for each lead. An incomplete
lead stays NaN while complete other leads remain usable; the legacy three raw
keys, timing formula, calibration and gate thresholds are unchanged.
`summarize_prev_checked` exposes the same denominators and reason per lead.
No historical replay was run or rewritten.

NFL's separate `summarize_hourly` and `previous_forecasts` contain analogous
skip-null sums/means and 23:00 clipping. Source inspection identifies a separate
NFL repair need; this PR implements the hub's current **CFB** assignment only.
Its local-hour input representation and midnight acquisition contract need their
own reviewed scope. No claim is made that NFL missingness is repaired here.
Missing weather does not block weather-independent props or CFB Rule HT.

## DRAFT prospective adoption; not a registration amendment

This is an input-eligibility correction. Do not silently deploy it into the
already-started registered CFB forward test. The hub must first determine and
record a dated future effective UTC/version before any affected outcome is
known, and obtain independent current-head agreement. Existing ledgers,
registration versions, pricing cohorts, replay files and prior reported results
remain immutable. Until that prospective decision, installed code stays as is.
This draft supplies no deployment, scoring or new research authority and tests
no new strategy variant.

## Verification

44 focused CFB checks passed: new synthetic completeness/board fixtures plus the
existing synthetic gate test and decision-clock test. Saved local process artifact:
`/private/tmp/weather-completeness-tests.json`, declared inputs/commands in
`verification.json`. Tests that read saved historical replay outcomes were not
run. The existing CFB interpreter ran isolated source with bytecode/plugin/cache
writes disabled; config creates only empty isolated project directories.

3 standard-library metadata projection checks passed; artifact
`/private/tmp/weather-coverage-tests.json`, configuration
`verification-coverage.json`. Artifacts contain private environment/provenance
bindings and remain local. Reviewers should validate them locally and review the
logic independently; passing fixtures do not establish live operational safety.
