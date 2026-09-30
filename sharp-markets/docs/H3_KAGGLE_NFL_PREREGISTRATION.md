# Betting splits, NFL test (H3, NFL): pre-registration

**Status: written September 30, 2026, for the hub to register.** The hub decided the terms below on the owner's standing instruction; the owner said yes to the download on September 29, 2026. Issue [#75](https://github.com/maxzipperman/value-finder/issues/75), part of [#66](https://github.com/maxzipperman/value-finder/issues/66). The test is registered once this file is on GitHub and before the file is downloaded. The report ([`reports/h3_kaggle_nfl.md`](../reports/h3_kaggle_nfl.md)) records the commit that first added this file, its time, and the time of the download, so anyone can check the order.

**Nothing has been downloaded.** Nobody working on this test has seen a row of the NFL file. The only football figures anyone here has seen are the ones in the repo's own tables (the schedule and scores in `nfl-weather/data/processed/games.parquet`, and the Rule B replay in `nfl-weather/data/processed/mos_replay.parquet`).

From this commit on, changing any rule below is a dated amendment, made before the affected result is known.

Anything this file does not state follows the NBA registration ([`H3_KAGGLE_PREREGISTRATION.md`](H3_KAGGLE_PREREGISTRATION.md)): the measure that decides, the standard errors, Student's t, the handling of prices and margins, the sign check and what each outcome means. Those rules are restated below where the NFL test uses them, so this file can be read on its own.

## The question

The NBA test (14 variants) found nothing: at BetMGM's close, the split between tickets and money said nothing detectable that the book's own closing price hadn't already priced in. This test asks the same narrow question of the same book in the NFL: **at BetMGM's close, does the split between tickets and money say anything that the book's own closing price hasn't already priced in?**

## 1. The data

