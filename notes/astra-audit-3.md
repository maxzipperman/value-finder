# Astra audit 3 — amended price engine and forward-test grading

Audited September 29, 2026, finishing before the 23:45 Pacific ledger publication. Read-only audit; no code changes, API calls, alert/capture executions, launchd actions, commits or branch switches.

| Target | Audited commit |
|---|---|
| Part A, PR85 `price-engine-amendment-1` | `8ce9b346c4b168061977b8cf8ab15c77a833a020` |
| Registration | `751ff67` |
| Updated main, Part B | `30444ec2f016b5fc7ec215172521d2eb51876e32` |
| Part C, PR87 `claude/quirky-goldberg-81hwy6` | `e40035e58f357668d717de1348f3f35fcb2dae5a` |
| Optional B9, PR86 `rule-ht-no-kickoff-time` | `2635ac81ecf949d4c0602927ca216f324bd9376f` |

PR87 was not merged into `origin/bulk-puller-followup` at the fetched snapshot; that branch remained `cc14201`. This report audits PR87's exported head. The original main export, `4bf0497`, remains in scratch; the two weather scorers are byte-unchanged between it and updated main.

## Verdict — four lines

1. **Thursday's price engine: yes with changes.** The amended loading and decision repairs held up; fix the preflight's result dependence and the numerical example below before relying on the amended protocol. The expressly accepted identity/orientation limits still apply.
2. **Forward-test grading: yes with changes.** Fix the captured-close join and test-end filtering in findings 1–2. Ordinary entries, settlement, intervals and recorded decisions passed the exercised cases.
3. **Spending code: C1–C5 closed on PR87 in offline tests; C6 disclosed and bounded, not numerically reconciled.** No live billing or account claim is made.
4. **PR85 safe to register exactly as requested: not yet.** `names_preflight.py:151` must stop loading result columns before Item 8 can serve as the requested result-blind preflight. Correct the −115 EV figures at registration line 74 as well. Neither requires a new strategy rule.

## Findings — reproduced, most severe first

Paths below are repository-relative to `/Users/maxzipperman/code/value-finder`. Reproductions run against exported commits, never that checkout. Command abbreviations are defined in the evidence section.

### 1. A new listing can inherit a captured close from three weeks earlier

**Severity: blocker.** `cfb-weather/scripts/score_forward.py:687–692, 715–719`, unchanged on updated main.

Amendment 4 §6 makes the fallback the close captured under amendment 2; amendment 2's capture is 2–20 minutes before kickoff. Amendment 4 §10 separates postponed listings. The scorer instead reduces `closes.csv` to one value per game ID and discards both its kickoff and capture time before joining.

**Command:** `AUDIT_VERSION=main-updated "$S/run_weather_version.sh" cfb "$S/weather_remaining.py" cfb`

**Input:** game 999 originally listed October 10, then signalled again October 31 at total 60. The only captured close is total 40, captured October 10 at 18:50 for an October 10 19:00 kickoff. Actual kickoff is October 31 19:00. The old listing is correctly void; its old close is nevertheless used for the new listing.

**Output:** `RULE_B: 2 signals, 1 settled, 0 pending, 1 void`; `mean CLV +20.00`; `primary close: 0 from a later logged quote, 1 from the captured close`. Game 999's entry 60 is joined to captured close 40. Evidence: `logs/weather-remaining.txt`, `logs/updated-cfb-stale-capture.txt`.

**Smallest fix:** retain capture and kickoff timestamps through the join; select a capture belonging to the graded game's valid kickoff/listing and registered pre-kickoff capture window. Otherwise count a missing close. This enforces the existing rule; it does not need a new strategy rule. State the timestamp/listing interpretation before the first outcome if any ambiguity remains.

### 2. A game moved beyond the test's end still enters its final record

**Severity: blocker.** `cfb-weather/scripts/score_forward.py:482–485` filters the ledger's `start_utc`, rather than checking the game's final scheduled kickoff against the test end.

Amendment 3 says both tests end with the 2027 title game and later games do not count. Amendment 4 §4 says a game dated after the test's end never counts, regardless of season label. The implementation's explicit cutoff is February 1, 2028 at 00:00 UTC.

**Command:** the same `weather_remaining.py` command as finding 1.

**Input:** Rule HT game 901 has entry-row kickoff January 31, 2028 at 23:00 UTC, but final schedule kickoff February 1 at 20:00 UTC. That is February 1 in both UTC and Eastern time, and a 21-hour move, so the more-than-24-hour void rule does not remove it. The scorer runs with explicit `--now 2028-02-02`.

**Output:** `RULE_HT: 1 signals ... 1 settled, 0 pending, 0 void`; `record 1-0-0`; `FINAL: STAY ON PAPER`. The out-of-test game is printed in that final decision. Evidence: `logs/weather-remaining.txt`, `logs/updated-cfb-after-horizon.txt`.

