# Review of the historical-odds first tranche and the expanded-lab evidence

*September 30, 2026. Read-only review by the hub's reviewer chat. No API call, no download, no credential read, no rule or job changed. This file is untracked; the hub decides whether it is committed.*

Material read: the research-lab folder (`odds-pull-plan.md`, `threshold-review.md`, `simulation-results.md`, `protocol.json`, `simulation_protocol.json`, `simulate.py`, `runner.py`, the vendored loader, both `runs/` trees), PR 96's branch (`REGISTRATION.md`, `timing.json`), and in the repo: `STATUS.md`, both `STRATEGY.md`, `nfl-weather/PREREGISTRATION.md`, `strategy-research/odds-api-credits.md`, `strategy-research/plan-review-2026-09-28.md`, `sharp-markets/config/odds5m.yaml`, `sharp-markets/src/markets/oddsapi/bulk.py`, `sharp-markets/docs/ODDS5M_DAY_ONE.md`, `sharp-markets/docs/PRICE_ENGINE_PREREGISTRATION.md`, and the processed replay tables.

## Verdict

Buy the core (step 2, F1 restricted to 2020–25) and the decision-slot totals (step 3), but not as written. Step 3 is 77% redundant with step 2, the probe as capped cannot build the schedules the puller needs, and the single 19:30 Pacific slot prices a rule that is not the one being forward-tested. The simulation does not show the thresholds are conservative in general; its null is more benign than the data, and its calibrated maximum-t threshold is unsafe outside that null. The 23 forecast-revision comparisons already failed at the scoring level, so no price data can rescue that family; the only live weather question the purchase can answer is whether the plain wind effect survives at an entry price, and that costs under 10K credits, not 40K.

## Independently verified findings

| # | Finding | Evidence |
|---|---|---|
| V1 | The weather schedule's 2,958 requests reproduce exactly from the processed replay tables: 665 decision slots (NFL 300, CFB 365) plus 2,293 closes (NFL 579, CFB 1,714). | Recomputed from `mos_replay.parquet`, 2020–25, with the plan's slot and close definitions. |
| V2 | Every one of the 2,293 close requests is at the same time F1 requests (both use the last 5-minute grid point at least 5 minutes before kickoff, `bulk.close_time`). Only the 665 decision slots are new. Windy-only (forecast ≥ 15 mph) decision slots: 209. | `bulk.py` lines 153–176; recount above. |
| V3 | F1's daily grid is 16:00 UTC. The decision slot sits 10.5–11.5 hours after the previous F1 snapshot, every time. Reusing the F1 snapshot as the entry would price the bet before the forecast run the decision uses was published. | `DAILY_HOUR = 16` in `bulk.py`; gap distribution computed. |
| V4 | 19:30 Pacific is 02:30 UTC in daylight time and 03:30 UTC in standard time. The live alerts run at about 02:30 UTC. So the MOS replay's slot and one of the four live alert slots coincide from September to early November and differ by an hour afterwards. | `odds-api-credits.md` line 235; `decision_time` in the vendored loader. |
| V5 | There is no historical Odds API cache on disk. The `oddsapi/live` folders hold 21 files (about 2 MB) of live alert responses since Sep 28; `sharp-markets/data/raw` holds Kalshi and Kaggle data only. Step 0 saves nothing on the historical side; its value is the request plan and the semantic dedup (totals inside three-market responses, which have a different cache key). | Directory listings. |
| V6 | The pilot plan file the plan cites (`historical-totals-pilot-plan.json`) is not on this Mac under `~/.codex` or `~/code`. The number it produced reproduces, but no frozen request list exists as an artifact. | `find` over both trees. |
| V7 | The repo's probe is about 10,700 credits (about 10,400 one-credit `/events` sweeps across all sports). The plan caps probes at 1,000. The puller's `plan_calls` needs saved schedules from those sweeps, so under the 1,000 cap F1 cannot be planned unless the sweeps are limited to the two football sports (roughly 1,000 sweeps at two-day spacing over six seasons). | `ODDS5M_DAY_ONE.md` lines 116–126; `bulk.plan_calls`. |
| V8 | The actual spread of the target (final total minus close) is 13.3 points NFL (12.9 for 2020–25) and 16.3 CFB (15.9). The simulation uses 10. Its power is overstated: a "1-point" effect at noise 10 is about 0.75 points NFL and 0.6 points CFB in real noise. | Computed from the replay tables; `noise_scale_points` in `simulation_protocol.json`. |
| V9 | A 1-point effect per standard deviation of forecast revision (2.0 mph NFL, 1.6 mph CFB) is about the size of the entire wind effect: the mean target at 15–20 mph is −1.48 (NFL) and −0.59 (CFB), and at 20+ mph −1.62 and −1.89. The realistic revision effect, if any, is a fraction of that, where every method's power is near its null rate. | Computed from the replay tables. |
| V10 | Under the simulation's null, Holm, BH and Bonferroni select anything in 0.00–0.10% of searches against a nominal 5%, and the calibrated maximum-t 95th percentile is 1.63–1.68, while the symmetric sign-flip diagnostic on the real data gives 3.04. The t statistics are shifted negative under the null because every candidate nests its control and adds pure-noise features, so out-of-sample it is almost always slightly worse. | `threshold_comparison.csv`, the three `*_calibration.json`, `selection_diagnostic.json`, `simulate.py` lines 18–45 and 70–85. |
| V11 | The three noise regimes barely differ for paired comparisons because day and season noise hit control and candidate identically and cancel in the paired loss difference. The regimes do not test the dependence that matters here. | `synthetic_targets` and `refit_statistics` in `simulate.py`; the CSV. |
| V12 | The 7.0% maximum-t rate (independent regime) is about three standard errors from 5% given 2,000 calibration and 2,000 evaluation draws; the three regimes average 5.8%. Not adopting it was right, but the real problem is V10: the threshold is tied to this null. | Wilson intervals in the CSV. |
| V13 | The whole 30,000-search simulation ran in 25 seconds and the 26-model batch in 10 seconds. Compute was not the constraint on any of this evidence. | `simulation_manifest.json`, `manifest.json`. |
| V14 | The lab's batch found no scoring improvement from forecast revisions, persistence, crossings, curvature or style interactions (23 comparisons, best raw p 0.047, most point estimates negative). | `leaderboard.csv`. |
| V15 | NFL closing totals already exist free for every season (nflverse `total_line`, SBR open/close 2007–21), and CFB consensus closes exist from cfbfastR. F1's scarce content is per-book prices, Pinnacle specifically, spreads and moneylines by book, and the daily path. | Replay table columns; `sbr_open_close.parquet`. |
| V16 | The live Rule B uses Open-Meteo forecasts, a 1–3 day window, four alert times and Pinnacle at −115 or better. The replay uses NWS MOS at one slot the evening before, with no price. The historical test and the forward test are different procedures. | `nfl-weather/STRATEGY.md`, `PREREGISTRATION.md` amendment 1, the vendored loader. |

