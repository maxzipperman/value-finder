# Player props, the line against the median: pre-registration (issue [#10](https://github.com/maxzipperman/value-finder/issues/10))

**Status: registered September 30, 2026 (Pacific) by the hub, on the owner's standing instruction of September 29, 2026, by the merge of pull request 82, before the October 1 day-one probe and the F3a pull; no prop price had been pulled and no prop row had been joined to an outcome. The two marked choices are taken as written (the Act condition read as five checks; the 2026 confirmation criteria of section 2.2). One addition at registration: the committed `nfl-weather/data/processed/player_week.parquet` holds rows for the sealed 2026 season, so every reader of it for this test filters on season 2025 or earlier as it reads, before anything is counted.**

- **Registered:** *(the hub fills this in: date and time, Pacific, before the October 1 probe and pull; the registering commit)*
- **Count and bar at registration:** *(the hub fills this in: the running count in STATUS.md at registration, plus variants already run but not yet in STATUS.md; the bar is p < 0.05 / that count. Sections 2.9, 4 and 5 use this field.)* As of writing, for illustration: 274 in STATUS.md on `main`, plus [PR 70](https://github.com/maxzipperman/value-finder/pull/70)'s H3 test (14 variants, already run, PR open) = 288, p < 0.05 / 288 = 0.000174; other registrations in flight add theirs.
- **2026 confirmation criteria, and what the 2026 read decides:** *(the hub accepts the drafter's proposed defaults in section 2.2, the criteria and the mapping, or amends them, at registration)*
- **Confirmed at registration:** the day-one probe and the F3a pull had not run, and no F3a row had been joined to an outcome *(the hub signs this line)*

It becomes the registered rule when the hub merges it, and that has to happen **before the October 1 probe and pull**. The owner's note on #10 (September 28; [`STATUS.md`](../STATUS.md), the October 20 gate decisions) asks for registration before any F3a prop row is joined to an outcome, dated before the October pull. The requirement to register before the probe as well is this file's own: it follows from the departure in section 2.4, which takes the book rule off the probe. From the registering commit on, changing anything here is a dated amendment, made before the affected result is known. The book (section 2.4) is not a registration input: it is the output of a registered rule applied to F3a's coverage counts, recorded afterwards in a dated note (section 8).

When this draft was written, nobody had seen a prop price. F3a, the 2025 season of NFL props at T−24h and the close, is pulled on Thursday, October 1, 2026, after the day-one probe. No 2026-season row was read. Nothing on disk joins a posted prop line to an outcome.

## The short version

- **The question.** Do posted NFL receiving-yards and rushing-yards lines sit above the median of the outcome, so that the under wins more often than its price implies?
- **The data.** F3: NFL props at T−24h and the close, 2023–25, regular season and playoffs. F3a (the 2025 season) comes first. F3b (2023–24, plus 2026 games as sealed data) is bought only if F3a passes the gate in section 3.
- **The grade.** Excess under rate: the under's actual win rate minus the probability its closing price implies after the vig is removed by the power method. This rule bets *at* the close, so it is graded on win rate and ROI at that price, not on closing-line value (CLAUDE.md, "Grade on price").
- **Count.** 1 variant. It has been in the running count since September 29 (section 4), so this file adds none. The bar is the header's "count and bar at registration" (as of writing, 274 in STATUS.md, 288 with PR 70's run test).
- **The sealed 2026 season** confirms, against criteria fixed at registration (section 2.2). It is opened once, for every hypothesis registered by then.
- **If the F3b gate fails,** #10 is set aside with no Act or Drop verdict (section 3).
- **Power.** F3a alone can clear the bar only for an edge of about 4 to 7 points of under rate (3.6 to 6.7 across the cases of section 5), at or near the pre-check's ceiling for this mechanism (about 4.4). The F3b gate is a spending gate, not evidence: an efficient market passes it about half the time (section 5).
- **For the hub, two marked choices:** the Act condition is read as five checks, not six cells (section 2.9, with the power of each in section 5), and the 2026 confirmation criteria are a proposed default (section 2.2).

## 1. The draft this file carries over

The draft was written on September 29, 2026, before any prop line was pulled or seen, as idea 7 of [`strategy-research/README.md`](../strategy-research/README.md#7-prop-structure-the-line-against-the-median). Its free pre-check is [`strategy-research/props_median_check.py`](../strategy-research/props_median_check.py) ([#41](https://github.com/maxzipperman/value-finder/issues/41)). The draft says it "goes into a pre-registration file, unchanged or by dated amendment, before F3's rows are first joined to outcomes". Its table, quoted as written:

> **Pre-registration draft (1 variant; running count 192).** Written September 29, 2026, before any prop line was pulled or seen.
>
> | | |
> |---|---|
> | **Hypothesis** | Posted lines sit above the empirical median of the player's outcome, so the under wins more often than its price implies. |
> | **Sample** | F3, NFL 2023–25 regular season and playoffs. The 2026 season is sealed and opened only to confirm. |
> | **Markets** | Primary, pooled into one test: `player_reception_yds` and `player_rush_yds`, the two markets where the pre-check finds skew. Controls, reported but not tested: `player_pass_yds` (no skew) and `player_receptions` (little). The mechanism predicts no edge in the controls. |
> | **Line and price** | Each player's main line and both prices at the close, the last F3 snapshot at least 5 minutes before kickoff (`bulk.close_time`). Pinnacle, if the day-one probe shows it quotes the market in at least 80% of player-games; otherwise DraftKings. Alternate-ladder lines are out. |
> | **Metric** | Excess under rate: Σ(winᵢ − pᵢ) / n, where pᵢ is the under's probability after removing the vig by the **power method**. The additive and multiplicative methods are reported next to it. One-sided z test, variance Σpᵢ(1 − pᵢ), also with standard errors clustered by game. ROI at the actual under price is reported next to it. |
> | **Pushes and voids** | Whole-number lines that land exactly, and props voided because the player didn't play, are left out of n and counted. |
> | **Mechanism readout** | Descriptive, not graded: the line minus the player's same-season median (known only after the season), and the share of lines above it. |
> | **Decision** | **Act** (a paper forward test on the 2026 sealed season; never staked on this result alone): pooled p < 0.05 / 192, *and* a positive excess with p < 0.01 in each of 2023, 2024 and 2025 and in each primary market ([plan review](plan-review-2026-09-28.md), section 3). **Drop:** the pooled excess is at or below zero, or one market or one season carries it. **Otherwise:** no action; re-read once 2026 is unsealed. |
> | **Secondary** | The same statistic at T−24h, and the line move from T−24h to the close. Reported, not a second test. |

Section 2 restates each row as the rule. Everything in it is the draft's unless marked **Added** or **Changed**. Each of those says why. Where the draft could be read two ways, the stricter reading is taken and named, with one exception: the Act condition (section 2.9) takes the sentence's natural reading, because the brief keeps the draft's decision rule. Section 7 lists every change in one place.

## 2. The rule

### 2.1 Hypothesis

Posted lines sit above the empirical median of the player's outcome, so the under wins more often than its price implies. *(The draft's words.)*

The mechanism, from the draft and the pre-check: a bet that simply wins or loses depends only on where the line sits against the *median* of the outcome. Yardage outcomes are right-skewed. The pre-check found the season mean above the season median by 7.6% for WR1 receiving yards and 3.2% for RB1 rushing yards, and no skew for passing yards; receptions were close to symmetric (2023–25, [README](../strategy-research/README.md#props-how-far-the-mean-sits-above-the-median-added-september-29-2026-41)). So the under has an edge only if posted lines sit above the median, towards the mean.

### 2.2 Sample and the sealed 2026 holdout

- **Tested sample:** F3, NFL 2023–25, regular season and playoffs. *(The draft's.)* "2025" means the 2025 NFL season, which includes its playoff games played in January and February 2026. The same applies to 2023 and 2024.
- **F3a** is the 2025 season: 285 games (272 regular season, 13 playoff), six markets, two snapshots (T−24h and the close), 10 × 6 × 2 × 285 = 34,200 credits. **F3b** is 2023–24 and the 2026 games played, bought only through the gate in section 3.
- **The 2026 season is sealed and opened only to confirm.** *(The draft's.)* Sealed means every prop row for a 2026-season game, from any source: F3b's 2026 part, the live props log (`nfl-weather/data/forward/props_log.csv`, rows marked `sealed=True`, [`ops/LIVE_USES.md`](../ops/LIVE_USES.md)) and any March 2027 completion. Nothing joins a sealed row to an outcome, summarizes its prices, or compares its lines with anything until the seal is opened.
- **The sealed 2026 props are opened once, for every hypothesis registered by then.** *(Added, from decision D3 of the model-layer memo, [`strategy-research/model-layer-memo-2026-09-29.md`](../strategy-research/model-layer-memo-2026-09-29.md) on `main` (PR 72): once #10 opens the 2026 props to confirm itself, they can't confirm anything registered later. The sentence keeps later options open at no cost.)*
- **Added: what confirms.** The draft doesn't say what result on 2026 confirms. The criteria are fixed **before any F3a row is joined to an outcome**, and the seal isn't opened without them. *(Why: fixing them any later would let them be chosen after some of the 2023–25 result is known.)*
  - **Proposed default, added by the drafter; the hub accepts or amends it at registration.** On the 2026-season rows, graded by sections 2.4 to 2.8 with the book fixed in 2.4: the same statistic (the excess under rate at the power-method close, the two primary markets pooled), its p-value from the larger of the two standard errors (2.6), one-sided **p < 0.05**, **and** a positive excess in each primary market. All three hold: confirmed. Anything else: not confirmed.
  - **Which close, for 2026.** The graded rows are the historical close as defined in 2.4 (`bulk.close_time`, the 5-minute grid point 5 to 10 minutes before kickoff), from F3b's 2026 part and the March 2027 completion. A 2026 game with no historical close row is excluded and counted. The live props log's close is a different snapshot: a poll landing 2 to 20 minutes before kickoff (`CLOSE_WINDOW` in [`nfl-weather/nflweather/live.py`](nflweather/live.py)), so it may be up to 15 minutes earlier or 8 minutes later than the historical close. It is not graded, not pooled with the historical rows and doesn't fill a missing one; it is reported next to the 2026 result at the same opening.
- **Added: when the seal opens, and what the 2026 read decides.** The seal opens once, only after the 2026 season's last game and the March 2027 completion pull. If that completion isn't bought, it opens on whatever historical-close 2026 rows exist, and the report says so.
  - **Proposed mapping, added by the drafter; the hub accepts or amends it at registration** (header). Act and confirmed: a candidate for a 2027 paper forward test, never staked on this result alone. Act and not confirmed: Drop. Otherwise and confirmed: no action, reported. Otherwise and not confirmed: Drop. No branch puts money in; that needs its own forward test and gate.

### 2.3 Markets

- **Primary, pooled into one test:** `player_reception_yds` and `player_rush_yds`. *(The draft's.)*
- **Controls, reported but not tested:** `player_pass_yds` and `player_receptions`. The mechanism predicts no edge in them. *(The draft's.)* **Added:** no p-value on a control is used for any decision, and a control can't stand in for a primary market. *(Why: a control that looked good would otherwise be a second, uncounted test.)*
- F3's other two markets, `player_kicking_points` and `player_field_goals`, belong to [#21](https://github.com/maxzipperman/value-finder/issues/21) and are not part of this file.

### 2.4 Line, price and book

- **Snapshot:** the close, the last F3 snapshot at least 5 minutes before kickoff (`bulk.close_time` in [`sharp-markets/src/markets/oddsapi/bulk.py`](../sharp-markets/src/markets/oddsapi/bulk.py): the last 5-minute grid point at least 5 minutes before kickoff). *(The draft's.)* **Added:** kickoff is the event's latest listed kickoff (`commence_time` from the latest `/events` sighting before kickoff, `bulk.build_schedule`), and the close is taken relative to it. If the game's kickoff moved earlier than the graded snapshot (nflverse's `games.csv` kickoff, `gameday` and `gametime`, US Eastern, at or before the snapshot's time), the game is excluded and counted, so no in-play price is graded.
- **Line and prices:** each player's main line and both prices. Alternate-ladder lines are out. *(The draft's.)* **Added:** the main line is the one listed under the market key itself (not an `_alternate` key). If the chosen book lists more than one line for a player at the close, the one whose prices are closest to even is used: the smallest |pᵢ − 0.5|, with pᵢ the under's probability after the power-method de-vig (2.5). If two are equally close, the line is excluded and counted. *(Why: the draft assumes one main line; this settles the rare exception without looking at outcomes.)*
- **Book:** Pinnacle, if it quotes the market in at least 80% of player-games; otherwise DraftKings. *(The draft's rule.)* **Changed, where the 80% comes from:** the draft reads it from the day-one probe. The probe (`bulk.billing_probes`) makes two prop calls on one 2024 game, inside the tested sample: one with all 10 `us10` books (Pinnacle among them) and one Pinnacle-only. One game can't measure coverage. The figure is instead computed mechanically from **F3a's coverage counts at the close snapshot**: in each primary market, the player-games with a main line at Pinnacle, over the player-games with a main line at any `us10` book in that snapshot. A player-game here is (event id, the `description` as returned), counted before any roster matching. It counts which books list a line and reads no price level and no outcome. **Stricter reading:** Pinnacle is used only if it clears 80% in **each** of the two primary markets, and then one book is used for all four markets; otherwise DraftKings is used for all four. The resulting book, with the two coverage figures, is recorded after the F3a pull, and before any F3a row is joined to an outcome, in a dated note (section 8), as the output of this rule; the note changes nothing else. **The book is fixed on F3a's coverage and not revisited when F3b arrives, whatever F3b's coverage.** A player-game with no line at the chosen book is excluded and counted; no second book fills it in. *(Why: "the market" is singular and could be read per market; mixing books across markets, re-choosing on later data, or filling gaps from another book, would add a choice made after seeing the data.)*

### 2.5 Removing the vig

- **The graded probability pᵢ comes from the power method.** *(The draft's.)* **Added, the formula:** with decimal odds d_over and d_under, the implied probabilities are q = 1/d. Find k > 0 such that q_overᵏ + q_underᵏ = 1; then pᵢ = q_underᵏ. *(Why: the draft names the method but not the formula; this is the standard form.)*
- **Reported next to it, not graded:** the additive method, pᵢ = q_under − (q_over + q_under − 1)/2, and the multiplicative method, pᵢ = q_under / (q_over + q_under). *(The draft's; formulas added.)*

### 2.6 Metric and test

- **Excess under rate:** Σ(winᵢ − pᵢ) / n over the graded lines, where winᵢ is 1 if the under won and 0 if it lost. *(The draft's.)*
- **Test:** one-sided z test, z = Σ(winᵢ − pᵢ) / √Σpᵢ(1 − pᵢ), and also with standard errors clustered by game. *(The draft's.)* **Added, the clustered form:** SE = √[G/(G−1) · Σ_g (Σ_{i in g}(winᵢ − pᵢ))²] / n over G games, and z = excess / SE. The game sums are deliberately **not centred** on the estimated excess: the SE is taken under the null of no excess, which makes it slightly conservative. It is not statsmodels' CR1 cluster-robust SE, which centres the residuals; an implementer should not substitute it. The p-value, not a rounded z threshold, decides. **Stricter reading:** every p-value in the decision rule is taken from **the larger of the two standard errors**. *(Why: the draft computes both and doesn't say which decides; the registered keep-test amendments settled the same question for the weather rules by taking the wider interval.)*
- **ROI at the actual under price**, reported next to it: Σ(winᵢ · (d_under,i − 1) − (1 − winᵢ)) / n, one unit a line. *(The draft's; formula added.)*

### 2.7 Pushes, voids and other exclusions

- **Whole-number lines that land exactly, and props voided because the player didn't play, are left out of n and counted.** *(The draft's.)*
- **Added, "didn't play":** outcomes come from `nfl-weather/data/processed/player_week.parquet` (nflverse weekly stats). A player with no row for that game is treated as not having played, and the line is void. A player with a row but no attempt in the market is graded (0 yards, the under wins). *(Why: the table can't tell an inactive player from one who played and recorded nothing. Voiding those lines drops some real under wins, which works against the hypothesis, so it is the cautious error.)*
- **Added, matching players:** prop rows name the player (`description`). The name → `player_id` map is built from a season roster (one row per player per team-season: name, team, `player_id`; for example nflverse's season rosters), with no outcome column, and committed before the first join. A prop row matches when its name maps to exactly one player on either team in its game that season. A row with no match, or more than one, is **unmatched**. A matched player with no `player_week` row for that game is **void** (didn't play, above). The two are separate exclusion reasons, each counted.
- **Added:** every exclusion is counted by reason and listed on request, as the project's scorers do (CLAUDE.md, "Log, don't drop"): push, void, unmatched player, no line at the chosen book, two equally close main lines, missing price, kickoff moved before the snapshot (2.4), and, for 2026, no historical close row (2.2).

### 2.8 Mechanism readout

Descriptive, not graded: the line minus the player's same-season median (known only after the season), and the share of lines above it. *(The draft's.)* **Added, the same-season median:** the median of the player's outcome in that market over every game of that season (regular season and playoffs) in which he has a `player_week` row, whether or not a line was posted for it. It is reported per primary market and per season, as two numbers: the mean of (line − same-season median), and the share of lines strictly above it (a line equal to the median is not above).

### 2.9 Decision

Read once, on 2023–25, after F3b is in and joined. If the F3b gate fails, this section isn't read (section 3).

- **Act** (a paper forward test on the 2026 sealed season; never staked on this result alone) only if both hold. *(The draft's.)*
  1. The pooled excess over the two primary markets and three seasons has **p < the bar in the header's "count and bar at registration"** (as of writing, 0.05 / 274 = 0.000182 from STATUS.md, or 0.05 / 288 = 0.000174 with PR 70's run test). **Changed:** the draft wrote 0.05 / 192, the count on September 29. The project judges every analysis against the running count at the time it is registered, and the plan table already moved this rule to 0.05 / 198 ([`odds-api-credits.md`](../strategy-research/odds-api-credits.md#data-use-plan)). The stricter current count applies. Section 4 says how it is fixed.
  2. A positive excess with p < 0.01 in each of 2023, 2024 and 2025 and in each primary market. *(The draft's.)* **Reading registered, marked for the hub: five checks.** Each season with the two primary markets pooled (2023, 2024, 2025: three checks) and each primary market with the three seasons pooled (receiving yards, rushing yards: two checks), each with a positive excess and p < 0.01 (larger SE, 2.6). This is the sentence's natural reading, and the brief keeps the draft's decision rule. **Considered and rejected: six season × market cells**, each at p < 0.01. See section 7 for why, and section 5 for the power of each.
- **Drop:** the pooled excess is at or below zero, or one market or one season carries it. *(The draft's.)* **Added, "carries it":** with that one market, or that one season, removed, the pooled excess of what remains is at or below zero.
- **Otherwise:** no action; re-read once 2026 is unsealed. *(The draft's.)* That re-read happens at the single opening of the seal (section 2.2), under the confirmation criteria fixed at registration.

**Added:** the Act, Drop and Otherwise branches are read only on the full 2023–25 sample. The F3a read on 2025 alone decides only the F3b purchase (section 3). *(Why: condition 2 needs 2023 and 2024, which F3a doesn't contain.)*

### 2.10 Secondary

The same statistic at T−24h, and the line move from T−24h to the close. Reported, not a second test. *(The draft's.)* T−24h is the F3 snapshot at the 5-minute grid point at or before 24 hours before kickoff (`bulk.event_snapshots`, offset 24).

## 3. The F3b gate

As [`strategy-research/odds-api-credits.md`](../strategy-research/odds-api-credits.md#gated-inside-the-month-2031260-at-most-decided-by-about-october-20) has it. The row's cell text is quoted exactly; the bold on **F3b** is added, and the table's header is dropped. Its columns are: ID | Pull | Credits (upper bound) | 2026 share; on Oct 1 | Gate (act-or-drop), so "34,200; 5,760" is the 2026 share and the part pulled on October 1. The credits doc is the named source; `GATES["F3b"]` in [`strategy-research/odds_5m.py`](../strategy-research/odds_5m.py) carries a differently worded copy of the same gate.

> **F3b** | NFL props, the same markets and snapshots as F3a, 2023–24 and the 2026 games played | 102,600 | 34,200; 5,760 | Only if, on the 2025 slice (F3a), graded exactly as #10's pre-registration draft says (the excess under rate over the power-method de-vigged close price, receiving and rushing yards pooled, passing yards and receptions as controls): the pooled excess is positive, and the posted line sits above the player's same-season median in both primary markets. Before that read, the draft goes into a pre-registration file unchanged or by dated amendment. If the lines sit at the median or the excess is at or below zero, F3b moves to March and only the kicking markets (#21) stay in play.

**What result of this test passes or fails it.** The read is on F3a (2025) only, graded by sections 2.4 to 2.8, by about October 20, and not before this file is registered.

| | Passes the gate (F3b is bought in October) | Fails the gate (F3b moves to March; only the kicking markets stay in play; #10 is set aside) |
|---|---|---|
| Pooled excess under rate, receiving and rushing yards, 2025 | Above zero (the point estimate; no p-value is required) | At or below zero |
| Line against the same-season median, **in each primary market** | Both readout numbers of section 2.8 point above: the mean of (line − same-season median) is above zero **and** more than half of the lines sit strictly above the median | Either number at or below its mark in either market |
| Result | Both rows pass | Anything else |

- **Stricter reading, the median condition:** "sits above" is read as both the mean difference above zero and a majority of lines above. *(Why: the readout gives both numbers, and they can disagree when a few lines sit far above.)*
- **Stricter reading, mixed results:** the credits doc names two ways to fail (lines at the median, or the excess at or below zero). Any other result that doesn't meet both pass conditions, such as lines above the median in one market only, also fails.
- **A failed gate sets #10 aside with no Act or Drop verdict.** As the credits doc says, F3b moves to March and only the kicking markets (#21) stay in play, so the 2023–24 yardage props aren't bought and section 2.9 is never read. It is read, as registered here and with the book of 2.4 unchanged, only if 2023–24 yardage props are bought later by a separate, dated decision.
- **The gate read reports, and decides nothing else:** the pooled excess with both standard errors and its p-value, each market's excess, ROI, and the readout. None of it is a test. The 2025 season stays in the 2023–25 sample the decision reads.
- **What the gate is worth:** see section 5. It rarely blocks a real edge, but an efficient market passes it about half the time.

## 4. Variants and the bar

- **Variants in this file: 1**, the pooled primary test. The controls, the T−24h statistic, the other two de-vig methods, the ROI, the readout and the F3b gate read are reported and decide no claim of an edge, so they count 0. The five checks of section 2.9 are conditions on the same test, not new hypotheses.
- **That 1 is already in the running count.** The README's running count added it on September 29 ("The props pre-registration draft below (idea 7) adds 1 … counted separately to be safe"), and the 5M plan's table lists #10 as "4 (+1 for the draft, in the 198)". The count went 198 → 200 → 232 → 233 → 271 → 273 → 274 after that, so the 274 in [`STATUS.md`](../STATUS.md) on `main` includes it. **This file adds 0 variants and is not counted twice.**
- **The bar is one field, in the header,** filled by the hub at registration: the running count in STATUS.md at that moment, plus variants already run but not yet in STATUS.md. **Variants already run count whether or not their PR has merged.** Sections 2.9, 4 and 5 refer to that field.
- **As of writing (September 30, 2026), for illustration:** 274 in STATUS.md on `main`, p < 0.05 / 274 = 0.000182. [PR 70](https://github.com/maxzipperman/value-finder/pull/70)'s H3 test, 14 variants, has been run and isn't in that count, so the field would read 288, p < 0.05 / 288 = 0.000174, plus whatever other registrations in flight have run by then.
- The owner hasn't decided whether a small registered family of tests may use its own bar (the plan review's proposal, question 3 of the model-layer memo). This file uses the single running count. A family bar would be an amendment made before registration.

## 5. Power, from the sample sizes alone

No prop line exists on disk, so the number of posted lines is an assumption. Everything below comes from game counts and stated assumptions; no price and no outcome was read for it.

**Assumptions.**

- **Games:** F3a is 285 (the 2025 season). 2023–25 is 855.
- **Primary lines a game at the chosen book** (receiving plus rushing yards), three cases:
  - **Low, 6:** a thin book (Pinnacle-like).
  - **Proxy, 9.8:** the model-layer memo's usage proxy, 2,342 rusher games with 8+ carries and 6,041 receiver games with 4+ targets in 855 games of 2023–25, (2,342 + 6,041) / 855 = 9.8. Receiving yards are 72% of these lines, rushing yards 28%: about 7.1 receiving and 2.7 rushing lines a game.
  - **High, 14:** a broad book (DraftKings-like).
  - The low and high cases are split between the markets in the proxy's proportions (an assumption): 4.3 receiving and 1.7 rushing lines a game at 6, 10.1 and 3.9 at 14.
- **Excluded lines** (voids, pushes, unmatched): 5%.
- **pᵢ near 0.5**, so each line's variance is about 0.25.
- **Correlation within a game** (ρ, between the residuals winᵢ − pᵢ of lines in the same game) is unmeasured. The design effect is 1 + (m − 1)ρ, where m is the number of lines a game **in the test at hand**: all primary lines for the pooled test and for a season's check over both markets (9.8 in the proxy case), but only that market's lines for a single-market check or cell (7.1 receiving, 2.7 rushing). Cases: ρ = 0 (independent), 0.02, 0.05 and 0.10.
- **The bar:** the header field; for illustration, the 274 in STATUS.md as written: one-sided α = 0.05 / 274 = 0.000182, z = 3.564. 80% power adds z = 0.842, so the minimum detectable difference (MDD) = (3.564 + 0.842) × SE = 4.406 × SE, with SE = 0.5 / √(n / design effect). At 288 (with PR 70's test) the MDDs rise by less than 0.1 point.

**Worked example, the proxy case on F3a.** n = 285 × 9.8 × 0.95 = 2,653 lines. Independent: SE = 0.5 / √2,653 = 0.97 points, MDD = 4.406 × 0.97 = 4.3 points of under rate. With ρ = 0.05: design effect = 1 + 8.8 × 0.05 = 1.44, SE = 0.97 × √1.44 = 1.16, MDD = 5.1 points.

**F3a (2025) alone: the pooled test at the bar, 80% power.**

| Lines a game | n | MDD, ρ = 0 | ρ = 0.02 | ρ = 0.05 | ρ = 0.10 | MDD at p < 0.05, ρ = 0.05 |
|---|---|---|---|---|---|---|
| 6 | 1,624 | 5.5 | 5.7 | 6.1 | 6.7 | 3.4 |
| 9.8 | 2,653 | 4.3 | 4.6 | 5.1 | 5.9 | 2.9 |
| 14 | 3,790 | 3.6 | 4.0 | 4.6 | 5.4 | 2.6 |

MDD is in points of under rate (a true 54% under against a 50% price is 4 points).

**How big an edge could be.** If books set lines at the season mean and priced the under at a fair 50%, the pre-check's under rates (55.0% for WR1 receiving yards, 53.0% for RB1 rushing yards) give a pooled edge of about 0.72 × 5.0 + 0.28 × 3.0 = 4.4 points. That is a ceiling for this mechanism, not a forecast: nobody can set a line at a season mean they don't yet know, and a book that shades the line towards the median, or prices the under shorter, removes part of it. So F3a on its own detects, at the bar, only an edge at or near that ceiling. It isn't meant to decide anything, and under section 2.9 it can't.

**The F3b gate on F3a.** The gate asks only for a positive point estimate (with the median condition). The chance the excess comes out positive, with SE from the table (proxy, ρ = 0.05, SE = 1.16 points):

| True excess | 0 (no edge) | 1 point | 2 points | 3 points |
|---|---|---|---|---|
| Chance the pooled excess is positive | 50% | 80% | 96% | 99% |

Across all twelve cases above the figures run 74–89% at 1 point, 91–99% at 2, and 98–100% at 3. The median condition doesn't tighten it much: the pre-check's caution found outcomes fall below a player's trailing median 56–57% of the time, so a line set from past games tends to sit above the same-season median even when it is efficient. **So an efficient market passes the gate close to half the time,** and a real edge of 2 points or more almost always passes. It is a spending filter, which is what the credits doc asks of it.

**The full test, 2023–25 (855 games), pooled at the bar, 80% power.**

| Lines a game | n | MDD, ρ = 0 | ρ = 0.05 |
|---|---|---|---|
| 6 | 4,874 | 3.2 | 3.5 |
| 9.8 | 7,960 | 2.5 | 3.0 |
| 14 | 11,372 | 2.1 | 2.7 |

**The chance of Act, both conditions** (the pooled bar and p < 0.01 in each check), for a true edge the same in every season and market. Each check's design effect uses the lines a game in that check (see the assumptions). The pooled test and the checks are treated as independent and their chances multiplied, which is roughly right across seasons and slightly pessimistic otherwise:

| Lines a game, ρ | Five checks (registered): 3 / 4 / 5 / 6 points | Six cells (rejected): 3 / 4 / 5 / 6 points |
|---|---|---|
| 6, 0 | 5 / 39 / 80 / 96% | 0 / 1 / 5 / 18% |
| 6, 0.05 | 2 / 23 / 66 / 91% | 0 / 0 / 3 / 15% |
| 9.8, 0 | 31 / 83 / 98 / 100% | 0 / 6 / 26 / 56% |
| 9.8, 0.05 | 11 / 58 / 91 / 99% | 0 / 3 / 19 / 48% |
| 14, 0 | 65 / 97 / 100 / 100% | 2 / 21 / 56 / 84% |
| 14, 0.05 | 26 / 79 / 98 / 100% | 1 / 11 / 42 / 74% |

Under the six-cell reading the binding cell is rushing yards in a single season: in the proxy case about 742 lines, where p < 0.01 at 80% power needs (2.326 + 0.842) × 0.5 / √742 = 5.8 points at ρ = 0, and 6.1 at ρ = 0.05 (design effect 1 + 1.7 × 0.05). That is above the mechanism's ceiling of about 4.4 points, so six cells would make Act close to unreachable. Under the registered five checks, in the proxy case each season's check needs 3.1 points (ρ = 0) to 3.7 (ρ = 0.05), rushing yards over three seasons 3.4 to 3.5, and receiving yards 2.1 to 2.4; a 4-point edge is found about 58 to 83% of the time. The pooled test alone, at 2.1 to 3.5 points, sits below the ceiling.

These figures assume one line per player per market at one book. The real counts are known once F3a lands; the correlation within a game can be measured on F3a after registration and is reported, not used to change any threshold.

## 6. What was and wasn't read for this draft

- **Read:** `CLAUDE.md`, `STATUS.md`, `strategy-research/README.md` (idea 7, the pre-check and the running count), `strategy-research/props_median_check.py`, `strategy-research/odds-api-credits.md`, `strategy-research/plan-review-2026-09-28.md` (section 3), the model-layer memo (on `main` since PR 72), `strategy-research/odds_5m.py` (`GATES`), `sharp-markets/src/markets/oddsapi/bulk.py` and `sharp-markets/config/odds5m.yaml` (F3's definition, the close, the schedule and the day-one probe), `ops/LIVE_USES.md` and `nfl-weather/nflweather/live.py` (the live log's close window), and `nfl-weather/scripts/build_player_week.py` (the outcome table's columns).
- **Not read:** any prop price, any 2026-season row, any outcome row. No API was called. The power figures use game counts and the memo's published usage counts only; the script that computed them is not in the repo, and its arithmetic is stated in section 5.

## 7. Every change from the draft, in one place

| Where | Change | Kind | Why |
|---|---|---|---|
| 2.2 | "The sealed 2026 props are opened once, for every hypothesis registered by then." | Added | Model-layer memo, decision D3 |
| 2.2 | The 2026 confirmation criteria are fixed before any F3a row is joined to an outcome; a proposed default is written here (same statistic, larger SE, p < 0.05, positive in each primary market), **added by the drafter for the hub to accept or amend at registration** | Added | The draft doesn't say what confirms; fixing it later would let it be chosen after 2023–25 is known |
| 2.2 | The seal opens once, after the 2026 season and the March 2027 completion (or on the historical-close rows that exist, said so); a proposed mapping from the 2023–25 branch and the 2026 result to an outcome, **added by the drafter for the hub to accept or amend at registration** | Added | The draft says "re-read once 2026 is unsealed" but not when, or what follows |
| 2.2 | 2026 is graded at the historical close; the live log's close (2 to 20 minutes out) is reported, not graded | Added | The two closes are different snapshots |
| 2.3 | No control p-value decides anything | Added | Keeps the controls from becoming uncounted tests |
| 2.4 | Close taken from the latest listed kickoff; a game whose kickoff moved before the snapshot excluded and counted | Added | No in-play price is graded |
| 2.4 | Main line defined (closest to even = smallest \|pᵢ − 0.5\| after the power de-vig); ties excluded | Added | The draft assumes one main line |
| 2.4 | The 80% coverage figure comes from F3a's coverage counts at the close, not the day-one probe; the book is recorded afterwards in a dated note as the rule's output, and not revisited on F3b | **Changed (departure)** | The probe makes two prop calls (all 10 books, then Pinnacle only) on one 2024 game, inside the tested sample, and one game can't measure coverage; registering before the probe keeps the book a mechanical rule |
| 2.4 | Pinnacle only if 80% in each primary market; one book for all markets; no fill-in from other books | Stricter reading | "The market" is ambiguous |
| 2.5, 2.6 | Formulas for the power, additive and multiplicative methods, the clustered SE (not centred: null-based, not statsmodels' CR1) and ROI | Added | The draft names them |
| 2.6 | The larger of the two SEs decides every p-value | Stricter reading | The draft computes both and doesn't say which decides |
| 2.7 | "Didn't play" = no `player_week` row (void); names matched through a season roster committed before the first join (unmatched); both counted separately, with every other exclusion | Added | Settles voids with the data on disk, erring against the hypothesis; keeps a matching failure from passing as a void |
| 2.8 | Same-season median defined; both readout numbers reported | Added | The draft names the readout |
| 2.9 | Bar 0.05 / 192 → the header's count at registration, including variants already run but not yet in STATUS.md (274 in STATUS.md as written; 288 with PR 70) | Changed | The project's rule; the plan already moved it to 198 |
| 2.9 | **Marked for the hub.** "In each of 2023, 2024 and 2025 and in each primary market" registered as five checks (three seasons, two markets). The six-cell reading was considered and **rejected** | Natural reading (not the stricter one) | The brief keeps the draft's decision rule, and five checks is how the sentence reads. Six cells would need about 5.8 to 6.1 points in rushing yards for a single season, above the mechanism's ceiling of about 4.4: at ρ = 0.05 and 9.8 lines a game, Act's chance at 3 / 4 / 5 / 6 points is 0 / 3 / 19 / 48% for six cells against 11 / 58 / 91 / 99% for five checks (section 5) |
| 2.9 | "Carries it" defined | Added | The draft names it |
| 2.9 | Act, Drop and Otherwise read only on 2023–25 | Added | Condition 2 needs three seasons |
| 3 | Gate's median condition needs both readout numbers in both markets; any other result fails | Stricter reading | The credits doc names two failures only |
| 3 | A failed gate sets #10 aside with no Act or Drop verdict, unless 2023–24 yardage props are bought later by a separate decision | Added | The credits doc: on failure only the kicking markets stay in play |

## 8. Dated notes

*(After the F3a pull and before any F3a row is joined to an outcome: the book chosen by the rule in section 2.4, with its two coverage figures, dated. It records the rule's output and changes nothing else.)*