**Smallest fix:** enforce the test's game-date boundary using the scheduled kickoff as well as the entry row; retain the declared behavior for an unavailable schedule. This restores the exclusion already registered. If the intended test instead follows the entry row's date even after rescheduling, that is a different reading and needs a dated amendment.

### 3. The names-only preflight reads results and its output depends on them

**Severity: major.** PR85 `sharp-markets/src/markets/research/price_engine/names_preflight.py:151`; `outcomes.py:41–59`.

Item 8's protocol allows further aliases to come from names and schedules, “never on a price or a result.” The addendum explicitly asks whether the preflight reads names, kickoffs and IDs only, never results. It does not meet that stronger boundary: `main()` calls both full score readers, which request score columns and discard games with missing scores. `_planted()` replaces scores only afterwards.

There is a distinction here: Item 8's narrower literal statement “reads no price and prints no score” holds in this check. It should not be presented as proof that the process never reads or depends on results.

**Command:** `AUDIT_VERSION=amended "$S/run_sharp.sh" "$S/preflight_probe.py"`

**Output with identical teams, kickoff and event ID:** `final_score_present=true, matched_events=1`; changing only the synthetic final score to missing gives `final_score_present=false, matched_events=0, unmatched={"cfb_team_name_unknown":1}`. The read spy records requested NFL `home_score, away_score` and CFB `home_points, away_points` columns. Evidence: `logs/preflight-probe.txt`.

**Smallest fix:** add projected metadata readers for the preflight, with the same season filter but no score columns and no score-presence filter; plant IDs before matching. If final-score coverage is also wanted, run that separately after the names decision. This fulfills the requested pre-price protocol without changing a betting rule. No price or sealed score was exposed by this reproduction.

### 4. The exact −115 EV example rounds to −2.0% and −2.4%, not the printed figures

**Severity: major under this audit's definition of an unreproducible quoted number; small practical impact.** PR85 `sharp-markets/docs/PRICE_ENGINE_PREREGISTRATION.md:74`.

The example says −1.9% NFL and −2.3% CFB at −115. Independently counting the frozen residuals gives probabilities 0.524390243902439 and 0.5222222222222223. At the actual −115 decimal price, `1 + 100/115`, the EVs are −0.019618239660657455 and −0.023671497584541124: **−1.9618% and −2.3671%**, rounding to **−2.0% and −2.4%**.

**Command:** `AUDIT_VERSION=amended "$S/run_sharp.sh" "$S/audit_amended.py"`; output labels `A4_total_example` in `logs/amended-own.txt`.

The printed figures are reproducible if one uses the rounded decimal price **1.87**. Item 7 correctly states that 1.87 is rounded; it does not identify this example as using rounded-price arithmetic. **Smallest fix:** correct the two percentages or explicitly label them as the 1.87 approximation. Documentation only; no rule or code change. This is not a re-report of H2's accepted negative-EV minimum.

## Amendment 1, item by item

| Item | Independent audit result |
|---|---|
| 1 — A2 seasons | Pass. Actual `a2()` agreed with independent arithmetic on 10,000 random cells; 402 passed and none passed if either earlier reading failed. Bet counts and close counts remain separate. Missing values do not create an act verdict. |
| 2 — loading | Pass on the exercised repeated-snapshot cases. One-call loading restores quotes previously destroyed by duplicate grouping, counts duplicates separately, and retains returned snapshot timing. Staged comparisons attribute all quote/bet changes to this item. |
| 3 — tied books | Pass. 60 DraftKings bets at +3 cents and 60 FanDuel at −1 produce `draftkings+fanduel`, worst remainder −1, and `kill: one book carries it` in either row order. |
| 4 — K2/result minimum | Pass. Otherwise passing cells with 0 or 99 graded results are inconclusive; 100 can act. Kill rules still precede this gate. Pushes are excluded from `graded`, as the amendment expressly states. |
| 5 — sealed reads | Pass. Synthetic NFL and CFB readers receive only 2024, with read-time season filters. The amendment suite checks the spread-table reader and unchanged frozen cohort hashes. No synthetic 2026 game enters bets, results or calibration. |
| 6 — meaning of act | Text supplies the missing operational reading for other primary cells: a separately registered paper forward test and the owner's logging-cost decision. No code difference claimed or found. |
| 7 — constants/readings | Values checked against source; the coarse-cut limitation, CFB exact-distance tie, H2 scalar rank and season windows are now explicit. Numerical example finding 4 remains. |
| 8 — names | Forty aliases and matching diagnostics implemented. Alias-dependent score changes are isolated in staged runs. Names-only/result-blind boundary fails as in finding 3. Prefix resolution remains a review obligation: “Miami of Ohio RedHawks,” unlike the listed aliases, still falls through to Miami. Do not assume the alias table covers every spelling. |
| 9 — scale record | No code change. The amendment's other reviewers' 4,841-call/7.6-GB and heavier 12.3-GB measurements were not independently rerun. My separate 450-call measurement is below; it neither validates nor disproves their exact figures. |

