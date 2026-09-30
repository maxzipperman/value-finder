# Betting splits, first test (H3): pre-registration

**Status: registered September 29, 2026, by the hub on the owner's standing instruction of September 29, 2026** (the hub decides research-protocol questions and reports them to the owner afterwards). Part of issue [#66](https://github.com/maxzipperman/value-finder/issues/66).

**Nothing has been downloaded.** This file is committed and pushed on its own before the dataset is downloaded. Nobody working on this test has seen a row of the file. The report ([`reports/h3_kaggle_mgm.md`](../reports/h3_kaggle_mgm.md)) will give the time this registration was pushed and the time the file was downloaded, so anyone can check the order.

From this commit on, changing any rule below is a dated amendment, made before the affected result is known.

## The question

The owner asked whether there is historical data on the share of bets and the share of money on each side of a line, and whether it tells us anything the closing price doesn't. The one free historical source is a Kaggle dataset of closing betting splits from one retail sportsbook in the NBA. This test asks one narrow thing of it: **at that book's close, does the split between tickets and money say anything that the book's own closing price hasn't already priced in?**

The idea behind it is common in betting media: when a side draws a bigger share of the money than of the tickets, the average bet on it is bigger, which is read as "sharp money". Nobody we know of has published a test of it.

## 1. The data

- **The file.** Kaggle dataset `caseydurfee/mgm-grand-nba-betting-data`, licence CC BY-SA 4.0: one file, `all_odds.csv`, about 1.6 MB. It is said to hold BetMGM's closing prices for NBA moneylines, spreads and totals, with each side's share of tickets (the file calls it "wager percentage") and share of money ("stake percentage"), and each side's result, for the seasons 2021-22 to 2025-26.
- **What kind of data it is.** One retail book. Closing figures only, with no timestamps. Scraped by a third party from Yahoo. It is not the market, and a single large bet at one book can move that book's money share.
- **The cut-off.** Games dated after January 31, 2026 are **left out of every test**. They fall in the validation period of the project's Kalshi study (`train_end: 2026-01-31` in `config/backtest.yaml` and in `config/sports/nba.yaml`), and they stay untouched: their results are not read, and their splits are not loaded into the project's database. The report counts how many rows the cut-off removes. The date used is the game date the file gives; if the file gives a time instead of a date, the date is taken in US Eastern time.
- **Sealed.** NBA 2026-27 is sealed and is not in the file.
- **Seasons.** A game dated in August or later belongs to the season that starts that year (a game on March 3, 2023 is in 2022-23). Regular season, play-in and playoffs are all included; they are not split apart.
- **Shares.** "Points" means percentage points. If the file gives shares as fractions (0.62 rather than 62), they are multiplied by 100.
- **Prices.** If the file gives American odds rather than decimal odds, they are converted to decimal.

## 2. What is tested: 14 variants, no more

For every market below, the **divergence** of a side is its share of money minus its share of tickets, in percentage points. A side with 60% of the money and 45% of the tickets has a divergence of +15.

**Family A, "money ahead of tickets" (9 variants).** For each of the three markets (moneyline, spread, total), and for each threshold k of 5, 10 and 15 points: back the side whose share of money exceeds its share of tickets by at least k points, at BetMGM's closing price. That is one bet per game at most. If both sides of a game meet the threshold (possible only if the file's shares don't add up), the game is left out of that variant and counted.

**Family B, the same idea without a threshold (3 variants).** For each of the three markets: a regression of (won minus fair chance) for the home side (the over, for totals) on the home side's divergence per 10 points, with an intercept and dummies for the tenth of the fair-chance scale the home side's fair chance falls in (0 to 10%, 10 to 20%, and so on up to 90 to 100%; tenths with no games are dropped, and one tenth is the baseline). The dummies are there because favourites and long shots can be mispriced for reasons that have nothing to do with the splits. The tested number is the coefficient on the divergence: how much more often the home side wins than its fair chance says, for each 10 points of divergence.

**Family C, "fade the public" (2 variants).** For spreads and totals: back the side that has 30% of the tickets or fewer, at BetMGM's closing price. If both sides have 30% or fewer (again possible only if the shares don't add up), the game is left out of that variant and counted.

Nothing else is computed from the results. There is no regular-season-only cut, no favourites-only cut, no cut by year, no other threshold and no other market.

## 3. The measure that decides

- **The fair chance** of a side is BetMGM's own closing price for that side with the book's margin removed proportionally: with decimal prices a and b for the two sides, the first side's fair chance is (1/a) / (1/a + 1/b).
- **The deciding measure** for families A and C is the mean, over the bets, of (won minus fair chance), where won is 1 for a win and 0 for a loss. A positive number means the backed sides won more often than BetMGM's closing price said they would. For family B it is the regression coefficient described above.
- **Left out:** pushes (neither side of a spread or total won) and any game with a missing figure in that market. A figure is missing when either side's closing price, share of tickets, share of money or result is blank or unreadable, or when a decimal price is 1.00 or less. A market whose two closing prices imply a book margin below 0% or above 20% is treated as having a missing figure too, because no book posts those prices on purpose. Every left-out game is counted by reason in the report.
- **Return at the closing price** (profit per unit staked, pushes left out) is reported beside the measure. It decides nothing.

