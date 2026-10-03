# Value Finder — running progress and credit plan

Updated October 2, 2026, 7:31 PM Pacific. Maintained by hub chat.

**Current position:** recent football odds, NFL alternate lines and the first NFL props slice are downloaded. The exact older offline reconciliation is complete. **Owner-directed hold: remaining bulk downloads wait for an outcome-blind coverage pilot and predeclared confidence-bound gate.** Executor and analysis repairs continue in parallel.

This is a readable status mirror, not purchase authority or a second queue. The repo’s [current queue](https://github.com/maxzipperman/value-finder/blob/main/sharp-markets/docs/OCTOBER_2026_QUEUE.md), exact approvals and local spending ledgers control purchases. Update this document after each completed run, stop or verified analysis.

## Credit position

| Measure | Credits | Meaning |
|---|---:|---|
| Prepaid monthly allowance | 5,000,000 | Credits, not HTTP calls. No renewal authorized. |
| Recorded terminal charges, including the probe | 167,177 | Completed/missing ledger charges across the purchases below, plus the 1,687-credit probe. |
| Certified missing older request | 30 | Now included in recorded charges; lagged response retained, reservation preserved, never resent. |
| Known purchase charges including that observed response | 167,177 | Excludes live/other account usage that is not individually itemized here. |
| Conservative cumulative budget debit | **170,306** | Includes retained reservations and carried other usage. Use this higher figure for planning; it is not an additional charge. |
| Last observed provider balance | 4,832,809 | From the stopped request’s headers. Historical evidence, **not a current balance check**. |
| Protected account reserve | 531,630 | Must remain available under the existing plan. |
| Monthly spending ceiling | 4,440,000 | Existing ceiling; exact future caps still need review. |

Recorded charges reconcile to: probe 1,687 + recent football 82,830 + NFL alternates 34,140 + NFL props 34,090 + older responses 14,430 = 167,177. The older total includes one charged response certified missing. Conservative reservations are not double-counted as extra purchases.

## Downloaded data

| Dataset | What is on disk | Charges so far | Analysis state |
|---|---|---:|---|
| Acquisition probe | Completed; reused responses preserved | 1,687 | Acquisition/coverage diagnostics complete; do not repurchase. |
| Recent football featured odds, 2023–2025 | 2,761 new requests: 2,760 valid, one explicitly missing; 12 reused probe responses | 82,830 | Identity/timing reader repairs exist. Price-engine registration/eligibility still blocks new strategy grading. |
| NFL alternate spreads/totals | Complete union: 1,773 slots, 1,707 valid and 66 explicitly missing responses; 1,774 linked opportunities | 34,140 | Pilot paired-curve coverage checked. Acquisition completeness is not an ROI or execution result. |
| NFL 2025 props, six markets | 570 completed requests at day-before/close slots | 34,090 | Coverage inventory complete; 564 requests contain all six markets at some book. Per-player paired coverage and grading remain unfinished. |
| Older football featured odds, 2020–2022 | 480 completed new responses; one charged lagged response retained as certified missing. Original scope also reuses 12 probe responses. | 14,430 recorded | Offline recovery installed under exact approval; 1,786 original requests remain untouched. |
| Historical weather forecasts | Existing NWS MOS and Open-Meteo caches; coverage audit complete | 0 Odds API credits | Most known outdoor games support 24–48-hour MOS replay under the assumed publication delay. Exact 72-hour inputs need a longer-range archive. |
| NBA sample supporting data | Free Kalshi cache for 112 markets / 259,778 price minutes, per preparation report | 0 in this stage | Paid NBA sample odds not yet acquired; no sample strategy results verified. |

“Missing” remains in the denominator. Available quotes are not confirmed fills, limits or first-play timing. Schedule-based weather coverage is not the same as provider-offered betting coverage.

## Planned additional credits

Amounts below are **maximum new credits or planning bounds**, not amounts already spent. Only an exact reviewed list and active hub approval permits a run.

| Next work | Maximum new credits | Readiness / dependency |
| Cache-only coverage audit and sampling protocol | **0** | Underway. Define usable paired coverage, representative samples, confidence bounds, cost/yield and pass/skip criteria before bulk purchases. |
| Small gap-filling coverage pilot | **To be frozen** | Reuse existing evidence first. Exact finite sample and cap require review; pilot inputs should be reused by the final archive. |
|---|---:|---|
| Finish older 2020–2022 football | **53,580** | 1,786 never-sent requests. PR #129 merged; exact offline reconciliation installed. Actual successor frozen in PR #134; independent review, new coverage gate and fresh paid approval remain. |
| NFL/CFB listing discovery | **1,544** | Exact first metadata stage in PR #132. Auditor reproduced cache/ancestry validation blockers; worker repairing them. Also waits on representative coverage measurement and the approved global predecessor. |
| NFL/CFB market availability at two times | **7,032 currently proposed** | Full stage held for coverage-first planning; separate metadata stage after pilot/listing reconciliation. Newly discovered events can expand this list and cap. Returns availability, not prices/player counts. |
| All supported NFL/CFB props, 2023–2025, day-before + scheduled close | **2,747,340 planning bound** | NFL 1,011,870 + CFB 1,735,470, after compatible prior-cache reuse, up to ten selected books. Actual billing depends on returned markets. Exact universe, books and price list follow discovery. |
| Optional earlier timing: eight core markets at 72/48/6/1 hours | **1,112,960 planning bound** | Keeps broad baseline and adds timing depth. Requires coverage and settlement support; extra early-time metadata and new events are not included. Weather-dependent T72 tests need archived forecasts. |
| NBA January 5–11, 2026 sample odds | **7,540** | 754 requests. Needs completed older successor ancestry, reviewed driver and exact approval. This NBA sample is separately unsealed. |
| Qualifying MLB/soccer heat-game closes | **16,000 ceiling** | Free venue/forecast qualification first; buy only the exact deduplicated qualifying list. |

**Illustrative broad-plus-depth plan:** 170,306 carried debit + 53,580 older + 8,576 two-stage metadata + 2,747,340 broad props + 1,112,960 optional depth + 7,540 NBA + 16,000 heat = **4,116,302 credits**. This leaves 883,698 of the nominal allowance, including the protected reserve. It excludes extra early-time metadata, new event listings and subsequent live/other usage; it is not a final approval or billing forecast.

The existing **250,000-credit first-tranche ceiling** must be prospectively extended through a reviewed budget before a larger props run. Small stages do not authorize that extension. Twenty-book broad coverage has a 5,528,880-credit bound; all markets at all six times has an 8,260,260-credit bound. Neither fits this month at those maxima.

Conditional NBA full-season and hourly featured-football purchases remain behind their existing gates and are **not included** above. If earned, rebalance against actual remaining credits and overlaps before purchase. Reset date is not yet confirmed; do not assume calendar month-end.

## Coverage gate before bulk acquisition

Owner requested this on October 2. Test coverage without viewing outcomes or choosing profitable games. Existing cached inputs come first; a finite random/stratified pilot fills unmeasured sport/year/time cells. Count independent games or request/day clusters, not books, players and snapshots as separate independent successes. Use a predeclared lower confidence bound against a useful coverage threshold and report credits per usable paired game. Metadata presence is insufficient to establish complete paired prices, freshness or settlement support. Unknown, cancelled, unmatched and unsupported cases remain visible.

The existing 480 older responses are a chronological sample; the 570 props responses cover only NFL 2025. Neither by itself establishes representative coverage of the remaining archive. A small pilot is the measurement step; its exact list and maximum cost still require approval. Full stages above remain held pending this gate. Confidence on coverage does not prove a betting edge.

## Analyzed versus prepared

| Work | Verified status | What remains |
|---|---|---|
| Earlier weather studies and strategy screens | Existing write-ups report completed observed-weather, NWS MOS and limited Open-Meteo retrospective tests | They do not establish an executable edge for the newly acquired archive. |
| Forecast source/coverage audit | Completed, outcome-blind; government, GitHub and academic alternatives identified | Join forecasts to exact odds decision times; verify source availability/latency and venue mapping. |
| Forecast revisions / offensive style | Six specifications and outcome-blind input preflight prepared | No reproducibly verified historical fit in this status document; keep discovery separate from confirmation. |
| New featured-odds price-engine tests | Reader/registration work partly prepared | Complete registered eligibility and timing amendments before grading. |
| New props tests, pooled 2023–2025 | Acquisition scope approved by owner; cached coverage inspected | Bounded close-slot reader, primary-book selection, settlement mappings, correct over/under grading and missing-stat handling. Report NFL/CFB and markets separately as well as pooled years. |
| Live weather rules | Four daily collections running; provenance links checked | Forward test remains paper research. No hourly or near-kickoff weather collector verified. |

## Remaining work and owner

1. **Hub:** PR #129 review and exact offline transition are complete; actual successor is frozen in PR #134. Validate representative coverage before bulk execution, then execute only untouched requests. Retain the charged missing request and its reservation.
2. **Worker → auditor → hub:** repair/review PR #132’s missing-cache and uncertified-partial acceptance. First freeze a small stratified coverage pilot; full discovery follows only when useful coverage/cost is supported. Reconcile events and freeze each subsequent finite list.
3. **Worker → auditor → hub:** correct college forecast missingness. Reproduced bug: partial wind is accepted and entirely missing precipitation becomes zero. Preserve complete-input behavior; no retroactive rule changes or live deployment yet.
4. **Auditor as implementation worker → independent reviewer → hub:** repair props analysis inputs and settlement. Missing statistics must stay missing, not become zero; over-only/yes-no markets must not acquire invented under sides.
5. **Hub:** preregister the acquisition coverage gate, then choose the exact incremental broad/depth price list using measured paired availability, confidence bounds, settlement support, cache reuse and budget. Extra snapshots are correlated observations, not extra independent games.
6. **Hub:** confirm allowance reset date and update this artifact after each run or verified analysis. Keep 2026 football outcomes sealed, requests cache-first and purchases sequential.

## Evidence and links

- [Older recovery PR #129](https://github.com/maxzipperman/value-finder/pull/129)
- [Props discovery and cost PR #132](https://github.com/maxzipperman/value-finder/pull/132)
- [NBA preparation PR #128](https://github.com/maxzipperman/value-finder/pull/128)
- [Forecast coverage report](/private/tmp/value-finder-forecast-coverage-review-2026-10-02.md)
- Local ledger inventory and pending-response hash checked October 2; original stopped bytes preserved by the exact certified transition. Saved test artifacts are reused only when source, environment and command bindings match.