The amendment now expressly states duplicate physical-event IDs and home/away changes across snapshots as known limits. My reproductions confirm duplicate IDs can create two bets; these are **not new findings**. The preflight's >1% duplicate-game protocol and the report's orientation count need to be acted on as the amendment says. Declaring a limitation does not make affected grades correct.

### Before/after attribution

`--fixture` was run in the registration, original main and amended exports. Registration and main had identical results. Registration versus amended: all existing `results.csv` values equal, only `seasons_20_closes` added; `dropped.csv` byte-identical; `bets.parquet` semantically identical, 17 rows × 44 columns.

Two independently constructed inputs exercised repeated snapshots, missing Pinnacle closes, kickoff moves, pushes, retail ties and alias-dependent names. For each I ran four stages: registration; registration with only amended loader; that plus amended matcher; full amendment. These are audit-only module substitutions in scratch, not proposed source changes.

| Input / stage | Calls | Games retained | Quotes | Scores matched | Bet rows across all variants |
|---|---:|---:|---:|---:|---:|
| Smaller, registration | 240 | 72 | 1,260 | 36 | 1,296 |
| Smaller, loader only | 240 | 96 | 1,674 | 48 | 1,728 |
| Smaller, + matcher / full | 240 | 96 | 1,674 | 96 | 1,728 |
| Larger, registration | 576 | 226 | 4,068 | 120 | 4,068 |
| Larger, loader only | 576 | 250 | 4,428 | 132 | 4,500 |
| Larger, + matcher / full | 576 | 250 | 4,428 | 250 | 4,500 |

On the larger input, Item 2 changes loading counts and the consequent bet statistics; Item 8 changes only result-derived fields after loading. With both repairs already applied, the full amendment changes only `seasons_counted` (Item 1), `top_book` (Item 3), and adds `seasons_20_closes` (Item 1). Bets and drops are identical at that last stage. No verdict changes in either mixed input; the larger input has one act verdict throughout. Full per-column change counts are in `logs/output-comparison.txt` and `logs/large-comparison.txt`.

The “only harder” claim holds for Items 1, 3 and 4 in the tested cases and follows from their added requirements. Items 2 and 8 are not monotone: restoring a favorable quote subset can reverse K1, and correcting losing to winning results can reverse K2. `repair_direction.py` constructs those summary-level cells: kill → act for each mechanism. These are decision-cell demonstrations, not a claim that the mixed replay above changed verdicts. The amended text now correctly acknowledges both directions.

## What held up, and what each check establishes

