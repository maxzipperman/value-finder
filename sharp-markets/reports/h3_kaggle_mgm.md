# Betting splits, first test (H3): NBA money versus tickets at BetMGM's close

Registered in [`docs/H3_KAGGLE_PREREGISTRATION.md`](../docs/H3_KAGGLE_PREREGISTRATION.md) before the file was downloaded. Data: Kaggle `caseydurfee/mgm-grand-nba-betting-data` (CC BY-SA 4.0). Part of issue [#66](https://github.com/maxzipperman/value-finder/issues/66). **n_variants_tested = 14**; the project's running count goes from 273 to 287, so the bar is p < 0.05 / 287 = 0.000174.

## The finding

**None of the 14 variants passes the bar** (p below 0.000174 and the same sign in at least 4 of the 5 seasons): at BetMGM's close in the NBA, from 2021-22 to January 2026, the split between tickets and money says nothing detectable that BetMGM's own closing price hadn't already priced in. The closest was the moneyline regression (the home side won 0.9 points less often than its fair chance for every 10 points by which its share of money beat its share of tickets), with p = 0.032, about 185 times too large for the bar; 2 of the 14 were below an ordinary 0.05, where chance alone would give about 0.7. The test could only have detected effects of about 2.8 points of win chance or more in its biggest variants, and far more in the thin ones, so a small edge of the size that matters in betting is not ruled out.

## Limits

- **One retail book.** BetMGM's own tickets and money, not the market's. One large bet can move a retail book's money share.
- **Closing figures only, no timestamps.** Whether a line moved against the public (reverse line movement) and anything about timing can't be tested: the file has no opening figures.
- **The benchmark is BetMGM's own close,** with the margin removed proportionally, not Pinnacle's.
- **Scraped by a third party from Yahoo.** Provenance is a caveat; the checks under "The file itself" are what we could verify.
- **Games after January 31, 2026 are left out of everything** (82 rows): they are the validation period of the Kalshi study. The registered code counts those rows and uses nothing else from them. No result after the cut-off was computed (the notes below describe a direct look at the raw file, for its dates and team names).
- **Only large effects are detectable.** See the "Smallest detectable" column: a null here means any effect is smaller than that, not that there is none.
- **NBA only.** Nothing here tests football.

## Results

Differences, standard errors and detectable effects are in percentage points of win chance (for family B, per 10 points of divergence). "Won − fair" is how much more often the backed side won than BetMGM's closing price, margin removed, said it would. Signs by season run 2021-22, 2022-23, 2023-24, 2024-25, 2025-26 (to January 31); "·" is a season with no bets, and "0" a season whose figure is zero, which counts as neither sign. The return at the close decides nothing.

### Family A: back the side whose share of money exceeds its share of tickets by at least k points

| Variant | n | Win rate | Mean fair chance | Won − fair | SE plain | SE by date | Wider | p | Bar | Passes | Signs by season | Same sign | Smallest detectable | Return at the close |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| A: moneyline, money − tickets ≥ 5 | 3,662 | 36.6% | 37.5% | -0.94 | 0.75 | 0.72 (861 dates) | plain | 0.210 | 0.000174 | no | − − − + + | 3 of 5 | 3.10 | -6.22% |
| A: moneyline, money − tickets ≥ 10 | 2,486 | 33.4% | 34.6% | -1.17 | 0.90 | 0.85 (812 dates) | plain | 0.192 | 0.000174 | no | − − − + + | 3 of 5 | 3.76 | -8.22% |
| A: moneyline, money − tickets ≥ 15 | 1,658 | 30.7% | 32.9% | -2.22 | 1.09 | 1.05 (724 dates) | plain | 0.042 | 0.000174 | no | − − − − − | 5 of 5 | 4.61 | -9.52% |
| A: spread, money − tickets ≥ 5 | 2,201 | 51.2% | 50.0% | +1.14 | 1.07 | 1.06 (775 dates) | plain | 0.286 | 0.000174 | no | + + + − + | 4 of 5 | 4.00 | -2.37% |
| A: spread, money − tickets ≥ 10 | 818 | 52.0% | 50.0% | +1.97 | 1.75 | 1.75 (464 dates) | plain | 0.261 | 0.000174 | no | + − + + − | 3 of 5 | 6.56 | -0.75% |
| A: spread, money − tickets ≥ 15 | 305 | 49.2% | 50.0% | -0.82 | 2.86 | 2.97 (209 dates) | grouped | 0.783 | 0.000174 | no | + − + + − | 2 of 5 | 10.75 | -6.16% |
| A: total, money − tickets ≥ 5 | 876 | 48.1% | 49.9% | -1.82 | 1.68 | 1.70 (441 dates) | grouped | 0.286 | 0.000174 | no | − − − + + | 3 of 5 | 6.34 | -8.33% |
| A: total, money − tickets ≥ 10 | 174 | 45.4% | 49.8% | -4.39 | 3.76 | 3.69 (130 dates) | plain | 0.245 | 0.000174 | no | − − − + + | 3 of 5 | 14.23 | -13.45% |
| A: total, money − tickets ≥ 15 | 36 | 50.0% | 50.2% | -0.18 | 8.38 | 8.35 (30 dates) | plain | 0.983 | 0.000174 | no | + − 0 − · | 2 of 5 | 31.28 | -5.44% |

### Family B: the same idea without a threshold (regression with fair-chance tenths)

| Variant | n | Win rate | Mean fair chance | Coefficient per 10 points | SE plain (HC1) | SE by date | Wider | p | Bar | Passes | Signs by season | Same sign | Smallest detectable | Return at the close |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| B: moneyline, per 10 points (home side) | 5,565 | 55.4% | 55.9% | -0.91 | 0.42 | 0.41 (878 dates) | plain | 0.032 | 0.000174 | no | − − − − − | 5 of 5 | 1.54 | no bet |
| B: spread, per 10 points (home side) | 5,566 | 49.6% | 49.9% | +1.11 | 0.88 | 0.88 (878 dates) | plain | 0.210 | 0.000174 | no | + − + + + | 4 of 5 | 3.31 | no bet |
| B: total, per 10 points (over) | 5,564 | 50.4% | 50.3% | -2.59 | 1.67 | 1.66 (878 dates) | plain | 0.122 | 0.000174 | no | − − − + + | 3 of 5 | 6.31 | no bet |

### Family C: fade the public (back the side with 30% of the tickets or fewer)

| Variant | n | Win rate | Mean fair chance | Won − fair | SE plain | SE by date | Wider | p | Bar | Passes | Signs by season | Same sign | Smallest detectable | Return at the close |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| C: spread, tickets ≤ 30% | 1,807 | 52.2% | 50.0% | +2.18 | 1.18 | 1.15 (664 dates) | plain | 0.063 | 0.000174 | no | + + + − + | 4 of 5 | 4.42 | -0.29% |
| C: total, tickets ≤ 30% | 4,475 | 49.5% | 49.8% | -0.22 | 0.75 | 0.76 (863 dates) | grouped | 0.769 | 0.000174 | no | + − − − + | 3 of 5 | 2.81 | -5.29% |

### Season figures (used only for the sign check; no standard error or p-value is computed for a season)

| Variant | 2021-22 | 2022-23 | 2023-24 | 2024-25 | 2025-26 |
|---|---|---|---|---|---|
| A: moneyline, money − tickets ≥ 5 | -1.76 (n 855) | -2.27 (n 891) | -0.44 (n 661) | +0.14 (n 866) | +0.63 (n 389) |
| A: moneyline, money − tickets ≥ 10 | -2.65 (n 567) | -1.37 (n 643) | -2.47 (n 454) | +0.98 (n 583) | +0.12 (n 239) |
| A: moneyline, money − tickets ≥ 15 | -3.87 (n 398) | -0.59 (n 464) | -4.69 (n 300) | -0.16 (n 359) | -3.03 (n 137) |
| A: spread, money − tickets ≥ 5 | +1.81 (n 548) | +0.50 (n 560) | +2.13 (n 433) | -0.56 (n 439) | +2.50 (n 221) |
| A: spread, money − tickets ≥ 10 | +6.24 (n 210) | -0.02 (n 286) | +5.33 (n 141) | +0.41 (n 125) | -8.92 (n 56) |
| A: spread, money − tickets ≥ 15 | +3.87 (n 78) | -7.75 (n 142) | +7.11 (n 42) | +8.10 (n 31) | -0.17 (n 12) |
| A: total, money − tickets ≥ 5 | -3.29 (n 328) | -6.25 (n 204) | -4.62 (n 141) | +2.87 (n 162) | +23.00 (n 41) |
| A: total, money − tickets ≥ 10 | -1.19 (n 64) | -10.93 (n 44) | -17.74 (n 31) | +7.86 (n 31) | +25.00 (n 4) |
| A: total, money − tickets ≥ 15 | +20.10 (n 10) | -13.30 (n 8) | 0.00 (n 12) | -16.84 (n 6) | — (n 0) |
| B: moneyline, per 10 points (home side) | -1.73 (n 1,260) | -1.02 (n 1,246) | -0.78 (n 1,014) | -0.30 (n 1,319) | -1.24 (n 726) |
| B: spread, per 10 points (home side) | +2.87 (n 1,260) | -1.14 (n 1,245) | +3.04 (n 1,015) | +0.78 (n 1,320) | +2.18 (n 726) |
| B: total, per 10 points (over) | -1.85 (n 1,260) | -8.43 (n 1,244) | -4.93 (n 1,015) | +1.86 (n 1,319) | +16.02 (n 726) |
| C: spread, tickets ≤ 30% | +2.21 (n 475) | +2.28 (n 492) | +4.26 (n 288) | -1.08 (n 400) | +6.47 (n 152) |
| C: total, tickets ≤ 30% | +1.04 (n 867) | -0.63 (n 1,005) | -1.17 (n 806) | -1.92 (n 1,164) | +3.01 (n 633) |

### Games left out, by market and reason

Out of 5,999 games dated on or before 2026-01-31.

| Market | Games tested | missing figure | margin below 0% or above 20% | both sides marked won | push |
|---|---|---|---|---|---|
| moneyline | 5,565 | 434 | 0 | 0 | 0 |
| spread | 5,566 | 433 | 0 | 0 | 0 |
| total | 5,564 | 435 | 0 | 0 | 0 |

Games where both sides met a family A or C rule (left out of that variant): none.

### Closest to the bar

Variants with p below an ordinary 0.05, none of which comes near the bar:
- B: moneyline, per 10 points (home side): the moneyline regression (the home side won 0.9 points less often than its fair chance for every 10 points by which its share of money beat its share of tickets); p = 0.032, 185 times the bar; the same sign in 5 of 5 seasons.
- A: moneyline, money − tickets ≥ 15: backing the moneyline side with at least 15 points more of the money than of the tickets (it won 2.2 points less often than its fair chance); p = 0.042, 238 times the bar; the same sign in 5 of 5 seasons.

## What it means

**Nothing passes: recorded as a null.** Closing splits at one retail book add nothing detectable to that book's own closing price in the NBA. This does not test football, and it does not test splits before the close.

Either way, no football splits data is bought on the strength of this test alone.

## The file itself

- **Columns (40):** an unnamed first column, `game_id`, `game_date`, `away_team`, `home_team`, `pregame_odds`, `total_over_points`, `total_over_stake_percentage`, `total_over_wager_percentage`, `total_over_odds`, `total_over_decimal_odds`, `total_over_won`, `total_under_points`, `total_under_stake_percentage`, `total_under_wager_percentage`, `total_under_odds`, `total_under_decimal_odds`, `total_under_won`, `money_away_odds`, `money_away_decimal_odds`, `money_away_stake_percentage`, `money_away_wager_percentage`, `money_away_won`, `money_home_odds`, `money_home_decimal_odds`, `money_home_stake_percentage`, `money_home_wager_percentage`, `money_home_won`, `spread_away_points`, `spread_away_odds`, `spread_away_decimal_odds`, `spread_away_stake_percentage`, `spread_away_wager_percentage`, `spread_away_won`, `spread_home_points`, `spread_home_odds`, `spread_home_decimal_odds`, `spread_home_stake_percentage`, `spread_home_wager_percentage`, `spread_home_won`.
- **Rows:** 6,081 in all; 82 dated after 2026-01-31 (counted, nothing else read); 0 with an unreadable date; 5,999 tested.
- **Shares** were read as percentages; prices as decimal odds.
- **Columns with one value on every tested row:** an unnamed first column (always "0").
- **Duplicated games** (same date, home and away team): 12; duplicated game ids: 12; rows that repeat an earlier row in every column: 12. They are counted as the file gives them (so twice); that few can't move any result.
- **Opening figures:** none. The `pregame_odds` column repeats the closing spread and total as text: the spread agrees with the line columns in 5,969 of 5,985 games and the total in 5,882 of 5,997 (2 unreadable). The test never uses the lines themselves.
- **Pushes:** the file marks no spread or total as a push (both sides lost). 90 spreads and 74 totals closed on a whole number, where a push can happen. 4 spreads have a blank result; 2 of them closed on a whole number (−13 and 3), so those are probably pushes the file left blank. All 4 are left out as missing figures, so no result depends on whether they were pushes. No total has a blank result. The file has no final scores, so whether any other whole-number game was a push can't be checked.
- **Prices:** the test uses the file's decimal prices as given. They mostly agree with the file's American odds; moneylines: 632 of 11,998 differ by more than 0.01 (at most 0.05); spreads: 10 of 11,994 differ by more than 0.01 (at most 0.02); totals: 20 of 11,998 differ by more than 0.01 (at most 0.02). The most common mismatches are American -145 given as decimal 1.70 (where -145 is 1.69; 169 times), American -350 given as decimal 1.30 (where -350 is 1.29; 164 times), American -130 given as decimal 1.78 (where -130 is 1.77; 104 times). An error of 0.02 in a favourite's price moves its fair chance by a fraction of a point.
- **Dates:** every game id carries a date; it matches the `game_date` column on 5,999 of 5,999 tested rows.
- **Team names that don't resolve** against `config/teams/nba.csv`: "New York" (418 appearances). Team names play no part in the test, so these games stay in it; they only get no team code in the `splits` table and can't join to a Kalshi game.
- **Games that join to a Kalshi game** (same Eastern date, away and home team): 744. The closing splits of every tested game are written to the `splits` table of the database this run used (`data/markets.duckdb` in the checkout where it ran; see the notes below for this run).

| Season | Rows tested | Games | First date | Last date | Games missing any split | Rows after the cut-off |
|---|---|---|---|---|---|---|
| 2021-22 | 1,331 | 1,319 | 2021-10-19 | 2022-06-16 | 72 | 0 |
| 2022-23 | 1,304 | 1,304 | 2022-10-18 | 2023-06-12 | 62 | 0 |
| 2023-24 | 1,318 | 1,318 | 2023-10-24 | 2024-06-17 | 304 | 0 |
| 2024-25 | 1,320 | 1,320 | 2024-10-22 | 2025-06-22 | 1 | 0 |
| 2025-26 | 726 | 726 | 2025-10-21 | 2026-01-31 | 0 | 82 |

| Market | Games | Missing splits | Tickets add to 100 (±1) | Money adds to 100 (±1) | Ticket sums, min to max | Money sums, min to max | Missing or impossible price | Margin below 0% | Margin above 20% | Median margin | Decimal prices, min to max | Missing result | Push | Both won | Lines that don't mirror |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| moneyline | 5,999 | 434 | 100.0% | 100.0% | 100.00 to 100.01 | 99.98 to 100.02 | 0 | 0 | 0 | 4.60% | 1.01 to 18.50 | 0 | 0 | 0 | 0 |
| spread | 5,999 | 432 | 100.0% | 100.0% | 100.00 to 100.00 | 100.00 to 100.00 | 2 | 0 | 0 | 4.71% | 1.17 to 5.25 | 4 | 0 | 0 | 0 |
| total | 5,999 | 435 | 100.0% | 100.0% | 100.00 to 100.00 | 99.98 to 100.02 | 0 | 0 | 0 | 4.71% | 1.17 to 5.25 | 0 | 0 | 0 | 0 |

## Record

- **Registration:** commit `ea635ecf1628955ebc806a5d487ba1e968c90b76`, committed 2026-09-29T23:05:39Z; GitHub records the branch created with it at 2026-09-29T23:05:40Z (UTC), before the download.
- **The code for the registered test:** commit `b4cd484c1c440ad6cdc9746b51ed790935200ca6`, on GitHub at 2026-09-29T23:22:30Z (UTC), before the download.
- **Download:** 2026-09-29T23:22:41Z (UTC), 392,024 bytes.
- **The file's sha256** (the zip as downloaded): `0fcad0af76c52733cf3d4bf24adf3698f21d5bd3ff528d81fa74673a1f49a06b`.
- **Variants:** 14 (9 in family A, 3 in B, 2 in C); running count 273 → 287; bar p < 0.000174; the smallest detectable effect is 3.75 × 0.5 / √n.
- Command: `uv run markets h3-kaggle` in `sharp-markets/`.


## Football splits on Kaggle

*Written by hand on September 29, 2026 from Kaggle's metadata. The run keeps this section when it rewrites the report.*

**One likely source for the NFL, none for college football.** The search went through the project's own code (`search()` and `dataset_files()` in `kaggle_h3.py`, read-only and cached): 18 search terms (betting splits; public betting; betting percentages; NFL betting; college football betting; consensus picks; sports insights; action network; money percentage; ticket percentage; handle percentage; NFL betting trends; wagering percentages; mgm grand nfl; ncaaf betting; college football odds; public money betting; bet percentage), 148 distinct datasets in the results, and file lists for the 6 that could plausibly be football odds or splits. **Nothing was downloaded.** Kaggle's interface gave no description and no column list for any dataset (it gave none for the NBA file either), so what follows comes from each dataset's title, subtitle, file names and sizes.

| Dataset | Owner | Size | Licence | Last update | What its page says | Seasons | Share of tickets | Share of money | Opening figures |
|---|---|---|---|---|---|---|---|---|---|
| `caseydurfee/mgm-grand-nfl-betting-data` | Casey Durfee, who made the NBA file | 88 KB zipped; one file, `all_odds.csv`, 358 KB | CC BY-SA 4.0 | February 5, 2026 | "2021-2025 NFL regular season odds and wagering percentages" | 2021 to 2025, regular season only | Almost certainly: same author, same file name and the same size per game as the NBA file (about 263 bytes a game in both), whose tickets column is `*_wager_percentage` | Almost certainly (`*_stake_percentage` in the NBA file) | Almost certainly not: the NBA file has closing figures only |

Checked and not splits data:

- `tobycrabtree/nfl-scores-and-betting-data` (spreadspoke; CC BY-NC-SA 4.0; updated February 11, 2026): NFL scores with the closing spread and total (`spreadspoke_scores.csv`). No splits.
- `willvernon/nfl-scores-and-lines` (Apache 2.0; March 6, 2024): NFL scores, lines, stadiums and teams. No splits.
- `oliviersportsdata/nfl-sample-2018-2026` (CC BY-NC-SA 4.0; September 15, 2026): timestamped odds for 18 games, 8 of them Super Bowls. A sample of odds; no splits.
- `oliviersportsdata/us-sports-master-historical-closing-odds` (CC BY-NC 4.0; March 21, 2026): 50-row samples of closing odds for nine sports, the NFL and college football among them. Closing odds only.
- `scottfree/sports-lines` (CC0; November 8, 2017): small files of game summaries and lines for the NFL, college football and college and pro basketball. No splits.
- **College football:** no dataset with a share of tickets or money came up under any term.

**What the NFL file would take.** It is free under the same token, but this task allowed one download, so it was not fetched. Like the NBA file it is one retail book at the close, so it could not test a line moving against the public. Five regular seasons are about 1,350 games: a test on every game could only detect about 5 points of win chance or more, and a subset such as Rule B's windy games far more. Any test on it would need its own registration first, and the owner's rule stands that no football splits data is *bought* on the strength of the NBA result.

## Choices made after seeing the file

Three choices were made after the file was downloaded. Each is shown here both ways; none changes the finding.

1. **Reading the dates** (before any result was computed, commit `b4c2e38`). The file writes every date as `2021-10-19-10:00`, which the first run's loader couldn't read, so that run tested no games. The loader now reads the first ten characters, which match the date in each game id on every tested row. The other way tests nothing at all.
2. **Keeping the games with an unresolved team name** (the same commit, also before any result). "New York" (the Knicks) is not in `config/teams/nba.csv`. The code written before the download dropped such games; the fix keeps them, because team names play no part in the registered test, which leaves out only pushes and games with a missing figure. With them (as reported): the smallest p of the 14 is 0.032. Without them (the independent review's figure): 0.022. Nothing passes either way.
3. **What counts as a figure of exactly zero** (after the results were seen, at review). The registration says a season whose figure is exactly zero doesn't count toward the sign check. One season figure, family A, totals, k = 15, 2023-24 (12 bets), came out of the arithmetic as −0.0000000000000000185: zero, up to the rounding of decimal fractions in a computer. The first version of this report counted it as a minus, giving 3 of 5 seasons with the same sign; it now counts as zero, giving 2 of 5. The variant fails either way (p = 0.983).

## Notes on this run

- **The running count is 288, not 287** (note added when this test merged, September 29, 2026, after the results). While this test was in review, the academy check's opener grading ([#54](https://github.com/maxzipperman/value-finder/issues/54)) was counted on the main branch, taking the count from 273 to 274 before this test's 14 were added. The bar is then 0.05 / 288 = 0.0001736, which rounds to the same 0.000174 used above; each "times the bar" figure would be about 0.3% larger. No variant came near either figure, so no verdict changes. The figures above are left as the registered code printed them.
- **Every tested number above is from the first run that computed results.** The review's rerun (September 29, from the cached file, no request to Kaggle) changed one cell of the results, the sign count in choice 3 above, and some wording under "The file itself".
- **After the results were seen,** only the description of the file was extended (duplicates, pushes, opening figures, price mismatches, missing splits by season). No tested number changed, and no other cut was computed by this project's code.
- **The raw file was also opened directly,** outside the registered code, while the loader could not yet read its dates: to see the date format and to count the team names that don't resolve. That count ("New York", 424 appearances, in the commit message of `b4c2e38`) covered all 6,081 rows, the 82 after the cut-off included; over the tested rows it is 418. Team names are neither results nor splits, and no result after the cut-off was computed then or since. But nothing in the code stopped that look from reading those rows' other columns.
- **An independent review** recomputed all 14 variants with its own code (pandas, scipy and statsmodels, not this project's code) and matched every figure in the tables, cell for cell: the 70 season figures, the games left out, the 744 games that join to Kalshi, and the smallest p (0.032). It also recomputed the smallest p of the 14 under four other ways of handling the file, after the results were known: dropping the 12 duplicated rows (0.036), using the American odds instead of the decimal prices (0.031), dropping the "New York" games (0.022), and cutting family B's fair chances into ten equal-sized groups instead of tenths (0.027). None comes near the bar. They decide nothing and are listed so they aren't hidden.
- **The `splits` table.** This run used a copy of the live `data/markets.duckdb` in a worker's worktree, so the closing splits of the 5,999 tested games are in that copy only. The live database has no `splits` table until `uv run markets h3-kaggle` is run in the live checkout. Copy `dataset.zip` and `download.json` into its `data/raw/nba/kaggle_mgm/2026-09-29/` first, so the run reads them and makes no second download (it then rewrites this report with the same content).
- **Pushes.** The first version of this report gave NBA push rates ("roughly 3%" and "2%") with no source, and guessed that the file records pushes as a win for one side. The file points the other way: 2 of its 4 spreads with a blank result closed on a whole number. The paragraph under "The file itself" now says only what the file shows.
- **The token, after review.** The review found that the first version's check on where to send the token could be fooled: a redirect to `https://evil.example\@www.kaggle.com/x` reads as Kaggle's address to Python's URL parser, but requests connects to evil.example, and the token would have gone with it. It would take Kaggle itself sending such a redirect, and nothing suggests it happened: in the real download Kaggle redirected to its storage host, which got no credential. The code now sends the credential with the first request only, to the fixed Kaggle API address as requests will actually connect to it, and never on a redirect, whatever its host; addresses with a backslash, a space or an '@' before the path are refused. This was tested against a fake server only: no request has gone to Kaggle since the change.
- **Times on GitHub** are from GitHub's own record of the branch (the repository activity API), not from this computer's clock: the branch was created with the registration commit at 23:05:40 UTC, and the code commit arrived at 23:22:30 UTC, 11 seconds before the download (23:22:41 UTC).
- **The missing splits** fall mostly in December 2023 and January 2024 (294 of the 434 games with no moneyline splits): a gap in the scrape. Those games have prices and results but no splits, so they are left out as registered.
- **The two moneyline variants closest to the bar lean the same way in every season:** on moneylines, the side with more of the money than of the tickets won a little less often than its fair chance. Family A's moneyline bets are mostly underdogs (a mean fair chance of 33 to 38%), and removing the margin in proportion may overstate an underdog's chance, so part of that lean may come from the prices rather than the splits. The regression (family B), which allows for the price level, leans the same way. Neither is anywhere near the bar.
- **"New York" is the Knicks** (the Nets appear as "Brooklyn"). Adding it as a Knicks alias in `config/teams/nba.csv` would let those games join to Kalshi games; that file is outside this change.
- **Kaggle requests,** all GET and all answered 200: 1 download, 19 searches (one of them for the NBA dataset itself), 7 file lists. The token was read only by the project's code, at run time.