## Assumptions and unverified claims

- Snapshot cadence (10 minutes from June 2020, 5 minutes from September 2022) and the "nearest at or before" rule are the plan's claims. They match my understanding of The Odds API's documentation; I did not contact the API or the docs.
- Pinnacle's presence in 2020–21 historical NFL and CFB snapshots is unverified. Pinnacle historically sat in the EU region of this feed; `bookmakers=` works regardless, but presence per season must be probed before F1's 2020–22 slice.
- Book coverage by season is uneven by construction: Fanatics and ESPN BET did not exist before 2023 and Caesars changed brand in 2021. The 2020–22 slice will have fewer retail books per snapshot.
- The hub's global variant ledger (STATUS says 271 at Sep 29 plus later additions; PR 96 says 294 at PR 94) was not reconciled here. The lab's 314 is a floor, as it says.

## Revised first tranche (ranked)

| Order | What | Credits (estimate) | Why this order |
|---|---|---:|---|
| 0 | Freeze the protocol and the exact request list (below), commit them with hashes. | 0 | Nothing is bought before the list exists in git. |
| 1 | Probe, football only: `/events` sweeps for NFL and NCAAF 2020–25; one featured close and one 16:00 UTC snapshot per sport per season at `us10` and all three markets; the four billing checks. Read: Pinnacle present, books returned, snapshot lag, `last_update` ages, billing headers. | 1,000–2,000 | Settles coverage, billing and the 2020–21 Pinnacle question before anything large. The repo's full probe (all sports, 10,700) is deferred to the day the other sports are bought. |
| 2a | F1, 2023–25 only, both sports, three markets, `us10`. | 60,000–75,000 | The 5-minute era, full retail book set, same era as F2/F3. Enough to run the price-engine backtest and H16b as registered. History does not expire. |
| 2b | F1, 2020–22, both sports, after 2a's coverage report and only if Pinnacle is present in the 2020–21 probes. | 55,000–70,000 | Lower information per credit (10-minute snapshots, fewer books, the 2020 season). |
| 3 | Decision-slot totals, all three markets, at the 02:30 UTC alert grid for the three evenings before each football game date, 2020–25, plus the 19:30 Pacific slot where it differs (standard time). Union across games. | 15,000–25,000 at 30 credits; 5,000–8,000 totals-only | Prices both the MOS replay's decision and the live rule's entries. The close half of the old step 3 is dropped (V2). |
| 4 | Contingency. | 10,000 | Retries and the alarm margin. |
| | Total ceiling | about 170,000 | Under the proposed 250,000. |