| Claim | Result / evidence |
|---|---|
| A1 — entry timing | Earlier/later/twice-moved and next-day kickoffs; exact last-hour boundary; returned snapshot rather than requested timestamp; old book update does not time entry. No admitted lookahead in these cases. Event-ID duplication is now a stated limit. `amended-own.txt`, `decision-extra.txt`. |
| A2 — closes | Exact/post-kickoff quotes rejected; 61-minute-old quote gives no close; latest kickoff used; missing Pinnacle close leaves the bet counted but ungraded for CLV. Six-side close tests and amended suite. |
| A3 — sealed 2026 | Actual synthetic cached fixture with and without sealed games produces identical results/drop counts/calibration and only `c2,n1,n2` bets. Both score readers apply read-time filters. `amended_sealed_output_check.txt`. |
| A4 — arithmetic | Independent two-outcome Shin probabilities: .5 for 1.95/1.95, .651515 for 1.5/2.75, .539683 for 1.8/2.1; missing-LowVig blend .5085034. Totals probabilities agree; spreads .452569 and .554036 agree. Finding 4 is the rounding mismatch. Extra stress pair 1.6/1.6 returns NaN under the frozen solver rather than .5, and suppresses its flag; existing test explicitly pins that behavior. It is not evidence of general solver correctness. |
| A5 — first/best/unique | Ordinary fixture results unchanged across three shuffled call orders; correct sharp/retail partition; duplicate-snapshot repair verified. Physical IDs, orientation swaps and extreme H2 ranking now have declared limits; do not read this as unconditional physical-game deduplication. |
| A6 — signs/results | Toward/away checks for over, under, home/away spread and moneyline: cents signs correct; point signs correct where defined (moneyline points NaN). Reversed score-table teams are reoriented; totals/spread/moneyline pushes recognized. |
| A7 — matching | Rematches on separated dates; neutral reversal; Michigan/State and Ohio/State; nearby different opponents; postponed game; unmatched-name reasons. Equal-distance CFB games follow table order, now explicitly Item 7. Alias preflight caveat in finding 3. |
| A8 — statistics/count | Independent clustered example: mean 1.5, SE .8050764859, n 6, one-sided p .0312186831; code agrees. Fixed bar .05/271; 99 bets or 99 closes cannot act. |
| A9 — decisions | Individually exercised too-few, K1–K4, A1–A6, their boundaries and missing values. New graded-result gate and tied-book tests pass; A2 random-cell comparison passes. |
| A10 — variants/constants | 38 result rows, eight primary, fixed count 271. Complete module-level constant inventory appended below; no extra selecting variant found. |
| A11 — frozen dependencies | Engine and registration unchanged from `751ff67` to updated main. Imported bulk/market validation code changed; ordinary fixture is unchanged. PR85 carries the dated amendment for its engine changes; it is still a branch, not yet registered. Cohort files and processed score-table changes are not the source of the staged differences. |
| A12 — offline/run size | Fixture and no-data runs work with sockets blocked. No-data says nothing to backtest. Synthetic 450 calls × 50 games × 10 books × 3 markets × 2 outcomes = 1,350,000 outcome rows / 675,000 quotes; original engine pipeline 37.95 seconds, peak RSS 866,369,536 bytes. Cache creation took 244.28 seconds. Disk compression of repetitive fake rows is not a real-cache forecast. `scale450.txt`. |
| A13 — test gaps | Five important boundaries not established by the original test file: result-blind preflight reads; physical-event identity; changes of home/away between snapshots; adversarial real name coverage; real-cache full-scale resources. New tests improve coverage but do not remove the stated limits. |
| A14 — readings | Amendment resolves season counting, tied-book removal, insufficient scores, non-CFB act, coarse cut and H2 rank. Result-blind preflight remains unresolved. Duplicate IDs above the stated threshold require a pre-price decision, not a choice after viewing returns. |
| B1 — entry | Earliest Rule B row; both kickoff directions; equality/in-play excluded using earlier row/schedule kickoff. Rule HT is intentionally last valid quote, not Rule B's first-row rule. |
| B2 — close | Pure extracted event selector chooses priced rule book, then nearest within six hours; rematch rejected; equal identical feed quotes accepted; unequal ties/missing time rejected. Captured-close consumption fails finding 1. The prompt's “at most 20 closes” is not registered: the actual rule is a 2–20-minute window and at most two calls per slot, not 20 game rows. |
| B3 — settlement | More-than-24-hour moves void; no-result 30-day rule; pending holds decision; separate listings. Test-end failure in finding 2. |
| B4 — record | Second synthetic run preserves recorded bytes; truncated record rejected rather than appended; damaged record still exposes readable decisions. Publication tests preserve prior lines. No live ledger or decision file modified. |
| B5 — intervals | Independent 40-bet, four-day month: mean .30, plain half-width .8421133831, grouped half-width 0, interval [−.5421133831,1.1421133831]; code agrees. One-day sample inconclusive. CFB not kept in this month. |
| B6 — clock | DST's two 01:30 instants both lead to the next 07:30 Pacific run; New Year rolls correctly; Eastern-date grouping puts Jan 1 04:30 UTC on Dec 31 and 05:30 on Jan 1. NaT helper produces no last-run trigger. Placeholder behavior on main is the accepted issue; see optional B9 below. |
| B7 — alert language | Source-only inspection. Number and price appear; CFB Rule B's “EV+”/“Bet only this number” wording lacks an explicit paper marker. This is acknowledged D10 and remains the hub's money-gate task; no alert executed and no new finding counted. |
| B8 — nightly copy | Not yet observable: before 23:45 Sept 29. Fetched `origin/ledgers` is `27c10ce…`, Sept 28 23:45 PDT. Both ledgers exist, neither runs.csv yet; decisions absent as expected. D11 is pending tonight, not a failed new publication. |

### Ten additional registered sentences

Commands: `"$S/run_weather.sh" nfl "$S/selected_sentences.py" nfl` and `AUDIT_VERSION=main-updated "$S/run_weather_version.sh" cfb "$S/sentences_final.py" cfb`. These drive the project's small synthetic tests with explicit scratch ledger and clock. The extra record-reading cases below check presentation/time parsing beyond the record's write-once claim.

| Sentence / specific reading | Result |
|---|---|
| NFL amendment 6 §5: a lean enters at its first snapshot with a posted total | Pass, first usable total retained. |
| NFL amendment 6 §6: inconclusive 2026 is decided once more after 2027 | Pass, pooled-decision case. |
| NFL amendment 6 §7: ties with the close are excluded from win rate | Pass, tied moves excluded from that denominator. |
| NFL amendment 6 §8: corrected pricing examples are the frozen model's numbers | Pass, model-number test. |
| NFL amendment 7 §3: a record timestamp lacking a time zone is damage, not a crash | Pass. |
| CFB amendment 4 §5: later total without a valid under price does not replace HT's entry | Pass. |
| CFB amendment 4 §7: not-kept means no money goes on the rule | Pass, decision wording. |
| CFB amendment 4 §8: HT is reported by price source | Pass, distinct source summaries. |
| CFB amendment 4 §9: model examples correct break-even to about −130 and rejection from 1.5 points below reference | Pass. |
| CFB amendment 5 §3: damaged record still prints decisions it can read | Pass. |

