# Completed football cache: readiness before grading

**Cached quote diagnostics are available; registered grading is still blocked.**
This is a read-only acquired-data report, not another pilot gate look, draw,
confidence bound, book selection or profitability result. Original pilot final
hash is retained in provenance and unchanged. Owner-authorized local work uses
merged, source-pinned `slot_pairs`, `bind_asof`, timing guards and `saved_record`.
No outcome values, sealed2026 football, APIs, credentials, runtime writes,
registrations or jobs were accessed/changed. Statistical source files were opened
for schema names only, never rows, outcome missingness or participation counts.

## Scope and provenance

Successor151 root `c7d3ea3d938918735e3ec99f9b56652f67f4f200c93f233385b4d6429fbe1376`;
terminal ledger `58b3ee64c6320fb29989b7ae41f2866ae2f9102e9bbfed703b684625187f017c`.
Reuse hub completion: 1,288 completed / two missing, 65,880 billed / 66,480 reserved.
Diagnostic projection checks 2,525 designated ordinary receipt/raw records across
pinned current/predecessor roots, including all 1,290 current IDs. Each record's
hash, receipt and decoded raw binding is checked by the merged saved-record reader.
Ledger pins are rechecked after projection under a read-only shared lock.

Fixed denominators: **2,401 games**, comprising 2,116 passing-group frame identities
plus the separate 285-game NFL2025 census. Every missing/unbound older EARLY and
CLOSE remains a zero-coverage opportunity; no played-game or complete-case filter
silently removes it. The 440 sport/season/market/book/time rows and 1,854 slot-reason
records are in [readiness.json](readiness.json). Reasons are shared slot/response
flags, not mutually exclusive book-specific causal exclusions. A quote-age flag
may coexist with valid quotes at another book. Provider labels are identity proxies,
not roster-certified unique people. Raw quotes/player rows are not committed.

## Primary NFL close-proxy diagnostics

DraftKings is shown descriptively; it is not an activated book selection. Counts
are eligible same-response/book/label/point Over+Under quote pairs, before roster
matching and registered main-line/tie selection. Different families need not have
the same player. T24 intersections are separate descriptive fields and never a
prerequisite for an otherwise eligible close player-game.

| NFL season | Fixed games | Rush: games / provider-label player-games | Reception: games / provider-label player-games |
|---|---:|---:|---:|
| 2023 | 294 | 221 / 1109 | 222 / 2507 |
| 2024 | 308 | 215 / 1167 | 215 / 2506 |
| 2025 | 285 | 191 / 1057 | 192 / 2164 |

Pinnacle raw listing coverage reproduces the existing conditional 2025 note:
**1,291/1,789 rushing (72.16%)**, **2,670/3,785 receiving (70.54%)**. Both miss
80%, so the existing mechanical candidate remains DraftKings. This is raw listing
coverage across us10, not fresh paired-quote coverage; do not interchange them.
The dated [registration note](../../nfl-weather/PREREGISTRATION_PROPS.md#8-dated-notes)
already calls this pending, not active. Later-season coverage cannot reselect it.
A missing/not-requested book is not proof that it was never offered. The requested
book count describes projected records only, not every original planned request.

## Acquired older totals

A paired game requires the same domestic book at EARLY and CLOSE and Pinnacle at
both. The stricter column requires all four quote sets at the same point.

| Group | Fixed games | Paired domestic + reference | Same-point four-set games |
|---|---:|---:|---:|
| ncaaf 2020 | 653 | 457 | 76 |
| nfl 2020 | 285 | 252 | 52 |
| nfl 2021 | 291 | 282 | 99 |
| nfl 2022 | 285 | 276 | 107 |

Thus **1,267** games support quote-feasibility pairing, but only **334** meet the
same-point diagnostic. Simulation must explicitly handle changing total lines;
comparing prices at different points as if they were the same bet is invalid.
This is not renewed utility-gate acceptance or permission to grade.
CFB2021/22 totals and CFB2023–25 props remain held; no quote measurement here
releases them or extrapolates the passing NFL/CFB2020 evidence to those cohorts.

## Clocks, freshness and execution limits

All timing remains **scheduled proxy**, with no independent first-play certificate
or actual fill. Both provider and independent schedule clocks are checked.
52 bound slot clocks differ by more than five minutes; they are not silently
replaced. Snapshot/event orientation, as-of binding, and both kickoff restrictions
remain those of the reviewed classifier.

All 4,362 measured game-slot snapshot ages were 0–600 seconds. Of 112,486
measured event/market-clock occurrences, **19,972 market updates were after the
returned snapshot** (but before the decision), and **111 were more than 900
seconds old relative to snapshot**. No quote-clock semantics or thresholds were
relaxed. This distinguishes a future-relative-snapshot timestamp from an old
quote; both can fail the existing reader. Shared responses serving different
fixed game slots create distinct clock observations, not additional independent
trials. Missing quote clocks in the measured observations: zero.

Clock-only 30/120-second hypothetical delays leave 10 of 4,392 bound slots not
strictly pregame; a 300-second delay leaves 1,344 not strictly pregame. These are
schedule-clock stresses, not executable quote/fill tests or conditional win rates.
Actual live trigger and forecast vintages remain separate prerequisites for weather
simulations: observed wind cannot replace the forecast available at entry.

## Concrete grading blockers and smallest next work

1. **Bought T10 vs registered T5.** `bulk.close_time` chooses the last grid at least
   five minutes before kickoff; the archive planner chooses T−10. The measured
   NFL2025 census is also T−10, so it is not exempt. Preserve the existing
   [draft amendment](../../sharp-markets/docs/props-archive/AMENDMENT-DRAFT.md);
   hub must review/adopt the prospective timing/unknown-stat clarification before
   activating its book note or joining outcomes. Do not silently relabel T10 as
   the registered close or buy replacement snapshots without separate authority.
2. **Book/count prerequisites.** The actual registration reader reports no active
   dated book entry and an unfilled count-at-registration header (runtime count
   294). Resolve scope/effective-date differences (historical271, running294,
   possible searchfloor314) prospectively; do not guess a smaller threshold.
3. **Identity/settlement.** NFL rush/reception stat columns exist in the source
   schema. Passing/kicking/receptions mappings also have their declared columns;
   no availability/participation/null rate was measured. Roster linkage, exact
   player-game identity, participation, book terms and registered main-line/tie
   selection still need reviewed work. CFB player settlement remains unsupported.
   NFL/CFB total-score columns exist, but actual matching, overtime/void terms and
   first-play timing remain unverified. Schema presence is not grading authority.
4. **Price-engine adoption.** Amendments2/3 are still drafts and `REGISTERED_ROOT`
   is None in the merged handoff. A registered, bounded eligible reader is required
   before realized results/CLV are graded. No outcome command was invoked here.

Next: independent worker checks these prerequisites/source-bound artifacts; hub
adopts any required prospective registration changes. Then build only the
registered eligible analysis population, report every exclusion and execution
stress, and keep2026 sealed. No new purchase is recommended by this report.

## Reproduce

From this isolated checkout, use the existing Python3.12.11 football environment
with `-B` and run `diagnostic.py`, redirecting stdout to a new local artifact. Its
fixed sources are the retained approved Mac captures/runtime; it never fetches or
writes there. `verification.json` covers the focused synthetic and measured-artifact
invariants. [Saved test evidence](test-evidence.json) is separate from native cache
measurement provenance; no unchanged broad acquisition suites were repeated.
