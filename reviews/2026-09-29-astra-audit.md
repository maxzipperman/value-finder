# Independent forward-test audit — 2026-09-29

Audited local commit **`0aba1e2292c9ca23736f6e6ddf25b20c102bca24`** (PR #48), with a clean working tree. Ledger snapshot: **2026-09-29 04:02 UTC / Sep 28, 9:02 PM Pacific**. There were **102 NFL and 238 CFB data rows**, not counting headers, and **zero Rule B or HT signals**. References below are relative to `/Users/maxzipperman/code/value-finder/` at that commit. This is an independent reading of the contracts, code, data and Git history.

## 1. Verdict

**I would not certify that these forward tests do exactly what their registrations say:** the advertised line-sensitive EV gate is ineffective, HT notification timing differs from its scored entry, and the scorers do not enforce the registered evaluation populations or decisions. Several important pieces are correct, including the price ceiling, frozen historical season bounds, entry-price outcome grading, descriptive captured-close separation, and HT’s unchanged 2026 threshold after PR #48. No affected Rule B/HT signal or outcome appears in the inspected ledgers, so there is still an opportunity to correct and date the contract and implementation before their first qualifying signals.

## 2. Contract-to-code trace

| Rule / gate | Document says | Code does | Assessment |
|---|---|---|---|
| NFL B: weather | Outdoor; calibrated kickoff wind ≥15 mph | `nflweather/board.py:29–44,87–98` requires `wx_src="era5"`, wind ≥15; domes, closed roofs and explicitly open retractable roofs are excluded. Wind is interpolated at kickoff in `nflweather/weather.py:32–55`. | Threshold matches; explicitly document exclusion of open retractable roofs. |
| CFB B: weather | FBS, known outdoor venue/time; “kickoff wind” ≥15 mph | `cfbweather/board.py:90–114` filters FBS involvement and retains missing-venue/time statuses; `cfbweather/weather.py:8–23` uses a **four-hour mean**, not kickoff wind. | Definition differs; see D4. |
| Both B: lead | “1–3 days”; NFL original entry definition also says ≥24 hours | NFL `board.py:80,108`; CFB `board.py:96–97`: kickoff’s Eastern calendar date minus the Mac’s local calendar date, inclusive 1–3. These are current forecasts, not the archived `previous_day1/3` fields. | Calendar-day implementation; hour/time-zone contract ambiguous. |
| Both B: price | Under −115 or better; total and price required | NFL `board.py:38–43`; CFB `board.py:64–69`: missing values rejected, odds below −115 rejected, EV must exceed zero. | Gate comparisons match for valid American odds. |
| Both B: EV | Positive EV **at that line and price** | NFL `board.py:128–130`; CFB `board.py:129–131`: passes the offered line as both the offer and the market reference. | Does not provide the advertised line sensitivity; D1. |
| Both B: pricing history | NFL 1999–2023; CFB 2006–2023 windy outdoor games | Those season bounds and observed-wind ≥15 filters are applied before residual extraction. Current cohorts contain 656 NFL and 855 CFB observations. | Matches; no 2024+ outcomes in these EV cohorts. |
| NFL B: book | Amendment 3 describes Pinnacle entry prices; `RULE_BOOK="pinnacle"` | `_pinnacle_live()` selects Pinnacle, but `board.py:110–122` retains nflverse prices when Pinnacle is unavailable or unmatched. Source is not a signal gate. | Pinnacle preference, not Pinnacle-only; D5. |
| CFB B/HT: book | Pinnacle, else DraftKings; ESPN fallback described in playbook | `fetch.py:237–260` selects the first configured book with a totals market; `board.py:119–126` uses ESPN only if the entire mapped API frame is empty. | Mostly matches; missing *under* within a Pinnacle totals market does not trigger DraftKings fallback. |
| Both B: ledger and entry | Record snapshots; grade earliest qualifying signal | NFL `board.py:165–182`, CFB `board.py:144–157` record selected number/odds and status; scorers take first `SIGNAL` per game. | Entry selection matches intended B rule, but versions and periods are insufficiently restricted; D2. |
| NFL model lean | ≥.55 under / ≤.45 over; earliest snapshot ≥24h pregame | NFL `board.py:155–156`, `score_forward.py:91–95` implement those thresholds and lead condition; fitted data stop in 2025 (`market.py:88–110`). | Matches. Missing prices are explicitly graded at assumed −110, so this is not an executable-price result. |
| B: primary CLV | NFL consensus close; CFB last alert quote before kickoff | NFL `score_forward.py:39–42,62`; CFB `score_forward.py:45,65–76` implement entry total minus that reference. | Matches the **current** registrations; cross-book/stale-close limitations remain by design. |
| B/HT: secondary close | Descriptive captured close; missing stays missing | NFL scorer filters Pinnacle; CFB uses captured selected-book total. Both print missing counts (`NFL:43–48,80–87`; `CFB:48–62`). | Matches descriptive separation; neither replaces the primary metric or HT entry. |
| B/HT: outcome / pushes | Grade entry line and odds; push returns stake | NFL scorer `53–65`; CFB scorer `71–76,87–93`: win payout from American odds, loss −1, push 0. | Settlement arithmetic matches. NFL ROI excludes pushes from its denominator; HT ROI includes them—label that distinction. |
| HT: 2026 threshold | Prior-season mean +10, frozen approximately 62.6175 | `cfbweather/board.py:28–42` returns **62.617539** immediately for 2026; no parquet read is reached. | Verified correct, including after PR #48. |
| HT: eligibility / entry | FBS; from 2026 Week 6 through 2027 title game; last logged pre-kickoff quote must qualify | Board’s lower cutoff is `2026-10-07T00:00Z`; scorer selects last pre-kickoff row with a nonmissing total, then requires HT `SIGNAL` (`score_forward.py:45,81–96`). No upper season boundary. | Last-quote selection works for priced rows, but notification and upper cutoff differ; D2/D3. |
| Decisions | NFL B amendment 4: pooled seasons, season-specific consistency and keep/drop criteria; CFB B: 40/end-of-season rule; HT: one decision after 2027, significance plus ROI | Scorers print statistics; NFL also prints horizon prose. No executable keep/drop evaluator, season-specific CLV check, or final/interim gate. | Incomplete; D2. |

**HT rebuild check:** comparing PR #48 with parent `4719959` showed 34,249 rows before and after; **only `home_spread` changed**. The diff for CFB board/scripts/preregistration was empty. An independent call to `ht_threshold(2026)` succeeded with parquet reads deliberately disabled and returned **62.617539**; recomputing from today’s data would give **62.534661** over 1,594 prior-season records, but that path is not used for 2026. The 2027 threshold is still dynamically recomputed from 2026 data and is not yet frozen.

## 3. Discrepancies, most consequential first

### D1 — VERIFIED: the EV gate does not implement the promised offered-line sensitivity

**Contract:** NFL amendment 2, `PREREGISTRATION.md:71–77`, explicitly says the probability should differ at totals 30 and 60; both playbooks require positive EV at the offered line and price.

**Implementation:** NFL `nflweather/board.py:130` and CFB `cfbweather/board.py:131` call `ev_under(L, odds, L, residuals)`. Their pricing functions subtract the two line inputs (`NFL market.py:134–148`; `CFB market.py:138–150`), making the cutoff zero regardless of L. Independently, at −110 the current cohorts give **+9.784% NFL EV** and **+8.123% CFB EV** at each of 30, 44 and 60. The same calculation assigns a **1.524% NFL / 1.170% CFB push probability at 44.5**, although an integer final score cannot push that line. Correct final-result push grading does not fix this signal-generation error.

**One-line fix:** separate and freeze the market reference from the offered strike, enforce integer-score support, and test the actual board wiring—or explicitly amend this into a price-capped weather screen without a claimed line-sensitive EV filter.

### D2 — VERIFIED: scoring does not enforce the registered experiment boundaries or decisions

**Contract:** NFL amendments 2/4 restrict the evaluated window and prescribe multiple decision conditions; CFB HT is a 2026 Weeks 6+ / 2027 experiment with one final decision.

**Implementation:** NFL `scripts/score_forward.py:50` accepts **any nonempty** version; CFB has no version filter (`:34–36,65,82–83`). Both B selectors trust `SIGNAL` without independently validating pre-kickoff timing. Neither scorer limits the evaluated population to its registered ending season. An isolated fixture with `rules_version="NOT_REGISTERED"` was accepted by both; a **2028 CFB HT game** was included in the purported registered HT result. NFL `:118–120` merely prints amendment 4; it never computes mean CLV by season, win rate against the close, the keep/drop decision, or a final-versus-interim state. CFB likewise prints metrics without its decision logic. NFL’s primary CI also divides by all settled bets even if some primary closes are missing (`:75`).

**One-line fix:** validate each rule’s permitted versions, pregame entries and season bounds, then implement a single explicit decision function with separate settled, priced and CLV-complete counts.

**Contract ambiguity to settle first:** NFL amendment 4 says “earlier at 40 signals,” requires positive CLV in **both seasons**, and says a 2026-only read “decides nothing” (`:133–142`); it does not resolve 40 signals reached during 2026. Its heading also does not clearly say whether the model-lean rule inherits the new horizon, although the scorer prints it globally. HT’s “binomial … break-even of the prices taken” leaves aggregation unspecified: code uses the arithmetic mean of individual break-evens, which is not an exact heterogeneous-probability binomial model (`CFB scorer:89–91`).

### D3 — VERIFIED: HT can alert before the last scheduled run, then score a different entry

**Contract:** CFB `STRATEGY.md:25` says the alert fires on the last scheduled run and entry is the last logged quote before kickoff.

**Implementation:** `cfb-weather/scripts/alerts.py:43–55` permits kickoff within **4.5 hours**, then permanently marks the game’s `ht` notification sent. With a 4:00 PM Pacific kickoff, both the **11:30 AM** and **3:30 PM** runs satisfy this condition; the first qualifying alert suppresses the second. The scorer still uses the later quote (`score_forward.py:45,82–83`), which could have different odds, a different total, or no qualifying HT signal at all. The plist confirms those run times.

**One-line fix:** determine the actual last scheduled run before kickoff and tie the notification’s entry-row ID to the scored entry; explicitly define how subsequent manual snapshots or a missed run are handled.

### D4 — VERIFIED: the wind and lead-time definitions are not fully specified by the contract

**Contract:** CFB says “kickoff wind”; both rules say “1–3 days,” while the NFL’s original entry provision says at least 24 hours.

**Implementation:** CFB `cfbweather/weather.py:8–23` averages kickoff hour through hour +3. Both boards count calendar dates, combining an Eastern kickoff date with `date.today()` on the Pacific Mac (`NFL board.py:80,108`; `CFB board.py:96–97`). For an Oct 1, 5:00 PM Pacific kickoff, Sep 28 at 7:30 AM is **81.5 hours** out and Sep 30 at 7:30 PM is **21.5 hours** out; both satisfy the implemented 1–3-day rule.

**One-line fix:** register the intended wind aggregation and one exact lead-time convention/time zone, then make the predicate and boundary tests use that definition.

### D5 — VERIFIED: NFL source fallback can still produce a non-Pinnacle signal

**Contract:** NFL amendment 3 describes Rule B entries as coming from Pinnacle (`PREREGISTRATION.md:104–107`); the rule is described as requiring a usable offered price.

**Implementation:** `nflweather/board.py:110–122` leaves nflverse total/odds in place if Pinnacle is unavailable, and `rule_b_status()` never checks `line_src`. If those fallback values are present and pass the numerical gates, they can become a signal. Quote freshness and provider update time are not checked or retained in the ledger (`board.py:171–175`). Earlier registration language does allow nflverse lines, so the documents themselves also need reconciliation.

**One-line fix:** explicitly register permitted entry sources and freshness requirements; if Pinnacle-only is intended, missing Pinnacle must yield WATCH/no-price rather than a fallback signal.

### D6 — VERIFIED: a failed run does not always produce missing-data ledger rows

**Contract:** the requested operating standard is “log, don’t drop,” and NFL preregistration `:18–20` says every upcoming game is appended.

**Implementation:** alerts call `board.compute()` **before** `board.save()` (`NFL alerts.py:60–66`; `CFB alerts.py:38–42`). Schedule/weather retries ultimately raise (`NFL fetch.py:50–66`; `CFB fetch.py:44–57`); the boards do not catch those errors per game. A single exhausted forecast request can therefore prevent the entire run’s rows from being saved. NFL `weather.game_weather()` also returns a columnless empty frame when all forecasts are missing (`weather.py:65–76`), which cannot merge on `game_id` at `board.py:88`. CFB’s ESPN fallback has an uncaught connection-error path (`fetch.py:167–180`).

**One-line fix:** persist a run record and an expected-game skeleton first, then record per-game failure reasons without letting one failed dependency erase the batch.

## 4. Lookahead and silent-failure findings

**Historical cutoffs are correct:** NFL board caps its EV cohort at 2023; CFB explicitly loads 2006–2023. Saved calibration metadata say NFL 1999–2023 and CFB 2016–2023; their builders apply those cutoffs (`NFL nflweather/build.py:97–113`; `CFB scripts/calibrate.py:24–44`). The live boards read saved calibrations, not refit them on 2024+ results. NFL’s model lean intentionally trains through 2025; that is in its contract.

**No direct future-result input found in current live Rule B/HT predicates.** NFL upcoming games require missing results; CFB selects future kickoff times. Their historical outcomes are used only in the described training/cohort calculations. However, “frozen” currently pins the **season cutoff**, not a hash of the historical dataset; rebuilding old records could alter probabilities without changing `rules_version`.

**Historical as-of reconstruction remains unverified.** Forecast files are overwritten on refresh (`NFL fetch.py:189–205`; `CFB fetch.py:136–144`), while ledgers keep neither forecast issue/retrieval time nor raw-payload identity. The ledger snapshot is stamped after computation; future forecast *valid times* are not themselves lookahead, but the missing provenance prevents reconstructing exactly which issued forecast and price were available for an old row. NFL `decision_time()` is an archived-replay scheduling heuristic, not the live Rule B lead predicate; it does not prove provider publication timing.

| Situation | Verified behavior |
|---|---|
| Odds API HTTP failure / quota low | NFL catches `OddsAPIUnavailable`/`SystemExit` and falls back; CFB returns an empty price frame and attempts ESPN. This **alone** need not erase a run. NFL empty responses are now handled in `_pinnacle_live()`. |
| Missing forecast without a request exception | CFB keeps `no_forecast`, `no_venue` or `time_tbd`. NFL can retain a row when some forecasts exist, but reports absent weather as `not_outdoor`/`no_trigger`; the all-missing case can fail as D6 describes. |
| Unknown odds-provider team name | Price rows are unmapped; left joins normally retain the scheduled game. CFB can show no-price for a windy/high-total candidate; NFL can use nflverse fallback. No separate mapping-failure status is preserved (`CFB board.py:120–126`; `NFL board.py:117–122`). |
| Mac asleep through close window | Capture scripts only consider games 2–20 minutes ahead; on later execution an already-started slot is not backfilled. Scorers report absent secondary closes, as registered. The CFB **primary** remains an older alert quote and may even equal the entry; there is no maximum age (`CFB scorer:45`). |
| Partially missing capture response | Both capture scripts mark the **whole slot** captured after a left join, even if some games/books have no price (`NFL capture_close.py:52–59`; `CFB capture_close.py:50–60`). Those missing games will not retry within the remaining window. |
| Close-capture quota near exhaustion | `quota.scheduled()` recognizes labels ending `.alerts`; the installed close job is `com.valuefinder.closecapture`. It therefore receives the **60-credit manual floor**, while alerts may continue down to one credit. This is actual current behavior, not an assurance that closes get reserved credits. |

The four requested plists point to this checkout and specify alerts at 7:30/11:30/15:30/19:30, close capture every 900 seconds, and ledger sync at 23:45. I read them without loading/unloading jobs. `ops/capture_closes.sh` exits zero even if a child capture fails; file existence and a successful wrapper exit therefore do not prove capture success.

## 5. Amendment timeline check

Checked with `git log --format='%H %ad %s' --date=iso -- <preregistration>` and first-parent merge history. All times below are **Sep 28 Pacific**, except the first ledger row explicitly dated Sep 27. Commit times establish repository history, not independently authenticated real-world publication timestamps.

| Contract | Commit / arrival on main | Ledger comparison | Conclusion |
|---|---|---|---|
| NFL original + amendment 1 | `cbd87a2`, 9:57:40 AM; first repository commit already contains both | Earliest blank-version ledger rows: **Sep 27, 10:15:21 PM**, including two model leans | Git does **not** prove these were committed before logging began. Current evaluation excludes these rows. |
| NFL amendment 2 | `29e4681`, 11:14:28 AM; merged `ddba06c`, 11:16:16 AM | First `v2-2026-09-28` snapshot: **10:44:56 AM**, 29m32s before the commit | Versioned logging preceded commitment. Those games are before the amended Oct 8 evaluation boundary, so this is not evidence of a contaminated evaluated result. |
| NFL amendment 3 | Initially `5bd55e3`, 4:33:16 PM; finalized `6fc7b1c`, 5:04:20 PM; merged `81a2ac9`, 5:04:34 PM | Existing snapshots predate it; subsequent snapshot 5:06:38 PM. No Rule B signals or eligible Week 5 rows | Before evaluated signals; not before every ledger row. Secondary/descriptive amendment. |
| NFL amendment 4 | `384063c`, 8:10:07 PM; merged `1962591`, 8:10:22 PM | Latest NFL snapshot 7:30:10 PM; still zero Rule B signals. All logged kickoff dates are Sep 28 or Oct 1/4/5 | Before any currently logged eligible Week 5 signal/outcome; it changes the future decision horizon, not those excluded rows. |
| CFB original | `29e4681`, 11:14:28 AM; main 11:16:16 AM | First `cfb-v1` snapshot 11:30:18 AM | Committed before the first current CFB ledger row. |
| CFB amendment 1 / HT | `2af7ba2`, 4:25:49 PM; merged `c075b27`, 4:57:31 PM | First `cfb-v2` snapshot 5:06:51 PM; no HT signals | Committed and merged before the corresponding versioned rows and eligible kickoff. |
| CFB amendment 2 / captured close | `5bd55e3`, 4:33:16 PM; combined with HT in `ee85604`, 5:03:05 PM; main 5:04:34 PM | Earlier CFB B snapshots exist, but zero B/HT signals | Before affected signal/outcome; cannot claim before all logged observations. |
| PR #48 rebuild | `bb4e6da`, 8:53:35 PM; main `0aba1e2`, 8:53:58 PM | After latest CFB snapshot, which still contains no signals | Historical spread repair; verified no change to HT code, registration or frozen 2026 threshold. |

The stated HT cutoff **`2026-10-07 00:00 UTC` is Oct 6 at 5:00 PM Pacific**, not Oct 7 Pacific. The code and registration agree on the UTC instant.

## 6. Tests and verification limits

**Test results: NFL 60 passed; CFB 49 passed; sharp-markets 73 passed.** I used each existing environment, disabled bytecode/pytest-cache writes, and blocked socket access and `.env` reads. Sharp-markets initially failed collection because its settings module automatically loads `.env`; rerunning with the library’s supported `PYTHON_DOTENV_DISABLED=1` passed. No secret file was opened; no installation or live API request was made.

The suites cover numerical gates, pure pricing helpers, ordinary HT last-quote selection, frozen-threshold provenance, mocked API errors and quota behavior. They **do not** establish board-level line sensitivity, zero half-point push probability, HT last-scheduled-run notification identity, registered-version rejection, final season boundaries, full decision criteria, or complete ledger coverage during forecast/schedule failures. The pricing test holds its reference at 44 while varying the offer (`NFL tests/test_rules.py:45–49`); the actual board varies both together, explaining why that test passes despite D1.

Independent local probes reproduced D1, acceptance of unknown versions, inclusion of a 2028 HT game, the HT overlapping alert windows, and the frozen-threshold/rebuild results. These used pure functions and synthetic CSV inputs to scoring scripts; no alert, board-computation, capture, poller, props-logging or fetch workflow was invoked by the audit. Some repository tests execute logger code with mocked dependencies and temporary paths; network access remained blocked.

I did not verify live provider freshness, actual notification delivery, launchd’s loaded/running state, wake-from-sleep behavior, or a future end-to-end capture: those would require actions excluded by this audit. I did not infer an executed bet from a posted quote: `fills.csv` is used only for a separate cost-of-waiting comparison, while primary scores still use ledger quotes (`NFL scorer:108–117`; `CFB scorer:98–111`). No source, registration, existing output, scheduler or Git commit was changed.