### Optional B9 — draft Rule HT amendment

35 selected tests passed, three alert/notice-execution tests deliberately deselected. The branch holds HT while the row is untimed, selects the last timed valid quote when the time arrives, and does not resurrect an earlier signal when the last quote is untimed. Late-time example: old untimed 70.5 would win at 67; final timed 64.5 at −105 correctly loses.

**It is not an unconditional no-lookahead guarantee.** The draft explicitly allows up to placeholder +30 hours when the final schedule still has midnight as the kickoff. Its own reproduced case has a true noon Eastern kickoff, a stale listed 19:30 kickoff and a 15:00 quote. That in-play quote is accepted and graded. The draft openly states this gap at lines 757–769 and requires manual checking of completed placeholder games before a decision. It affects Rule B closes as well as HT entries. This is an acknowledged exception, not an undisclosed new defect; approval of PR86 entails that manual dependency. Evidence: `logs/ht-suite.txt`; `test_the_stated_gap_a_placeholder_in_the_schedule_and_an_earlier_real_kickoff`.

## Part C — PR87 and Thursday's runbook

Commands: `AUDIT_VERSION=pr87 "$S/run_sharp.sh" "$S/c-checks/check_six.py"`, the adapted audit-2 `check_current.py`, `check_remaining.py`, and `check_counts.py`. `check_current.py` additionally sets `MARKETS_DATA_DIR="$S/pr87-c-data"`. All HTTP replies are synthetic objects; “paid_calls” below means a classified mock request, not network use.

| Finding | Result |
|---|---|
| C1 — NBA shared floor/billing guard | Closed. Mock balance 500,000 versus floor 531,630: zero paid requests. Overbill case: exactly one paid mock reply, 300 counted, stopped before second. |
| C2 — billed failed attempt/retry | Closed. HTTP 500 billing 300 with budget 60: one attempt, 300 counted, no retry. Additional missing/zero/fractional/bad-header cases stop as recorded. |
| C3 — successful response key echo | Closed. Planted fake key absent from cached successful body. No real key used or inspected. |
| C4 — cached 404 retry policy | Closed. Ordinary rerun reuses cached 404 (one request); explicit refetch makes second request and saves 200. Branch tests cover the explicit retry guard. |
| C5 — exact-tip NBA close | Closed. Quote exactly at kickoff with fair .99 and post-tip quote ignored; pre-tip fair .5 selected. |
| C6 — rehearsal/production grid | Disclosed/bounded, not reconciled to equality. Same cached schedule stand-ins yield F1 164,910 and net F4 1,483,650, versus published estimates 162,210 / 1,442,220. The runbook labels estimates and uses higher bounds (170,000 / 1,520,000). NBA sample exact count unavailable without its cache. |

PR87 `tests/test_bulk.py`: **163 passed, one skipped, one guard-induced failure**. The failure is `test_network_failure_stops_the_run_without_showing_the_key`: it deliberately reaches the network failure path, but the audit's socket/DNS guard raises first. It is not evidence of a production failure and no connection occurred. The earlier followup suite had 242 passes with the three network-dependent cases deselected; that is not substituted for PR87's result.

Read and exercised the runbook's non-confirming research commands on empty isolated data: balance dry run, probe dry run, headers, plan, sliced F3 plan/check, sample-week planning, F1/F2 checks, price engine, NBA plan/build/backtest, weather check/plan/join/qualifying, heat plan/check and manifest query. **No `--confirm` command was run**, including free balance checks. Read-only git/setup instructions were inspected; credential and mutation steps were not run.

No-data engine behavior and venue check (205 venues, zero problems) work. Empty-schedule plans are empty. Headers/manifest and NBA/heat outputs cannot match the populated-cache examples without the preceding data. NBA planning/build attempt a Kalshi fallback on an empty cache; the network guard stops them. Backtest lacks its analysis table. These are prerequisites/limitations, not claims of successful Thursday rehearsal. The runbook has paid prerequisites; this audit does not certify them from empty exports. Full command transcript: `logs/pr87-runbook.txt`.

## Evidence, scope and limits

Reproduction environment:

```sh
S=/Users/maxzipperman/Documents/Codex/2026-09-29/audit-3/scratch
# run_sharp.sh enters the selected exported sharp-markets project and uses uv run --offline --no-sync.
# run_weather_version.sh uses the relevant live project's Python with the exported source on its path.
# Both wrappers inject guard/sitecustomize.py: deny sockets, .env/.kaggle reads, live-repo writes,
# forbidden alert/capture entrypoint execution, and scorer subprocesses missing --ledger or --now.
```