Removed: the 2,293 close requests inside step 3 (22,930 credits, duplicated by F1). Deferred unchanged: F2, F3a, the NBA week, heat closes (they are the repo's day-one items, not this tranche's), F4, N1, and the other sports' sweeps. Sample rather than buy: a windy-day hourly pull (below) instead of F4.

## Questions 1–3: purchase, coverage, validation

**Is this the best first purchase?** Nearly. F1 is the right core and the decision-slot pull is the one weather item that pays, but at roughly a fifth of its cap. The best information per credit is the 2023–25 F1 slice plus the slot pull: together they let the price-engine backtest, H16b, the Rule B and Rule HT re-grades at Pinnacle's close, and the decision-slot CLV test all run on about 90K credits.

**Are daily snapshots too coarse?** For the level questions, no. For the two strongest timing hypotheses, yes: soft-book lag after a forecast update (minutes to hours) and the market's absorption of a new forecast run. The right instrument is not F4 (1.44M) but a targeted pull: hourly featured snapshots on the 209 windy decision dates only, from 03:00 UTC through the last close of that date, about 7,500 snapshot-hours, so 75,000 credits totals-only or 225,000 at three markets. Gate it on the decision-slot test showing positive CLV with the interval clear of zero.

**Deduplication and validation.** Cache keys are exact on parameters, so a totals-only request does not hit a three-market response: the plan must dedup semantically (same sport, same requested time, requested markets a subset of a cached response's) before the request list is frozen, and the manifest row for a reused response must say which call it served. Validate on the probe and again after each slice: (a) returned snapshot timestamp minus requested time, by era, with a hard limit (10 minutes before Sep 2022, 5 after) and anything larger logged; (b) per-book `last_update` age at the decision slot, with an entry-eligibility rule written down (I suggest Pinnacle within 60 minutes at the slot, retail books within 3 hours, else "stale, counted"); (c) game matching by alias table and kickoff within 90 minutes, with every unmatched feed event and every unmatched schedule game listed by reason; (d) postponements: the schedule's `commence_time` is the latest sighting before kickoff, so any game whose feed kickoff differs from nflverse or cfbfastR by more than 2 hours is flagged and its close taken at the final kickoff only, and a move of more than 24 hours is void as the amendments already say; (e) a close is valid only if the snapshot timestamp is before the game's final kickoff and the game is still listed as upcoming; (f) settlement from the processed tables only, with no-score games kept for CLV and excluded from ROI with a reason.

## Question 4: hypotheses worth testing

Ranked by mechanism strength, then cost. "Count" is the expected sample in 2020–25.

| Rank | Hypothesis | Mechanism | Data | Extra credits | Count | Falsified when |
|---|---|---|---|---:|---|---|
| 1 | Rule B entry CLV at the decision slot (both sports), Pinnacle to Pinnacle's close, and best-of-10 to Pinnacle's close | The forecast exists at 19:30 PT; if the close moves toward wind afterwards the slot captures it | Step 3 + F1 | in tranche | 145 NFL, 306 CFB windy games | Mean CLV < 0.25 points or interval touches zero, either sport |
| 2 | Price engine H1/H2 as registered | Soft books lag the sharp fair price | F1 | in tranche | hundreds of flags per market | As registered |
| 3 | Overnight stale retail quotes at 02:30 UTC: retail total a point or more off Pinnacle with `last_update` older than Pinnacle's | Books don't re-price overnight | Step 3 | 0 beyond step 3 | unknown; the slot pull measures it | CLV to the retail book's own close ≤ 0 |
| 4 | Market absorption of the forecast: does the open-to-slot move already carry the wind discount, or does slot-to-close carry it? | Separates "market knew" from "market learned" | F1 + step 3 + the MOS archive | 0 | 451 windy games | Slot-to-close move for windy games is not more negative than for calm games |
| 5 | H16b daily reversal as registered | Over-reaction | F1 | 0 | thousands of game-days | As registered |
| 6 | Rule HT re-grade at Pinnacle's close and at best retail under | The consensus close may not be a bettable price | F1 | 0 | 653 games | Win rate at the prices taken below break-even |
| 7 | Windy-day hourly: when inside the final 36 hours does Pinnacle move on wind, and do retail books follow within the hour? | Timing of information arrival | Targeted hourly pull | 75K–225K | 209 dates | No systematic retail lag after Pinnacle moves |
| 8 | Kicker props in wind and cold (F3a) | Direct physical mechanism | F3a | repo day-one | about 180 lines | As registered |

Free, existing data only, no purchase: (i) a residual-bootstrap null for the 23-comparison family (Question 5); (ii) wind-coefficient drift by era, since the 20+ mph bucket has decayed (the Sep 28 review's "expect decay"); (iii) Kalshi 2025 NFL totals versus the nflverse close around forecast updates (H4a data already on disk). None of these establishes an edge; (i) decides what the batch's nulls mean.

Not worth buying for the weather question: more forecast-revision variants. The scoring-level test already failed across 23 specifications. A price edge from a feature that carries no scoring information would have to come from market over-reaction, which is a different hypothesis (rank 4 and 5 test it).

## Question 5: where compute helps

1. **A realistic null, not a pure-noise null.** Keep the real target and the real wind, and destroy only the candidate information: permute forecast revision (and style) within season-week strata, or replace it with a placebo (a different stadium's revision the same day). Refit the whole 26-model search per draw. This keeps heteroskedasticity, era drift and the nested-model penalty as they are in the data and gives an honest family-wise threshold. It costs minutes.
2. **Residual bootstrap by game day and season** with the real residual distribution (13.3 and 16.3 points), to replace the 10-point assumption and re-derive power at 0.25, 0.5 and 0.75 points.
3. **Nested chronological validation** for the ridge penalty and feature set, so the penalty of 10 is chosen inside each fold rather than fixed, and the leaderboard's "best variant" is compared against a selection-aware baseline.
4. **Execution stress** once F1 exists: fill at the next snapshot after the signal, at the worse of the two best books, at −115 instead of the posted price, with a 20% random no-fill, and report CLV under each.
5. **Full-search false positive rate for the price engine's 38 variants** by resampling game days of F1 before any result is read, so its bar is calibrated on its own dependence.

## Questions 6 and 7: significance policy and the simulation

**The simulation's verdict.** It is well built (hash-pinned, chronological, cached design matrices verified equal to independent fits, sealed data excluded at the reader) and honestly described. But it does not demonstrate conservative thresholds. Its null adds features with no information to a correctly specified baseline, so the candidate can only lose out of sample and positive false discoveries are nearly impossible (V10). In real data the baseline is misspecified (the wind effect is nonlinear and drifts by era, residual variance differs by wind), and a candidate feature correlated with that misspecification will "improve" MSE without exploitable information. Those are the false positives that matter, and this null cannot produce them. Consequently: the Holm and BH null rates of 0.05% are not evidence those methods are conservative here; the calibrated maximum-t threshold of about 1.67 is dangerously low for anything but this null; and the power figures are optimistic for two reasons (V8, V9). The one robust conclusion is that a global Bonferroni over 314 heterogeneous specifications has essentially no power at plausible effect sizes.

**Recommended policy, prospective only.** Three standards, written into each project's registration before its next study:

- *Discovery.* Each study names its family in advance and lists every specification before outcomes are read, as the lab did. Shortlist with BH at q = 0.10 inside that family, calibrated by the realistic-null refit above rather than by uniform p-values, and report effect size, the share of seasons with the right sign, and the leave-one-season-out minimum. The global count stays as a reporting fact beside every result, never as the test.
- *Confirmation.* At most three candidates per family, direction fixed, one look, on data no discovery study has touched: a sealed season or the forward test. Holm at α = 0.05 over that confirmation family. Each sealed season is consumed by the family that reads it; a second family reading the same season budgets its alpha with the first. Repeated looks are forbidden except where a registration already defines them (the forward tests' fixed horizons).
- *Economic.* Decision-time prices, CLV at least 0.25 points with the wider of the plain and game-day-clustered intervals above zero, ROI after vig at the price taken, survival of the staleness filter and of dropping any single book or season.

Do not re-score the current batch under any of these. It failed its own bar and would fail these too (best raw p 0.047 against 23).

## Question 8: what to freeze before any download

Commit, with SHA-256 hashes recorded in the pull's manifest:

1. The request list itself: one row per call with sport, endpoint, requested time, markets, book list, planned credits, and the cache key; and a dedup table mapping each reused call to the cached response that serves it.
2. The schedule used to generate it, with the slot and close definitions quoted (02:30 UTC grid for the three evenings before each game date in both sports; 19:30 Pacific added where it differs; close at the last 5-minute point at least 5 minutes before the final kickoff).
3. Season windows and the sealed list, unchanged from `odds5m.yaml`.
4. Entry eligibility: book, maximum `last_update` age, maximum snapshot lag, price cap (−115), and what happens to a game with no eligible quote (counted, excluded, listed).
5. Matching: the alias table version, the kickoff tolerance, the postponement rule, and the void rule.
6. Close selection and settlement sources, and the CLV conversion (the registered pricing model for totals; the margin table for spreads).
7. The hypothesis list with the direction, metric, sample, and act/drop criterion for each (ranks 1–6 above), and its variant count added to the global ledger.
8. The order of slices (probe, F1 2023–25, step 3, F1 2020–22) with each slice's `--max-credits` and the stop conditions, and the rule that no analysis joins outcomes to prices until the slice's coverage report is written.

## Decisions needed from the owner

1. Re-scope step 3 to the alert grid plus the differing standard-time slot, all three markets, and drop its close half (saves about 23K; costs about 15–25K instead of 40K).
2. Split F1 into 2023–25 first and 2020–22 second, the second conditional on the probe's Pinnacle coverage. Or buy all six seasons at once as planned.
3. Allow the probe to run football-only `/events` sweeps now (1–2K) and defer the other sports' sweeps, or raise this tranche's probe cap to the repo's 11K.
4. Adopt the three-standard significance policy prospectively, starting with the price-engine and decision-slot analyses, and have the realistic-null refit run (zero credits) before any F1 result is read.
5. Whether the windy-day hourly pull (75K–225K) is written into the gated list now, behind rank 1's result, or left for March.

## Candour on the odds of an actionable edge

The data are worth buying because they settle the entry-price question for the weather rules cheaply and make the price engine testable. They are unlikely to reveal a new, large edge. The plain wind effect is about 1.5 points against the NFL close at 15 mph and above, less in college, and it has been shrinking; the forward tests' own rehearsal says a losing season is common even with a real edge. The forecast-revision family is dead at the scoring level. The realistic prize is a procedure with positive but small CLV, limited by fillability nobody can see in this feed.

---

## Addendum, October 1, 2026 (UTC): the football probe and the candidate archive list

Read-only review of `research-lab/acquisition/football-probe-v1` and `football-archive-candidate-v1`, plus the three new lab scripts and `odds-pull-plan-revised.md`. No API call, no credential read.

**The probe is sound and its accounting reconciles.** 991 requests, 1,687 credits counted; the manifest's per-call bills sum to 1,687 (967 sweeps at 1, 24 price probes at 30); the balance header fell monotonically from 5,000,000 to 4,998,313; every call returned 200. The runner reused the repo's `BulkClient`, cache, key scrubbing and billing checks, held a process lock, and reserved each call's worst case in a durable ledger before sending it. No saved file contains the key. Bodies keep `timestamp`, `previous_timestamp` and `next_timestamp`, and headers keep the three `x-requests-*` fields. One stale label: `request-manifest.json` still says "prepared, not authorized and not executed".

**What the probe showed, as I read it.**

| Finding | Evidence |
|---|---|
| Pinnacle is present in every sampled season, but on the NFL evening slot in 2022–24 it prices about half the listed events (13–15 of 25–29). The other half are the following week's games, not yet posted. The daily grid will see those a day or two later. | Probe table, `book_event_counts`. |
| Fanatics does not exist before 2025 and ESPN BET not before 2023; BetMGM covers 13 of 27 NFL events in 2025. The ten-book panel is a 6-to-8-book panel in 2020–22. | Same. |
| Snapshot lag is 4.3–5.0 minutes at every requested time, so the provider's grid is offset from ours: a request at the 5-minute point before kickoff returns the snapshot about 10 minutes before kickoff. Fine, but the close should be labelled T−10 proxy, not T−5. | `returned_utc` versus `requested_utc`. |
| The summary's "quote updates 4.43–19.03 minutes old" measures age from the requested time, not from the returned snapshot. Relative to the snapshot the ages are 0–15 minutes. | `quote_age_minutes_min` equals the snapshot lag in every probe. |
| The sample is one early-October weekend per season. Nothing in November–January (standard time, the windy months, the playoffs) was sampled. | `request-list.csv`. |
| Schedules are complete in season. 34 event sweeps returned snapshots up to 7 days old, all after each season's last game, when the feed had nothing upcoming. No in-season gap. | Manifest `returned_ts` versus `requested_ts`. |
| Duplicate provider IDs are the season-long listing (first seen in late August or early September) and the week-of relisting of the same game; 203 of the 262 NFL groups and 105 of the 139 CFB groups differ in kickoff (flex moves and TBA times). The fix is a canonical key of team pair plus kickoff within 24 hours, keeping the latest-seen listing's kickoff. Only 19 candidate requests (570 credits) are driven solely by stale IDs, so the cost is small; the analysis risk (a "close" taken at a placeholder kickoff) is the real issue. | `_schedules/*.parquet`; `candidate-manifest.json`. |
| Canonical NFL games per season after that merge: 285–308 against nflverse's 285 (269 in 2020), so a few duplicates survive a same-UTC-date merge because the kickoff moved across midnight UTC. The 24-hour rule handles them. | Computed. |
| The 85 "unmatched" weather closes are two things: the replay's kickoff (nflverse or cfbfastR) differs from the provider's by 5 to 60 minutes (the provider's close is the right one), or the game is not in the feed at all (2020 FCS opponents such as Stephen F. Austin, Austin Peay, The Citadel). None needs a purchase; each needs a logged reason. | Joined the 85 times to `mos_replay` and the schedules. |
| CFB games that first appear in the feed less than 2 days before kickoff: 281 of 5,072 (181 under 1 day). Those have no 7-day daily path and must be counted as "late-listed", not as missing data. | Computed from `first_seen`. |

**The candidate list (5,290 requests, 144,940 new credits) matches the revised tranche I recommended** in structure: 2023–25 first (75,980), 2020–22 second (68,960), the 665 MOS slots as a labelled diagnostic, and 24 probe responses reused. Three differences to decide:

1. The MOS slots are totals-only at 10 credits (6,640). All three markets would cost 13,300 more and give the price engine a decision-time snapshot it otherwise lacks. I would pay it.
2. The slots follow 19:30 Pacific through the clock change, so 340 are at 02:30 UTC and 324 at 03:30 UTC. The 02:30 ones coincide with a live alert run; the 03:30 ones do not. If a live-rule replay is wanted later, its 02:30 UTC standard-time slots are a separate list of about 324 requests.
3. Nothing in the list serves the 1-to-3-day alert window of the live rule. The revised plan says so and defers it. Agreed, provided the deferral is written as a gate rather than left open.

**Before the bulk run, in this order:** merge duplicate IDs into canonical games and freeze the rule; resolve the 85 closes by reason; relabel the close as a T−10 proxy; decide the three items above; then re-freeze the request list and its hash. The outcome-blind coverage report after the 2023–25 slice should repeat the probe's book-presence table by month, not by one weekend, before 2020–22 is bought.

---

## Addendum 2, October 1, 2026 (UTC): audit of the frozen `football-archive-v2` bundle

Read-only. Validator run against the independently pinned root `954cd9cb…17c69`: passes. The 18 frozen tests pass (run from the lab's `tests/` folder, where they import from). The lab-root copies of `builder.py`, `validator.py`, `price_eligibility.py` and `protocol.json` are byte-identical to the bundle's. Cache keys for 300 sampled requests match the repo's `markets.cache.cache_key`. Credits reconcile: 5,024 requests, 5,000 paid at 30 (150,000) and 24 reused probe responses (0), split 82,410 for 2023–25 and 67,590 for 2020–22; plus the 1,687 probe, 151,687 of the 250,000 ceiling. All 665 MOS slots carry three markets (341 at 02:30 UTC, 324 at 03:30). No request time lies before June 6, 2020 or after February 8, 2026. All 85 original close groups and all 2,293 legacy closes have a logged reason.

### Blockers (cheap, fix before the recent slice)

**B1. Fifty-four games get a close request at a kickoff the provider had wrong, and no request at the right one.** `builder.py` lines 303–312 and the request loop take the close anchor from the last two-day sweep sighting before kickoff (`close_anchor_utc`), while `scheduled_utc` (nflverse or cfbfastR, the final kickoff) disagrees by more than 5 minutes for 54 canonical games (45 CFB, 9 NFL; 13 by more than an hour). Example: Notre Dame at Georgia, 2024 season, anchor `2025-01-02T01:45Z`, actual `2025-01-02T21:00Z` (the Sugar Bowl postponed on the morning of Jan 1; the last sweep was Jan 1, 05:55). The close is requested 19 hours early and `price_eligibility.evaluate` will reject it (`close_proxy_not_in_valid_pregame_window`), so these games have no usable close at all; for the 31 where the provider's time is later than the actual kickoff, the purchased snapshot may be in play. Smallest correction: for every game with `abs(schedule_discrepancy_minutes) > 5`, add a second close request at `snapshots(scheduled_utc)` (54 requests, 1,620 credits) and let eligibility pick whichever precedes both kickoffs. New version, new root.

**B2. The execution wrapper does not exist, and the freeze does not bind the code that will spend.** The root covers the protocol, requests, eligibility and builder, but not `sharp-markets/src/markets/oddsapi/bulk.py`, `markets/cache.py` or the wrapper itself. Before the run, the wrapper must: record the SHA-256 of `bulk.py`, `cache.py` and its own source in the run's manifest; verify the bundle root equals the pinned root; load the probe's ledger and start its cumulative count at 1,687; reserve each call's 30 credits durably before sending (the probe runner's pattern, `run_football_probe.py` lines 66–72 and 84–100); hold a process lock; refuse to run if a prior ledger shows `pending` or `stopped`; make zero automatic retries; stop on the protocol's `mandatory_halt` list; cap the run at the slice's figure (82,410) and the cumulative at 250,000; and refuse the 2020–22 slice until a coverage report file for 2023–25 exists with the fields `before_older_slice` names. Restart and the monthly credit reset must not reset any of this. Smallest correction: a wrapper that imports the frozen validator, then reuses `BulkClient` as the probe runner did, with those checks; no new fetching code.

### Not blockers, but should be stated in the bundle

- **NFL canonical games are played games.** Both nflverse files on the Mac (raw `games.csv` and processed `games.parquet`) carry 1,693 games for 2020–25 with no missing score; the cancelled Bills at Bengals game of January 2, 2023 is absent from the source itself, so it is absent from the external index, the canonical games and the request list (no Jan 2 03:30 UTC slot, no daily path). That is one game, but the protocol's `source_nfl_game_types` reads as a schedule, not a results table. State it, and count it as a void in any denominator that counts decision slots. Contingent playoff listings (the 2024 unmatched pairs such as Chargers at Ravens and Vikings at Rams, seen only in early January) are correctly excluded; they never occurred.
- **`unmatched-provider-ids.json` does not say whether the same pair and season became canonical through another ID.** Most of the 87 "pair exists" entries are stale duplicates whose kickoff differed by more than 24 hours (Colts at Vikings, 2024, seen once on Oct 23). Add a `canonical_game_id_via_other_provider_id` field so a reader can tell a lost game from a duplicate.
- **Postponement voids are not in the eligibility code.** The live amendments void a bet whose game moved more than 24 hours. `evaluate()` excludes an entry only when the decision is after the final kickoff. Add a `postponed_over_24h_void` reason computed from the as-of listing's kickoff versus the final kickoff, so the historical grade matches the live rule.
- **Home and away are swapped in 42 games' provider observations** (neutral sites). Team matching is unordered so the games are fine, but spread and moneyline sides must be joined by team name, never by home or away position. Say so in `ELIGIBILITY.md`.
- **`test_freeze.py` is not runnable in place.** It imports `freeze_football_archive`, `verify_football_freeze` and `football_price_eligibility` from its parent's parent. From inside the bundle that path is `acquisition/`, which has none of them. Either copy it with the bundle names or note where it runs.
- **Quote-age cutoffs (15 minutes at the snapshot, 25 at the decision) will exclude most retail quotes in the 2020–21 ten-minute era**, where the probe's observed ages ran 9.5 to 18 minutes from the requested time. That is a coverage fact to report by era, not a reason to loosen the rule after seeing prices.
- **Snapshot lag is allowed to 600 seconds** but the probe observed 4.3 to 5.0 minutes everywhere; a lag above 5 minutes in the run should be reported as a provider gap, not silently accepted.

### Reproduction of the 85

Of the 85 original groups: 34 are `canonical_provider_kickoff_revision` (the legacy time came from nflverse or cfbfastR's kickoff and the provider's anchor differs; the canonical close request is used, the legacy one is not bought), 48 are `provider_pair_absent_from_observed_sweeps` (mostly 2020 FCS opponents; absence from two-day sweeps, not proof the game was never offered, and the bundle labels it that way), 2 are `no_valid_pregame_listing`, 1 is a mixed group. None adds a purchase. The labels are correct; B1 above is the one case where "kickoff revision" means the canonical request is the wrong one, not the legacy one.

### Verdict

The recent slice is ready once B1 is added (a v3 bundle with 54 extra close requests, re-frozen and re-pinned) and the wrapper in B2 exists and has been rehearsed against the probe's cached responses with the network disabled. Nothing in the eligibility rules uses information from after the decision for inclusion; the one place future information enters (the final kickoff in the entry guard) only excludes, and the postponement note above makes that exclusion match the live rule. The 2020–22 slice stays behind the coverage report.

---

## Addendum 3, October 1, 2026 (UTC): review of the frozen `football-archive-v3` bundle

Read-only, on a scratch copy for anything executable. The original bundle still verifies afterwards.

**Verified.** Validator passes against the pinned root `d5c441c2…5e9a`, with the reused-cache check on. The 90 tests pass from a copy of the bundle with plugin autoload off, so portability is fixed. The executor's offline preflight passes with no key. The vendored market client (`bulk.py`, `cache.py`, `http.py`, `settings.py`, `sport.py`, `normalize.py`) is byte-identical to the repo's. The 24 reused responses are byte-identical to the probe's cache files. The runtime lock (Python 3.12.11 and eight pinned distributions) matches `sharp-markets/.venv` exactly, so that is the interpreter the live run must use. Credits: 5,052 requests, 5,028 paid, 82,830 recent and 68,010 older, 152,527 with the probe; 28 new alternate-close calls, 14 per slice, and 22 existing slots now carry the alternate purpose; the Sugar Bowl's alternate close at `2025-01-02T20:55Z` is present. All 665 MOS slots are three-market. The canonical games, aliases, exclusions and external index are inherited unchanged from v2 (the validator checks their hashes against the v2 root), and the opportunity registry keeps all 7,234 observed provider IDs with status, including the 350 unmatched, with other-ID links as annotations. The protocol now states that the NFL external index is played games. Sides join by team key or Over/Under. The 24-hour postponement void exists as a labelled paper status. `coverage_report.py` reads no scores; its "outcome" is the API's market outcome object.

**Eligibility repairs hold.** The two counterexamples from the fix plan (an entry decision after verified first play passing, and an arbitrary side passing) now fail: `test_after_first_play_entry_rejected`, `test_delayed_execution_crosses_play`, `test_source_market_side_validated`. Quotes bind to an immutable response hash, exact provider ID and canonical game; a caller cannot override source fields; simultaneous conflicting listings are quarantined; close selection ranks by time and freshness only. The final independent kickoff is still used as an exclusion guard at entry, labelled a retrospective safety check, which is the right compromise.

### Blocker

**B1. Billing reconciliation is exact-equality on a key other jobs may share, and the "documented reconciliation" the halts demand has no implementation.** `executor.py` line 72 hard-codes the baseline (used 1,687, remaining 4,998,313); line 107 halts unless the account check returns exactly those; line 139 halts on any call whose header deltas differ from its own bill by one credit. Three things make this fail in practice: the alert jobs (`com.nflweather.alerts`, `com.cfbweather.alerts`) run at 02:30, 14:30, 18:30 and 22:30 UTC and `com.valuefinder.closecapture` every 15 minutes, and if they are on the paid key any call during the roughly 12-minute run halts it with a stopped ledger; the provider's usage counter resets on the first of the month, which is today; and the repo's own puller already found the balance header can lag (`ODDS5M_DAY_ONE.md`, "Why the margin isn't smaller"), which exact equality cannot tolerate. `observe_headers` (line 129) already computes an external-usage attribution but `complete` ignores it. The halt messages say "requires documented reconciliation" (lines 77, 108, 140) but there is no input, file or command that performs one, so a halted run can only be restarted by editing the ledger by hand, which the design forbids. Smallest correction: (a) an `account-reconciliation.json` the executor accepts on `--confirm`, with the account's used and remaining at start, the reason, and the owner's note, hashed into `run-manifest.json`, replacing the hard-coded baseline; (b) in `complete`, attribute a positive external delta to `other_usage_reserved` (as `observe_headers` does) and halt only when cumulative external usage exceeds a written margin, say 100 credits, or when the delta is negative; (c) run on a morning with no kickoff inside the window, or have the hub pause the three launchd jobs for the run (its call, since they protect the forward tests). Without (a) the first run halts at the free account check if the counter has moved at all.

### Optional

- `test_v3.py` expects the probe ledger to total exactly 1,687; if the probe is ever re-run or repaired, the bundle must be re-frozen. Fine, but say so.
- `alarm_margin=0` is passed to `BulkClient` (line 245); with B1 fixed, set it to the probe-derived margin the day-one checklist asks for (A30), so the two accounting layers agree.
- The run manifest should record the interpreter path, not only versions, since two local venvs share Python 3.12.11.
- The 22 slots that were already requested and now also serve as alternate closes should appear in the coverage report with both purposes, so the "alternate" count the report prints matches 54 games, 50 slots.
- The authorization artifact the executor requires (`bundle_root_sha256`, `priority: 1`, `max_new_credits: 82830`, `human_authorization_evidence`) is not drafted anywhere. Draft it now so the go-ahead is a one-word confirmation of a file the owner has read.

### Verdict

The recent slice is ready to run once B1 is implemented and re-frozen (it changes `executor.py`, so a v4 root), the authorization artifact is written against that root, and the run is scheduled outside the alert and close-capture windows or with those jobs paused by the hub. Nothing else in the bundle needs to change before spending. The older slice stays behind the coverage report and a separate acceptance, as the protocol says.

Side note from the run logs read for this check: the CFB alert at 02:30 UTC on October 1 logged two signals. CFB Rule B is scored from October 1, so these may be the first graded signals.