- **The file.** Kaggle dataset `caseydurfee/mgm-grand-nfl-betting-data`, licence CC BY-SA 4.0: one file, `all_odds.csv` (88 KB zipped, 358 KB unzipped). Its page says "2021-2025 NFL regular season odds and wagering percentages": BetMGM's closing prices for the 2021 to 2025 regular seasons, with each side's share of tickets ("wager percentage") and of money ("stake percentage"). Same author and, by its name and size, the same layout as the NBA file. About 1,350 games.
- **What kind of data it is.** One retail book. Closing figures only, with no timestamps. Scraped by a third party from Yahoo. It is not the market.
- **The layout.** The code reads the file on the NBA file's column names: `game_date`, `home_team`, `away_team`, and for spreads and totals `{market}_{side}_decimal_odds`, `_stake_percentage` (money), `_wager_percentage` (tickets), `_points` (the line) and `_won`, with sides `home` and `away` for spreads and `over` and `under` for totals. Moneyline columns are not needed. **If any of those columns is missing, the run stops before reading any figure and names every missing column.** The hub then adapts only the column mapping (which column holds which figure), by a dated note in this file, before any result is read. The same goes for the file's name inside the zip: it must be `all_odds.csv`.
- **Seasons.** An NFL season is named for the year it starts: a game dated in August or later belongs to that year's season, and one dated before August to the previous year's (a game on January 4, 2026 is in the 2025 season). The tested seasons are 2021 to 2025; within them, every game the file holds is tested, whatever its type (the report counts the game types from the repo's schedule), as the NBA test did.
- **No 2026 game is read.** A row dated in the 2026 season or later (dated August 1, 2026 or later) is counted by season and nothing else about it is read: not its teams, prices, shares or flags. The cut is there because the 2026 NFL season is a sealed holdout in the project's Odds API plan: [`config/odds5m.yaml`](../config/odds5m.yaml) marks the NFL window `2026` (September 1, 2026 to February 20, 2027) `sealed: true`, never analysed until a hypothesis about it is pre-registered, and this test is not that hypothesis. The repo's schedule and scores are read only for the seasons 2021 to 2025. A row before the 2021 season is counted and left out.
- **Shares and prices.** "Points" means percentage points. If the file gives shares as fractions (0.62 rather than 62), they are multiplied by 100. If it gives American odds rather than decimal odds, they are converted to decimal. Both are judged over the whole tested part of the file, as in the NBA test.
- **Shares at a threshold are rounded to 9 decimals before the comparison,** so a computer's arithmetic can't move a game across a threshold: family A is `round(money share − ticket share, 9) >= 10` and family C is `round(ticket share, 9) <= 30` (both in points, after any scaling from fractions). A side with 16.4% of the money and 6.4% of the tickets (9.999999999999998 in floating point) is 10 points ahead, as is one with 0.57 and 0.47 given as fractions. The same rounding applies wherever else a share meets a limit: the 10-point bands of section 7, the 0-to-100 range there, and the "adds to 100 (±1)" checks on the file.

### Three things declared now because the NBA file taught them

1. **Exact duplicate rows are dropped to one.** A row that repeats an earlier row in every column counts once. The report gives the number dropped. An unnamed row-index column (a column named `""` or `Unnamed: 0`, as pandas writes a running row number) is ignored in that comparison, since a running row number would make every row differ; the report names the column if there is one. Nothing else reads it. (If the same game appears on two rows that differ in any column, neither row is chosen over the other: both are left out and counted.)
2. **A game's result comes from the repo's own scores,** `nfl-weather/data/processed/games.parquet` (nflverse's schedule with final scores), at the file's own closing line. The home side of a spread covers when its points plus its line beat the away side's points; the over wins when the two teams' points add to more than the line. **The file's won flags are only a cross-check:** for every game whose line allows a result, the report counts how often the flags agree with the scores, disagree, or are blank. A disagreement changes nothing in the test.
3. **A bet that lands exactly on its line is a push and is left out,** counted by market.

### Joining the file to the repo's scores

- **Team names** are read through an explicit mapping to nflverse's codes, written in the code (`TEAM_NAMES` in [`kaggle_h3_nfl.py`](../src/markets/research/kaggle_h3_nfl.py)): each team's full name, its city or region, its nickname and Yahoo's short forms (`NY Giants`, `LA Rams`, `L.A. Chargers`). Case, full stops and extra spaces don't matter. Washington played as the Washington Football Team in 2021 and as the Commanders from 2022; both names, and "Washington", map to `WAS`. The Raiders (`LV`), the Rams (`LA`) and the Chargers (`LAC`) had moved before 2021, so their old names are not in the mapping. "New York" and "Los Angeles" on their own name two teams each (`NYG` and `NYJ`; `LA` and `LAC`), as do "NY" and "LA", so they are not in the mapping. **A two-team city name is resolved by one rule that reads no result:** it stands for whichever of its two codes has a game against the other named team (either team at home) within one day either side of the file's date in the repo's schedule, when exactly one of the two does. If neither does, or both do, or the other name is itself a two-team city name, the game is left out and counted ("two-team city name not resolved"); or the other name isn't in the mapping (then the game is counted under that unknown name, "team name not in the mapping"). The report counts each city name by what it resolved to. **Any other name that isn't in the mapping is never guessed:** the game is left out and the name is counted.
- **The join** matches the two teams and the date: the file's date, or one day either side of it (the file's date may be in a different time zone from the schedule's Eastern date). If no game matches with the file's home and away teams, the same two teams the other way round are tried (a neutral-site game may name its home side differently); the report counts those. The result is always taken for the file's own home side, from that team's own points. A game that matches nothing, or has no final score in the repo's table, is left out and counted.
- **Before the run that computes results,** the hub runs `uv run markets h3-kaggle --sport nfl --check-only`. It checks the columns, counts the rows by season, the duplicates, the names the mapping lacks, the city names and the games that don't join, and it counts the format of the joined games' figures: missing and unreadable lines, lines that don't mirror, whole-number lines, whether shares are fractions or percentages and how often each side's shares add to 100, whether prices are American or decimal, and the margins (the median and how many fall below 0% or above 20%). It also checks **the sign and mapping of the spread and total lines** against prices, never results, and prints the agreements and disagreements of each: (a) the file's home spread line against nflverse's closing `spread_line` in `games.parquet` (the home side's expected margin, so the file's home line should be about −`spread_line`, or +`spread_line` when the join swapped home and away): the same sign or the opposite, and how many are within 3 points; (b) the file's total line against `games.parquet`'s `total_line`, within 3 points or not; (c) if the file has moneyline prices, whether the side giving points on the spread is the moneyline favourite. A spread line whose sign is flipped, or a line read from the wrong side's column, changes every result and shows only here before the results run. It computes no result: it reads no score and no won flag. (The exact-duplicate check compares every column of a row as text, won flags included, only to see whether two rows are the same; no flag's value is read or counted.) Prices, shares and lines are read only for those counts.
- **What may change after the check, and only then.** If names are missing from the mapping or the join fails for a reason of format (a date written another way, say), the hub may add names to the mapping or adapt the date reading. If the check's format counts or line checks show that lines, shares or prices are being read wrongly, the hub may adapt how they are read: the column and format mapping only (which column holds which figure, the scale of the shares, the form of the prices, and the sign and mapping of the spread and total lines), never a rule, threshold or exclusion. Each such change is a dated note in this file, made before the run that computes results and based only on the check-only output. Nothing else may change. **The full run is not made until the check-only output has been read and any dated note made.** The full report shows the same format counts and line checks, from the same code.

## 2. What is tested: 6 variants, no more

For every market below, the **divergence** of a side is its share of money minus its share of tickets, in percentage points. A side with 60% of the money and 45% of the tickets has a divergence of +15. There are no moneylines in this test.

For **spreads** and for **totals**:

- **(A) Money ahead of tickets (2 variants).** Back the side whose share of money exceeds its share of tickets by at least 10 points (`round(money share − ticket share, 9) >= 10`), at BetMGM's closing price. One bet per game at most. If both sides of a game meet the rule (possible only if the file's shares don't add up), the game is left out of that variant and counted.
- **(B) The same idea without a threshold (2 variants).** A regression of (won minus fair chance) for the home side (the over, for totals) on the home side's divergence per 10 points, with an intercept and dummies for the tenth of the fair-chance scale the home side's fair chance falls in (0 to 10%, 10 to 20%, and so on up to 90 to 100%; tenths with no games are dropped, and one tenth is the baseline), as in the NBA test. The tested number is the coefficient on the divergence: how much more often the home side (the over) wins than its fair chance says, for each 10 points of divergence.
- **(C) Fade the public (2 variants).** Back the side with 30% of the tickets or fewer (`round(ticket share, 9) <= 30`), at BetMGM's closing price. If both sides qualify, the game is left out of that variant and counted.

Nothing else is computed from the results: no other threshold, no moneyline, no cut by season, week, favourite or weather.

## 3. The measure that decides

- **The fair chance** of a side is BetMGM's own closing price for that side with the book's margin removed proportionally: with decimal prices a and b for the two sides, the first side's fair chance is (1/a) / (1/a + 1/b).
- **The deciding measure** for families A and C is the mean, over the bets, of (won minus fair chance), where won is 1 for a win and 0 for a loss, from the repo's scores. A positive number means the backed sides won more often than BetMGM's closing price said they would. For family B it is the regression coefficient.
- **Left out of a market, counted by reason:** a missing figure (either side's closing price, share of tickets, share of money or line is blank or unreadable, or a decimal price is 1.00 or less); a margin below 0% or above 20%, which no book posts on purpose; lines that don't mirror (a spread whose two lines don't add to zero, or a total whose over and under lines differ, since the result depends on the line); and a push. Every left-out game is counted in the report.
- **Return at the closing price** (profit per unit staked, pushes left out) is reported beside the measure. It decides nothing.

## 4. The test

- **Two-sided.** A variant can pass by beating the fair chance or by falling short of it.
- **The standard error** for families A and C is the **wider** of two:
  - the plain one: the standard deviation of (won minus fair chance) over the bets, divided by the square root of the number of bets;
  - the one grouped by game date (the Eastern date of the game in the repo's schedule): with G dates, its square is (G / (G − 1)) times the sum over dates of the squared sum of (won minus fair chance minus the mean) on that date, divided by the square of the number of bets.
- **For family B** it is the wider of the HC1 standard error and the one grouped by game date (with the small-sample factor (G / (G − 1)) × ((n − 1) / (n − k)), where k counts the regression's coefficients).
- **The p-value** is two-sided, from Student's t: on one less than the number of bets (families A and C) or n − k (family B) when the plain or HC1 error is the wider, and on G − 1 when the grouped one is the wider.

## 5. The bar

The project's running count of variants tested goes from **288 to 294** with this test. (The hub's brief said 287 to 293. The count on the main branch had become 288 by the time this file was committed, because the academy check's opener grading, [#54](https://github.com/maxzipperman/value-finder/issues/54), was counted while the NBA test was in review; 288 to 294 gives the stricter bar, the cautious choice.) A variant passes only if **both**:

1. p < 0.05 / 294 = **0.000170**, and
2. the same sign in **at least 4 of the 5 seasons** (2021 to 2025): the season's own figure (the mean of won minus fair chance for families A and C; the same regression fitted on that season alone for family B) has the same sign as the figure over all seasons. A season with no bets, or a figure of exactly zero (up to the rounding of a computer's arithmetic, as the NBA test settled), does not count as the same sign.

Season figures are shown only for that sign check. No p-value or standard error is computed for a season.

## 6. What is detectable

Stated from the sample sizes before any data is seen. With a bar of p < 0.000170, a variant passes (half the time) only when its measure is about **3.76 standard errors** from zero. For a bet near even money the standard error is close to 0.5 divided by the square root of the number of bets, n, so the smallest effect the bar can detect is about **3.76 × 0.5 / √n**, in points of win chance:

| Bets in the variant | Smallest detectable effect |
|---:|---:|
| 50 | 26.6 points |
| 100 | 18.8 points |
| 200 | 13.3 points |
| 300 | 10.9 points |
| 400 | 9.4 points |
| 500 | 8.4 points |
| 1,000 | 5.9 points |
| 1,250 | 5.3 points |

A 10-point effect means the backed sides win 60% of the time when the price says 50%. Detecting a 2-point effect half the time would take about 8,800 bets.

**The expected sample.** Five regular seasons are 1,359 games in the repo's schedule. The NBA file had splits for about 93% of its games; pushes remove a few more from spreads and totals, so about 1,200 to 1,300 games a market are expected to be tested. How many of them each rule selects can only be guessed before the download. If the NFL's splits look like the NBA file's, the shares of games selected would be:

| Variant | Share of games in the NBA file | Expected bets (of 1,250) | Smallest detectable |
|---|---:|---:|---:|
| A: spread, money − tickets ≥ 10 | 14.7% | about 180 | about 14 points |
| A: total, money − tickets ≥ 10 | 3.1% | about 40 | about 30 points |
| C: spread, tickets ≤ 30% | 32.5% | about 410 | about 9 points |
| C: total, tickets ≤ 30% | 80.4% | about 1,000 | about 6 points |
| B: spread, per 10 points | every game | about 1,250 | about 7 points per 10 points of divergence |
| B: total, per 10 points | every game | about 1,250 | about 13 points per 10 points of divergence |

(Family B's figure is the formula above divided by the spread of the divergence in 10-point units, taken here from the NBA test's own printed detectable effects; the report prints each variant's from its own n and spread.) NFL bettors may split differently, so the counts could be several times larger or smaller. With 200 to 400 bets a variant, the bar can only see an effect of about 9 to 13 points of win chance (7 points needs about 720 bets). On NBA-like shares, the two family-A variants could only see about 14 points (spreads) and 30 points (totals), and family B about 7 points (spreads) and 13 points (totals) per 10 points of divergence. That is wider than the "7 to 10 points" in the hub's brief. **This test cannot prove a small edge, and a null is the expected result.** A null says the effect, if there is one, is smaller than the "Smallest detectable" column of the report; it does not say there is none.

## 7. A description with no result in it (0 variants)

For the games that met **Rule B's wind trigger**, the report shows the distribution of the share of tickets on the over: the number of games in each 10-point band (0 to 10%, 10 to 20%, up to 90 to 100%), and the number with no share. The games are those the repo's own table marks as triggers: the forecast replay of Rule B on NWS MOS, `nfl-weather/data/processed/mos_replay.parquet`, column `mos_signal` (an outdoor game, at a stadium with a MOS station within 40 km, whose MOS wind forecast was at least 15 mph at a lead of 1 to 3 days; see `nfl-weather/scripts/mos_replay.py`), for the seasons 2021 to 2025 (153 games in that table: 34, 30, 27, 29 and 33 by season; 13 of them are playoff games, 1, 2, 3, 2 and 5 by season, which a regular-season file may not hold). Only the game ids and seasons are read from that table. Beside it, the same count for every joined game, for scale.

Why that table and that column: Rule B's trigger is a forecast, a wind of at least 15 mph forecast 1 to 3 days before the game, not the wind that blew. `mos_signal` is that trigger on forecasts as they were issued (NWS MOS). The board's own forecasts (`fc1_wind` to `fc3_wind` in `games.parquet`, from Open-Meteo) are missing for all of 2021 and 2022 and nearly all of 2023, so they can't mark the trigger games across the five seasons. The observed wind is the realized weather, not the trigger, so the games it flags are not the games Rule B would have bet.

**Counts only.** No result is read for these games in this description, no figure is compared with it, and it tests nothing, so it adds nothing to the count. It describes where the public stood on windy games; it says nothing about Rule B.

## 8. What each outcome means

- **Nothing passes.** Recorded as a null. It says closing splits at one retail book add nothing detectable to that book's own closing price in the NFL, within what 1,300 games can see. It does not test splits before the close or college football.
- **Something passes.** A lead, not a rule. The next steps would be the same test against a sharper close (that costs Odds API credits: the owner's decision) and a forward test. No rule is registered from this test and no money follows from it.
- **Either way,** no football splits data is bought on the strength of this test.

## 9. What this file cannot test

- Whether a line moved against the public (reverse line movement): the file has no opening figures.
- Anything about timing: closing figures only, with no timestamps.
- Whether the splits say anything beyond a sharper book's price: the benchmark is BetMGM's own close.

## 10. Record

- Written September 30, 2026, on the hub's brief (issue #75), on the owner's yes of September 29 to the one download. The hub registers it by putting it on GitHub before the download.
- The code that runs it is `uv run markets h3-kaggle --sport nfl` ([`src/markets/research/kaggle_h3_nfl.py`](../src/markets/research/kaggle_h3_nfl.py), which uses the NBA test's download, credential and statistics in [`kaggle_h3.py`](../src/markets/research/kaggle_h3.py)), with tests on a small synthetic file built by hand (`tests/test_kaggle_h3_nfl.py`). The NBA test and its report are unchanged. The download is cached in `data/raw/nfl/kaggle_mgm/{date}/`, with its time, size and sha256; a rerun reads the cache.
- The report gives the registration commit and its time, the download time, the file's sha256, and the sha256 of the two repo tables the run reads (`games.parquet` and `mos_replay.parquet`, each whole file), so the inputs can be checked. For now the code reads the registration commit from git (the commit that first added this file). After registering, the hub pins the commit, its time and the time GitHub records for it in `REGISTRATION` in the code, as the NBA module's `REGISTRATION` does; until then those are blank and nothing is guessed.
- The count in `STATUS.md` goes from 288 to 294 when the hub makes the run, not before.
- Raw data never goes into git; the report holds aggregate numbers only. Unlike the NBA run, this run writes nothing to `data/markets.duckdb`.