Price suite command: `AUDIT_VERSION=amended "$S/run_sharp.sh" -m pytest tests/test_price_engine.py tests/test_price_engine_amendment1.py tests/test_price_engine_checks.py -q` — 106 collected cases, 105 passed and one skipped (quiet configuration prints progress rather than the summary). Optional HT command uses its weather environment and `-k 'not alert and not notice'`: 35 passed, three deselected. Selected original-main readings: NFL 44 passed / 16 deselected; CFB 45 passed / 17 deselected. Ledger publication tests: 35 passed. The prior readings' code is unchanged on updated main.

Mixed-input commands: run `amendment_independent.py` and `amendment_large.py` with arguments `registered`, `loading`, `matching` in the registration environment, and `amended` in the amended environment; then `compare_outputs.py` and `compare_large.py`. The first three stages differ only by explicitly loaded audit modules. `decision_extra.py` checks actual A2 and tied-book functions. All outputs are synthetic.

Limitations: no paid/free Odds API call; no live alert/capture end-to-end execution; no real F1; no live alias preflight against Thursday's as-yet-unbought schedules; no full-size independent amended benchmark; no post-23:45 publication check. The amendment's historical checker counts and other reviewers' precise timing claims are provenance statements, not independently reproduced measurements here. No automatic wakeup was created. Existing tests and audit adapters sometimes needed environment/API adaptations; earlier failed harness attempts remain in scratch but are not findings.

The complete scripts/logs remain under the requested scratch directory. A compact evidence ZIP accompanies the report copy in this chat's outputs. No repository file was changed.

## Constant inventory

Module-level constants were extracted from every Python file under the amended price engine. Classification of every category follows; the exact names and values are in the machine-generated inventory below.

- **Explicit strategy/statistics values, stated:** `THRESHOLDS`, `PRIMARY_THRESHOLD`, `FAIRS`, `H1_MARKETS`, `BLEND_WEIGHTS`, `LAG_POINTS`, `LAG_MIN_DEC`, `CLOSE_WINDOW`, `EV_ERROR`, `PRIOR_COUNT`, `MIN_BETS`, `MIN_SEASON_BETS`, `EPS`, `VARIANTS`, `RUNNING_COUNT`, `ALPHA`. Original §§3–8 and amendment Items 1, 4, 7.
- **Model choices, stated or pinned by referenced hashed artifacts:** `REGISTERED`, `SPREAD_COHORT`, `SPREAD_SEASONS`, `SPREAD_NEIGHBORS`, `SPREAD_COHORT_SHA256`; model files/cohorts in §§3 and 6. Paths/hash literals are implementation provenance, not additional tested hypotheses.
- **Matching/window/coverage choices, now stated:** `SEASONS`, `SEASON_FILTER`, `EXTRA_NFL`, `CFB_WINDOW`, all 40 `CFB_ALIASES`, `SHARP`, `RETAIL`, `WINDOW`, `COARSE_MARGIN`, `MIN_SCORE_SHARE`, `TWO_EVENT_LIMIT`; §§2–5 and amendment Items 5, 7, 8. `SEASON_FILTER` implements the stated season range.
- **Definitions rather than free numeric choices:** `NFL`, `CFB`, `SPORTS`, `LABEL`, `MARKETS`, `SIDES`; sport/market/side meanings are stated. `ALIAS`, `TEAM_FILES`, `SCHOOL_NAME`, `PREFIX`, `UNRESOLVED` are diagnostic labels, not new variants.
- **Not separately registered as tunable values:** `REPO`, `PREREG`, `COLUMNS`, `COLS`, `GRADE_COLS`, `RESULT_COLS`, `MOVED_COLS`, `DAILY_NOTE`, `TOO_FEW_RESULTS` are paths, schemas and presentation strings. The document describes their behavior; exact column-list/string literals do not select a strategy.
- **Synthetic-only constants, intentionally not real-data rules:** fixture `UTC`, `NOW`, `CFG`, `GAMES`, and its `NFL`/`CFB` aliases. They define the test example, not the registered backtest universe.

The inventory is module-level, not a claim that every literal in imported numerical routines is separately printed in the registration. Imported Shin's iteration/bracketing choices and the model's numerical-solution acceptance tolerance are pinned by code; the 1.6/1.6 stress case above illustrates that boundary.