## 4. The test

- **Two-sided.** A variant can pass by beating the fair chance or by falling short of it.
- **The standard error** for families A and C is the **wider** of two, as the project has done since the amendments of September 29 (nfl-weather amendment 7, cfb-weather amendment 5):
  - the plain one: the standard deviation of (won minus fair chance) over the bets, divided by the square root of the number of bets;
  - the one grouped by game date: bets on the same date share one group, with G dates in all; its square is (G / (G − 1)) times the sum over dates of the squared sum of (won minus fair chance minus the mean) on that date, divided by the square of the number of bets.
- **For family B** it is the wider of the HC1 standard error (robust to unequal spread) and the one grouped by game date (the usual grouped estimator with the small-sample factor (G / (G − 1)) × ((n − 1) / (n − k)), where k counts the regression's coefficients).
- **The p-value** is two-sided, from Student's t: on one less than the number of bets (families A and C) or n − k (family B) when the plain or HC1 error is the wider, and on G − 1 when the grouped one is the wider.

## 5. The bar

The project's running count of variants tested goes from **273 to 287** with this test. A variant passes only if **both**:

1. p < 0.05 / 287 = **0.000174**, and
2. the same sign in **at least 4 of the 5 seasons**: the season's own figure (the mean of won minus fair chance for families A and C; the same regression fitted on that season alone for family B) has the same sign as the figure over all seasons. A season with no bets, or a figure of exactly zero, does not count as the same sign.

Season-by-season figures are shown only for that sign check. No p-value or standard error is computed for a season.

*Note, September 29, 2026, added when this test merged, after its results were known. It corrects the project's count, not the rule above.* While this test was in review, another check (the academy check's opener grading, [#54](https://github.com/maxzipperman/value-finder/issues/54)) was counted on the main branch, taking the running count from 273 to 274 before this test's 14 were added. So the count after this test is **288**, not 287, and the bar is 0.05 / 288 = 0.0001736, which rounds to the same **0.000174**. No variant here came near either figure (the closest p was 0.032), so no verdict changes. The sentences above, the code and the report's figures are left as registered.

## 6. What is detectable

Before any result is seen: with a bar of p < 0.000174, a variant passes (half the time) only when its measure is about **3.75 standard errors** from zero. For a win-or-lose bet near even money, the standard error is close to 0.5 divided by the square root of the number of bets, n. So the smallest effect the bar could detect is about **3.75 × 0.5 / √n**, in units of win chance:

| Bets in the variant | Smallest detectable effect |
|---:|---:|
| 100 | 18.8 points |
| 300 | 10.8 points |
| 500 | 8.4 points |
| 1,000 | 5.9 points |
| 2,000 | 4.2 points |
| 3,000 | 3.4 points |
| 6,000 | 2.4 points |

"Points" here means percentage points of win chance: a 5.9-point effect means the backed sides win, say, 55.9% of the time when the price says 50%. For scale, a bettor who beats the close by 2 points is doing very well, and detecting a 2-point effect half the time would take about 8,800 bets. The file is expected to hold roughly 6,000 games before the cut-off, and families A and C use only the games whose splits cross a threshold, so **only large effects can pass this test**. A null result says the effect, if there is one, is smaller than this table; it does not say there is none.

For family B, the same formula is divided by the standard deviation of the divergence in 10-point units, which comes from the splits alone, not from any result. The report prints the smallest detectable effect for each of the 14 variants from its own n (and, for family B, the spread of its divergence), next to its result.

## 7. What each outcome means

- **Nothing passes.** Recorded as a null. It says closing splits at one retail book add nothing detectable to that book's own closing price in the NBA. It does not test football, and it does not test splits before the close.
- **Something passes.** A lead, not a rule. The next steps would be the same test against Pinnacle's close (that costs Odds API credits: the owner's decision) and a forward test. No rule is registered from this test and no money follows from it.
- **Either way,** no football splits data is bought on the strength of this test alone.

## 8. What this file cannot test

- Whether a line moved against the public ("reverse line movement"): the file has no opening figures.
- Anything about timing: the file has closing figures only, with no timestamps, so it can't say whether splits seen hours before the game would have helped.
- Whether the splits say anything beyond a sharper book's price: the benchmark is BetMGM's own close, not Pinnacle's.

## 9. Record

- Registered by the hub on the owner's standing instruction of September 29, 2026. This file is committed alone and pushed before the download.
- The code that runs it is `markets h3-kaggle` ([`src/markets/research/kaggle_h3.py`](../src/markets/research/kaggle_h3.py)), changed to match this file after this commit and before the download, with tests on a synthetic file.
- The report gives the registration commit's hash and time, the download time, and the file's sha256.
- Raw data never goes into git; the report holds aggregate numbers only.