```text
engine.py:42 THRESHOLDS = (0.01, 0.02, 0.03)
engine.py:43 PRIMARY_THRESHOLD = 0.02
engine.py:44 FAIRS = ('pinnacle', 'blend')
engine.py:45 H1_MARKETS = ('totals', 'spreads', 'h2h')
engine.py:48 BLEND_WEIGHTS = {'pinnacle': 0.55, 'lowvig': 0.3, 'betonlineag': 0.15}
engine.py:49 LAG_POINTS = 1.0
engine.py:50 LAG_MIN_DEC = 1 + 100 / 115
engine.py:51 CLOSE_WINDOW = pd.Timedelta(minutes=60)
engine.py:52 EV_ERROR = 0.1
engine.py:57 PRIOR_COUNT = 233
engine.py:58 MIN_BETS,MIN_SEASON_BETS = (100, 20)
engine.py:59 EPS = 1e-09
engine.py:80 VARIANTS = tuple([Variant('H1', s, m, f, t) for s in SPORTS for m in H1_MARKETS for f in FAIRS for t in THRESHOLDS] + [Variant('H2', s, 'totals', 'lag', LAG_POINTS) for s in SPORTS])
engine.py:82 RUNNING_COUNT = PRIOR_COUNT + len(VARIANTS)
engine.py:83 ALPHA = 0.05 / RUNNING_COUNT
engine.py:279 GRADE_COLS = ['clv_pin_cents', 'clv_own_cents', 'clv_pin_pts', 'clv_own_pts', 'pin_moved', 'clv_pin_expected', 'won', 'push', 'profit', 'pin_stale', 'hours_before', 'home_score', 'away_score']
engine.py:372 TOO_FEW_RESULTS = 'inconclusive: too few results to check the return'
fixture.py:26 UTC = timezone.utc
fixture.py:27 NOW = datetime(2026, 9, 29, 12, tzinfo=UTC)
fixture.py:28 CFG = {'books': {'us10': ['pinnacle', 'lowvig', 'betonlineag', 'draftkings', 'fanduel', 'betmgm', 'williamhill_us', 'fanatics', 'betrivers', 'espnbet'], 'sharp3': ['pinnacle', 'lowvig', 'betonlineag']}, 'featured': 'h2h,spreads,totals', 'sports': {'americanfootball_nfl': {'history_from': '2020-06-06', 'sweep_every_days': 2, 'windows': [{'label': '2024', 'from': '2024-09-01', 'to': '2025-02-15'}, {'label': '2026', 'from': '2026-09-01', 'to': '2027-02-20', 'sealed': True}]}, 'americanfootball_ncaaf': {'history_from': '2020-06-06', 'sweep_every_days': 2, 'windows': [{'label': '2024', 'from': '2024-08-20', 'to': '2025-01-25'}, {'label': '2026', 'from': '2026-08-20', 'to': '2027-01-25', 'sealed': True}]}}, 'pulls': {'F1': {'kind': 'featured', 'sports': ['americanfootball_nfl', 'americanfootball_ncaaf'], 'schedule': 'daily_close', 'books': 'us10'}}}
fixture.py:44 NFL,CFB = ('americanfootball_nfl', 'americanfootball_ncaaf')
fixture.py:45 GAMES = {'n1': (NFL, '2024-09-08T17:00:00Z', 'Kansas City Chiefs', 'Baltimore Ravens', 20, 21), 'n2': (NFL, '2024-09-09T00:20:00Z', 'Philadelphia Eagles', 'Green Bay Packers', 34, 29), 'n26': (NFL, '2026-09-13T17:00:00Z', 'Buffalo Bills', 'New York Jets', 30, 10), 'c1': (CFB, '2024-09-07T16:00:00Z', 'Alabama Crimson Tide', 'Wisconsin Badgers', 42, 10), 'c2': (CFB, '2024-09-07T23:30:00Z', 'Texas Longhorns', 'Michigan Wolverines', 31, 12), 'c26': (CFB, '2026-09-12T19:30:00Z', 'Ohio State Buckeyes', 'Oregon Ducks', 24, 21)}
model.py:35 REPO = Path(__file__).resolve().parents[5]
model.py:36 NFL,CFB = ('americanfootball_nfl', 'americanfootball_ncaaf')
model.py:37 SPORTS = (NFL, CFB)
model.py:38 LABEL = {NFL: 'NFL', CFB: 'CFB'}
model.py:40 REGISTERED = {NFL: ('nflweather', 'nfl-weather', '897a61b6846b077b71c324dc0c2f4b2e28bda963aa69d0cc4a89f181eb039556'), CFB: ('cfbweather', 'cfb-weather', 'c49a6649c3f86ac1280ed488f675c14859b23073c1aa8e18aab63060b38bff67')}
model.py:104 SPREAD_COHORT = Path(__file__).with_name('spread_cohort.json')
model.py:105 SPREAD_SEASONS = {NFL: (1999, 2019), CFB: (2006, 2019)}
model.py:106 SPREAD_NEIGHBORS = 1000
model.py:107 SPREAD_COHORT_SHA256 = {NFL: '19957e80dd193907d693e8bd49fb7bbcd1ef7d90ca6a22d0489c831e2c46506b', CFB: '63917879c6b5f2615edd243e7fee6ea260bb5ef5abe7b75e9ddc0a5d664a6fd5'}
names_preflight.py:46 COLS = ['id', 'commence_time', 'home_team', 'away_team']
names_preflight.py:47 TWO_EVENT_LIMIT = 0.01
outcomes.py:27 SEASONS = range(2020, 2026)
outcomes.py:28 SEASON_FILTER = [('season', 'in', list(SEASONS))]
outcomes.py:29 EXTRA_NFL = {'washington football team': 'WAS', 'washington redskins': 'WAS', 'oakland raiders': 'LV'}
outcomes.py:30 CFB_WINDOW = pd.Timedelta(hours=36)
outcomes.py:84 CFB_ALIASES = {'umass minutemen': 'Massachusetts', 'miami redhawks': 'Miami (OH)', 'miami ohio redhawks': 'Miami (OH)', 'miamiohio redhawks': 'Miami (OH)', 'louisiana monroe warhawks': 'UL Monroe', 'louisianamonroe warhawks': 'UL Monroe', 'ulmonroe warhawks': 'UL Monroe', 'louisianalafayette ragin cajuns': 'Louisiana', 'north carolina state wolfpack': 'NC State', 'southern california trojans': 'USC', 'mississippi rebels': 'Ole Miss', 'texas el paso miners': 'UTEP', 'ut san antonio roadrunners': 'UTSA', 'nevada las vegas rebels': 'UNLV', 'alabama birmingham blazers': 'UAB', 'southeastern louisiana lions': 'SE Louisiana', 'tennesseemartin skyhawks': 'UT Martin', 'albany great danes': 'UAlbany', 'citadel bulldogs': 'The Citadel', 'saint francis pa red flash': 'St. Francis (PA)', 'saint francis red flash': 'St. Francis (PA)', 'tarleton texans': 'Tarleton State', 'se missouri state redhawks': 'Southeast Missouri State', 'appalachian state mountaineers': 'App State', 'southern mississippi golden eagles': 'Southern Miss', 'connecticut huskies': 'UConn', 'houston baptist huskies': 'Houston Christian', 'texas amcommerce lions': 'East Texas A&M', 'dixie state trailblazers': 'Utah Tech', 'central florida knights': 'UCF', 'southern methodist mustangs': 'SMU', 'texas christian horned frogs': 'TCU', 'louisiana state tigers': 'LSU', 'brigham young cougars': 'BYU', 'tennessee martin skyhawks': 'UT Martin', 'arkansas pine bluff golden lions': 'Arkansas-Pine Bluff', 'san diego st aztecs': 'San Diego State', 'ohio st buckeyes': 'Ohio State', 'iowa st cyclones': 'Iowa State', 'utah st aggies': 'Utah State'}
outcomes.py:127 ALIAS,TEAM_FILES,SCHOOL_NAME,PREFIX,UNRESOLVED = ('alias table', 'team files', 'school name', 'prefix rule', 'unresolved')
quotes.py:42 MARKETS = ('h2h', 'spreads', 'totals')
quotes.py:43 SIDES = {'h2h': ('home', 'away'), 'spreads': ('home', 'away'), 'totals': ('over', 'under')}
quotes.py:44 SHARP = ('pinnacle', 'lowvig', 'betonlineag')
quotes.py:45 RETAIL = ('draftkings', 'fanduel', 'betmgm', 'williamhill_us', 'fanatics', 'betrivers', 'espnbet')
quotes.py:46 WINDOW = bulk.LOOKBACK
quotes.py:47 COARSE_MARGIN = timedelta(days=2)
quotes.py:48 COLUMNS = ['sport', 'season', 'event_id', 'kickoff', 'commence', 'home', 'away', 'snap', 'book', 'market', 'line', 'dec_a', 'dec_b', 'upd']
run.py:30 DAILY_NOTE = "F1 sees each game at 16:00 UTC on each of the 7 days before kickoff and, on busy days, also at every other game's close (each snapshot lists every game). A price gap shows up only if it is open at one of those moments, so gaps that last minutes, the kind Kaunitz et al. found with minute data and issue #53 describes, are mostly missed, and nothing here says how long any gap lasted."
run.py:34 PREREG = 'sharp-markets/docs/PRICE_ENGINE_PREREGISTRATION.md'
run.py:73 MIN_SCORE_SHARE = 0.95
run.py:136 RESULT_COLS = ['variant', 'bets', 'clv_pin_n', 'graded', 'pushes', 'games', 'ev_entry_pct', 'clv_pin_expected', 'clv_pin_cents', 'clv_pin_se', 'clv_pin_p', 'clv_pin_pts', 'clv_own_cents', 'clv_own_pts', 'seasons_positive', 'seasons_counted', 'seasons_20_closes', 'top_book', 'win_rate', 'roi', 'roi_lo', 'roi_hi', 'decision']
run.py:140 MOVED_COLS = ['variant', 'bets', 'clv_pin_n', 'clv_pin_same_n', 'clv_pin_cents_same', 'clv_pin_moved_n', 'clv_pin_cents_moved', 'clv_pin_cents', 'clv_pin_pts']
```
